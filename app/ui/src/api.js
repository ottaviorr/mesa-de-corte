// api.js — conversa com o backend Python (via proxy do Vite, mesma origem).

export async function getStatus() {
  return (await fetch('/api/status')).json();
}

export async function getEntrada() {
  return (await fetch('/api/entrada')).json();
}

export async function getDiagnostico() {
  return (await fetch('/api/diagnostico')).json();
}

export async function confirmarRevisao(cortes, zooms) {
  return fetch('/api/confirmar', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cortes, zooms }),
  });
}

export async function cancelarEdicao() {
  return fetch('/api/cancelar', { method: 'POST' });
}

export async function resetar() {
  return fetch('/api/reset', { method: 'POST' });
}

// Upload com progresso (XHR — fetch não reporta progresso de envio).
export function iniciarEdicao(formData, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/iniciar');
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      if (xhr.status === 200) return resolve(JSON.parse(xhr.responseText || '{}'));
      let msg = 'Falha ao iniciar.';
      try { msg = JSON.parse(xhr.responseText).erro || msg; } catch { /* corpo não-JSON */ }
      reject(new Error(msg));
    };
    xhr.onerror = () => reject(new Error('Não consegui falar com o servidor. Ele ainda está rodando?'));
    xhr.send(formData);
  });
}
