"""Sets (cli/videocraft/sets): block states and turns, the command merge and its limits, marks, the script hook, skins,
and every shipped set building cleanly."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'cli'))
from videocraft import script  # noqa: E402
from videocraft.sets import SETS_DIR, SetError, build, emit, load, place, shapes, skin  # noqa: E402
from videocraft.sets.model import BlockState, Grid, turn_cell, turn_point, turn_yaw  # noqa: E402


def apply(commands):
    """Replays fill/setblock commands into a dict, as the game would (later wins)."""
    world = {}
    for c in commands:
        parts = c.split(' ')
        if parts[0] == 'fill':
            x1, y1, z1, x2, y2, z2 = map(int, parts[1:7])
            for x in range(x1, x2 + 1):
                for y in range(y1, y2 + 1):
                    for z in range(z1, z2 + 1):
                        world[(x, y, z)] = parts[7]
        elif parts[0] == 'setblock':
            world[tuple(map(int, parts[1:4]))] = parts[4]
    return world


class BlockStates(unittest.TestCase):
    def test_parse_and_format_sort_properties(self):
        s = BlockState.parse('oak_stairs[half=bottom,facing=east]')
        self.assertEqual(s.text, 'minecraft:oak_stairs[facing=east,half=bottom]')
        self.assertEqual(BlockState.parse(s.text), s)

    def test_turns_follow_vanilla_clockwise(self):
        s = BlockState.parse('oak_stairs[facing=north]')
        self.assertEqual(s.turned(1).props['facing'], 'east')
        self.assertEqual(s.turned(2).props['facing'], 'south')
        self.assertEqual(s.turned(4), s)
        self.assertEqual(BlockState.parse('oak_log[axis=x]').turned(1).props['axis'], 'z')
        self.assertEqual(BlockState.parse('oak_sign[rotation=2]').turned(1).props['rotation'], '6')
        fence = BlockState.parse('oak_fence[north=true,east=false,south=false,west=false]').turned(1)
        self.assertEqual((fence.props['east'], fence.props['north']), ('true', 'false'))

    def test_mirror_swaps_east_west_and_handedness(self):
        s = BlockState.parse('oak_stairs[facing=east,shape=inner_left]').turned(0, mirror=True)
        self.assertEqual((s.props['facing'], s.props['shape']), ('west', 'inner_right'))
        self.assertEqual(BlockState.parse('oak_door[hinge=left]').turned(0, True).props['hinge'], 'right')

    def test_cells_and_points_turn_together(self):
        for q in range(4):
            for mirror in (False, True):
                for x, z in ((0, 0), (3, -2), (-5, 7)):
                    cx, cz = turn_cell(x, z, q, mirror)
                    px, pz = turn_point(x + 0.5, z + 0.5, q, mirror)
                    self.assertEqual((cx + 0.5, cz + 0.5), (px, pz))
        self.assertEqual(turn_cell(*turn_cell(2, 5, 3), 1), (2, 5))
        self.assertEqual(turn_yaw(180, 1), -90)  # facing north, turned clockwise: facing east


class Merge(unittest.TestCase):
    def test_boxes_rebuild_the_grid_exactly(self):
        g = Grid()
        for x in range(-20, 21):
            for z in range(-20, 21):
                g.set(x, -1, z, 'gravel' if (x * 7 + z * 13) % 11 == 0 else 'grass_block')
                if x == z:
                    g.set(x, 0, z, 'stone')
        cells = dict(g.cells)
        cmds = emit.block_commands(cells)
        world = apply(cmds)
        self.assertEqual(world, {k: s.text for k, s in cells.items()})
        # A plate with spots: one big fill and a setblock per spot, not a fill per row.
        spots = sum(1 for s in cells.values() if s.id == 'gravel')
        self.assertLess(len(cmds), spots + 45)

    def test_fills_stay_within_the_vanilla_limit(self):
        g = Grid()
        for x in range(80):
            for y in range(10):
                for z in range(80):
                    g.set(x, y, z, 'stone')
        for c in emit.block_commands(g.cells):
            p = c.split(' ')
            if p[0] == 'fill':
                x1, y1, z1, x2, y2, z2 = map(int, p[1:7])
                self.assertLessEqual((x2 - x1 + 1) * (y2 - y1 + 1) * (z2 - z1 + 1), emit.FILL_LIMIT)
        self.assertEqual(len(apply(emit.block_commands(g.cells))), 80 * 10 * 80)
        for a, b in emit.split_box((-300, 0, -300), (300, 40, 300)):
            self.assertLessEqual((b[0] - a[0] + 1) * (b[1] - a[1] + 1) * (b[2] - a[2] + 1), emit.FILL_LIMIT)

    def test_biome_boxes_are_aligned_to_biome_cells(self):
        for c in emit.biome_commands((-57, 157, -48), (55, 203, 45), 'minecraft:plains'):
            x1, y1, z1, x2, y2, z2 = map(int, c.split(' ')[1:7])
            self.assertEqual([v % 4 for v in (x1, y1, z1)], [0, 0, 0])
            self.assertEqual([v % 4 for v in (x2, y2, z2)], [3, 3, 3])
            self.assertLessEqual((x2 - x1 + 1) * (y2 - y1 + 1) * (z2 - z1 + 1), emit.FILL_LIMIT)

    def test_clearing_never_issues_a_fill_that_changes_nothing(self):
        cmds = emit.clear_commands((0, 0, 0), (40, 40, 40))
        self.assertTrue(cmds[0].startswith('execute if block 0 0 0 air run setblock 0 0 0 barrier'))
        self.assertTrue(all(c.startswith(('execute if block', 'fill')) for c in cmds))

    def test_summon_coordinates_keep_a_decimal_point(self):
        c = emit.summon_command({'type': 'minecraft:text_display', 'pos': (4, 161, -2.5), 'nbt': {'text': {'text': 'Hi'}}})
        self.assertTrue(c.startswith('summon minecraft:text_display 4.0 161.0 -2.5 {text:{text:"Hi"}}'), c)


class Shapes(unittest.TestCase):
    def test_fences_join_and_hip_corners_turn_outward(self):
        g = Grid()
        for x in range(3):
            g.set(x, 0, 0, 'spruce_fence')
        g.set(3, 0, 0, 'stone')
        g.set(0, 1, 5, 'oak_stairs[facing=south,half=bottom]')
        g.set(0, 1, 6, 'oak_stairs[facing=east,half=bottom]')
        shapes.finish(g)
        mid = g.get(1, 0, 0)
        self.assertEqual((mid.props['east'], mid.props['west'], mid.props['north']), ('true', 'true', 'false'))
        self.assertEqual(g.get(2, 0, 0).props['east'], 'true')  # joins the stone
        self.assertEqual(g.get(0, 1, 5).props['shape'], 'outer_left')

    def test_floating_blocks_are_found(self):
        g = Grid()
        g.set(0, -1, 0, 'grass_block')
        g.set(0, 0, 0, 'stone')
        g.set(5, 4, 5, 'stone')
        self.assertEqual(shapes.supported(g), [(1, (5, 4, 5))])


SMALL = {
    'name': 'tiny', 'time': 9000, 'biome': 'minecraft:plains',
    'build': [
        {'do': 'ground', 'from': [-8, -8], 'to': [8, 8]},
        {'do': 'lane', 'points': [[-8, 0], [8, 0]], 'width': 3, 'mark': 'lane', 'smooth': False},
        {'do': 'house', 'from': [-6, -7], 'to': [-1, -3], 'roof': {'kind': 'hip'}},
        {'do': 'stall', 'at': [3, 4], 'facing': 'north', 'mark': 'stall'},
        {'do': 'poster', 'at': [2, 1, -6], 'facing': 'south', 'size': [2, 2], 'lines': [{'text': 'HI'}], 'mark': 'poster'},
    ],
    'mark': [
        {'name': 'door', 'at': [0, 0, 5], 'facing': 'east'},
        {'name': 'walk', 'along': 'lane', 'from': 2, 'to': 10},
        {'name': 'cam', 'eye': [0, 3, 8], 'look': 'door', 'fov': 60},
    ],
}


class Sets(unittest.TestCase):
    def test_marks_turn_with_the_set(self):
        built = build(dict(SMALL))
        p0 = place(built, (100, 160, 50), 0)
        p1 = place(built, (100, 160, 50), 90)
        self.assertEqual(p0.marks['door']['at'], (100.5, 160.0, 55.5))
        x, z = turn_point(0.5, 5.5, 1)
        self.assertEqual(p1.marks['door']['at'], (100 + x, 160.0, 50 + z))
        self.assertEqual(p1.marks['door']['yaw'], 0.0)  # east, turned clockwise: south
        self.assertEqual(len(p0.cells), len(p1.cells))
        walk = p0.marks['walk']['points']
        self.assertAlmostEqual(walk[-1][0] - walk[0][0], 8, delta=1.0)
        self.assertEqual(p0.marks['poster']['kind'], 'camera')

    def test_counts_box_and_commands(self):
        p = place(build(dict(SMALL)), (0, 160, 0))
        s = p.summary()
        self.assertEqual(s['commands']['summon'], len(p.entities))
        self.assertGreater(s['blocks'], 17 * 17 * 2)
        self.assertEqual(s['box']['from'][1], 158)  # the plate is two deep under feet level 160
        cmds = p.commands()
        self.assertTrue(cmds[0].startswith('forceload add'))
        self.assertTrue(all(c.startswith('summon') for c in cmds[-len(p.entities):]))
        self.assertFalse(any(' air strict' in c and c.startswith('setblock') for c in cmds))

    def test_errors_name_the_entry(self):
        bad = dict(SMALL, build=[{'do': 'ground', 'from': [0, 0], 'to': [1, 1], 'colour': 'red'}])
        with self.assertRaisesRegex(SetError, r'build\[0\].*unknown key\(s\) colour'):
            build(bad)
        with self.assertRaisesRegex(SetError, r'unknown build `do = "castle"`'):
            build(dict(SMALL, build=[{'do': 'castle'}]))

    def test_script_hook_stages_the_set_and_resolves_marks(self):
        with tempfile.TemporaryDirectory() as d:
            setfile = Path(d) / 'tiny.toml'
            setfile.write_text(_toml(SMALL))
            raw = {'name': 'uses-a-set', 'world': {'seed': 'x', 'set': [{'name': str(setfile), 'at': [0, 160, 0], 'rotate': 90}]},
                   'shot': [{'name': 'a', 'duration': 1, 'camera': {'view': 'tiny:cam'},
                             'cue': [{'at': 0.5, 'do': 'walk', 'path': {'path': 'tiny:walk'}, 'to': {'anchor': 'tiny:door', 'offset': [0, 1, 0]}}]}]}
            plan, _ = script.compile_script(raw)
            world = plan['world']
            self.assertEqual(world['time'], 9000)
            self.assertEqual(world['stage'][0]['commands'][0].split(' ')[0], 'forceload')
            self.assertEqual(world['stage'][1]['forceload'][0], world['sets'][0]['box']['from'][0])
            self.assertTrue(all(c.startswith('forceload add') for c in world['stage'][0]['commands']))
            self.assertEqual([c['do'] for c in world['stage'] if c['do'] == 'wait'], ['wait'])
            self.assertIn('tiny:door', world['anchors'])
            cam = plan['shots'][0]['camera']
            self.assertEqual((cam['rig'], cam['fov']), ('fixed', 60.0))
            cue = plan['shots'][0]['timeline'][0]
            self.assertIsInstance(cue['path'][0], list)
            door = world['anchors']['tiny:door']
            self.assertEqual(cue['to'], [door[0], door[1] + 1, door[2]])
            raw['shot'][0]['camera'] = {'view': 'tiny:nope'}
            with self.assertRaisesRegex(script.ScriptError, 'no mark "nope"'):
                script.compile_script(raw)


class Skins(unittest.TestCase):
    def test_a_skin_is_a_64x64_png_with_an_opaque_face(self):
        spec = {'model': 'slim', 'skin': '#c68e6a', 'hair': {'style': 'long', 'color': '#3a2a20'},
                'top': {'color': '#e04040', 'sleeves': 'short'}, 'jacket': {'color': '#203040'}}
        data = skin.png(64, 64, skin.paint(spec))
        w, h, rows = skin.read_png(data)
        self.assertEqual((w, h), (64, 64))
        self.assertTrue(all(rows[y][x][3] == 255 for y in range(8, 16) for x in range(8, 16)))  # head front
        self.assertEqual(rows[0][0][3], 0)  # outside every box
        self.assertEqual(rows[20][55][3], 0)  # slim arms leave the fourth column of the wide layout empty

    def test_shipped_skin_specs_paint(self):
        for p in sorted((SETS_DIR / 'skins').glob('*.toml')):
            with self.subTest(spec=p.name):
                skin.paint(skin.load_spec(p))


LANE = {'do': 'lane', 'points': [[0, 0], [40, 0], [70, 15]], 'width': 5, 'mark': 'lane'}
STRAIGHT = {'do': 'lane', 'points': [[0, 0], [80, 0]], 'width': 5, 'mark': 'lane', 'smooth': False}
PLATE = {'do': 'ground', 'from': [-5, -25], 'to': [80, 40]}


class LaneDressing(unittest.TestCase):
    def test_kerb_props_stand_beside_the_lane_and_face_it(self):
        raw = {'name': 'k', 'build': [PLATE, STRAIGHT, {'do': 'kerb', 'from': 2, 'to': 38, 'side': 4, 'lamps': 6,
                                                     'props': {'bench': 1, 'barrels': 1}}]}
        g = build(raw).grid
        props = [(k, v) for k, v in g.cells.items() if k[1] >= 0 and v.id != 'air']
        self.assertGreater(len(props), 20)
        # A straight lane along z = 0: everything stands 2.5 to 6 blocks off the centre line, none on the lane.
        self.assertTrue(all(2.5 <= abs(k[2] + 0.5) <= 6 for k, _ in props), sorted({k[2] for k, _ in props}))
        lanterns = [k for k, v in g.cells.items() if v.id == 'lantern' and v.props.get('hanging') == 'true']
        self.assertGreaterEqual(len(lanterns), 5)
        stairs = [(k, v) for k, v in g.cells.items() if v.id == 'spruce_stairs']
        for (x, y, z), v in stairs:  # a bench's back is away from the lane
            self.assertEqual(v.props['facing'], 'north' if z < 0 else 'south')

    def test_kerb_skips_where_something_stands(self):
        raw = {'name': 'k', 'build': [PLATE, STRAIGHT, {'do': 'box', 'from': [0, 0, -8], 'to': [40, 3, -3], 'block': 'stone'},
                                      {'do': 'kerb', 'from': 2, 'to': 38, 'side': 4, 'props': {'barrels': 1}}]}
        g = build(raw).grid
        self.assertTrue(all(v.id == 'stone' for k, v in g.cells.items() if k[1] >= 0 and k[2] < 0 and v.id != 'air'))

    def test_bunting_is_flags_across_the_lane(self):
        raw = {'name': 'k', 'build': [PLATE, STRAIGHT, {'do': 'bunting', 'd': [10, 20], 'side': 4.5}]}
        b = build(raw)
        flags = [e for e in b.entities if 'box' in e and e['block'].id.endswith('_wool')]
        self.assertGreater(len(flags), 20)
        for e in flags:
            (lx, ly, lz), (hx, hy, hz) = e['box']
            self.assertLess(hx - lx, 0.1)        # thin along the lane (x), so a lens down the lane sees them
            self.assertTrue(3.5 < ly < 6.5)
            self.assertTrue(-5 < lz < 6)

    def test_bridge_and_crops_follow_a_bend(self):
        raw = {'name': 'k', 'build': [PLATE, LANE,
                                      {'do': 'bridge', 'along': 'lane', 'd': [36, 50], 'width': 7},
                                      {'do': 'crops', 'from': [42, -20], 'to': [79, 40], 'avoid': 'lane', 'margin': 5}]}
        g = build(raw).grid
        from videocraft.sets.ops import ribbon, smooth
        spine = smooth(LANE['points'])
        lane = set(ribbon(spine, 2.5))
        self.assertFalse(any(g.get(x, -1, z).id == 'farmland' for x, z in lane if g.get(x, -1, z)))
        on_bend = [(x, z) for (x, z), v in ribbon(spine, 2.5).items() if 44 <= v[1] <= 48]
        self.assertTrue(on_bend and all(g.get(x, -1, z).id.endswith('_planks') for x, z in on_bend))


class ShippedSets(unittest.TestCase):
    def test_every_set_builds_without_floating_blocks(self):
        for p in sorted(SETS_DIR.glob('*.toml')):
            with self.subTest(set=p.stem):
                built = build(load(str(p)))
                self.assertEqual(built.warnings, [])
                placed = place(built, (0, 160, 0))
                self.assertGreater(len(placed.marks), 0)
                for c in placed.block_commands():
                    q = c.split(' ')
                    if q[0] == 'fill':
                        x1, y1, z1, x2, y2, z2 = map(int, q[1:7])
                        self.assertLessEqual((x2 - x1 + 1) * (y2 - y1 + 1) * (z2 - z1 + 1), emit.FILL_LIMIT)


def _toml(d):
    def val(v):
        if isinstance(v, bool):
            return 'true' if v else 'false'
        if isinstance(v, (int, float)):
            return repr(v)
        if isinstance(v, str):
            return '"' + v + '"'
        if isinstance(v, list):
            return '[' + ', '.join(val(x) for x in v) + ']'
        return '{ ' + ', '.join(f'{k} = {val(x)}' for k, x in v.items()) + ' }'
    lines = [f'{k} = {val(v)}' for k, v in d.items() if not isinstance(v, list)]
    for table in ('build', 'mark'):
        for e in d.get(table, []):
            lines.append(f'\n[[{table}]]')
            lines += [f'{k} = {val(v)}' for k, v in e.items()]
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    unittest.main()
