"""Checa o loop de leitura do rodar() — precisa funcionar no Windows (sem select).

    python app/test_rodar.py
"""
import os
import sys
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pipeline


def nova(job_extra=None):
    job = {'log': deque(maxlen=500), 'fase': None}
    job.update(job_extra or {})
    p = pipeline.Pipeline(job)
    p.etapas, p.pesos_ativos = ['x'], {'x': 100}
    return p


def main():
    # saída capturada, linha a linha, com acento e emoji
    p = nova()
    p.rodar([sys.executable, '-c',
             'print("ola \\u00e7\\u00e3o \\U0001f3ac"); print("fim")'], 'x')
    linhas = list(p.job['log'])
    assert 'ola ção 🎬' in linhas, linhas
    assert 'fim' in linhas, linhas

    # código != 0 vira erro
    p = nova()
    try:
        p.rodar([sys.executable, '-c', 'raise SystemExit(3)'], 'x')
        raise AssertionError('devia ter levantado')
    except RuntimeError as e:
        assert 'código 3' in str(e), e

    # cancelamento mata o processo em vez de esperar ele terminar
    p = nova({'cancelar': True})
    try:
        p.rodar([sys.executable, '-c', 'import time; time.sleep(60)'], 'x')
        raise AssertionError('devia ter cancelado')
    except pipeline.Cancelado:
        pass

    # linha de progresso do ffmpeg move a barra em vez de virar log
    p = nova()
    p.rodar([sys.executable, '-c', r'print("time=00:00:30.00 bitrate=1")'],
            'x', dur_referencia=60.0)
    assert p.job['progresso'] == 50, p.job['progresso']
    assert not list(p.job['log'])[1:], list(p.job['log'])

    print('ok')


if __name__ == '__main__':
    main()
