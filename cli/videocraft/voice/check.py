"""`videocraft voice check <iteration>`: did the dialogue land where the resolver said it would?

Three measurements, each within TOL frames (2 at 60 fps, 33 ms):
  captions  every caption word's first frame on screen (take/shots/<shot>/text.json) against the aligned onset of
            that word in the line (voice.json): round((at + start) * fps)
  cuts      for every cut-on line, the first frame of the next clip in the cut (cut/timeline.json) against the cut
            word's onset as it plays in the cut
  voice     each line found in the master's sound track: the line's loudness envelope (5 ms blocks) cross-correlated
            with the master's around where the mix put it (cut/audio.json); the lag and the correlation, and the
            master's loudness while the line plays against the master as a whole
Standard library only (ffmpeg decodes).
"""
import array
import json
import math
import subprocess
from pathlib import Path

from videocraft import tools
from videocraft.paths import ROOT

TOL = 2
RATE = 8000
BLOCK = 40   # 5 ms at 8 kHz


def _decode(path, start=None, seconds=None):
    cmd = [tools.ffmpeg() or 'ffmpeg', '-v', 'error']
    if start is not None:
        cmd += ['-ss', f'{max(0.0, start):.4f}']
    if seconds is not None:
        cmd += ['-t', f'{seconds:.4f}']
    cmd += ['-i', str(path), '-vn', '-ac', '1', '-ar', str(RATE), '-f', 'f32le', '-']
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    a = array.array('f')
    a.frombytes(raw[:len(raw) // 4 * 4])
    return a


def _envelope(x):
    out = []
    for i in range(0, len(x) - BLOCK + 1, BLOCK):
        s = 0.0
        for v in x[i:i + BLOCK]:
            s += v * v
        out.append(math.sqrt(s / BLOCK))
    return out


def _corr(a, b):
    n = min(len(a), len(b))
    if n < 4:
        return 0.0
    a, b = a[:n], b[:n]
    ma, mb = sum(a) / n, sum(b) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((y - mb) ** 2 for y in b))
    return num / (da * db) if da > 0 and db > 0 else 0.0


def _text_items(path):
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    items = data.get('items', data) if isinstance(data, dict) else data
    return [i for i in items if isinstance(i, dict) and i.get('kind') == 'caption']


def check(it, say=print):
    from videocraft.audio import timeline as tl
    plan = it.plan()
    fps = int(plan['output']['fps'])
    f = it.path / 'voice.json'
    lines = json.loads(f.read_text()) if f.exists() else it.edit().get('dialogue') or []
    if not lines:
        say(f'No dialogue in {it.path} (no say cues)')
        return {'pass': True, 'lines': []}
    report = {'fps': fps, 'tolerance_frames': TOL, 'captions': [], 'cuts': [], 'voice': []}

    # Captions: the word frames the mod drew against the onsets of the line.
    for e in lines:
        shown = e['words'][:e['cut_on']['index']] if e.get('cut_on') else e['words']
        items = _text_items(it.take / 'shots' / e['shot'] / 'text.json')
        cap = next((c for c in items if abs(float(c.get('cue_at', -1)) - e['at']) < 0.5 / fps
                    and [w['w'] for w in c.get('words', [])][:len(shown)] == [w['word'].lstrip('*') for w in shown]), None)
        if shown and cap is None:
            report['captions'].append({'line': e['id'], 'ok': False, 'why': 'no caption with these words in text.json'})
        elif shown:
            errs = [cw['frame'] - round((e['at'] + w['start']) * fps) for cw, w in zip(cap['words'], shown)]
            report['captions'].append({'line': e['id'], 'ok': max(map(abs, errs)) <= TOL, 'max_frames': max(map(abs, errs)), 'errors': errs})
        if e.get('cut_on') and e.get('carried_to'):
            rest = e['words'][e['cut_on']['index']:]
            items = _text_items(it.take / 'shots' / e['carried_to'] / 'text.json')
            cap = next((c for c in items if [w['w'] for w in c.get('words', [])] == [w['word'].lstrip('*') for w in rest]), None)
            if cap is None:
                report['captions'].append({'line': e['id'] + ' (carried)', 'ok': False, 'why': f'no carried caption in {e["carried_to"]}'})
            else:
                t0 = e['cut_on']['frame'] / fps
                errs = [cw['frame'] - max(0, round((e['at'] + w['start'] - t0) * fps)) for cw, w in zip(cap['words'], rest)]
                report['captions'].append({'line': e['id'] + ' (carried)', 'ok': max(map(abs, errs)) <= TOL,
                                           'max_frames': max(map(abs, errs)), 'errors': errs})

    # Cuts: the next clip starts on the word.
    timeline = tl.load(it)
    for e in lines:
        if not e.get('cut_on'):
            continue
        clips = timeline.shot_clips(e['shot'])
        start = round(e['at'] * fps)
        clip = next((c for c in clips if c.contains(start)), clips[0] if clips else None)
        if clip is None:
            report['cuts'].append({'line': e['id'], 'ok': False, 'why': f'shot {e["shot"]} is not in the cut'})
            continue
        onset = clip.out_frame(start) + (e['at'] * fps - start) + e['words'][e['cut_on']['index']]['start'] * fps
        nxt = next((c for c in timeline.clips if c.out_start >= clip.out_end), None)
        cut = nxt.out_start if nxt else clip.out_end
        report['cuts'].append({'line': e['id'], 'word': e['cut_on']['word'], 'onset_frame': round(onset, 2), 'cut_frame': cut,
                               'error_frames': round(cut - onset, 2), 'ok': abs(cut - onset) <= TOL})

    # Voice: in the master, where the mix put it.
    master = it.cut / 'master.mp4'
    placed = {}
    af = it.cut / 'audio.json'
    if af.exists():
        for v in json.loads(af.read_text()).get('voice', []):
            placed.setdefault((v['shot'], Path(v['file']).name), []).append(v['time'])
    if master.exists():
        from videocraft.audio import loudness
        try:
            whole = loudness.measure(master)['integrated']
        except RuntimeError:
            whole = None
        report['master_lufs'] = whole
        for e in lines:
            if not e.get('file'):
                continue
            times = placed.get((e['shot'], Path(e['file']).name))
            if not times:
                report['voice'].append({'line': e['id'], 'ok': False, 'why': 'not placed by the mix (cut/audio.json)'})
                continue
            t = times[0]
            wav = Path(e['file']) if Path(e['file']).is_absolute() else ROOT / e['file']
            ref = _envelope(_decode(wav))
            pad = 0.15
            seg = _envelope(_decode(master, t - pad, len(ref) * BLOCK / RATE + 2 * pad))
            off = int(round(min(pad, t) * RATE / BLOCK))
            best = max(((_corr(ref, seg[off + lag:]), lag) for lag in range(-off, int(pad * RATE / BLOCK) + 1)
                        if off + lag >= 0), default=(0.0, 0))
            r, lag = best
            speech = e['words'][0]['start'], e['words'][-1]['end']
            try:
                during = loudness.measure(master, start=t + speech[0], duration=max(0.4, speech[1] - speech[0]))['integrated']
            except RuntimeError:
                during = None
            lag_ms = lag * BLOCK / RATE * 1000
            report['voice'].append({'line': e['id'], 'time': round(t, 3), 'lag_ms': round(lag_ms, 1), 'corr': round(r, 3),
                                    'lufs_during': during, 'ok': abs(lag_ms) <= TOL * 1000 / fps and r >= 0.5})
    else:
        report['voice_note'] = 'no cut/master.mp4 (take only?)'
    report['pass'] = all(x['ok'] for k in ('captions', 'cuts', 'voice') for x in report[k])
    report['lines'] = [e['id'] for e in lines]
    out = it.path / 'measure'
    out.mkdir(exist_ok=True)
    (out / 'voice.json').write_text(json.dumps(report, indent=2) + '\n')
    for c in report['captions']:
        say(f'CAPTION  {c["line"]:<20} {"ok  " if c["ok"] else "FAIL"} ' + (f'max {c["max_frames"]} frame(s) off {c["errors"]}' if 'errors' in c else c.get('why', '')))
    for c in report['cuts']:
        say(f'CUT      {c["line"]:<20} {"ok  " if c["ok"] else "FAIL"} ' + (f'on "{c["word"]}": next clip at frame {c["cut_frame"]}, word at {c["onset_frame"]} ({c["error_frames"]:+} frames)' if 'cut_frame' in c else c.get('why', '')))
    for c in report['voice']:
        say(f'VOICE    {c["line"]:<20} {"ok  " if c["ok"] else "FAIL"} ' + (f'at {c["time"]:.3f} s: lag {c["lag_ms"]:+.0f} ms, r {c["corr"]:.2f}, {c["lufs_during"]} LUFS while it speaks (master {report.get("master_lufs")})' if 'lag_ms' in c else c.get('why', '')))
    say(f'RESULT   {"PASS" if report["pass"] else "FAIL"} dialogue check, {len(lines)} line(s); {out / "voice.json"}')
    return report
