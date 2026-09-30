#!/usr/bin/env bash
# setup.sh — instala TODAS as dependências do Motor de Edição de uma vez.
# Roda no macOS (Homebrew) e Linux (apt/dnf). Idempotente: pode rodar de novo.
set -uo pipefail

echo "════════════════════════════════════════════════"
echo "  Mesa de Corte — instalação de dependências"
echo "════════════════════════════════════════════════"

ok()   { printf "  \033[32m✓\033[0m %s\n" "$1"; }
info() { printf "  \033[33m›\033[0m %s\n" "$1"; }
erro() { printf "  \033[31m✗\033[0m %s\n" "$1"; }

SO="$(uname -s)"

# ---- 1) ffmpeg (traz o ffprobe junto) ----
if command -v ffmpeg >/dev/null 2>&1; then
  ok "ffmpeg já instalado ($(ffmpeg -version | head -1 | awk '{print $3}'))"
else
  info "instalando ffmpeg..."
  if [ "$SO" = "Darwin" ]; then
    if command -v brew >/dev/null 2>&1; then brew install ffmpeg
    else erro "Homebrew não encontrado. Instale em https://brew.sh e rode de novo."; fi
  elif command -v apt-get >/dev/null 2>&1; then sudo apt-get update && sudo apt-get install -y ffmpeg
  elif command -v dnf >/dev/null 2>&1; then sudo dnf install -y ffmpeg
  else erro "instale o ffmpeg manualmente pro seu sistema."; fi
fi

# ---- 2) Node (pra interface Vite+React) ----
if command -v node >/dev/null 2>&1; then
  ok "node já instalado ($(node --version))"
else
  info "instalando node..."
  if [ "$SO" = "Darwin" ] && command -v brew >/dev/null 2>&1; then brew install node
  elif command -v apt-get >/dev/null 2>&1; then sudo apt-get install -y nodejs npm
  else erro "instale o Node em https://nodejs.org e rode de novo."; fi
fi

# ---- 3) Python: auto-editor + openai-whisper (Whisper roda LOCAL, sem chave) ----
if command -v python3 >/dev/null 2>&1; then
  ok "python3 já instalado ($(python3 --version | awk '{print $2}'))"
  info "instalando auto-editor + openai-whisper (pip --user)..."
  python3 -m pip install --user --upgrade auto-editor openai-whisper \
    && ok "auto-editor + whisper ok" \
    || erro "falha no pip — veja a mensagem acima."
else
  erro "python3 não encontrado. Instale o Python 3 e rode de novo."
fi

# ---- 4) PATH dos binários do pip (whisper/auto-editor) ----
PYBIN="$(python3 -c 'import site, os; print(os.path.join(site.getuserbase(), "bin"))' 2>/dev/null || true)"
if [ -n "$PYBIN" ] && [ -d "$PYBIN" ]; then
  case ":$PATH:" in
    *":$PYBIN:"*) ok "PATH do pip já configurado" ;;
    *) info "os binários do pip estão em: $PYBIN"
       info "o ./iniciar_app.sh já adiciona esse caminho sozinho ao subir." ;;
  esac
fi

# ---- 5) dependências do front ----
if [ -d app/ui ]; then
  info "instalando dependências do front (npm install)..."
  (cd app/ui && npm install >/dev/null 2>&1) && ok "front pronto" || erro "npm install falhou"
fi

# ---- 6) Claude CLI (opcional — análise semântica dos cortes/thumb) ----
if command -v claude >/dev/null 2>&1; then
  ok "Claude CLI presente (análise inteligente + prompts de thumb ligados)"
else
  info "Claude CLI ausente (opcional): sem ele, roda só com as heurísticas locais."
  info "  instale em https://claude.ai/code se quiser a análise semântica."
fi

echo
echo "  Pronto!  Rode:  ./iniciar_app.sh"
echo "  (abre http://localhost:8766 no navegador)"
