#!/usr/bin/env bash
# 05_montar.sh — intro + corpo + CTA final. Codec/qualidade = app/encode.py.
# Intro/CTA são casados à RESOLUÇÃO e FPS do CORPO (o que o passo 01 produziu),
# pra o concat bater mesmo em 1440p/4K/60fps.
set -euo pipefail

IN="trabalho/04_limpo.mp4"
OUT="trabalho/05_montado.mp4"
INTRO="assets/intro.mp4"
CTA_FIM="assets/cta_final.mp4"
mkdir -p saida trabalho/montagem

source scripts/_encode.sh   # -> VENC, AENC

# dimensões e fps do corpo (o alvo pra todos os clipes casarem)
FPS=$(ffprobe -v error -select_streams v:0 -show_entries stream=r_frame_rate -of default=nk=1:nw=1 "$IN" 2>/dev/null | awk -F/ 'NF==2{printf "%.4g",$1/$2} NF==1{print $1}')
[ -z "$FPS" ] && FPS=60
W=$(ffprobe -v error -select_streams v:0 -show_entries stream=width  -of default=nk=1:nw=1 "$IN" 2>/dev/null); [ -z "$W" ] && W=1920
H=$(ffprobe -v error -select_streams v:0 -show_entries stream=height -of default=nk=1:nw=1 "$IN" 2>/dev/null); [ -z "$H" ] && H=1080

# helper: padroniza qualquer clipe pro formato do corpo antes de concatenar
norm () {
  ffmpeg -y -i "$1" \
    -vf "scale=${W}:${H}:force_original_aspect_ratio=decrease,pad=${W}:${H}:(ow-iw)/2:(oh-ih)/2,fps=${FPS}" \
    "${VENC[@]}" "${AENC[@]}" -ar 48000 "$2"
}

CORPO="$IN"   # sem overlay de logo no vídeo

SEQ=()
if [[ -f "$INTRO" ]]; then norm "$INTRO" trabalho/montagem/intro.mp4; SEQ+=("trabalho/montagem/intro.mp4"); fi
norm "$CORPO" trabalho/montagem/corpo_n.mp4
SEQ+=("trabalho/montagem/corpo_n.mp4")
if [[ -f "$CTA_FIM" ]]; then norm "$CTA_FIM" trabalho/montagem/ctafim.mp4; SEQ+=("trabalho/montagem/ctafim.mp4"); fi

# caminhos RELATIVOS: o concat resolve cada entrada a partir da pasta da lista, e
# todos os clipes estão lá do lado. Com $PWD absoluto o Git Bash escrevia
# "/c/Users/..." e o ffmpeg nativo do Windows não abria ("Impossible to open").
: > trabalho/montagem/lista.txt
for p in "${SEQ[@]}"; do echo "file '${p##*/}'" >> trabalho/montagem/lista.txt; done
ffmpeg -y -f concat -safe 0 -i trabalho/montagem/lista.txt -c copy "$OUT"

echo "OK -> $OUT (próximo: 06_velocidade.sh aplica a velocidade)"
