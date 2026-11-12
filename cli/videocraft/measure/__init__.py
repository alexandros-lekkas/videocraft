"""Measurements of a cut (or of any video file), written to measure/metrics.json and measure/report.md.

    measure(it)                         an iteration: format checks against the plan, then everything below
    measure_video(path, start, end, out) any video file (the benchmark's reference too), same code, same keys

metrics.json keys are stable (add, never rename): master, expectedFrames, checks, pass, take (format; runs only),
picture (shots, cut statistics, black, frozen, duplicated frames at cuts), cut_check (detected cuts against the
cut's own boundaries; runs only), loudness (null without audio), camera and framing (per shot, from frames.csv and
actors.csv), text (DESIGN.md section 5 rules from text.json), dialogue (words a second per line, the share of the
runtime with a voice, the longest silences and dead air, from voice.json and cut/audio.json; runs with say lines
only), balance (voice over music per line, the music between lines, the effects' loudest: cut/audio.json's, measured
on the mix's buses), warnings (what a reviewer should look at).
`checks` decides PASS: only the format, so a weak but correct cut still passes; the rest is for review and lint.
Owned by workstream (d).
"""
import json
import subprocess
from pathlib import Path

from videocraft import timeline as tl, tools
from videocraft.measure import camera, dialogue, loudness, text, video
from videocraft.measure.report import write_report

VERSION = 2


def probe(path):
    out = subprocess.run([tools.ffprobe(), '-v', 'error', '-select_streams', 'v:0', '-count_packets', '-show_entries',
                          'stream=width,height,r_frame_rate,nb_read_packets,codec_name,pix_fmt:format=duration,size', '-of', 'json', str(path)],
                         capture_output=True, text=True, check=True)
    data = json.loads(out.stdout)
    s, f = data['streams'][0], data['format']
    num, den = s['r_frame_rate'].split('/')
    return {'width': s['width'], 'height': s['height'], 'fps': int(num) / int(den), 'frames': int(s['nb_read_packets']),
            'codec': s['codec_name'], 'pixfmt': s['pix_fmt'], 'seconds': float(f['duration']), 'bytes': int(f['size']),
            'audio': loudness.has_audio(path)}


def _picture(path, fps, start=None, end=None):
    pic = video.analyse(video.decode(path, start, end), fps, start or 0.0)
    return pic, pic.pop('signals')


def _write_signals(sig, path):
    with open(path, 'w') as f:
        f.write('frame,full,blur,peak,luma\n')
        for i, row in enumerate(zip(sig['full'], sig['blur'], sig['peak'], sig['luma'])):
            f.write(f'{i},{row[0]:.3f},{row[1]:.3f},{row[2]},{row[3]:.2f}\n')


def _shots_measures(it, plan, fps, aspect):
    cams, frames_out, texts, problems = {}, {}, [], []
    out = plan['output']
    for shot in plan['shots']:
        d = it.take / 'shots' / shot['name']
        fcsv = d / 'frames.csv'
        if not fcsv.exists():
            continue
        rows = camera.read_csv(fcsv)
        cams[shot['name']] = {'rig': (shot.get('camera') or {}).get('rig'), **camera.kinematics(rows, fps)}
        acsv = d / 'actors.csv'
        actors = camera.read_csv(acsv) if acsv.exists() else []
        rig = (shot.get('camera') or {}).get('rig')
        tracks = {}
        subject = camera.subject_of(shot)
        for who in dict.fromkeys(([subject] if subject else []) + [str(a['actor']) for a in actors]):
            tracks[who] = camera.framing(camera.subject_track(rows, actors, who, camera.height_of(who, plan), aspect), rig if who == subject else None)
        seen = {k: v for k, v in tracks.items() if v.get('seen')}
        if seen:
            # the camera's subject, else the actor biggest in frame
            inside = {k: v for k, v in seen.items() if 0 <= v['x']['median'] <= 1 and 0 <= v['y']['median'] <= 1} or seen
            main = subject if subject in seen else max(inside, key=lambda k: inside[k]['height']['median'])
            others = {k: {'x': v['x']['median'], 'height': v['height']['median'], 'seen': v['seen']} for k, v in seen.items() if k != main}
            frames_out[shot['name']] = {'subject': main, 'from': 'camera' if main == subject else 'biggest actor', 'rig': rig,
                                        **tracks[main], 'others': others}
        tjson = d / 'text.json'
        if tjson.exists():
            items, size = text.load(tjson, fps)
            table, probs = text.check(items, fps, size[0] or out['width'], size[1] or out['height'], shot['name'])
            texts += table
            problems += probs
    counts = {}
    for p in problems:
        counts[p['rule']] = counts.get(p['rule'], 0) + 1
    return cams, frames_out, {'items': texts, 'problems': problems, 'counts': counts}


def _warnings(m):
    w = []
    pic = m.get('picture') or {}
    moving = m.get('_moving')
    for d in pic.get('duplicate_at_cuts', []):
        f = d['frame'] - 1 if d.get('side') == 'before' else d['frame']    # the frame of the shot that repeats
        if moving is not None and not (0 <= f < len(moving) and moving[f]):
            continue
        w.append(f'repeated frame at the cut at {d["t"]:.2f} s (frame {d["frame"]})')
    moving = m.get('_moving')   # master frames whose clip's camera moves (runs); None: unknown (any video)
    for f in pic.get('frozen', []):
        a, b = f['frames']
        if f['end'] - f['start'] >= 0.5 and (moving is None or any(moving[i] for i in range(a, min(b, len(moving))))):
            w.append(f'picture frozen {f["start"]:.2f}-{f["end"]:.2f} s' + ('' if moving is None else ' while the camera moves'))
    cc = m.get('cut_check') or {}
    if cc.get('missed'):
        w.append(f'{len(cc["missed"])} cut(s) in the edit not seen as cuts (same picture both sides?): frames {cc["missed"][:8]}')
    if cc.get('extra'):
        w.append(f'{len(cc["extra"])} picture jump(s) inside clips: frames {cc["extra"][:8]}')
    for name, fr in (m.get('framing') or {}).items():
        for flag in fr.get('flags', []):
            w.append(f'shot {name}: subject {fr.get("subject")} {flag}')
    for p in (m.get('text') or {}).get('problems', []):
        if p['rule'] != 'reading_one_word':
            w.append(f'text {p["rule"]} in shot {p["shot"]} at frame {p["frame"]}: "{p["text"]}" {p["detail"]}')
    dl = m.get('dialogue') or {}
    for g in dl.get('dead_air', []):
        w.append(f'dead air {g["start"]:.2f}-{g["end"]:.2f} s ({g["seconds"]:.2f} s without a voice between {g["after"]} and {g["before"]})')
    for l in dl.get('slow_lines', []):
        if not l['slow_style']:
            w.append(f'slow line {l["id"]}: {l["wps"]:.2f} words a second (under {dialogue.SLOW_WPS})')
    from videocraft.audio import balance
    w += balance.warnings(m.get('balance'))
    ld = m.get('loudness')
    if ld and ld.get('true_peak') is not None and ld['true_peak'] > -1.0:
        w.append(f'true peak {ld["true_peak"]} dBFS (over -1)')
    return w


def _moving_frames(clips, cams, total, covered=None):
    """Per master frame: whether its clip's camera moves (travels or turns). A still picture under a still camera (a
    card, a locked-off shot of a resting subject) is not a fault; under a moving camera it is."""
    out = [False] * total
    for c in clips:
        k = cams.get(c.get('shot') or '') or {}
        moves = (k.get('travel') or 0) > 0.05 or (k.get('yaw_range') or 0) > 0.5 or (k.get('pitch_range') or 0) > 0.5
        hidden = (covered or {}).get(c.get('shot'), ())
        for f in range(c['out_start'], min(total, c['out_start'] + c['out_frames'])):
            src = (c.get('src_in') or 0) + round((f - c['out_start']) * (c.get('speed') or 1))
            out[f] = moves and not any(a <= src < b for a, b in hidden)
    return out


def _dialogue(it, total):
    """Dialogue pace in the cut: each line where the mix placed it (cut/audio.json), its words from voice.json."""
    vf, af = it.path / 'voice.json', it.cut / 'audio.json'
    if not vf.exists() or not af.exists():
        return None
    entries = json.loads(vf.read_text())
    placed = {}
    for v in json.loads(af.read_text()).get('voice', []):
        placed.setdefault((v.get('shot'), Path(v.get('file', '')).name), []).append(float(v['time']))
    fps = it.plan()['output']['fps']
    segments = [{'start': c['out_start'] / fps, 'end': (c['out_start'] + c['out_frames']) / fps,
                 'kind': 'black' if c['kind'] == 'black' else 'shot', 'shot': c.get('shot')} for c in tl.clips(it)]
    lines, shots = [], set()
    for e in entries:
        times = placed.get((e.get('shot'), Path(e.get('file') or '').name))
        if not times or not e.get('words'):
            continue
        shots.add(e['shot'])
        if e.get('carried_to'):
            shots.add(e['carried_to'])
        w = e['words']
        lines.append({'id': e['id'], 'character': e.get('character'), 'shot': e['shot'], 'start': round(times[0] + w[0]['start'], 3),
                      'end': round(times[0] + w[-1]['end'], 3), 'words': len(w),
                      'wps': e.get('wps') if e.get('wps') is not None else dialogue.wps(w), 'beat': bool(e.get('beat')),
                      'style': e.get('style')})
    return dialogue.summary(lines, segments, shots, total) if lines else None


def _balance(it):
    """The mix's balance as the mix measured it (cut/audio.json); None for a cut mixed before it was measured."""
    af = it.cut / 'audio.json'
    if not af.exists():
        return None
    return json.loads(af.read_text()).get('balance')


def measure(it):
    plan, result = it.plan(), it.result()
    out = plan['output']
    master = it.cut / 'master.mp4'
    vid = probe(master)
    expected = sum(s['frames'] for s in result['shots'])
    for clip in it.edit()['clip']:
        expected -= sum(clip.get('trim') or [0, 0])
    timeline = it.cut / 'timeline.json'
    if timeline.exists():
        expected = json.loads(timeline.read_text()).get('frames', expected)
    checks = {
        'size': vid['width'] == out['width'] and vid['height'] == out['height'],
        'fps': abs(vid['fps'] - out['fps']) < 1e-6,
        'frames': vid['frames'] == expected,
        'shots_complete': all(s['frames'] == round(p['duration'] * out['fps']) for s, p in zip(result['shots'], plan['shots'])),
    }
    it.measure.mkdir(exist_ok=True)
    pic, sig = _picture(master, out['fps'])
    _write_signals(sig, it.measure / 'signals.csv')
    hard, soft = tl.boundaries(tl.clips(it))
    matched, missed, extra = video.compare_cuts([c['frame'] for c in pic['cuts']], hard)
    soft_seen = [f for f in extra if any(abs(f - s) <= 3 for s in soft)]
    extra = [f for f in extra if f not in soft_seen]
    cams, framing, texts = _shots_measures(it, plan, out['fps'], out['width'] / out['height'])
    metrics = {'version': VERSION, 'source': {'kind': 'run', 'path': str(master)},
               'master': vid, 'expectedFrames': expected, 'checks': checks, 'pass': all(checks.values()),
               'take': {'wallSeconds': result.get('wallSeconds'), 'captureFps': result.get('captureFps')},
               'picture': pic,
               'cut_check': {'expected': hard, 'soft': soft, 'matched': len(matched), 'missed': missed, 'extra': extra},
               'loudness': loudness.measure(master) if vid['audio'] else None,
               'camera': cams, 'framing': framing, 'text': texts}
    metrics['dialogue'] = _dialogue(it, vid['seconds'])
    metrics['balance'] = _balance(it)
    cards = {}
    for t in texts['items']:
        if t['kind'] == 'card':     # a full-frame card hides the camera: a still picture under it is right
            cards.setdefault(t['shot'], []).append((t['start'], t['end']))
    metrics['_moving'] = _moving_frames(tl.clips(it), cams, vid['frames'], cards)
    metrics['warnings'] = _warnings(metrics)
    metrics.pop('_moving')
    (it.measure / 'metrics.json').write_text(json.dumps(metrics, indent=2) + '\n')
    write_report(metrics, it.measure / 'report.md', title=f'{plan["name"]} {it.name}', plan=plan)
    return metrics


def measure_video(path, start=None, end=None, out=None):
    """Measures any video file (or the stretch from `start` to `end` seconds) into `out`/metrics.json + report.md."""
    path = Path(path)
    vid = probe(path)
    pic, sig = _picture(path, vid['fps'], start, end)
    metrics = {'version': VERSION, 'source': {'kind': 'video', 'path': str(path.resolve()), 'from': start, 'to': end},
               'master': vid, 'picture': pic, 'loudness': loudness.measure(path, start, end) if vid['audio'] else None}
    metrics['warnings'] = _warnings(metrics)
    if out:
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        _write_signals(sig, out / 'signals.csv')
        (out / 'metrics.json').write_text(json.dumps(metrics, indent=2) + '\n')
        write_report(metrics, out / 'report.md', title=path.name + (f' {start or 0:g}-{end:g} s' if end else ''))
    return metrics
