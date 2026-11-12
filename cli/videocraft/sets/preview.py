"""`videocraft sets preview <name>`: a take that looks at a set from everywhere a script might, and a contact sheet.

Viewpoints: every camera mark of the set; an orbit-style high wide over the whole set; for every path, a low wide
lens (one block up, 105°) at its start looking along it, and one at its end looking back (what a lead track sees);
for every point mark with a facing, a low view from it. Each is a short fixed shot; one frame of each goes into
`<run>/preview/<nn>-<view>.png` and all of them into `<run>/preview/contact.png` (legend: `preview/views.json`).
"""
import json
import math
import subprocess
from pathlib import Path

from . import ROOT, build, load, place

SHOT_SECONDS = 0.25
FRAME = 8


def viewpoints(placed, low_fov=105.0, include=None):
    """[(name, {eye, at, fov})] in world coordinates."""
    out = []
    for name, m in sorted(placed.marks.items()):
        if not m.get('preview', True):
            continue
        if m['kind'] == 'camera':
            out.append((name, {'eye': list(m['eye']), 'at': list(m['look']), 'fov': m['fov']}))
    lo, hi = placed.lo, placed.hi
    ground = placed.at[1]
    cx, cz = (lo[0] + hi[0]) / 2, (lo[2] + hi[2]) / 2
    span = max(hi[0] - lo[0], hi[2] - lo[2])
    out.append(('overview', {'eye': [cx, ground + span * 0.42, cz + span * 0.5], 'at': [cx, ground, cz], 'fov': 70.0}))
    out.append(('overview-back', {'eye': [cx, ground + span * 0.42, cz - span * 0.5], 'at': [cx, ground, cz], 'fov': 70.0}))
    for name, m in sorted(placed.marks.items()):
        if not m.get('preview', True):
            continue
        if m['kind'] == 'path' and len(m['points']) >= 2:
            pts = m['points']
            for tag, a, b in (('start', pts[0], pts[min(len(pts) - 1, 3)]), ('end', pts[-1], pts[max(0, len(pts) - 4)])):
                dx, dz = b[0] - a[0], b[2] - a[2]
                n = math.hypot(dx, dz) or 1
                eye = [a[0] - dx / n * 0.5, a[1] + 1.0, a[2] - dz / n * 0.5]
                look = [a[0] + dx / n * 8, a[1] + 1.0 - 8 * math.tan(math.radians(5)), a[2] + dz / n * 8]
                out.append((f'{name}-{tag}', {'eye': eye, 'at': look, 'fov': low_fov}))
        elif m['kind'] == 'point' and m.get('yaw') is not None:
            yaw = math.radians(m['yaw'])
            fx, fz = -math.sin(yaw), math.cos(yaw)
            a = m['at']
            out.append((name, {'eye': [a[0], a[1] + 1.2, a[2]], 'at': [a[0] + fx * 6, a[1] + 0.8, a[2] + fz * 6], 'fov': 90.0}))
    if include:
        out = [v for v in out if any(k in v[0] for k in include)]
    return out


def script(name, at=(0, 160, 0), rotate=0, world_seed='videocraft', include=None, time=None):
    """The preview take as a script (a dict) and the viewpoint list."""
    built = build(load(name))
    placed = place(built, at, rotate)
    views = viewpoints(placed, include=include)
    shots = []
    for i, (vname, v) in enumerate(views):
        shots.append({'name': f'v{i:02d}', 'duration': SHOT_SECONDS,
                      'camera': {'rig': 'fixed', 'eye': [round(c, 3) for c in v['eye']], 'at': [round(c, 3) for c in v['at']],
                                 'fov': round(v['fov'], 1)}})
    world = {'seed': world_seed, 'set': [{'name': name, 'at': list(at), 'rotate': rotate}]}
    if time is not None:
        world['time'] = int(time)
    raw = {'name': f'set-{built.name}'[:48], 'description': f'preview of the set {built.name}', 'world': world, 'shot': shots}
    return raw, views


def to_toml(raw):
    """A small TOML writer for the preview script (tables, arrays of tables, inline values)."""
    def val(v):
        if isinstance(v, bool):
            return 'true' if v else 'false'
        if isinstance(v, (int, float)):
            return repr(v)
        if isinstance(v, str):
            return json.dumps(v)
        if isinstance(v, list):
            return '[' + ', '.join(val(x) for x in v) + ']'
        if isinstance(v, dict):
            return '{ ' + ', '.join(f'{k} = {val(x)}' for k, x in v.items()) + ' }'
        raise TypeError(v)
    lines = []
    for k, v in raw.items():
        if not isinstance(v, (dict, list)) or (isinstance(v, list) and v and not isinstance(v[0], dict)):
            lines.append(f'{k} = {val(v)}')
    w = raw['world']
    lines.append('\n[world]')
    for k, v in w.items():
        if k != 'set':
            lines.append(f'{k} = {val(v)}')
    for s in w.get('set', []):
        lines.append('\n[[world.set]]')
        for k, v in s.items():
            lines.append(f'{k} = {val(v)}')
    for shot in raw['shot']:
        lines.append('\n[[shot]]')
        for k, v in shot.items():
            lines.append(f'{k} = {val(v)}')
    return '\n'.join(lines) + '\n'


def contact(iteration_path, views, ffmpeg='ffmpeg', cols=4):
    """One frame per view into preview/, and a contact sheet. Returns the sheet's path (or None)."""
    it = Path(iteration_path)
    out = it / 'preview'
    out.mkdir(exist_ok=True)
    frames = []
    for i, (vname, _v) in enumerate(views):
        video = it / 'take' / 'shots' / f'v{i:02d}' / 'video.mp4'
        png = out / f'{i:02d}-{vname}.png'
        if not video.exists():
            continue
        subprocess.run([ffmpeg, '-loglevel', 'error', '-y', '-i', str(video), '-vf', f"select='eq(n\\,{FRAME})'",
                        '-fps_mode', 'passthrough', '-frames:v', '1', str(png)], check=False)
        if png.exists():
            frames.append(png)
    (out / 'views.json').write_text(json.dumps([{'index': i, 'name': n, **v} for i, (n, v) in enumerate(views)], indent=2) + '\n')
    if not frames:
        return None
    rows = math.ceil(len(frames) / cols)
    sheet = out / 'contact.png'
    inputs = []
    for f in frames:
        inputs += ['-i', str(f)]
    pad = cols * rows - len(frames)
    graph = ''.join(f'[{i}:v]scale=480:270[s{i}];' for i in range(len(frames)))
    for k in range(pad):
        graph += f'color=c=black:s=480x270:d=1[p{k}];'
    labels = ''.join(f'[s{i}]' for i in range(len(frames))) + ''.join(f'[p{k}]' for k in range(pad))
    layout = '|'.join(f'{(i % cols) * 480}_{(i // cols) * 270}' for i in range(cols * rows))
    graph += f'{labels}xstack=inputs={cols * rows}:layout={layout}[out]'
    subprocess.run([ffmpeg, '-loglevel', 'error', '-y', *inputs, '-filter_complex', graph, '-map', '[out]',
                    '-frames:v', '1', str(sheet)], check=False)
    return sheet if sheet.exists() else None


def preview_script_path(name):
    d = ROOT / 'runs' / '_sets'
    d.mkdir(parents=True, exist_ok=True)
    return d / f'{name}-preview.toml'
