#!/usr/bin/env bash
# 07_volume.sh — deixa o volume no padrão do YouTube (-14 LUFS, pico -1.5 dB).
# O YouTube só ABAIXA vídeo alto, nunca sobe vídeo baixo: a gravação crua sai
# em ~-28 LUFS (medido), 4x mais baixa que os outros vídeos do feed.
# Só VOLUME: sem denoise, sem EQ, sem highpass — o timbre da voz fica igual.
# Vídeo é copiado (sem re-encode); só o áudio passa pelo loudnorm. Leva segundos.
# Pra desligar ou mudar o alvo:  MOTOR_LOUDNESS=off | MOTOR_LOUDNESS=-16
set -euo pipefail

ARQ="saida/video_final.mp4"
ALVO="${MOTOR_LOUDNESS:--14}"
[ "$ALVO" = "off" ] && { echo ">> Volume: desligado (MOTOR_LOUDNESS=off)"; exit 0; }

source scripts/_encode.sh   # -> AENC

echo ">> Ajustando volume pra ${ALVO} LUFS (padrão YouTube; vídeo copiado) ..."
# Passada única (modo dinâmico): o ganho de ~14 dB estouraria os picos, então o
# modo linear cairia no dinâmico de qualquer jeito. aresample: o loudnorm
# trabalha a 192 kHz internamente, volta pra 48 kHz.
TMP="saida/.video_final.volume.mp4"
ffmpeg -y -i "$ARQ" -map 0 -c:v copy \
  -af "loudnorm=I=${ALVO}:TP=-1.5:LRA=11,aresample=48000" \
  "${AENC[@]}" -movflags +faststart "$TMP"
mv -f "$TMP" "$ARQ"

echo "OK -> $ARQ (volume ${ALVO} LUFS)"
