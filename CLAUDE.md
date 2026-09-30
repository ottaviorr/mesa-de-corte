# Mesa de Corte — motor de edição

## Interface gráfica (Mesa de Corte)
Existe um app local em `app/` que roda este MESMO pipeline com 4 modos
(1=só silêncio, 2=+análise IA, 3=1+velocidade, 4=2+velocidade).
- Frontend: **Vite + React** em `app/ui/` (`npm run dev` → UI em :8766, que faz
  proxy de /api,/video,/baixar pro backend). `./iniciar_app.sh` sobe tudo.
- Sem terminal: `Mesa de Corte.vbs` (atalho na área de trabalho / menu Iniciar)
  roda `iniciar_app.sh --sem-terminal` escondido — só o backend em :8765 servindo
  o build de `app/static`. Fecha com `Fechar Mesa de Corte.vbs`. Log: trabalho/app.log.
- Backend: `app/servidor.py` (stdlib, API + serve `app/static` como fallback do
  build), `app/pipeline.py` (orquestra os scripts/), `app/analisador.py` (passo 4:
  heurísticas + `claude -p`).
Se o usuário pedir edição via chat, siga o fluxo abaixo normalmente — o app é só
outro jeito de disparar. Você pode usar `python3 app/analisador.py` pra gerar um
rascunho de cortes.txt e revisar/refinar em cima dele. Se mexer no frontend,
rode `cd app/ui && npm run build` pra atualizar o fallback em `app/static`.

## Contexto
Edito tutoriais de **GoHighLevel (GHL) em português (PT-BR)** pro meu canal no YouTube.
Gravo agora no **Screen Studio** (tela com zoom automático + câmera + mic Fifine).
As gravações têm pausas, hesitações, recados pro editor e takes repetidos (falei errado e refiz).
Foco em **vídeo paisagem (16:9)** pro YouTube. NÃO faço mais Short.

## Objetivo
Pegar a gravação em `entrada/` e devolver em `saida/video_final.mp4`:
paisagem 1080p, sem silêncios, sem takes repetidos, com intro + CTA final (SEM logo estampada), e acelerado pra 1,15x (voz mantida natural).
A legenda é gerada como ARQUIVO (.srt/.txt) mas NÃO é queimada no vídeo.

## Stack
- `ffmpeg` / `ffprobe` — base
- `auto-editor` — corte de silêncios
- `openai-whisper` — transcrição PT-BR

## Pastas
- `entrada/`  → gravação bruta (NUNCA apagar o original)
- `trabalho/` → intermediários (pode apagar)
- `saida/`    → entregáveis
- `assets/`   → intro.mp4, cta_final.mp4 (opcionais)
- `scripts/`  → o pipeline

## Pipeline (a ORDEM importa)
1. `scripts/01_normalizar.sh entrada/SEU_VIDEO.mp4`   -> trabalho/01_normalizado.mp4
2. `scripts/02_cortar_silencio.sh`                    -> trabalho/02_cortado.mp4
3. `scripts/03_transcrever.sh`                        -> trabalho/transcricao.srt + .txt
4. [VOCÊ, agente] analisa a transcrição e gera trabalho/cortes.txt (ver regras abaixo)
5. `scripts/04_limpar.sh`                             -> trabalho/04_limpo.mp4
6. `scripts/05_montar.sh`                             -> trabalho/05_montado.mp4
7. `scripts/06_velocidade.sh`                         -> saida/video_final.mp4 (1,15x)
8. `scripts/07_volume.sh`                             -> ajusta saida/video_final.mp4 pra -14 LUFS (só áudio)

## PASSO 4 — Como gerar trabalho/cortes.txt (a parte inteligente)
Leia `trabalho/transcricao.srt` (tem texto + timestamps) e identifique trechos pra REMOVER:

a) **Recados ao editor** — frases tipo "corta", "editou", "edita isso", "deixa eu ver",
   "o que você coloca na tela menor", "não sei se vai encaixar", "isso aqui você corta".
   Remova a frase inteira E o trecho atrapalhado em volta dela.

b) **Takes repetidos por erro** — quando a MESMA ideia aparece 2+ vezes seguidas porque
   eu errei e refiz. MANTENHA a ÚLTIMA versão (a boa) e corte as anteriores.
   Atenção: nem sempre as palavras são idênticas — pode ser uma tentativa truncada
   ("o workflow ele... ãã... o workflow dispara quando o lead..."). Corte a tentativa falha.

c) **Hesitações longas** — "ééé", "ãã", começos de frase abandonados.

d) **Falsos começos** — ele inicia uma frase, abandona e refaz com quase as mesmas
   palavras, às vezes só truncando a última ("eu vou fazer que... eu vou fazer
   questão"). O `analisador.py` (detectar_falsos_comecos) pega isso via timestamps
   por palavra; corta a tentativa e mantém a refeita. Precisa do `transcricao.json`
   (whisper com `--word_timestamps True --condition_on_previous_text False`).

NÃO corte: repetições intencionais pra dar ênfase ("tudo, tudo, tudo"), listas com
prefixo comum ("o CRM, o funil, o tráfego"), nem conteúdo válido.

### Formato do cortes.txt
Uma linha por trecho a REMOVER, em segundos: `inicio fim`
Use os timestamps do SRT como base, com ~0.3s de margem. Linhas com # são ignoradas. Ex:
```
# take repetido sobre workflow
42.5 49.0
# recado "corta editou"
312.0 317.5
```

### IMPORTANTE antes de aplicar
Antes de rodar o passo 04, me MOSTRE a lista de cortes propostos com o texto de cada um,
e só aplique depois que eu confirmar — a não ser que eu já tenha dito pra ir direto.

## Regras gerais
- Nunca apague nada de `entrada/`.
- Se uma flag de ferramenta der erro, rode `--help` e adapte, não desista.
- Se faltar algum asset em `assets/`, os scripts pulam aquela parte (não trava).
- Ao final, AVISE que é obrigatória a revisão humana assistindo `video_final.mp4` a 1.5x.

## Painel (gestor de projetos)

Ao FINAL de cada sessão de trabalho, reporte o estado deste projeto ao Painel:

curl -s -m 3 -X POST http://localhost:4747/api/report \
  -H "Content-Type: application/json" \
  -d '{
    "projeto": "motor-edicao-ava-partners",
    "status": "ativo",
    "resumo": "resumo curto do que foi feito nesta sessão",
    "tarefas": [
      { "titulo": "tarefa concluída nesta sessão", "coluna": "done" },
      { "titulo": "próximo passo pendente", "coluna": "todo" }
    ]
  }' > /dev/null 2>&1 || true

Regras:
- "status": ativo | parado | ideia | concluido
- "coluna": todo | doing | done
- Ajuste status/resumo/tarefas para refletir a sessão real
- Se o comando falhar (Painel desligado), ignore em silêncio e NÃO tente de novo
