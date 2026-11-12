"""Just enough imaging for review packets, standard library only: an RGB canvas, a 5x7 bitmap font for labels
(ffmpeg here has no drawtext), frames pasted in from ffmpeg's raw output, and a PNG writer (zlib + struct)."""
import struct
import zlib

# 5x7 glyphs, one string of 7 rows per character, '#' is ink. Lowercase is drawn as uppercase.
_GLYPHS = {
    ' ': '.....|.....|.....|.....|.....|.....|.....',
    'A': '.###.|#...#|#...#|#####|#...#|#...#|#...#', 'B': '####.|#...#|#...#|####.|#...#|#...#|####.',
    'C': '.###.|#...#|#....|#....|#....|#...#|.###.', 'D': '####.|#...#|#...#|#...#|#...#|#...#|####.',
    'E': '#####|#....|#....|####.|#....|#....|#####', 'F': '#####|#....|#....|####.|#....|#....|#....',
    'G': '.###.|#...#|#....|#.###|#...#|#...#|.####', 'H': '#...#|#...#|#...#|#####|#...#|#...#|#...#',
    'I': '.###.|..#..|..#..|..#..|..#..|..#..|.###.', 'J': '..###|...#.|...#.|...#.|...#.|#..#.|.##..',
    'K': '#...#|#..#.|#.#..|##...|#.#..|#..#.|#...#', 'L': '#....|#....|#....|#....|#....|#....|#####',
    'M': '#...#|##.##|#.#.#|#.#.#|#...#|#...#|#...#', 'N': '#...#|#...#|##..#|#.#.#|#..##|#...#|#...#',
    'O': '.###.|#...#|#...#|#...#|#...#|#...#|.###.', 'P': '####.|#...#|#...#|####.|#....|#....|#....',
    'Q': '.###.|#...#|#...#|#...#|#.#.#|#..#.|.##.#', 'R': '####.|#...#|#...#|####.|#.#..|#..#.|#...#',
    'S': '.####|#....|#....|.###.|....#|....#|####.', 'T': '#####|..#..|..#..|..#..|..#..|..#..|..#..',
    'U': '#...#|#...#|#...#|#...#|#...#|#...#|.###.', 'V': '#...#|#...#|#...#|#...#|#...#|.#.#.|..#..',
    'W': '#...#|#...#|#...#|#.#.#|#.#.#|#.#.#|.#.#.', 'X': '#...#|#...#|.#.#.|..#..|.#.#.|#...#|#...#',
    'Y': '#...#|#...#|.#.#.|..#..|..#..|..#..|..#..', 'Z': '#####|....#|...#.|..#..|.#...|#....|#####',
    '0': '.###.|#...#|#..##|#.#.#|##..#|#...#|.###.', '1': '..#..|.##..|..#..|..#..|..#..|..#..|.###.',
    '2': '.###.|#...#|....#|...#.|..#..|.#...|#####', '3': '#####|...#.|..#..|...#.|....#|#...#|.###.',
    '4': '...#.|..##.|.#.#.|#..#.|#####|...#.|...#.', '5': '#####|#....|####.|....#|....#|#...#|.###.',
    '6': '..##.|.#...|#....|####.|#...#|#...#|.###.', '7': '#####|....#|...#.|..#..|.#...|.#...|.#...',
    '8': '.###.|#...#|#...#|.###.|#...#|#...#|.###.', '9': '.###.|#...#|#...#|.####|....#|...#.|.##..',
    '.': '.....|.....|.....|.....|.....|.##..|.##..', ',': '.....|.....|.....|.....|.##..|..#..|.#...',
    ':': '.....|.##..|.##..|.....|.##..|.##..|.....', ';': '.....|.##..|.##..|.....|.##..|..#..|.#...',
    '-': '.....|.....|.....|#####|.....|.....|.....', '_': '.....|.....|.....|.....|.....|.....|#####',
    '+': '.....|..#..|..#..|#####|..#..|..#..|.....', '=': '.....|.....|#####|.....|#####|.....|.....',
    '/': '....#|....#|...#.|..#..|.#...|#....|#....', '(': '...#.|..#..|.#...|.#...|.#...|..#..|...#.',
    ')': '.#...|..#..|...#.|...#.|...#.|..#..|.#...', '#': '.#.#.|.#.#.|#####|.#.#.|#####|.#.#.|.#.#.',
    '%': '##..#|##..#|...#.|..#..|.#...|#..##|#..##', "'": '..#..|..#..|.#...|.....|.....|.....|.....',
    '"': '.#.#.|.#.#.|.#.#.|.....|.....|.....|.....', '!': '..#..|..#..|..#..|..#..|..#..|.....|..#..',
    '?': '.###.|#...#|....#|...#.|..#..|.....|..#..', '*': '.....|..#..|#.#.#|.###.|#.#.#|..#..|.....',
    '<': '...#.|..#..|.#...|#....|.#...|..#..|...#.', '>': '.#...|..#..|...#.|....#|...#.|..#..|.#...',
    '[': '.###.|.#...|.#...|.#...|.#...|.#...|.###.', ']': '.###.|...#.|...#.|...#.|...#.|...#.|.###.',
    '|': '..#..|..#..|..#..|..#..|..#..|..#..|..#..', 'x': '.....|.....|#...#|.#.#.|..#..|.#.#.|#...#',
}
FONT = {c: [[ch == '#' for ch in row] for row in g.split('|')] for c, g in _GLYPHS.items()}
GLYPH_W, GLYPH_H = 5, 7


class Canvas:
    def __init__(self, width, height, color=(0, 0, 0)):
        self.w, self.h = width, height
        self.px = bytearray(bytes(color) * (width * height))

    def fill(self, x, y, w, h, color):
        x0, y0, x1, y1 = max(0, x), max(0, y), min(self.w, x + w), min(self.h, y + h)
        if x1 <= x0 or y1 <= y0:
            return
        row = bytes(color) * (x1 - x0)
        for yy in range(y0, y1):
            i = (yy * self.w + x0) * 3
            self.px[i:i + len(row)] = row

    def paste(self, rgb, w, h, x, y):
        """Pastes a raw RGB24 image of w x h at (x, y), clipped to the canvas."""
        x0, x1 = max(0, x), min(self.w, x + w)
        if x1 <= x0:
            return
        for yy in range(max(0, y), min(self.h, y + h)):
            src = ((yy - y) * w + (x0 - x)) * 3
            dst = (yy * self.w + x0) * 3
            self.px[dst:dst + (x1 - x0) * 3] = rgb[src:src + (x1 - x0) * 3]

    def text(self, x, y, s, scale=2, color=(255, 255, 255)):
        """Draws s with the bitmap font; returns the width drawn. Unknown characters are drawn as '?'."""
        cx = x
        for ch in s:
            glyph = FONT.get(ch) or FONT.get(ch.upper()) or FONT['?']
            for gy, row in enumerate(glyph):
                for gx, ink in enumerate(row):
                    if ink:
                        self.fill(cx + gx * scale, y + gy * scale, scale, scale, color)
            cx += (GLYPH_W + 1) * scale
        return cx - x

    def save(self, path, quality=2):
        """JPEG through ffmpeg when the path ends in .jpg (a tenth of the PNG's size, labels still crisp at q 2), else PNG."""
        if str(path).endswith('.jpg'):
            import subprocess
            from videocraft import tools
            if tools.ffmpeg():
                subprocess.run([tools.ffmpeg(), '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{self.w}x{self.h}', '-i', '-',
                                '-q:v', str(quality), '-pix_fmt', 'yuvj444p', str(path)], input=bytes(self.px), check=True)
                return path
            path = str(path)[:-4] + '.png'
        self.png(path)
        return path

    def png(self, path):
        raw = b''.join(b'\x00' + bytes(self.px[r * self.w * 3:(r + 1) * self.w * 3]) for r in range(self.h))
        chunk = lambda tag, data: struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)
        with open(path, 'wb') as f:
            f.write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', self.w, self.h, 8, 2, 0, 0, 0))
                    + chunk(b'IDAT', zlib.compress(raw, 6)) + chunk(b'IEND', b''))


def text_width(s, scale=2):
    return len(s) * (GLYPH_W + 1) * scale

