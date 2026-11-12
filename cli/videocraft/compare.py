"""`videocraft compare <a> <b>`: what changed between two iterations, written to <b>/compare/<a name>/.

    compare.md        scores per criterion (a, b, delta), the pass verdicts, measured deltas, the notes of b
    compare.json      the same as data
    shots/<shot>.png  for every shot in both: first, middle and last frame of a (top row) over b (bottom row)
Owned by workstream (d).
"""
import json

from videocraft import timeline
from videocraft.review.image import Canvas
from videocraft.review.packet import BIG, BG, DIM, GAP, HEADER, INK, grab

METRICS = [('shots', 'picture.shot_stats.count'), ('median shot s', 'picture.shot_stats.median'), ('mean shot s', 'picture.shot_stats.mean'),
           ('longest shot s', 'picture.shot_stats.longest'), ('seconds', 'master.seconds'), ('black s', 'picture.black_seconds'),
           ('loudness LUFS', 'loudness.integrated'), ('true peak dBFS', 'loudness.true_peak'), ('text problems', 'text.problems'),
           ('warnings', 'warnings'), ('capture fps', 'take.captureFps')]


def _read(path):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _dig(d, dotted):
    for part in dotted.split('.'):
        if not isinstance(d, dict):
            return None
        d = d.get(part)
    return len(d) if isinstance(d, list) else d


def _delta(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        d = round(b - a, 3)
        return f'{d:+g}'
    return '' if a == b else 'changed'


def compare(a, b):
    sa, sb = _read(a.path / 'score.json'), _read(b.path / 'score.json')
    ma, mb = _read(a.measure / 'metrics.json'), _read(b.measure / 'metrics.json')
    crit = list(dict.fromkeys(list((sa.get('criteria') or {}).keys()) + list((sb.get('criteria') or {}).keys())))
    scores = [{'criterion': c, 'a': (sa.get('criteria') or {}).get(c), 'b': (sb.get('criteria') or {}).get(c)} for c in crit]
    scores.append({'criterion': 'average', 'a': sa.get('average'), 'b': sb.get('average')})
    measured = [{'metric': name, 'a': _dig(ma, key), 'b': _dig(mb, key)} for name, key in METRICS]
    out = b.path / 'compare' / f'{a.path.parent.name}-{a.name}'
    (out / 'shots').mkdir(parents=True, exist_ok=True)
    images = _side_by_side(a, b, out / 'shots')
    data = {'a': str(a.path), 'b': str(b.path), 'scores': scores, 'pass': {'a': sa.get('pass'), 'b': sb.get('pass')},
            'measured': measured, 'images': images}
    (out / 'compare.json').write_text(json.dumps(data, indent=2) + '\n')
    L = [f'# Compare {a.path.parent.name}/{a.name} → {b.path.parent.name}/{b.name}', '',
         f'Pass: {sa.get("pass")} → {sb.get("pass")} (rubric {sb.get("rubric") or sa.get("rubric") or "-"})', '',
         '| Criterion | a | b | Δ |', '|:--|--:|--:|--:|']
    L += [f'| {s["criterion"]} | {s["a"] if s["a"] is not None else "-"} | {s["b"] if s["b"] is not None else "-"} | {_delta(s["a"], s["b"])} |' for s in scores]
    L += ['', '| Measured | a | b | Δ |', '|:--|--:|--:|--:|']
    L += [f'| {m["metric"]} | {m["a"] if m["a"] is not None else "-"} | {m["b"] if m["b"] is not None else "-"} | {_delta(m["a"], m["b"])} |' for m in measured]
    notes = b.path / 'notes.md'
    if notes.exists():
        L += ['', '## What b changed (notes.md)', '', notes.read_text().strip()]
    if images:
        L += ['', '## The same shots, a over b', ''] + [f'- `{p}`' for p in images]
    (out / 'compare.md').write_text('\n'.join(L) + '\n')
    return out, data


def _side_by_side(a, b, out):
    ca = {c['shot']: c for c in timeline.clips(a) if c['kind'] == 'shot'} if (a.cut / 'master.mp4').exists() else {}
    cb = {c['shot']: c for c in timeline.clips(b) if c['kind'] == 'shot'} if (b.cut / 'master.mp4').exists() else {}
    both = [s for s in cb if s in ca]
    if not both:
        return []
    picks = lambda c: [c['out_start'], c['out_start'] + c['out_frames'] // 2, c['out_start'] + max(0, c['out_frames'] - 1)]
    fa = grab(a.cut / 'master.mp4', [f for s in both for f in picks(ca[s])], BIG)
    fb = grab(b.cut / 'master.mp4', [f for s in both for f in picks(cb[s])], BIG)
    fps_a, fps_b = a.plan()['output']['fps'], b.plan()['output']['fps']
    w, h = BIG
    files = []
    for s in both:
        canvas = Canvas(GAP + 3 * (w + GAP), HEADER + 2 * (h + 30 + GAP) + GAP, BG)
        canvas.text(GAP, 12, s, 3, INK)
        canvas.text(GAP, 40, f'TOP {a.path.parent.name}/{a.name}  BOTTOM {b.path.parent.name}/{b.name}', 2, DIM)
        for row, (clips, frames, fps, it) in enumerate(((ca, fa, fps_a, a), (cb, fb, fps_b, b))):
            for k, f in enumerate(picks(clips[s])):
                x, y = GAP + k * (w + GAP), HEADER + row * (h + 30 + GAP)
                canvas.fill(x - 1, y - 1, w + 2, h + 2, (60, 60, 70))
                if frames.get(f):
                    canvas.paste(frames[f], w, h, x, y)
                canvas.text(x + 4, y + h + 6, f'{it.name}  {timeline.timecode(f, fps)}  M{f}', 2, INK)
        path = out / f'{s}.png'
        canvas.png(path)
        files.append(str(path.relative_to(out.parent)))
    return files
