// Barra lateral — nome do app, etapas do fluxo (a atual acende; o backend dita a
// tela, então não são clicáveis) e cartão do usuário com o indicador REC.

const ICONES = {
  preparo: 'M4 5h11a2 2 0 0 1 2 2v1.5l3-1.8v10.6l-3-1.8V17a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z',
  render: 'M12 3v3M12 18v3M4.2 7.5l2.6 1.5M17.2 15l2.6 1.5M4.2 16.5l2.6-1.5M17.2 9l2.6-1.5',
  revisao: 'M9 11l3 3 8-8M20 12v6a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h9',
  pronto: 'M12 3v12m0 0-4-4m4 4 4-4M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2',
}
const ITENS = [
  ['preparo', 'Nova edição'],
  ['render', 'Processando'],
  ['revisao', 'Revisão'],
  ['pronto', 'Master pronto'],
]

export default function Barra({ view, ativa }) {
  return (
    <aside className="lateral">
      <div className="lateral-marca">
        <span className="marca-icone" aria-hidden="true">
          <svg viewBox="0 0 24 24"><circle cx="6" cy="6" r="3" /><circle cx="6" cy="18" r="3" /><path d="M20 4 8.1 15.9M14.5 14.5 20 20M8.1 8.1 12 12" /></svg>
        </span>
        <span className="marca-nome">Mesa de Corte<small>motor de edição</small></span>
      </div>

      <nav className="lateral-nav">
        {ITENS.map(([chave, rotulo]) => (
          <span key={chave} className={'nav-item' + ((view === chave || (chave === 'pronto' && view === 'erro')) ? ' atual' : '')}>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d={ICONES[chave]} /></svg>
            {chave === 'pronto' && view === 'erro' ? 'Erro' : rotulo}
          </span>
        ))}
      </nav>

      <div className="lateral-rodape">
        <span className="lateral-stack">ffmpeg · auto-editor · whisper · claude</span>
        <div className="usuario">
          <span className="avatar">OH</span>
          <span className="usuario-txt">
            <strong>Otavio Herdy</strong>
            <small>{ativa ? 'editando agora' : 'ocioso'}</small>
          </span>
          <span className={'rec' + (ativa ? ' ligado' : '')} title="gravando = editando" />
        </div>
      </div>
    </aside>
  )
}
