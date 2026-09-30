#!/usr/bin/env bash
# 04_limpar.sh — remove os trechos listados em trabalho/cortes.txt (takes repetidos, recados, etc.)
# Se cortes.txt não existir, só passa o vídeo adiante (sem limpeza semântica).
set -euo pipefail

IN="trabalho/02_cortado.mp4"
CORTES="trabalho/cortes.txt"
OUT="trabalho/04_limpo.mp4"

if [[ ! -f "$CORTES" ]]; then
  echo "(sem trabalho/cortes.txt — pulando limpeza semântica)"
  cp "$IN" "$OUT"
  exit 0
fi

DUR=$(ffprobe -v error -show_entries format=duration -of default=nk=1:nw=1 "$IN")

echo ">> Aplicando cortes de trabalho/cortes.txt ..."
python3 - "$IN" "$CORTES" "$OUT" "$DUR" <<'PY'
import sys, subprocess, os
sys.path.insert(0, 'app')
import encode                         # fonte única dos args de codec/qualidade
inp, cortes, out, dur = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4])

rem = []
for line in open(cortes):
    line = line.strip()
    if not line or line.startswith('#'):
        continue
    a, b = line.split()[:2]
    rem.append((float(a), float(b)))
rem.sort()

# keep = tudo que NÃO está nos trechos removidos
keep = []
cur = 0.0
for a, b in rem:
    if a > cur:
        keep.append((cur, a))
    cur = max(cur, b)
if cur < dur:
    keep.append((cur, dur))

venc, aenc = encode.venc(), encode.aenc()

# descarta fragmentos ínfimos
keep = [(a, b) for a, b in keep if b - a >= 0.02]
if not keep:                                  # nada sobrou (não deveria): só re-encoda
    subprocess.run(['ffmpeg', '-y', '-i', inp, *venc, *aenc, out], check=True)
    print('OK (nada a cortar) ->', out); sys.exit(0)

# fps do vídeo -> reconstrói os timestamps sem buracos (mantém A/V travado)
try:
    r = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                        '-show_entries', 'stream=r_frame_rate', '-of',
                        'default=nk=1:nw=1', inp],
                       capture_output=True, text=True, check=True).stdout.strip()
    num, den = (r.split('/') + ['1'])[:2]
    fps = float(num) / float(den or 1)
except Exception:
    fps = 60.0

# PASSE ÚNICO: select/aselect mantêm SÓ os intervalos bons, com os MESMOS tempos
# pra vídeo e áudio; setpts/asetpts recolam a timeline sem gaps. Resultado: corte
# com precisão de frame, voz travada no vídeo, e UM re-encode (não N + concat).
expr = '+'.join('between(t,%.3f,%.3f)' % (a, b) for a, b in keep)
vf = "select='%s',setpts=N/%.6f/TB" % (expr, fps)
af = "aselect='%s',asetpts=N/SR/TB" % expr
subprocess.run(['ffmpeg', '-y', '-i', inp, '-vf', vf, '-af', af,
                *venc, *aenc, out], check=True)
print('OK ->', out)
PY
