// utils.js — formatadores puros (JSX já escapa texto, então sem escapeHtml).

export function fmtHMS(s) {
  s = Math.max(0, Math.round(s));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), seg = s % 60;
  return [h, m, seg].map((n) => String(n).padStart(2, '0')).join(':');
}

export function fmtMS(s) {
  s = Math.max(0, Math.round(s));
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
}

export function fmtBytes(b) {
  if (b > 1e9) return (b / 1e9).toFixed(2) + ' GB';
  if (b > 1e6) return (b / 1e6).toFixed(1) + ' MB';
  return Math.round(b / 1e3) + ' KB';
}

// Estimativa (grosseira) da taxa de saída e do peso do arquivo, conforme a
// config de qualidade escolhida. A heurística de CRF é ancorada em conteúdo de
// TELA (medido no vídeo real: CRF 14 ≈ 2,9 Mbps @1080p30). É só uma noção — o
// resultado final costuma ser MENOR (os cortes encurtam o vídeo).
export function estimarSaida(q, meta) {
  const bits = (s) => {                       // '20M'->20, '320k'->0.32 (Mbps)
    const m = String(s || '').match(/^([\d.]+)\s*([MmKk])/);
    if (!m) return 0;
    const n = parseFloat(m[1]);
    return m[2].toLowerCase() === 'm' ? n : n / 1000;
  };
  const PX1080 = 1920 * 1080;
  let px;
  if (q.res === '1080') px = 1920 * 1080;
  else if (q.res === '1440') px = 2560 * 1440;
  else if (q.res === '2160') px = 3840 * 2160;
  else px = (meta && meta.w && meta.h) ? meta.w * meta.h : PX1080;   // original
  const fRes = px / PX1080;
  const fps = q.fps === 'original' ? 30 : Number(q.fps);
  const fFps = 1 + ((fps - 30) / 30) * 0.6;   // 60fps ~ +60% de taxa

  let vMbps;
  const codec = q.vcodec;
  if (codec === 'prores_ks') {
    vMbps = 176 * fRes * (fps / 30);          // ProRes 422 HQ ~176 Mbps @1080p30
  } else if (codec.includes('videotoolbox') || q.rate_mode === 'bitrate') {
    vMbps = bits(q.vbitrate);                 // bitrate alvo é o próprio número
  } else {                                    // CRF (x264/x265) — conteúdo de tela
    let base = 3.5 * Math.pow(2, (14 - Number(q.crf)) / 6);
    if (codec === 'libx265' || codec === 'hevc_nvenc') base *= 0.6;
    vMbps = base * fRes * fFps;
  }
  const aMbps = q.acodec === 'aac' ? bits(q.audio_bitrate) : 1.0;  // alac/flac ~1 Mbps
  const total = vMbps + aMbps;
  return { total, mbPorMin: total * 7.5, dur: meta && meta.dur ? meta.dur : null };
}

export const FASES_RODANDO = ['iniciando', 'normalizar', 'silencio', 'transcrever',
  'analise', 'limpar', 'montagem', 'velocidade', 'finalizar'];

export const FRASES = {
  enviando:    ['Recebendo a fita… não fecha a aba!'],
  iniciando:   ['Ligando a mesa…', 'Esquentando as válvulas…'],
  normalizar:  ['Esticando pra 1080p sem perder o brilho…', 'Nivelando o áudio do mic…', 'Padronizando 30fps…'],
  silencio:    ['Caçando silêncios constrangedores…', 'Respiro longo? Aqui não.', 'Apertando o ritmo da fala…'],
  transcrever: ['Ouvindo tudo com atenção (Whisper)…', 'Anotando cada palavra em PT-BR…', 'Marcando o tempo de cada palavra…'],
  analise:     ['Procurando aquele "corta, editou"…', 'Comparando takes — a última versão vence…', 'Consultando o Claude sobre os tropeços…', 'Separando ênfase de gagueira…'],
  limpar:      ['Tesoura em punho ✂', 'Removendo os takes que não mereciam ficar…', 'Colando os pedaços bons…'],
  montagem:    ['Colando intro e CTA…', 'Costurando as pontas…'],
  velocidade:  ['Acelerando sem virar voz de esquilo…', 'Ajustando o tempo, preservando o tom…'],
  finalizar:   ['Carimbando o master…', 'Sincronizando a legenda…', 'Últimos frames…'],
};

export const CANAIS = [
  { modo: 1, num: 'CH·01', nome: 'Silêncio fora', tags: [],
    desc: 'Corta pausas, respiros e buracos. O vídeo inteiro, só que enxuto.' },
  { modo: 2, num: 'CH·02', nome: 'Corte inteligente', tags: ['ia'],
    desc: 'Silêncio fora + caça takes errados, recados pro editor e gagueiras.' },
  { modo: 3, num: 'CH·03', nome: 'Silêncio + turbo', tags: ['vel'],
    desc: 'Canal 01 com aceleração de 1.05× a 2× — voz mantida natural.' },
  { modo: 4, num: 'CH·04', nome: 'Edição completa', tags: ['ia', 'vel'],
    desc: 'Canal 02 com aceleração. O tratamento completo do canal.' },
];
