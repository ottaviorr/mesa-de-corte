// Tela 4 — master pronto: player, estatísticas e download.

import { useMemo } from 'react'
import { fmtMS } from '../utils.js'
import MaterialThumb from '../components/MaterialThumb.jsx'

export default function Resultado({ status, onNovo }) {
  const s = status.stats || {}
  const srcVideo = useMemo(() => '/video/final?t=' + Date.now(), [])

  const cards = []
  if (s.tempo_economizado != null) {
    cards.push({ t: 'tempo economizado', v: `−${fmtMS(s.tempo_economizado)}`, sub: 'a menos pro seu público', destaque: true })
  }
  cards.push({ t: 'cortes da IA', v: String(s.n_cortes ?? 0),
    sub: (status.modo === 2 || status.modo === 4) ? 'takes/recados removidos' : 'modo sem análise IA' })
  if (s.n_zooms) {
    cards.push({ t: 'zooms de ênfase', v: String(s.n_zooms), sub: 'nas ações que importam' })
  }
  if (s.duracao_final != null) {
    cards.push({ t: 'duração final', v: fmtMS(s.duracao_final), sub: s.duracao_original != null ? `antes: ${fmtMS(s.duracao_original)}` : '' })
  }
  if (status.modo === 3 || status.modo === 4) {
    cards.push({ t: 'velocidade', v: `${Number(status.velocidade).toFixed(2)}×`, sub: 'voz mantida natural' })
  }

  return (
    <section className="tela ativa">
      <div className="carimbo">MASTER PRONTO</div>

      <div className="monitor-video">
        <div className="monitor-moldura">
          <video src={srcVideo} controls playsInline preload="metadata" />
          <div className="monitor-rodape"><span className="led" aria-hidden="true" /> SAÍDA &nbsp;//&nbsp; saida/video_final.mp4</div>
        </div>
      </div>

      <div className="stats">
        {cards.map((c) => (
          <dl key={c.t} className={'stat' + (c.destaque ? ' destaque' : '')}>
            <dt>{c.t}</dt>
            <dd>{c.v}{c.sub && <small>{c.sub}</small>}</dd>
          </dl>
        ))}
      </div>

      {status.revisao_corte && (
        <div className={'revisao-corte' + (status.revisao_corte.ok ? ' ok' : ' alerta')}>
          <strong>{status.revisao_corte.ok ? '✓ Corte revisado' : '⚠ Revisão do corte'}</strong>
          <span>{status.revisao_corte.resumo}</span>
          {status.revisao_corte.suspeitos?.length > 0 && (
            <ul>{status.revisao_corte.suspeitos.map((s, i) => <li key={i}>“{s}…”</li>)}</ul>
          )}
        </div>
      )}

      <div className="acoes">
        <a className="btn-principal" href="/baixar/video" download>⬇ &nbsp;BAIXAR VÍDEO</a>
        {status.tem_legenda && <a className="btn-fantasma" href="/baixar/legenda" download>⬇ legenda .txt</a>}
        <button className="btn-fantasma" onClick={onNovo}>+ nova edição</button>
      </div>

      <MaterialThumb thumb={status.thumb} />

      <p className="lembrete">⚠ Revisão humana obrigatória: assista o master a 1.5× antes de publicar.</p>
    </section>
  )
}
