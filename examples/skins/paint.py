"""Paints the example mannequins' skins (original art, flat colours on the 64x64 player-skin layout), stdlib only.

    python3 examples/skins/paint.py      # rewrites ana.png and ben.png next to this file
"""
import struct
import zlib
from pathlib import Path

SKINS = {
    'ana': {'skin': (226, 182, 150), 'hair': (64, 38, 28), 'eyes': (40, 90, 160), 'top': (214, 76, 64),
            'trim': (250, 236, 220), 'legs': (52, 64, 98), 'shoes': (240, 240, 240), 'long_hair': True},
    'ben': {'skin': (150, 104, 74), 'hair': (24, 20, 18), 'eyes': (30, 30, 30), 'top': (70, 140, 96),
            'trim': (36, 80, 54), 'legs': (120, 96, 70), 'shoes': (60, 44, 34), 'long_hair': False},
}


def paint(spec):
    px = [[(0, 0, 0, 0)] * 64 for _ in range(64)]

    def rect(x, y, w, h, rgb):
        for j in range(y, y + h):
            for i in range(x, x + w):
                px[j][i] = (*rgb, 255)

    # Head: faces at y 0-16 (top/bottom row 0-8, sides 8-16), all skin, then hair on top, back and the upper sides.
    rect(8, 0, 16, 8, spec['skin'])
    rect(0, 8, 32, 8, spec['skin'])
    rect(8, 0, 8, 8, spec['hair'])                       # top of the head
    rect(24, 8, 8, 8 if spec['long_hair'] else 6, spec['hair'])  # back
    rect(0, 8, 8, 5 if spec['long_hair'] else 3, spec['hair'])   # right side
    rect(16, 8, 8, 5 if spec['long_hair'] else 3, spec['hair'])  # left side
    rect(8, 8, 8, 2, spec['hair'])                        # fringe on the face
    # Face (front, x 8-16, y 8-16): eyes with whites, a mouth.
    for ex in (9, 13):
        rect(ex, 11, 2, 1, (250, 250, 250))
        rect(ex + (1 if ex == 9 else 0), 11, 1, 1, spec['eyes'])
    rect(11, 14, 2, 1, tuple(max(0, c - 60) for c in spec['skin']))
    # Body and arms (y 16-32): the top, with trim at the collar and the cuffs; hands in skin.
    rect(16, 16, 40, 16, spec['top'])
    rect(20, 20, 8, 1, spec['trim'])
    for x in (40, 44, 48, 52):
        rect(x, 29, 4, 1, spec['trim'])
        rect(x, 30, 4, 2, spec['skin'])
    rect(48, 16, 4, 4, spec['skin'])                      # bottom of the right hand
    # Legs: right leg (x 0-16, y 16-32), left leg and left arm on the lower half (y 48-64).
    rect(0, 16, 16, 16, spec['legs'])
    rect(0, 29, 16, 3, spec['shoes'])
    rect(16, 48, 16, 16, spec['legs'])
    rect(16, 61, 16, 3, spec['shoes'])
    rect(32, 48, 16, 16, spec['top'])
    for x in (32, 36, 40, 44):
        rect(x, 61, 4, 1, spec['trim'])
        rect(x, 62, 4, 2, spec['skin'])
    return px


def png(px, path):
    raw = b''.join(b'\x00' + b''.join(bytes(p) for p in row) for row in px)
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    data = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 64, 64, 8, 6, 0, 0, 0))
    data += chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b'')
    Path(path).write_bytes(data)


if __name__ == '__main__':
    here = Path(__file__).parent
    for name, spec in SKINS.items():
        png(paint(spec), here / f'{name}.png')
        print(here / f'{name}.png')
