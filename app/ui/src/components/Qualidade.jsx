// Qualidade — painel avançado de codec/qualidade/resolução/fps/áudio.
// Gerencia o próprio estado e reporta pro pai (via onChange) já no formato que o
// backend espera (vcodec, rate_mode, crf, vbitrate, preset, res, fps, acodec,
// audio_bitrate). Padrões vêm no MÁXIMO — o usuário baixa se quiser.
// Com placa NVIDIA detectada (prop gpu), o padrão vira o encoder da GPU (NVENC).

import { useEffect, useRef, useState } from 'react'
import { estimarSaida } from '../utils.js'

const CODECS = [
  { v: 'h264_nvenc', nome: 'H.264 · NVIDIA', sub: 'placa de vídeo — bem mais rápido' },
  { v: 'hevc_nvenc', nome: 'H.265 · NVIDIA', sub: 'placa de vídeo — arquivo menor' },
  { v: 'libx264', nome: 'H.264', sub: 'CPU — compatível com tudo' },
  { v: 'libx265', nome: 'H.265 / HEVC', sub: 'CPU — mesma qualidade, arquivo menor' },
  { v: 'prores_ks', nome: 'ProRes 422 HQ', sub: 'mastering quase-lossless (enorme)' },
  { v: 'h264_videotoolbox', nome: 'H.264 · hardware', sub: 'rápido (GPU do Mac)' },
  { v: 'hevc_videotoolbox', nome: 'H.265 · hardware', sub: 'rápido (GPU do Mac)' },
]
const PRESETS = ['ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow', 'slower', 'veryslow']
// qualidade padrão por família: CRF do x264/x265 e CQ do NVENC (mesma escala 0-51)
const CRF_PADRAO = (codec) => (codec.includes('nvenc') ? 19 : 12)

export const QUALIDADE_PADRAO = {
  vcodec: 'libx264', rate_mode: 'crf', crf: 12, vbitrate: '20M', preset: 'slow',
  res: 'original', fps: 'original', acodec: 'aac', audio_bitrate: '320k',
}

// soBitrate: no canal 01 (sem zoom) o master sai direto do auto-editor, que só
// aceita bitrate — CRF/CQ seria ignorado, então a tela mostra o que vale de fato.
export default function Qualidade({ onChange, meta, gpu, soBitrate }) {
  const [vcodec, setVcodec] = useState('libx264')
  const [rateMode, setRateMode] = useState('crf')
  const [crf, setCrf] = useState(12)
  const [vbitrate, setVbitrate] = useState('20M')
  const [preset, setPreset] = useState('slow')
  const [res, setRes] = useState('original')
  const [fps, setFps] = useState('original')
  const [acodec, setAcodec] = useState('aac')
  const [abitrate, setAbitrate] = useState('320k')
  const mexeuNoCodec = useRef(false)

  function trocarCodec(v) {
    mexeuNoCodec.current = true
    setVcodec(v)
    setCrf(CRF_PADRAO(v))
  }

  // placa NVIDIA detectada -> começa na GPU (se você ainda não escolheu outro)
  useEffect(() => {
    if (gpu && !mexeuNoCodec.current) { setVcodec('h264_nvenc'); setCrf(CRF_PADRAO('h264_nvenc')) }
  }, [gpu])

  const modoTaxa = soBitrate ? 'bitrate' : rateMode
  const q = { vcodec, rate_mode: modoTaxa, crf, vbitrate, preset, res, fps, acodec, audio_bitrate: abitrate }

  useEffect(() => { onChange(q) },
    [vcodec, modoTaxa, crf, vbitrate, preset, res, fps, acodec, abitrate, onChange]) // eslint-disable-line

  const est = estimarSaida(q, meta)

  const ehX26x = vcodec === 'libx264' || vcodec === 'libx265'
  const ehNvenc = vcodec.includes('nvenc')
  const ehProres = vcodec === 'prores_ks'
  const ehHardware = vcodec.includes('videotoolbox')
  // ProRes/Mac-hardware não usam CRF; só x26x usa preset. NVENC: CQ ou bitrate.
  const usaCrf = (ehX26x || ehNvenc) && modoTaxa === 'crf'
  const usaBitrate = ((ehX26x || ehNvenc) && modoTaxa === 'bitrate') || ehHardware
  const rotuloQ = ehNvenc ? 'CQ' : 'CRF'

  return (
    <details className="qualidade">
      <summary>
        <span className="secao">Qualidade / Codec</span>
        <span className="q-resumo">{CODECS.find((c) => c.v === vcodec)?.nome} · {ehProres ? 'HQ' : usaCrf ? `${rotuloQ} ${crf}` : vbitrate} · {res === 'original' ? 'res orig' : res + 'p'} · {fps === 'original' ? 'fps orig' : fps + 'fps'}</span>
      </summary>

      <div className="q-grade">
        <label className="q-campo q-largo">
          <span>Codec de vídeo</span>
          <select value={vcodec} onChange={(e) => trocarCodec(e.target.value)}>
            {CODECS.filter((c) => gpu || !c.v.includes('nvenc') || c.v === vcodec)
              .map((c) => <option key={c.v} value={c.v}>{c.nome} — {c.sub}</option>)}
          </select>
        </label>

        {!ehProres && (
          <label className="q-campo">
            <span>Modo de taxa{soBitrate && <small>canal 01: o corte já gera o master, só por bitrate</small>}</span>
            <select value={ehHardware ? 'bitrate' : modoTaxa} disabled={ehHardware || soBitrate}
                    onChange={(e) => setRateMode(e.target.value)}>
              <option value="crf">{rotuloQ} (qualidade constante)</option>
              <option value="bitrate">Bitrate (taxa alvo)</option>
            </select>
          </label>
        )}

        {usaCrf && (
          <label className="q-campo q-largo">
            <span>Qualidade ({rotuloQ} {crf}) <small>menor = melhor{ehNvenc ? ' · 19 ≈ visualmente sem perda' : ' · 0 = lossless'}</small></span>
            <input type="range" min="0" max="28" step="1" value={crf}
                   onChange={(e) => setCrf(Number(e.target.value))} />
          </label>
        )}

        {usaBitrate && (
          <label className="q-campo">
            <span>Bitrate de vídeo</span>
            <select value={vbitrate} onChange={(e) => setVbitrate(e.target.value)}>
              {['8M', '12M', '20M', '30M', '50M', '80M'].map((b) => <option key={b} value={b}>{b}bps</option>)}
            </select>
          </label>
        )}

        {ehX26x && (
          <label className="q-campo">
            <span>Esforço (preset)</span>
            <select value={preset} onChange={(e) => setPreset(e.target.value)}>
              {PRESETS.map((p) => <option key={p} value={p}>{p}{p === 'slow' ? ' (padrão)' : ''}</option>)}
            </select>
          </label>
        )}

        <label className="q-campo">
          <span>Resolução</span>
          <select value={res} onChange={(e) => setRes(e.target.value)}>
            <option value="original">Original (preserva)</option>
            <option value="1080">1080p</option>
            <option value="1440">1440p (2K)</option>
            <option value="2160">2160p (4K)</option>
          </select>
        </label>

        <label className="q-campo">
          <span>FPS</span>
          <select value={fps} onChange={(e) => setFps(e.target.value)}>
            <option value="original">Original (preserva)</option>
            <option value="30">30</option>
            <option value="60">60</option>
          </select>
        </label>

        <label className="q-campo">
          <span>Codec de áudio</span>
          <select value={acodec} onChange={(e) => setAcodec(e.target.value)}>
            <option value="aac">AAC (compatível)</option>
            <option value="alac">ALAC (lossless)</option>
            <option value="flac">FLAC (lossless)</option>
          </select>
        </label>

        {acodec === 'aac' && (
          <label className="q-campo">
            <span>Bitrate de áudio</span>
            <select value={abitrate} onChange={(e) => setAbitrate(e.target.value)}>
              {['128k', '192k', '256k', '320k'].map((b) => <option key={b} value={b}>{b}bps</option>)}
            </select>
          </label>
        )}

        <div className="q-estimativa q-largo">
          <span className="q-est-num">≈ {est.total.toFixed(1)} Mbps</span>
          <span className="q-est-num">~{Math.round(est.mbPorMin)} MB/min</span>
          {est.dur && (
            <span className="q-est-num q-est-forte">
              ~{est.mbPorMin * est.dur / 60 >= 1000
                ? (est.mbPorMin * est.dur / 60 / 1000).toFixed(1) + ' GB'
                : Math.round(est.mbPorMin * est.dur / 60) + ' MB'} no seu vídeo
            </span>
          )}
          <small>estimativa · o final costuma ser menor (os cortes encurtam o vídeo)</small>
        </div>
      </div>
    </details>
  )
}
