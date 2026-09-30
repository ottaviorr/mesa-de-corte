// Mascote — gatinho que vive na tela (e vai pra onde você arrastar).
//   sentado   : respira, pisca, mexe a orelha, segue o cursor com olhos e cabeça
//               (mouse rápido -> pupilas dilatam, modo caçador)
//   rotina    : de tempos em tempos passeia, boceja, se lambe ou olha em volta
//   carinho   : mouse em cima dele -> fecha os olhos e ronrona
//   arrastado : pendurado pelo cangote, balança com o movimento e chuta as patinhas
//   pousando  : "plop" ao ser solto ou ao chegar do passeio
//   dormindo  : mouse parado um tempo -> cochila (zzz); mexeu, acorda bocejando
//   feliz     : clique -> pulinhos, corações e "miau!"
// Editando (ativo) ele não dorme e fica de olhos brilhando.
// A posição onde você o larga fica salva no navegador.

import { useEffect, useRef, useState } from 'react'

const VEL = 70              // px/s no passeio
const SONO = 30000          // ms sem mexer o mouse até cochilar
const TAM = 88
const CHAVE = 'mesa-gato-pos'

const prende = (v, a, b) => Math.min(b, Math.max(a, v))
const calmo = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches

function limitesX() {
  const min = window.innerWidth > 860 ? 262 : 8     // passeio não entra na lateral
  return [min, Math.max(min, window.innerWidth - TAM - 16)]
}
function dentro(p) {
  return { x: prende(p.x, 0, window.innerWidth - TAM), y: prende(p.y, 8, window.innerHeight - TAM) }   // 8: pontas das orelhas
}
// y salvo como distância do rodapé, pra continuar "no chão" se a janela mudar de altura
function posInicial() {
  try {
    const p = JSON.parse(localStorage.getItem(CHAVE))
    if (p) return dentro({ x: p.x, y: window.innerHeight - p.b })
  } catch { /* sem storage: posição padrão */ }
  return { x: limitesX()[1], y: window.innerHeight - TAM - 12 }
}
function salvar(p) {
  try { localStorage.setItem(CHAVE, JSON.stringify({ x: p.x, b: window.innerHeight - p.y })) } catch { /* ok */ }
}

export default function Mascote({ ativo }) {
  const [estado, setEstado] = useState('sentado')
  const [pos, setPos] = useState(posInicial)
  const [dur, setDur] = useState(0)
  const [virado, setVirado] = useState(false)      // true = de frente pra direita
  const [miau, setMiau] = useState(0)               // re-dispara corações/balão
  const raiz = useRef(null)
  const pendura = useRef(null)
  const svg = useRef(null)
  const drag = useRef(null)
  const cursor = useRef({ x: 0, y: 0, t: performance.now() })
  const olhando = useRef([0, 0])
  const pupila = useRef(1)
  const t = useRef({})                              // timeouts nomeados
  const r = useRef({})                              // estado atual pra timers/listeners
  r.current = { estado, pos, virado, ativo }

  // pupilas + inclinação da cabeça (direto no DOM — sem re-render a cada pixel)
  function olhar(dx, dy) {
    const s = svg.current
    if (!s) return
    olhando.current = [dx, dy]
    const d = Math.hypot(dx, dy) || 1
    const tr = `translate(${(dx / d) * 1.2}px, ${(dy / d) * 1.1}px) scale(${pupila.current})`
    s.querySelectorAll('.gato-pupila').forEach((p) => { p.style.transform = tr })
    s.querySelector('.gato-cabeca').style.transform =
      `rotate(${prende(dx / 400, -1, 1) * 6}deg)`
  }

  // estado temporário que volta pro "sentado" sozinho (se nada o interrompeu)
  function acao(nome, ms) {
    clearTimeout(t.current.acao)
    setEstado(nome)
    t.current.acao = setTimeout(() => { if (r.current.estado === nome) setEstado('sentado') }, ms)
  }

  function andar() {
    const [a, b] = limitesX()
    const atual = r.current.pos.x
    let alvo = atual
    for (let i = 0; i < 6 && Math.abs(alvo - atual) < 160; i++) alvo = a + Math.random() * (b - a)
    if (Math.abs(alvo - atual) < 60) return
    setVirado(alvo > atual)
    setDur(Math.abs(alvo - atual) / VEL)
    setPos({ x: alvo, y: r.current.pos.y })
    setEstado('andando')
  }

  function olharEmVolta() {
    ;[[-400, 60], [400, 60], [150, -200], [0, 0]].forEach(([dx, dy], i) => {
      setTimeout(() => { if (r.current.estado === 'sentado') olhar(dx, dy) }, i * 650)
    })
  }

  // balanço de quem está pendurado: inclina com a velocidade e volta com mola
  function balancar(graus) {
    const el = pendura.current
    if (!el) return
    el.style.transition = 'transform .15s ease-out'
    el.style.transform = `rotate(${graus}deg)`
    clearTimeout(t.current.mola)
    t.current.mola = setTimeout(() => {
      el.style.transition = 'transform .9s cubic-bezier(.3, 1.9, .4, 1)'
      el.style.transform = 'rotate(0deg)'
    }, 90)
  }

  function mover(e) {
    const agora = performance.now()
    const c = cursor.current
    const vel = Math.hypot(e.clientX - c.x, e.clientY - c.y) / Math.max(1, agora - c.t)
    cursor.current = { x: e.clientX, y: e.clientY, t: agora }
    if (drag.current) return
    const { estado: est, virado: vir } = r.current
    if (est === 'dormindo') { acao('bocejo', 1900); return }   // acorda bocejando
    if (est !== 'sentado' || !svg.current) return
    if (vel > 2.5) {                                            // mouse rápido: modo caçador
      pupila.current = 1.4
      clearTimeout(t.current.caca)
      t.current.caca = setTimeout(() => { pupila.current = 1; olhar(...olhando.current) }, 900)
    }
    const b = svg.current.getBoundingClientRect()
    // a cabeça fica no terço esquerdo do desenho (o rabo ocupa a direita)
    const dx = e.clientX - (b.left + b.width * (vir ? 0.67 : 0.33))
    olhar(vir ? -dx : dx, e.clientY - (b.top + b.height * 0.3))
  }

  function clicar() {
    cursor.current.t = performance.now()
    if (r.current.estado === 'andando') {           // para onde está
      const b = raiz.current.getBoundingClientRect()
      setDur(0)
      setPos({ x: b.left, y: b.top })
    }
    setMiau((n) => n + 1)
    acao('feliz', 1800)
  }

  // ---- arrastar (pointer events: mouse e toque)
  function agarrar(e) {
    if (e.button !== 0) return
    const b = raiz.current.getBoundingClientRect()
    drag.current = {
      ox: e.clientX - b.left, oy: e.clientY - b.top, sx: e.clientX, sy: e.clientY,
      movido: false, vx: 0, lx: e.clientX, lt: performance.now(), pos: null,
    }
    e.currentTarget.setPointerCapture(e.pointerId)
  }
  function arrastar(e) {
    const d = drag.current
    if (!d) return
    if (!d.movido) {
      if (Math.hypot(e.clientX - d.sx, e.clientY - d.sy) < 5) return   // ainda é clique
      d.movido = true
      clearTimeout(t.current.acao)
      setDur(0)
      setEstado('arrastado')
    }
    const agora = performance.now()
    d.vx = d.vx * 0.6 + ((e.clientX - d.lx) / Math.max(1, agora - d.lt)) * 0.4
    d.lx = e.clientX
    d.lt = agora
    d.pos = dentro({ x: e.clientX - d.ox, y: e.clientY - d.oy })
    setPos(d.pos)
    balancar(prende(d.vx * 25, -40, 40))
  }
  function soltar() {
    const d = drag.current
    drag.current = null
    if (!d) return
    if (!d.movido) { clicar(); return }
    if (d.pos) salvar(d.pos)
    balancar(0)
    acao('pousando', 520)
  }

  function chegou(e) {
    if (e.target === raiz.current && r.current.estado === 'andando') {
      setDur(0)
      salvar(r.current.pos)
      acao('pousando', 450)
    }
  }

  useEffect(() => {
    const tt = t.current
    window.addEventListener('mousemove', mover)

    // rotina: passeio / bocejo / lambida / olhar em volta
    const rotina = () => {
      tt.rotina = setTimeout(() => {
        if (r.current.estado === 'sentado' && !document.hidden) {
          const s = Math.random()
          if (s < 0.4) { if (!calmo()) andar() }
          else if (s < 0.58) acao('bocejo', 2000)
          else if (s < 0.8) acao('lambendo', 3200)
          else olharEmVolta()
        }
        rotina()
      }, 6000 + Math.random() * 9000)
    }
    rotina()

    // piscadas em ritmo irregular (às vezes dupla)
    const umaPiscada = () => {
      const el = raiz.current
      if (!el) return
      el.classList.add('pisca')
      setTimeout(() => el.classList.remove('pisca'), 130)
    }
    const piscar = () => {
      tt.pisca = setTimeout(() => {
        umaPiscada()
        if (Math.random() < 0.25) setTimeout(umaPiscada, 280)
        piscar()
      }, 1800 + Math.random() * 4500)
    }
    piscar()

    const sono = setInterval(() => {
      if (r.current.estado === 'sentado' && !r.current.ativo &&
          performance.now() - cursor.current.t > SONO) setEstado('dormindo')
    }, 2000)

    const ajustar = () => { setDur(0); setPos((p) => dentro(p)) }
    window.addEventListener('resize', ajustar)
    return () => {
      window.removeEventListener('mousemove', mover)
      window.removeEventListener('resize', ajustar)
      clearInterval(sono)
      Object.values(tt).forEach(clearTimeout)
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // fora do "sentado", olha pra frente (andando: pra onde vai)
  useEffect(() => {
    if (estado === 'andando') olhar(-1, 0)
    else if (estado !== 'sentado') olhar(0, 0)
  }, [estado])

  useEffect(() => { if (ativo && r.current.estado === 'dormindo') setEstado('sentado') }, [ativo])

  return (
    <div
      ref={raiz}
      className={`mascote ${estado}${ativo ? ' ativo' : ''}${virado ? ' virado' : ''}`}
      style={{ transform: `translate(${pos.x}px, ${pos.y}px)`, transition: `transform ${dur}s linear` }}
      onTransitionEnd={chegou}
      aria-hidden="true"
    >
      {estado === 'feliz' && <span key={'b' + miau} className="gato-balao">miau!</span>}
      {estado === 'feliz' && <span key={'c' + miau} className="gato-coracoes"><i>♥</i><i>♥</i><i>♥</i></span>}
      {estado === 'dormindo' && <span className="gato-zz"><i>z</i><i>z</i><i>Z</i></span>}
      {estado === 'carinho' && <span className="gato-zz gato-prr"><i>prr</i><i>prr</i></span>}
      <div ref={pendura} className="gato-pendura" style={{ transformOrigin: virado ? '67% 4%' : '33% 4%' }}>
        <div className={'gato-flip' + (virado ? ' virado' : '')}>
          <svg
            ref={svg} viewBox="0 0 64 64" width={TAM} height={TAM}
            onPointerDown={agarrar} onPointerMove={arrastar}
            onPointerUp={soltar} onPointerCancel={soltar}
            onPointerEnter={() => { if (!drag.current && r.current.estado === 'sentado') setEstado('carinho') }}
            onPointerLeave={() => { if (r.current.estado === 'carinho') setEstado('sentado') }}
          >
            <ellipse className="gato-sombra" cx="26" cy="61.6" rx="21" ry="1.8" />
            <g className="gato-todo">
              <g className="gato-respira">
                <rect className="gato-rabo" x="40" y="55.6" width="22" height="3.6" rx="1.8" />
                <rect className="gato-pelo pata-e" x="8.1" y="50" width="7.4" height="11" rx="3.7" />
                <rect className="gato-pelo pata-d" x="19.8" y="50" width="7.4" height="11" rx="3.7" />
                <path className="gato-pelo" d="M8.1 30H32.6C39.5 33.6 44.2 41.7 44.2 49.8V58.4H8.1Z" />

                <g className="gato-cabeca">
                  <g className="orelha-e">
                    <path className="gato-pelo" d="M3.5 11 5.4-1.8 15.1 6.8Z" />
                    <path className="gato-rosa" d="M4.6 8.6 5.6.2 10.4 5.2Z" />
                  </g>
                  <g className="orelha-d">
                    <path className="gato-pelo" d="M38.5 11 36.6-1.8 26.9 6.8Z" />
                    <path className="gato-rosa" d="M37.4 8.6 36.4.2 31.6 5.2Z" />
                  </g>
                  <rect className="gato-pelo" x="1.2" y="5.7" width="39.6" height="26.7" rx="7.5" />
                  <ellipse className="gato-bochecha" cx="9" cy="23.6" rx="2.4" ry="1.3" />
                  <ellipse className="gato-bochecha" cx="33" cy="23.6" rx="2.4" ry="1.3" />

                  <g className="olhos-abertos">
                    <circle className="gato-olho" cx="12.8" cy="18.4" r="4.3" />
                    <circle className="gato-olho" cx="29.2" cy="18.4" r="4.3" />
                    <circle className="gato-pelo gato-pupila" cx="12.8" cy="18.4" r="2.3" />
                    <circle className="gato-pelo gato-pupila" cx="29.2" cy="18.4" r="2.3" />
                  </g>
                  <path className="gato-arco olhos-fechados" d="M9.6 18.6Q12.8 21.2 16 18.6M26 18.6Q29.2 21.2 32.4 18.6" />
                  <path className="gato-arco olhos-felizes" d="M9.6 19.8Q12.8 16 16 19.8M26 19.8Q29.2 16 32.4 19.8" />

                  <path className="gato-nariz" d="M19.9 21.4h2.2L21 22.6Z" />
                  <path className="gato-boca boca-normal" d="M21 22.6v.8m0 0-1 .7m1-.7 1 .7" />
                  <ellipse className="boca-o" cx="21" cy="24.6" rx="1.2" ry="1.5" />
                  <g className="boca-bocejo">
                    <ellipse cx="21" cy="25.4" rx="2.7" ry="3.3" fill="#6b2228" />
                    <ellipse cx="21" cy="27.2" rx="1.7" ry="1.2" fill="#e8674a" />
                  </g>
                  <ellipse className="gato-lingua" cx="21" cy="24.2" rx=".9" ry=".8" />
                </g>

                {/* patinha que sobe pra se lamber (só aparece no "lambendo") */}
                <g className="gato-braco">
                  <path d="M12 45 16.4 27.5" stroke="#1a1416" strokeWidth="7.6" strokeLinecap="round" />
                  <path className="gato-braco-pelo" d="M12 45 16.4 27.5" strokeWidth="6" strokeLinecap="round" />
                  <circle cx="15.3" cy="26.6" r=".7" fill="#e8674a" />
                  <circle cx="17.2" cy="26.9" r=".7" fill="#e8674a" />
                </g>
              </g>
            </g>
          </svg>
        </div>
      </div>
    </div>
  )
}
