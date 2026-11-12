"""The set's voxel model: block states, the grid they sit in, and how both turn and mirror.

Coordinates are the set's own: x east, y up, z south, in whole blocks. Layer y = 0 is where feet stand, so the ground
is at y = -1. A cell (x, y, z) spans [x, x+1] x [y, y+1] x [z, z+1]; continuous points (entities, marks) use the
same axes, so the middle of the floor of cell (3, 0, 5) is the point (3.5, 0, 5.5).

Turns are clockwise seen from above, in quarter turns, like vanilla's Rotation.CLOCKWISE_90 (north becomes east).
A mirror flips x (east and west swap) before the turn.
"""
import re

HORIZONTAL = ('north', 'east', 'south', 'west')
STATE = re.compile(r'^([a-z0-9_:.\-/]+)(?:\[(.*)\])?$')


class BlockState:
    """An immutable block state: a namespaced id and its properties. Parsed once; compared and hashed by text."""
    __slots__ = ('name', 'props', 'text')

    def __init__(self, name, props=None):
        if ':' not in name:
            name = 'minecraft:' + name
        self.name = name
        self.props = dict(props or {})
        self.text = name + ('[' + ','.join(f'{k}={v}' for k, v in sorted(self.props.items())) + ']' if self.props else '')

    @staticmethod
    def parse(text):
        if isinstance(text, BlockState):
            return text
        m = STATE.match(str(text).strip())
        if not m:
            raise ValueError(f'not a block state: {text!r} (expected "oak_stairs[facing=east,half=bottom]")')
        props = {}
        if m.group(2):
            for part in m.group(2).split(','):
                if part.strip():
                    k, _, v = part.partition('=')
                    if not _:
                        raise ValueError(f'block state {text!r}: property {part!r} is not key=value')
                    props[k.strip()] = v.strip()
        return BlockState(m.group(1), props)

    @property
    def id(self):
        return self.name.split(':', 1)[1]

    def with_props(self, **props):
        p = dict(self.props)
        for k, v in props.items():
            if v is None:
                p.pop(k, None)
            else:
                p[k] = str(v).lower() if isinstance(v, bool) else str(v)
        return BlockState(self.name, p)

    def turned(self, quarters, mirror=False):
        """This state after the set is mirrored (x) and then turned clockwise by quarter turns."""
        p = dict(self.props)
        if mirror:
            p = _mirror_props(p, self.id)
        for _ in range(quarters % 4):
            p = _turn_props(p)
        return BlockState(self.name, p)

    def __eq__(self, other):
        return isinstance(other, BlockState) and other.text == self.text

    def __hash__(self):
        return hash(self.text)

    def __repr__(self):
        return self.text


AIR = BlockState('air')


def turn_dir(d, quarters=1, mirror=False):
    if d in HORIZONTAL:
        if mirror and d in ('east', 'west'):
            d = 'west' if d == 'east' else 'east'
        return HORIZONTAL[(HORIZONTAL.index(d) + quarters) % 4]
    return d


def _turn_props(p):
    """One clockwise quarter turn of a property map."""
    out = dict(p)
    for key in ('facing', 'horizontal_facing', 'orientation_facing'):
        if p.get(key) in HORIZONTAL:
            out[key] = turn_dir(p[key])
    if p.get('axis') in ('x', 'z'):
        out['axis'] = 'z' if p['axis'] == 'x' else 'x'
    if 'rotation' in p and p['rotation'].isdigit():
        out['rotation'] = str((int(p['rotation']) + 4) % 16)
    # Connections (fences, walls, panes, vines, mushroom blocks): north's value moves to east, and so on round.
    if any(d in p for d in HORIZONTAL):
        for d in HORIZONTAL:
            out.pop(d, None)
        for i, d in enumerate(HORIZONTAL):
            if d in p:
                out[HORIZONTAL[(i + 1) % 4]] = p[d]
    if 'orientation' in p:  # jigsaw/crafter style "north_up"
        a, _, b = p['orientation'].partition('_')
        out['orientation'] = f'{turn_dir(a)}_{turn_dir(b)}'
    return out


def _mirror_props(p, block_id):
    """Mirror in x: east and west swap; handed shapes (stairs corners, door hinges) swap sides."""
    out = dict(p)
    for key in ('facing', 'horizontal_facing'):
        if p.get(key) in ('east', 'west'):
            out[key] = 'west' if p[key] == 'east' else 'east'
    if 'rotation' in p and p['rotation'].isdigit():
        out['rotation'] = str((16 - int(p['rotation'])) % 16)
    if 'east' in p or 'west' in p:
        out.pop('east', None)
        out.pop('west', None)
        if 'west' in p:
            out['east'] = p['west']
        if 'east' in p:
            out['west'] = p['east']
    if p.get('hinge') in ('left', 'right'):
        out['hinge'] = 'right' if p['hinge'] == 'left' else 'left'
    if p.get('shape', '').endswith(('_left', '_right')):
        s = p['shape']
        out['shape'] = s[:-5] + '_right' if s.endswith('_left') else s[:-6] + '_left'
    if p.get('type') in ('left', 'right') and 'chest' in block_id:
        out['type'] = 'right' if p['type'] == 'left' else 'left'
    return out


def turn_cell(x, z, quarters, mirror=False):
    """Where cell (x, z) goes: mirrored in x, then turned clockwise. Cells map to cells (a cell has a size)."""
    if mirror:
        x = -x - 1
    for _ in range(quarters % 4):
        x, z = -z - 1, x
    return x, z


def turn_point(x, z, quarters, mirror=False):
    """Where the continuous point (x, z) goes."""
    if mirror:
        x = -x
    for _ in range(quarters % 4):
        x, z = -z, x
    return x, z


def turn_yaw(yaw, quarters, mirror=False):
    """Minecraft yaw (0 = facing south, 90 = west, 180 = north, -90 = east) after the same transform."""
    if mirror:
        yaw = -yaw
    yaw = yaw + 90 * (quarters % 4)
    yaw = (yaw + 180) % 360 - 180
    return yaw


def quarters_of(rotate):
    try:
        r = int(rotate)
    except (TypeError, ValueError):
        raise ValueError(f'rotate = {rotate!r}: a turn is 0, 90, 180 or 270 (degrees clockwise from above)')
    if r % 90:
        raise ValueError(f'rotate = {rotate}: a turn is 0, 90, 180 or 270 (degrees clockwise from above)')
    return (r // 90) % 4


class Grid:
    """Blocks by cell. Later writes win, so a build is a stack of layers. Air can be written explicitly (it clears)."""

    def __init__(self):
        self.cells = {}

    def set(self, x, y, z, state):
        self.cells[(int(x), int(y), int(z))] = state if isinstance(state, BlockState) else BlockState.parse(state)

    def get(self, x, y, z):
        return self.cells.get((x, y, z))

    def has(self, x, y, z):
        s = self.cells.get((x, y, z))
        return s is not None and s.name != 'minecraft:air'

    def remove(self, x, y, z):
        self.cells.pop((x, y, z), None)

    def stamp(self, other, at=(0, 0, 0), quarters=0, mirror=False, keep=False):
        """Copies another grid into this one, mirrored and turned about its own origin, then moved to `at`."""
        ax, ay, az = at
        for (x, y, z), s in other.cells.items():
            tx, tz = turn_cell(x, z, quarters, mirror)
            key = (tx + ax, y + ay, tz + az)
            if keep and key in self.cells:
                continue
            self.cells[key] = s.turned(quarters, mirror) if (quarters or mirror) else s

    def bounds(self):
        if not self.cells:
            return (0, 0, 0), (0, 0, 0)
        xs, ys, zs = zip(*self.cells)
        return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))

    def __len__(self):
        return len(self.cells)
