"""The sound sheet of a review packet: what the sound reviewer judges instead of hearing. `sound.md` lists every
placed effect (cut/audio.json), every voice line with its word onsets (voice.json), the music cues, the script's
visible actions and a per-shot table of what is heard, all in master frames (M) and shot frames (S) so a reviewer
can line a sound up with the strips; `sound/loudness-<k>.png` draws the master's loudness over time with the clips,
joins, black gaps, voice, effects and music cues under it. Owned by workstream (d)."""
import array
import json
import math
import statistics
import subprocess
from pathlib import Path

from videocraft import timeline, tools
from videocraft.measure import loudness as mloud
from videocraft.review.image import Canvas, text_width

ROW_SECONDS = 15.0       # seconds of the cut per chart row
PX_PER_S = 120           # 2 px a frame at 60 fps
PLOT_H = 220
TOP_DB, BOTTOM_DB = 0.0, -60.0
ENV_RATE = 24000         # samples a second for the peak envelope
TEXT_CUES = {'caption', 'title', 'lower_third', 'card', 'keycap', 'message', 'text'}
QUIET_CUES = {'place', 'stop', 'look', 'face'}
BG, INK, DIM, GRID = (18, 18, 22), (255, 255, 255), (150, 150, 160), (52, 52, 60)
CURVE, PEAK, JOIN, BLACK = (255, 210, 60), (70, 110, 150), (235, 235, 235), (90, 30, 30)
VOICE, GAME, SYNTH, MUSIC = (120, 200, 255), (130, 220, 120), (240, 140, 220), (255, 160, 80)
BAND = ((34, 34, 42), (44, 44, 54))


def momentary(path):
    """[(t, momentary LUFS)] every 100 ms of a file's sound (ebur128), or [] when it has none."""
    if not mloud.has_audio(path):
        return []
    cmd = [tools.ffmpeg(), '-hide_banner', '-nostdin', '-v', 'verbose', '-i', str(path), '-vn',
           '-filter_complex', 'ebur128=framelog=verbose', '-f', 'null', '-']
    return mloud.parse(subprocess.run(cmd, capture_output=True, text=True).stderr)[0]


def envelope(path, columns, seconds):
    """Peak level (dBFS) of each of `columns` equal slices of the sound, mono."""
    cmd = [tools.ffmpeg(), '-v', 'error', '-nostdin', '-i', str(path), '-vn', '-ac', '1', '-ar', str(ENV_RATE), '-f', 's16le', '-']
    data = subprocess.run(cmd, capture_output=True).stdout
    a = array.array('h')
    a.frombytes(data[:len(data) // 2 * 2])
    out = []
    per = ENV_RATE * seconds / max(1, columns)
    for k in range(columns):
        s = a[int(k * per):int((k + 1) * per)]
        peak = max(max(s), -min(s)) if len(s) else 0
        out.append(20 * math.log10(peak / 32768) if peak > 0 else -120.0)
    return out


def _load(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def _cue_frame(cue, fps):
    return round(float(cue.get('at', 0) or 0) * fps)


def gather(it, plan, clips, fps):
    """Everything heard and every visible action, in master frames: {events, voice, music, actions, gaps, skipped}."""
    audio = _load(it.cut / 'audio.json', {})
    by_shot = {}
    for c in clips:
        if c['kind'] == 'shot':
            by_shot.setdefault(c['shot'], []).append(c)

    def to_master(shot, sframe):
        for c in by_shot.get(shot, []):
            if c['src_in'] <= sframe < c['src_in'] + c['out_frames'] * c.get('speed', 1.0):
                return c['out_start'] + round((sframe - c['src_in']) / c.get('speed', 1.0))
        return None

    events = []
    for e in audio.get('events', []):
        m = round(float(e['time']) * fps)
        events.append({**e, 'm': m})
    lines = {}
    for v in _load(it.path / 'voice.json', []):
        lines.setdefault(v.get('file'), []).append(v)
    voice = []
    for v in audio.get('voice', []):
        meta = (lines.get(v.get('file')) or [{}]).pop(0) if lines.get(v.get('file')) else {}
        t0 = float(v['time'])
        words = [{'word': w['word'], 'm': round((t0 + float(w['start'])) * fps), 'end_m': round((t0 + float(w['end'])) * fps)}
                 for w in meta.get('words', [])]
        voice.append({'id': meta.get('id', ''), 'character': meta.get('character', ''), 'shot': v.get('shot'), 'text': meta.get('text', ''),
                      'm': round(t0 * fps), 'end_m': round((t0 + float(meta.get('seconds') or 0)) * fps), 'words': words,
                      'engine': meta.get('engine', ''), 'gain_db': v.get('gain_db', 0)})
    music = dict(audio.get('music') or {})
    music['cues'] = [{**c, 'm': round(float(c['time']) * fps)} for c in music.get('cues', [])]
    actions = []
    for shot in plan.get('shots', []):
        for cue in shot.get('timeline', []):
            do = cue.get('do')
            if not do or do in TEXT_CUES or do in QUIET_CUES:
                continue
            s = _cue_frame(cue, fps)
            m = to_master(shot['name'], s)
            if m is None:
                continue
            what = cue.get('id') or cue.get('text') or cue.get('to') or cue.get('name') or ''
            if isinstance(what, (list, dict)):
                what = ''
            actions.append({'shot': shot['name'], 'do': do, 'actor': cue.get('actor', ''), 's': s, 'm': m, 'what': str(what)[:60]})
    actions.sort(key=lambda a: a['m'])
    gaps = [{'m': c['out_start'], 'end_m': c['out_start'] + c['out_frames']} for c in clips if c['kind'] != 'shot']
    return {'audio': audio, 'events': sorted(events, key=lambda e: e['m']), 'voice': voice, 'music': music,
            'actions': actions, 'gaps': gaps, 'skipped': audio.get('skipped', [])}


def _short(event):
    return event.split(':', 1)[-1]


def _level(samples, a, b):
    """(median, max) momentary LUFS of the readings whose 400 ms window ends in [a, b) seconds; None when silent."""
    vals = [max(-120.0, m) for t, m in samples if a < t <= b + 1e-6]
    if not vals:
        return None, None
    return round(statistics.median(vals), 1), round(max(vals), 1)


def markdown(it, plan, clips, fps, g, samples, charts):
    tc = lambda f: timeline.timecode(f, fps)
    audio, music = g['audio'], g['music']
    loud = audio.get('loudness') or {}
    L = ['# Sound sheet', '',
         'What the sound track holds, for a reviewer who cannot hear it. Every time is given as the cut\'s timecode, the '
         'master frame `M` (the number burnt into the strips and cut pairs) and, for effects, the shot\'s own frame `S`. '
         'An effect is in sync when its `M` is the frame of the action it belongs to in the strips (within 2 frames).', '']
    if not audio:
        L += ['**No cut/audio.json:** the cut has no mixed sound track (silent, or `audio = "none"`).', '']
        return '\n'.join(L)
    L += ['## Master', '',
          f'- Mode `{audio.get("mode")}`, {audio.get("sample_rate")} Hz, {audio.get("channels")} channels, {audio.get("seconds")} s.',
          f'- Integrated {loud.get("integrated")} LUFS, true peak {loud.get("true_peak")} dBTP, LRA {loud.get("lra")} LU '
          f'(mastering gain {loud.get("gain_db")} dB from {loud.get("before")} LUFS).',
          f'- {len(g["events"])} effects placed, {len(g["voice"])} voice lines, {len(g["skipped"])} logged sounds left out (listed at the end).',
          '- Chart' + ('s' if len(charts) > 1 else '') + ': ' + ', '.join(f'`{c}`' for c in charts) + ' (loudness over time, see the legend in each).', '']
    if g['gaps']:
        L += ['## Black gaps (the dips)', '', '| Black | Seconds | Momentary in the gap (median / max) | Mixed integrated |', '|:--|--:|:--|--:|']
        mixed = {round(x['time'] * fps): x for x in audio.get('black_gaps', [])}
        for gap in g['gaps']:
            med, mx = _level(samples, gap['m'] / fps + 0.4, gap['end_m'] / fps)
            x = mixed.get(gap['m'], {})
            L.append(f'| {tc(gap["m"])}-{tc(gap["end_m"])} (M{gap["m"]}-M{gap["end_m"]}) | {(gap["end_m"] - gap["m"]) / fps:.2f} | '
                     f'{med} / {mx} LUFS | {x.get("integrated", "-")} |')
        L += ['', 'Momentary loudness is a 400 ms window, so it lags an edge by up to 0.4 s; below -50 LUFS counts as silence.', '']
    L += ['## Music', '']
    if music:
        L.append(f'- Source `{music.get("source")}`' + ''.join(f', {k} `{music[k]}`' for k in ('style', 'track', 'bpm', 'key') if music.get(k))
                 + f'; starts at {music.get("at", 0)} s in the cut, level {music.get("level_db")} dB; ducks under voice'
                 + (' and marked effects' if any(e.get('duck') for e in g['events']) else '') + '; silent over black gaps unless `through_black`.')
        if music['cues']:
            L += ['', '| Cut | M | Cue |', '|--:|--:|:--|']
            L += [f'| {tc(c["m"])} | {c["m"]} | {c.get("do")} |' for c in music['cues']]
    else:
        L.append('No music bed.')
    L += ['', '## Voice lines', '']
    for v in g['voice']:
        words = ' '.join(f'{w["word"]}@M{w["m"]}' for w in v['words'])
        L.append(f'- **{v["character"] or "?"}** in `{v["shot"]}`, {tc(v["m"])}-{tc(v["end_m"])} (M{v["m"]}-M{v["end_m"]}): '
                 f'"{v["text"]}"' + (f' Word onsets: {words}' if words else ''))
    if not g['voice']:
        L.append('No voice.')
    L += ['', '## Per shot: what is seen to happen and what is heard', '',
          '| # | Clip | Cut | Momentary median / max | Actions in the script (M) | Heard (M) |', '|--:|:--|:--|:--|:--|:--|']
    for c in clips:
        a, b = c['out_start'], c['out_start'] + c['out_frames']
        med, mx = _level(samples, a / fps + 0.4, b / fps)
        acts = '; '.join(f'{x["do"]} {x["actor"]}{(" " + x["what"]) if x["what"] and x["do"] != "say" else ""} @{x["m"]}'
                         for x in g['actions'] if a <= x['m'] < b)
        heard = []
        for v in g['voice']:
            if a <= v['m'] < b:
                heard.append(f'voice {v["character"]} "{v["text"]}" @{v["m"]}')
        groups = {}
        for e in g['events']:
            if a <= e['m'] < b:
                groups.setdefault(_short(e['event']), []).append(e['m'])
        heard += [f'{k} @{",".join(str(m) for m in ms)}' for k, ms in groups.items()]
        heard += [f'music {x.get("do")} @{x["m"]}' for x in music.get('cues', []) if a <= x['m'] < b]
        L.append(f'| {c["index"] + 1} | {c["shot"] or "black"} | {tc(a)}-{tc(b)} | {med} / {mx} | {acts or "-"} | {"; ".join(heard) or "silence"} |')
    L += ['', '## Every placed effect', '',
          '| Cut | M | Shot | S | Source | Event | File | Gain dB | Notes |', '|--:|--:|:--|--:|:--|:--|:--|--:|:--|']
    for e in g['events']:
        notes = ', '.join(x for x, on in (('ducks the music', e.get('duck')), ('loops', e.get('looping')),
                                          (f'starts {e.get("offset", 0):.2f} s in', e.get('offset'))) if on)
        L.append(f'| {tc(e["m"])} | {e["m"]} | {e.get("shot")} | {e.get("frame")} | {e.get("source")} | {_short(e["event"])} | '
                 f'{e.get("file") or "-"} | {e.get("gain_db")} | {notes} |')
    if g['skipped']:
        groups = {}
        for x in g['skipped']:
            groups.setdefault((_short(x.get('event', '')), x.get('reason', '')), []).append(f'{x.get("shot")}:{x.get("frame")}')
        L += ['', '## Logged by the game but not placed', '', '| Event | Why | Count | Where (shot:S) |', '|:--|:--|--:|:--|']
        for (ev, why), where in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            L.append(f'| {ev} | {why} | {len(where)} | {", ".join(where[:6])}{" …" if len(where) > 6 else ""} |')
    return '\n'.join(L) + '\n'


def _x(t, row_start):
    return 70 + round((t - row_start) * PX_PER_S)


def _y(db, top):
    db = max(BOTTOM_DB, min(TOP_DB, db))
    return top + round((TOP_DB - db) / (TOP_DB - BOTTOM_DB) * PLOT_H)


def chart(path, clips, fps, g, samples, env, seconds, row_start, row_seconds, name):
    width = 70 + round(row_seconds * PX_PER_S) + 30
    bands_y, plot_y = 70, 110
    lanes_y = plot_y + PLOT_H + 30
    height = lanes_y + 4 * 30 + 20
    cv = Canvas(width, height, BG)
    row_end = row_start + row_seconds
    cv.text(8, 10, f'LOUDNESS  {name}  {timeline.timecode(round(row_start * fps), fps)}-{timeline.timecode(round(min(row_end, seconds) * fps), fps)}', 3, INK)
    leg = 8
    for label, col in (('MOMENTARY LUFS', CURVE), ('PEAK DBFS', PEAK), ('JOIN', JOIN), ('BLACK', BLACK), ('VOICE', VOICE),
                       ('GAME SFX', GAME), ('SYNTH SFX', SYNTH), ('MUSIC CUE', MUSIC)):
        cv.fill(leg, 44, 14, 14, col)
        leg += 20 + cv.text(leg + 20, 45, label, 2, DIM) + 14
    x0, x1 = _x(row_start, row_start), _x(min(row_end, seconds), row_start)
    # clips: alternating bands with their names; black gaps tinted over the plot
    for k, c in enumerate(clips):
        a, b = c['out_start'] / fps, (c['out_start'] + c['out_frames']) / fps
        if b <= row_start or a >= row_end:
            continue
        xa, xb = max(x0, _x(a, row_start)), min(x1, _x(b, row_start))
        col = BLACK if c['kind'] != 'shot' else BAND[k % 2]
        cv.fill(xa, bands_y, xb - xa, 32, col)
        label = f'{c["index"] + 1} {c["shot"] or "black"}'
        while label and text_width(label, 2) > xb - xa - 6:
            label = label[:-1]
        cv.text(xa + 3, bands_y + 9, label, 2, INK)
        if c['kind'] != 'shot':
            cv.fill(xa, plot_y, xb - xa, PLOT_H, (50, 22, 22))
    # grid: every 10 dB, the -14 target and the -50 silence line; a tick every second
    for db in range(0, -61, -10):
        cv.fill(x0, _y(db, plot_y), x1 - x0, 1, GRID)
        cv.text(8, _y(db, plot_y) - 6, f'{db}', 2, DIM)
    for db, col in ((-14, (90, 120, 90)), (-50, (120, 70, 70))):
        cv.fill(x0, _y(db, plot_y), x1 - x0, 2, col)
    for s in range(math.ceil(row_start), int(min(row_end, seconds)) + 1):
        x = _x(s, row_start)
        cv.fill(x, plot_y, 1, PLOT_H, GRID)
        cv.text(x - 10, plot_y + PLOT_H + 6, timeline.timecode(s * fps, fps)[:-3], 2, DIM)
    # peak envelope as bars, momentary loudness as a line
    per_col = len(env) / max(1e-9, seconds) / PX_PER_S
    for x in range(x0, x1):
        k = int(((x - 70) / PX_PER_S + row_start) * PX_PER_S * per_col)
        if 0 <= k < len(env):
            y = _y(env[k], plot_y)
            cv.fill(x, y, 1, plot_y + PLOT_H - y, PEAK)
    prev = None
    for t, m in samples:
        t0 = t - 0.4          # the reading covers (t - 0.4, t]: draw it at the middle of its window
        tm = t0 + 0.2
        if tm < row_start or tm > row_end:
            prev = None
            continue
        x, y = _x(tm, row_start), _y(m if m != float('-inf') else BOTTOM_DB, plot_y)
        if prev:
            px, py = prev
            last = py
            for xx in range(px, x + 1):          # a 3 px line, joined column to column
                yy = py + round((y - py) * (xx - px) / max(1, x - px))
                cv.fill(xx - 1, min(yy, last) - 1, 3, abs(yy - last) + 3, CURVE)
                last = yy
        prev = (x, y)
    # joins
    for c in clips[1:]:
        t = c['out_start'] / fps
        if row_start <= t <= row_end:
            x = _x(t, row_start)
            for y in range(plot_y, plot_y + PLOT_H, 6):
                cv.fill(x, y, 1, 3, JOIN)
    # lanes: voice spans with word ticks, game and synth effects, music cues
    lanes = (('VOICE', lanes_y), ('GAME', lanes_y + 30), ('SYNTH', lanes_y + 60), ('MUSIC', lanes_y + 90))
    for label, y in lanes:
        cv.text(8, y + 6, label[:5], 2, DIM)
        cv.fill(x0, y + 24, x1 - x0, 1, GRID)
    inrow = lambda m: row_start <= m / fps < row_end
    for v in g['voice']:
        a, b = v['m'] / fps, max(v['end_m'], v['m'] + 1) / fps
        if b < row_start or a >= row_end:
            continue
        xa, xb = max(x0, _x(a, row_start)), min(x1, _x(b, row_start))
        cv.fill(xa, lanes[0][1] + 4, max(2, xb - xa), 18, (40, 70, 100))
        for w in v['words']:
            if inrow(w['m']):
                cv.fill(_x(w['m'] / fps, row_start), lanes[0][1] + 2, 2, 22, VOICE)
    for e in g['events']:
        if inrow(e['m']):
            y = lanes[1][1] if e.get('source') == 'game' else lanes[2][1]
            cv.fill(_x(e['m'] / fps, row_start), y + 2, 2, 22, GAME if e.get('source') == 'game' else SYNTH)
    for c in g['music'].get('cues', []):
        if inrow(c['m']):
            x = _x(c['m'] / fps, row_start)
            cv.fill(x, lanes[3][1] + 2, 2, 22, MUSIC)
            cv.text(x + 4, lanes[3][1] + 6, str(c.get('do', '')).upper(), 2, MUSIC)
    return cv.png(path)


def build(it, plan, clips, fps, total, out):
    """Writes sound.md and sound/loudness-<k>.png into the packet folder `out`; returns the chart paths (relative)."""
    g = gather(it, plan, clips, fps)
    master = it.cut / 'master.mp4'
    seconds = total / fps
    samples = momentary(master) if master.exists() else []
    charts = []
    if samples:
        (out / 'sound').mkdir(exist_ok=True)
        env = envelope(master, round(seconds * PX_PER_S), seconds)
        rows = max(1, math.ceil(seconds / ROW_SECONDS - 0.05))
        row_seconds = seconds / rows
        for k in range(rows):
            p = out / 'sound' / f'loudness-{k + 1}.png'
            chart(p, clips, fps, g, samples, env, seconds, k * row_seconds, row_seconds, f'{plan["name"]} {it.name}  {k + 1}/{rows}')
            charts.append(str(p.relative_to(out)))
    (out / 'sound.md').write_text(markdown(it, plan, clips, fps, g, samples, charts))
    return charts
