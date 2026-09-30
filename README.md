
<h1 align="center">Mesa de Corte — motor de edição</h1>
<p align="center"><em>Da gravação crua ao master pronto, sem encostar na timeline.</em></p>
<p align="center">
  Corta silêncios e takes errados, acelera, dá zoom nas ações e gera material de thumbnail —
  tudo local. <strong>Código aberto (MIT)</strong>: livre pra usar, modificar e compartilhar.
</p>

---


Pipeline pra editar tutoriais de GoHighLevel.
Foco: vídeo paisagem (16:9), sem Short.

## 🎛 Mesa de Corte (interface gráfica) — o jeito novo

App **Vite + React** (em `app/ui/`) com backend **Python** (a API + o pipeline).
Roda 100% em localhost — não precisa subir nada.

```
./iniciar_app.sh        # 1ª vez instala as deps; depois é só rodar
# ou, manualmente:
cd app/ui && npm install && npm run dev
```

`npm run dev` sobe os dois juntos (API em :8765, UI em :8766) e abre
`http://localhost:8766` no navegador. Arraste a gravação, escolha o canal
e clique em **INICIAR CORTE**:

| Canal | O que faz |
|-------|-----------|
| CH·01 Silêncio fora | corta pausas, respiros e buracos |
| CH·02 Corte inteligente | CH·01 + IA caça takes errados, recados pro editor e gagueiras |
| CH·03 Silêncio + turbo | CH·01 + aceleração de 1.05× a 2× (voz natural) |
| CH·04 Edição completa | CH·02 + aceleração — o tratamento completo |

Extras na interface:
- **Zoom de ênfase** — detecta os momentos de AÇÃO localizada (clique, digitação,
  abrir menu) e dá um zoom suave naquela região. Ignora o que é a tela toda
  mudando (slide/scroll) — zoom ali não ajuda. Na revisão sai um **thumbnail com
  a caixa** mostrando exatamente onde cada zoom acontece; você escolhe quais usar.
- **Revisar cortes/zooms antes de aplicar** — pausa e mostra a lista (texto dos
  cortes + thumbnails dos zooms); você desmarca o que quiser manter.
- **Gerar legenda (.txt)** — o texto das falas do vídeo final (desconta os
  cortes e a aceleração). Nos canais com IA já vem incluída.
- Tela de progresso com as etapas do pipeline + log ao vivo; no final, player,
  estatísticas (tempo economizado, nº de cortes) e botão de download.

A análise inteligente usa duas camadas: heurísticas locais (padrões de
"corta/editou", takes truncados, gagueiras — com timestamp por palavra do
Whisper) **+ o Claude CLI** (`claude -p`) pra entender takes refeitos com
palavras diferentes e recados sutis. Sem o Claude disponível, segue só com as
heurísticas.

## Fluxo clássico (Claude Code no terminal)

1. **Gravar** no Screen Studio (zoom automático já vem pronto)
2. **Exportar** o MP4 e colocar em `entrada/`
3. Abrir `claude` na pasta e pedir: *"edita o vídeo de entrada/ seguindo o CLAUDE.md"*

Ou manual, sem limpeza inteligente: `./editar.sh entrada/SEU_VIDEO.mp4`
(a limpeza pode ser gerada avulsa com `python3 app/analisador.py`).

## Assets (opcionais — coloque em assets/)
- `intro.mp4`       → abertura
- `cta_final.mp4`   → CTA de encerramento

Se faltar qualquer asset, a montagem é pulada (sem re-encode à toa).

## Sobre os CTAs / motion
Vídeo gerado por IA (Omni) erra texto/logo. Faça as peças (intro, cta_final)
UMA vez num template de motion (Canva/After Effects/Remotion) pro texto ficar nítido —
use o Omni só pra fundo/atmosfera se quiser. Depois reutilize em todo vídeo.

## Legenda
Gerada como arquivo, NÃO queimada no vídeo.
- Pela interface: `saida/legenda.txt` (texto das falas do vídeo final).
- Pelo fluxo clássico: `trabalho/transcricao.srt` (sincronizada com o vídeo
  ANTES dos cortes inteligentes/aceleração).

## Instalar (uma vez)

Clonou o repo? Roda o setup — ele instala tudo (ffmpeg, node, whisper, auto-editor):
```
git clone https://github.com/JuniorrBraga/motor-edicao-ava-partners.git
cd motor-edicao-ava-partners
./setup.sh          # instala as dependências (macOS via brew, Linux via apt/dnf)
./iniciar_app.sh    # sobe o app em http://localhost:8766
```

Ou à mão:
```
brew install ffmpeg node                          # macOS
pip3 install --user auto-editor openai-whisper
```

**Sobre o Whisper:** ele roda **100% local** (não precisa de conta nem chave de API).
Na primeira transcrição, baixa sozinho o modelo (`small` por padrão). Pra mais
precisão, use `MOTOR_WHISPER_MODEL=medium` (mais lento). O app mostra na tela de
preparo se faltar alguma ferramenta e aponta o `./setup.sh`.

**Claude CLI** (opcional): com ele ligado, a análise dos cortes e os prompts de
thumbnail ficam bem melhores. Sem ele, roda só com heurísticas locais.

O backend é só a biblioteca padrão do Python. A interface usa Node (Vite/React);
o `./iniciar_app.sh` roda o `npm install` na primeira vez e já ajeita o PATH dos
binários do pip (whisper/auto-editor) sozinho.

> Sem Node? Dá pra gerar o build estático uma vez (`cd app/ui && npm run build`)
> e rodar só o backend (`python3 app/servidor.py` → http://localhost:8765), que
> serve o build de `app/static`.

## Ajustes finos (variáveis de ambiente)
- `MOTOR_CRF=14` → qualidade do vídeo. **Menor = melhor (e arquivo maior).**
  14 é praticamente sem perda pra tela/texto; `12` é exagero; `18` pra arquivos menores. Padrão `14`.
- `MOTOR_FPS` → por padrão **preserva o fps do original** (Screen Studio = 60fps).
  Defina `30` só se quiser forçar 30fps.
- `MOTOR_PRESET=medium` → esforço de compressão do x264 (`slow` = um tico melhor, bem mais lento)
- `MOTOR_AUDIO_BITRATE=256k` → bitrate do áudio (mais alto perde menos a cada re-encode)
- `MOTOR_SILENCIO_THRESHOLD=6%` → sensibilidade do corte de silêncio. **Maior =
  corta mais**. Se cortar fala baixa, abaixe (5%); se sobrar silêncio (inclusive
  com algum ruído de fundo), suba (7–8%). Padrão `6%`.
- `MOTOR_SILENCIO_MARGIN=0.2sec` → respiro mantido antes/depois de cada fala
- `MOTOR_WHISPER_MODEL=medium` → transcrição mais precisa/fiel (mais lenta); padrão `small`.
  O `medium` capta melhor os começos abandonados ("falei errado e refiz").
- `MOTOR_CLAUDE_MODEL=...`     → modelo do `claude -p` na análise; padrão o da sua CLI
- `MOTOR_PORTA=8765`           → porta do backend

> **Take errado que a legenda não pegava:** o Whisper agora transcreve mais
> literal (`--condition_on_previous_text False`) e o analisador detecta o "falso
> começo" mesmo quando só a última palavra muda ("fazer que…" → "fazer questão").
> **Silêncio:** quem decide o corte é o nível de áudio (threshold). Se sobrar
> silêncio com algum ruído de fundo, suba o `MOTOR_SILENCIO_THRESHOLD`.

> **Precisão dos cortes:** pra não cortar fala correta, as heurísticas
> especulativas (semelhança de frase, falso começo por divergência) só são
> aplicadas se o Claude concordar com elas. As certeiras (recado, gagueira,
> truncamento "que→questão") valem sozinhas. Deixe a opção **"Revisar cortes"**
> ligada (padrão) pra dar o ok antes de aplicar.

> **Qualidade VÍDEO (medido com VMAF/SSIM):** preserva o **fps nativo (60fps)** —
> antes caía pra 30fps, picotando o movimento. Re-encodes em **CRF 14 / `yuv420p` /
> cor bt709 preservada**. Medições no vídeo real: normalizar antigo (CRF16/30fps)
> VMAF 96.5 → novo (CRF14/60fps) **VMAF 97.2 / SSIM 0.9994**, e 4 re-encodes em
> cascata custam ~0.1 de VMAF (praticamente nada). Master final com `+faststart`.
> **Áudio:** sai **do jeito que veio** — nenhum tratamento (sem normalização,
> sem highpass, sem denoise). A única coisa que mexe no som é o **acelerador**
> (`atempo`, que mantém o tom). O resto é só re-encode AAC 256k pra poder cortar.

> ⚠ Em qualquer fluxo: **revisão humana é obrigatória** — assista o
> `saida/video_final.mp4` a 1.5× antes de publicar.
