#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
zoom.py — propõe e aplica ZOOM de ênfase (punch-in) em pontos que importam.

Ideia: num tutorial de tela, o que "importa" é onde acontece AÇÃO localizada
(clique, digitação, abrir menu). A gente acha esses momentos por diferença de
quadro (atividade) e, quando a ação é LOCALIZADA (não a tela toda mudando),
propõe um zoom suave naquela região. A tela inteira mudando (scroll/troca de
página) NÃO vira zoom — zoom ali não ajuda.

Fluxo:
  analisar_zooms(video) -> lista de zooms [{inicio,fim,zoom,cx,cy,w,h,motivo}]
                           (cx,cy,w,h normalizados 0..1) + thumbnails + json
  construir_filtro(zooms, W, H) -> string -vf do ffmpeg (1 passada, com easing)

Sem dependência além de numpy + ffmpeg.
"""

import json
import os
import subprocess

import numpy as np

# --- parâmetros (ajustáveis por env no pipeline) ---
FPS = 4                  # amostragem da análise (quadros/seg)
AW, AH = 128, 72         # resolução baixa pra análise (rápida)
EVENTO_MIN = 0.4         # ignora pisca-pisca menor que isso (s)
GAP_MERGE = 0.5          # junta atividade separada por menos que isso (s) — pequeno, pra não grudar eventos distintos
ZOOM_DUR_MIN = 2.5       # o evento é curto, mas o zoom FICA pelo menos isso (s)
ZOOM_DUR_MAX = 6.0       # e no máximo isso
PAD = 1.0               # folga somada à duração do evento ao esticar o zoom
ESPACO = 1.2            # silêncio mínimo entre dois zooms (s)
COBERTURA_MAX = 0.45     # no máx 45% do vídeo com zoom
N_MAX = 12               # teto de zooms propostos
AREA_MAX = 0.5           # ação tem que ser localizada: bbox menor que metade da tela
ZOOM_MIN, ZOOM_MAX = 1.08, 1.22   # zoom SUTIL (punch-in leve, não estoura no mouse)
RAMP = 0.5              # segundos de transição suave (entra/sai do zoom)
THUMB_LARG = 360


def _ffprobe_dim(video):
    try:
        out = subprocess.run(
            ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
             '-show_entries', 'stream=width,height', '-of', 'csv=p=0:s=x', video],
            capture_output=True, text=True, timeout=30, check=True).stdout.strip()
        w, h = out.split('x')[:2]
        return int(w), int(h)
    except Exception:
        return 1920, 1080


def _ffprobe_fps(video):
    try:
        r = subprocess.run(
            ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
             '-show_entries', 'stream=r_frame_rate', '-of', 'default=nk=1:nw=1', video],
            capture_output=True, text=True, timeout=30, check=True).stdout.strip()
        num, den = (r.split('/') + ['1'])[:2]
        return float(num) / float(den or 1)
    except Exception:
        return None


def _extrair_frames(video):
    """Lê o vídeo em cinza/baixa resolução via ffmpeg. Devolve array (n,AH,AW)."""
    proc = subprocess.run(
        ['ffmpeg', '-v', 'error', '-i', video,
         '-vf', 'fps=%d,scale=%d:%d,format=gray' % (FPS, AW, AH),
         '-f', 'rawvideo', '-'],
        capture_output=True, check=True)
    arr = np.frombuffer(proc.stdout, dtype=np.uint8)
    n = arr.size // (AW * AH)
    if n < 2:
        return np.zeros((0, AH, AW), dtype=np.int16)
    return arr[:n * AW * AH].reshape(n, AH, AW).astype(np.int16)


def _segmentos_ativos(activity, fps):
    """Acha trechos com atividade sustentada acima de um limiar dinâmico."""
    if activity.size == 0:
        return []
    base = np.median(activity)
    desvio = np.median(np.abs(activity - base)) + 1e-6   # MAD
    limiar = base + 1.2 * desvio
    ativo = activity > max(limiar, 0.4)                   # piso pra ignorar ruído ínfimo

    segs, ini = [], None
    gap = int(round(GAP_MERGE * fps))
    zeros = 0
    for i, a in enumerate(ativo):
        if a:
            if ini is None:
                ini = i
            zeros = 0
        elif ini is not None:
            zeros += 1
            if zeros > gap:
                segs.append((ini, i - zeros + 1))
                ini = None
    if ini is not None:
        segs.append((ini, len(ativo)))
    return segs


def _foco_do_segmento(diff_seg):
    """Centroide e caixa (bbox ponderada) da ação no segmento. Devolve
    (cx,cy,w,h) normalizados 0..1, e a fração de área da caixa."""
    mapa = diff_seg.mean(axis=0)                 # (AH,AW) energia média de mudança
    total = mapa.sum()
    if total <= 0:
        return 0.5, 0.5, 1.0, 1.0, 1.0
    ys, xs = np.arange(AH), np.arange(AW)
    px = mapa.sum(axis=0); py = mapa.sum(axis=1)
    cx = (xs * px).sum() / total
    cy = (ys * py).sum() / total
    # desvio padrão ponderado -> tamanho da caixa (2.5 sigma cobre a ação)
    sx = np.sqrt(((xs - cx) ** 2 * px).sum() / total)
    sy = np.sqrt(((ys - cy) ** 2 * py).sum() / total)
    w = min(1.0, (5.0 * sx) / AW)
    h = min(1.0, (5.0 * sy) / AH)
    area = w * h
    return cx / AW, cy / AH, w, h, area


def _coarse(m, bs):
    """Reduz o mapa por média de blocos bs×bs (pra coerência espacial)."""
    H, W = m.shape
    Hc, Wc = H // bs, W // bs
    return m[:Hc * bs, :Wc * bs].reshape(Hc, bs, Wc, bs).mean((1, 3))


def _componentes(mask):
    """Componentes conexos (4-viz) numa grade pequena — sem depender de scipy."""
    Hc, Wc = mask.shape
    vis = np.zeros_like(mask, bool)
    comps = []
    for i in range(Hc):
        for j in range(Wc):
            if mask[i, j] and not vis[i, j]:
                pilha, cur = [(i, j)], []
                vis[i, j] = True
                while pilha:
                    y, x = pilha.pop()
                    cur.append((y, x))
                    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        ny, nx = y + dy, x + dx
                        if 0 <= ny < Hc and 0 <= nx < Wc and mask[ny, nx] and not vis[ny, nx]:
                            vis[ny, nx] = True
                            pilha.append((ny, nx))
                comps.append(cur)
    return comps


def _detectar_camera(frames):
    """Acha a bolha da CÂMERA (webcam) — um bloco compacto, num CANTO, com
    'chão de vídeo ao vivo' (muitos pixels com variação pequena e contínua no
    tempo) E textura fotográfica alta. Isso distingue a câmera tanto da tela
    ESTÁTICA (variação zero) quanto da tela ATIVA (variações grandes/bruscas).
    Devolve (cx,cy,w,h) normalizado 0..1, snapado pro canto com margem, ou None.
    Medido em gravação real (Screen Studio/OBS): câmera tem ~44% de pixels
    'vivos' (1<std<40) contra ~0% na tela."""
    if frames.shape[0] < 8:
        return None
    f = frames.astype(float)
    std = f.std(0)
    gy, gx = np.gradient(f.mean(0))
    tex = np.hypot(gx, gy)
    vivo = ((std > 1) & (std < 40)).astype(float)     # variação pequena e contínua
    bs = 6
    g, gt = _coarse(vivo, bs), _coarse(tex, bs)
    Hc, Wc = g.shape
    mask = (g > 0.30) & (gt > 6)                       # bloco vivo E fotográfico

    melhor = None
    for comp in _componentes(mask):
        ys = [c[0] for c in comp]
        xs = [c[1] for c in comp]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        nx0, nx1 = x0 / Wc, (x1 + 1) / Wc
        ny0, ny1 = y0 / Hc, (y1 + 1) / Hc
        w, h = nx1 - nx0, ny1 - ny0
        dens = len(comp) / float((x1 - x0 + 1) * (y1 - y0 + 1))
        canto = (nx0 <= 0.10 or nx1 >= 0.90) and (ny0 <= 0.10 or ny1 >= 0.90)
        if dens > 0.55 and 0.02 < w * h < 0.33 and w < 0.6 and h < 0.6 and canto:
            if melhor is None or len(comp) > melhor[0]:
                melhor = (len(comp), nx0, nx1, ny0, ny1)

    if melhor is None:
        return None
    _, nx0, nx1, ny0, ny1 = melhor
    # snap pro canto que a bolha encosta + margem generosa (melhor sobrepor um
    # cantinho de tela do que deixar a borda da câmera receber zoom)
    m = 0.07
    if nx1 >= 0.90: nx1 = 1.0
    else: nx1 = min(1.0, nx1 + m)
    if nx0 <= 0.10: nx0 = 0.0
    else: nx0 = max(0.0, nx0 - m)
    if ny1 >= 0.90: ny1 = 1.0
    else: ny1 = min(1.0, ny1 + m)
    if ny0 <= 0.10: ny0 = 0.0
    else: ny0 = max(0.0, ny0 - m)
    return ((nx0 + nx1) / 2.0, (ny0 + ny1) / 2.0, nx1 - nx0, ny1 - ny0)


def analisar_zooms(video, saida_json='trabalho/zooms.json',
                   thumbs_dir='trabalho/zoom_thumbs', log=print,
                   exigir_camera=True):
    W, H = _ffprobe_dim(video)
    frames = _extrair_frames(video)
    if frames.shape[0] < 2:
        log('  (vídeo curto demais pra propor zoom)')
        _escrever([], saida_json, None)
        return []

    diff = np.abs(frames[1:] - frames[:-1])      # (n-1,AH,AW)
    fps = FPS
    dur_total = frames.shape[0] / fps

    # ignora pixels que mudam o tempo TODO (câmera/rosto, animação de fundo) —
    # zoom deve seguir EVENTOS (clique, slide, digitação), não movimento constante.
    freq = (diff > 12).mean(axis=0)
    camera = _detectar_camera(frames)
    if camera is None and exigir_camera:
        log('  (câmera não detectada — zoom NÃO aplicado, pra não zoomar a câmera por engano)')
        _escrever([], saida_json, dur_total, camera=None)
        return []
    if camera:
        log('  câmera detectada no canto — será preservada (só a tela recebe zoom)')
    estavel = (freq < 0.5).astype(np.int16)
    diff = diff * estavel
    activity = diff.mean(axis=(1, 2))

    propostas = []
    for (a, b) in _segmentos_ativos(activity, fps):
        ev_dur = (b - a) / fps
        if ev_dur < EVENTO_MIN:
            continue
        cx, cy, w, h, area = _foco_do_segmento(diff[a:b])
        if area > AREA_MAX:
            continue                              # tela toda mudou -> zoom não ajuda
        # o evento é curto; o zoom fica em cena ZOOM_DUR_MIN..MAX, centrado nele
        meio = (a + b) / 2.0 / fps
        zdur = float(np.clip(ev_dur + PAD, ZOOM_DUR_MIN, ZOOM_DUR_MAX))
        ini = max(0.0, meio - zdur / 2.0)
        fim = min(dur_total, ini + zdur)
        ini = max(0.0, fim - zdur)
        alvo = 1.0 / max(w, h, 1e-3) ** 0.5       # caixa menor -> mais zoom (com teto)
        zoom = float(np.clip(alvo, ZOOM_MIN, ZOOM_MAX))
        propostas.append({
            'inicio': round(ini, 2), 'fim': round(fim, 2),
            'zoom': round(zoom, 2),
            'cx': round(float(cx), 3), 'cy': round(float(cy), 3),
            'w': round(float(w), 3), 'h': round(float(h), 3),
            'forca': float(activity[a:b].mean()),
            'motivo': 'ação localizada (%.0f%% da tela) — zoom %.2fx' % (area * 100, zoom),
        })

    # prioriza os mais "ativos"; descarta sobreposição (fica o mais forte) e
    # respeita espaçamento, teto de quantidade e de cobertura total.
    propostas.sort(key=lambda z: -z['forca'])
    aceitos, cobertura = [], 0.0
    for z in propostas:
        if len(aceitos) >= N_MAX:
            break
        d = z['fim'] - z['inicio']
        if dur_total and (cobertura + d) > dur_total * COBERTURA_MAX:
            continue
        conflito = any(z['inicio'] < x['fim'] + ESPACO and x['inicio'] < z['fim'] + ESPACO
                       for x in aceitos)
        if conflito:
            continue
        aceitos.append(z); cobertura += d
    aceitos.sort(key=lambda z: z['inicio'])
    for z in aceitos:
        z.pop('forca', None)

    if aceitos:
        _gerar_thumbnails(video, aceitos, thumbs_dir, W, H, log=log)
    _escrever(aceitos, saida_json, dur_total, camera=camera)
    log('OK -> %d zooms propostos (%.0fs de %.0fs)' % (len(aceitos), cobertura, dur_total))
    return aceitos


def _escrever(zooms, saida_json, dur, camera=None):
    os.makedirs(os.path.dirname(saida_json) or '.', exist_ok=True)
    cam = None
    if camera:
        cam = {'cx': round(camera[0], 3), 'cy': round(camera[1], 3),
               'w': round(camera[2], 3), 'h': round(camera[3], 3)}
    with open(saida_json, 'w', encoding='utf-8') as f:
        json.dump({'zooms': zooms, 'duracao': dur, 'camera': cam},
                  f, ensure_ascii=False, indent=2)


def ler_camera(caminho='trabalho/zooms.json'):
    try:
        return json.load(open(caminho, encoding='utf-8')).get('camera')
    except (OSError, ValueError):
        return None


def _gerar_thumbnails(video, zooms, thumbs_dir, W, H, log=print):
    """Salva um thumbnail por zoom com a CAIXA do zoom desenhada — é o
    'me mostre onde' da revisão."""
    os.makedirs(thumbs_dir, exist_ok=True)
    for i, z in enumerate(zooms):
        t = (z['inicio'] + z['fim']) / 2.0
        bw, bh = z['w'] * W, z['h'] * H
        bx = max(0, min(W - bw, z['cx'] * W - bw / 2))
        by = max(0, min(H - bh, z['cy'] * H - bh / 2))
        vf = ("drawbox=x=%d:y=%d:w=%d:h=%d:color=orange@0.9:t=5,"
              "scale=%d:-2" % (bx, by, bw, bh, THUMB_LARG))
        try:
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', '%.2f' % t,
                            '-i', video, '-frames:v', '1', '-vf', vf,
                            os.path.join(thumbs_dir, 'z%03d.jpg' % i)],
                           check=True, timeout=60)
        except Exception as e:
            log('  (thumb do zoom %d falhou: %s)' % (i, e))


def construir_filtro(zooms, W, H, fps=None):
    """Monta o -vf do ffmpeg (filtro ZOOMPAN) que aplica todos os zooms numa
    passada só, com transição suave (entra em RAMP s, segura, sai em RAMP s).
    USA ZOOMPAN e não `crop`: no crop, as expressões de w/h são avaliadas UMA vez
    na init (t=0, rampa=0) — então o crop NUNCA zoomava. O zoompan reavalia o
    zoom a cada quadro. `fps` deve casar com a fonte (senão o zoompan reamostra
    pra 25 e quebra o A/V)."""
    if not zooms:
        return None
    z_terms, cx_terms, cy_terms = [], [], []
    for z in zooms:
        a, b, Z = z['inicio'], z['fim'], z['zoom']
        cxp = max(0.0, min(1.0, z['cx'])) * W
        cyp = max(0.0, min(1.0, z['cy'])) * H
        env = ("min(min((time-%.3f)/%.3f,1),min((%.3f-time)/%.3f,1))" % (a, RAMP, b, RAMP))
        gate = "between(time,%.3f,%.3f)" % (a, b)
        z_terms.append("+%.4f*if(%s,%s,0)" % (Z - 1.0, gate, env))
        cx_terms.append("+if(%s,%.2f,0)" % (gate, cxp))    # centro fixo na janela
        cy_terms.append("+if(%s,%.2f,0)" % (gate, cyp))
    zexpr = "(1" + "".join(z_terms) + ")"
    cxexpr = "(0" + "".join(cx_terms) + ")"
    cyexpr = "(0" + "".join(cy_terms) + ")"
    # zoompan: x,y são o canto do recorte na imagem JÁ ampliada (×zoom).
    x = "clip(%s*zoom-ow/2,0,iw*zoom-ow)" % cxexpr
    y = "clip(%s*zoom-oh/2,0,ih*zoom-oh)" % cyexpr
    fpspart = (":fps=%s" % _fps_str(fps)) if fps else ""
    return ("zoompan=z='%s':x='%s':y='%s':d=1:s=%dx%d%s"
            % (zexpr, x, y, W, H, fpspart))


def _fps_str(fps):
    return ('%.4f' % fps).rstrip('0').rstrip('.')


def construir_filtergraph(zooms, W, H, camera=None, fps=None):
    """Como aplicar os zooms no ffmpeg:
      ('vf', vf)                  -> use  -vf vf
      ('complex2', graph, '[v]')  -> use  -i body -i body -filter_complex graph -map [v]
    Com câmera, usa DOIS inputs (o mesmo vídeo): o input 0 recebe o zoompan (só a
    tela amplia) e o input 1 doa a bolha da câmera no tamanho/posição originais,
    sobreposta por cima — então a câmera NÃO amplia junto."""
    vf = construir_filtro(zooms, W, H, fps)
    if vf is None:
        return None
    if not camera:
        return ('vf', vf)
    cw = max(2, (int(round(camera['w'] * W)) // 2) * 2)
    ch = max(2, (int(round(camera['h'] * H)) // 2) * 2)
    cx = int(round(camera['cx'] * W - cw / 2.0))
    cy = int(round(camera['cy'] * H - ch / 2.0))
    cx = max(0, min(W - cw, cx))
    cy = max(0, min(H - ch, cy))
    graph = ("[0:v]%s[z];[1:v]crop=%d:%d:%d:%d[c];[z][c]overlay=%d:%d[v]"
             % (vf, cw, ch, cx, cy, cx, cy))
    return ('complex2', graph, '[v]')


def ler_zooms(caminho='trabalho/zooms.json'):
    try:
        return json.load(open(caminho, encoding='utf-8')).get('zooms', [])
    except (OSError, ValueError):
        return []


if __name__ == '__main__':
    import sys
    v = sys.argv[1] if len(sys.argv) > 1 else 'trabalho/02_cortado.mp4'
    for z in analisar_zooms(v):
        print('  %5.1f-%5.1f  %.2fx  foco(%.2f,%.2f)  %s'
              % (z['inicio'], z['fim'], z['zoom'], z['cx'], z['cy'], z['motivo']))
