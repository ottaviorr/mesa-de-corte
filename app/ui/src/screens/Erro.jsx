// Tela 5 — erro: mensagem + cauda do log, com volta pra mesa.

export default function Erro({ status, onVoltar }) {
  return (
    <section className="tela ativa">
      <h2 className="titulo-tela erro-titulo">⊘ SINAL PERDIDO</h2>
      <p className="lema">{status.erro || 'Algo deu errado no meio da edição.'}</p>
      <pre className="monitor">{(status.log || []).join('\n')}</pre>
      <div className="acoes">
        <button className="btn-principal" onClick={onVoltar}>← voltar à mesa</button>
      </div>
    </section>
  )
}
