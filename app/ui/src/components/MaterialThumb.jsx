// MaterialThumb — mostra o material de thumbnail gerado da transcrição
// (título, textos curtos, resumo, prompt de cena e refs), com botão de copiar
// em cada campo pra você colar direto no seu gerador de thumb com IA.

import { useState } from 'react'

function Copiavel({ id, texto, className = '', copiado, copiar, children }) {
  return (
    <button
      type="button"
      className={'th-copiavel ' + className}
      onClick={() => copiar(texto, id)}
      title="Clique pra copiar"
    >
      <span className="th-conteudo">{children}</span>
      <span className="th-copia">{copiado === id ? 'copiado ✓' : 'copiar'}</span>
    </button>
  )
}

export default function MaterialThumb({ thumb }) {
  const [copiado, setCopiado] = useState('')

  const copiar = async (texto, id) => {
    try {
      await navigator.clipboard.writeText(texto)
      setCopiado(id)
      setTimeout(() => setCopiado((c) => (c === id ? '' : c)), 1400)
    } catch { /* clipboard indisponível fora de contexto seguro */ }
  }

  if (!thumb || !thumb.ok) return null
  const {
    titulo, textos_thumb = [], sobre, prompt_cena, imagens_referencia = [],
  } = thumb
  const props = { copiado, copiar }

  return (
    <div className="th">
      <div className="th-cabec">
        <span className="secao">Material pra thumbnail · gerado da transcrição</span>
        <a className="btn-fantasma th-baixar" href="/baixar/thumb" download>⬇ thumb.txt</a>
      </div>

      {titulo && (
        <div className="th-campo">
          <div className="th-rotulo">Título / tema do vídeo</div>
          <Copiavel id="titulo" texto={titulo} className="th-titulo" {...props}>{titulo}</Copiavel>
        </div>
      )}

      {textos_thumb.length > 0 && (
        <div className="th-campo">
          <div className="th-rotulo">Texto da thumb <small>curto e forte · clique pra copiar</small></div>
          <div className="th-chips">
            {textos_thumb.map((t, i) => (
              <Copiavel key={i} id={'txt' + i} texto={t} className="th-chip" {...props}>{t}</Copiavel>
            ))}
          </div>
        </div>
      )}

      {sobre && (
        <div className="th-campo">
          <div className="th-rotulo">Sobre o que é o vídeo</div>
          <Copiavel id="sobre" texto={sobre} className="th-bloco" {...props}>{sobre}</Copiavel>
        </div>
      )}

      {prompt_cena && (
        <div className="th-campo">
          <div className="th-rotulo">Prompt da cena <small>pra IA de imagem</small></div>
          <Copiavel id="prompt" texto={prompt_cena} className="th-bloco th-prompt" {...props}>{prompt_cena}</Copiavel>
        </div>
      )}

      {imagens_referencia.length > 0 && (
        <div className="th-campo">
          <div className="th-rotulo">Imagens de referência <small>anexe no gerador</small></div>
          <ul className="th-refs">
            {imagens_referencia.map((r, i) => <li key={i}>{r}</li>)}
          </ul>
        </div>
      )}
    </div>
  )
}
