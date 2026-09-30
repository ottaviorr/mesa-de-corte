// App — orquestra o polling do backend, a máquina de telas e o upload.

import { useCallback, useEffect, useRef, useState } from 'react'
import Barra from './components/Barra.jsx'
import Mascote from './components/Mascote.jsx'
import { Topo } from './components/Chrome.jsx'
import Preparo from './screens/Preparo.jsx'
import Render from './screens/Render.jsx'
import Revisao from './screens/Revisao.jsx'
import Resultado from './screens/Resultado.jsx'
import Erro from './screens/Erro.jsx'
import { getStatus, iniciarEdicao, resetar } from './api.js'
import { FASES_RODANDO } from './utils.js'

const OCIOSO = { fase: 'ocioso' }

export default function App() {
  const [status, setStatus] = useState(OCIOSO)
  const [enviando, setEnviando] = useState(false)
  const [progressoEnvio, setProgressoEnvio] = useState(0)
  const [aviso, setAviso] = useState(null)
  const [dispensado, setDispensado] = useState(false)   // após reset: ignora fase terminal
  const [fitaEnvio, setFitaEnvio] = useState('')

  // refs pra ler estado atual dentro do intervalo sem recriá-lo
  const enviandoRef = useRef(false)
  const congeladoRef = useRef(false)                    // congela polling durante reset
  enviandoRef.current = enviando

  useEffect(() => {
    let vivo = true
    async function pulso() {
      if (enviandoRef.current || congeladoRef.current) return
      try {
        const st = await getStatus()
        if (vivo && !congeladoRef.current) setStatus(st)
      } catch { /* servidor reiniciando; tenta no próximo tick */ }
    }
    pulso()
    const t = setInterval(pulso, 900)
    return () => { vivo = false; clearInterval(t) }
  }, [])

  const onIniciar = useCallback((formData, info) => {
    setAviso(null)
    setDispensado(false)
    setFitaEnvio(info.nome || '')
    setProgressoEnvio(0)
    setEnviando(true)
    setStatus((s) => ({ ...s, decorrido: 0 }))
    iniciarEdicao(formData, setProgressoEnvio)
      .then(() => setEnviando(false))               // polling assume daqui
      .catch((e) => { setEnviando(false); setAviso(e.message) })
  }, [])

  const voltarParaMesa = useCallback(async () => {
    setDispensado(true)
    congeladoRef.current = true
    try { await resetar() } catch { /* segue mesmo assim */ }
    setStatus(OCIOSO)
    congeladoRef.current = false
  }, [])

  // máquina de telas, derivada do estado
  const fase = status.fase
  const rodando = FASES_RODANDO.includes(fase)
  let view
  if (enviando || rodando) view = 'render'
  else if (fase === 'revisao') view = 'revisao'
  else if (fase === 'pronto' && !dispensado) view = 'pronto'
  else if (fase === 'erro' && !dispensado) view = 'erro'
  else view = 'preparo'

  const recAtiva = enviando || rodando || fase === 'revisao'

  return (
    <>
      <Mascote ativo={recAtiva} />
      <Barra view={view} ativa={recAtiva} />
      <main>
        <Topo />
        {view === 'preparo' && <Preparo onIniciar={onIniciar} aviso={aviso} />}
        {view === 'render' && (
          <Render status={status} enviando={enviando} progressoEnvio={progressoEnvio} arquivo={fitaEnvio} />
        )}
        {view === 'revisao' && <Revisao status={status} />}
        {view === 'pronto' && <Resultado status={status} onNovo={voltarParaMesa} />}
        {view === 'erro' && <Erro status={status} onVoltar={voltarParaMesa} />}
      </main>
    </>
  )
}
