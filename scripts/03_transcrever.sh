#!/usr/bin/env bash
# 03_transcrever.sh — transcreve PT-BR (Whisper) em arquivo. NÃO queima no vídeo.
set -euo pipefail

IN="trabalho/02_cortado.mp4"

echo ">> Transcrevendo PT-BR (Whisper) ..."
# NOTA: esta versão do whisper só respeita o ÚLTIMO --output_format, então passar
# "srt" e "txt" separados gera só o txt. Use "all" pra garantir o .srt (com timestamps).
# --word_timestamps True grava o tempo de CADA PALAVRA no .json — o analisador
# (app/analisador.py) usa isso pra cortar gagueiras/hesitações com precisão.
# --condition_on_previous_text False: sem isso o Whisper "conserta" a fala usando
# o contexto e ENGOLE os começos abandonados ("eu vou fazer que... eu vou fazer
# questão") — justo o que a gente quer cortar. Com False ele transcreve mais
# literal, então o analisador enxerga o falso começo e corta.
MODELO="${MOTOR_WHISPER_MODEL:-small}"
whisper "$IN" --language Portuguese --model "$MODELO" \
  --word_timestamps True \
  --condition_on_previous_text False \
  --output_format all --verbose False --output_dir trabalho

BASE="$(basename "${IN%.*}")"
mv -f "trabalho/${BASE}.srt" "trabalho/transcricao.srt"
mv -f "trabalho/${BASE}.txt" "trabalho/transcricao.txt"
mv -f "trabalho/${BASE}.json" "trabalho/transcricao.json" 2>/dev/null || true

echo "OK -> trabalho/transcricao.srt  e  trabalho/transcricao.txt"
echo "   (esse .srt você pode subir no YouTube como legenda/CC)"
