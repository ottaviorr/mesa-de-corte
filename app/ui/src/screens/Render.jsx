// Tela 2 — renderizando: VU meter, filmstrip, trilha de etapas, monitor de log.

import { useEffect, useRef, useState } from 'react'
import { cancelarEdicao } from '../api.js'
import { fmtHMS, FRASES, FASES_RODANDO } from '../utils.js'

const VU_BARRAS = Array.from({ length: 24 })

export default function Render({ status, enviando, progressoEnvio, arquivo }) {
  const [cancelando, setCancelando] = useState(false)
  const [frase, setFrase] = useState('')
  const monitorRef = useRef(null)

  const fase = enviando ? 'enviando' : status.fase
  const rodando = enviando || FASES_RODANDO.includes(status.fase)
  const progresso = enviando ? progressoEnvio : (status.progresso || 0)
  const etapas = status.etapas || []
  const idxAtual = etapas.findIndex((e) => e.chave === status.fase)

  // frases rotativas da fase atual
  useEffect(() => {
    const lista = FRASES[fase]
    if (!lista) { setFrase(''); return }
    setFrase(lista[0])
    if (lista.length === 1) return
    let i = 0
    const t = setInterval(() => { i = (i + 1) % lista.length; setFrase(lista[i]) }, 4200)
    return () => clearInterval(t)
  }, [fase])

  // auto-scroll do monitor
  useEffect(() => {
    if (monitorRef.current) monitorRef.current.scrollTop = monitorRef.current.scrollHeight
  }, [status.log])

  async function cancelar() {
    setCancelando(true)
    try { await cancelarEdicao() } catch { /* ignore */ }
    setTimeout(() => setCancelando(false), 2000)
  }

  const rotulo = enviando ? 'Enviando a fita…' : (status.rotulo || '…')
  const nomeFita = enviando ? arquivo : status.entrada
  const pct = enviando ? `envio ${progresso}%` : `${progresso}%`

  return (
    <section className="tela ativa">
      <div className="card">
        <div className="render-topo">
          <span className="onair">● ON AIR</span>
          <span className="render-arquivo">fita: {nomeFita || ''}</span>
          <span className="timecode grande">{fmtHMS(status.decorrido || 0)}</span>
        </div>
  
        <div className={'vu' + (rodando ? '' : ' parado')} aria-hidden="true">
          {VU_BARRAS.map((_, i) => <i key={i} />)}
        </div>
  
        <h2 className="render-rotulo">{rotulo}</h2>
        <p className="render-frase">{frase || ' '}</p>
  
        <div className="filmstrip" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progresso}>
          <div className="filmstrip-fill" style={{ width: progresso + '%' }} />
        </div>
        <div className="pct timecode">{pct}</div>
  
        <ol className="etapas">
          {etapas.map((e, i) => (
            <li key={e.chave}
                className={(idxAtual === -1 ? (status.fase === 'pronto') : i < idxAtual) ? 'feita'
                          : i === idxAtual ? 'atual' : ''}>
              {e.rotulo}
            </li>
          ))}
        </ol>
      </div>

      <div className="card">
        <h2 className="card-titulo">Log do motor</h2>
        <pre className="monitor" ref={monitorRef}>{(status.log || []).join('\n')}</pre>
        <div className="render-acoes">
          <button className="btn-fantasma vermelho" onClick={cancelar} disabled={cancelando || enviando}>
            ✕ cancelar edição
          </button>
        </div>
      </div>
    </section>
  )
}
