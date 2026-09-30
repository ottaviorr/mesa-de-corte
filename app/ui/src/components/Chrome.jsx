// Cabeçalho do conteúdo — saudação pela hora do dia + data + selo de formato.

export function Topo() {
  const agora = new Date()
  const h = agora.getHours()
  const saudacao = h < 12 ? 'Bom dia' : h < 18 ? 'Boa tarde' : 'Boa noite'
  const data = agora.toLocaleDateString('pt-BR', { weekday: 'long', day: 'numeric', month: 'long' })
  return (
    <header className="topo">
      <div>
        <h1 className="topo-titulo">{saudacao}, Otavio</h1>
        <p className="topo-data">{data}</p>
      </div>
      <span className="selo">Paisagem · 1080p · 16:9</span>
    </header>
  )
}
