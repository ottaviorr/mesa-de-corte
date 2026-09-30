#!/usr/bin/env bash
# 02_cortar_silencio.sh — remove silêncios/pausas com auto-editor.
# O auto-editor não expõe CRF (só -c:v/-b:v/-c:a/-b:a), então este passo sempre
# codifica em BITRATE alto (intermediário generoso). Nos modos 2/4 ele é
# re-encodado depois no codec/qualidade finais; no modo 1 ele É a saída.
set -euo pipefail

IN="trabalho/01_normalizado.mp4"
OUT="trabalho/02_cortado.mp4"

# THRESHOLD: nível abaixo do qual o trecho é considerado silêncio e cortado.
#   É ABSOLUTO (fração do fundo de escala), então depende do ganho do mic —
#   por isso NÃO é mais um número fixo: app/limiar.py mede o áudio desta
#   gravação e põe o corte no vale entre o ruído de fundo e a fala.
#   HISTÓRICO: 4%->6% picotava a fala; voltou pra 4% e AINDA comia início/fim de
#   palavra — medindo o áudio real, a fala fica em ~-22dB e 4% (-28dB) está
#   DENTRO da faixa da fala. O medido dá ~1,3% (-38dB) neste mic.
#   Pra forçar um valor:  MOTOR_SILENCIO_THRESHOLD=2% ./iniciar_app.sh
THRESHOLD="${MOTOR_SILENCIO_THRESHOLD:-}"
if [ -z "$THRESHOLD" ]; then
  THRESHOLD="$(python3 app/limiar.py "$IN" 2>/dev/null)" || {
    THRESHOLD=1.2%
    echo ">> AVISO: não consegui medir o áudio desta gravação — usando o limiar padrão 1.2%"
  }
fi
# MARGIN: respiro "ANTES,DEPOIS" de cada fala. Assimétrico porque a fala ataca
#   rápido e decai devagar. MEDIDO no áudio real (limiar ~1,4%): 94% dos inícios
#   têm <=33ms de som fraco antes do limiar, e os finais <=67ms de cauda —
#   0.15s/0.2s cobre os dois com folga. O antigo 0.3s simétrico deixava toda
#   pausa <0.6s intacta: ~8% a mais de vídeo parado, sem proteger palavra
#   nenhuma a mais. (O 0.2s que "comia palavra" era com o limiar fixo de 4%.)
MARGIN="${MOTOR_SILENCIO_MARGIN:-0.15s,0.2s}"

# codec/áudio escolhidos na UI (via app/encode.py). auto-editor usa bitrate.
VCODEC="${MOTOR_VCODEC:-libx264}"
ACODEC="${MOTOR_ACODEC:-aac}"
ABV="${MOTOR_AUDIO_BITRATE:-320k}"
VBV="${MOTOR_VBITRATE:-20M}"   # bitrate alto pro intermediário (folga p/ 60fps)

AE_V=(-c:v "$VCODEC")
[ "$VCODEC" != "prores_ks" ] && AE_V+=(-b:v "$VBV")
[ "$VCODEC" = "libx264" ] && AE_V+=(-profile:v high)   # (auto-editor não repassa o profile pro NVENC)

AE_A=(-c:a "$ACODEC")
[ "$ACODEC" = "aac" ] && AE_A+=(-b:a "$ABV")

echo ">> Cortando silêncios (threshold=$THRESHOLD, margin=$MARGIN, codec=$VCODEC ${VBV}) ..."
# Se a flag der erro, rode 'auto-editor --help' (muda entre versões).
auto-editor "$IN" \
  --margin "$MARGIN" \
  --edit "audio:threshold=${THRESHOLD}" \
  "${AE_V[@]}" "${AE_A[@]}" \
  --no-open \
  -o "$OUT"
# --no-open: sem isso o auto-editor abre o vídeo no player do sistema ao terminar

echo "OK -> $OUT"
