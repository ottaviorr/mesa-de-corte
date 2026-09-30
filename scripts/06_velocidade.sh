#!/usr/bin/env bash
# 06_velocidade.sh — acelera o vídeo final mantendo a voz natural (sem ficar aguda)
# e o áudio TRAVADO no vídeo (sem atrasar/adiantar). Codec/qualidade = app/encode.py.
set -euo pipefail

IN="trabalho/05_montado.mp4"
OUT="saida/video_final.mp4"
VEL="${1:-1.15}"   # opcional: ./scripts/06_velocidade.sh 1.2
mkdir -p saida

source scripts/_encode.sh   # -> VENC, AENC

# setpts = 1/VEL acelera o vídeo; atempo = VEL acelera o áudio corrigindo o pitch.
# LC_ALL=C força ponto decimal (locale pt-BR usa vírgula, que quebra o filtergraph).
PTS=$(LC_ALL=C awk "BEGIN{printf \"%.6f\", 1/$VEL}")

echo ">> Aplicando velocidade ${VEL}x (voz natural, áudio travado; $(python3 app/encode.py resumo)) ..."
# aresample=async=1 mantém o áudio ancorado ao vídeo (corrige micro-deriva do atempo).
# +faststart: metadados no início -> player começa a tocar antes de baixar tudo.
ffmpeg -y -i "$IN" \
  -filter_complex "[0:v]setpts=${PTS}*PTS[v];[0:a]atempo=${VEL},aresample=async=1:first_pts=0[a]" \
  -map "[v]" -map "[a]" \
  "${VENC[@]}" "${AENC[@]}" -movflags +faststart \
  "$OUT"

echo "OK -> $OUT (em ${VEL}x)"
