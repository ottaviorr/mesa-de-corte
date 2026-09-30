#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pipeline.py — executa a edição completa chamando os scripts existentes em
scripts/ (que continuam sendo a fonte da verdade), conforme o modo escolhido:

  modo 1: cortar silêncio
  modo 2: cortar silêncio + análise inteligente (takes errados, recados)
  modo 3: modo 1 + acelerar (1.05x–2x)
  modo 4: modo 2 + acelerar (1.05x–2x)

Roda numa thread; o estado vive no dict `job` compartilhado com o servidor.
"""

import codecs
import json
import os
import queue
import re
import shutil
import signal
import subprocess
import threading
import time
import traceback

import analisador
import encode
import zoom as zoom_mod

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# whisper/auto-editor escrevem no pipe; sem isso o Python filho usa cp1252 no
# Windows e morre no primeiro acento/emoji que imprime.
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

# auto-editor e whisper só existem dentro da .venv do projeto. O app costuma ser
# aberto sem a venv ativada (npm run dev / iniciar_app.sh), e aí os scripts .sh
# davam "command not found". Põe a venv na frente do PATH que os filhos herdam.
for _bin in (os.path.join(RAIZ, '.venv', 'Scripts'), os.path.join(RAIZ, '.venv', 'bin')):
    if os.path.isdir(_bin) and _bin not in os.environ.get('PATH', '').split(os.pathsep):
        os.environ['PATH'] = _bin + os.pathsep + os.environ.get('PATH', '')

RE_PORCENTO = re.compile(r'(\d{1,3})(?:\.\d+)?%')
RE_TEMPO = re.compile(r'time=(\d+):(\d+):([\d.]+)')

ROTULOS = {
    'normalizar': 'Preparando vídeo',
    'silencio': 'Caçando silêncios',
    'transcrever': 'Transcrevendo (Whisper PT-BR)',
    'analise': 'Análise inteligente (takes + zoom)',
    'revisao': 'Aguardando sua revisão',
    'limpar': 'Removendo takes errados',
    'zoom': 'Aplicando zoom de ênfase',
    'montagem': 'Montagem (intro + CTA)',
    'velocidade': 'Acelerando',
    'finalizar': 'Finalizando master',
}

PESOS = {'normalizar': 18, 'silencio': 22, 'transcrever': 30, 'analise': 8, 'zoom': 12,
         'limpar': 12, 'montagem': 4, 'velocidade': 10, 'finalizar': 2}


def ffprobe_duracao(caminho):
    try:
        out = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=nk=1:nw=1', caminho],
            capture_output=True, text=True, timeout=30, check=True).stdout.strip()
        return float(out)
    except Exception:
        return None


class Cancelado(Exception):
    pass


class Pipeline:
    def __init__(self, job):
        self.job = job          # dict compartilhado (o servidor lê, nós escrevemos)
        self.proc = None
        self.evento_revisao = threading.Event()

    # ------------------------------------------------------------- log/estado

    def log(self, linha):
        linha = str(linha).rstrip()
        if linha:
            self.job['log'].append(linha)

    def checar_cancelamento(self):
        if self.job.get('cancelar'):
            raise Cancelado()

    def definir_fase(self, chave, fracao_interna=0.0):
        self.job['fase'] = chave
        self.job['rotulo'] = ROTULOS.get(chave, chave)
        base = self.acumulado_ate(chave)
        peso = self.pesos_ativos.get(chave, 0)
        self.job['progresso'] = min(99, round(base + peso * min(1.0, fracao_interna)))

    def acumulado_ate(self, chave):
        total = 0
        for k in self.etapas:
            if k == chave:
                break
            total += self.pesos_ativos.get(k, 0)
        return total

    # --------------------------------------------------------------- execução

    def rodar(self, cmd, fase, dur_referencia=None):
        """Roda um comando capturando saída (linhas \\n e \\r) e estimando
        progresso interno pela % impressa ou pelo time= do ffmpeg.
        Uma thread lê o fd cru e empilha numa fila; o loop principal consome com
        timeout de 0.3s, então o cancelamento é checado nesse intervalo mesmo
        quando o processo fica em silêncio (ex.: whisper carregando).
        (select() não serve: no Windows só funciona com socket, não com pipe.)"""
        self.checar_cancelamento()
        self.log('$ ' + ' '.join(cmd))
        self.proc = subprocess.Popen(
            cmd, cwd=RAIZ, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            bufsize=0, start_new_session=(os.name != 'nt'))   # p/ killpg no matar_proc
        stream = self.proc.stdout
        fila = queue.Queue()

        def ler_stream():
            try:
                while True:
                    dados = os.read(stream.fileno(), 65536)
                    fila.put(dados)
                    if not dados:
                        return
            except (OSError, ValueError):
                # stream/fd fechou de forma inesperada — NÃO é motivo pra falhar
                # a edição: trata como fim de saída e deixa o wait() julgar pelo
                # código de saída real do processo. (era a fonte do "I/O
                # operation on closed file" abortando encodes longos.)
                fila.put(b'')

        threading.Thread(target=ler_stream, daemon=True).start()
        decoder = codecs.getincrementaldecoder('utf-8')('replace')  # não quebra char multibyte partido entre leituras
        buffer = ''
        while True:
            if self.job.get('cancelar'):
                self.matar_proc()
                raise Cancelado()
            try:
                dados = fila.get(timeout=0.3)
            except queue.Empty:
                if self.proc.poll() is not None:
                    break
                continue
            if not dados:
                break
            buffer += decoder.decode(dados)
            while True:
                m = re.search(r'[\r\n]', buffer)
                if not m:
                    break
                linha, buffer = buffer[:m.start()], buffer[m.end():]
                self.processar_linha(linha, fase, dur_referencia)
        buffer += decoder.decode(b'', final=True)
        if buffer.strip():
            self.processar_linha(buffer, fase, dur_referencia)
        codigo = self.proc.wait()
        self.proc = None
        if codigo != 0:
            raise RuntimeError('comando falhou (código %d): %s' % (codigo, ' '.join(cmd)))

    def matar_proc(self):
        """Mata o processo E os filhos. Os scripts rodam via bash, que chama
        ffmpeg/auto-editor: matar só o bash deixava o ffmpeg órfão encodando
        (e travando os arquivos de trabalho/) depois do "cancelar"."""
        if self.proc is None:
            return
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(self.proc.pid), '/T', '/F'],
                           capture_output=True)
        else:
            try:
                os.killpg(self.proc.pid, signal.SIGTERM)   # grupo criado no Popen
            except ProcessLookupError:
                pass
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()

    def fechar_proc(self):
        """Garante que nenhum subprocesso/stream fique pendurado ao sair."""
        try:
            if self.proc is not None and self.proc.poll() is None:
                self.matar_proc()
            if self.proc is not None and self.proc.stdout:
                self.proc.stdout.close()
        except Exception:
            pass
        self.proc = None

    def processar_linha(self, linha, fase, dur_referencia):
        linha = linha.strip()
        if not linha:
            return
        if linha.startswith('>>'):      # anúncio de etapa dos scripts: sempre vai pro log
            self.log(linha)             # (o "threshold=1.3%" era engolido como progresso)
            return
        fracao = None
        m = RE_TEMPO.search(linha)
        if m and dur_referencia:
            t = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
            fracao = t / max(0.1, dur_referencia)
        else:
            m = RE_PORCENTO.search(linha)
            if m:
                fracao = int(m.group(1)) / 100.0
                # o auto-editor mostra 2 barras 0-100% (analisar o áudio, rápida;
                # depois exportar) — sem isso a barra do app enchia e voltava a zero
                if fase == 'silencio':
                    fracao = 0.2 * fracao if 'Analyzing' in linha else 0.2 + 0.8 * fracao
        if fracao is not None:
            # linhas de progresso (time=/xx%) repetem centenas de vezes; só atualizam a barra
            self.definir_fase(fase, fracao)
        else:
            self.log(linha)

    def mover(self, origem, destino):
        """Passa o vídeo adiante sem copiar (renomeia — instantâneo, mesmo disco).
        Só use quando `origem` não for mais lida depois: copiar 3x um vídeo de
        1 GB no fim do modo 1 era ~3 GB gravados à toa."""
        os.replace(os.path.join(RAIZ, origem), os.path.join(RAIZ, destino))
        self.log('(movido: %s -> %s)' % (origem, destino))

    # -------------------------------------------------------------- pipeline

    # mapeia o dict job['qualidade'] (escolhas da UI) -> variáveis MOTOR_* que os
    # scripts e o app/encode.py leem. Limpa antes pra um job não herdar do outro.
    _MAPA_QUALIDADE = {
        'vcodec': 'MOTOR_VCODEC', 'rate_mode': 'MOTOR_RATE_MODE',
        'crf': 'MOTOR_CRF', 'vbitrate': 'MOTOR_VBITRATE', 'preset': 'MOTOR_PRESET',
        'acodec': 'MOTOR_ACODEC', 'audio_bitrate': 'MOTOR_AUDIO_BITRATE',
        'res': 'MOTOR_RES', 'fps': 'MOTOR_FPS',
    }

    def _aplicar_env_qualidade(self):
        q = self.job.get('qualidade') or {}
        for envk in self._MAPA_QUALIDADE.values():
            os.environ.pop(envk, None)
        for k, envk in self._MAPA_QUALIDADE.items():
            v = q.get(k)
            if v not in (None, ''):
                os.environ[envk] = str(v)
        self.log('Qualidade de saída: ' + encode.resumo())

    def executar(self):
        job = self.job
        modo = job['modo']
        velocidade = job['velocidade'] if modo in (3, 4) else 1.0
        inteligente = modo in (2, 4)
        zoom_on = bool(job.get('zoom'))
        analisar_algo = inteligente or zoom_on
        quer_thumb = job.get('gerar_thumb', True)
        # a transcrição alimenta os cortes de IA, a legenda E os prompts de thumb;
        # por isso ela roda também no CH·01/03 quando o material de thumb é pedido.
        transcrever = inteligente or job.get('legenda') or quer_thumb

        self.etapas = ['normalizar', 'silencio']
        if transcrever:
            self.etapas.append('transcrever')
        if analisar_algo:
            self.etapas.append('analise')
        if inteligente:
            self.etapas.append('limpar')
        if zoom_on:
            self.etapas.append('zoom')
        tem_assets = job.get('montagem') and any(
            os.path.isfile(os.path.join(RAIZ, 'assets', a))
            for a in ('intro.mp4', 'cta_final.mp4'))
        if tem_assets:
            self.etapas.append('montagem')
        if modo in (3, 4):
            self.etapas.append('velocidade')
        self.etapas.append('finalizar')
        self.pesos_ativos = {k: PESOS[k] for k in self.etapas}
        escala = 100.0 / sum(self.pesos_ativos.values())
        self.pesos_ativos = {k: v * escala for k, v in self.pesos_ativos.items()}
        job['etapas'] = [{'chave': k, 'rotulo': ROTULOS[k]} for k in self.etapas]

        # Artefatos de edições anteriores NÃO podem vazar pra esta: um cortes.txt
        # velho seria aplicado pelo 04_limpar.sh com timestamps de outro vídeo;
        # uma legenda velha apareceria como "baixar legenda" desta edição.
        job['legenda_gerada'] = False
        for resto in ('trabalho/cortes.txt', 'trabalho/cortes.json',
                      'trabalho/zooms.json', 'saida/legenda.txt', 'saida/legenda.srt',
                      'saida/thumb.json', 'saida/thumb.txt'):
            try:
                os.remove(os.path.join(RAIZ, resto))
            except OSError:
                pass
        shutil.rmtree(os.path.join(RAIZ, 'trabalho/zoom_thumbs'), ignore_errors=True)
        shutil.rmtree(os.path.join(RAIZ, 'trabalho/verif'), ignore_errors=True)

        try:
            self._aplicar_env_qualidade()
            entrada = job['entrada']
            job['stats'] = {'duracao_original': ffprobe_duracao(os.path.join(RAIZ, entrada))}

            # 1) normalizar
            self.definir_fase('normalizar')
            self.rodar(['bash', 'scripts/01_normalizar.sh', entrada],
                       'normalizar', job['stats']['duracao_original'])

            # 2) silêncio
            self.definir_fase('silencio')
            self.rodar(['bash', 'scripts/02_cortar_silencio.sh'], 'silencio')
            job['stats']['duracao_sem_silencio'] = ffprobe_duracao(
                os.path.join(RAIZ, 'trabalho/02_cortado.mp4'))

            # 3) transcrição
            if transcrever:
                self.definir_fase('transcrever')
                self.rodar(['bash', 'scripts/03_transcrever.sh'], 'transcrever')

            # 4) análise (cortes e/ou zoom) -> revisão -> limpeza -> zoom
            cortes_aplicados, zooms_aplicados = [], []
            if analisar_algo:
                self.definir_fase('analise')
                self.checar_cancelamento()

                cortes = []
                if inteligente:
                    cortes = analisador.analisar(
                        srt=os.path.join(RAIZ, 'trabalho/transcricao.srt'),
                        video=os.path.join(RAIZ, 'trabalho/02_cortado.mp4'),
                        palavras_json=os.path.join(RAIZ, 'trabalho/transcricao.json'),
                        saida_txt=os.path.join(RAIZ, 'trabalho/cortes.txt'),
                        saida_json=os.path.join(RAIZ, 'trabalho/cortes.json'),
                        usar_claude=not job.get('sem_claude'),
                        cancelado=lambda: bool(self.job.get('cancelar')),
                        log=self.log)
                    self.checar_cancelamento()
                    job['cortes'] = cortes

                zooms = []
                if zoom_on:
                    zooms = zoom_mod.analisar_zooms(
                        os.path.join(RAIZ, 'trabalho/02_cortado.mp4'),
                        saida_json=os.path.join(RAIZ, 'trabalho/zooms.json'),
                        thumbs_dir=os.path.join(RAIZ, 'trabalho/zoom_thumbs'),
                        log=self.log)
                    self.checar_cancelamento()
                    job['zooms'] = zooms

                # revisão única, cobrindo cortes E zooms
                if job.get('revisar') and (cortes or zooms):
                    self.definir_fase('revisao')
                    job['rotulo'] = ROTULOS['revisao']
                    self.evento_revisao.wait()      # servidor libera após confirmação
                    self.checar_cancelamento()
                    ic = job.get('cortes_confirmados')
                    if ic is not None and inteligente:
                        cortes = [c for i, c in enumerate(cortes) if i in set(ic)]
                        analisador.escrever_saidas(
                            cortes, os.path.join(RAIZ, 'trabalho/cortes.txt'),
                            os.path.join(RAIZ, 'trabalho/cortes.json'),
                            job['stats'].get('duracao_sem_silencio'))
                        job['cortes'] = cortes
                    iz = job.get('zooms_confirmados')
                    if iz is not None and zoom_on:
                        zooms = [z for i, z in enumerate(zooms) if i in set(iz)]
                        job['zooms'] = zooms

                # 4a) limpeza (remove os cortes)
                if inteligente:
                    cortes_aplicados = cortes
                    self.definir_fase('limpar')
                    if cortes:
                        self.rodar(['bash', 'scripts/04_limpar.sh'], 'limpar',
                                   job['stats'].get('duracao_sem_silencio'))
                        # 4a.1) corte perfeito: 2ª transcrição confere/corrige (Fase B)
                        if job.get('revisao_dupla', True):
                            cortes_aplicados = self._revisar_corte(cortes)
                    else:
                        self.log('(nenhum corte inteligente — vídeo segue como está)')
                        self.mover('trabalho/02_cortado.mp4', 'trabalho/04_limpo.mp4')
                else:
                    self.mover('trabalho/02_cortado.mp4', 'trabalho/04_limpo.mp4')

                # 4b) zoom (sobre o corpo já limpo; tempos remapeados pelos cortes)
                if zoom_on and zooms:
                    self.definir_fase('zoom')
                    zooms_aplicados = self.aplicar_zoom(zooms, cortes_aplicados)
            else:
                self.mover('trabalho/02_cortado.mp4', 'trabalho/04_limpo.mp4')

            # 5) montagem (só se houver assets — senão é re-encode à toa)
            intro_offset = 0.0
            if tem_assets:
                self.definir_fase('montagem')
                self.rodar(['bash', 'scripts/05_montar.sh'], 'montagem')
                # a intro é PREPENDADA ao corpo; a legenda (referente ao corpo)
                # precisa deslocar por essa duração pra continuar sincronizada
                if os.path.isfile(os.path.join(RAIZ, 'assets/intro.mp4')):
                    intro_offset = ffprobe_duracao(
                        os.path.join(RAIZ, 'trabalho/montagem/intro.mp4')) or 0.0
            else:
                self.mover('trabalho/04_limpo.mp4', 'trabalho/05_montado.mp4')

            # 6) velocidade
            os.makedirs(os.path.join(RAIZ, 'saida'), exist_ok=True)
            if modo in (3, 4):
                self.definir_fase('velocidade')
                dur_montado = ffprobe_duracao(os.path.join(RAIZ, 'trabalho/05_montado.mp4'))
                self.rodar(['bash', 'scripts/06_velocidade.sh', '%.2f' % velocidade],
                           'velocidade', (dur_montado or 0) / velocidade or None)
            else:
                self.mover('trabalho/05_montado.mp4', 'saida/video_final.mp4')

            # 7) finalizar: legenda sincronizada + estatísticas
            self.definir_fase('finalizar')
            self.rodar(['bash', 'scripts/07_volume.sh'], 'finalizar',
                       ffprobe_duracao(os.path.join(RAIZ, 'saida/video_final.mp4')))
            # legenda: só nos canais de IA (vem de carona) ou quando o usuário pediu —
            # não emitir só porque transcrevemos pros prompts de thumb.
            if inteligente or job.get('legenda'):
                self.gerar_legenda_sincronizada(
                    cortes_aplicados, velocidade, offset=intro_offset / velocidade)

            job['stats']['duracao_final'] = ffprobe_duracao(
                os.path.join(RAIZ, 'saida/video_final.mp4'))
            job['stats']['n_cortes'] = len(cortes_aplicados)
            job['stats']['n_zooms'] = len(zooms_aplicados)
            do, df = job['stats'].get('duracao_original'), job['stats'].get('duracao_final')
            if do and df:
                job['stats']['tempo_economizado'] = max(0.0, do - df)

            # material de thumbnail (título, textos, prompt de cena, refs) a partir
            # da transcrição — extra opcional; se falhar, o master já está pronto.
            if quer_thumb:
                try:
                    material = analisador.gerar_material_thumb(
                        os.path.join(RAIZ, 'trabalho/transcricao.txt'),
                        usar_claude=not job.get('sem_claude'),
                        cancelado=lambda: bool(self.job.get('cancelar')),
                        log=self.log)
                    job['thumb'] = material
                    if material.get('ok'):
                        self.salvar_material_thumb(material)
                except Exception as e:
                    self.log('(material de thumb falhou: %s)' % e)

            # só o master importa: apaga os vídeos intermediários (GBs) de trabalho/.
            # Transcrição/cortes (.srt/.txt/.json) ficam — são leves e servem pra refinar.
            # Em erro/cancelamento não chega aqui, então sobram pra depurar.
            trab = os.path.join(RAIZ, 'trabalho')
            for nome in os.listdir(trab):
                if nome.endswith('.mp4'):
                    os.remove(os.path.join(trab, nome))
            for pasta in ('montagem', 'zoom_thumbs', 'verif'):
                shutil.rmtree(os.path.join(trab, pasta), ignore_errors=True)

            job['progresso'] = 100
            job['fase'] = 'pronto'
            job['rotulo'] = 'Master pronto'
            self.log('=== PRONTO -> saida/video_final.mp4 ===')
            self.log('>> REVISE assistindo a 1.5x antes de publicar (obrigatório).')

        except Cancelado:
            job['fase'] = 'cancelado'
            job['rotulo'] = 'Cancelado'
            self.log('=== Edição cancelada pelo usuário ===')
        except Exception as e:
            job['fase'] = 'erro'
            job['rotulo'] = 'Erro'
            job['erro'] = str(e) or e.__class__.__name__
            # traceback completo no log -> dá pra ver ONDE quebrou, não só a mensagem
            for linha in traceback.format_exc().rstrip().splitlines():
                self.log(linha)
        finally:
            self.fechar_proc()

    # ------------------------------------------------ corte perfeito (Fase B)

    def _transcrever_para_verificar(self, caminho):
        """Roda o Whisper no vídeo JÁ cortado (2ª transcrição) e devolve o texto,
        ou None se falhar. Usa uma subpasta separada pra não pisar na transcrição
        original."""
        destino = os.path.join(RAIZ, 'trabalho', 'verif')
        os.makedirs(destino, exist_ok=True)
        modelo = os.environ.get('MOTOR_WHISPER_MODEL', 'small')
        try:
            self.rodar(['whisper', caminho, '--language', 'Portuguese',
                        '--model', modelo, '--condition_on_previous_text', 'False',
                        '--output_format', 'txt', '--verbose', 'False',
                        '--output_dir', destino], 'limpar')
        except Exception as e:
            self.log('  (whisper de verificação falhou: %s)' % e)
            return None
        base = os.path.splitext(os.path.basename(caminho))[0]
        try:
            return open(os.path.join(destino, base + '.txt'), encoding='utf-8').read()
        except OSError:
            return None

    def _revisar_corte(self, cortes):
        """Re-transcreve o vídeo cortado, confere contra o que DEVERIA sobrar e,
        se achar trecho perdido, encolhe o corte culpado e recorta UMA vez.
        Devolve os cortes (possivelmente ajustados) e guarda o relatório."""
        palavras = analisador.ler_palavras(os.path.join(RAIZ, 'trabalho/transcricao.json'))
        if not palavras:
            return cortes                      # sem timestamps por palavra: não dá pra conferir
        self.checar_cancelamento()
        self.log('>> Revisando o corte (2ª transcrição de verificação) ...')
        texto = self._transcrever_para_verificar(os.path.join(RAIZ, 'trabalho/04_limpo.mp4'))
        if texto is None:
            return cortes
        rel = analisador.verificar_corte(palavras, cortes, texto, log=self.log)
        self.log('   ' + rel['resumo'])

        if not rel['ok'] and rel['suspeitos']:
            novos, aj = analisador.encolher_cortes_por_perda(cortes, palavras, rel['suspeitos'])
            if aj and novos != cortes:
                self.log('   corrigindo: devolvendo trecho(s) perdido(s) e recortando ...')
                analisador.escrever_saidas(
                    novos, os.path.join(RAIZ, 'trabalho/cortes.txt'),
                    os.path.join(RAIZ, 'trabalho/cortes.json'),
                    self.job['stats'].get('duracao_sem_silencio'))
                self.rodar(['bash', 'scripts/04_limpar.sh'], 'limpar',
                           self.job['stats'].get('duracao_sem_silencio'))
                cortes = novos
                self.job['cortes'] = cortes
                texto2 = self._transcrever_para_verificar(
                    os.path.join(RAIZ, 'trabalho/04_limpo.mp4'))
                if texto2:
                    rel = analisador.verificar_corte(palavras, cortes, texto2, log=self.log)
                    self.log('   após correção: ' + rel['resumo'])
        self.job['revisao_corte'] = rel
        return cortes

    # ---------------------------------------------------------- zoom de ênfase

    def _remapear_zooms(self, zooms, remocoes):
        """Os zooms foram detectados na timeline do 02_cortado; os cortes
        semânticos encurtam essa timeline. Reposiciona cada zoom pra bater com
        o 04_limpo (desconta os trechos removidos; descarta zoom que caiu dentro
        de um corte)."""
        def remap(t):
            removido = 0.0
            for a, b in remocoes:
                if t >= b:
                    removido += b - a
                elif t > a:
                    return None
            return t - removido
        out = []
        for z in zooms:
            ini, fim = remap(z['inicio']), remap(z['fim'])
            if ini is None or fim is None or fim - ini < 1.0:
                continue
            out.append(dict(z, inicio=round(ini, 2), fim=round(fim, 2)))
        return out

    def aplicar_zoom(self, zooms, cortes_aplicados):
        """Aplica os zooms no corpo (trabalho/04_limpo.mp4), numa passada só."""
        body = os.path.join(RAIZ, 'trabalho/04_limpo.mp4')
        remocoes = sorted((c['inicio'], c['fim']) for c in (cortes_aplicados or []))
        zr = self._remapear_zooms(zooms, remocoes)
        if not zr:
            self.log('(zoom: nada a aplicar após os cortes)')
            return []
        W, H = zoom_mod._ffprobe_dim(body)
        fps = zoom_mod._ffprobe_fps(body)              # zoompan precisa casar o fps da fonte
        camera = zoom_mod.ler_camera(os.path.join(RAIZ, 'trabalho/zooms.json'))
        fg = zoom_mod.construir_filtergraph(zr, W, H, camera, fps)
        if fg is None:
            return []
        dur = ffprobe_duracao(body)
        tmp = os.path.join(RAIZ, 'trabalho/04z.mp4')
        if fg[0] == 'vf':
            cmd = ['ffmpeg', '-y', '-i', body, '-vf', fg[1],
                   *encode.venc(), '-c:a', 'copy', tmp]
        else:                                    # com câmera: 2 inputs (o mesmo vídeo) + overlay
            cmd = ['ffmpeg', '-y', '-i', body, '-i', body, '-filter_complex', fg[1],
                   '-map', fg[2], '-map', '0:a?', *encode.venc(), '-c:a', 'copy', tmp]
        self.rodar(cmd, 'zoom', dur)
        os.replace(tmp, body)   # 04_limpo agora tem o zoom; a montagem segue daqui
        self.log('zoom aplicado em %d trecho(s)%s'
                 % (len(zr), ' (câmera preservada)' if camera else ''))
        return zr

    # ------------------------------------------------------ legenda ajustada

    def gerar_legenda_sincronizada(self, cortes, velocidade, offset=0.0):
        """A legenda foi gerada ANTES dos cortes inteligentes e da aceleração.
        Reajusta os timestamps (desconta trechos removidos, divide pela
        velocidade, soma o offset da intro) pra ela bater com o vídeo final."""
        origem = os.path.join(RAIZ, 'trabalho/transcricao.srt')
        destino = os.path.join(RAIZ, 'saida/legenda.txt')
        if not os.path.isfile(origem):
            return
        remocoes = sorted((c['inicio'], c['fim']) for c in (cortes or []))

        def removido_no_corte(t):
            for a, b in remocoes:
                if a < t < b:            # o bloco caiu DENTRO de um corte
                    return True
            return False

        # legenda .txt: só o TEXTO das falas que sobraram no vídeo final,
        # um bloco por linha (sem timestamps). Bom pra descrição/roteiro.
        blocos = analisador.ler_srt(origem)
        saida, n = [], 0
        for b in blocos:
            meio = (b['inicio'] + b['fim']) / 2.0
            if removido_no_corte(meio):
                continue                  # bloco cortado — não entra
            texto = b['texto'].strip()
            if texto:
                n += 1
                saida.append(texto)
        with open(destino, 'w', encoding='utf-8') as f:
            f.write('\n'.join(saida) + '\n')
        self.job['legenda_gerada'] = True
        self.log('Legenda (.txt) -> saida/legenda.txt (%d linhas)' % n)

    # ------------------------------------------------- material de thumbnail

    def salvar_material_thumb(self, m):
        """Grava o material de thumb em saida/: JSON (pro app/reuso) e um .txt
        legível pra copiar direto pro seu gerador de thumb com IA."""
        saida = os.path.join(RAIZ, 'saida')
        os.makedirs(saida, exist_ok=True)
        with open(os.path.join(saida, 'thumb.json'), 'w', encoding='utf-8') as f:
            json.dump(m, f, ensure_ascii=False, indent=2)

        linhas = ['TÍTULO / TEMA DO VÍDEO', m.get('titulo', ''), '',
                  'TEXTO DA THUMB (curto e forte — máx 4 palavras)']
        linhas += ['  • ' + t for t in m.get('textos_thumb', [])]
        linhas += ['', 'SOBRE O QUE É O VÍDEO', m.get('sobre', ''), '',
                   'PROMPT DA CENA (pra IA de imagem)', m.get('prompt_cena', ''), '',
                   'IMAGENS DE REFERÊNCIA (anexe no gerador)']
        linhas += ['  • ' + r for r in m.get('imagens_referencia', [])]
        with open(os.path.join(saida, 'thumb.txt'), 'w', encoding='utf-8') as f:
            f.write('\n'.join(linhas) + '\n')
        self.log('Material de thumb -> saida/thumb.txt')


def iniciar_em_thread(job):
    p = Pipeline(job)
    job['_pipeline'] = p
    t = threading.Thread(target=p.executar, daemon=True)
    t.start()
    return p
