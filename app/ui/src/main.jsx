import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'

// fontes (bundladas — funcionam offline): Inter + JetBrains Mono
import '@fontsource-variable/inter'
import '@fontsource/jetbrains-mono/400.css'
import '@fontsource/jetbrains-mono/500.css'
import '@fontsource/jetbrains-mono/600.css'

// estilos
import './styles/base.css'
import './styles/barra.css'
import './styles/controles.css'
import './styles/preparo.css'
import './styles/render.css'
import './styles/revisao.css'
import './styles/resultado.css'
import './styles/thumb.css'
import './styles/qualidade.css'
import './styles/mascote.css'

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
