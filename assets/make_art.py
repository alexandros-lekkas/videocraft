#!/usr/bin/env python3
"""Draws the repo's block-style images from code: python3 assets/make_art.py

Writes assets/banner.svg (README banner) and assets/social-preview.svg (GitHub social preview, 1280x640). Both reuse
assets/icon.svg (a pixel grass block with a play mark) and spell the name in a 5x7 pixel font drawn as rects, so no
font file is embedded and nothing comes from the game. Standard library only; the output is deterministic.
On macOS with Xcode's command line tools it also renders banner.png and social-preview.png through assets/render.swift
(GitHub's social preview setting takes a PNG).
"""
import random
import shutil
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent

BG = '#17181d'
INK = '#f2f2ee'
INK_SHADOW = '#2f5a26'
ACCENT = '#79cc5f'
MUTED = '#9aa0a8'
GRASS = ['#79cc5f', '#6cc054', '#5fb04a', '#57a343', '#4f963d']
DIRT = ['#845c3c', '#775033', '#724b31', '#68452b', '#5d3d25', '#4f4f4f']

# 5x7 glyphs, rows top to bottom, '#' = on.
FONT = {
    'A': ['.###.', '#...#', '#...#', '#####', '#...#', '#...#', '#...#'],
    'B': ['####.', '#...#', '#...#', '####.', '#...#', '#...#', '####.'],
    'C': ['.###.', '#...#', '#....', '#....', '#....', '#...#', '.###.'],
    'D': ['####.', '#...#', '#...#', '#...#', '#...#', '#...#', '####.'],
    'E': ['#####', '#....', '#....', '####.', '#....', '#....', '#####'],
    'F': ['#####', '#....', '#....', '####.', '#....', '#....', '#....'],
    'G': ['.###.', '#...#', '#....', '#.###', '#...#', '#...#', '.####'],
    'H': ['#...#', '#...#', '#...#', '#####', '#...#', '#...#', '#...#'],
    'I': ['#####', '..#..', '..#..', '..#..', '..#..', '..#..', '#####'],
    'J': ['..###', '...#.', '...#.', '...#.', '#..#.', '#..#.', '.##..'],
    'K': ['#...#', '#..#.', '#.#..', '##...', '#.#..', '#..#.', '#...#'],
    'L': ['#....', '#....', '#....', '#....', '#....', '#....', '#####'],
    'M': ['#...#', '##.##', '#.#.#', '#.#.#', '#...#', '#...#', '#...#'],
    'N': ['#...#', '##..#', '#.#.#', '#..##', '#...#', '#...#', '#...#'],
    'O': ['.###.', '#...#', '#...#', '#...#', '#...#', '#...#', '.###.'],
    'P': ['####.', '#...#', '#...#', '####.', '#....', '#....', '#....'],
    'Q': ['.###.', '#...#', '#...#', '#...#', '#.#.#', '#..#.', '.##.#'],
    'R': ['####.', '#...#', '#...#', '####.', '#.#..', '#..#.', '#...#'],
    'S': ['.####', '#....', '#....', '.###.', '....#', '....#', '####.'],
    'T': ['#####', '..#..', '..#..', '..#..', '..#..', '..#..', '..#..'],
    'U': ['#...#', '#...#', '#...#', '#...#', '#...#', '#...#', '.###.'],
    'V': ['#...#', '#...#', '#...#', '#...#', '#...#', '.#.#.', '..#..'],
    'W': ['#...#', '#...#', '#...#', '#.#.#', '#.#.#', '#.#.#', '.#.#.'],
    'X': ['#...#', '#...#', '.#.#.', '..#..', '.#.#.', '#...#', '#...#'],
    'Y': ['#...#', '#...#', '.#.#.', '..#..', '..#..', '..#..', '..#..'],
    'Z': ['#####', '....#', '...#.', '..#..', '.#...', '#....', '#####'],
    '-': ['.....', '.....', '.....', '.###.', '.....', '.....', '.....'],
    '.': ['.....', '.....', '.....', '.....', '.....', '.##..', '.##..'],
    ',': ['.....', '.....', '.....', '.....', '.##..', '..#..', '.#...'],
    '>': ['.#...', '..#..', '...#.', '....#', '...#.', '..#..', '.#...'],
    ' ': ['.....'] * 7,
}


def glyph_rows(ch, bold):
    """A glyph's rows; bold doubles every vertical stroke (each pixel also lights its right neighbour)."""
    rows = FONT[ch]
    if not bold:
        return rows
    return [''.join('#' if line[i] == '#' or (i > 0 and line[i - 1] == '#') else '.' for i in range(5))
            + ('#' if line[4] == '#' else '.') for line in rows]


def text_width(text, px, gap=1, bold=False):
    return (len(text) * (5 + bold + gap) - gap) * px


def pixel_text(text, x, y, px, fill, shadow=None, gap=1, bold=False):
    """The text as rects (one per horizontal run of pixels), with an optional one-pixel drop shadow."""
    out = []
    width = 5 + bold
    layers = ([(shadow, px)] if shadow else []) + [(fill, 0)]
    for color, off in layers:
        rects = []
        for i, ch in enumerate(text.upper()):
            gx = x + i * (width + gap) * px
            for row, line in enumerate(glyph_rows(ch, bold)):
                col = 0
                while col < width:
                    if line[col] == '#':
                        start = col
                        while col < width and line[col] == '#':
                            col += 1
                        rects.append(f'<rect x="{gx + start * px + off}" y="{y + row * px + off}" '
                                     f'width="{(col - start) * px}" height="{px}"/>')
                    else:
                        col += 1
        out.append(f'<g fill="{color}">' + ''.join(rects) + '</g>')
    return '\n'.join(out)


def icon(x, y, size, background=False):
    """assets/icon.svg as a nested image at (x, y), size x size; without its rounded backing unless asked."""
    lines = (HERE / 'icon.svg').read_text().splitlines()
    body = [l for l in lines[1:-1] if background or not l.startswith('<rect width="64"')]
    return (f'<svg x="{x}" y="{y}" width="{size}" height="{size}" viewBox="0 0 64 64" shape-rendering="crispEdges">\n'
            + '\n'.join(body) + '\n</svg>')


def ground(width, top, px, seed):
    """A strip of grass over dirt, one block-pixel per px, to the bottom edge: two grass rows, then dirt."""
    rng = random.Random(seed)
    cols = -(-width // px)
    rects = []
    for c in range(cols):
        grass_rows = 2 + (1 if rng.random() < 0.35 else 0)
        for r in range(6):
            color = rng.choice(GRASS) if r < grass_rows else rng.choice(DIRT)
            rects.append(f'<rect x="{c * px}" y="{top + r * px}" width="{px}" height="{px}" fill="{color}"/>')
    return '<g shape-rendering="crispEdges">' + ''.join(rects) + '</g>'


def svg(width, height, body, title):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
            f'shape-rendering="crispEdges" role="img" aria-label="{title}">\n<title>{title}</title>\n'
            f'<rect width="{width}" height="{height}" fill="{BG}"/>\n{body}\n</svg>\n')


def social_preview():
    w, h = 1280, 640
    title_px = 10
    tag_px = 5
    icon_size = 330
    tw = text_width('VIDEOCRAFT', title_px, bold=True)
    block_w = icon_size + 48 + tw
    x0 = (w - block_w) // 2
    title_x = x0 + icon_size + 48
    top = 104
    body = [
        icon(x0, top, icon_size),
        pixel_text('VIDEOCRAFT', title_x, top + 70, title_px, INK, INK_SHADOW, bold=True),
        f'<rect x="{title_x}" y="{top + 70 + 7 * title_px + 24}" width="{tw}" height="{tag_px}" fill="{ACCENT}"/>',
        pixel_text('AGENT-DIRECTED VIDEO,', title_x, top + 70 + 7 * title_px + 52, tag_px, MUTED),
        pixel_text('FILMED INSIDE MINECRAFT', title_x, top + 70 + 7 * title_px + 52 + 10 * tag_px, tag_px, MUTED),
        ground(w, h - 6 * 16, 16, seed=26),
    ]
    return svg(w, h, '\n'.join(body), 'videocraft: agent-directed video, filmed inside Minecraft')


def banner():
    w, h = 1280, 320
    title_px = 9
    tag_px = 3
    icon_size = 184
    tw = text_width('VIDEOCRAFT', title_px, bold=True)
    block_w = icon_size + 40 + tw
    x0 = (w - block_w) // 2
    title_x = x0 + icon_size + 40
    top = 52
    body = [
        icon(x0, top, icon_size),
        pixel_text('VIDEOCRAFT', title_x, top + 34, title_px, INK, INK_SHADOW, bold=True),
        f'<rect x="{title_x}" y="{top + 34 + 7 * title_px + 18}" width="{tw}" height="{tag_px}" fill="{ACCENT}"/>',
        pixel_text('SHOT SCRIPT IN > FILMED VIDEO OUT', title_x, top + 34 + 7 * title_px + 36, tag_px, MUTED),
        ground(w, h - 6 * 8, 8, seed=263),
    ]
    return svg(w, h, '\n'.join(body), 'videocraft: shot script in, filmed video out')


if __name__ == '__main__':
    (HERE / 'social-preview.svg').write_text(social_preview())
    (HERE / 'banner.svg').write_text(banner())
    print('wrote', HERE / 'social-preview.svg', 'and', HERE / 'banner.svg')
    if shutil.which('swiftc'):
        with tempfile.TemporaryDirectory() as tmp:
            render = Path(tmp) / 'render'
            subprocess.run(['swiftc', '-O', str(HERE / 'render.swift'), '-o', str(render)], check=True)
            for name, w, h in (('social-preview', 1280, 640), ('banner', 1280, 320)):
                subprocess.run([str(render), str(HERE / f'{name}.svg'), str(HERE / f'{name}.png'), str(w), str(h)], check=True)
    else:
        print('no swiftc: PNGs not rendered')
