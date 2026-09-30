#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analisador.py — Passo 4 do pipeline, automatizado.

Lê trabalho/transcricao.srt (e trabalho/transcricao.json, se existir, pra ter
timestamp por PALAVRA) e gera trabalho/cortes.txt + trabalho/cortes.json com os
trechos a REMOVER: recados ao editor, takes repetidos e hesitações.

Duas camadas, que se somam:
  1. Claude CLI (`claude -p`)  -> entende semântica: takes refeitos com palavras
     diferentes, recados sutis, desvios. É a camada forte.
  2. Heurísticas locais        -> determinísticas, rodam sempre. Pegam padrões
     conhecidos (corta/editou, gagueiras, falsas partidas) mesmo sem Claude.

Uso:
  python3 app/analisador.py [--srt CAMINHO] [--video CAMINHO] [--sem-claude]
"""

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
import unicodedata
from difflib import SequenceMatcher

# console do Windows é cp1252 e engasga com emoji/acento
for _s in (sys.stdout, sys.stderr):
    _s.reconfigure(encoding='utf-8', errors='replace')

MARGEM = 0.3            # segundos de respiro em volta de cada corte
JUNTAR_GAP = 0.5        # cortes a menos de 0.5s um do outro viram um só
CORTE_MINIMO = 0.25     # ignora cortes menores que isso
TETO_FRACAO = 0.35      # trava de segurança: nunca remover mais de 35% do vídeo
CLAUDE_TIMEOUT = 600
THUMB_TIMEOUT = 180     # geração do material de thumb é tarefa curta; timeout menor
FALSO_K_MAX = 7         # maior janela (em palavras) de falso começo procurada
FALSO_MIN_DUR = 0.15    # ignora falso começo mais curto que isso (em s)

# ---------------------------------------------------------------- utilidades

def sem_acento(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s)
                   if unicodedata.category(c) != 'Mn')

def normalizar(s):
    """minúsculas, sem acento, sem pontuação — pra comparar takes."""
    s = sem_acento(s.lower())
    s = re.sub(r'[^a-z0-9 ]+', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()

def ts_para_seg(ts):
    h, m, resto = ts.split(':')
    s, ms = resto.split(',')
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0

def fmt_tc(seg):
    m, s = divmod(max(0.0, seg), 60)
    return '%02d:%05.2f' % (int(m), s)

def ler_srt(caminho):
    """Devolve lista de {idx, inicio, fim, texto}."""
    blocos = []
    conteudo = open(caminho, encoding='utf-8').read()
    for bloco in re.split(r'\n\s*\n', conteudo.strip()):
        linhas = [l for l in bloco.splitlines() if l.strip()]
        if len(linhas) < 2:
            continue
        m = re.search(r'(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})',
                      linhas[1] if '-->' in linhas[1] else linhas[0])
        if not m:
            continue
        texto = ' '.join(linhas[2:]) if '-->' in linhas[1] else ' '.join(linhas[1:])
        blocos.append({
            'idx': len(blocos) + 1,
            'inicio': ts_para_seg(m.group(1)),
            'fim': ts_para_seg(m.group(2)),
            'texto': texto.strip(),
        })
    return blocos

def ler_palavras(caminho_json):
    """Timestamps por palavra do whisper (--word_timestamps True), se houver."""
    try:
        dados = json.load(open(caminho_json, encoding='utf-8'))
    except (OSError, ValueError):
        return []
    palavras = []
    for seg in dados.get('segments', []):
        for w in seg.get('words', []):
            palavras.append({'texto': w.get('word', '').strip(),
                             'inicio': float(w['start']), 'fim': float(w['end'])})
    return palavras

def duracao_video(caminho):
    try:
        saida = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=nk=1:nw=1', caminho],
            capture_output=True, text=True, timeout=30, check=True).stdout.strip()
        return float(saida)
    except Exception:
        return None

# ------------------------------------------------------- camada heurística

# Recados pro editor — vocabulário real das gravações do canal.
PADROES_RECADO = [
    r'\bse puder cortar\b',
    r'\bpode(m)? cortar\b',
    r'\bvoce corta\b',
    r'\bcorta[, ]+(editou|edita)\b',
    r'\bcorta (isso|essa parte|esse trecho|aqui|essa)\b',
    r'\b(isso|essa parte|esse trecho) (aqui )?(voce|vc) corta\b',
    r'\bpra (eu|mim) cortar\b',
    r'\bedita (isso|essa parte|aqui|esse)\b',
    r'\bdeixa eu ver o que (voce|vc)\b',
    r'\bdeixa eu ver aqui se\b',
    r'\b(na )?tela menor\b',
    r'\bnao sei se (isso )?(vai )?encaixa',
    r'\bnao sei (em )?que parte (vai )?encaixa',
    r'\bse nao encaixa\b',
    r'\bvou (refazer|gravar de novo|repetir|falar de novo)\b',
    r'\bdeixa eu (refazer|repetir|comecar de novo|gravar de novo)\b',
    r'\bcomo (e )?que (eu )?falo (isso|essa)\b',
    r'\bperdi o raciocinio\b',
    r'\besqueci o que (eu )?ia falar\b',
    r'\b(recado|aviso) pro editor\b',
    r'\bdepois (a gente|voce) (tira|corta|arruma|ajeita)\b',
]
RE_RECADO = [re.compile(p) for p in PADROES_RECADO]

# Hesitações longas que o whisper costuma escrever por extenso.
RE_HESITACAO = re.compile(
    r'\b(e[eé]+h*|[ée]{2,}h*|a[aã]+h*|[ãa]{2,}h*|h?u[mn]m+|ahn+|ehn+)\b')

# Gagueira: a mesma sequência curta de palavras, duas vezes seguidas.
# Ex.: "junta a, junta a," / "o workflow ele, o workflow ele dispara"
RE_GAGUEIRA = re.compile(
    r'\b([a-z0-9]+(?: [a-z0-9]+){0,3})[,.]?\s+\1\b')

FILLERS_COMPARACAO = {'ne', 'enfim', 'entao', 'assim', 'tipo', 'ta', 'ok',
                      'bom', 'olha', 'cara', 'gente', 'aqui', 'la'}

def tokens_essencia(texto_norm):
    return [t for t in texto_norm.split() if t not in FILLERS_COMPARACAO]

def similaridade(a, b):
    return SequenceMatcher(None, a, b).ratio()

def fim_recado_refinado(blocos, i, m_norm, palavras):
    """Devolve (fim, retomada). Em geral o bloco de recado é lixo inteiro
    (retomada=False). MAS quando o take bom recomeça DENTRO do mesmo bloco
    ("...você pode corta, esse mcp aqui permite..."), cortar o bloco todo
    levaria conteúdo válido junto — então o fim para no recado (retomada=True).
    Sinal de take reiniciado: as primeiras palavras depois do recado ecoam
    algo dito nos blocos anteriores (a tentativa abandonada)."""
    b = blocos[i]
    norm = normalizar(b['texto'])
    depois = norm[m_norm.end():].strip().split()
    if len(depois) >= 5:
        eco = ' '.join(depois[:3])
        contexto = ' '.join(normalizar(blocos[j]['texto'])
                            for j in range(max(0, i - 2), i))
        if eco in contexto:
            jan = janela_palavras(palavras, b, m_norm.group(0))
            if jan:
                return jan[1], True
            return estimar_por_proporcao(b, m_norm.start(), m_norm.end())[1], True
    return b['fim'], False

def detectar_recados(blocos, palavras):
    cortes = []
    for i, b in enumerate(blocos):
        norm = normalizar(b['texto'])
        for rx in RE_RECADO:
            m = rx.search(norm)
            if m:
                fim, retomada = fim_recado_refinado(blocos, i, m, palavras)
                cortes.append({
                    'inicio': b['inicio'], 'fim': fim,
                    # se o take bom retoma dentro do mesmo bloco, não pôr margem
                    # no fim (comeria a retomada); senão, bloco inteiro é lixo
                    'tipo': 'recado', 'confianca': 0.9, 'margem_fim': not retomada,
                    'motivo': 'recado ao editor ("%s")' % m.group(0),
                    'trecho': b['texto'], 'origem': 'heuristica',
                })
                break
    return cortes

def detectar_takes_repetidos(blocos):
    """Mesma ideia dita 2+ vezes seguidas: corta as tentativas, mantém a ÚLTIMA."""
    cortes = []
    n = len(blocos)
    for i in range(n - 1):
        norm_i = normalizar(blocos[i]['texto'])
        toks_i = tokens_essencia(norm_i)
        if len(toks_i) < 3:
            continue
        for j in range(i + 1, min(i + 4, n)):
            norm_j = normalizar(blocos[j]['texto'])
            toks_j = tokens_essencia(norm_j)
            if len(toks_j) < 3:
                continue
            sim = similaridade(norm_i, norm_j)
            mesmo_comeco = toks_i[:3] == toks_j[:3]
            # tentativa truncada: bloco curto, terminou em vírgula/reticências,
            # e o seguinte recomeça com as mesmas palavras
            truncada = (mesmo_comeco and j == i + 1
                        and blocos[i]['texto'].rstrip().endswith((',', '...', '-'))
                        and len(toks_i) <= len(toks_j))
            # Frases paralelas de retórica ("pode vender como X / como Y") batem
            # 60-75% de similaridade SEM serem take refeito. Por isso, similaridade
            # sozinha só vale com nota alta; abaixo disso, exige o mesmo começo.
            if sim >= 0.8 or truncada or (mesmo_comeco and sim >= 0.65):
                cortes.append({
                    'inicio': blocos[i]['inicio'], 'fim': blocos[j]['inicio'],
                    'tipo': 'take_repetido', 'margem_fim': False,
                    # similaridade pura é especulativa (frases paralelas se parecem):
                    # só corta se o Claude corroborar. Truncamento é sinal forte.
                    'risco': 'normal' if truncada else 'alto',
                    'confianca': 0.8 if truncada else min(0.85, sim),
                    'motivo': 'take refeito (similaridade %.0f%% com o bloco %d) — mantém a última versão'
                              % (sim * 100, blocos[j]['idx']),
                    'trecho': blocos[i]['texto'], 'origem': 'heuristica',
                })
                break
    return cortes

def janela_palavras(palavras, bloco, texto_alvo):
    """Acha o intervalo de tempo de `texto_alvo` dentro do bloco usando os
    timestamps por palavra. Devolve (inicio, fim) ou None."""
    if not palavras:
        return None
    dentro = [w for w in palavras
              if w['inicio'] >= bloco['inicio'] - 0.2 and w['fim'] <= bloco['fim'] + 0.2]
    alvo = normalizar(texto_alvo).split()
    if not alvo or not dentro:
        return None
    norm_ws = [normalizar(w['texto']) for w in dentro]
    for k in range(len(dentro) - len(alvo) + 1):
        if norm_ws[k:k + len(alvo)] == alvo:
            return dentro[k]['inicio'], dentro[k + len(alvo) - 1]['fim']
    return None

def estimar_por_proporcao(bloco, pos_ini, pos_fim):
    """Sem timestamp por palavra: estima pela posição do caractere no bloco."""
    total = max(1, len(bloco['texto']))
    dur = bloco['fim'] - bloco['inicio']
    return (bloco['inicio'] + dur * pos_ini / total,
            bloco['inicio'] + dur * pos_fim / total)

def detectar_hesitacoes_e_gagueiras(blocos, palavras):
    cortes = []
    for b in blocos:
        norm = normalizar(b['texto'])

        m = RE_HESITACAO.search(norm)
        if m and len(m.group(0)) >= 2:
            jan = janela_palavras(palavras, b, m.group(0))
            if jan is None:
                jan = estimar_por_proporcao(b, m.start(), m.end())
            cortes.append({
                'inicio': jan[0], 'fim': jan[1],
                'tipo': 'hesitacao', 'confianca': 0.6,
                'motivo': 'hesitação ("%s")' % m.group(0),
                'trecho': b['texto'], 'origem': 'heuristica',
            })

        g = RE_GAGUEIRA.search(norm)
        if (g and len(g.group(1)) >= 4 and not eh_enfase(g.group(1))
                and not repeticao_de_enfase(norm, g.group(1))):
            # corta só a PRIMEIRA ocorrência; a repetição (a boa) fica
            jan = janela_palavras(palavras, b, g.group(1))
            if jan is None:
                jan = estimar_por_proporcao(b, g.start(), g.start() + len(g.group(1)))
            cortes.append({
                'inicio': jan[0], 'fim': jan[1],
                'tipo': 'hesitacao', 'confianca': 0.55,
                'motivo': 'gagueira ("%s, %s")' % (g.group(1), g.group(1)),
                'trecho': b['texto'], 'origem': 'heuristica',
            })
    return cortes

def eh_enfase(frase):
    """Repetição proposital pra dar ênfase ("é fácil, é fácil", "não, não") —
    o CLAUDE.md manda NÃO cortar. Padrão típico: predicado curto começando
    com cópula/negação/intensificador."""
    return bool(re.match(r'^(e|eh|nao|muito|bem|sim|olha|vai|isso) ', frase + ' '))

def repeticao_de_enfase(norm, unidade):
    """3+ repetições seguidas = ênfase ("tudo, tudo, tudo"), NÃO corta."""
    u = re.escape(unidade.strip())
    return bool(re.search(r'\b%s\b(?:[ ,.]+%s\b){2,}' % (u, u), norm))

def detectar_falsos_comecos(palavras):
    """Pega o falso começo que o TEXTO do bloco esconde: o apresentador inicia
    uma frase, abandona e refaz ("eu vou fazer que... eu vou fazer questão").
    O Whisper muitas vezes só transcreve a versão boa — mas com
    --condition_on_previous_text False ele mantém a tentativa, e aqui a gente
    acha o prefixo repetido (2+ palavras) cuja cauda diverge ou está truncada
    (que -> questão). Precisa dos timestamps por palavra (JSON do whisper).
    MANTÉM a última tentativa; corta a anterior, com fim cravado (sem margem)."""
    cortes = []
    norm = [normalizar(w['texto']) for w in palavras]
    n = len(norm)
    i = 0
    while i < n - 3:
        achou = False
        for k in range(FALSO_K_MAX, 1, -1):
            if i + 2 * k > n:
                continue
            seg1, seg2 = norm[i:i + k], norm[i + k:i + 2 * k]
            if '' in seg1 or '' in seg2 or seg1[:k - 1] != seg2[:k - 1]:
                continue                       # prefixo (tudo menos a última) tem que bater
            if len(set(seg1)) < 2 or norm[i - 1:i] == norm[i:i + 1]:
                continue                       # palavra repetida (ênfase "tudo tudo"), não falso começo
            ult1, ult2 = seg1[-1], seg2[-1]
            truncada = ult2.startswith(ult1) and len(ult1) >= 2 and ult1 != ult2
            if not (truncada or ult1 != ult2):
                continue                       # idêntico não é falso começo (é ênfase/gagueira)
            if k == 2 and not truncada:
                continue                       # "o crm/o funil" é lista, não falso começo;
                                               # janela de 2 só conta se a palavra foi truncada
            # ênfase: a mesma sequência ainda vem uma 3ª vez ("de novo, de novo, de novo")
            if seg1 == norm[i + 2 * k:i + 3 * k]:
                break
            ini, fim = palavras[i]['inicio'], palavras[i + k]['inicio']
            if fim - ini >= FALSO_MIN_DUR:
                cortes.append({
                    'inicio': ini, 'fim': fim,
                    'tipo': 'take_repetido', 'margem_fim': False,
                    # truncamento (que->questão) é sinal forte e entra sozinho;
                    # divergência pura pode ser fala paralela válida ("criar
                    # sites, criar funis") -> só corta se o Claude corroborar.
                    'risco': 'normal' if truncada else 'alto',
                    'confianca': 0.7 if truncada else 0.6,
                    'motivo': 'falso começo refeito ("%s…")' % ' '.join(seg1),
                    'trecho': ' '.join(seg1), 'origem': 'heuristica',
                })
                i += k
                achou = True
                break
        if not achou:
            i += 1
    return cortes

# ---------------------------------------------------------- camada Claude

PROMPT_CLAUDE = """Você é o editor de vídeo de um canal de tutoriais de GoHighLevel em PT-BR.
Abaixo está a transcrição de uma gravação, em blocos numerados com timestamps em segundos.
O apresentador grava sem parar: erra, refaz frases, e fala recados pro editor no meio.

Identifique os trechos que devem ser REMOVIDOS do vídeo:

1. RECADOS AO EDITOR — frases como "corta", "editou", "edita isso", "deixa eu ver",
   "o que você coloca na tela menor", "não sei se vai encaixar", "isso aqui você corta",
   "essas pausas pra eu cortar". Remova a frase inteira E o trecho atrapalhado em volta.

2. TAKES REPETIDOS — a MESMA ideia aparece 2+ vezes seguidas porque ele errou e refez.
   MANTENHA a ÚLTIMA versão (a boa) e marque as tentativas anteriores pra corte.
   Atenção: as palavras quase nunca são idênticas — pode ser tentativa truncada
   ("o workflow ele... ãã..." e depois "o workflow dispara quando o lead...").

3. HESITAÇÕES LONGAS — "ééé", "ãã", começos de frase abandonados, divagações
   que ele mesmo abandona ("não, deixa pra lá").

NÃO remova (isto é fala VÁLIDA, mesmo que pareça repetição):
 - ênfase intencional: "tudo, tudo, tudo", "muito, muito bom";
 - estruturas paralelas / listas: "você vai criar sites, criar funis, fazer tráfego",
   "o CRM, o funil, o tráfego", "ctrl-c, ctrl-v";
 - reforço retórico: a mesma ideia retomada de propósito mais à frente pra explicar.
O apresentador fala rápido e às vezes repete estrutura de propósito — isso NÃO é erro.
REGRA DE OURO: só marque pra corte quando tiver CERTEZA que foi erro/refação/recado.
Na dúvida, NÃO corte — cortar fala correta é o pior resultado possível; deixar
passar uma hesitação pequena é aceitável.
Prefira cortes CURTOS e cirúrgicos: numa divagação longa, remova só o aparte
claramente abandonado ("parece que eu sou o defensor, enfim"), não o trecho
inteiro em volta — o resto pode ter conteúdo aproveitável.

Use os timestamps dos blocos como referência (pode cortar do meio de um bloco até
o meio de outro se fizer sentido, estimando proporcionalmente pela posição do texto).

Responda APENAS com JSON válido, sem markdown, neste formato exato:
{"cortes": [{"inicio": 42.5, "fim": 53.3, "tipo": "recado|take_repetido|hesitacao",
  "motivo": "explicação curta", "trecho": "o texto que será removido", "confianca": 0.9}]}
Se não houver nada a cortar, responda {"cortes": []}.

TRANSCRIÇÃO:
"""

def montar_prompt(blocos):
    linhas = []
    for b in blocos:
        linhas.append('[%d] %.2f-%.2f | %s' % (b['idx'], b['inicio'], b['fim'], b['texto']))
    return PROMPT_CLAUDE + '\n'.join(linhas)

def extrair_json(texto):
    """Acha o primeiro objeto JSON válido dentro de um texto qualquer."""
    texto = re.sub(r'^```(json)?|```$', '', texto.strip(), flags=re.MULTILINE)
    ini = texto.find('{')
    if ini == -1:
        return None
    decoder = json.JSONDecoder()
    while ini != -1:
        try:
            obj, _ = decoder.raw_decode(texto[ini:])
            return obj
        except ValueError:
            ini = texto.find('{', ini + 1)
    return None

def chamar_claude(prompt, log=print, cancelado=None, timeout=CLAUDE_TIMEOUT):
    """Roda `claude -p` headless com o prompt dado e devolve o texto do campo
    'result' do envelope JSON (string), ou None se o CLI não existe, falhou,
    estourou o tempo ou foi cancelado. Plumbing compartilhada pela análise de
    cortes e pela geração do material de thumb.

    communicate(input=...) escreve+fecha o stdin e LÊ stdout/stderr ao mesmo
    tempo (sem deadlock e sem dois donos do stdin). Um watchdog mata o processo
    se o usuário cancelar ou estourar o timeout, fazendo o communicate retornar."""
    modelo = os.environ.get('MOTOR_CLAUDE_MODEL', '')
    cmd = ['claude', '-p', '--output-format', 'json']
    if modelo:
        cmd += ['--model', modelo]
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)
    except FileNotFoundError:
        log('  (claude CLI não encontrado — seguindo sem ele)')
        return None

    parar = threading.Event()
    def _watchdog():
        inicio = time.monotonic()
        while not parar.wait(0.3):
            if (cancelado and cancelado()) or (time.monotonic() - inicio > timeout):
                proc.kill()
                return
    vigia = threading.Thread(target=_watchdog, daemon=True)
    vigia.start()
    try:
        saida, erro = proc.communicate(prompt)
    except Exception as e:
        proc.kill()
        log('  (claude falhou: %s)' % e)
        return None
    finally:
        parar.set()

    if cancelado and cancelado():
        log('  (claude cancelado pelo usuário)')
        return None
    if proc.returncode != 0:
        log('  (claude demorou/falhou: %s)' % (erro or saida or '?').strip()[:200])
        return None

    envelope = extrair_json(saida)
    resultado = envelope.get('result', '') if isinstance(envelope, dict) else saida
    return resultado if isinstance(resultado, str) else ''


def analisar_com_claude(blocos, log=print, cancelado=None):
    """Chama `claude -p` em modo headless. Devolve lista de cortes (pode ser vazia).
    `cancelado` é um callable opcional: se virar True durante a espera, mata o
    processo e devolve [] (pra UI conseguir cancelar uma análise longa)."""
    resultado = chamar_claude(montar_prompt(blocos), log=log, cancelado=cancelado)
    if resultado is None:
        return []
    dados = extrair_json(resultado)
    if not isinstance(dados, dict) or 'cortes' not in dados:
        log('  (resposta do claude sem JSON de cortes — seguindo só com heurísticas)')
        return []

    cortes = []
    for c in dados['cortes']:
        try:
            ini, fim = float(c['inicio']), float(c['fim'])
        except (KeyError, TypeError, ValueError):
            continue
        if fim <= ini:
            continue
        cortes.append({
            'inicio': ini, 'fim': fim,
            'tipo': c.get('tipo', 'recado'),
            'confianca': float(c.get('confianca', 0.75)),
            'motivo': str(c.get('motivo', ''))[:200],
            'trecho': str(c.get('trecho', ''))[:300],
            'origem': 'claude',
        })
    return cortes

# ----------------------------------------------------- material de thumbnail

PROMPT_THUMB = """Você é o roteirista de thumbnails de um canal de tutoriais de
GoHighLevel em PT-BR, no YouTube, formato paisagem 16:9. Você recebe a TRANSCRIÇÃO de um
vídeo JÁ gravado e produz o material pra criar a thumbnail com IA e escrever o título.

Baseie TUDO no conteúdo real da transcrição (o tema, as ferramentas citadas, o que é ensinado).
Gere:
- titulo: 1 título de YouTube forte em PT-BR (até ~70 caracteres), específico ao que o vídeo
  ensina. Nada de clickbait vazio — promessa clara e verdadeira.
- textos_thumb: 3 opções de TEXTO pra estampar na thumb, cada uma com NO MÁXIMO 4 palavras,
  em CAIXA ALTA, alto impacto e curiosidade (ex: "AGENTE DE IA", "SEM CÓDIGO", "FAÇA ISSO").
- sobre: 1 frase (até ~200 caracteres) dizendo sobre o que é o vídeo — vai alimentar a IA da cena.
- prompt_cena: um prompt em PT-BR descrevendo a CENA da thumbnail pra uma IA de imagem.
  Descreva composição, elementos visuais concretos ligados ao tema, cores, iluminação e o clima
  de uma thumb de alto CTR. NÃO peça texto/letras na imagem (o texto entra depois). Seja concreto.
- imagens_referencia: 3 a 5 sugestões PRÁTICAS de imagens que o apresentador deve anexar como
  referência pra IA (ex: "Seu rosto de frente com expressão de surpresa", "Logo do GoHighLevel
  em PNG de alta resolução", "Print da tela do resultado final"). Baseie no que aparece no vídeo.

Responda APENAS com JSON válido, sem markdown, neste formato exato:
{"titulo": "...", "textos_thumb": ["...", "...", "..."], "sobre": "...",
 "prompt_cena": "...", "imagens_referencia": ["...", "..."]}

TRANSCRIÇÃO:
"""


def _texto_transcricao(caminho, limite=8000):
    """Lê o texto da transcrição (.txt); se faltar, cai pro .srt irmão sem os
    timestamps. Trunca em `limite` chars pra manter o prompt do claude enxuto."""
    try:
        txt = open(caminho, encoding='utf-8').read().strip()
    except OSError:
        txt = ''
    if not txt:
        srt = os.path.splitext(caminho)[0] + '.srt'
        if os.path.isfile(srt):
            txt = ' '.join(b['texto'] for b in ler_srt(srt)).strip()
    return txt[:limite]


def material_thumb_vazio(motivo=''):
    return {'titulo': '', 'textos_thumb': [], 'sobre': '', 'prompt_cena': '',
            'imagens_referencia': [], 'ok': False, 'motivo': motivo}


def gerar_material_thumb(transcricao_txt='trabalho/transcricao.txt',
                         usar_claude=True, cancelado=None, log=print):
    """A partir da transcrição, gera o material pra montar a thumbnail com IA:
    título, textos curtos da thumb, resumo, prompt de cena e sugestões de imagens
    de referência. Usa `claude -p`. Sem claude ou sem transcrição, devolve um dict
    vazio com ok=False (o pipeline segue normal — é um extra, não trava nada)."""
    texto = _texto_transcricao(transcricao_txt)
    if not texto:
        log('  (sem transcrição — material de thumb não gerado)')
        return material_thumb_vazio('sem transcrição')
    if not usar_claude:
        return material_thumb_vazio('claude desligado')

    log('>> Gerando material de thumbnail (título, texto, prompt de cena) ...')
    resultado = chamar_claude(PROMPT_THUMB + texto, log=log,
                              cancelado=cancelado, timeout=THUMB_TIMEOUT)
    if resultado is None:
        return material_thumb_vazio('claude indisponível')
    dados = extrair_json(resultado)
    if not isinstance(dados, dict):
        log('  (resposta do claude sem JSON de thumb)')
        return material_thumb_vazio('resposta inválida')

    def lista_str(v, n, maxlen):
        out = []
        if isinstance(v, list):
            for x in v:
                s = str(x).strip()
                if s:
                    out.append(s[:maxlen])
        return out[:n]

    material = {
        'titulo': str(dados.get('titulo', '')).strip()[:140],
        'textos_thumb': lista_str(dados.get('textos_thumb'), 4, 40),
        'sobre': str(dados.get('sobre', '')).strip()[:400],
        'prompt_cena': str(dados.get('prompt_cena', '')).strip()[:1200],
        'imagens_referencia': lista_str(dados.get('imagens_referencia'), 6, 160),
        'ok': True, 'motivo': '',
    }
    log('   material de thumb gerado (%d textos, %d refs)'
        % (len(material['textos_thumb']), len(material['imagens_referencia'])))
    return material


# ----------------------------------------------------------- consolidação

def consolidar(cortes, duracao, log=print):
    """Aplica margem, junta sobreposições, e respeita o teto de segurança."""
    if not cortes:
        return []
    ajustados = []
    for c in cortes:
        ini = max(0.0, c['inicio'] - MARGEM)
        # NÃO somar margem no fim quando o corte termina colado no take BOM que
        # deve ser mantido (take repetido / recado com retomada): a margem
        # comeria a primeira sílaba da versão boa.
        fim = c['fim'] + (MARGEM if c.get('margem_fim', True) else 0.0)
        if duracao:
            fim = min(fim, duracao)
        if fim - ini >= CORTE_MINIMO:
            ajustados.append(dict(c, inicio=ini, fim=fim))
    ajustados.sort(key=lambda c: c['inicio'])

    unidos = []
    for c in ajustados:
        if unidos and c['inicio'] <= unidos[-1]['fim'] + JUNTAR_GAP:
            ant = unidos[-1]
            ant['fim'] = max(ant['fim'], c['fim'])
            ant['confianca'] = max(ant['confianca'], c['confianca'])
            if c['motivo'] not in ant['motivo']:
                ant['motivo'] += ' + ' + c['motivo']
            if c['trecho'] and c['trecho'] not in ant['trecho']:
                ant['trecho'] = (ant['trecho'] + ' […] ' + c['trecho'])[:400]
            if ant['tipo'] != c['tipo']:
                ant['tipo'] = 'misto'
        else:
            unidos.append(dict(c))

    if duracao:
        total = sum(c['fim'] - c['inicio'] for c in unidos)
        if total > duracao * TETO_FRACAO:
            log('  AVISO: cortes somam %.0fs (%.0f%% do vídeo) — mantendo só os de maior confiança.'
                % (total, 100 * total / duracao))
            unidos.sort(key=lambda c: -c['confianca'])
            aceitos, acumulado = [], 0.0
            for c in unidos:
                d = c['fim'] - c['inicio']
                if acumulado + d <= duracao * TETO_FRACAO:
                    aceitos.append(c)
                    acumulado += d
            unidos = sorted(aceitos, key=lambda c: c['inicio'])
    return unidos

def escrever_saidas(cortes, caminho_txt, caminho_json, duracao):
    rotulos = {'recado': 'recado ao editor', 'take_repetido': 'take repetido',
               'hesitacao': 'hesitação', 'misto': 'trecho misto'}
    with open(caminho_txt, 'w', encoding='utf-8') as f:
        f.write('# cortes.txt — trechos a REMOVER (segundos: inicio fim).\n')
        f.write('# Gerado por app/analisador.py%s\n'
                % (' (video de %.0fs)' % duracao if duracao else ''))
        for i, c in enumerate(cortes, 1):
            f.write('\n# [%d] %s [%s] (%s, conf %.0f%%): %s\n#     "%s"\n%.2f %.2f\n'
                    % (i, rotulos.get(c['tipo'], c['tipo']), fmt_tc(c['inicio']),
                       c['origem'], c['confianca'] * 100, c['motivo'],
                       c['trecho'][:160], c['inicio'], c['fim']))
    with open(caminho_json, 'w', encoding='utf-8') as f:
        json.dump({'cortes': cortes, 'duracao': duracao}, f,
                  ensure_ascii=False, indent=2)

# ------------------------------------------------- corte perfeito (Fase B)

def _snap_borda(t, palavras, lado):
    """Se o tempo t cai DENTRO de uma palavra, encosta na borda dela pela REGRA
    DA MAIORIA (pra não clipar): se o centro da palavra está dentro do trecho a
    remover, inclui a palavra inteira; se está fora, exclui inteira.
    lado='a' é o início da remoção; 'b' é o fim."""
    for w in palavras:
        if w['inicio'] < t < w['fim']:
            centro = (w['inicio'] + w['fim']) / 2.0
            if lado == 'a':        # centro >= a -> palavra é removida (inclui borda esq)
                return w['inicio'] if centro >= t else w['fim']
            else:                  # centro <= b -> palavra é removida (inclui borda dir)
                return w['fim'] if centro <= t else w['inicio']
    return t


def ajustar_bordas_palavra(cortes, palavras, log=print):
    """PROATIVO: encosta as bordas de cada corte no silêncio ENTRE palavras
    (timestamps por palavra do Whisper), pra NUNCA cortar no meio de uma palavra.
    Cortes que encolhem abaixo do mínimo são descartados."""
    if not palavras:
        return cortes
    out, mexidos = [], 0
    for c in cortes:
        a = _snap_borda(c['inicio'], palavras, 'a')
        b = _snap_borda(c['fim'], palavras, 'b')
        if abs(a - c['inicio']) > 1e-3 or abs(b - c['fim']) > 1e-3:
            mexidos += 1
        if b - a >= CORTE_MINIMO:
            out.append(dict(c, inicio=round(a, 3), fim=round(b, 3)))
    if mexidos:
        log('   %d corte(s) encostado(s) no silêncio entre palavras (anti-clipe)' % mexidos)
    return out


def _tokens(texto):
    return [t for t in re.findall(r'\w+', normalizar(texto), re.UNICODE) if t]


def palavras_mantidas(palavras, cortes):
    """Palavras (texto) que DEVERIAM sobrar depois de remover os cortes —
    decidido pelo CENTRO de cada palavra cair fora dos trechos removidos."""
    rem = sorted((c['inicio'], c['fim']) for c in cortes)
    mantidas = []
    for w in palavras:
        centro = (w['inicio'] + w['fim']) / 2.0
        if not any(a <= centro <= b for a, b in rem):
            mantidas.append(w['texto'])
    return mantidas


def verificar_corte(palavras_orig, cortes, texto_final, log=print):
    """REDE DE SEGURANÇA: compara o que DEVERIA sobrar (palavras fora dos cortes)
    com o texto realmente transcrito do vídeo já cortado (2ª transcrição).
    Devolve um relatório. Só marca como suspeito um TRECHO CONTÍGUO perdido
    (>=3 palavras) — mismatch de 1 palavra é ruído normal do Whisper."""
    esperado = _tokens(' '.join(palavras_mantidas(palavras_orig, cortes)))
    obtido = _tokens(texto_final)
    if len(esperado) < 5:
        return {'ok': True, 'cobertura': 1.0, 'esperado': len(esperado),
                'suspeitos': [], 'resumo': 'pouco texto — nada a verificar'}
    sm = SequenceMatcher(None, esperado, obtido, autojunk=False)
    cobertura = sm.ratio()
    suspeitos = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ('delete', 'replace') and (i2 - i1) >= 3:
            suspeitos.append(' '.join(esperado[i1:i2])[:120])
    ok = not suspeitos and cobertura >= 0.85
    resumo = ('corte revisado ✓ (%.0f%% do conteúdo confere)' % (cobertura * 100)
              if ok else '%d trecho(s) possivelmente perdido(s) no corte'
              % len(suspeitos))
    return {'ok': ok, 'cobertura': round(cobertura, 4),
            'esperado': len(esperado), 'suspeitos': suspeitos[:8], 'resumo': resumo}


def encolher_cortes_por_perda(cortes, palavras_orig, suspeitos):
    """AUTO-CORREÇÃO (1 iteração): pra cada trecho suspeito de ter sido perdido,
    SUBTRAI o tempo daquelas palavras de dentro do corte que as removeu (podendo
    dividir o corte em dois), devolvendo o conteúdo. Só encolhe — nunca invade
    conteúdo bom novo."""
    if not suspeitos:
        return cortes, 0
    alvo = set()
    for s in suspeitos:
        alvo.update(_tokens(s))
    perdidos = sorted((w['inicio'] - 0.05, w['fim'] + 0.05) for w in palavras_orig
                      if any(tok in alvo for tok in _tokens(w['texto'])))
    if not perdidos:
        return cortes, 0
    uni = []                                    # une intervalos perdidos próximos
    for a, b in perdidos:
        if uni and a <= uni[-1][1]:
            uni[-1] = (uni[-1][0], max(uni[-1][1], b))
        else:
            uni.append((a, b))

    novos, ajustes = [], 0
    for c in cortes:
        pedacos = [(c['inicio'], c['fim'])]
        for (pa, pb) in uni:                    # subtrai cada perdido dos pedaços
            resto = []
            for (a, b) in pedacos:
                if pb <= a or pa >= b:          # sem sobreposição
                    resto.append((a, b))
                else:
                    ajustes += 1
                    if a < pa:
                        resto.append((a, pa))    # sobra à esquerda do perdido
                    if pb < b:
                        resto.append((pb, b))    # sobra à direita do perdido
            pedacos = resto
        for (a, b) in pedacos:
            if b - a >= CORTE_MINIMO:
                novos.append(dict(c, inicio=round(a, 3), fim=round(b, 3)))
    return novos, ajustes


def analisar(srt='trabalho/transcricao.srt', video='trabalho/02_cortado.mp4',
             palavras_json='trabalho/transcricao.json', usar_claude=True,
             saida_txt='trabalho/cortes.txt', saida_json='trabalho/cortes.json',
             cancelado=None, log=print):
    blocos = ler_srt(srt)
    if not blocos:
        log('Transcrição vazia — nada a cortar.')
        escrever_saidas([], saida_txt, saida_json, None)
        return []
    palavras = ler_palavras(palavras_json)
    duracao = duracao_video(video)

    log('>> Analisando %d blocos de transcrição%s ...'
        % (len(blocos), ' (com timestamps por palavra)' if palavras else ''))

    heuristicos = []
    heuristicos += detectar_recados(blocos, palavras)
    heuristicos += detectar_takes_repetidos(blocos)
    heuristicos += detectar_hesitacoes_e_gagueiras(blocos, palavras)
    heuristicos += detectar_falsos_comecos(palavras)
    log('   heurísticas: %d candidatos' % len(heuristicos))

    do_claude = []
    if usar_claude:
        log('   consultando Claude (análise semântica) ...')
        do_claude = analisar_com_claude(blocos, log=log, cancelado=cancelado)
        log('   claude: %d candidatos' % len(do_claude))

    # Com o Claude ligado:
    #  - heurística que SOBREPÕE um corte do Claude: o span semântico dele vence
    #    (unir os dois tende a engolir o take bom que vem logo depois) -> descarta a heurística;
    #  - heurística de RISCO ALTO (semelhança/divergência — pode pegar fala correta)
    #    sem corroboração do Claude: descarta, pra evitar cortar quando você não errou;
    #  - heurística de alta precisão (recado, gagueira, truncamento): mantém sempre.
    # Sem Claude, nada disso roda e todas as heurísticas valem (recall no modo offline).
    if do_claude:
        def sobrepoe(c):
            return any(c['inicio'] < d['fim'] and d['inicio'] < c['fim']
                       for d in do_claude)
        mantidos, cobertos, sem_corrob = [], 0, 0
        for c in heuristicos:
            if sobrepoe(c):
                cobertos += 1
            elif c.get('risco') == 'alto':
                sem_corrob += 1
            else:
                mantidos.append(c)
        if cobertos:
            log('   %d heurísticos cobertos pelo claude (span dele vence)' % cobertos)
        if sem_corrob:
            log('   %d heurísticos especulativos descartados (sem corroboração do claude)' % sem_corrob)
        heuristicos = mantidos

    finais = consolidar(do_claude + heuristicos, duracao, log=log)
    finais = ajustar_bordas_palavra(finais, palavras, log=log)   # anti-clipe (Fase B)
    escrever_saidas(finais, saida_txt, saida_json, duracao)
    total = sum(c['fim'] - c['inicio'] for c in finais)
    log('OK -> %s (%d cortes, %.1fs removidos)' % (saida_txt, len(finais), total))
    return finais

def main():
    ap = argparse.ArgumentParser(description='Gera trabalho/cortes.txt a partir da transcrição.')
    ap.add_argument('--srt', default='trabalho/transcricao.srt')
    ap.add_argument('--video', default='trabalho/02_cortado.mp4')
    ap.add_argument('--palavras', default='trabalho/transcricao.json')
    ap.add_argument('--saida-txt', default='trabalho/cortes.txt')
    ap.add_argument('--saida-json', default='trabalho/cortes.json')
    ap.add_argument('--sem-claude', action='store_true',
                    help='só heurísticas locais (rápido, offline)')
    ap.add_argument('--thumb', action='store_true',
                    help='gera material de thumbnail da transcrição e sai (não corta)')
    ap.add_argument('--transcricao', default='trabalho/transcricao.txt')
    args = ap.parse_args()

    if args.thumb:
        material = gerar_material_thumb(args.transcricao, usar_claude=not args.sem_claude)
        print(json.dumps(material, ensure_ascii=False, indent=2))
        return

    cortes = analisar(srt=args.srt, video=args.video, palavras_json=args.palavras,
                      usar_claude=not args.sem_claude,
                      saida_txt=args.saida_txt, saida_json=args.saida_json)
    for c in cortes:
        print('  %s -> %s  [%s] %s' % (fmt_tc(c['inicio']), fmt_tc(c['fim']),
                                       c['tipo'], c['motivo'][:80]))

if __name__ == '__main__':
    main()
