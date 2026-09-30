#!/usr/bin/env python3
"""limiar.py — escolhe o threshold de silêncio a partir do PRÓPRIO áudio.

Valor fixo não serve: o threshold do auto-editor é ABSOLUTO (fração do fundo de
escala), então depende do ganho do mic naquela gravação. O 4% fixo caía DENTRO
da faixa da fala deste canal (fala ~-22 dB, ruído ~-50 dB) e por isso comia
início/fim de palavra. Aqui o corte cai no meio do caminho EM dB entre o ruído
de fundo (p10) e a fala (p75) — o vale do histograma.

Uso:  python3 app/limiar.py trabalho/01_normalizado.mp4   -> imprime ex. "1.3%"
      python3 app/limiar.py --demo                        -> autoteste
"""
import subprocess
import sys

MIN, MAX = 0.008, 0.030   # trava: nem mais agressivo que 3%, nem inútil abaixo de 0,8%


def escolher(niveis):
    """Média geométrica entre ruído e fala = ponto médio em dB (o vale)."""
    n = sorted(niveis)
    p = lambda q: n[min(len(n) - 1, int(q * len(n)))]
    ruido, fala = max(p(0.10), 1e-4), p(0.75)
    return min(MAX, max(MIN, (ruido * fala) ** 0.5))


def niveis_do_video(caminho):
    """Os mesmos números que o auto-editor usa pra decidir o corte."""
    saida = subprocess.run(['auto-editor', 'levels', caminho, '--edit', 'audio'],
                           capture_output=True, text=True, check=True).stdout
    return [float(l) for l in saida.splitlines() if l.strip() and not l.startswith('@')]


def demo():
    fala = escolher([0.003] * 500 + [0.08] * 500)     # caso real: ruído -50dB, fala -22dB
    assert 0.003 < fala < 0.08, fala                  # corta o ruído, poupa a fala
    assert escolher([0.08] * 1000) <= MAX             # sem silêncio: não vira agressivo
    assert escolher([0.0] * 1000) >= MIN              # tudo mudo: não zera
    print('ok')


if __name__ == '__main__':
    if '--demo' in sys.argv:
        demo()
    else:
        print('%.1f%%' % (escolher(niveis_do_video(sys.argv[1])) * 100))
