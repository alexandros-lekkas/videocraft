"""From a finished grid to vanilla commands: few, large `fill`s, then single `setblock`s, then entity summons.

The merge is greedy in layers of popularity: the most common block goes first in the biggest boxes it can make, and a
box may run over cells that a later (less common) block will overwrite. A grass plate with gravel spots becomes a
handful of grass fills and one setblock per spot, instead of a fill per row of grass. Every fill stays within
vanilla's limit of 32768 blocks. Everything is placed `strict` (no block updates; see shapes.py).
"""
from collections import Counter

FILL_LIMIT = 32768
FORCELOAD_LIMIT = 256  # chunks per forceload command


def boxes(cells, limit=FILL_LIMIT):
    """[(x1, y1, z1, x2, y2, z2, state)] in placing order. `cells` maps (x, y, z) to a BlockState."""
    counts = Counter(cells.values())
    order = sorted(counts, key=lambda s: (-counts[s], s.text))
    rank = {s: i for i, s in enumerate(order)}
    crank = {k: rank[s] for k, s in cells.items()}
    by_state = {s: [] for s in order}
    for k, s in cells.items():
        by_state[s].append(k)
    out = []
    for s in order:
        r = rank[s]
        mine = set(by_state[s])
        todo = sorted(mine, key=lambda k: (k[1], k[2], k[0]))

        def ok(x, y, z):
            q = crank.get((x, y, z))
            return q is not None and q >= r

        for (x, y, z) in todo:
            if (x, y, z) not in mine:
                continue
            x2 = x
            while ok(x2 + 1, y, z) and (x2 + 2 - x) <= limit:
                x2 += 1
            z2 = z
            while (x2 - x + 1) * (z2 + 2 - z) <= limit and all(ok(i, y, z2 + 1) for i in range(x, x2 + 1)):
                z2 += 1
            y2 = y
            area = (x2 - x + 1) * (z2 - z + 1)
            while area * (y2 + 2 - y) <= limit and all(ok(i, y2 + 1, k) for i in range(x, x2 + 1) for k in range(z, z2 + 1)):
                y2 += 1
            for i in range(x, x2 + 1):
                for j in range(y, y2 + 1):
                    for k in range(z, z2 + 1):
                        mine.discard((i, j, k))
            out.append((x, y, z, x2, y2, z2, s))
    return out


def block_commands(cells):
    cmds = []
    for x1, y1, z1, x2, y2, z2, s in boxes(cells):
        if (x1, y1, z1) == (x2, y2, z2):
            cmds.append(f'setblock {x1} {y1} {z1} {s.text} strict')
        else:
            cmds.append(f'fill {x1} {y1} {z1} {x2} {y2} {z2} {s.text} strict')
    return cmds


def split_box(lo, hi, limit=FILL_LIMIT, align=1):
    """Splits an inclusive box into boxes of at most `limit` cells: slabs of whole layers where a layer fits, else
    strips. With `align` (4 for biomes), every piece starts and ends on that grid (the box must already be aligned)."""
    (x1, y1, z1), (x2, y2, z2) = lo, hi
    out = []
    dx, dz = x2 - x1 + 1, z2 - z1 + 1
    if dx * dz * align <= limit:
        step = max(align, limit // (dx * dz) // align * align)
        for y in range(y1, y2 + 1, step):
            out.append(((x1, y, z1), (x2, min(y2, y + step - 1), z2)))
        return out
    if dx * align * align <= limit:
        rows = max(align, limit // (dx * align) // align * align)
        for z in range(z1, z2 + 1, rows):
            for y in range(y1, y2 + 1, align):
                out.append(((x1, y, z), (x2, y + align - 1, min(z2, z + rows - 1))))
        return out
    cols = max(align, limit // (align * align) // align * align)
    for x in range(x1, x2 + 1, cols):
        for z in range(z1, z2 + 1, align):
            for y in range(y1, y2 + 1, align):
                out.append(((x, y, z), (min(x2, x + cols - 1), y + align - 1, z + align - 1)))
    return out


def clear_commands(lo, hi):
    """Air over a box. A fill that changes nothing fails, so each box first gets one block in its corner if that corner
    is air (`execute if block … run` is silent when the test does not pass): the fill then always changes something."""
    out = []
    for a, b in split_box(lo, hi):
        out.append(f'execute if block {a[0]} {a[1]} {a[2]} air run setblock {a[0]} {a[1]} {a[2]} barrier strict')
        out.append(f'fill {a[0]} {a[1]} {a[2]} {b[0]} {b[1]} {b[2]} air strict')
    return out


def biome_commands(lo, hi, biome):
    """`fillbiome` works in 4x4x4 biome cells and counts the volume of the cells it touches: align to 4, then split."""
    a = (lo[0] // 4 * 4, lo[1] // 4 * 4, lo[2] // 4 * 4)
    b = (hi[0] // 4 * 4 + 3, hi[1] // 4 * 4 + 3, hi[2] // 4 * 4 + 3)
    out = []
    for p, q in split_box(a, b, FILL_LIMIT, align=4):
        out.append(f'fillbiome {p[0]} {p[1]} {p[2]} {q[0]} {q[1]} {q[2]} {biome}')
    return out


def forceload_commands(lo, hi):
    """`forceload add` over the box's columns, at most 256 chunks per command."""
    cx1, cz1, cx2, cz2 = lo[0] >> 4, lo[2] >> 4, hi[0] >> 4, hi[2] >> 4
    out = []
    for cx in range(cx1, cx2 + 1, 16):
        for cz in range(cz1, cz2 + 1, 16):
            ex, ez = min(cx2, cx + 15), min(cz2, cz + 15)
            out.append(f'forceload add {cx * 16} {cz * 16} {ex * 16 + 15} {ez * 16 + 15}')
    return out


def _num(v):
    return f'{v:.4f}'.rstrip('0').rstrip('.') if isinstance(v, float) else str(v)


def snbt(value):
    """Python data → SNBT: dict → {k:v}, list → [..], float → 1.5f, int → 1, bool → 1b/0b, str → "…"."""
    if isinstance(value, bool):
        return '1b' if value else '0b'
    if isinstance(value, Float):
        return _num(float(value)) + 'f'
    if isinstance(value, float):
        return _num(value) + 'f'
    if isinstance(value, int):
        return str(value)
    if isinstance(value, Raw):
        return str(value)
    if isinstance(value, str):
        return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'
    if isinstance(value, (list, tuple)):
        return '[' + ','.join(snbt(v) for v in value) + ']'
    if isinstance(value, dict):
        return '{' + ','.join(f'{k}:{snbt(v)}' for k, v in value.items()) + '}'
    raise TypeError(f'cannot write {value!r} as SNBT')


class Float(float):
    """A float written as a float even when whole (2.0f)."""


class Raw(str):
    """SNBT written as is (a byte like 3b)."""


def _coord(v):
    """A coordinate for summon: always with a decimal point, because vanilla moves a whole number to the middle of
    its block (`4` is read as 4.5)."""
    t = _num(float(v))
    return t if '.' in t else t + '.0'


def summon_command(entity):
    x, y, z = entity['pos']
    nbt = snbt(entity['nbt']) if entity.get('nbt') else ''
    return f'summon {entity["type"]} {_coord(x)} {_coord(y)} {_coord(z)} {nbt}'.rstrip()
