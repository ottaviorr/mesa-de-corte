// Tela 3 — revisão: cortes da IA e/ou zooms de ênfase, pra você confirmar.

import { useMemo, useState } from 'react'
import { confirmarRevisao } from '../api.js'
import { fmtMS } from '../utils.js'

const ROTULOS = { recado: 'recado', take_repetido: 'take repetido', hesitacao: 'hesitação', misto: 'misto' }

export default function Revisao({ status }) {
  const cortes = useMemo(() => status.cortes || [], [status.cortes])
  const zooms = useMemo(() => status.zooms || [], [status.zooms])
  const [mc, setMc] = useState(() => cortes.map(() => true))
  const [mz, setMz] = useState(() => zooms.map(() => true))
  const [enviando, setEnviando] = useState(false)

  const nc = mc.filter(Boolean).length
  const nz = mz.filter(Boolean).length

  async function enviar(cIdx, zIdx) {
    setEnviando(true)
    try { await confirmarRevisao(cIdx, zIdx) } finally { setEnviando(false) }
  }
  function aplicar() {
    enviar(cortes.map((_, i) => i).filter((i) => mc[i]),
           zooms.map((_, i) => i).filter((i) => mz[i]))
  }

  const partes = []
  if (cortes.length) partes.push(`${nc} corte${nc === 1 ? '' : 's'}`)
  if (zooms.length) partes.push(`${nz} zoom${nz === 1 ? '' : 's'}`)

  return (
    <section className="tela ativa">
      <h2 className="titulo-tela">REVISÃO</h2>
      <p className="lema">Confira o que a IA propôs. Desmarque o que não quiser — o resto é aplicado.</p>

      {cortes.length > 0 && (
        <>
          <h3 className="secao">cortes — trechos a remover</h3>
          <div className="lista-cortes">
            {cortes.map((c, i) => (
              <label key={i} className={'corte' + (mc[i] ? '' : ' desmarcado')}>
                <input type="checkbox" checked={mc[i]} onChange={() => setMc((m) => m.map((v, j) => j === i ? !v : v))} />
                <span className="corte-tempo">{fmtMS(c.inicio)} → {fmtMS(c.fim)}<br /><small>−{(c.fim - c.inicio).toFixed(1)}s</small></span>
                <span className="corte-corpo">
                  <span className="corte-meta">
                    <span className={'badge ' + c.tipo}>{ROTULOS[c.tipo] || c.tipo}</span>
                    <span className="conf">confiança {Math.round((c.confianca || 0) * 100)}% · {c.origem === 'claude' ? 'análise semântica' : 'heurística'}</span>
                  </span>
                  <span className="corte-motivo">{c.motivo}</span>
                  {c.trecho && <span className="corte-trecho">"{c.trecho}"</span>}
                </span>
              </label>
            ))}
          </div>
        </>
      )}

      {zooms.length > 0 && (
        <>
          <h3 className="secao">zooms — ênfase nas ações (a caixa mostra onde)</h3>
          <div className="lista-zooms">
            {zooms.map((z, i) => (
              <label key={i} className={'zoomcard' + (mz[i] ? '' : ' desmarcado')}>
                <img className="zoom-thumb" src={`/zoom/thumb/${i}`} alt={`zoom ${i + 1}`} loading="lazy" />
                <div className="zoom-info">
                  <input type="checkbox" checked={mz[i]} onChange={() => setMz((m) => m.map((v, j) => j === i ? !v : v))} />
                  <span className="corte-tempo">{fmtMS(z.inicio)} → {fmtMS(z.fim)}</span>
                  <span className="badge zoomtag">{z.zoom}×</span>
                  <span className="corte-motivo">{z.motivo}</span>
                </div>
              </label>
            ))}
          </div>
        </>
      )}

      <div className="acoes">
        <button className="btn-principal" disabled={enviando} onClick={aplicar}>
          ✓ &nbsp;APLICAR {partes.join(' + ') || 'E SEGUIR'}
        </button>
        <button className="btn-fantasma" disabled={enviando} onClick={() => enviar([], [])}>
          seguir sem nenhum
        </button>
      </div>
    </section>
  )
}
