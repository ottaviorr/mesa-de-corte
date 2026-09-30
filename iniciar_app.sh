#!/usr/bin/env bash
# iniciar_app.sh — sobe a Mesa de Corte (Vite + React + backend Python).
# `npm run dev` já roda os dois juntos (API em :8765, UI em :8766) e abre o navegador.
#
# --sem-terminal: modo do atalho da área de trabalho ("Mesa de Corte.vbs") —
# sobe só o backend Python, que serve a UI já compilada (app/static) em :8765.
# Não precisa de Node nem de janela aberta.
set -euo pipefail
cd "$(dirname "$0")"
SEM_TERMINAL=0
[ "${1:-}" = "--sem-terminal" ] && SEM_TERMINAL=1

# Venv local (se existir): é onde moram whisper/auto-editor e o python do backend.
# No Windows a venv só cria python.exe, mas os scripts chamam python3 — cria o alias.
if [ -d .venv/Scripts ]; then
  [ -f .venv/Scripts/python3.exe ] || cp .venv/Scripts/python.exe .venv/Scripts/python3.exe
  export PATH="$PWD/.venv/Scripts:$PATH"
  # Os .exe da venv (auto-editor, whisper) gravam o caminho ABSOLUTO do python:
  # se a pasta do projeto for movida, eles saem com código 1 sem dizer nada.
  # Reinstalar sem deps só regenera os lançadores (rápido).
  if ! auto-editor --version >/dev/null 2>&1; then
    echo ">> venv movida de pasta — refazendo lançadores do auto-editor/whisper..."
    python3 -m pip install -q --force-reinstall --no-deps auto-editor openai-whisper || true
  fi
elif [ -d .venv/bin ]; then
  export PATH="$PWD/.venv/bin:$PATH"
fi

# Garante que os binários do pip --user (whisper, auto-editor) estejam no PATH —
# eles são instalados em ~/Library/Python/X.Y/bin (Mac) ou ~/.local/bin (Linux),
# que muitas vezes não está no PATH. Detecta sozinho, sem depender do shell.
PYBIN="$(python3 -c 'import site, os; print(os.path.join(site.getuserbase(), "bin"))' 2>/dev/null || true)"
if [ -n "$PYBIN" ] && [ -d "$PYBIN" ]; then
  export PATH="$PYBIN:$PATH"
fi

# Checagem rápida de dependências — se faltar algo, aponta o setup.sh.
faltando=()
command -v ffmpeg   >/dev/null 2>&1 || faltando+=("ffmpeg")
command -v node     >/dev/null 2>&1 || faltando+=("node")
command -v whisper  >/dev/null 2>&1 || faltando+=("whisper")
command -v auto-editor >/dev/null 2>&1 || faltando+=("auto-editor")
if [ "${#faltando[@]}" -gt 0 ]; then
  echo "⚠  Faltando: ${faltando[*]}"
  echo "   Rode primeiro:  ./setup.sh"
  echo "   (ou instale à mão — veja o README)"
  for dep in "${faltando[@]}"; do            # sem node não dá pra subir a interface
    [ "$dep" = "node" ] && [ "$SEM_TERMINAL" = 0 ] && { echo "   (node é obrigatório — abortando)"; exit 1; }
  done
fi

# no modo atalho, fechar a aba basta: sem aba por 2 min e sem edição rodando, ele sai
[ "$SEM_TERMINAL" = 1 ] && MOTOR_AUTO_FECHAR="${MOTOR_AUTO_FECHAR:-120}" exec python3 app/servidor.py

cd app/ui
# instala as dependências do front na primeira vez
if [[ ! -d node_modules ]]; then
  echo ">> Primeira execução: instalando dependências do front (npm install)..."
  npm install
fi

exec npm run dev
