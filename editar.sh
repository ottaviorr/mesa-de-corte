#!/usr/bin/env bash
# editar.sh — roda a parte determinística. A LIMPEZA semântica (passo 4) é melhor
# feita pelo Claude Code lendo o CLAUDE.md (ele gera trabalho/cortes.txt).
#
# Uso normal (recomendado): abra 'claude' na pasta e peça pra seguir o CLAUDE.md.
# Uso manual: ./editar.sh entrada/SEU_VIDEO.mp4
set -euo pipefail

IN="${1:?Uso: ./editar.sh entrada/SEU_VIDEO.mp4}"

bash scripts/01_normalizar.sh "$IN"
bash scripts/02_cortar_silencio.sh
bash scripts/03_transcrever.sh

echo ""
echo ">> Transcrição pronta em trabalho/transcricao.srt"
echo ">> Para a limpeza inteligente (takes repetidos/recados), gere trabalho/cortes.txt"
echo "   (o Claude Code faz isso lendo o CLAUDE.md). Se cortes.txt não existir,"
echo "   o passo 04 só passa o vídeo adiante."
echo ""

bash scripts/04_limpar.sh
bash scripts/05_montar.sh
bash scripts/06_velocidade.sh

echo ""
echo "==================================================="
echo " PRONTO -> saida/video_final.mp4 (paisagem 16:9, 1,15x)"
echo " Legenda -> trabalho/transcricao.srt (suba no YouTube como CC)"
echo " >> REVISE a 1.5x antes de publicar."
echo "==================================================="
