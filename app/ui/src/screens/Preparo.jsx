// Tela 1 — preparação: upload (drag & drop), canais (modos), fader, chaves.

import { useEffect, useRef, useState } from 'react'
import { getEntrada, getDiagnostico } from '../api.js'
import { fmtBytes, CANAIS } from '../utils.js'
import Qualidade, { QUALIDADE_PADRAO } from '../components/Qualidade.jsx'

const DEPS_NUCLEO = { ffmpeg: 'ffmpeg', whisper: 'whisper', auto_editor: 'auto-editor' }

const ICONE_FITA = (
  <svg className="dz-icone" viewBox="0 0 48 48" aria-hidden="true"><path fill="currentColor" d="M6 10h28a4 4 0 0 1 4 4v3.5l8-4.5v22l-8-4.5V34a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4V14a4 4 0 0 1 4-4Zm14 6.8v14.4c0 .8.9 1.3 1.6.9l11-7.2c.6-.4.6-1.4 0-1.8l-11-7.2c-.7-.4-1.6.1-1.6.9Z" /></svg>
)
const ICONE_OK = (
  <svg className="dz-icone" viewBox="0 0 48 48" aria-hidden="true"><path fill="currentColor" d="M24 4a20 20 0 1 0 0 40 20 20 0 0 0 0-40Zm-3.5 28.6-8-8 3-3 5 5 12-12 3 3-15 15Z" /></svg>
)

export default function Preparo({ onIniciar, aviso }) {
  const [arquivo, setArquivo] = useState(null)
  const [existente, setExistente] = useState('')
  const [lista, setLista] = useState([])
  const [modo, setModo] = useState(1)
  const [velocidade, setVelocidade] = useState(1.15)
  const [revisar, setRevisar] = useState(true)        // padrão: revisar (contrato do CLAUDE.md)
  const [legenda, setLegenda] = useState(false)       // escolha real do usuário
  const [zoom, setZoom] = useState(false)             // zoom de ênfase nas ações
  const [thumb, setThumb] = useState(true)            // prompts de thumb (transcreve em qualquer canal)
  const [revisaoDupla, setRevisaoDupla] = useState(true)  // 2ª transcrição confere o corte
  const [qualidade, setQualidade] = useState(QUALIDADE_PADRAO)  // codec/qualidade/res/fps/áudio
  const [metaVideo, setMetaVideo] = useState(null)    // {dur,w,h} do arquivo selecionado (p/ estimativa)
  const [arrastando, setArrastando] = useState(false)
  const inputFile = useRef(null)

  const comVel = modo === 3 || modo === 4
  const comIA = modo === 2 || modo === 4
  const legendaEfetiva = comIA ? true : legenda    // modos IA já trazem legenda de carona

  const [diag, setDiag] = useState(null)

  useEffect(() => { getEntrada().then((d) => setLista(d.arquivos || [])).catch(() => {}) }, [])
  useEffect(() => { getDiagnostico().then(setDiag).catch(() => {}) }, [])

  const faltando = diag
    ? Object.entries(DEPS_NUCLEO).filter(([k]) => !diag[k]).map(([, v]) => v)
    : []

  // lê duração/dimensões do arquivo enviado (client-side) pra estimar peso/taxa
  useEffect(() => {
    if (!arquivo) { setMetaVideo(null); return }
    const url = URL.createObjectURL(arquivo)
    const v = document.createElement('video')
    v.preload = 'metadata'
    v.onloadedmetadata = () => {
      setMetaVideo({ dur: v.duration, w: v.videoWidth, h: v.videoHeight })
      URL.revokeObjectURL(url)
    }
    v.onerror = () => { setMetaVideo(null); URL.revokeObjectURL(url) }
    v.src = url
    return () => URL.revokeObjectURL(url)
  }, [arquivo])

  function escolherArquivo(f) {
    if (!f) return
    setArquivo(f); setExistente('')
  }

  function dropzoneConteudo() {
    if (arquivo) return (
      <>{ICONE_OK}<span className="dz-nome">{arquivo.name}</span>
        <small>{fmtBytes(arquivo.size)} · fita carregada</small>
        <span className="dz-troca">clique pra trocar</span></>
    )
    if (existente) return (
      <>{ICONE_OK}<span className="dz-nome">entrada/{existente}</span>
        <small>fita da estante · pronta pra rodar</small>
        <span className="dz-troca">ou arraste outra aqui</span></>
    )
    return (
      <>{ICONE_FITA}<strong>ARRASTE SUA GRAVAÇÃO</strong>
        <small>ou clique pra escolher · .mp4 .mov .mkv</small></>
    )
  }

  function iniciar() {
    const fd = new FormData()
    fd.append('modo', modo)
    fd.append('velocidade', velocidade)
    fd.append('legenda', legendaEfetiva ? '1' : '0')
    fd.append('revisar', revisar ? '1' : '0')
    fd.append('zoom', zoom ? '1' : '0')
    fd.append('thumb', thumb ? '1' : '0')
    fd.append('revisao_dupla', revisaoDupla ? '1' : '0')
    Object.entries(qualidade).forEach(([k, v]) => fd.append(k, v))
    if (arquivo) fd.append('video', arquivo)
    else fd.append('arquivo_existente', existente)
    onIniciar(fd, { modo, velocidade, nome: arquivo ? arquivo.name : existente })
  }

  const enchimento = ((velocidade - 1.05) / (2 - 1.05)) * 100
  const canal = CANAIS.find((c) => c.modo === modo)

  const kpis = [
    { t: 'Fitas na entrada', v: lista.length, sub: 'prontas em entrada/' },
    { t: 'Motor', v: !diag ? '…' : faltando.length ? 'Incompleto' : 'Pronto',
      sub: faltando.length ? 'faltando ' + faltando.join(', ') : diag?.nvenc ? 'placa NVIDIA ativa (NVENC)' : 'ffmpeg · whisper · auto-editor',
      tom: !diag ? '' : faltando.length ? 'ruim' : 'bom' },
    { t: 'Análise IA', v: !diag ? '…' : diag.claude ? 'Claude' : 'Heurística',
      sub: diag && !diag.claude ? 'Claude CLI ausente' : 'cortes semânticos', tom: !diag ? '' : diag.claude ? 'bom' : 'alerta' },
    { t: 'Canal', v: canal?.num, sub: canal?.nome },
  ]

  return (
    <section className="tela ativa">
      <div className="kpis">
        {kpis.map((k) => (
          <div key={k.t} className="card kpi">
            <span className="kpi-t">{k.t}</span>
            <strong className="kpi-v">{k.v}</strong>
            <small className={'kpi-sub ' + (k.tom || '')}>{k.sub}</small>
          </div>
        ))}
      </div>

      {faltando.length > 0 && (
        <div className="aviso-deps">
          ⚠ Faltando no seu sistema: <strong>{faltando.join(', ')}</strong>. Rode <code>./setup.sh</code> no terminal e reinicie o app.
        </div>
      )}

      <div className="preparo-grid">
        <div className="card coluna-fita">
          <h2 className="card-titulo">Gravação</h2>
          <label
            className={'dropzone' + (arrastando ? ' arrastando' : '')}
            onDragEnter={(e) => { e.preventDefault(); setArrastando(true) }}
            onDragOver={(e) => { e.preventDefault(); setArrastando(true) }}
            onDragLeave={(e) => { e.preventDefault(); setArrastando(false) }}
            onDrop={(e) => { e.preventDefault(); setArrastando(false); escolherArquivo(e.dataTransfer.files?.[0]) }}
          >
            <span className="dz-conteudo">{dropzoneConteudo()}</span>
            <input
              ref={inputFile} type="file"
              accept="video/mp4,video/quicktime,video/x-matroska,video/webm,.mp4,.mov,.mkv,.webm,.m4v"
              onChange={(e) => escolherArquivo(e.target.files?.[0])}
            />
          </label>

          <div className="ja-na-entrada">
            <label htmlFor="existente">ou use uma fita que já está em <code>entrada/</code></label>
            <select
              id="existente" value={existente}
              onChange={(e) => { setExistente(e.target.value); if (e.target.value) { setArquivo(null); if (inputFile.current) inputFile.current.value = '' } }}
            >
              <option value="">— escolher —</option>
              {lista.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
          </div>
        </div>

        <div className="card coluna-canais">
          <h2 className="card-titulo">Canal de edição</h2>
          <div className="canais">
            {CANAIS.map((c) => (
              <button
                key={c.modo} type="button"
                className={'canal' + (modo === c.modo ? ' selecionado' : '')}
                onClick={() => setModo(c.modo)}
              >
                <span className="canal-num">{c.num}
                  {c.tags.includes('ia') && <em className="tag-ia">IA</em>}
                  {c.tags.includes('vel') && <em className="tag-vel">⚡</em>}
                </span>
                <span className="canal-nome">{c.nome}</span>
                <span className="canal-desc">{c.desc}</span>
              </button>
            ))}
          </div>

          {comVel && (
            <div className="painel-vel">
              <div className="vel-cabeca">
                <h2 className="secao">velocidade</h2>
                <output className="vel-out">{velocidade.toFixed(2).replace(/0$/, '')}×</output>
              </div>
              <input
                type="range" min="1.05" max="2" step="0.05" value={velocidade}
                style={{ '--enchimento': enchimento + '%' }}
                onChange={(e) => setVelocidade(Number(e.target.value))}
                aria-label="Velocidade do vídeo final"
              />
              <div className="vel-ticks" aria-hidden="true">
                <span>1.05</span><span>1.25</span><span>1.5</span><span>1.75</span><span>2.0</span>
              </div>
            </div>
          )}

          <div className="chaves">
            <label className="chave">
              <input type="checkbox" checked={thumb}
                     onChange={(e) => setThumb(e.target.checked)} />
              <span className="trilho" aria-hidden="true" />
              <span className="chave-txt">Gerar prompts de thumbnail
                <small>transcreve o vídeo (em qualquer canal) e cria título, textos e prompt de cena pra IA</small></span>
            </label>
            <label className="chave">
              <input type="checkbox" checked={zoom}
                     onChange={(e) => setZoom(e.target.checked)} />
              <span className="trilho" aria-hidden="true" />
              <span className="chave-txt">Zoom de ênfase nas ações
                <small>dá um zoom suave nos momentos de ação (clique, digitação) — você revisa onde</small></span>
            </label>
            <label className={'chave' + (comIA || zoom ? '' : ' desativada')}>
              <input type="checkbox" checked={revisar} disabled={!(comIA || zoom)}
                     onChange={(e) => setRevisar(e.target.checked)} />
              <span className="trilho" aria-hidden="true" />
              <span className="chave-txt">Revisar cortes/zooms antes de aplicar
                <small>pausa e te mostra a lista — você dá o ok</small></span>
            </label>
            <label className={'chave' + (comIA ? '' : ' desativada')}>
              <input type="checkbox" checked={revisaoDupla && comIA} disabled={!comIA}
                     onChange={(e) => setRevisaoDupla(e.target.checked)} />
              <span className="trilho" aria-hidden="true" />
              <span className="chave-txt">Corte perfeito (revisão dupla)
                <small>{comIA ? 're-transcreve o corte, confere se algo se perdeu e corrige'
                              : 'só nos canais com IA (CH·02/04)'}</small></span>
            </label>
            <label className={'chave' + (comIA ? ' desativada' : '')}>
              <input type="checkbox" checked={legendaEfetiva} disabled={comIA}
                     onChange={(e) => setLegenda(e.target.checked)} />
              <span className="trilho" aria-hidden="true" />
              <span className="chave-txt">Gerar legenda (.txt)
                <small>{comIA ? 'incluída no corte inteligente — sai sincronizada'
                              : 'transcreve com Whisper, sincronizada com o final'}</small></span>
            </label>
          </div>

          <Qualidade onChange={setQualidade} meta={metaVideo} gpu={!!diag?.nvenc}
                     soBitrate={modo === 1 && !zoom} />

          <button className="btn-principal" disabled={!(arquivo || existente)} onClick={iniciar}>
            ▶ &nbsp;INICIAR CORTE
          </button>
          {aviso && <p className="aviso">{aviso}</p>}
        </div>
      </div>
    </section>
  )
}
