"""`videocraft review packet`: everything a reviewer agent judges, in review/packet/ (docs/REVIEW.md lists it).

Frames come from cut/master.mp4 through one ffmpeg pass per tile size (a select filter keeps exactly the frames
needed); labels are drawn with the built-in bitmap font. Owned by workstream (d).
"""
import json
import math
import shutil
import subprocess
from pathlib import Path

from videocraft import timeline, tools
from videocraft.review import prompts, rubric as rubrics, sound
from videocraft.review.image import Canvas

BIG = (640, 360)
SMALL = (320, 180)
GAP = 8
LABEL = 30            # label band under a tile, pixels (font scale 2: 14 px glyphs)
HEADER = 64
BG, INK, DIM, MARK = (18, 18, 22), (255, 255, 255), (170, 170, 180), (255, 210, 60)
STRIP_TILES = 12      # at most this many frames in a strip (first and last always)
CONTACT_FPS = 4
CONTACT_COLS, CONTACT_ROWS = 6, 8


def select_expr(frames):
    """An ffmpeg select expression true on exactly these frames. Runs of consecutive frames become between(); the sum
    is a balanced tree, because ffmpeg's parser nests a flat a+b+c+... chain and refuses one of about a hundred terms."""
    terms, frames = [], sorted(set(frames))
    i = 0
    while i < len(frames):
        j = i
        while j + 1 < len(frames) and frames[j + 1] == frames[j] + 1:
            j += 1
        terms.append(f'eq(n,{frames[i]})' if i == j else f'between(n,{frames[i]},{frames[j]})')
        i = j + 1

    def tree(t):
        if len(t) == 1:
            return t[0]
        mid = len(t) // 2
        return f'({tree(t[:mid])}+{tree(t[mid:])})'
    return tree(terms) if terms else '0'


def grab(video, frames, size, ffmpeg=None):
    """{frame: RGB24 bytes} for the given frame numbers of a video, scaled to size."""
    frames = sorted(set(int(f) for f in frames if f >= 0))
    if not frames:
        return {}
    w, h = size
    expr = select_expr(frames)
    cmd = [ffmpeg or tools.ffmpeg(), '-v', 'error', '-nostdin', '-i', str(video), '-an',
           '-vf', f"select='{expr}',scale={w}:{h}:flags=area,format=rgb24", '-fps_mode', 'passthrough', '-f', 'rawvideo', '-']
    data = subprocess.run(cmd, capture_output=True, check=True).stdout
    n = w * h * 3
    got = [data[i * n:(i + 1) * n] for i in range(len(data) // n)]
    return dict(zip(frames, got))


def strip_frames(n, tiles=STRIP_TILES, every=None):
    """Frame offsets in a clip of n frames: the first, the last and every n-th between."""
    if n <= 0:
        return []
    step = every or max(1, math.ceil((n - 1) / max(1, tiles - 1)))
    picks = list(range(0, n, step))
    if picks[-1] != n - 1:
        picks.append(n - 1)
    return picks


def _tile(canvas, rgb, size, x, y, lines, color=INK):
    w, h = size
    canvas.fill(x - 1, y - 1, w + 2, h + 2, (60, 60, 70))
    if rgb:
        canvas.paste(rgb, w, h, x, y)
    for k, (s, c) in enumerate(lines):
        canvas.text(x + 4, y + h + 6 + k * 18, s, 2, c or color)


def _sheet(tiles, size, cols, header):
    w, h = size
    rows = max(1, math.ceil(len(tiles) / cols))
    lines = max((len(t[1]) for t in tiles), default=1)
    band = 8 + 18 * lines
    canvas = Canvas(GAP + cols * (w + GAP), HEADER + rows * (h + band + GAP) + GAP, BG)
    canvas.text(GAP, 12, header[0], 3, INK)
    if len(header) > 1:
        canvas.text(GAP, 40, header[1], 2, DIM)
    for k, (rgb, label) in enumerate(tiles):
        r, c = divmod(k, cols)
        _tile(canvas, rgb, size, GAP + c * (w + GAP), HEADER + r * (h + band + GAP), label)
    return canvas


def _captions(it, plan, clips, fps):
    lines = ['# Captions and on-screen text', '', 'Per shot, in cut order: what the text layer logged (text.json) and what the script asked for.', '']
    for clip in clips:
        if clip['kind'] != 'shot':
            continue
        name = clip['shot']
        shot = next((s for s in plan['shots'] if s['name'] == name), {})
        lines.append(f'## {name} ({timeline.timecode(clip["out_start"], fps)}, {clip["out_frames"] / fps:.2f} s)')
        tj = it.take / 'shots' / name / 'text.json'
        if tj.exists():
            from videocraft.measure import text as textrules
            items, _ = textrules.load(tj, fps)
            for t in items:
                at = clip['out_start'] + t['start'] - clip['src_in']
                lines.append(f'- logged {t["kind"]} frames {t["start"]}-{t["end"]} (cut {timeline.timecode(at, fps)}), cap {t["cap"]} px: "{t["text"]}"')
        for cue in shot.get('timeline', []):
            words = cue.get('text') or cue.get('title') or cue.get('words')
            if cue.get('do') in ('caption', 'title', 'say', 'lower_third', 'card', 'keycap') and words:
                if isinstance(words, list):
                    words = ' / '.join(w if isinstance(w, str) else str(w.get('w', '')) for w in words)
                who = f' ({cue["actor"]})' if cue.get('do') == 'say' else ''
                lines.append(f'- script {cue["do"]}{who} at {cue["at"]:g} s: "{words}"')
        lines.append('')
    return '\n'.join(lines)


def build(it, rubric_ref=None, reviewers=None, every=None, say=print):
    """Writes review/packet/ for an iteration; returns its manifest."""
    plan, result = it.plan(), it.result()
    if not result or result.get('verdict') != 'PASS':
        raise SystemExit(f'No packet: the take in {it.take} did not pass')
    master = it.cut / 'master.mp4'
    if not master.exists():
        raise SystemExit(f'No packet: {master} is missing (videocraft cut {it.path})')
    metrics_file = it.measure / 'metrics.json'
    if not metrics_file.exists() or json.loads(metrics_file.read_text()).get('version', 1) < 2:
        from videocraft.measure import measure
        say('measuring first')
        measure(it)
    metrics = json.loads(metrics_file.read_text())
    rub = rubrics.load(rubric_ref)
    roles = [r['id'] for r in rub['role']] if not reviewers else [x.strip() for x in reviewers.split(',') if x.strip()]
    for r in roles:
        rubrics.role(rub, r)
    fps = plan['output']['fps']
    clips = timeline.clips(it)
    total = metrics['master']['frames']
    out = it.review / 'packet'
    if out.exists():
        shutil.rmtree(out)
    for d in ('strips', 'contact', 'cuts', 'prompts'):
        (out / d).mkdir(parents=True)

    shot_of = {}
    for c in clips:
        for f in range(c['out_start'], c['out_start'] + c['out_frames']):
            shot_of[f] = c
    strip_picks = {c['index']: [c['out_start'] + o for o in strip_frames(c['out_frames'], every=every)] for c in clips if c['kind'] == 'shot'}
    hard, soft = timeline.boundaries(clips)
    joins = sorted(set(hard) | set(soft))
    cut_picks = {j: [f for f in range(j - 3, j + 3) if 0 <= f < total] for j in joins}
    contact_picks = list(range(0, total, max(1, round(fps / CONTACT_FPS))))
    big = grab(master, {f for v in strip_picks.values() for f in v} | {f for v in cut_picks.values() for f in v}, BIG)
    small = grab(master, contact_picks, SMALL)
    tc = lambda f: timeline.timecode(f, fps)

    def label(f):
        c = shot_of.get(f)
        own = f'S{c["src_in"] + f - c["out_start"]}' if c and c['kind'] == 'shot' else 'BLACK'
        return [(f'{tc(f)}  M{f}  {own}', None)]

    files = {'strips': [], 'contact': [], 'cuts': []}
    for c in clips:
        if c['index'] not in strip_picks:      # black gaps: the cut pairs and contact sheets show them
            continue
        name = c['shot'] or 'black'
        picks = strip_picks[c['index']]
        header = (f'{c["index"] + 1:02d} {name}',
                  f'{c["kind"].upper()}  {c["out_frames"]} FRAMES {c["out_frames"] / fps:.2f} S  CUT {tc(c["out_start"])}-{tc(c["out_start"] + c["out_frames"])}'
                  + (f'  RIG {_rig(plan, name)}' if c['kind'] == 'shot' else ''))
        tiles = [(big.get(f), label(f)) for f in picks]
        path = Path(_sheet(tiles, BIG, 3, header).save(out / 'strips' / f'{c["index"] + 1:02d}-{name}.jpg'))
        files['strips'].append(str(path.relative_to(out)))
    per_sheet = CONTACT_COLS * CONTACT_ROWS
    for k in range(0, len(contact_picks), per_sheet):
        chunk = contact_picks[k:k + per_sheet]
        tiles = [(small.get(f), [(tc(f), None), ((shot_of.get(f) or {}).get('shot') or 'black', DIM)]) for f in chunk]
        path = Path(_sheet(tiles, SMALL, CONTACT_COLS, (f'CONTACT {k // per_sheet + 1}  {tc(chunk[0])}-{tc(chunk[-1])}',
                                                         f'{CONTACT_FPS} FRAMES A SECOND, {plan["name"]} {it.name}')).save(out / 'contact' / f'sheet-{k // per_sheet + 1}.jpg'))
        files['contact'].append(str(path.relative_to(out)))
    for n, j in enumerate(joins):
        a, b = shot_of.get(j - 1), shot_of.get(j)
        tiles = [(big.get(f), label(f)) for f in cut_picks[j]]
        header = (f'CUT {n + 1:02d} AT {tc(j)} (M{j})',
                  f'TOP: END OF {(a or {}).get("shot") or "black"}   BOTTOM: START OF {(b or {}).get("shot") or "black"}' + ('   SOFT' if j in soft else ''))
        path = Path(_sheet(tiles, BIG, 3, header).save(out / 'cuts' / f'cut-{n + 1:02d}.jpg'))
        files['cuts'].append(str(path.relative_to(out)))

    (out / 'captions.md').write_text(_captions(it, plan, clips, fps))
    files['sound'] = sound.build(it, plan, clips, fps, total, out)
    for name in ('report.md', 'metrics.json'):
        if (it.measure / name).exists():
            shutil.copyfile(it.measure / name, out / name)
    script = next(it.path.glob('script.*'), None)
    if script:
        shutil.copyfile(script, out / ('script' + script.suffix))
    shutil.copyfile(rub['path'], out / ('rubric' + ('.toml' if rub['path'].endswith('.toml') else '.md')))
    manifest = {'run': f'{plan["name"]}/{it.name}', 'rubric': rub['name'], 'rubric_path': rub['path'], 'roles': roles,
                'fps': fps, 'frames': total, 'seconds': round(total / fps, 3), 'files': files,
                'clips': [{**c, 'start': tc(c['out_start']), 'end': tc(c['out_start'] + c['out_frames'])} for c in clips],
                'joins': [{'frame': j, 't': tc(j), 'soft': j in soft} for j in joins]}
    (out / 'packet.json').write_text(json.dumps(manifest, indent=2) + '\n')
    for r in roles:
        (out / 'prompts' / f'{r}.md').write_text(prompts.prompt(rub, r, manifest, metrics, out))
    return manifest


def _rig(plan, name):
    shot = next((s for s in plan['shots'] if s['name'] == name), None)
    return ((shot or {}).get('camera') or {}).get('rig', '-')
