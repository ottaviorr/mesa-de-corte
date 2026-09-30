#!/usr/bin/env bash
# _encode.sh — carrega os args de codificação (fonte única: app/encode.py) em
# dois arrays bash: VENC (vídeo) e AENC (áudio). Sourced pelos passos do pipeline.
#   source scripts/_encode.sh   # depois use: ffmpeg ... "${VENC[@]}" "${AENC[@]}"
# Roda a partir da RAIZ do projeto (cwd), como o pipeline e o fluxo clássico fazem.
_ENC_PY="${MOTOR_ENCODE_PY:-app/encode.py}"
eval "VENC=( $(python3 "$_ENC_PY" venc) )"
eval "AENC=( $(python3 "$_ENC_PY" aenc) )"
