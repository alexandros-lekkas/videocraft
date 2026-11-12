"""Original 64x64 player skins painted from a small spec, written as PNG with the standard library.

    videocraft sets skin sets/skins/presenter.toml -o presenter.png

A spec (TOML):

    model = "wide"                       # or "slim" (3-pixel arms)
    skin = "#c68e6a"
    seed = 3                             # the slight per-pixel variation
    hair = { style = "short", color = "#3a2a20" }     # short, long, bun, buzz, fringe, bald, ponytail
    eyes = { color = "#3b6fb5" }
    brows = "#2a1d16"                    # default: a little darker than the hair
    mouth = "smile"                      # smile, flat, none
    beard = "#3a2a20"                    # optional; also stubble = "#…"
    glasses = "#202020"                  # optional frames
    top = { color = "#e8e8e8", sleeves = "short", collar = "#c8c8c8", logo = "#…" }   # short, long, none
    jacket = { color = "#2b3440", sleeves = "long", open = true }                   # optional, on the outer layer
    trousers = { color = "#2e3b55", belt = "#3b2a1e" }
    shoes = { color = "#2a2a2a", sole = "#e0e0e0" }

Faces are shaded like the game's own skins (top lighter, sides and back a little darker), so a skin does not read
flat in third person. Layout: the standard 64x64 format (base and outer layer for head, body, arms, legs).
"""
import struct
import tomllib
import zlib
from pathlib import Path

from .noise import rand

KEYS = {'name', 'model', 'skin', 'seed', 'hair', 'eyes', 'brows', 'mouth', 'beard', 'stubble', 'glasses', 'top',
        'jacket', 'trousers', 'shoes', 'description', 'blush'}


class SkinError(ValueError):
    pass


def color(text, where='colour'):
    if isinstance(text, (list, tuple)) and len(text) in (3, 4):
        c = tuple(int(v) for v in text)
        return c if len(c) == 4 else c + (255,)
    t = str(text).strip().lstrip('#')
    if len(t) not in (6, 8) or any(ch not in '0123456789abcdefABCDEF' for ch in t):
        raise SkinError(f'{where}: a colour is "#rrggbb" (got {text!r})')
    v = [int(t[i:i + 2], 16) for i in range(0, len(t), 2)]
    return tuple(v) + ((255,) if len(v) == 3 else ())


def shade(c, k):
    return tuple(max(0, min(255, round(ch * k))) for ch in c[:3]) + (c[3],)


def png(width, height, pixels):
    """pixels: rows of (r, g, b, a). Returns PNG bytes."""
    raw = b''.join(b'\x00' + bytes(v for px in row for v in px) for row in pixels)

    def chunk(tag, data):
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xFFFFFFFF)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def read_png(data):
    """Reads back an 8-bit RGBA PNG written by `png` (for tests): (width, height, rows)."""
    assert data[:8] == b'\x89PNG\r\n\x1a\n'
    pos, idat, w, h = 8, b'', 0, 0
    while pos < len(data):
        n = struct.unpack('>I', data[pos:pos + 4])[0]
        tag = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + n]
        if tag == b'IHDR':
            w, h = struct.unpack('>II', body[:8])
        elif tag == b'IDAT':
            idat += body
        pos += 12 + n
    raw = zlib.decompress(idat)
    rows, stride = [], w * 4 + 1
    for y in range(h):
        line = raw[y * stride + 1:(y + 1) * stride]
        rows.append([tuple(line[i:i + 4]) for i in range(0, len(line), 4)])
    return w, h, rows


# Box layout of the 64x64 format: (u, v) of the box, its width, height and depth in pixels.
def boxes(slim):
    aw = 3 if slim else 4
    return {
        'head': ((0, 0), (8, 8, 8)), 'hat': ((32, 0), (8, 8, 8)),
        'body': ((16, 16), (8, 12, 4)), 'jacket': ((16, 32), (8, 12, 4)),
        'right_arm': ((40, 16), (aw, 12, 4)), 'right_sleeve': ((40, 32), (aw, 12, 4)),
        'left_arm': ((32, 48), (aw, 12, 4)), 'left_sleeve': ((48, 48), (aw, 12, 4)),
        'right_leg': ((0, 16), (4, 12, 4)), 'right_pants': ((0, 32), (4, 12, 4)),
        'left_leg': ((16, 48), (4, 12, 4)), 'left_pants': ((0, 48), (4, 12, 4)),
    }


def faces(uv, size):
    """{face: (x0, y0, w, h)} of a box in the texture."""
    (u, v), (w, h, d) = uv, size
    return {'top': (u + d, v, w, d), 'bottom': (u + d + w, v, w, d), 'right': (u, v + d, d, h),
            'front': (u + d, v + d, w, h), 'left': (u + d + w, v + d, d, h), 'back': (u + d + w + d, v + d, w, h)}


LIGHT = {'top': 1.08, 'front': 1.0, 'right': 0.9, 'left': 0.9, 'back': 0.86, 'bottom': 0.78}
HAIR_STYLES = {'short', 'long', 'bun', 'buzz', 'fringe', 'bald', 'ponytail'}


def paint(spec):
    """A spec (a dict) → 64 rows of 64 RGBA pixels."""
    extra = sorted(set(spec) - KEYS)
    if extra:
        raise SkinError(f'skin: unknown key(s) {", ".join(extra)}; allowed: {", ".join(sorted(KEYS))}')
    slim = spec.get('model', 'wide') == 'slim'
    if spec.get('model', 'wide') not in ('wide', 'slim'):
        raise SkinError('skin: model is "wide" or "slim"')
    seed = int(spec.get('seed', 1))
    skin = color(spec.get('skin', '#c68e6a'), 'skin')
    hair = spec.get('hair', {})
    hair_c = color(hair.get('color', '#3a2a20'), 'hair.color')
    style = hair.get('style', 'short')
    if style not in HAIR_STYLES:
        raise SkinError(f'skin: hair.style is one of {", ".join(sorted(HAIR_STYLES))}')
    top = spec.get('top', {})
    top_c = color(top.get('color', '#e8e8e8'), 'top.color')
    sleeves = top.get('sleeves', 'short')
    trousers = spec.get('trousers', {})
    tr_c = color(trousers.get('color', '#2e3b55'), 'trousers.color')
    shoes = spec.get('shoes', {})
    shoe_c = color(shoes.get('color', '#2a2a2a'), 'shoes.color')
    sole = color(shoes.get('sole', '#d8d8d8'), 'shoes.sole') if shoes.get('sole') else shade(shoe_c, 0.7)
    jacket = spec.get('jacket')
    img = [[(0, 0, 0, 0)] * 64 for _ in range(64)]
    B = boxes(slim)

    def put(x, y, c, face, jitter=0.035):
        k = LIGHT[face] * (1 + (rand(seed, x, y) - 0.5) * 2 * jitter)
        img[y][x] = shade(c, k)

    def fill_box(name, fn):
        for face, (x0, y0, w, h) in faces(*B[name]).items():
            for j in range(h):
                for i in range(w):
                    c = fn(face, i, j, w, h)
                    if c is not None:
                        put(x0 + i, y0 + j, c, face)

    # Head: skin, hair, face.
    eyes = spec.get('eyes', {})
    eye_c = color(eyes.get('color', '#3b6fb5'), 'eyes.color')
    brows = color(spec['brows'], 'brows') if spec.get('brows') else shade(hair_c, 0.8)
    beard = color(spec['beard'], 'beard') if spec.get('beard') else None
    stubble = color(spec['stubble'], 'stubble') if spec.get('stubble') else None
    glasses = color(spec['glasses'], 'glasses') if spec.get('glasses') else None
    mouth = spec.get('mouth', 'smile')
    blush = color(spec['blush'], 'blush') if spec.get('blush') else None
    lip = shade(skin, 0.72)

    def head(face, i, j, w, h):
        bald = style == 'bald'
        if face == 'top':
            return skin if bald else hair_c
        if face == 'bottom':
            return beard if beard else shade(skin, 0.9)
        if face == 'back':
            depth = {'buzz': 3, 'short': 5, 'fringe': 5, 'bun': 6, 'long': 8, 'ponytail': 7, 'bald': 0}[style]
            if j < depth:
                return hair_c
            return beard if beard and j >= 7 else skin
        if face in ('left', 'right'):
            depth = {'buzz': 2, 'short': 3, 'fringe': 3, 'bun': 3, 'long': 7, 'ponytail': 3, 'bald': 0}[style]
            ear = (j in (4, 5) and i in ((5,) if face == 'right' else (2,)))
            front_i = i if face == 'left' else w - 1 - i  # how far from the face's front edge
            if j < depth and not (style == 'long' and front_i < 2 and j > 2):
                return hair_c
            if beard and j >= 5 and front_i < 5:
                return beard
            if stubble and j >= 6 and front_i < 4:
                return stubble
            return shade(skin, 0.93) if ear else skin
        # Front: hairline, brows, eyes, nose shadow, mouth, beard.
        hairline = {'buzz': 1, 'short': 1, 'fringe': 2, 'bun': 1, 'long': 1, 'ponytail': 1, 'bald': 0}[style]
        if j < hairline:
            return hair_c
        if style == 'fringe' and j == 2 and i in (0, 1, 2, 5, 6, 7):
            return hair_c
        if style == 'long' and i in (0, 7) and j < 7:
            return hair_c
        if j == 3 and i in (1, 2, 5, 6):
            return brows
        if j == 4:
            if i in (1, 6):
                return (245, 245, 245, 255)
            if i in (2, 5):
                return eye_c
            if glasses and i in (0, 3, 4, 7):
                return glasses
        if glasses and j == 3 and i in (0, 3, 4, 7):
            return glasses
        if j == 5 and i in (3, 4):
            return shade(skin, 0.88)
        if blush and j == 5 and i in (1, 6):
            return blush
        if beard and (j >= 6 or (j == 5 and i in (0, 7))):
            if j == 6 and i in (3, 4) and mouth != 'none':
                return lip
            return beard
        if stubble and j >= 6:
            return stubble if (i + j) % 2 == 0 else skin
        if j == 6 and mouth == 'smile' and i in (2, 3, 4, 5):
            return lip if i in (3, 4) else shade(skin, 0.85)
        if j == 6 and mouth == 'flat' and i in (3, 4):
            return lip
        return skin

    fill_box('head', head)

    def hat(face, i, j, w, h):
        # The outer layer adds a little volume to longer styles and the bun / ponytail.
        if style == 'bun' and face == 'top' and 2 <= i <= 5 and 4 <= j <= 7:
            return shade(hair_c, 0.92)
        if style == 'ponytail' and face == 'back' and 3 <= i <= 4 and j >= 4:
            return shade(hair_c, 0.95)
        if style == 'long' and face == 'back' and j >= 6:
            return hair_c
        if style in ('short', 'fringe') and face == 'top' and (i + j) % 3 == 0:
            return shade(hair_c, 1.1)
        return None

    fill_box('hat', hat)

    collar = color(top['collar'], 'top.collar') if top.get('collar') else None
    logo = color(top['logo'], 'top.logo') if top.get('logo') else None
    stripe = color(top['stripe'], 'top.stripe') if top.get('stripe') else None
    belt = color(trousers['belt'], 'trousers.belt') if trousers.get('belt') else shade(tr_c, 0.75)

    def body(face, i, j, w, h):
        if face == 'top':
            return collar or top_c
        if face == 'bottom':
            return tr_c
        if j >= 10:
            return belt if j == 10 else tr_c
        if collar and face == 'front' and j == 0 and 2 <= i <= 5:
            return collar if i in (2, 5) else skin
        if logo and face == 'front' and 3 <= j <= 5 and 3 <= i <= 4:
            return logo
        if stripe and j == 6:
            return stripe
        return top_c

    fill_box('body', body)
    sleeve_rows = {'short': 4, 'long': 12, 'none': 0}.get(sleeves, 4)

    def arm(face, i, j, w, h):
        if face == 'top':
            return top_c if sleeve_rows else skin
        if face == 'bottom':
            return skin
        if j < sleeve_rows and not (sleeve_rows == 12 and j >= 11):
            return stripe if (stripe and j == sleeve_rows - 1 and sleeve_rows < 12) else top_c
        return skin

    fill_box('right_arm', arm)
    fill_box('left_arm', arm)

    def leg(face, i, j, w, h):
        if face == 'top':
            return tr_c
        if face == 'bottom':
            return sole
        if j >= 10:
            return sole if j == 11 and face != 'top' else shoe_c
        return shade(tr_c, 0.94) if (face == 'front' and i == w - 1 and j < 9) else tr_c

    fill_box('right_leg', leg)
    fill_box('left_leg', leg)

    if jacket:
        jc = color(jacket.get('color', '#2b3440'), 'jacket.color')
        open_ = jacket.get('open', True)
        js = {'short': 4, 'long': 12, 'none': 0}.get(jacket.get('sleeves', 'long'), 12)

        def jbody(face, i, j, w, h):
            if face in ('top', 'bottom'):
                return jc if face == 'top' else None
            if j >= 10:
                return None
            if face == 'front' and open_ and 3 <= i <= 4:
                return None  # the shirt shows between the open fronts
            if face == 'front' and open_ and j <= 2 and i in (2, 5):
                return shade(jc, 0.8)  # lapels
            return jc

        def jarm(face, i, j, w, h):
            if face == 'bottom':
                return None
            if face == 'top':
                return jc
            return jc if j < js else None

        fill_box('jacket', jbody)
        fill_box('right_sleeve', jarm)
        fill_box('left_sleeve', jarm)
    return img


def load_spec(path):
    p = Path(path)
    try:
        return tomllib.loads(p.read_text(encoding='utf-8'))
    except tomllib.TOMLDecodeError as e:
        raise SkinError(f'{p}: {e}') from e


def write(spec, out):
    img = paint(spec)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_bytes(png(64, 64, img))
    return Path(out)
