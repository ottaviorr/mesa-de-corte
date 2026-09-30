#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""encode.py — FONTE ÚNICA dos argumentos de codificação do ffmpeg.

Lê as variáveis de ambiente MOTOR_* (as escolhas de codec/qualidade/áudio que o
usuário faz na UI) e devolve as listas de flags do ffmpeg. É usado pelo pipeline
(Python, importando este módulo) E pelos scripts bash (via
`python3 app/encode.py venc|aenc`), pra que os 6 passos codifiquem exatamente
com os mesmos parâmetros — sem divergência entre eles.

Padrões vêm no MÁXIMO de qualidade (o usuário pode baixar na UI):
libx264, CRF 12, preset slow, cor bt709 preservada, áudio AAC 320k.
"""

import os
import shlex
import sys

DEFAULTS = {
    'MOTOR_VCODEC': 'libx264',      # libx264 | libx265 | prores_ks | h264_videotoolbox | hevc_videotoolbox | h264_nvenc | hevc_nvenc
    'MOTOR_RATE_MODE': 'crf',       # crf | bitrate
    'MOTOR_CRF': '12',              # menor = melhor (x264/x265; no NVENC vira o -cq). 12 ~ quase sem perda
    'MOTOR_VBITRATE': '20M',        # usado quando RATE_MODE=bitrate
    'MOTOR_PRESET': 'slow',         # esforço x264/x265 (slower = melhor/mais lento)
    'MOTOR_PIXFMT': 'yuv420p',
    'MOTOR_ACODEC': 'aac',          # aac | alac | flac
    'MOTOR_AUDIO_BITRATE': '320k',  # só p/ aac (alac/flac são lossless)
    'MOTOR_PRORES_PROFILE': '3',    # 0-5 (3 = 422 HQ)
    'MOTOR_VTQ': '55',              # qualidade videotoolbox (0-100, maior=melhor)
}

# codecs que aceitam -preset/-crf estilo x26x
_X26X = ('libx264', 'libx265')
_VIDEOTOOLBOX = ('h264_videotoolbox', 'hevc_videotoolbox')
_NVENC = ('h264_nvenc', 'hevc_nvenc')

COR = ['-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709']


def _get(chave):
    v = os.environ.get(chave, '')
    return v if v != '' else DEFAULTS.get(chave, '')


def venc():
    """Args de codificação de VÍDEO conforme as MOTOR_*."""
    codec = _get('MOTOR_VCODEC')
    modo = _get('MOTOR_RATE_MODE')

    if codec in ('prores_ks', 'prores'):
        # ProRes: mastering quase-lossless; profile define a qualidade (3 = HQ).
        return ['-c:v', 'prores_ks', '-profile:v', _get('MOTOR_PRORES_PROFILE'),
                '-pix_fmt', 'yuv422p10le']

    args = ['-c:v', codec]
    if codec in _X26X:
        args += ['-preset', _get('MOTOR_PRESET')]
        if modo == 'bitrate':
            args += ['-b:v', _get('MOTOR_VBITRATE')]
        else:
            args += ['-crf', _get('MOTOR_CRF')]
        args += ['-pix_fmt', _get('MOTOR_PIXFMT')]
        if codec == 'libx265':
            args += ['-tag:v', 'hvc1']       # compatibilidade Apple/QuickTime
    elif codec in _VIDEOTOOLBOX:
        # aceleração por hardware do Mac: usa bitrate OU -q:v (qualidade)
        if modo == 'bitrate':
            args += ['-b:v', _get('MOTOR_VBITRATE')]
        else:
            args += ['-q:v', _get('MOTOR_VTQ')]
        args += ['-pix_fmt', _get('MOTOR_PIXFMT')]
        if codec == 'hevc_videotoolbox':
            args += ['-tag:v', 'hvc1']
    elif codec in _NVENC:
        # placa NVIDIA: p5 + tune hq = bom equilíbrio velocidade/qualidade.
        # Modo "crf" vira qualidade constante (-cq, mesma escala 0-51).
        args += ['-preset', 'p5', '-tune', 'hq', '-rc', 'vbr']
        if modo == 'bitrate':
            args += ['-b:v', _get('MOTOR_VBITRATE')]
        else:
            args += ['-cq', _get('MOTOR_CRF'), '-b:v', '0']
        args += ['-pix_fmt', _get('MOTOR_PIXFMT')]
        if codec == 'hevc_nvenc':
            args += ['-tag:v', 'hvc1']
        else:
            args += ['-profile:v', 'high']   # sem isso o NVENC cai no Main
    else:                                   # desconhecido: trata como x264
        args += ['-preset', _get('MOTOR_PRESET'), '-crf', _get('MOTOR_CRF'),
                 '-pix_fmt', _get('MOTOR_PIXFMT')]
    args += COR
    return args


def aenc():
    """Args de codificação de ÁUDIO conforme as MOTOR_*."""
    codec = _get('MOTOR_ACODEC')
    if codec == 'alac':
        return ['-c:a', 'alac']              # lossless
    if codec == 'flac':
        return ['-c:a', 'flac']              # lossless
    return ['-c:a', 'aac', '-b:a', _get('MOTOR_AUDIO_BITRATE')]


def resumo():
    """String curta pro log/UI descrevendo a config atual."""
    codec = _get('MOTOR_VCODEC')
    if codec in ('prores_ks', 'prores'):
        taxa = 'prores p%s' % _get('MOTOR_PRORES_PROFILE')
    elif _get('MOTOR_RATE_MODE') == 'bitrate':
        taxa = 'bitrate %s' % _get('MOTOR_VBITRATE')
    elif codec in _VIDEOTOOLBOX:
        taxa = 'q %s' % _get('MOTOR_VTQ')
    elif codec in _NVENC:
        taxa = 'cq %s' % _get('MOTOR_CRF')
    else:
        taxa = 'crf %s' % _get('MOTOR_CRF')
    res = _get('MOTOR_RES') or 'original'
    fps = _get('MOTOR_FPS') or 'original'
    return '%s · %s · %s · %s · %sfps' % (
        codec, taxa, _get('MOTOR_ACODEC'), res if res != 'original' else 'res-orig',
        fps if fps != 'original' else 'orig')


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else 'venc'
    fn = {'venc': venc, 'aenc': aenc}.get(what)
    if fn is None:
        print(resumo()); return
    # imprime shell-quoted pra ser lido com `eval "X=( $(...) )"` no bash
    print(' '.join(shlex.quote(a) for a in fn()))


if __name__ == '__main__':
    main()
