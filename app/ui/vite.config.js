import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Frontend em :8766; backend Python (API + vídeo) em :8765.
// O proxy faz o browser falar só com o Vite — sem CORS, mesma origem.
const API = 'http://localhost:8765'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 8766,
    open: true,
    proxy: {
      '/api': API,
      '/video': API,
      '/baixar': API,
    },
  },
  // build opcional (npm run build): cai em app/static, que o servidor.py
  // serve como fallback caso você rode só o Python, sem o Vite.
  build: {
    outDir: '../static',
    emptyOutDir: true,
  },
})
