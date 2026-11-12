"""Looks over a run of clips: a colour grade, and a frame (a border with a soft inner glow, as for a flashback).

A grade is an ffmpeg filter chain worked in RGB with the BT.709 matrix both ways (the capture and the master are
BT.709; ffmpeg's automatic conversion would assume BT.601 and shift the colours). A frame is a PNG with alpha made
here with the standard library (zlib), overlaid on each clip of the run.
"""
import math
import struct
import zlib
from pathlib import Path

TO_RGB = 'scale=in_color_matrix=bt709:in_range=tv,format=gbrp'
TO_YUV = 'scale=out_color_matrix=bt709:out_range=tv,format=yuv420p'

# Named grades: (saturation, contrast, brightness, gamma, tint colour, tint amount). Tint keeps each pixel's luminance
# and moves its colour towards the tint's.
PRESETS = {
    'sepia': (0.75, 0.97, -0.01, 1.0, '#b89470', 0.5),
    'warm': (1.06, 1.03, 0.01, 1.0, '#ffb070', 0.14),
    'cool': (0.94, 1.03, 0.0, 1.0, '#7fb0ff', 0.16),
    'crush': (1.12, 1.22, -0.03, 1.0, None, 0.0),
    'mono': (0.0, 1.08, 0.0, 1.0, None, 0.0),
    'none': (1.0, 1.0, 0.0, 1.0, None, 0.0),
}


def hex_rgb(text, where='colour'):
    h = str(text).lstrip('#')
    if len(h) != 6 or any(c not in '0123456789abcdefABCDEF' for c in h):
        raise ValueError(f'{where}: a colour is "#rrggbb" (got {text!r})')
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def grade_filter(grade):
    """The ffmpeg chain for a grade name or table, starting and ending in yuv420p; '' for none."""
    if grade is None:
        return ''
    if isinstance(grade, str):
        sat, con, bri, gam, tint, amount = PRESETS[grade]
    else:
        sat = float(grade.get('saturation', 1.0))
        con = float(grade.get('contrast', 1.0))
        bri = float(grade.get('brightness', 0.0))
        gam = float(grade.get('gamma', 1.0))
        tint = grade.get('tint')
        amount = float(grade.get('amount', 0.5 if tint else 0.0))
    chain = []
    if (sat, con, bri, gam) != (1.0, 1.0, 0.0, 1.0):
        chain.append(f'eq=saturation={sat:.4f}:contrast={con:.4f}:brightness={bri:.4f}:gamma={gam:.4f}')
    if tint and amount > 0:
        chain += [TO_RGB, 'colorchannelmixer=' + ':'.join(f'{v:.5f}' for v in tint_matrix(hex_rgb(tint, 'grade.tint'), amount)), TO_YUV]
    return ','.join(chain)


def tint_matrix(rgb, amount):
    """colorchannelmixer coefficients rr:rg:rb:ra:gr:gg:gb:ga:br:bg:bb:ba blending each pixel towards luma * tint.

    The tint is scaled so its own luminance is 1: white stays white-ish, grey keeps its brightness, colours drift to the tint.
    """
    luma = (0.2126, 0.7152, 0.0722)
    tl = sum(l * c for l, c in zip(luma, rgb)) or 1.0
    t = [c / tl for c in rgb]
    out = []
    for row, tc in enumerate(t):
        for col in range(3):
            ident = 1.0 if row == col else 0.0
            out.append((1 - amount) * ident + amount * tc * luma[col])
        out.append(0.0)
    return out


def frame_png(path, width, height, color='#e8a23a', border=28, glow=12, opacity=1.0, scale=1.0):
    """Writes the frame of a look as an RGBA PNG: a solid border `border` px wide and a glow fading inwards over about
    `glow` px. Sizes are 1080-line pixels (scaled by `scale` for other frames)."""
    r, g, b = (int(round(c * 255)) for c in hex_rgb(color, 'frame.color'))
    bw = max(0.0, border * scale)
    gl = max(0.0, glow * scale)
    reach = int(math.ceil(bw + gl * 3)) + 1

    def alpha(d):  # d: distance in pixels from the frame's outer edge to the pixel's centre
        if d < bw - 0.5:
            a = 1.0
        elif d < bw + 0.5:
            a = bw + 0.5 - d  # antialiased inner edge of the solid border
            if gl > 0:
                a = max(a, 0.55)
        elif gl > 0:
            a = 0.55 * math.exp(-((d - bw) / gl) ** 2 * 1.6)
        else:
            a = 0.0
        return int(round(255 * opacity * min(1.0, max(0.0, a))))

    edge = [alpha(d + 0.5) for d in range(reach)]

    def row(y):
        dy = min(y, height - 1 - y)
        out = bytearray(b'\x00')  # filter type: none
        for x in range(width):
            d = min(x, width - 1 - x, dy)
            a = edge[d] if d < reach else 0
            out += bytes((r, g, b, a))
        return bytes(out)

    middle = None
    rows = []
    for y in range(height):
        if reach <= y < height - reach:
            if middle is None:
                middle = row(y)
            rows.append(middle)
        else:
            rows.append(row(y))
    raw = b''.join(rows)

    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xFFFFFFFF)

    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(raw, 6)) + chunk(b'IEND', b'')
    Path(path).write_bytes(png)
    return Path(path)
