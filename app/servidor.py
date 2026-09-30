#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
servidor.py — Mesa de Corte: interface gráfica local do motor de edição.

Só usa a biblioteca padrão do Python (nada pra instalar). Sobe em
http://localhost:8765 e conversa com app/pipeline.py, que roda os scripts
de scripts/ numa thread.

Uso:  python3 app/servidor.py   (ou ./iniciar_app.sh, que já abre o navegador)
"""

import functools
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# console do Windows é cp1252 e engasga com emoji/acento
for _s in (sys.stdout, sys.stderr):
    _s.reconfigure(encoding='utf-8', errors='replace')

import pipeline

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ESTATICO = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
PORTA = int(os.environ.get('MOTOR_PORTA', '8765'))

EXTENSOES_VIDEO = {'.mp4', '.mov', '.mkv', '.webm', '.m4v', '.avi'}
FASES_ENCERRADAS = {None, 'pronto', 'erro', 'cancelado'}

trava = threading.Lock()
job = {'fase': None}
ultimo_contato = time.time()   # última vez que uma aba pediu /api/status


def job_ativo():
    return job.get('fase') not in FASES_ENCERRADAS


def novo_job(entrada, modo, velocidade, legenda, revisar, montagem, sem_claude,
             zoom, gerar_thumb=True, qualidade=None, revisao_dupla=True):
    return {
        'fase': 'iniciando', 'rotulo': 'Preparando...', 'progresso': 0,
        'entrada': entrada, 'modo': modo, 'velocidade': velocidade,
        'legenda': legenda, 'revisar': revisar, 'montagem': montagem,
        'sem_claude': sem_claude, 'zoom': zoom, 'gerar_thumb': gerar_thumb,
        'qualidade': qualidade or {}, 'revisao_dupla': revisao_dupla,
        'log': deque(maxlen=500), 'cortes': [], 'zooms': [], 'stats': {},
        'erro': None, 'cancelar': False, 'iniciado_em': time.time(),
    }


_VCODECS = {'libx264', 'libx265', 'prores_ks', 'h264_videotoolbox', 'hevc_videotoolbox',
            'h264_nvenc', 'hevc_nvenc'}
_ACODECS = {'aac', 'alac', 'flac'}
_PRESETS = {'ultrafast', 'superfast', 'veryfast', 'faster', 'fast',
            'medium', 'slow', 'slower', 'veryslow'}


def parsear_qualidade(campos):
    """Lê e VALIDA (whitelist) os campos de qualidade do form -> dict pro job.
    Como esses valores viram argumentos do ffmpeg, tudo passa por whitelist;
    o que não bater é omitido e o app/encode.py usa o padrão (máximo)."""
    q = {}

    def por_conjunto(nome, conjunto):
        v = str(campos.get(nome, '')).strip()
        if v in conjunto:
            q[nome] = v

    por_conjunto('vcodec', _VCODECS)
    por_conjunto('rate_mode', {'crf', 'bitrate'})
    por_conjunto('preset', _PRESETS)
    por_conjunto('acodec', _ACODECS)
    por_conjunto('res', {'original', '1080', '1440', '2160'})
    por_conjunto('fps', {'original', '30', '60'})

    crf = str(campos.get('crf', '')).strip()
    if crf.isdigit() and 0 <= int(crf) <= 51:
        q['crf'] = crf
    vb = str(campos.get('vbitrate', '')).strip()
    if re.match(r'^\d+(\.\d+)?[MK]$', vb, re.IGNORECASE):
        q['vbitrate'] = vb.upper()
    ab = str(campos.get('audio_bitrate', '')).strip()
    if re.match(r'^\d+k$', ab, re.IGNORECASE):
        q['audio_bitrate'] = ab.lower()
    return q


def estado_publico():
    with trava:
        ativo = job.get('fase') is not None
        return {
            'fase': job.get('fase') or 'ocioso',
            'rotulo': job.get('rotulo', ''),
            'progresso': job.get('progresso', 0),
            'modo': job.get('modo'),
            'velocidade': job.get('velocidade'),
            'entrada': os.path.basename(job.get('entrada', '')) if ativo else '',
            'decorrido': round(time.time() - job['iniciado_em']) if ativo and job.get('iniciado_em') else 0,
            'log': list(job.get('log', []))[-40:],
            'etapas': job.get('etapas', []),
            'cortes': job.get('cortes', []),
            'zooms': job.get('zooms', []),
            'stats': job.get('stats', {}),
            'erro': job.get('erro'),
            # amarrado ao job atual: não vaza a legenda de uma edição anterior
            'tem_legenda': bool(job.get('legenda_gerada')),
            # material de thumbnail (título, textos, prompt de cena, refs) do job atual
            'thumb': job.get('thumb'),
            # relatório da revisão dupla do corte (Fase B)
            'revisao_corte': job.get('revisao_corte'),
        }


@functools.lru_cache(maxsize=1)
def tem_nvenc():
    """Placa NVIDIA utilizável pelo ffmpeg? Testa encodando 0,1s de verdade —
    o ffmpeg listar o h264_nvenc não garante que exista a placa/driver."""
    try:
        r = subprocess.run(
            ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi',
             '-i', 'color=s=256x256:d=0.1', '-c:v', 'h264_nvenc', '-f', 'null', '-'],
            capture_output=True, timeout=20)
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def diagnostico():
    """Checa se as ferramentas externas estão disponíveis — o front usa isso pra
    avisar (com o setup.sh) o que falta instalar. Whisper é LOCAL (sem chave)."""
    def tem(nome):
        return bool(shutil.which(nome))
    return {
        'ffmpeg': tem('ffmpeg'), 'ffprobe': tem('ffprobe'),
        'whisper': tem('whisper'), 'auto_editor': tem('auto-editor'),
        'claude': tem('claude'),
        'nvenc': tem('ffmpeg') and tem_nvenc(),
        'whisper_model': os.environ.get('MOTOR_WHISPER_MODEL', 'small'),
    }


def parsear_range(header, tamanho):
    """Interpreta um header Range. Devolve (inicio, fim) inclusivos, ou None
    quando o header está ausente OU malformado (aí o chamador responde 200)."""
    if not header:
        return None
    m = re.match(r'bytes=(\d*)-(\d*)$', header.strip())
    if not m or (not m.group(1) and not m.group(2)):
        return None
    if m.group(1):
        inicio = int(m.group(1))
        fim = min(int(m.group(2)), tamanho - 1) if m.group(2) else tamanho - 1
    else:                                            # sufixo: últimos N bytes
        inicio = max(0, tamanho - int(m.group(2)))
        fim = tamanho - 1
    return inicio, fim


def criar_em_entrada(nome):
    """Cria o arquivo em entrada/ de forma ATÔMICA (open 'xb'), achando um nome
    livre. Devolve (file_handle, caminho). NUNCA sobrescreve nada em entrada/
    — nem sob dois uploads simultâneos (o 'xb' falha se o nome já existe)."""
    nome = os.path.basename(nome or 'gravacao.mp4')
    nome = re.sub(r'[^\w.\- ]+', '_', nome, flags=re.UNICODE).strip() or 'gravacao.mp4'
    base, ext = os.path.splitext(nome)
    if ext.lower() not in EXTENSOES_VIDEO:
        ext = '.mp4'
    i = 1
    while True:
        sufixo = '' if i == 1 else '_%d' % i
        destino = os.path.join(RAIZ, 'entrada', '%s%s%s' % (base, sufixo, ext))
        try:
            return open(destino, 'xb'), destino
        except FileExistsError:
            i += 1


def _boundary_do_content_type(content_type):
    """Extrai o boundary de um header multipart/form-data (aceita aspas)."""
    if 'multipart/form-data' not in (content_type or '').lower():
        return None
    m = re.search(r'boundary=(?:"([^"]+)"|([^;]+))', content_type, re.IGNORECASE)
    if not m:
        return None
    return (m.group(1) or m.group(2)).strip()


def parsear_multipart(fp, content_length, boundary, dir_temp):
    """Parser streaming de multipart/form-data — substitui cgi.FieldStorage,
    removido no Python 3.13+. Campos de texto vão pra um dict; o campo de
    ARQUIVO é gravado em disco (tempfile em dir_temp) sem carregar o vídeo
    inteiro na memória. Devolve (campos: dict, arquivo: (filename, caminho_temp)
    ou None). Consome exatamente content_length bytes do socket."""
    sep = b'--' + boundary.encode('latin-1')
    marcador = b'\r\n' + sep            # delimita o fim do corpo de cada parte
    CHUNK = 1024 * 1024
    estado = {'restante': content_length}
    buf = bytearray()

    def encher(minimo):
        while len(buf) < minimo and estado['restante'] > 0:
            dados = fp.read(min(CHUNK, estado['restante']))
            if not dados:
                estado['restante'] = 0
                break
            estado['restante'] -= len(dados)
            buf.extend(dados)

    campos, arquivo = {}, None

    encher(len(sep) + 4)
    idx = buf.find(sep)
    if idx == -1:
        return campos, arquivo
    del buf[:idx + len(sep)]            # pula o preâmbulo até o 1º separador

    while True:
        encher(2)
        if buf[:2] == b'--':            # separador de fechamento -> acabou
            break
        if buf[:2] == b'\r\n':
            del buf[:2]
        while b'\r\n\r\n' not in buf and estado['restante'] > 0:
            encher(len(buf) + CHUNK)
        fim_hdr = buf.find(b'\r\n\r\n')
        if fim_hdr == -1:
            break
        cabec = bytes(buf[:fim_hdr]).decode('utf-8', 'replace')  # filename costuma vir UTF-8
        del buf[:fim_hdr + 4]

        nome = filename = None
        for linha in cabec.split('\r\n'):
            if linha.lower().startswith('content-disposition'):
                mn = re.search(r'name="([^"]*)"', linha)
                mf = re.search(r'filename="([^"]*)"', linha)
                nome = mn.group(1) if mn else None
                filename = mf.group(1) if mf else None

        if filename is not None:
            handle = caminho = None
            if filename.strip():
                fd, caminho = tempfile.mkstemp(dir=dir_temp, suffix='.part')
                handle = os.fdopen(fd, 'wb')
            while True:
                pos = buf.find(marcador)
                if pos != -1:
                    if handle:
                        handle.write(buf[:pos])
                    del buf[:pos + len(marcador)]
                    break
                if estado['restante'] > 0:       # mantém uma cauda do tamanho
                    seguro = len(buf) - len(marcador)   # do marcador p/ não partir
                    if seguro > 0:
                        if handle:
                            handle.write(buf[:seguro])
                        del buf[:seguro]
                    encher(len(buf) + CHUNK)
                else:                            # fim do input sem marcador
                    if handle:
                        handle.write(buf)
                    buf.clear()
                    break
            if handle:
                handle.close()
                if arquivo is None:              # guarda o 1º arquivo enviado
                    arquivo = (filename, caminho)
                else:
                    os.unlink(caminho)
        else:
            while buf.find(marcador) == -1 and estado['restante'] > 0:
                encher(len(buf) + CHUNK)
            pos = buf.find(marcador)
            if pos == -1:
                valor = bytes(buf); buf.clear()
            else:
                valor = bytes(buf[:pos]); del buf[:pos + len(marcador)]
            if nome is not None:
                campos[nome] = valor.decode('utf-8', 'replace')

    while estado['restante'] > 0:               # drena o resto p/ não sujar o keep-alive
        d = fp.read(min(CHUNK, estado['restante']))
        if not d:
            break
        estado['restante'] -= len(d)

    return campos, arquivo


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, formato, *args):   # silencia o log padrão por request
        pass

    # ------------------------------------------------------------ respostas

    def responder_json(self, dados, codigo=200):
        corpo = json.dumps(dados, ensure_ascii=False).encode('utf-8')
        self.send_response(codigo)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(corpo)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(corpo)

    def responder_arquivo(self, caminho, baixar_como=None):
        if not os.path.isfile(caminho):
            return self.responder_json({'erro': 'arquivo não encontrado'}, 404)
        tamanho = os.path.getsize(caminho)
        tipo = mimetypes.guess_type(caminho)[0] or 'application/octet-stream'
        faixa = parsear_range(self.headers.get('Range'), tamanho)
        if faixa is None:                            # ausente OU malformado -> 200
            inicio, fim = 0, tamanho - 1
            self.send_response(200)
        else:
            inicio, fim = faixa
            if inicio >= tamanho:
                self.send_response(416)
                self.send_header('Content-Range', 'bytes */%d' % tamanho)
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            self.send_response(206)
            self.send_header('Content-Range', 'bytes %d-%d/%d' % (inicio, fim, tamanho))
        self.send_header('Content-Type', tipo)
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Length', str(fim - inicio + 1))
        if baixar_como:
            self.send_header('Content-Disposition',
                             'attachment; filename="%s"' % baixar_como)
        self.end_headers()
        with open(caminho, 'rb') as f:
            f.seek(inicio)
            restante = fim - inicio + 1
            while restante > 0:
                bloco = f.read(min(65536, restante))
                if not bloco:
                    break
                try:
                    self.wfile.write(bloco)
                except (BrokenPipeError, ConnectionResetError):
                    return                      # player fechou a conexão; normal
                restante -= len(bloco)

    # ----------------------------------------------------------------- rotas

    def do_GET(self):
        rota = self.path.split('?')[0]
        if rota == '/':
            rota = '/index.html'

        if rota == '/api/status':
            global ultimo_contato
            ultimo_contato = time.time()      # a aba aberta chama isto a cada ~1s
            return self.responder_json(estado_publico())

        if rota == '/api/diagnostico':
            return self.responder_json(diagnostico())

        if rota == '/api/entrada':
            pasta = os.path.join(RAIZ, 'entrada')
            arquivos = sorted(
                (f for f in os.listdir(pasta)
                 if os.path.splitext(f)[1].lower() in EXTENSOES_VIDEO),
                key=lambda f: -os.path.getmtime(os.path.join(pasta, f)))
            return self.responder_json({'arquivos': arquivos})

        if rota == '/video/final':
            return self.responder_arquivo(os.path.join(RAIZ, 'saida/video_final.mp4'))

        if rota == '/baixar/video':
            return self.responder_arquivo(os.path.join(RAIZ, 'saida/video_final.mp4'),
                                          baixar_como='video_final.mp4')

        if rota == '/baixar/legenda':
            return self.responder_arquivo(os.path.join(RAIZ, 'saida/legenda.txt'),
                                          baixar_como='legenda.txt')

        if rota == '/baixar/thumb':
            return self.responder_arquivo(os.path.join(RAIZ, 'saida/thumb.txt'),
                                          baixar_como='thumb.txt')

        if rota.startswith('/zoom/thumb/'):
            m = re.match(r'/zoom/thumb/(\d+)$', rota)
            if m:
                return self.responder_arquivo(os.path.join(
                    RAIZ, 'trabalho/zoom_thumbs', 'z%03d.jpg' % int(m.group(1))))

        # estático (sem path traversal)
        caminho = os.path.normpath(os.path.join(ESTATICO, rota.lstrip('/')))
        if caminho.startswith(ESTATICO) and os.path.isfile(caminho):
            return self.responder_arquivo(caminho)
        return self.responder_json({'erro': 'rota desconhecida'}, 404)

    def do_POST(self):
        rota = self.path.split('?')[0]
        if rota == '/api/iniciar':
            return self.api_iniciar()
        if rota == '/api/confirmar':
            return self.api_confirmar()
        if rota == '/api/cancelar':
            return self.api_cancelar()
        if rota == '/api/reset':
            return self.api_reset()
        return self.responder_json({'erro': 'rota desconhecida'}, 404)

    # ------------------------------------------------------------------- api

    def api_iniciar(self):
        global job
        with trava:
            if job_ativo():
                return self.responder_json(
                    {'erro': 'Já existe uma edição em andamento.'}, 409)

        boundary = _boundary_do_content_type(self.headers.get('Content-Type', ''))
        if not boundary:
            return self.responder_json({'erro': 'envio inválido (esperado multipart)'}, 400)
        try:
            tamanho = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            tamanho = 0
        # o arquivo é gravado em entrada/ (mesmo FS) p/ o os.replace ser atômico
        campos, arquivo = parsear_multipart(
            self.rfile, tamanho, boundary, os.path.join(RAIZ, 'entrada'))

        def campo(nome, padrao=''):
            return campos.get(nome, padrao)

        def descartar_upload():
            if arquivo and os.path.exists(arquivo[1]):
                os.unlink(arquivo[1])

        try:
            modo = int(campo('modo', '1'))
            assert modo in (1, 2, 3, 4)
        except (ValueError, AssertionError):
            descartar_upload()
            return self.responder_json({'erro': 'modo inválido'}, 400)
        try:
            velocidade = round(float(campo('velocidade', '1.15')), 2)
            assert 1.05 <= velocidade <= 2.0
        except (ValueError, AssertionError):
            descartar_upload()
            return self.responder_json({'erro': 'velocidade inválida (1.05–2.0)'}, 400)

        # vídeo: upload novo OU arquivo já em entrada/
        entrada = None
        if arquivo:
            filename, temp = arquivo
            f, destino = criar_em_entrada(filename)   # atômico, não sobrescreve
            f.close()                                 # reserva o nome (arquivo vazio)
            os.replace(temp, destino)                 # move o upload por cima (mesmo FS)
            entrada = os.path.relpath(destino, RAIZ)
        else:
            existente = os.path.basename(campo('arquivo_existente', ''))
            if existente:
                caminho = os.path.join(RAIZ, 'entrada', existente)
                if os.path.isfile(caminho):
                    entrada = os.path.join('entrada', existente)
        if not entrada:
            return self.responder_json({'erro': 'Nenhum vídeo recebido.'}, 400)

        with trava:
            if job_ativo():
                return self.responder_json(
                    {'erro': 'Já existe uma edição em andamento.'}, 409)
            job = novo_job(
                entrada=entrada, modo=modo, velocidade=velocidade,
                legenda=campo('legenda') == '1', revisar=campo('revisar') == '1',
                montagem=campo('montagem', '1') == '1',
                sem_claude=campo('sem_claude') == '1', zoom=campo('zoom') == '1',
                gerar_thumb=campo('thumb', '1') == '1',
                qualidade=parsear_qualidade(campos),
                revisao_dupla=campo('revisao_dupla', '1') == '1')
            pipeline.iniciar_em_thread(job)
        return self.responder_json({'ok': True, 'entrada': entrada})

    def api_confirmar(self):
        tamanho = int(self.headers.get('Content-Length', '0'))
        try:
            dados = json.loads(self.rfile.read(tamanho) or b'{}')
            # aceita {cortes:[...], zooms:[...]} (ou {indices:[...]} legado = cortes)
            bruto_cortes = dados.get('cortes', dados.get('indices', []))
            cortes = [int(i) for i in bruto_cortes]
            zooms = [int(i) for i in dados.get('zooms', [])]
        except (ValueError, TypeError):
            return self.responder_json({'erro': 'corpo inválido'}, 400)
        with trava:
            p = job.get('_pipeline')
            if job.get('fase') != 'revisao' or p is None:
                return self.responder_json({'erro': 'não há revisão pendente'}, 409)
            job['cortes_confirmados'] = cortes
            job['zooms_confirmados'] = zooms
            p.evento_revisao.set()
        return self.responder_json({'ok': True})

    def api_cancelar(self):
        with trava:
            if not job_ativo():
                return self.responder_json({'erro': 'nenhuma edição em andamento'}, 409)
            job['cancelar'] = True
            p = job.get('_pipeline')
            if p is not None:
                p.evento_revisao.set()       # acorda se estiver parado na revisão
        return self.responder_json({'ok': True})

    def api_reset(self):
        """Volta o estado pra 'ocioso' depois que uma edição terminou (pronto/
        erro/cancelado). É o que destrava a UI pra uma nova edição."""
        global job
        with trava:
            if job_ativo():
                return self.responder_json(
                    {'erro': 'edição em andamento — cancele antes'}, 409)
            job = {'fase': None}
        return self.responder_json({'ok': True})


def vigiar_aba(servidor, limite):
    """Fecha o servidor quando nenhuma aba chamou /api/status por `limite`
    segundos E não há edição rodando (nem esperando revisão) — fechar a aba
    basta. Ligado pelo atalho sem terminal (MOTOR_AUTO_FECHAR=segundos)."""
    while True:
        time.sleep(10)
        with trava:
            ativo = job_ativo()
        if not ativo and time.time() - ultimo_contato > limite:
            print('Nenhuma aba aberta há %ds — encerrando.' % limite)
            servidor.shutdown()
            return


def main():
    os.chdir(RAIZ)
    for pasta in ('entrada', 'trabalho', 'saida', 'assets'):
        os.makedirs(os.path.join(RAIZ, pasta), exist_ok=True)
    servidor = ThreadingHTTPServer(('127.0.0.1', PORTA), Handler)
    print('🎬 Mesa de Corte no ar: http://localhost:%d  (Ctrl+C pra parar)' % PORTA)
    auto = int(os.environ.get('MOTOR_AUTO_FECHAR', '0') or 0)
    if auto > 0:
        threading.Thread(target=vigiar_aba, args=(servidor, auto), daemon=True).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print('\nAté a próxima edição!')


if __name__ == '__main__':
    main()
