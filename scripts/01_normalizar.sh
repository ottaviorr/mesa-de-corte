#!/usr/bin/env bash
# 01_normalizar.sh — padroniza só o VÍDEO (paisagem, resolução/fps escolhidos).
# ÁUDIO: passa do jeito que veio (nenhum filtro — sem loudnorm, sem highpass,
# sem denoise). AAC é só copiado; outro codec é re-encodado conforme o escolhido
# pra caber no mp4. Codec/qualidade/áudio vêm de app/encode.py (MOTOR_*).
set -euo pipefail

IN="${1:?Uso: scripts/01_normalizar.sh entrada/SEU_VIDEO.mp4}"
mkdir -p trabalho saida

# args de codec/qualidade/áudio (fonte única) -> arrays VENC e AENC
source scripts/_encode.sh

# RESOLUÇÃO: 'original' preserva a do arquivo (só garante dimensões pares);
# 1080/1440/2160 encaixam em 16:9 com letterbox se precisar.
RES="${MOTOR_RES:-original}"

# ATALHO DE VELOCIDADE: se a resolução e o fps são os ORIGINAIS, não precisa
# re-encodar o vídeo INTEIRO aqui só pra "padronizar" — os passos seguintes
# (corte, velocidade) já re-encodam no codec/qualidade finais. Um stream-copy
# (remux) é instantâneo e evita um re-encode gigante do vídeo todo (era o maior
# gargalo: ~50 min num vídeo de 36 min). Só cai no re-encode quando muda res/fps.
# ...MAS só quando a fonte já está em 8 bits. O resto do pipeline entrega
# yuv420p (app/encode.py) e o libx264 do passo 02 não encoda 10 bits ("high
# profile doesn't support a bit depth of 10"). Screen Studio grava HEVC 10-bit,
# então nesse caso o re-encode aqui é obrigatório — é onde a conversão cabe.
PIXFMT_IN="$(ffprobe -v error -select_streams v:0 -show_entries stream=pix_fmt \
  -of default=nk=1:nw=1 "$IN" 2>/dev/null || true)"
OITO_BITS=0
{ [ "$PIXFMT_IN" = "yuv420p" ] || [ "$PIXFMT_IN" = "yuvj420p" ]; } && OITO_BITS=1
# ...EXCETO com NVENC: o auto-editor do passo 02 com h264/hevc_nvenc lê o HEVC
# 10-bit direto e já entrega 8 bits. MEDIDO (30s da gravação real): normalizar
# + cortar = 24,6s; cortar direto = 8,7s, com os mesmos cortes. Re-encodar aqui
# seria um encode inteiro a mais (e uma geração de compressão a mais).
case "${MOTOR_VCODEC:-libx264}" in *_nvenc) OITO_BITS=1 ;; esac

if [ "$RES" = "original" ] && { [ "${MOTOR_FPS:-original}" = "original" ] || [ -z "${MOTOR_FPS:-}" ]; } \
   && [ "$OITO_BITS" = 1 ]; then
  echo ">> Normalizando (stream-copy — res/fps originais, sem re-encode) ..."
  # sem -movflags +faststart: é intermediário, não vai pra web — evita regravar tudo
  ffmpeg -y -i "$IN" -c copy trabalho/01_normalizado.mp4
  echo "OK -> trabalho/01_normalizado.mp4 (copiado, instantâneo)"
  exit 0
fi
if [ "$OITO_BITS" = 0 ]; then
  echo ">> Fonte em $PIXFMT_IN — convertendo pra 8 bits (sem isso o passo 02 falha)."
fi
# FPS: 'original' preserva (Screen Studio grava 30/60 — não jogar fora!).
FPSFILTRO=""
if [ "${MOTOR_FPS:-original}" != "original" ] && [ -n "${MOTOR_FPS:-}" ]; then
  FPSFILTRO=",fps=${MOTOR_FPS}"
fi

if [ "$RES" = "original" ]; then
  VF="scale=trunc(iw/2)*2:trunc(ih/2)*2${FPSFILTRO}"
else
  case "$RES" in
    1080) W=1920; H=1080 ;;
    1440) W=2560; H=1440 ;;
    2160) W=3840; H=2160 ;;
    *)    W=1920; H=1080 ;;
  esac
  VF="scale=${W}:${H}:force_original_aspect_ratio=decrease,pad=${W}:${H}:(ow-iw)/2:(oh-ih)/2${FPSFILTRO}"
fi

echo ">> Normalizando vídeo de $IN ($(python3 app/encode.py resumo)) ..."
# ÁUDIO: se já é AAC (Screen Studio), só copia — o passo 02 codifica o áudio
# final de qualquer jeito; recodificar aqui era uma geração de perda a mais.
ACODEC_IN="$(ffprobe -v error -select_streams a:0 -show_entries stream=codec_name \
  -of default=nk=1:nw=1 "$IN" 2>/dev/null || true)"
if [ "$ACODEC_IN" = "aac" ]; then AUDIO=(-c:a copy); else AUDIO=("${AENC[@]}"); fi
ffmpeg -y -i "$IN" -vf "$VF" "${VENC[@]}" "${AUDIO[@]}" trabalho/01_normalizado.mp4

echo "OK -> trabalho/01_normalizado.mp4"
