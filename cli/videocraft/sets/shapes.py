"""Block shapes a placed set works out from its neighbours, because staging places blocks without block updates.

Sets are placed with `strict` fills (no neighbour updates, so lanterns, flowers and carpets never pop off and water
never runs). The price is that fences, walls, panes and stair corners do not join up by themselves; this module
joins them the way vanilla would, from the finished grid. Leaves are made persistent (they never decay) and
two-block plants get their upper half.
"""
from .model import HORIZONTAL, BlockState

STEP = {'north': (0, -1), 'east': (1, 0), 'south': (0, 1), 'west': (-1, 0)}
OPPOSITE = {'north': 'south', 'south': 'north', 'east': 'west', 'west': 'east'}
CCW = {'north': 'west', 'west': 'south', 'south': 'east', 'east': 'north'}
CW = {v: k for k, v in CCW.items()}

DOUBLE_PLANTS = {'tall_grass', 'large_fern', 'sunflower', 'lilac', 'rose_bush', 'peony', 'pitcher_plant', 'tall_seagrass'}
# Not full cubes, or full cubes vanilla never joins a fence to (FenceBlock.isExceptionForConnection and friends).
PARTIAL_SUFFIX = ('_stairs', '_slab', '_fence', '_fence_gate', '_wall', '_pane', '_door', '_trapdoor', '_carpet',
                  '_button', '_pressure_plate', '_sign', '_banner', '_leaves', '_sapling', '_candle', '_bed', '_head',
                  '_skull', '_rail', '_coral', '_coral_fan', '_tulip', '_bars', '_chain', '_lantern', '_torch',
                  '_mushroom', '_shulker_box', '_candle_cake', '_button', '_lantern')
PARTIAL_IDS = {
    'air', 'light', 'barrier', 'structure_void', 'water', 'lava', 'lantern', 'soul_lantern', 'torch', 'candle',
    'short_grass', 'tall_grass', 'fern', 'large_fern', 'dandelion', 'poppy', 'blue_orchid', 'allium', 'azure_bluet',
    'oxeye_daisy', 'cornflower', 'lily_of_the_valley', 'wither_rose', 'sunflower', 'lilac', 'rose_bush', 'peony',
    'flower_pot', 'wheat', 'carrots', 'potatoes', 'beetroots', 'dirt_path', 'farmland', 'ladder', 'vine', 'snow',
    'cake', 'lever', 'campfire', 'soul_campfire', 'anvil', 'bell', 'lectern', 'grindstone', 'brewing_stand',
    'cauldron', 'composter', 'hopper', 'enchanting_table', 'end_rod', 'chest', 'trapped_chest', 'ender_chest',
    'iron_bars', 'chain', 'lily_pad', 'cactus', 'bamboo', 'pumpkin', 'carved_pumpkin', 'jack_o_lantern', 'melon',
    'scaffolding', 'cobweb', 'stonecutter', 'daylight_detector', 'conduit', 'pink_petals', 'leaf_litter', 'bush',
    'dead_bush', 'sweet_berry_bush', 'glass_pane', 'decorated_pot', 'sea_pickle', 'kelp', 'seagrass',
    'firefly_bush', 'short_dry_grass', 'tall_dry_grass', 'wildflowers', 'cactus_flower', 'moss_carpet'}


def _id(s):
    return s.id if s is not None else None


def full_cube(s):
    if s is None:
        return False
    i = s.id
    return not (i in PARTIAL_IDS or i.startswith('potted_') or i.endswith(PARTIAL_SUFFIX))


def _fence_family(i):
    if i is None:
        return None
    if i == 'nether_brick_fence':
        return 'nether'
    if i.endswith('_fence'):
        return 'wood'
    return None


def finish(grid):
    """Joins fences, walls, panes and stairs; makes leaves persistent; completes two-block plants. In place."""
    cells = grid.cells
    for (x, y, z), s in list(cells.items()):
        i = s.id
        if i in DOUBLE_PLANTS and 'half' not in s.props:
            cells[(x, y, z)] = s.with_props(half='lower')
            if (x, y + 1, z) not in cells:
                cells[(x, y + 1, z)] = s.with_props(half='upper')
    for (x, y, z), s in list(cells.items()):
        if s.id.endswith('_leaves') and not any(
                cells.get(n) is not None and cells[n].id != 'air' for n in
                ((x + 1, y, z), (x - 1, y, z), (x, y + 1, z), (x, y - 1, z), (x, y, z + 1), (x, y, z - 1))):
            del cells[(x, y, z)]  # a lone leaf in the air, left by a noisy canopy edge
    for (x, y, z), s in list(cells.items()):
        i = s.id
        if i.endswith('_leaves'):
            if s.props.get('persistent') != 'true':
                cells[(x, y, z)] = s.with_props(persistent='true')
        elif i.endswith('_fence') and not i.endswith('_gate'):
            fam = _fence_family(i)
            props = {}
            for d, (dx, dz) in STEP.items():
                n = cells.get((x + dx, y, z + dz))
                ni = _id(n)
                gate = ni is not None and ni.endswith('_fence_gate') and n.props.get('facing') in (CW[d], CCW[d])
                props[d] = 'true' if (_fence_family(ni) == fam or gate or full_cube(n)) else 'false'
            cells[(x, y, z)] = s.with_props(**props)
        elif i.endswith('_wall') and 'sign' not in i and 'banner' not in i and 'torch' not in i and 'fan' not in i:
            props = {}
            joined = []
            for d, (dx, dz) in STEP.items():
                n = cells.get((x + dx, y, z + dz))
                ni = _id(n)
                ok = ni is not None and ((ni.endswith('_wall') and 'sign' not in ni) or ni.endswith('_pane')
                                         or ni == 'iron_bars' or ni.endswith('_fence_gate') or full_cube(n))
                above = cells.get((x, y + 1, z))
                props[d] = ('tall' if full_cube(above) else 'low') if ok else 'none'
                if ok:
                    joined.append(d)
            straight = sorted(joined) in (['north', 'south'], ['east', 'west'])
            above = cells.get((x, y + 1, z))
            props['up'] = 'false' if straight and not (above is not None and above.id not in ('air',) and not full_cube(above)) else 'true'
            cells[(x, y, z)] = s.with_props(**props)
        elif i.endswith('_pane') or i == 'iron_bars':
            props = {}
            for d, (dx, dz) in STEP.items():
                n = cells.get((x + dx, y, z + dz))
                ni = _id(n)
                ok = ni is not None and (ni.endswith('_pane') or ni == 'iron_bars' or (ni.endswith('_wall') and 'sign' not in ni) or full_cube(n))
                props[d] = 'true' if ok else 'false'
            cells[(x, y, z)] = s.with_props(**props)
    for (x, y, z), s in list(cells.items()):
        if s.id.endswith('_stairs'):
            cells[(x, y, z)] = s.with_props(shape=_stairs_shape(cells, x, y, z, s))


def _stairs(cells, x, y, z):
    s = cells.get((x, y, z))
    return s if s is not None and s.id.endswith('_stairs') else None


def _stairs_shape(cells, x, y, z, s):
    """Vanilla's StairBlock.getStairsShape on the finished grid."""
    facing, half = s.props.get('facing', 'north'), s.props.get('half', 'bottom')
    if facing not in STEP:
        return 'straight'
    dx, dz = STEP[facing]
    front = _stairs(cells, x + dx, y, z + dz)
    if front is not None and front.props.get('half', 'bottom') == half:
        f2 = front.props.get('facing', 'north')
        if f2 in STEP and (f2 in ('east', 'west')) != (facing in ('east', 'west')):
            ox, oz = STEP[OPPOSITE[f2]]
            if _can_take(cells, x + ox, y, z + oz, facing, half):
                return 'outer_left' if f2 == CCW[facing] else 'outer_right'
    bx, bz = STEP[OPPOSITE[facing]]
    back = _stairs(cells, x + bx, y, z + bz)
    if back is not None and back.props.get('half', 'bottom') == half:
        f2 = back.props.get('facing', 'north')
        if f2 in STEP and (f2 in ('east', 'west')) != (facing in ('east', 'west')):
            ox, oz = STEP[f2]
            if _can_take(cells, x + ox, y, z + oz, facing, half):
                return 'inner_left' if f2 == CCW[facing] else 'inner_right'
    return 'straight'


def _can_take(cells, x, y, z, facing, half):
    n = _stairs(cells, x, y, z)
    return n is None or n.props.get('facing') != facing or n.props.get('half', 'bottom') != half


def supported(grid, ground_y=-1, drop_leaves=0):
    """Cells not connected (face to face) to the ground layer or below: floating blocks a viewer would notice.
    Returns a list of (count, example cell) per floating group, largest first. Floating groups of at most
    `drop_leaves` cells that are only leaves (a noisy canopy's stray tufts) are removed from the grid instead."""
    cells = grid.cells
    solid = {k for k, s in cells.items() if s.id not in ('air', 'light', 'barrier', 'structure_void')}
    seen = set()
    stack = [k for k in solid if k[1] <= ground_y]
    seen.update(stack)
    while stack:
        x, y, z = stack.pop()
        for n in ((x + 1, y, z), (x - 1, y, z), (x, y + 1, z), (x, y - 1, z), (x, y, z + 1), (x, y, z - 1)):
            if n in solid and n not in seen:
                seen.add(n)
                stack.append(n)
    rest = solid - seen
    groups = []
    while rest:
        start = rest.pop()
        group = [start]
        stack = [start]
        while stack:
            x, y, z = stack.pop()
            for n in ((x + 1, y, z), (x - 1, y, z), (x, y + 1, z), (x, y - 1, z), (x, y, z + 1), (x, y, z - 1)):
                if n in rest:
                    rest.discard(n)
                    group.append(n)
                    stack.append(n)
        if len(group) <= drop_leaves and all(cells[k].id.endswith('_leaves') for k in group):
            for k in group:
                del cells[k]
            continue
        groups.append((len(group), min(group)))
    return sorted(groups, reverse=True)


__all__ = ['finish', 'supported', 'full_cube', 'HORIZONTAL', 'BlockState']
