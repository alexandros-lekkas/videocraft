"""Sets: places to film, written as data (sets/<name>.toml), built by code into vanilla commands, with named marks.

    built = build(load('market-lane'))                 # set coordinates: grid, entities, marks
    placed = place(built, at=(0, 160, 0), rotate=90)   # world coordinates: commands, anchors, paths, views

The format is docs/SETS.md. A set is a self-contained island: its own ground plate and backdrop, so the natural
world never shows, placeable anywhere (by default at y 230, above the clouds). Nothing here touches a game; the commands are
staged by the take (`[[world.set]]` in a script, see expand.py).
"""
import math
import tomllib
from pathlib import Path

from . import emit, shapes
from .model import Grid, quarters_of, turn_cell, turn_point, turn_yaw, turn_dir
from .ops import Builder, SetError, YAW, FACING_QUARTERS, transform_entity  # noqa: F401  (re-exported)

ROOT = Path(__file__).resolve().parents[3]
SETS_DIR = ROOT / 'sets'
TOP = {'name', 'description', 'time', 'weather', 'biome', 'seed', 'clear', 'headroom', 'part', 'build', 'mark',
       'preview', 'tags', 'kind'}
MARK = {'name', 'at', 'facing', 'path', 'along', 'from', 'to', 'offset', 'reverse', 'eye', 'look', 'fov', 'note', 'y',
        'preview'}
# Above the cloud layer (y 192): no clouds slab overhead, and below the horizon only the set's own backdrop shows.
DEFAULT_AT = (0, 230, 0)


def find(name):
    """A set by name (sets/<name>.toml) or by path."""
    p = Path(name)
    if p.suffix == '.toml' and p.exists():
        return p
    cand = SETS_DIR / f'{name}.toml'
    if cand.exists():
        return cand
    known = ', '.join(sorted(q.stem for q in SETS_DIR.glob('*.toml'))) if SETS_DIR.exists() else 'none'
    raise SetError(f'no set "{name}" (looked for {cand}); sets: {known}')


def load(name):
    path = find(name)
    try:
        raw = tomllib.loads(path.read_text(encoding='utf-8'))
    except tomllib.TOMLDecodeError as e:
        raise SetError(f'{path}: {e}') from e
    raw.setdefault('name', path.stem)
    raw['_path'] = str(path)
    return raw


def listing():
    out = []
    for p in sorted(SETS_DIR.glob('*.toml')) if SETS_DIR.exists() else []:
        try:
            raw = load(str(p))
            out.append({'name': raw['name'], 'description': raw.get('description', ''), 'time': raw.get('time'),
                        'path': str(p), 'marks': len(raw.get('mark', []))})
        except SetError as e:
            out.append({'name': p.stem, 'error': str(e), 'path': str(p)})
    return out


class Built:
    """A set in its own coordinates."""

    def __init__(self, raw, grid, entities, marks, warnings):
        self.raw, self.grid, self.entities, self.marks, self.warnings = raw, grid, entities, marks, warnings
        self.name = raw['name']
        self.time = int(raw.get('time', 6000))
        self.weather = raw.get('weather', 'clear')
        self.biome = raw.get('biome')
        self.clear = bool(raw.get('clear', True))
        self.headroom = int(raw.get('headroom', 12))


def build(raw):
    """Runs a set's build entries and marks. Raises SetError naming the entry."""
    if not isinstance(raw, dict):
        raise SetError('a set is a table')
    name = raw.get('name', '?')
    extra = sorted(set(raw) - TOP - {'_path'})
    if extra:
        raise SetError(f'set {name}: unknown key(s) {", ".join(extra)}; allowed: {", ".join(sorted(TOP))}')
    parts = {}
    for i, part in enumerate(raw.get('part', [])):
        if 'name' not in part:
            raise SetError(f'set {name}: part[{i}] needs a name')
        parts[part['name']] = part.get('build', [])
    b = Builder(name, int(raw.get('seed', 1)), parts)
    b.run(raw.get('build', []), f'set {name}: build')
    shapes.finish(b.grid)
    for i, spec in enumerate(raw.get('mark', [])):
        _mark(b, spec, f'set {name}: mark[{i}]')
    warnings = []
    floating = shapes.supported(b.grid, drop_leaves=12)
    for count, cell in floating[:10]:
        warnings.append(f'{count} floating block(s) not joined to the ground, e.g. at {list(cell)} ({b.grid.get(*cell)})')
    return Built(raw, b.grid, b.entities, b.marks, warnings)


def _p(v, where, key):
    if not (isinstance(v, (list, tuple)) and len(v) in (2, 3) and all(isinstance(c, (int, float)) for c in v)):
        raise SetError(f'{where}: `{key}` is [x, y, z] (or [x, z] at feet level)')
    return (v[0] + 0.5, 0.0, v[1] + 0.5) if len(v) == 2 else (v[0] + 0.5, float(v[1]), v[2] + 0.5)


def _mark(b, spec, where):
    extra = sorted(set(spec) - MARK)
    if extra:
        raise SetError(f'{where}: unknown key(s) {", ".join(extra)}; allowed: {", ".join(sorted(MARK))}')
    name = spec.get('name')
    if not name or not isinstance(name, str):
        raise SetError(f'{where}: a mark needs a `name`')
    where = f'{where} "{name}"'
    preview = spec.get('preview', True)
    if 'eye' in spec:
        eye = _p(spec['eye'], where, 'eye')
        look = spec.get('look')
        if isinstance(look, str):
            if look not in b.marks:
                raise SetError(f'{where}: look = "{look}" is not a mark defined above')
            m = b.marks[look]
            look = m['at'] if m['kind'] == 'point' else m['points'][0] if m['kind'] == 'path' else m['eye']
        else:
            look = _p(look, where, 'look')
        b.add_mark(name, {'kind': 'camera', 'eye': eye, 'look': tuple(look), 'fov': float(spec.get('fov', 70)), 'preview': preview})
    elif 'path' in spec:
        pts = [_p(p, where, 'path') for p in spec['path']]
        b.add_mark(name, {'kind': 'path', 'points': pts, 'preview': preview})
    elif 'along' in spec:
        lane = spec['along']
        if lane not in b.spines:
            raise SetError(f'{where}: along = "{lane}" is not a lane with a mark; lanes: {", ".join(sorted(b.spines)) or "none"}')
        spine = b.spines[lane]
        total = spine[-1][2]
        d1, d2 = float(spec.get('from', 0)), float(spec.get('to', total))
        if not (0 <= d1 < d2 <= total + 1e-6):
            raise SetError(f'{where}: from/to must be within the lane (0 to {total:.1f} blocks along) and from < to')
        off = float(spec.get('offset', 0))
        y = float(spec.get('y', 0))
        pts = []
        for i, (x, z, d) in enumerate(spine):
            if d1 - 1e-6 <= d <= d2 + 1e-6:
                j = min(i + 1, len(spine) - 1)
                tx, tz = spine[j][0] - spine[max(0, j - 1)][0], spine[j][1] - spine[max(0, j - 1)][1]
                n = math.hypot(tx, tz) or 1
                # offset > 0 is to the right of the direction of travel along the lane (from its first point).
                pts.append((x - tz / n * off, y, z + tx / n * off))
        pts = pts[::4] + ([pts[-1]] if (len(pts) - 1) % 4 else [])
        if spec.get('reverse'):
            pts.reverse()
        b.add_mark(name, {'kind': 'path', 'points': pts, 'preview': preview})
    elif 'at' in spec:
        at = _p(spec['at'], where, 'at')
        facing = spec.get('facing')
        yaw = YAW[facing] if isinstance(facing, str) and facing in YAW else (float(facing) if isinstance(facing, (int, float)) else None)
        if isinstance(facing, str) and facing not in YAW:
            raise SetError(f'{where}: facing is north, east, south, west or a yaw in degrees')
        b.add_mark(name, {'kind': 'point', 'at': at, 'yaw': yaw, 'preview': preview})
    else:
        raise SetError(f'{where}: a mark is a point (`at`), a path (`path` or `along`), or a camera (`eye`, `look`)')


class Placed:
    """A built set put into a world: commands in order, the bounding box, and every mark in world coordinates."""

    def __init__(self, built, at, quarters, mirror):
        self.built, self.at, self.quarters, self.mirror = built, tuple(int(c) for c in at), quarters, mirror
        X, Y, Z = self.at
        cells = {}
        for (x, y, z), s in built.grid.cells.items():
            tx, tz = turn_cell(x, z, quarters, mirror)
            cells[(tx + X, y + Y, tz + Z)] = s.turned(quarters, mirror) if (quarters or mirror) else s
        self.cells = cells
        self.entities = [transform_entity(e, quarters, mirror, self.at) for e in built.entities]
        (x1, y1, z1), (x2, y2, z2) = Grid.bounds(type('G', (), {'cells': cells})())
        self.lo, self.hi = (x1, y1, z1), (x2, y2 + built.headroom, z2)
        self.marks = {k: self._mark(m) for k, m in built.marks.items()}

    def point(self, p):
        x, y, z = p
        tx, tz = turn_point(x, z, self.quarters, self.mirror)
        return (round(tx + self.at[0], 4), round(y + self.at[1], 4), round(tz + self.at[2], 4))

    def _mark(self, m):
        m = dict(m)
        if m['kind'] == 'point':
            m['at'] = self.point(m['at'])
            if m.get('yaw') is not None:
                m['yaw'] = turn_yaw(m['yaw'], self.quarters, self.mirror)
        elif m['kind'] == 'path':
            m['points'] = [self.point(p) for p in m['points']]
        else:
            m['eye'], m['look'] = self.point(m['eye']), self.point(m['look'])
        return m

    # ---- commands ----

    def block_commands(self):
        if getattr(self, '_blocks', None) is None:
            cells = self.cells
            if self.built.clear:
                # After clearing, air is already there: an air fill would change nothing, and a fill that changes
                # nothing is a failed command.
                cells = {k: v for k, v in cells.items() if v.name != 'minecraft:air'}
            self._blocks = emit.block_commands(cells)
        return self._blocks

    def entity_commands(self):
        out = []
        for e in self.entities:
            out.append(emit.summon_command(_entity_nbt(e)))
        return out

    def commands(self):
        """Everything, in staging order: forceload, biome, clear, blocks, entities (last)."""
        return self.prepare_commands() + self.build_commands() + self.entity_commands()

    def prepare_commands(self):
        return emit.forceload_commands(self.lo, self.hi)

    def build_commands(self):
        out = []
        if self.built.biome:
            out += emit.biome_commands(self.lo, self.hi, self.built.biome)
        if self.built.clear:
            out += emit.clear_commands(self.lo, self.hi)
        out += self.block_commands()
        return out

    def anchors(self, prefix):
        """{"<set>:<mark>": [x, y, z]}: a point's position, a path's first point, a camera's eye (and `.look`)."""
        out = {}
        for k, m in self.marks.items():
            if m['kind'] == 'point':
                out[f'{prefix}:{k}'] = list(m['at'])
            elif m['kind'] == 'path':
                out[f'{prefix}:{k}'] = list(m['points'][0])
                out[f'{prefix}:{k}.end'] = list(m['points'][-1])
            else:
                out[f'{prefix}:{k}'] = list(m['eye'])
                out[f'{prefix}:{k}.look'] = list(m['look'])
        return out

    def summary(self):
        from collections import Counter
        blocks = self.block_commands()
        kinds = Counter(c.split(' ', 1)[0] for c in blocks)
        return {
            'name': self.built.name, 'at': list(self.at), 'rotate': self.quarters * 90, 'mirror': self.mirror,
            'blocks': len(self.cells), 'entities': len(self.entities),
            'commands': {'forceload': len(self.prepare_commands()), 'fill': kinds.get('fill', 0),
                         'setblock': kinds.get('setblock', 0), 'summon': len(self.entities),
                         'total': len(self.commands())},
            'box': {'from': list(self.lo), 'to': list(self.hi)},
            'size': [self.hi[0] - self.lo[0] + 1, self.hi[1] - self.lo[1] + 1, self.hi[2] - self.lo[2] + 1],
            'time': self.built.time, 'weather': self.built.weather, 'biome': self.built.biome,
            'marks': {k: m['kind'] for k, m in sorted(self.marks.items())},
            'warnings': self.built.warnings,
        }


def _entity_nbt(e):
    from .emit import Float, Raw
    e = dict(e)
    nbt = dict(e.get('nbt') or {})
    if 'box' in e:
        (lx, ly, lz), (hx, hy, hz) = e['box']
        state = e['block']
        nbt['block_state'] = state.text  # 26.3 reads a block state string here ("minecraft:oak_stairs[facing=east]")
        nbt['transformation'] = {'left_rotation': [Float(0), Float(0), Float(0), Float(1)],
                                 'right_rotation': [Float(0), Float(0), Float(0), Float(1)],
                                 'translation': [Float(0), Float(0), Float(0)],
                                 'scale': [Float(round(hx - lx, 5)), Float(round(hy - ly, 5)), Float(round(hz - lz, 5))]}
        return {'type': 'minecraft:block_display', 'pos': (round(lx, 5), round(ly, 5), round(lz, 5)), 'nbt': nbt}
    if e.get('yaw') is not None:
        nbt['Rotation'] = [Float(e['yaw']), Float(0)]
    if e.get('facing'):
        nbt['Facing'] = Raw(f'{ {"down": 0, "up": 1, "north": 2, "south": 3, "west": 4, "east": 5}[e["facing"]] }b'.replace(' ', ''))
    for k, v in list(nbt.items()):
        if type(v).__name__ == '_Byte':
            nbt[k] = Raw(f'{int(v)}b')
    return {'type': e['type'], 'pos': e['pos'], 'nbt': nbt}


def place(built, at=DEFAULT_AT, rotate=0, mirror=False):
    if not (isinstance(at, (list, tuple)) and len(at) == 3):
        raise SetError(f'set {built.name}: at = [x, y, z] (got {at!r})')
    return Placed(built, at, quarters_of(rotate), bool(mirror))
