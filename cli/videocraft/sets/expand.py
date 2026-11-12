"""The script hook: `[[world.set]]` → staging cues, and `<set>:<mark>` references → world positions.

    [[world.set]]
    name = "market-lane"          # sets/market-lane.toml
    at = [0, 230, 0]              # where the set's origin goes (default [0, 230, 0], above the clouds)
    rotate = 0                    # 0, 90, 180, 270 (clockwise from above); mirror = true flips east and west
    as = "lane"                   # the prefix of its marks (default: the set's name)

The set is built when the script compiles. Its commands become staging cues before the script's own: `forceload`
first, then (two seconds of staging later, so the chunks are loaded) biome, clearing and blocks as one batched
`command` cue with a `forceload` box, then the entity summons. The script's own stage cues are moved after them.

Anywhere in the script (shots, cues, actors, stage), these are replaced by plain values, so the mod needs nothing
new to use them:

    { anchor = "market-lane:stall-1", offset = [0, 0, 1] }  →  [x, y, z]   (a point; a path's first point; a
                                                                           camera's eye; "…:cam.look" its target)
    { path = "market-lane:shot-01" }                         →  [[x, y, z], …]   (`reverse`, `from`/`to` 0-1)
    { view = "barn-stage:high-wide", fov = 60 }              →  { rig = "fixed", eye, at, fov }   (in a camera)
    { yaw = "market-lane:stall-1" }                          →  a number (a point mark's facing)

The plan's world also gets `anchors` (every mark, by name, for the runtime's anchor table), `paths` and `views`.
"""
from . import DEFAULT_AT, SetError, build, load, place

SET_KEYS = {'name', 'at', 'rotate', 'mirror', 'as', 'note'}
LOAD_DELAY = 2.0     # staging seconds between forceload and the first block, so the chunks have loaded
ENTITY_GAP = 0.1


def expand(raw, source='script'):
    """Returns a copy of the raw script with its sets staged and their marks resolved (or the script as is)."""
    world = raw.get('world')
    if not isinstance(world, dict) or not world.get('set'):
        return raw
    raw = dict(raw)
    world = dict(world)
    specs = world.pop('set')
    if isinstance(specs, dict):
        specs = [specs]
    placed = {}
    cues = []
    anchors, paths, views, info = {}, {}, {}, []
    for i, spec in enumerate(specs):
        where = f'world.set[{i}]'
        if not isinstance(spec, dict) or 'name' not in spec:
            raise SetError(f'{where}: a set is a table with `name` (a file in sets/) and `at` = [x, y, z]')
        extra = sorted(set(spec) - SET_KEYS)
        if extra:
            raise SetError(f'{where}: unknown key(s) {", ".join(extra)}; allowed: {", ".join(sorted(SET_KEYS))}')
        built = build(load(spec['name']))
        p = place(built, spec.get('at', DEFAULT_AT), spec.get('rotate', 0), spec.get('mirror', False))
        prefix = spec.get('as', built.name)
        if prefix in placed:
            raise SetError(f'{where}: "{prefix}" is placed twice; give the second one `as = "<other name>"`')
        placed[prefix] = p
        box = [p.lo[0], p.lo[2], p.hi[0], p.hi[2]]
        cues.append({'at': 0.0, 'do': 'command', 'commands': p.prepare_commands()})
        cues.append({'at': LOAD_DELAY, 'do': 'command', 'forceload': box, 'commands': p.build_commands()})
        ents = p.entity_commands()
        if ents:
            cues.append({'at': LOAD_DELAY + ENTITY_GAP, 'do': 'command', 'forceload': box, 'commands': ents})
        # Until the runtime waits for batched commands itself, give the server time to place them and the client
        # time to draw them before the first shot prepares (staging seconds run faster than real time).
        settle = round(3.0 + len(p.cells) / 15000, 1)
        cues.append({'at': LOAD_DELAY + 2 * ENTITY_GAP, 'do': 'wait', 'seconds': settle})
        anchors.update(p.anchors(prefix))
        for k, m in p.marks.items():
            if m['kind'] == 'path':
                paths[f'{prefix}:{k}'] = [list(q) for q in m['points']]
            elif m['kind'] == 'camera':
                views[f'{prefix}:{k}'] = {'eye': list(m['eye']), 'at': list(m['look']), 'fov': m['fov']}
        s = p.summary()
        info.append({'name': built.name, 'as': prefix, 'at': list(p.at), 'rotate': p.quarters * 90, 'mirror': p.mirror,
                     'box': s['box'], 'time': built.time, 'weather': built.weather, 'blocks': s['blocks'],
                     'commands': s['commands']['total']})
        if 'time' not in world and i == 0:
            world['time'] = built.time
        if 'weather' not in world and i == 0:
            world['weather'] = built.weather
    shift = LOAD_DELAY + 3 * ENTITY_GAP
    own = [dict(c, at=float(c.get('at', 0)) + shift) for c in world.get('stage', [])]
    world['stage'] = cues + own
    world['sets'] = info
    world['anchors'] = anchors
    world['paths'] = paths
    world['views'] = views
    raw['world'] = world
    ctx = Resolver(placed)
    for key, value in list(raw.items()):
        if key not in ('edit', 'world'):
            raw[key] = ctx.walk(value, key)
    world['stage'] = [ctx.walk(c, 'world.stage') if i >= len(cues) else c for i, c in enumerate(world['stage'])]
    return raw


class Resolver:
    def __init__(self, placed):
        self.placed = placed

    def _mark(self, ref, where):
        if not isinstance(ref, str) or ':' not in ref:
            return None, None
        prefix, _, name = ref.partition(':')
        if prefix not in self.placed:
            return None, None  # another namespace (a plugin's anchor): left alone for the runtime
        look = name.endswith('.look')
        end = name.endswith('.end')
        base = name[:-5] if look else name[:-4] if end else name
        marks = self.placed[prefix].marks
        if base not in marks:
            raise SetError(f'{where}: the set "{prefix}" has no mark "{base}"; marks: {", ".join(sorted(marks))}')
        return marks[base], ('look' if look else 'end' if end else None)

    def walk(self, v, where):
        if isinstance(v, list):
            return [self.walk(x, f'{where}[{i}]') for i, x in enumerate(v)]
        if not isinstance(v, dict):
            return v
        if 'anchor' in v and set(v) <= {'anchor', 'offset'}:
            m, sub = self._mark(v['anchor'], where)
            if m is not None:
                if m['kind'] == 'point':
                    p = m['at']
                elif m['kind'] == 'path':
                    p = m['points'][-1] if sub == 'end' else m['points'][0]
                else:
                    p = m['look'] if sub == 'look' else m['eye']
                off = v.get('offset', [0, 0, 0])
                if not (isinstance(off, list) and len(off) == 3):
                    raise SetError(f'{where}: offset is [x, y, z]')
                return [round(p[0] + off[0], 4), round(p[1] + off[1], 4), round(p[2] + off[2], 4)]
        if 'path' in v and isinstance(v['path'], str) and set(v) <= {'path', 'reverse', 'from', 'to', 'offset'}:
            m, _ = self._mark(v['path'], where)
            if m is not None:
                if m['kind'] != 'path':
                    raise SetError(f'{where}: "{v["path"]}" is a {m["kind"]} mark, not a path')
                pts = [list(p) for p in m['points']]
                n = len(pts)
                a, b = float(v.get('from', 0)), float(v.get('to', 1))
                pts = pts[int(round(a * (n - 1))):int(round(b * (n - 1))) + 1]
                if v.get('reverse'):
                    pts.reverse()
                off = v.get('offset', [0, 0, 0])
                return [[round(p[0] + off[0], 4), round(p[1] + off[1], 4), round(p[2] + off[2], 4)] for p in pts]
        if 'yaw' in v and isinstance(v['yaw'], str) and set(v) == {'yaw'}:
            m, _ = self._mark(v['yaw'], where)
            if m is not None:
                if m['kind'] != 'point' or m.get('yaw') is None:
                    raise SetError(f'{where}: "{v["yaw"]}" is not a point mark with a facing')
                return m['yaw']
        out = {k: self.walk(x, f'{where}.{k}') for k, x in v.items()}
        if 'view' in out and isinstance(out['view'], str):
            m, _ = self._mark(out['view'], where)
            if m is not None:
                if m['kind'] != 'camera':
                    raise SetError(f'{where}: view = "{out["view"]}" is a {m["kind"]} mark, not a camera')
                out.pop('view')
                out.setdefault('rig', 'fixed')
                out.setdefault('eye', list(m['eye']))
                out.setdefault('at', list(m['look']))
                out.setdefault('fov', m['fov'])
        return out
