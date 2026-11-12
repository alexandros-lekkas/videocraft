"""The building vocabulary: each `[[build]]` entry of a set file is one of these, run in file order (later wins).

Every op reads its keys through `Op`, so a typo or a missing key fails naming the set, the entry and what is allowed.
Oriented things (stalls, carts, wells, posters) are built facing south and turned to their `facing`.
"""
import math

from . import noise
from .model import AIR, BlockState, Grid, HORIZONTAL, turn_dir

FACING_QUARTERS = {'south': 0, 'west': 1, 'north': 2, 'east': 3}
YAW = {'south': 0.0, 'west': 90.0, 'north': 180.0, 'east': -90.0}
STEP = {'north': (0, -1), 'east': (1, 0), 'south': (0, 1), 'west': (-1, 0)}
PLANTS = ('short_grass', 'fern', 'dandelion', 'poppy', 'blue_orchid', 'allium', 'azure_bluet', 'red_tulip', 'orange_tulip',
          'white_tulip', 'pink_tulip', 'oxeye_daisy', 'cornflower', 'lily_of_the_valley', 'tall_grass', 'large_fern',
          'sunflower', 'lilac', 'rose_bush', 'peony', 'pink_petals', 'wildflowers', 'leaf_litter', 'bush', 'firefly_bush')


class SetError(ValueError):
    """A problem in a set file, phrased so an agent can fix it."""


class Op:
    """One build entry: its keys, checked. Positions may be given along a lane (see `Builder.along`)."""
    current = None  # the builder running the entry (set by Builder.run)

    def __init__(self, spec, where, allowed):
        self.spec, self.where = spec, where
        self.b = Op.current
        extra = sorted(set(spec) - set(allowed) - {'do', 'note'})
        if extra:
            raise SetError(f'{where}: unknown key(s) {", ".join(extra)}; allowed: {", ".join(sorted(allowed))}')

    def has(self, k):
        return k in self.spec

    def get(self, k, default=None):
        return self.spec.get(k, default)

    def req(self, k):
        if k not in self.spec:
            raise SetError(f'{self.where}: missing `{k}`')
        return self.spec[k]

    def num(self, k, default=None):
        v = self.spec.get(k, default)
        if v is None:
            raise SetError(f'{self.where}: missing `{k}` (a number)')
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise SetError(f'{self.where}: `{k}` is a number (got {v!r})')
        return v

    def xz(self, k, default=None):
        v = self.spec.get(k, default)
        if isinstance(v, dict) and 'along' in v and self.b is not None:
            x, z = self.b.along(v, self.where)
            return math.floor(x), math.floor(z)
        if not (isinstance(v, (list, tuple)) and len(v) in (2, 3)):
            raise SetError(f'{self.where}: `{k}` is [x, z] (got {v!r})')
        return (v[0], v[-1]) if len(v) == 2 else (v[0], v[2])

    def xyz(self, k, default=None):
        v = self.spec.get(k, default)
        if not (isinstance(v, (list, tuple)) and len(v) == 3):
            raise SetError(f'{self.where}: `{k}` is [x, y, z] (got {v!r})')
        return tuple(v)

    def facing(self, k='facing', default='south', at='at'):
        v = self.spec.get(k, default)
        if v in ('lane', 'away') and self.b is not None:
            # Toward (or away from) the nearest lane centre line, to the nearest of the four directions.
            x, z = self.xz(at)
            d = self.b.toward_lane(x + 0.5, z + 0.5, self.where)
            return turn_dir(d, 2) if v == 'away' else d
        if v not in FACING_QUARTERS:
            raise SetError(f'{self.where}: `{k}` is north, east, south, west, lane or away (got {v!r})')
        return v

    def points(self, k):
        v = self.req(k)
        if not isinstance(v, list) or not v:
            raise SetError(f'{self.where}: `{k}` is a list of positions')
        return [self._point(p, k) for p in v]

    def _point(self, p, k):
        if isinstance(p, dict) and 'along' in p and self.b is not None:
            x, z = self.b.along(p, self.where)
            return (math.floor(x), int(p['y']), math.floor(z)) if 'y' in p else (math.floor(x), math.floor(z))
        if isinstance(p, (list, tuple)) and len(p) in (2, 3) and all(isinstance(c, (int, float)) for c in p):
            return tuple(p)
        raise SetError(f'{self.where}: `{k}` holds [x, z] or [x, y, z] positions (got {p!r})')


class Builder:
    """Builds one set (or one part) into a grid, a list of entities and a table of marks, in set coordinates."""

    def __init__(self, name, seed, parts=None, where=None):
        self.name = name
        self.seed = int(seed)
        self.grid = Grid()
        self.entities = []   # {'type', 'pos', 'yaw', 'nbt'} or block displays with 'box'
        self.marks = {}
        self.spines = {}     # lane name -> [(x, z, distance along)]
        self.parts = parts if parts is not None else {}
        self.where = where or name
        self.n = 0

    # ---- helpers ----

    def mix(self, spec, grain=0.0, tag=''):
        try:
            return noise.Mix(spec, self.seed ^ noise.salt(f'{self.n}:{tag}'), grain)
        except ValueError as e:
            raise SetError(f'{self.where}: {e}') from e

    def state(self, text):
        try:
            return BlockState.parse(text)
        except ValueError as e:
            raise SetError(f'{self.where}: {e}') from e

    def put(self, x, y, z, block, keep=False):
        if keep and self.grid.has(x, y, z):
            return
        self.grid.set(x, y, z, block if isinstance(block, BlockState) else self.state(block))

    def rand(self, *c):
        return noise.rand(self.seed ^ noise.salt(self.n), *c)

    def add_mark(self, name, mark):
        if name in self.marks:
            raise SetError(f'{self.where}: the mark "{name}" is defined twice')
        self.marks[name] = mark

    def entity(self, type_, pos, nbt=None, yaw=None):
        self.entities.append({'type': type_, 'pos': tuple(float(c) for c in pos), 'yaw': yaw, 'nbt': dict(nbt or {})})

    def display_box(self, block, lo, hi, nbt=None):
        """A block_display filling the box lo..hi (continuous coordinates), axis-aligned."""
        self.entities.append({'type': 'minecraft:block_display', 'box': (tuple(lo), tuple(hi)), 'block': self.state(block), 'nbt': dict(nbt or {})})

    def run(self, builds, base_where):
        for i, spec in enumerate(builds or []):
            self.n = i
            where = f'{base_where}[{i}]'
            if not isinstance(spec, dict) or 'do' not in spec:
                raise SetError(f'{where}: a build entry is a table with `do` (one of {", ".join(sorted(OPS))})')
            fn = OPS.get(spec['do'])
            if fn is None:
                raise SetError(f'{where}: unknown build `do = "{spec["do"]}"`; known: {", ".join(sorted(OPS))}')
            self.where = f'{where} ({spec["do"]})'
            saved, Op.current = Op.current, self
            try:
                fn(self, spec)
            except SetError:
                raise
            except (TypeError, ValueError, KeyError, IndexError, AttributeError) as e:
                raise SetError(f'{self.where}: {type(e).__name__}: {e} (check the keys and value types of this entry)') from e
            finally:
                Op.current = saved

    # ---- positions along a lane ----

    def along(self, v, where):
        """`{ along = "lane", d = 40, side = 8 }`: `d` blocks along the lane mark's centre line from its first point,
        `side` blocks to the right of the direction of travel (negative: left). Returns a continuous (x, z)."""
        lane = v.get('along')
        if lane not in self.spines:
            raise SetError(f'{where}: along = "{lane}" is not a lane with a mark (yet); lanes: {", ".join(sorted(self.spines)) or "none"}')
        x, z, tx, tz = spine_at(self.spines[lane], float(v.get('d', 0)))
        side = float(v.get('side', 0))
        return x - tz * side, z + tx * side

    def spine(self, lane, where):
        if lane not in self.spines:
            raise SetError(f'{where}: along = "{lane}" is not a lane with a mark (yet); lanes: {", ".join(sorted(self.spines)) or "none"}')
        return self.spines[lane]

    def toward_lane(self, x, z, where):
        if not self.spines:
            raise SetError(f'{where}: facing = "lane" needs a lane with a mark before this entry')
        best = None
        for spine in self.spines.values():
            for sx, sz, _ in spine:
                d = (sx - x) ** 2 + (sz - z) ** 2
                if best is None or d < best[0]:
                    best = (d, sx - x, sz - z)
        _, dx, dz = best
        if abs(dx) >= abs(dz):
            return 'east' if dx > 0 else 'west'
        return 'south' if dz > 0 else 'north'

    # ---- areas ----

    def area(self, op):
        """Columns of an area: `from`/`to` (a rectangle, inclusive) or `center`/`radius` (a disc)."""
        if op.has('center'):
            cx, cz = op.xz('center')
            r = op.num('radius')
            out = []
            for x in range(math.floor(cx - r), math.ceil(cx + r) + 1):
                for z in range(math.floor(cz - r), math.ceil(cz + r) + 1):
                    if (x - cx) ** 2 + (z - cz) ** 2 <= r * r + 0.25:
                        out.append((x, z))
            return out
        (x1, z1), (x2, z2) = op.xz('from'), op.xz('to')
        return [(x, z) for x in range(min(x1, x2), max(x1, x2) + 1) for z in range(min(z1, z2), max(z1, z2) + 1)]

    def top(self, x, z, start=60, stop=-40):
        """The y of the highest solid block in a column (or None)."""
        for y in range(start, stop, -1):
            s = self.grid.get(x, y, z)
            if s is not None and s.id != 'air' and s.id not in PLANTS and s.id != 'light':
                return y
        return None


# ---------------------------------------------------------------- ground and paths


def op_ground(b, spec):
    """A plate of ground: top at `y` (default -1), `depth` layers (2), top `mix` with `grain`, `under` below."""
    op = Op(spec, b.where, {'from', 'to', 'center', 'radius', 'y', 'depth', 'mix', 'grain', 'under'})
    top = int(op.get('y', -1))
    depth = int(op.get('depth', 2))
    mix = b.mix(op.get('mix', 'grass_block'), op.get('grain', 3), 'top')
    under = b.state(op.get('under', 'dirt'))
    for x, z in b.area(op):
        b.put(x, top, z, mix.pick(x, z))
        for y in range(top - depth + 1, top):
            b.put(x, y, z, under)


def op_paint(b, spec):
    """Repaints the top layer (`y`, default -1) in an area with a mix; `only` limits it to some blocks."""
    op = Op(spec, b.where, {'from', 'to', 'center', 'radius', 'y', 'mix', 'grain', 'only', 'chance', 'along', 'd', 'width'})
    y = int(op.get('y', -1))
    mix = b.mix(op.req('mix'), op.get('grain', 2), 'paint')
    only = {BlockState.parse(o).name for o in op.get('only', [])}
    chance = float(op.get('chance', 1.0))
    if op.has('along'):
        # A stretch of a lane: `d = [from, to]` blocks along it, `width` across (default 9).
        d1, d2 = op.req('d')
        cells = [c for c, (_dist, a, _s) in ribbon(b.spine(op.get('along'), b.where), float(op.get('width', 9)) / 2).items()
                 if d1 <= a <= d2]
    else:
        cells = b.area(op)
    for x, z in cells:
        s = b.grid.get(x, y, z)
        if s is None or (only and s.name not in only):
            continue
        if chance < 1 and b.rand(x, z, 3) >= chance:
            continue
        b.put(x, y, z, mix.pick(x, z))


def smooth(points, step=0.25):
    """Catmull-Rom through 2D points, sampled about every `step` blocks: [(x, z, distance along)]."""
    pts = [(float(p[0]), float(p[-1])) for p in points]
    if len(pts) == 1:
        return [(pts[0][0], pts[0][1], 0.0)]
    ext = [pts[0]] + pts + [pts[-1]]
    out, dist = [], 0.0
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        seg = math.dist(p1, p2)
        n = max(2, int(seg / step))
        for k in range(n):
            t = k / n
            t2, t3 = t * t, t * t * t
            x = 0.5 * (2 * p1[0] + (-p0[0] + p2[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            z = 0.5 * (2 * p1[1] + (-p0[1] + p2[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            if out:
                dist += math.dist((out[-1][0], out[-1][1]), (x, z))
            out.append((x, z, dist))
    last = pts[-1]
    dist += math.dist((out[-1][0], out[-1][1]), last)
    out.append((last[0], last[1], dist))
    return out


def spine_at(spine, d):
    """The point and unit direction `d` blocks along a sampled spine (clamped to its ends)."""
    d = max(0.0, min(d, spine[-1][2]))
    for i in range(1, len(spine)):
        if spine[i][2] >= d or i == len(spine) - 1:
            a, c = spine[i - 1], spine[i]
            seg = (c[2] - a[2]) or 1e-9
            t = max(0.0, min(1.0, (d - a[2]) / seg))
            tx, tz = c[0] - a[0], c[1] - a[1]
            n = math.hypot(tx, tz) or 1.0
            return a[0] + (c[0] - a[0]) * t, a[1] + (c[1] - a[1]) * t, tx / n, tz / n
    return spine[0][0], spine[0][1], 1.0, 0.0


def straight(points, step=0.25):
    pts = [(float(p[0]), float(p[-1])) for p in points]
    out, dist = [], 0.0
    for a, c in zip(pts, pts[1:]):
        seg = math.dist(a, c)
        n = max(1, int(seg / step))
        for k in range(n):
            t = k / n
            x, z = a[0] + (c[0] - a[0]) * t, a[1] + (c[1] - a[1]) * t
            if out:
                dist += math.dist((out[-1][0], out[-1][1]), (x, z))
            out.append((x, z, dist))
    dist += math.dist((out[-1][0], out[-1][1]), pts[-1]) if out else 0
    out.append((pts[-1][0], pts[-1][1], dist))
    return out


def ribbon(spine, half):
    """Cells within `half` blocks of a spine: {(x, z): (distance from the spine, distance along, side sign)}."""
    cells = {}
    r = math.ceil(half + 1)
    for i, (sx, sz, along) in enumerate(spine):
        for x in range(math.floor(sx - r), math.floor(sx + r) + 1):
            for z in range(math.floor(sz - r), math.floor(sz + r) + 1):
                d = math.hypot(x + 0.5 - sx, z + 0.5 - sz)
                if d <= half and (cells.get((x, z)) is None or d < cells[(x, z)][0]):
                    j = min(i + 1, len(spine) - 1)
                    tx, tz = spine[j][0] - spine[max(0, j - 1)][0], spine[j][1] - spine[max(0, j - 1)][1]
                    side = 1 if (tx * (z + 0.5 - sz) - tz * (x + 0.5 - sx)) > 0 else -1
                    cells[(x, z)] = (d, along, side)
    return cells


def op_lane(b, spec):
    """A path painted into the ground along a smooth curve through `points`, `width` wide, with a `center` line.

    `center = { block = "smooth_stone", width = 1, dash = [3, 1] }`, `edge = { mix = …, width = 1, chance = 0.6 }`
    (a ragged border into the grass). `mark = "lane"` exports the centre line (feet level) as a path mark."""
    op = Op(spec, b.where, {'points', 'width', 'mix', 'grain', 'center', 'edge', 'y', 'smooth', 'mark', 'clear'})
    pts = op.points('points')
    spine = smooth(pts) if op.get('smooth', True) else straight(pts)
    width = float(op.get('width', 5))
    y = int(op.get('y', -1))
    mix = b.mix(op.get('mix', 'cobblestone'), op.get('grain', 2), 'lane')
    center = op.get('center')
    edge = op.get('edge')
    ew = float(edge.get('width', 1)) if edge else 0
    cells = ribbon(spine, width / 2 + ew)
    cmix = None
    if center:
        cw = float(center.get('width', 1)) / 2
        cmix = b.mix(center.get('block', 'smooth_stone'), 0, 'center')
        dash = center.get('dash')
    emix = b.mix(edge['mix'], edge.get('grain', 0), 'edge') if edge else None
    clear = int(op.get('clear', 2))
    for (x, z), (d, along, _side) in cells.items():
        if d > width / 2:
            if b.rand(x, z, 11) < float(edge.get('chance', 0.6)) * (1 - (d - width / 2) / max(ew, 0.01)) + 0.2:
                b.put(x, y, z, emix.pick(x, z))
            else:
                continue
        elif center and d <= max(cw, 0.5) and (not dash or (along % (dash[0] + dash[1])) < dash[0]):
            b.put(x, y, z, cmix.pick(x, z))
        else:
            b.put(x, y, z, mix.pick(x, z))
        for k in range(clear):
            s = b.grid.get(x, y + 1 + k, z)
            if s is not None and (s.id in PLANTS or s.id.endswith(('_sapling',))):
                b.grid.remove(x, y + 1 + k, z)
    name = op.get('mark')
    if name:
        b.spines[name] = spine
        b.add_mark(name, {'kind': 'path', 'points': [(sx, y + 1, sz) for sx, sz, _ in spine[::4]] + [(spine[-1][0], y + 1, spine[-1][1])]})


def op_crossing(b, spec):
    """A zebra crossing painted across a lane: at `d` blocks along `along` (the lane mark), stripes of `block`
    (white_concrete) running the way the lane goes, `stripe` wide (1) with `gap` (1) between them, across `width`
    (9, the road) and `depth` blocks along it (3); `y` is the layer (-1)."""
    op = Op(spec, b.where, {'along', 'd', 'width', 'depth', 'stripe', 'gap', 'block', 'y'})
    x0, z0, tx, tz = spine_at(b.spine(op.get('along', 'lane'), b.where), float(op.req('d')))
    width, depth = float(op.get('width', 9)), float(op.get('depth', 3))
    stripe, gap = float(op.get('stripe', 1)), float(op.get('gap', 1))
    y = int(op.get('y', -1))
    block = b.state(op.get('block', 'white_concrete'))
    r = math.ceil(math.hypot(width, depth) / 2) + 1
    for x in range(math.floor(x0 - r), math.floor(x0 + r) + 1):
        for z in range(math.floor(z0 - r), math.floor(z0 + r) + 1):
            dx, dz = x + 0.5 - x0, z + 0.5 - z0
            u, v = dx * tx + dz * tz, dz * tx - dx * tz          # along the lane, and to its right
            if abs(u) <= depth / 2 and abs(v) <= width / 2 and (v + width / 2) % (stripe + gap) < stripe:
                b.put(x, y, z, block)


def op_stream(b, spec):
    """Water in a channel along a curve: `width`, water `depth` (2), surface one block below the ground, banks of
    `bank` blocks, an optional `bed` mix and `plants` (lily pads on the surface, seagrass below)."""
    op = Op(spec, b.where, {'points', 'width', 'depth', 'bank', 'bed', 'y', 'plants', 'smooth'})
    pts = op.points('points')
    spine = smooth(pts) if op.get('smooth', True) else straight(pts)
    width = float(op.get('width', 3))
    depth = int(op.get('depth', 2))
    top = int(op.get('y', -1))
    bank = b.mix(op.get('bank', {'dirt': 3, 'gravel': 1, 'mud': 1}), 1.5, 'bank')
    bed = b.mix(op.get('bed', {'gravel': 3, 'sand': 2, 'clay': 1}), 1.5, 'bed')
    plants = float(op.get('plants', 0.04))
    inner = ribbon(spine, width / 2)
    outer = ribbon(spine, width / 2 + 1.5)
    surface = top - 1           # water's top block; the ground is cut away above it
    for (x, z), _ in outer.items():
        if (x, z) in inner:
            continue
        for y in range(surface - depth, top):
            b.put(x, y, z, bank.pick(x, z, y))
        if b.grid.get(x, top, z) is None:
            b.put(x, top, z, 'grass_block')
    for (x, z), (d, _a, _s) in inner.items():
        b.grid.remove(x, top, z)
        b.put(x, top, z, AIR)
        for y in range(surface - depth + 1, surface + 1):
            b.put(x, y, z, 'water')
        b.put(x, surface - depth, z, bed.pick(x, z))
        if b.rand(x, z, 5) < plants:
            b.put(x, top, z, 'lily_pad')
        elif b.rand(x, z, 6) < plants * 2 and depth >= 2:
            b.put(x, surface - depth + 1, z, 'seagrass')


def op_bridge(b, spec):
    """A plank bridge from `from` to `to` (straight, [x, z]): deck at the ground layer so the walk stays level, fence
    rails along both sides with gaps at the ends, log posts with lanterns at the four corners."""
    op = Op(spec, b.where, {'from', 'to', 'width', 'deck', 'rail', 'post', 'lanterns', 'y', 'beam', 'along', 'd'})
    width = int(op.get('width', 5))
    y = int(op.get('y', -1))
    deck = b.mix(op.get('deck', {'spruce_planks': 5, 'oak_planks': 1}), 0, 'deck')
    rail = op.get('rail', 'spruce_fence')
    post = op.get('post', 'stripped_spruce_log')
    beam = op.get('beam', 'stripped_spruce_log')
    if op.has('along'):
        _bridge_along(b, op, width, y, deck, rail, post, beam)
        return
    (x1, z1), (x2, z2) = op.xz('from'), op.xz('to')
    along_x = abs(x2 - x1) >= abs(z2 - z1)
    length = int(abs(x2 - x1) if along_x else abs(z2 - z1)) + 1
    sx = 1 if (x2 >= x1) else -1
    sz = 1 if (z2 >= z1) else -1
    half = width // 2
    for i in range(length):
        for j in range(-half, width - half):
            x, z = (x1 + i * sx, z1 + j) if along_x else (x1 + j, z1 + i * sz)
            b.grid.remove(x, y + 1, z)
            b.put(x, y, z, deck.pick(x, z))
            if j in (-half, width - half - 1):
                axis = 'x' if along_x else 'z'
                b.put(x, y - 1, z, f'{beam}[axis={axis}]')
                if 0 < i < length - 1:
                    b.put(x, y + 1, z, rail)
        if i in (0, length - 1):
            for j in (-half, width - half - 1):
                x, z = (x1 + i * sx, z1 + j) if along_x else (x1 + j, z1 + i * sz)
                b.put(x, y + 1, z, post)
                if op.get('lanterns', True):
                    b.put(x, y + 2, z, 'lantern')


def _bridge_along(b, op, width, y, deck, rail, post, beam):
    """A bridge that follows a curving lane: `along` (the lane), `d = [from, to]`; the deck is the lane's ribbon
    `width` wide, the outermost cells of it are the rails (on beams), with posts and lanterns at the four ends."""
    lane = op.get('along')
    spine = b.spine(lane, b.where)
    d1, d2 = op.req('d')
    half = width / 2
    cells = {c: v for c, v in ribbon(spine, half).items() if d1 <= v[1] <= d2}
    for (x, z), (dist, a, _sg) in cells.items():
        b.grid.remove(x, y + 1, z)
        b.put(x, y, z, deck.pick(x, z))
        if dist > half - 1:
            b.put(x, y - 1, z, f'{beam}[axis=y]')
            b.put(x, y + 1, z, rail)
    for d in (d1, d2):
        for sg in (-1, 1):
            x, z = b.along({'along': lane, 'd': d, 'side': (half - 0.5) * sg}, b.where)
            x, z = math.floor(x), math.floor(z)
            b.put(x, y + 1, z, f'{post}[axis=y]' if post.endswith('_log') else post)
            if op.get('lanterns', True):
                b.put(x, y + 2, z, 'lantern')


# ---------------------------------------------------------------- volumes


def op_box(b, spec):
    """A filled (or `hollow`) box of a block or a mix, `from` and `to` inclusive, [x, y, z]."""
    op = Op(spec, b.where, {'from', 'to', 'block', 'grain', 'hollow', 'keep'})
    (x1, y1, z1), (x2, y2, z2) = op.xyz('from'), op.xyz('to')
    mix = b.mix(op.req('block'), op.get('grain', 0), 'box')
    hollow, keep = op.get('hollow', False), op.get('keep', False)
    for x in range(min(x1, x2), max(x1, x2) + 1):
        for y in range(min(y1, y2), max(y1, y2) + 1):
            for z in range(min(z1, z2), max(z1, z2) + 1):
                edge = x in (x1, x2) or y in (y1, y2) or z in (z1, z2)
                if hollow and not edge:
                    b.put(x, y, z, AIR)
                else:
                    b.put(x, y, z, mix.pick(x, z, y), keep=keep)


def op_carve(b, spec):
    """Air in a box (clears what earlier entries put there)."""
    op = Op(spec, b.where, {'from', 'to'})
    (x1, y1, z1), (x2, y2, z2) = op.xyz('from'), op.xyz('to')
    for x in range(min(x1, x2), max(x1, x2) + 1):
        for y in range(min(y1, y2), max(y1, y2) + 1):
            for z in range(min(z1, z2), max(z1, z2) + 1):
                b.put(x, y, z, AIR)


def op_blocks(b, spec):
    """Single blocks: `list = [[x, y, z, "block[state]"], …]`."""
    op = Op(spec, b.where, {'list'})
    for e in op.req('list'):
        if not (isinstance(e, list) and len(e) == 4):
            raise SetError(f'{b.where}: each entry of `list` is [x, y, z, "block"] (got {e!r})')
        b.put(e[0], e[1], e[2], e[3])


def op_column(b, spec):
    """Stacks of blocks at positions: `at = [[x, y, z], …]`, `blocks = ["barrel", "hay_block", …]` bottom first."""
    op = Op(spec, b.where, {'at', 'blocks'})
    blocks = op.req('blocks')
    for p in op.points('at'):
        x, y, z = (p[0], 0, p[1]) if len(p) == 2 else p
        for k, blk in enumerate(blocks):
            b.put(x, y + k, z, blk)


# ---------------------------------------------------------------- buildings


def _line(a, c):
    """Cells on a straight (axis or diagonal-ish) line between two [x, z] cells, inclusive."""
    (x1, z1), (x2, z2) = a, c
    n = int(max(abs(x2 - x1), abs(z2 - z1)))
    if n == 0:
        return [(int(x1), int(z1))]
    return [(round(x1 + (x2 - x1) * t / n), round(z1 + (z2 - z1) * t / n)) for t in range(n + 1)]


def op_house(b, spec):
    """A cottage: a footprint `from`/`to` ([x, z], the walls), `height` of wall, `walls` mix, a `base` course, corner
    `frame` posts (also every `post_every`), a `band` course under the roof, `windows` with rhythm, a `door`, a `roof`
    (see `roof`), a `chimney`, a lit interior. Faces of the walls: windows on every side unless `windows.sides`."""
    op = Op(spec, b.where, {'from', 'to', 'y', 'height', 'walls', 'grain', 'base', 'frame', 'post_every', 'band',
                            'windows', 'door', 'roof', 'chimney', 'floor', 'light', 'interior', 'at', 'size', 'facing'})
    door = op.get('door', {'side': 'south'})
    if op.has('at'):
        # A footprint `size = [width, depth]` centred on `at`, its door on the `facing` side (e.g. "lane").
        cx, cz = op.xz('at')
        w, d = op.get('size', [7, 5])
        f = op.facing(default='south')
        W, D = (w, d) if f in ('north', 'south') else (d, w)
        x1, z1 = cx - (W - 1) // 2, cz - (D - 1) // 2
        x2, z2 = x1 + W - 1, z1 + D - 1
        door = {**(door or {}), 'side': f} if door is not False else False
    else:
        (x1, z1), (x2, z2) = op.xz('from'), op.xz('to')
    x1, x2, z1, z2 = min(x1, x2), max(x1, x2), min(z1, z2), max(z1, z2)
    y0 = int(op.get('y', 0))
    h = int(op.get('height', 4))
    walls = b.mix(op.get('walls', {'white_terracotta': 4, 'smooth_sandstone': 1}), op.get('grain', 0), 'walls')
    base = op.get('base', 'cobblestone')
    frame = op.get('frame', 'stripped_spruce_log')
    band = op.get('band', frame)
    post_every = int(op.get('post_every', 0))
    floor = op.get('floor', 'spruce_planks')
    top = y0 + h - 1
    # Shell and floor.
    for x in range(x1, x2 + 1):
        for z in range(z1, z2 + 1):
            b.put(x, y0 - 1, z, floor)
            edge = x in (x1, x2) or z in (z1, z2)
            for y in range(y0, top + 1):
                if edge:
                    blk = base if (y == y0 and base) else walls.pick(x, z, y)
                    b.put(x, y, z, blk)
                elif op.get('interior', True):
                    b.put(x, y, z, AIR)
    corners = {(x1, z1), (x1, z2), (x2, z1), (x2, z2)}
    posts = set(corners)
    if post_every:
        for x in range(x1, x2 + 1, post_every):
            posts |= {(x, z1), (x, z2)}
        for z in range(z1, z2 + 1, post_every):
            posts |= {(x1, z), (x2, z)}
        posts |= {(x2, z1), (x2, z2), (x1, z2)}
    if frame:
        for x, z in posts:
            for y in range(y0, top + 1):
                b.put(x, y, z, f'{frame}[axis=y]' if frame.endswith(('_log', '_wood')) and '[' not in frame else frame)
    if band:
        for x in range(x1, x2 + 1):
            for z in (z1, z2):
                b.put(x, top, z, f'{band}[axis=x]' if band.endswith('_log') and '[' not in band else band)
        for z in range(z1, z2 + 1):
            for x in (x1, x2):
                b.put(x, top, z, f'{band}[axis=z]' if band.endswith('_log') and '[' not in band else band)
    # Windows: a rhythm along each wall, skipping posts and the door.
    win = op.get('windows', {})
    door_cells = set()
    if door:
        side = door.get('side', 'south')
        if side not in STEP:
            raise SetError(f'{b.where}: door.side is north, east, south or west')
        off = int(door.get('offset', 0))
        cx, cz = (x1 + x2) // 2 + off, (z1 + z2) // 2 + off
        dx, dz = {'north': (cx, z1), 'south': (cx, z2), 'west': (x1, cz), 'east': (x2, cz)}[side]
        dblock = door.get('block', 'spruce_door')
        b.put(dx, y0, dz, f'{dblock}[facing={side},half=lower,hinge=left,open=false]')
        b.put(dx, y0 + 1, dz, f'{dblock}[facing={side},half=upper,hinge=left,open=false]')
        door_cells = {(dx, dz)}
        if door.get('step', True):
            sx, sz = STEP[side]
            if not b.grid.has(dx + sx, y0 - 1, dz + sz) or True:
                b.put(dx + sx, y0 - 1, dz + sz, door.get('step_block', 'cobblestone'))
        if door.get('lantern', True):
            sx, sz = STEP[side]
            b.put(dx + sx, y0 + 2, dz + sz, 'lantern[hanging=true]') if h >= 4 else None
            if h >= 4:
                b.put(dx + sx, y0 + 3, dz + sz, f'{frame}' if frame else 'spruce_planks')
    if win is not False:
        every = int(win.get('every', 3))
        ww = int(win.get('width', 1))
        wh = int(win.get('height', 2 if h >= 4 else 1))
        sill = int(win.get('sill', 1))
        glass = win.get('block', 'glass_pane')
        shutters = win.get('shutters')
        boxes = win.get('boxes')
        sides = win.get('sides', ['north', 'east', 'south', 'west'])
        walls_cells = {
            'north': [(x, z1) for x in range(x1 + 1, x2)], 'south': [(x, z2) for x in range(x1 + 1, x2)],
            'west': [(x1, z) for z in range(z1 + 1, z2)], 'east': [(x2, z) for z in range(z1 + 1, z2)]}
        for side in sides:
            cells = walls_cells[side]
            n = len(cells)
            if n < 3:
                continue
            # Centre the rhythm on the wall.
            starts = list(range(1, n - ww, every))
            if not starts:
                continue
            shift = (n - 1 - (starts[-1] + ww - 1) - starts[0]) // 2
            for s in starts:
                run = [cells[i] for i in range(s + shift, s + shift + ww) if 0 <= i < n]
                if any(c in posts or c in door_cells or any(abs(c[0] - d[0]) + abs(c[1] - d[1]) <= 1 for d in door_cells) for c in run):
                    continue
                for (x, z) in run:
                    for y in range(y0 + sill, min(top, y0 + sill + wh)):
                        b.put(x, y, z, glass)
                sx, sz = STEP[side]
                if shutters:
                    ends = [run[0], run[-1]]
                    along = (1, 0) if side in ('north', 'south') else (0, 1)
                    for (cx, cz), sign in ((ends[0], -1), (ends[-1], 1)):
                        px, pz = cx + along[0] * sign + sx, cz + along[1] * sign + sz
                        for y in range(y0 + sill, min(top, y0 + sill + wh)):
                            b.put(px, y, pz, f'{shutters}[facing={side},open=true,half=bottom,hinge=left]'
                                  if 'trapdoor' not in shutters else f'{shutters}[facing={side},open=true,half=bottom]')
                if boxes:
                    for (x, z) in run:
                        b.put(x + sx, y0 + sill - 1, z + sz, f'{boxes.get("block", "spruce_trapdoor")}[facing={side},half=top,open=false]'
                              if 'trapdoor' in boxes.get('block', 'spruce_trapdoor') else boxes.get('block'))
                        b.put(x + sx, y0 + sill, z + sz, b.mix(boxes.get('plants', {'potted_red_tulip': 1}), 0, 'box').pick(x, z))
    light = op.get('light', 11)
    if light:
        b.put((x1 + x2) // 2, y0 + max(1, h - 2), (z1 + z2) // 2, f'light[level={int(light)}]')
    roof = op.get('roof', {})
    if roof is not False:
        roof_spec = {'do': 'roof', 'from': [x1, z1], 'to': [x2, z2], 'y': top + 1, **roof}
        saved = b.where
        op_roof(b, roof_spec)
        b.where = saved
    ch = op.get('chimney')
    if ch:
        # Inside the footprint, by default at the back corner away from the door.
        back = {'north': (x2 - 1, z2 - 1), 'south': (x1 + 1, z1 + 1), 'east': (x1 + 1, z2 - 1), 'west': (x2 - 1, z1 + 1)}
        cx, cz = ch.get('at', back.get((door or {}).get('side', 'south'), (x1 + 1, z1 + 1)))
        for y in range(y0, top + 1 + int(ch.get('height', 6))):
            b.put(cx, y, cz, ch.get('block', 'bricks'))
        b.put(cx, top + 1 + int(ch.get('height', 6)), cz, ch.get('cap', 'brick_slab[type=bottom]'))


def op_roof(b, spec):
    """A roof on top of a rectangle of walls (`from`/`to` [x, z], at height `y`): `kind` gable or hip, of `block`
    stairs (`"dark_oak"` means dark_oak_stairs/planks/slab), with `overhang` (1), the ridge along the longer side
    unless `ridge = "x"|"z"`, gable ends filled with `gable` (planks), a slab `cap` on an odd ridge."""
    op = Op(spec, b.where, {'from', 'to', 'y', 'kind', 'block', 'overhang', 'ridge', 'gable', 'cap', 'trim'})
    (x1, z1), (x2, z2) = op.xz('from'), op.xz('to')
    x1, x2, z1, z2 = min(x1, x2), max(x1, x2), min(z1, z2), max(z1, z2)
    y0 = int(op.req('y'))
    kind = op.get('kind', 'gable')
    wood = op.get('block', 'dark_oak')
    stairs = wood if wood.endswith('_stairs') else (wood[:-7] if wood.endswith('_planks') else wood) + '_stairs'
    base_name = stairs[:-7]
    planks = {'brick': 'bricks', 'stone_brick': 'stone_bricks', 'mud_brick': 'mud_bricks', 'deepslate_tile': 'deepslate_tiles',
              'cobblestone': 'cobblestone', 'stone': 'stone', 'red_sandstone': 'red_sandstone', 'sandstone': 'sandstone'}.get(base_name, base_name + '_planks')
    slab = base_name + '_slab'
    if base_name in ('brick', 'stone_brick', 'mud_brick', 'deepslate_tile'):
        slab = base_name + '_slab'
    gable = op.get('gable', planks)
    o = int(op.get('overhang', 1))
    rx1, rx2, rz1, rz2 = x1 - o, x2 + o, z1 - o, z2 + o
    ridge = op.get('ridge', 'x' if (x2 - x1) >= (z2 - z1) else 'z')
    cap = op.get('cap', slab + '[type=bottom]')
    if kind == 'gable':
        if ridge == 'x':
            n = rz2 - rz1 + 1
            for i in range(n):
                z = rz1 + i
                hi = min(i, n - 1 - i)
                y = y0 + hi - o
                odd_ridge = (n % 2 == 1 and i == n // 2)
                for x in range(rx1, rx2 + 1):
                    if odd_ridge:
                        b.put(x, y, z, cap)
                        if y - 1 >= y0 - o:
                            b.put(x, y - 1, z, planks) if x in (x1, x2) or True else None
                    else:
                        facing = 'north' if i > (n - 1) / 2 else 'south'
                        b.put(x, y, z, f'{stairs}[facing={facing},half=bottom]')
                # Gable ends: fill the triangle under this roof row inside the wall planes.
                if z1 <= z <= z2:
                    for x in (x1, x2):
                        for yy in range(y0, y):
                            b.put(x, yy, z, gable)
        else:
            n = rx2 - rx1 + 1
            for i in range(n):
                x = rx1 + i
                hi = min(i, n - 1 - i)
                y = y0 + hi - o
                odd_ridge = (n % 2 == 1 and i == n // 2)
                for z in range(rz1, rz2 + 1):
                    if odd_ridge:
                        b.put(x, y, z, cap)
                        if y - 1 >= y0 - o:
                            b.put(x, y - 1, z, planks)
                    else:
                        facing = 'west' if i > (n - 1) / 2 else 'east'
                        b.put(x, y, z, f'{stairs}[facing={facing},half=bottom]')
                if x1 <= x <= x2:
                    for z in (z1, z2):
                        for yy in range(y0, y):
                            b.put(x, yy, z, gable)
    elif kind == 'hip':
        ax1, ax2, az1, az2 = rx1, rx2, rz1, rz2
        y = y0 - o
        while ax1 <= ax2 and az1 <= az2:
            if ax2 - ax1 == 0 or az2 - az1 == 0:
                for x in range(ax1, ax2 + 1):
                    for z in range(az1, az2 + 1):
                        b.put(x, y, z, cap)
                break
            if az2 - az1 == 1 or ax2 - ax1 == 1:
                # Two rows left: a short ridge of stairs facing each other.
                for x in range(ax1, ax2 + 1):
                    for z in range(az1, az2 + 1):
                        if az2 - az1 == 1:
                            b.put(x, y, z, f'{stairs}[facing={"south" if z == az1 else "north"},half=bottom]')
                        else:
                            b.put(x, y, z, f'{stairs}[facing={"east" if x == ax1 else "west"},half=bottom]')
                break
            for x in range(ax1, ax2 + 1):
                b.put(x, y, az1, f'{stairs}[facing=south,half=bottom]')
                b.put(x, y, az2, f'{stairs}[facing=north,half=bottom]')
            for z in range(az1 + 1, az2):
                b.put(ax1, y, z, f'{stairs}[facing=east,half=bottom]')
                b.put(ax2, y, z, f'{stairs}[facing=west,half=bottom]')
            # Corners: which way a corner stair faces decides the shape vanilla would give it (shapes.finish).
            b.put(ax1, y, az1, f'{stairs}[facing=south,half=bottom]')
            b.put(ax2, y, az1, f'{stairs}[facing=south,half=bottom]')
            b.put(ax1, y, az2, f'{stairs}[facing=north,half=bottom]')
            b.put(ax2, y, az2, f'{stairs}[facing=north,half=bottom]')
            ax1, ax2, az1, az2 = ax1 + 1, ax2 - 1, az1 + 1, az2 - 1
            y += 1
            # The next ring sits diagonally on this one; a hidden ring of planks under it makes the roof one piece.
            if y - 1 > y0 - o:
                for x in range(ax1, ax2 + 1):
                    for z in (az1, az2):
                        b.put(x, y - 1, z, planks, keep=True)
                for z in range(az1, az2 + 1):
                    for x in (ax1, ax2):
                        b.put(x, y - 1, z, planks, keep=True)
    else:
        raise SetError(f'{b.where}: roof kind is gable or hip (got {kind!r})')
    trim = op.get('trim')
    if trim:
        # Upside-down stairs under the eaves along the long sides: a soffit line.
        if ridge == 'x':
            for x in range(rx1, rx2 + 1):
                b.put(x, y0 - o - 1, rz1, f'{stairs}[facing=south,half=top]', keep=True)
                b.put(x, y0 - o - 1, rz2, f'{stairs}[facing=north,half=top]', keep=True)


def op_stall(b, spec):
    """A market stall facing `facing` (toward the customers): counter, posts, a striped awning in `colors`
    (two wool colours), a scalloped valance, `goods` on the counter, a hanging lantern. `at` is the middle of the
    counter's front. `mark = "stall-1"` exports a point three blocks in front, facing the stall."""
    op = Op(spec, b.where, {'at', 'facing', 'width', 'depth', 'wood', 'colors', 'goods', 'lantern', 'mark', 'height'})
    width = int(op.get('width', 5))
    depth = int(op.get('depth', 3))
    wood = op.get('wood', 'spruce')
    colors = op.get('colors', ['red_wool', 'white_wool'])
    goods = op.get('goods', ['pumpkin', 'melon', 'hay_block', 'barrel[facing=up]', 'potted_poppy'])
    ph = int(op.get('height', 3))
    part = Builder(b.name, b.seed ^ noise.salt(f'stall{b.n}'), b.parts, b.where)
    hw = width // 2
    xs = range(-hw, width - hw)
    back = -(depth - 1)
    # Posts at the corners: front ones `ph` tall, back ones a block taller (the awning slopes to the front).
    for x in (xs[0], xs[-1]):
        for y in range(0, ph):
            part.put(x, y, 0, f'{wood}_fence')
        for y in range(0, ph + 1):
            part.put(x, y, back, f'stripped_{wood}_log[axis=y]')
    # Counter along the front, goods on it; a back shelf of barrels.
    for i, x in enumerate(xs[1:-1]):
        part.put(x, 0, 0, f'{wood}_planks' if i % 2 else f'stripped_{wood}_log[axis=x]')
        g = goods[(i + b.n) % len(goods)] if goods else None
        if g:
            part.put(x, 1, 0, g)
        if depth > 2:
            part.put(x, 0, back, 'barrel[facing=up]' if i % 2 == 0 else 'composter[level=7]')
    # Awning: stripes run front to back, alternate per column; front lip one block out.
    for i, x in enumerate(range(xs[0], xs[-1] + 1)):
        color = colors[i % len(colors)]
        for z in range(back, 2):
            y = ph + 1 if z <= back + (depth - 1) // 2 else ph
            part.put(x, y, z, color)
        if i % 2 == 0:
            part.put(x, ph - 1, 1, color)  # the valance's scallops
    if op.get('lantern', True):
        part.put(0, ph - 1, 0, 'lantern[hanging=true]')
    _stamp(b, part, op.xz('at'), op.facing(), 0)
    name = op.get('mark')
    if name:
        f = op.facing()
        ax, az = op.xz('at')
        dx, dz = STEP[f]
        b.add_mark(name, {'kind': 'point', 'at': (ax + 0.5 + dx * 3, 0, az + 0.5 + dz * 3), 'yaw': YAW[turn_dir(f, 2)]})


def _stamp(b, part, at_xz, facing, y=0, mirror=False):
    """Copies a south-facing part into the set, turned to `facing`, its origin at `at_xz`."""
    q = FACING_QUARTERS[facing] if isinstance(facing, str) else int(facing)
    ax, az = at_xz
    b.grid.stamp(part.grid, (int(ax), int(y), int(az)), q, mirror)
    for e in part.entities:
        b.entities.append(transform_entity(e, q, mirror, (int(ax), int(y), int(az))))


def transform_entity(e, q, mirror, at):
    from .model import turn_point, turn_yaw
    ax, ay, az = at
    e = dict(e)
    if 'box' in e:
        (lx, ly, lz), (hx, hy, hz) = e['box']
        p1 = turn_point(lx, lz, q, mirror)
        p2 = turn_point(hx, hz, q, mirror)
        e['box'] = ((min(p1[0], p2[0]) + ax, ly + ay, min(p1[1], p2[1]) + az), (max(p1[0], p2[0]) + ax, hy + ay, max(p1[1], p2[1]) + az))
        e['block'] = e['block'].turned(q, mirror)
    else:
        x, y, z = e['pos']
        px, pz = turn_point(x, z, q, mirror)
        e['pos'] = (px + ax, y + ay, pz + az)
        if e.get('yaw') is not None:
            e['yaw'] = turn_yaw(e['yaw'], q, mirror)
        if e.get('facing'):
            e['facing'] = turn_dir(e['facing'], q, mirror)
    return e


def op_fence(b, spec):
    """A fence along straight segments through `points` ([x, z]), on layer `y` (0), `height` (1); `posts` every n
    with a `post` block and lanterns on top (`lanterns = true`)."""
    op = Op(spec, b.where, {'points', 'block', 'y', 'height', 'posts', 'post', 'lanterns', 'gaps'})
    pts = op.points('points')
    blk = op.get('block', 'spruce_fence')
    y = int(op.get('y', 0))
    h = int(op.get('height', 1))
    every = int(op.get('posts', 0))
    post = op.get('post', blk)
    gaps = {tuple(g) for g in op.get('gaps', [])}
    cells = []
    for a, c in zip(pts, pts[1:]):
        for cell in _line(a, c):
            if not cells or cells[-1] != cell:
                cells.append(cell)
    for i, (x, z) in enumerate(cells):
        if (x, z) in gaps:
            continue
        is_post = every and (i % every == 0 or i == len(cells) - 1)
        for k in range(h + (1 if is_post and post != blk else 0)):
            b.put(x, y + k, z, post if is_post else blk)
        if is_post and op.get('lanterns', False):
            b.put(x, y + h + (1 if post != blk else 0), z, 'lantern')


def op_lamp(b, spec):
    """Lantern posts at `at` ([x, z] or [x, y, z]): a `post` (spruce_fence) `height` tall on a `base`, a lantern on
    top, or hanging from an `arm` toward a side (north/east/south/west)."""
    op = Op(spec, b.where, {'at', 'height', 'post', 'base', 'arm', 'light', 'top'})
    h = int(op.get('height', 3))
    post = op.get('post', 'spruce_fence')
    base = op.get('base', 'cobblestone_wall')
    arm = op.get('arm')
    light = op.get('light', 'lantern')
    for p in op.points('at'):
        x, y, z = (p[0], 0, p[1]) if len(p) == 2 else p
        if base:
            b.put(x, y, z, base)
        for k in range(1 if base else 0, h):
            b.put(x, y + k, z, post)
        if arm:
            dx, dz = STEP[arm]
            b.put(x, y + h, z, op.get('top', post))
            b.put(x + dx, y + h, z + dz, post)
            b.put(x + dx, y + h - 1, z + dz, f'{light}[hanging=true]')
        else:
            b.put(x, y + h, z, f'{light}[hanging=false]')


# ---------------------------------------------------------------- plants


def op_tree(b, spec):
    """Trees at `at` ([x, z] or [x, y, z]): `kind` oak, birch, spruce, cherry, dark_oak, jungle or acacia (log and
    leaves of that wood), `height` [min, max], `radius` of the canopy; every tree differs by seed."""
    op = Op(spec, b.where, {'at', 'kind', 'height', 'radius', 'leaves', 'log'})
    kind = op.get('kind', 'oak')
    hmin, hmax = op.get('height', {'spruce': [7, 10], 'birch': [5, 7], 'cherry': [5, 6], 'dark_oak': [5, 7]}.get(kind, [4, 6]))
    radius = float(op.get('radius', {'spruce': 3, 'cherry': 3.5, 'dark_oak': 3.5}.get(kind, 2.6)))
    log = op.get('log', f'{kind}_log')
    leaves = op.get('leaves', 'azalea_leaves' if kind == 'azalea' else f'{kind}_leaves')
    for p in op.points('at'):
        x, y, z = (p[0], 0, p[1]) if len(p) == 2 else p
        r = b.rand(x, z, 1)
        h = int(hmin + (hmax - hmin + 1) * r)
        if kind == 'spruce':
            for k in range(h):
                b.put(x, y + k, z, f'{log}[axis=y]')
            top = y + h
            layers = h - 2
            for k in range(layers):
                yy = top - k
                rr = (k % 2 + 1) * (0.5 + k / layers * radius / 1.6) if k > 0 else 0.6
                for dx in range(-4, 5):
                    for dz in range(-4, 5):
                        d = math.hypot(dx, dz)
                        if d <= rr + 0.3 and not (dx == 0 and dz == 0 and k > 0):
                            if d > rr - 0.5 and b.rand(x + dx, yy, z + dz) < 0.25:
                                continue
                            b.put(x + dx, yy, z + dz, leaves, keep=True)
            b.put(x, top + 1, z, leaves)
            continue
        trunk = [(0, 0)] if kind != 'dark_oak' else [(0, 0), (1, 0), (0, 1), (1, 1)]
        for k in range(h):
            for tx, tz in trunk:
                b.put(x + tx, y + k, z + tz, f'{log}[axis=y]')
        cy = y + h - (1 if kind != 'cherry' else 0)
        rad = radius * (0.85 + 0.3 * b.rand(x, z, 2))
        flat = 0.7 if kind in ('cherry', 'acacia', 'dark_oak') else 1.0
        cxo = 0.5 if kind == 'dark_oak' else 0
        ri = math.ceil(rad) + 1
        for dx in range(-ri, ri + 1 + (1 if cxo else 0)):
            for dz in range(-ri, ri + 1 + (1 if cxo else 0)):
                for dy in range(-2, 3):
                    d = math.sqrt((dx - cxo) ** 2 + (dz - cxo) ** 2 + (dy / flat) ** 2)
                    edge = rad + (b.rand(x + dx, cy + dy, z + dz) - 0.5) * 1.2
                    if d <= edge and not (dy < -1 and d > rad * 0.6):
                        b.put(x + dx, cy + dy, z + dz, leaves, keep=True)
        _prune_leaves(b, x, cy, z, ri + 3)
        if kind in ('oak', 'birch', 'jungle', 'cherry') and b.rand(x, z, 9) < 0.5:
            # A low branch, so the silhouette is not a lollipop.
            side = HORIZONTAL[int(b.rand(x, z, 10) * 4)]
            dx, dz = STEP[side]
            by = y + max(2, h - 3)
            b.put(x + dx, by, z + dz, f'{log}[axis={"x" if dx else "z"}]')
            for ex in range(-1, 2):
                for ez in range(-1, 2):
                    b.put(x + 2 * dx + ex, by + 1, z + 2 * dz + ez, leaves, keep=True)


def _prune_leaves(b, x, y, z, r):
    """Drops leaf blocks that touch nothing (the noisy canopy edge leaves a few hanging in the air)."""
    cells = b.grid.cells
    for dx in range(-r, r + 1):
        for dz in range(-r, r + 1):
            for dy in range(-3, 4):
                k = (x + dx, y + dy, z + dz)
                s = cells.get(k)
                if s is None or not s.id.endswith('_leaves'):
                    continue
                if not any(cells.get((k[0] + a, k[1] + c, k[2] + e)) is not None for a, c, e in
                           ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))):
                    del cells[k]


def op_bush(b, spec):
    """Low leafy bushes at `at`: `leaves` (oak_leaves; azalea, flowering_azalea…), `size` 1-3."""
    op = Op(spec, b.where, {'at', 'leaves', 'size'})
    leaves = op.get('leaves', 'oak_leaves')
    size = int(op.get('size', 2))
    for p in op.points('at'):
        x, y, z = (p[0], 0, p[1]) if len(p) == 2 else p
        for dx in range(-size + 1, size):
            for dz in range(-size + 1, size):
                for dy in range(0, size):
                    d = math.sqrt(dx * dx + dz * dz + (dy * 1.6) ** 2)
                    if d <= size - 0.3 + (b.rand(x + dx, y + dy, z + dz) - 0.5):
                        b.put(x + dx, y + dy, z + dz, leaves, keep=True)


def op_scatter(b, spec):
    """Plants or small props scattered over an area on top of the ground: `blocks` mix, `density` (0-1), `on`
    (blocks they may stand on; default grass_block), `y` (0, the layer they go in)."""
    op = Op(spec, b.where, {'from', 'to', 'center', 'radius', 'blocks', 'density', 'on', 'y', 'grain', 'near', 'within'})
    mix = b.mix(op.req('blocks'), op.get('grain', 0), 'scatter')
    near = BlockState.parse(op.get('near')).name if op.has('near') else None
    within = int(op.get('within', 1))
    density = float(op.get('density', 0.15))
    on = {BlockState.parse(o).name for o in op.get('on', ['grass_block'])}
    y = op.get('y')
    for x, z in b.area(op):
        yy = int(y) if y is not None else None
        if yy is None:
            t = b.top(x, z)
            if t is None:
                continue
            yy = t + 1
        below = b.grid.get(x, yy - 1, z)
        if below is None or below.name not in on or b.grid.has(x, yy, z):
            continue
        if near and not any(b.grid.get(x + a, y2, z + c) is not None and b.grid.get(x + a, y2, z + c).name == near
                            for a in range(-within, within + 1) for c in range(-within, within + 1) for y2 in range(yy - 3, yy + 1)):
            continue
        if b.rand(x, z, 77) < density:
            blk = mix.pick(x, z)
            if blk != 'air':
                b.put(x, yy, z, blk)


def op_crops(b, spec):
    """A field: farmland rows in `from`/`to` ([x, z]) with `crop` (wheat, carrots, potatoes, beetroots) at `age`,
    a water channel every `water` rows (default 4), along `rows` ("x" or "z")."""
    op = Op(spec, b.where, {'from', 'to', 'crop', 'age', 'water', 'rows', 'y', 'avoid', 'margin'})
    crop = op.get('crop', 'wheat')
    age = int(op.get('age', 7 if crop != 'beetroots' else 3))
    water = int(op.get('water', 4))
    rows = op.get('rows', 'x')
    y = int(op.get('y', -1))
    # `avoid = "lane"`: keep `margin` (5) blocks clear of that lane's centre line (a field beside a bend).
    keep = set(ribbon(b.spine(op.get('avoid'), b.where), float(op.get('margin', 5)))) if op.has('avoid') else set()
    for x, z in b.area(op):
        if (x, z) in keep:
            continue
        k = z if rows == 'x' else x
        if water and k % (water + 1) == water:
            b.put(x, y, z, 'water')
            b.grid.remove(x, y + 1, z)
        else:
            b.put(x, y, z, 'farmland[moisture=7]')
            jitter = 0 if b.rand(x, z, 4) > 0.2 else -1
            b.put(x, y + 1, z, f'{crop}[age={max(0, age + jitter)}]')


# ---------------------------------------------------------------- props


def op_pile(b, spec):
    """A loose pile of props around `at` ([x, z] or [x, y, z]): `count` of `blocks` (a mix), stacked at most
    `stack` high within `radius`."""
    op = Op(spec, b.where, {'at', 'radius', 'count', 'blocks', 'stack'})
    mix = b.mix(op.get('blocks', {'barrel[facing=up]': 3, 'hay_block': 2, 'spruce_planks': 1}), 0, 'pile')
    radius = float(op.get('radius', 1.5))
    count = int(op.get('count', 5))
    stack = int(op.get('stack', 2))
    for p in op.points('at'):
        x0, y0, z0 = (p[0], 0, p[1]) if len(p) == 2 else p
        placed = 0
        tries = 0
        while placed < count and tries < count * 10:
            tries += 1
            a = b.rand(x0, z0, tries, 1) * 2 * math.pi
            r = b.rand(x0, z0, tries, 2) ** 0.7 * radius
            x, z = round(x0 + math.cos(a) * r), round(z0 + math.sin(a) * r)
            y = y0
            while b.grid.has(x, y, z) and y < y0 + stack:
                y += 1
            if y >= y0 + stack or (y > y0 and not b.grid.has(x, y - 1, z)):
                continue
            b.put(x, y, z, mix.pick(x, z, tries))
            placed += 1


def op_well(b, spec):
    """A village well at `at` ([x, z], its middle): a stone ring with water, two posts and a little roof."""
    op = Op(spec, b.where, {'at', 'stone', 'wood', 'roof', 'mark', 'facing'})
    stone = op.get('stone', {'cobblestone': 3, 'mossy_cobblestone': 1, 'stone_bricks': 1})
    wood = op.get('wood', 'spruce')
    roof = op.get('roof', 'dark_oak')
    part = Builder(b.name, b.seed ^ noise.salt(f'well{b.n}'), b.parts, b.where)
    mix = part.mix(stone, 0, 'well')
    for dx in range(-2, 3):
        for dz in range(-2, 3):
            ring = max(abs(dx), abs(dz)) == 2
            part.put(dx, -1, dz, mix.pick(dx, dz))
            if ring:
                part.put(dx, 0, dz, mix.pick(dx, dz, 1))
            else:
                part.put(dx, 0, dz, 'water')
                part.put(dx, -1, dz, 'water')
                part.put(dx, -2, dz, mix.pick(dx, dz, 2))
    for dx in (-2, 2):
        for y in range(1, 4):
            part.put(dx, y, 0, f'{wood}_fence')
    for dx in range(-3, 4):
        part.put(dx, 4, -1, f'{roof}_stairs[facing=south,half=bottom]')
        part.put(dx, 4, 1, f'{roof}_stairs[facing=north,half=bottom]')
        part.put(dx, 4, 0, f'{roof}_slab[type=top]' if abs(dx) < 3 else f'{roof}_slab[type=top]')
        part.put(dx, 5, 0, f'{roof}_slab[type=bottom]')
    part.put(0, 3, 0, 'iron_chain[axis=y]')
    part.put(0, 2, 0, 'lantern[hanging=true]')
    _stamp(b, part, op.xz('at'), op.facing(default='south'))
    name = op.get('mark')
    if name:
        ax, az = op.xz('at')
        b.add_mark(name, {'kind': 'point', 'at': (ax + 0.5, 0, az + 3.5), 'yaw': 180.0})


def op_cart(b, spec):
    """A hand cart at `at` ([x, z]) pointing `facing`: a plank bed on two wheels, shafts in front, a `load`."""
    op = Op(spec, b.where, {'at', 'facing', 'wood', 'load', 'mark'})
    wood = op.get('wood', 'spruce')
    load = op.get('load', ['hay_block', 'pumpkin', 'barrel[facing=up]'])
    part = Builder(b.name, b.seed ^ noise.salt(f'cart{b.n}'), b.parts, b.where)
    for z in range(-1, 2):
        for x in (0, 1):
            part.put(x, 0, z, f'{wood}_slab[type=top]')
    for x, side in ((-1, 'west'), (2, 'east')):
        part.put(x, 0, 0, f'dark_oak_trapdoor[facing={side},open=true,half=bottom]')
    part.put(0, 0, 2, f'{wood}_fence')
    part.put(1, 0, 2, f'{wood}_fence')
    for i, blk in enumerate(load[:4]):
        part.put(i % 2, 1, -1 + i // 2, blk)
    _stamp(b, part, op.xz('at'), op.facing())


def op_pots(b, spec):
    """Flower pots at `at` ([x, y, z]), each a plant from `plants` (potted_* blocks)."""
    op = Op(spec, b.where, {'at', 'plants'})
    mix = b.mix(op.get('plants', {'potted_poppy': 2, 'potted_dandelion': 2, 'potted_blue_orchid': 1, 'potted_azure_bluet': 1,
                                  'potted_red_tulip': 1, 'potted_fern': 1}), 0, 'pots')
    for p in op.points('at'):
        x, y, z = (p[0], 0, p[1]) if len(p) == 2 else p
        b.put(x, y, z, mix.pick(x, z, y))


# ---------------------------------------------------------------- light


def op_light(b, spec):
    """Hidden light blocks (no model, no shadow): at `at` ([x, y, z] list) or over a grid (`from`/`to` [x, z],
    `y`, `step`), at `level` (15). Only where the cell is free."""
    op = Op(spec, b.where, {'at', 'from', 'to', 'y', 'step', 'level'})
    level = int(op.get('level', 15))
    cells = []
    if op.has('at'):
        cells = [tuple(p) if len(p) == 3 else (p[0], 0, p[1]) for p in op.points('at')]
    else:
        step = int(op.get('step', 6))
        y = int(op.req('y'))
        (x1, z1), (x2, z2) = op.xz('from'), op.xz('to')
        cells = [(x, y, z) for x in range(min(x1, x2), max(x1, x2) + 1, step) for z in range(min(z1, z2), max(z1, z2) + 1, step)]
    for x, y, z in cells:
        if not b.grid.has(x, y, z):
            b.put(x, y, z, f'light[level={level}]')


# ---------------------------------------------------------------- the backdrop


def op_backdrop(b, spec):
    """A ring of hills round a rectangle (`from`/`to` [x, z], usually the ground plate), `width` blocks deep,
    rising from the ground at the inner edge to `height = [near, far]` with seeded `roughness`; a `surface` mix,
    `under` below, trees on top (`trees = { kinds = […], density }`), far cottages (`houses = n`).
    `open = { side = "east", drop = 18, far = 6 }` turns one side into a valley: the ground falls away and rises again
    to lower far hills, so a camera sees a view rather than a wall. The crust is a few blocks thick and closed."""
    op = Op(spec, b.where, {'from', 'to', 'width', 'height', 'roughness', 'surface', 'under', 'trees', 'houses', 'open',
                            'y', 'scale', 'skin'})
    (x1, z1), (x2, z2) = op.xz('from'), op.xz('to')
    x1, x2, z1, z2 = min(x1, x2), max(x1, x2), min(z1, z2), max(z1, z2)
    width = int(op.get('width', 32))
    near, far = op.get('height', [4, 22])
    rough = float(op.get('roughness', 6))
    scale = float(op.get('scale', 14))
    top0 = int(op.get('y', -1))
    surface = b.mix(op.get('surface', {'grass_block': 6, 'moss_block': 1, 'coarse_dirt': 1}), 4, 'surface')
    under = b.state(op.get('under', 'dirt'))
    opened = op.get('open')
    seed = b.seed ^ noise.salt(f'hills{b.n}')
    heights = {}
    ow = int(opened.get('width', width)) if opened else width
    reach = max(width, ow)
    oside = opened.get('side', 'east') if opened else None
    for x in range(x1 - reach, x2 + reach + 1):
        for z in range(z1 - reach, z2 + reach + 1):
            dx = max(x1 - x, 0, x - x2)
            dz = max(z1 - z, 0, z - z2)
            if dx == 0 and dz == 0:
                continue
            d = math.hypot(dx, dz)
            on_open = oside is not None and {'east': x > x2, 'west': x < x1, 'south': z > z2, 'north': z < z1}[oside]
            lim = ow if on_open else width
            if d > lim:
                continue
            t = min(1.0, d / width)
            ramp = t * t * (3 - 2 * t)
            h = near + (far - near) * ramp + (noise.fbm(seed, x / scale, z / scale, 3) - 0.5) * 2 * rough * min(1, t * 2.5)
            # The first blocks off the plate rise gently, so the join to the ground is not a step.
            h = min(h, d * 0.9)
            if opened and not on_open:
                # The hills either side lower toward the open end, so it opens out instead of making a gorge.
                taper = float(opened.get('taper', 40))
                to_open = {'east': x2 - x, 'west': x - x1, 'south': z2 - z, 'north': z - z1}[oside]
                if to_open < taper:
                    h *= 0.35 + 0.65 * max(0.0, to_open) / taper
            if opened:
                side = opened.get('side', 'east')
                dist_side = {'east': x - x2, 'west': x1 - x, 'south': z - z2, 'north': z1 - z}[side]
                if dist_side > 0:
                    drop = float(opened.get('drop', 18))
                    farh = float(opened.get('far', 6))
                    u = dist_side / ow
                    # Falls away over the first half, a valley floor, then rises gently to far hills at the rim.
                    if u < 0.45:
                        valley = -drop * math.sin(u / 0.45 * math.pi / 2)
                    elif u < 0.6:
                        valley = -drop
                    else:
                        t2 = (u - 0.6) / 0.4
                        valley = -drop + (drop + farh) * (t2 * t2 * (3 - 2 * t2))
                    other = max(0, {'east': max(z1 - z, z - z2), 'west': max(z1 - z, z - z2),
                                    'south': max(x1 - x, x - x2), 'north': max(x1 - x, x - x2)}[side])
                    blend = min(1.0, other / 12)
                    h = valley * (1 - blend) + h * blend + (noise.fbm(seed + 5, x / 9, z / 9, 2) - 0.5) * 3
            heights[(x, z)] = top0 + round(h)
    green = b.state(op.get('skin', 'moss_block'))
    for (x, z), h in heights.items():
        lowest = min([h] + [heights.get((x + a, z + c), top0) for a, c in ((1, 0), (-1, 0), (0, 1), (0, -1))]) - 2
        for y in range(min(lowest, h - 2), h):
            # The two layers under the surface show on the faces of steps: green there, so hills read as hills
            # rather than terraces of dirt.
            b.put(x, y, z, green if y >= h - 2 else under)
        b.put(x, h, z, surface.pick(x, z))
    trees = op.get('trees')
    if trees:
        kinds = trees.get('kinds', ['oak', 'spruce', 'birch'])
        density = float(trees.get('density', 0.02))
        spots = []
        for (x, z), h in heights.items():
            d = math.hypot(max(x1 - x, 0, x - x2), max(z1 - z, 0, z - z2))
            if d < 6:
                continue
            if b.rand(x, z, 41) < density * (0.4 + noise.fbm(seed + 9, x / 20, z / 20, 2)):
                spots.append((x, h + 1, z))
        for i, (x, y, z) in enumerate(spots):
            kind = kinds[int(b.rand(x, z, 42) * len(kinds))]
            saved = b.where
            op_tree(b, {'do': 'tree', 'at': [[x, y, z]], 'kind': kind})
            b.where = saved
    houses = int(op.get('houses', 0))
    if houses:
        cands = sorted(heights.items(), key=lambda kv: noise.rand(seed, kv[0][0], kv[0][1], 99))
        placed = []
        for (x, z), h in cands:
            if len(placed) >= houses:
                break
            d = math.hypot(max(x1 - x, 0, x - x2), max(z1 - z, 0, z - z2))
            if not (width * 0.35 < d < width * 0.8) or any(math.dist((x, z), p) < 24 for p in placed):
                continue
            # A small cottage on a level pad.
            hh = h
            for a in range(-3, 4):
                for c in range(-3, 4):
                    hh = max(hh, heights.get((x + a, z + c), h))
            for a in range(-3, 4):
                for c in range(-3, 4):
                    for y in range(heights.get((x + a, z + c), h) + 1, hh + 1):
                        b.put(x + a, y, z + c, under if y < hh else surface.pick(x + a, z + c))
            saved = b.where
            op_house(b, {'do': 'house', 'from': [x - 2, z - 2], 'to': [x + 2, z + 1], 'y': hh + 1, 'height': 3,
                         'walls': {'white_terracotta': 3, 'stripped_birch_log[axis=y]': 1}, 'door': {'side': 'south', 'lantern': False},
                         'windows': {'every': 2, 'height': 1}, 'light': 0,
                         'roof': {'block': ['dark_oak', 'spruce', 'brick'][len(placed) % 3], 'overhang': 1}})
            b.where = saved
            placed.append((x, z))


# ---------------------------------------------------------------- interiors


def op_shell(b, spec):
    """A room's shell, `from`/`to` [x, y, z] (outer faces, inclusive): `floor`, `walls`, `ceiling` (none for open
    roof), wall `posts` every n, ceiling `beams` every n along `axis`, `windows` like a house's; the inside is air."""
    op = Op(spec, b.where, {'from', 'to', 'floor', 'walls', 'ceiling', 'posts', 'beams', 'windows', 'grain', 'base'})
    (x1, y1, z1), (x2, y2, z2) = op.xyz('from'), op.xyz('to')
    x1, x2, y1, y2, z1, z2 = min(x1, x2), max(x1, x2), min(y1, y2), max(y1, y2), min(z1, z2), max(z1, z2)
    floor = b.mix(op.get('floor', 'spruce_planks'), op.get('grain', 0), 'floor')
    walls = b.mix(op.get('walls', 'spruce_planks'), op.get('grain', 0), 'walls')
    ceiling = op.get('ceiling', 'spruce_planks')
    cmix = b.mix(ceiling, 0, 'ceiling') if ceiling else None
    base = op.get('base')
    for x in range(x1, x2 + 1):
        for z in range(z1, z2 + 1):
            b.put(x, y1, z, floor.pick(x, z))
            if cmix:
                b.put(x, y2, z, cmix.pick(x, z))
            edge = x in (x1, x2) or z in (z1, z2)
            for y in range(y1 + 1, y2 if cmix else y2 + 1):
                if edge:
                    b.put(x, y, z, base if (base and y == y1 + 1) else walls.pick(x, z, y))
                else:
                    b.put(x, y, z, AIR)
    posts = op.get('posts')
    if posts:
        every = int(posts.get('every', 4))
        blk = posts.get('block', 'stripped_spruce_log[axis=y]')
        cols = [(x, z1) for x in range(x1, x2 + 1, every)] + [(x, z2) for x in range(x1, x2 + 1, every)] + \
               [(x1, z) for z in range(z1, z2 + 1, every)] + [(x2, z) for z in range(z1, z2 + 1, every)] + \
               [(x2, z1), (x2, z2), (x1, z2)]
        for x, z in cols:
            for y in range(y1 + 1, y2 if cmix else y2 + 1):
                b.put(x, y, z, blk)
    beams = op.get('beams')
    if beams:
        every = int(beams.get('every', 4))
        blk = beams.get('block', 'stripped_spruce_log')
        axis = beams.get('axis', 'z')
        y = int(beams.get('y', y2 - 1))
        if axis == 'z':
            for x in range(x1 + every, x2, every):
                for z in range(z1 + 1, z2):
                    b.put(x, y, z, f'{blk}[axis=z]' if blk.endswith('_log') else blk)
        else:
            for z in range(z1 + every, z2, every):
                for x in range(x1 + 1, x2):
                    b.put(x, y, z, f'{blk}[axis=x]' if blk.endswith('_log') else blk)
    win = op.get('windows')
    if win:
        every = int(win.get('every', 4))
        ww = int(win.get('width', 1))
        wh = int(win.get('height', 2))
        sill = int(win.get('sill', 2))
        glass = win.get('block', 'glass_pane')
        sides = win.get('sides', ['north', 'east', 'south', 'west'])
        offset = int(win.get('offset', every // 2))
        runs = {'north': [(x, z1) for x in range(x1 + 1, x2)], 'south': [(x, z2) for x in range(x1 + 1, x2)],
                'west': [(x1, z) for z in range(z1 + 1, z2)], 'east': [(x2, z) for z in range(z1 + 1, z2)]}
        for side in sides:
            cells = runs[side]
            for s in range(offset, len(cells) - ww + 1, every):
                for (x, z) in cells[s:s + ww]:
                    for y in range(y1 + sill, y1 + sill + wh):
                        b.put(x, y, z, glass)


# ---------------------------------------------------------------- entities: posters, text, displays


def _face_frame(facing):
    """For a surface facing `facing`: (right, normal) unit vectors in x/z as seen by someone looking at it."""
    return {'south': ((1, 0), (0, 1)), 'north': ((-1, 0), (0, -1)), 'east': ((0, -1), (1, 0)), 'west': ((0, 1), (-1, 0))}[facing]


def _plane_point(origin, facing, u, v, depth):
    """A point on the front face of the wall cell `origin` ([x, y, z], the board's bottom-left as seen from the
    front), `u` blocks right, `v` up and `depth` out from the face."""
    (rx, rz), (nx, nz) = _face_frame(facing)
    ox, oy, oz = origin
    # The bottom-left corner of the front face of that cell, as the viewer sees it.
    fx = ox + (0.5 + 0.5 * nx) - 0.5 * rx
    fz = oz + (0.5 + 0.5 * nz) - 0.5 * rz
    return (fx + rx * u + nx * depth, oy + v, fz + rz * u + nz * depth)


def text_nbt(text, color='white', bold=False, scale=1.0, background=0, shadow=True, line_width=400, align='center',
             brightness=None, facing='south'):
    from .emit import Float
    nbt = {
        'text': {'text': text, 'color': color, **({'bold': True} if bold else {})},
        'background': background,
        'line_width': int(line_width),
        'shadow': bool(shadow),
        'alignment': align,
        'billboard': 'fixed',
        'transformation': {'left_rotation': [Float(0), Float(0), Float(0), Float(1)], 'right_rotation': [Float(0), Float(0), Float(0), Float(1)],
                           'translation': [Float(0), Float(0), Float(0)], 'scale': [Float(scale), Float(scale), Float(scale)]},
    }
    if brightness is not None:
        nbt['brightness'] = {'sky': int(brightness), 'block': int(brightness)}
    return nbt


def op_text(b, spec):
    """Crisp text in the world (a text_display): `text`, `at` ([x, y, z] continuous: the bottom middle of the
    text), `facing` (the side it is read from), `scale`, `color` (name or #rrggbb), `bold`, `background` (ARGB int,
    0 = none), `glow` (full brightness)."""
    op = Op(spec, b.where, {'text', 'at', 'facing', 'scale', 'color', 'bold', 'background', 'glow', 'width', 'shadow'})
    f = op.facing()
    nbt = text_nbt(str(op.req('text')), op.get('color', 'white'), op.get('bold', False), float(op.get('scale', 1)),
                   int(op.get('background', 0)), op.get('shadow', True), int(op.get('width', 400)),
                   brightness=15 if op.get('glow') else None)
    b.entity('minecraft:text_display', op.xyz('at'), nbt, yaw=YAW[f])


def op_display(b, spec):
    """A block shown at any size and place (a block_display): `block`, `from` ([x, y, z] continuous corner) and
    `size` ([sx, sy, sz] blocks), `glow` for full brightness."""
    op = Op(spec, b.where, {'block', 'from', 'size', 'glow'})
    lo = op.xyz('from')
    sx, sy, sz = op.xyz('size')
    nbt = {'brightness': {'sky': 15, 'block': 15}} if op.get('glow') else {}
    b.display_box(op.req('block'), lo, (lo[0] + sx, lo[1] + sy, lo[2] + sz), nbt)


def op_item_frame(b, spec):
    """An item frame on the face of a block: `at` ([x, y, z], the cell the frame sits in, in front of a wall),
    `facing` (out of the wall), `item` (an item id), `glow`, `invisible`, `rotation` (0-7)."""
    op = Op(spec, b.where, {'at', 'facing', 'item', 'glow', 'invisible', 'rotation'})
    x, y, z = op.xyz('at')
    f = op.facing()
    nbt = {'Item': {'id': op.req('item'), 'count': 1}, 'Fixed': True, 'Invisible': bool(op.get('invisible', False)),
           'ItemRotation': _Byte(int(op.get('rotation', 0)))}
    b.entities.append({'type': 'minecraft:glow_item_frame' if op.get('glow') else 'minecraft:item_frame',
                       'pos': (x + 0.5, y + 0.5, z + 0.5), 'yaw': None, 'facing': f, 'nbt': nbt})


class _Byte(int):
    pass


PALETTE = {
    'W': 'white_concrete', 'w': 'white_wool', 'K': 'black_concrete', 'k': 'gray_concrete', 'g': 'light_gray_concrete',
    'R': 'red_concrete', 'r': 'pink_concrete', 'O': 'orange_concrete', 'Y': 'yellow_concrete', 'G': 'gold_block',
    'L': 'lime_concrete', 'E': 'green_concrete', 'C': 'cyan_concrete', 'B': 'blue_concrete', 'b': 'light_blue_concrete',
    'P': 'purple_concrete', 'M': 'magenta_concrete', 'N': 'brown_concrete', 'n': 'brown_terracotta', 'T': 'terracotta',
    'S': 'smooth_sandstone', 'Q': 'quartz_block', 'D': 'dark_oak_planks', 'A': 'snow_block'}


def pixel_rects(rows):
    """Greedy rectangles of equal characters in a grid of strings (top row first): [(char, col, row, w, h)]."""
    grid = [list(r) for r in rows]
    h = len(grid)
    w = max((len(r) for r in grid), default=0)
    for r in grid:
        r.extend(' ' * (w - len(r)))
    used = [[False] * w for _ in range(h)]
    out = []
    for j in range(h):
        for i in range(w):
            c = grid[j][i]
            if c in ' .' or used[j][i]:
                continue
            i2 = i
            while i2 + 1 < w and grid[j][i2 + 1] == c and not used[j][i2 + 1]:
                i2 += 1
            j2 = j
            while j2 + 1 < h and all(grid[j2 + 1][k] == c and not used[j2 + 1][k] for k in range(i, i2 + 1)):
                j2 += 1
            for jj in range(j, j2 + 1):
                for ii in range(i, i2 + 1):
                    used[jj][ii] = True
            out.append((c, i, j, i2 - i + 1, j2 - j + 1))
    return out


def op_poster(b, spec):
    """A poster on a wall: a `board` of blocks `size = [w, h]` (whole blocks) with its bottom-left cell at `at`
    ([x, y, z], left as seen from the front) facing `facing`, a `frame` round it, a `paper` sheet, `art` (pixel
    pictures: `{ rows = ["..WW..", …], at = [u, v] (blocks from the paper's bottom-left), pixel = 0.125, palette }`)
    and `lines` of text (`{ text, at = [u, v], scale, color, bold }`, u is the middle of the line).
    Layers stand off the wall at different depths, so nothing z-fights. `mark = "poster"` exports a straight-on
    camera that fills the frame with the poster at `fov` (40)."""
    op = Op(spec, b.where, {'at', 'facing', 'size', 'board', 'frame', 'paper', 'art', 'lines', 'mark', 'fov', 'glow',
                            'paper_margin', 'center', 'y', 'stand', 'roof'})
    w, h = op.req('size')
    if op.has('center'):
        # Centred on a column (`center`, e.g. along a lane), its bottom row at `y`, facing `facing` ("lane" works).
        cx, cz = op.xz('center')
        f = op.facing(default='south', at='center')
        (rx, rz), (nx, nz) = _face_frame(f)
        x0, y0, z0 = cx - rx * (w // 2), int(op.get('y', 1)), cz - rz * (w // 2)
    else:
        x0, y0, z0 = op.xyz('at')
        f = op.facing()
        (rx, rz), (nx, nz) = _face_frame(f)
    board = op.get('board', 'spruce_planks')
    frame = op.get('frame', 'stripped_dark_oak_log')
    for u in range(-1, w + 1):
        for v in range(-1, h + 1):
            x, z = x0 + rx * u, z0 + rz * u
            edge = u in (-1, w) or v in (-1, h)
            if edge and frame:
                axis = 'y' if u in (-1, w) else ('x' if rx else 'z')
                b.put(x, y0 + v, z, f'{frame}[axis={axis}]' if frame.endswith(('_log', '_wood')) and '[' not in frame else frame)
            elif not edge:
                b.put(x, y0 + v, z, board)
    if op.get('stand'):
        # A free-standing notice board: posts down to the ground either side and a little roof on top.
        post = op.get('stand') if isinstance(op.get('stand'), str) else 'spruce_log'
        roof = op.get('roof', 'dark_oak')
        for u in range(-2, w + 2):
            x, z = x0 + rx * u, z0 + rz * u
            b.put(x, y0 + h + 1, z, f'{roof}_planks')
            b.put(x + nx, y0 + h + 1, z + nz, f'{roof}_stairs[facing={turn_dir(f, 2)},half=bottom]')
            b.put(x - nx, y0 + h + 1, z - nz, f'{roof}_stairs[facing={f},half=bottom]')
        for u in (-1, w):
            x, z = x0 + rx * u, z0 + rz * u
            for y in range(0, y0 - 1):
                b.put(x, y, z, f'{post}[axis=y]' if post.endswith('_log') else post)
    glow = {'brightness': {'sky': 15, 'block': 15}} if op.get('glow') else {}
    paper = op.get('paper', 'white_concrete')
    margin = float(op.get('paper_margin', 0.125))

    def rect(block, u0, v0, u1, v1, depth, thick=0.01):
        p1 = _plane_point((x0, y0, z0), f, u0, v0, depth)
        p2 = _plane_point((x0, y0, z0), f, u1, v1, depth + thick)
        lo = (min(p1[0], p2[0]), min(p1[1], p2[1]), min(p1[2], p2[2]))
        hi = (max(p1[0], p2[0]), max(p1[1], p2[1]), max(p1[2], p2[2]))
        b.display_box(block, lo, hi, glow)

    if paper:
        rect(paper, margin, margin, w - margin, h - margin, 0.01)
    for a, art in enumerate(op.get('art', [])):
        rows = art['rows']
        px = float(art.get('pixel', 0.125))
        au, av = art.get('at', [0.5, 0.5])
        palette = {**PALETTE, **art.get('palette', {})}
        n = len(rows)
        for c, i, j, rw, rh in pixel_rects(rows):
            if c not in palette:
                raise SetError(f'{b.where}: art[{a}] uses "{c}", which is not in the palette ({"".join(sorted(palette))})')
            u0 = au + i * px
            v0 = av + (n - j - rh) * px
            rect(palette[c], u0, v0, u0 + rw * px, v0 + rh * px, 0.03 + 0.002 * a)
    for line in op.get('lines', []):
        u, v = line.get('at', [w / 2, h / 2])
        pos = _plane_point((x0, y0, z0), f, u, v, 0.06)
        nbt = text_nbt(line['text'], line.get('color', 'black'), line.get('bold', False), float(line.get('scale', 1)),
                       0, line.get('shadow', False), int(line.get('width', 400)), brightness=15 if op.get('glow') else None)
        b.entity('minecraft:text_display', pos, nbt, yaw=YAW[f])
    name = op.get('mark')
    if name:
        fov = float(op.get('fov', 40))
        # Far enough out that the board and its frame fill about 90% of the frame's height.
        dist = (h + 2) / 0.9 / 2 / math.tan(math.radians(fov) / 2)
        c = _plane_point((x0, y0, z0), f, w / 2, h / 2, 0)
        eye = (c[0] + nx * dist, c[1], c[2] + nz * dist)
        b.add_mark(name, {'kind': 'camera', 'eye': eye, 'look': c, 'fov': fov})


def op_entity(b, spec):
    """Any entity: `type`, `at` ([x, y, z] continuous), `yaw`, `nbt` (a table, written as SNBT)."""
    op = Op(spec, b.where, {'type', 'at', 'yaw', 'nbt'})
    b.entity(op.req('type'), op.xyz('at'), op.get('nbt', {}), yaw=op.get('yaw'))


def op_part(b, spec):
    """Places a `[[part]]` defined in this file: `name`, `at` ([x, y, z] or [x, z]), `rotate` (0/90/180/270),
    `mirror`, `seed` (a different seed gives the part's mixes and trees a different look)."""
    op = Op(spec, b.where, {'name', 'at', 'rotate', 'mirror', 'seed', 'facing'})
    name = op.req('name')
    if name not in b.parts:
        raise SetError(f'{b.where}: no part "{name}"; parts: {", ".join(sorted(b.parts)) or "none"}')
    from .model import quarters_of
    at = op.get('at')
    if not isinstance(at, list) or len(at) not in (2, 3):
        raise SetError(f'{b.where}: `at` is [x, z] or [x, y, z]')
    x, y, z = (at[0], 0, at[1]) if len(at) == 2 else at
    q = FACING_QUARTERS[op.facing()] if op.has('facing') else quarters_of(op.get('rotate', 0))
    part = Builder(b.name, int(op.get('seed', b.seed + 17 * b.n)), b.parts, f'{b.where} part {name}')
    part.run(b.parts[name], f'part {name}.build')
    b.grid.stamp(part.grid, (int(x), int(y), int(z)), q, bool(op.get('mirror', False)))
    for e in part.entities:
        b.entities.append(transform_entity(e, q, bool(op.get('mirror', False)), (int(x), int(y), int(z))))


# ---------------------------------------------------------------- dressing along a lane

KERB = {'lamp', 'barrels', 'crates', 'planter', 'pots', 'hay', 'pumpkins', 'fence', 'banner', 'bench', 'bush',
        'woodpile', 'sacks', 'lantern', 'tallflowers'}
FLOWERS = {'poppy': 2, 'dandelion': 2, 'cornflower': 1, 'allium': 1, 'red_tulip': 1, 'orange_tulip': 1,
           'pink_tulip': 1, 'oxeye_daisy': 1, 'azure_bluet': 1, 'blue_orchid': 1}
POTTED = {'potted_poppy': 2, 'potted_dandelion': 2, 'potted_red_tulip': 1, 'potted_blue_orchid': 1,
          'potted_allium': 1, 'potted_azure_bluet': 1, 'potted_cornflower': 1, 'potted_fern': 1}
BANNERS = ['red', 'yellow', 'blue', 'lime', 'orange', 'white', 'light_blue', 'magenta']


def _kerb_prop(b, kind, f, r, o):
    """One kerb prop as [(u, y, v, block)]: u along the lane, v away from it (0 is the kerb line), facing `f` (the
    lane). `r` is a seeded number per prop; `o` the op's options."""
    t = turn_dir(f, 1)
    away = turn_dir(f, 2)
    ax = 'x' if t in ('east', 'west') else 'z'
    wood = o['wood']
    pick = lambda mix, k: mix.pick(int(r * 9973) + k, k * 7)  # noqa: E731
    out = []
    if kind == 'lamp':
        h = o['lamp_height']
        out.append((0, 0, 0, 'cobblestone_wall'))
        out += [(0, y, 0, f'{wood}_fence') for y in range(1, h + 1)]
        out += [(0, h, -1, f'{wood}_fence'), (0, h - 1, -1, 'lantern[hanging=true]')]
    elif kind == 'barrels':
        out.append((0, 0, 0, 'barrel[facing=up]'))
        if r < 0.5:
            out.append((1, 0, 0, f'barrel[facing={f}]'))
        if r > 0.35:
            out.append((0, 1, 0, 'barrel[facing=up]' if r > 0.7 else 'lantern[hanging=false]'))
    elif kind == 'crates':
        out += [(0, 0, 0, f'barrel[facing={t}]'), (1, 0, 0, f'stripped_{wood}_wood'), (0, 1, 0, f'barrel[facing={t}]')]
        out.append((1, 1, 0, pick(o['potted'], 1)))
    elif kind == 'planter':
        n = 2 if r < 0.5 else 3
        for u in range(n):
            out += [(u, 0, 0, 'rooted_dirt'), (u, 1, 0, pick(o['flowers'], u)),
                    (u, 0, -1, f'{wood}_trapdoor[facing={f},half=bottom,open=true]')]
        out += [(-1, 0, 0, f'{wood}_trapdoor[facing={turn_dir(t, 2)},half=bottom,open=true]'),
                (n, 0, 0, f'{wood}_trapdoor[facing={t},half=bottom,open=true]')]
    elif kind == 'pots':
        out += [(0, 0, 0, pick(o['potted'], 0))]
        if r < 0.6:
            out.append((1, 0, 0, pick(o['potted'], 1)))
    elif kind == 'hay':
        out += [(0, 0, 0, f'hay_block[axis={ax}]'), (1, 0, 0, 'hay_block[axis=y]')]
        out.append((0, 1, 0, 'hay_block[axis=y]' if r < 0.5 else f'carved_pumpkin[facing={f}]'))
    elif kind == 'pumpkins':
        out += [(0, 0, 0, 'pumpkin'), (1, 0, 0, 'melon' if r < 0.4 else f'carved_pumpkin[facing={f}]')]
        if r > 0.5:
            out.append((-1, 0, 0, 'pumpkin'))
    elif kind == 'fence':
        out += [(u, 0, 0, f'{wood}_fence') for u in range(-1, 2)]
        if r < 0.4:
            out.append((1, 1, 0, 'lantern[hanging=false]'))
    elif kind == 'banner':
        out += [(0, y, 0, f'stripped_{wood}_log[axis=y]') for y in range(3)]
        colours = o['colors']
        c1, c2 = colours[int(r * len(colours)) % len(colours)], colours[int(r * 7 * len(colours)) % len(colours)]
        out += [(1, 2, 0, f'{c1}_wall_banner[facing={t}]'), (-1, 2, 0, f'{c2}_wall_banner[facing={turn_dir(t, 2)}]'),
                (0, 3, 0, 'lantern[hanging=false]')]
    elif kind == 'bench':
        out += [(0, 0, 0, f'{wood}_stairs[facing={away},half=bottom]'), (1, 0, 0, f'{wood}_stairs[facing={away},half=bottom]'),
                (-1, 0, 0, f'{wood}_trapdoor[facing={turn_dir(t, 2)},half=bottom,open=true]'),
                (2, 0, 0, f'{wood}_trapdoor[facing={t},half=bottom,open=true]')]
    elif kind == 'bush':
        leaves = 'flowering_azalea_leaves' if r < 0.5 else 'azalea_leaves'
        out += [(0, 0, 0, leaves), (1, 0, 0, leaves), (0, 0, 1, leaves)]
        if r > 0.3:
            out.append((0, 1, 0, leaves))
    elif kind == 'woodpile':
        log = f'{wood}_log[axis={ax}]'
        out += [(0, 0, 0, log), (1, 0, 0, log), (0, 1, 0, log)]
    elif kind == 'sacks':
        out += [(0, 0, 0, 'brown_wool'), (0, 1, 0, 'white_wool' if r < 0.5 else 'light_gray_wool'), (1, 0, 0, 'brown_wool')]
    elif kind == 'tallflowers':
        tall = ['sunflower', 'sunflower', 'rose_bush', 'lilac', 'peony']
        out += [(u, 0, 0, tall[int(r * 31 + u * 7) % len(tall)]) for u in range(-1, 2)]
    elif kind == 'lantern':
        out += [(0, 0, 0, f'stripped_{wood}_wood'), (0, 1, 0, 'lantern[hanging=false]')]
    return out


def op_kerb(b, spec):
    """Dressing right at the lane's edges, so a low lens walking the lane always has things beside it.

    `along` (the lane mark, default "lane"), `from`/`to` (blocks along it), `side` (blocks from the centre line to the
    kerb line, default 4), `sides` ("both", "left", "right"), a prop every `every` blocks (3) with seeded jitter,
    drawn from `props` (a mix of kinds: lamp, barrels, crates, planter, pots, hay, pumpkins, fence, banner, bench,
    bush, woodpile, sacks, lantern, tallflowers), and a lantern post every `lamps` blocks (0: none) alternating sides. Props are
    turned to face the lane and skipped where anything already stands (place stalls and houses first).
    `wood` (spruce), `colors` (banner colours), `flowers` and `potted` (mixes), `lamp_height` (4)."""
    op = Op(spec, b.where, {'along', 'from', 'to', 'side', 'sides', 'every', 'props', 'lamps', 'lamp_height', 'wood',
                            'colors', 'flowers', 'potted', 'chance'})
    lane = op.get('along', 'lane')
    spine = b.spine(lane, b.where)
    d1, d2 = float(op.get('from', 0)), float(op.get('to', spine[-1][2]))
    side = float(op.get('side', 4))
    sides = {'both': (-1, 1), 'left': (-1,), 'right': (1,)}.get(op.get('sides', 'both'))
    if sides is None:
        raise SetError(f'{b.where}: sides is both, left or right')
    every = float(op.get('every', 3))
    props = b.mix(op.get('props', {'barrels': 2, 'planter': 2, 'crates': 1, 'pots': 1, 'banner': 1, 'bench': 1}), 0, 'kerb')
    for name, _ in props.entries:
        if name not in KERB:
            raise SetError(f'{b.where}: unknown kerb prop "{name}"; known: {", ".join(sorted(KERB))}')
    o = {'wood': op.get('wood', 'spruce'), 'lamp_height': int(op.get('lamp_height', 4)),
         'colors': op.get('colors', BANNERS), 'flowers': b.mix(op.get('flowers', FLOWERS), 0, 'kflowers'),
         'potted': b.mix(op.get('potted', POTTED), 0, 'kpots')}
    chance = float(op.get('chance', 1.0))
    spots = []
    lamps = float(op.get('lamps', 0))
    if lamps:
        k, d = 0, d1 + lamps / 2
        while d <= d2:
            sg = sides[k % len(sides)]
            spots.append((d, sg, 'lamp'))
            k, d = k + 1, d + lamps
    for sg in sides:
        d = d1 + (every / 2 if sg > 0 else 0)
        i = 0
        while d <= d2:
            r = b.rand(int(d * 10), sg, 5)
            if r < chance:
                spots.append((d + (b.rand(int(d * 10), sg, 6) - 0.5) * every * 0.5, sg, None))
            d += every
            i += 1
    for d, sg, kind in spots:
        x, z = b.along({'along': lane, 'd': d, 'side': side * sg}, b.where)
        x, z = math.floor(x), math.floor(z)
        f = b.toward_lane(x + 0.5, z + 0.5, b.where)
        r = b.rand(x, z, 41)
        kind = kind or props.pick(x, z, int(d))
        t, away = STEP[turn_dir(f, 1)], STEP[turn_dir(f, 2)]
        cells = [(x + t[0] * u + away[0] * v, y, z + t[1] * u + away[1] * v, blk) for u, y, v, blk in _kerb_prop(b, kind, f, r, o)]
        ok = True
        for cx, cy, cz, _ in cells:
            if b.grid.has(cx, cy, cz) and b.grid.get(cx, cy, cz).id not in PLANTS:
                ok = False
                break
            if cy == 0:
                g = b.grid.get(cx, -1, cz)
                if g is None or g.id in ('water', 'air') or g.id.endswith(('_planks', '_slab')):
                    ok = False
                    break
        if not ok:
            continue
        for cx, cy, cz, blk in cells:
            b.put(cx, cy, cz, blk)


def op_bunting(b, spec):
    """Strings of little flags across a lane, from post to post: at `d` (a list of distances along `along`), between
    poles `side` blocks either side of the centre line (4.5), `height` (5) at the poles, sagging `sag` (0.8) in the
    middle, flags of `colors` (wool) every `spacing` (0.6). Flags are block displays facing along the lane, so a lens
    looking down the lane sees them face on. Poles are `pole` (spruce_fence) on a `base` (cobblestone_wall), and are
    skipped where something already stands (a lamp post or a stall post can hold the string). Or, anywhere (indoors),
    `strings = [[[x, y, z], [x, y, z]], …]`: each string between two points, no poles."""
    op = Op(spec, b.where, {'along', 'd', 'side', 'height', 'sag', 'colors', 'spacing', 'pole', 'base', 'string', 'strings'})
    side = float(op.get('side', 4.5))
    h = int(op.get('height', 5))
    sag = float(op.get('sag', 0.8))
    colours = op.get('colors', ['red_wool', 'yellow_wool', 'blue_wool', 'white_wool', 'lime_wool', 'orange_wool'])
    spacing = float(op.get('spacing', 0.6))
    pole = op.get('pole', 'spruce_fence')
    base = op.get('base', 'cobblestone_wall')
    string = op.get('string', 'brown_wool')
    if op.has('strings'):
        # Indoors or anywhere: `strings = [[[x, y, z], [x, y, z]], …]`, each string's two ends (continuous points).
        for n, (a, c) in enumerate(op.get('strings')):
            _flags(b, tuple(a), tuple(c), n, sag, colours, spacing, string)
        return
    lane = op.get('along', 'lane')
    for n, d in enumerate(op.req('d')):
        ends = []
        for sg in (-1, 1):
            x, z = b.along({'along': lane, 'd': d, 'side': side * sg}, b.where)
            cx, cz = math.floor(x), math.floor(z)
            if not b.grid.has(cx, 0, cz):
                b.put(cx, 0, cz, base)
                for y in range(1, h + 1):
                    b.put(cx, y, cz, pole)
            else:
                for y in range(1, h + 1):
                    if not b.grid.has(cx, y, cz):
                        b.put(cx, y, cz, pole)
            ends.append((cx + 0.5, h + 0.75, cz + 0.5))
        _flags(b, ends[0], ends[1], n, sag, colours, spacing, string)


def _flags(b, a, c, n, sag, colours, spacing, string):
    """One string of flags from point `a` to point `c` (block displays lit by the world where they hang)."""
    (x1, y1, z1), (x2, y2, z2) = a, c
    span = math.dist((x1, z1), (x2, z2))
    steps = max(2, int(span / spacing))
    thin_x = abs(x2 - x1) < abs(z2 - z1)  # the string runs mostly along z: flags are thin in x
    for k in range(1, steps):
        t = k / steps
        px, pz = x1 + (x2 - x1) * t, z1 + (z2 - z1) * t
        py = y1 + (y2 - y1) * t - sag * 4 * t * (1 - t)
        flag = colours[(k + n) % len(colours)]
        if string:
            # The string: a thin piece from this flag halfway to the last one.
            qx, qz = x1 + (x2 - x1) * (k - 0.5) / steps, z1 + (z2 - z1) * (k - 0.5) / steps
            b.display_box(string, [min(px, qx) - (0.015 if thin_x else 0), py, min(pz, qz) - (0 if thin_x else 0.015)],
                          [max(px, qx) + (0.015 if thin_x else 0), py + 0.03, max(pz, qz) + (0 if thin_x else 0.015)])
        for w, hh, dy in ((0.36, 0.2, 0.0), (0.2, 0.18, 0.2)):
            lo = [px - (0.02 if thin_x else w / 2), py - dy - hh, pz - (w / 2 if thin_x else 0.02)]
            hi = [px + (0.02 if thin_x else w / 2), py - dy, pz + (w / 2 if thin_x else 0.02)]
            b.display_box(flag, lo, hi)


OPS = {
    'ground': op_ground, 'paint': op_paint, 'lane': op_lane, 'crossing': op_crossing, 'stream': op_stream, 'bridge': op_bridge,
    'box': op_box, 'carve': op_carve, 'blocks': op_blocks, 'column': op_column, 'house': op_house, 'roof': op_roof,
    'stall': op_stall, 'fence': op_fence, 'lamp': op_lamp, 'tree': op_tree, 'bush': op_bush, 'scatter': op_scatter,
    'crops': op_crops, 'pile': op_pile, 'well': op_well, 'cart': op_cart, 'pots': op_pots, 'light': op_light,
    'backdrop': op_backdrop, 'shell': op_shell, 'text': op_text, 'display': op_display, 'item_frame': op_item_frame,
    'poster': op_poster, 'entity': op_entity, 'part': op_part,
    'kerb': op_kerb, 'bunting': op_bunting,
}
