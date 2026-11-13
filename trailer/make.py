#!/usr/bin/env python3
"""Builds the videocraft trailer: timeline → frames (trailer/render.swift) → x264, a mixed and mastered sound track,
the 16:9 master, the 9:16 cut and a poster. Standard library only, like the CLI.

    python3 trailer/make.py                     both layouts, audio, exports (runs/trailer/)
    python3 trailer/make.py --layout h          one layout (h: 1920x1080, v: 1080x1920)
    python3 trailer/make.py --stills 0,600,…    PNG stills of those frames into runs/trailer/stills/<layout>/
    python3 trailer/make.py --strip 16:20       a strip of every 4th frame between two times, for looking at motion
    python3 trailer/make.py --audio-only        only the sound track
    python3 trailer/make.py capture <file>…     copy command output into trailer/data/, local paths shortened

Everything on screen comes from trailer/trailer.toml and trailer/data/ (real command output, scores, hashes, word
timings); footage comes from runs/ (see trailer/README.md for the runs it needs).
"""
import argparse
import array
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tomllib
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / 'runs' / 'trailer'
DATA = HERE / 'data'
sys.path.insert(0, str(ROOT / 'cli'))

from videocraft import tools  # noqa: E402
from videocraft.audio import loudness  # noqa: E402
from videocraft.audio import library  # noqa: E402

SR = 48000
LAYOUTS = {'h': (1920, 1080), 'v': (1080, 1920)}


def say(*a):
    print(*a, flush=True)


# ---------------------------------------------------------------- data

def shorten(text):
    """Local absolute paths → repo-relative (`./…`) and `~`, so no machine's folders appear on screen or in git."""
    text = text.replace(str(ROOT) + '/', './').replace(str(ROOT), '.')
    text = re.sub(r'/Users/[^/\s]+/\.t3/worktrees/videocraft/[^/\s]+/', './', text)
    text = re.sub(r'/Users/[^/\s]+/Documents/Projects/videocraft/', './', text)
    return re.sub(r'/Users/[^/\s]+', '~', text)


def capture(paths):
    DATA.mkdir(exist_ok=True)
    for p in paths:
        p = Path(p)
        (DATA / p.name).write_text(shorten(p.read_text(encoding='utf-8')), encoding='utf-8')
        say(f'captured {p.name} → {(DATA / p.name).relative_to(ROOT)}')


def data_lines(name):
    return (DATA / name).read_text(encoding='utf-8').splitlines()


def find_line(lines, pattern):
    rx = re.compile(pattern)
    for l in lines:
        if rx.search(l):
            return l
    say(f'WARNING  no captured line matches /{pattern}/: left out')
    return None


def logo_quads():
    """assets/icon.svg's pixels as quads in its 64-unit box, ordered for the assembly (top face first)."""
    svg = (ROOT / 'assets' / 'icon.svg').read_text(encoding='utf-8')
    quads = []
    for gi, g in enumerate(re.finditer(r'<g transform="matrix\(([^)]*)\)">(.*?)</g>', svg, re.S)):
        a, b, c, d, e, f = map(float, g.group(1).split())
        for m in re.finditer(r'<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)" fill="(#[0-9a-fA-F]{6})"/>',
                             g.group(2)):
            x, y, w, h = map(float, m.groups()[:4])
            pts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
            tp = [[a * px + c * py + e, b * px + d * py + f] for px, py in pts]
            cx = sum(p[0] for p in tp) / 4
            cy = sum(p[1] for p in tp) / 4
            quads.append({'p': tp, 'c': m.group(5), 'face': gi, 'cx': cx, 'cy': cy})
    for q in quads:
        dist = math.hypot(q['cx'] - 32, q['cy'] - 30) / 32
        q['o'] = round(min(1.0, q['face'] * 0.22 + dist * 0.35), 4)
        for k in ('face', 'cx', 'cy'):
            del q[k]
    return quads


def media(spec):
    """Footage keys → files under runs/, with their frame sizes."""
    out = {}
    for key, rel in spec['media'].items():
        f = ROOT / 'runs' / rel
        if not f.exists():
            raise SystemExit(f'trailer: footage {key} missing: runs/{rel} (trailer/README.md lists the runs)')
        p = subprocess.run([tools.ffprobe(), '-v', 'error', '-select_streams', 'v', '-show_entries',
                            'stream=width,height', '-of', 'csv=p=0', str(f)], capture_output=True, text=True)
        w, h = map(int, p.stdout.strip().split(',')[:2])
        out[key] = {'file': str(f), 'w': w, 'h': h}
    return out


def timeline(spec, layout):
    w, h = LAYOUTS[layout]
    scenes = []
    for sc in spec['scene']:
        sc = json.loads(json.dumps(sc))
        if sc['type'] == 'make':
            cmd = sc['command_v'] if layout == 'v' and 'command_v' in sc else sc['command']
            lines = [{'t': sc['type_at'], 'text': '$ ' + cmd, 'typed': True, 'cps': sc['cps']}]
            for o in sc['out'] + [n for n in sc['nodes'] if 'match' in n]:
                if 'typed' in o:
                    typed = o['typed_v'] if layout == 'v' and 'typed_v' in o else o['typed']
                    lines.append({'t': o['t'], 'text': '$ ' + typed, 'typed': True, 'cps': o.get('cps', sc['cps'])})
                    continue
                line = find_line(data_lines(spec['data'][o.get('data', 'make')]), o['match'])
                if line is not None:
                    lines.append({'t': o['t'], 'text': line})
            sc['lines'] = sorted(lines, key=lambda l: l['t'])
            story = find_line(data_lines(spec['data']['make']), '^STORY')
            sc['footer'] = sc['footer'].format(story=story.split()[1] if story else '?')
        if sc['type'] == 't3':
            sc['keys'] = human_keys(sc['prompt'], sc['type_from'], sc['type_to'])
            for m in sc['messages']:
                if m['kind'] == 'text':
                    m['text'] = m['text'].format(story=story_line())
                for l in m.get('lines', []):
                    if 'text' not in l:
                        text = find_line(data_lines(spec['data'][l.get('data', 'make')]), l['match'])
                        if l.get('strip'):
                            text = re.sub(l['strip'], '', text)
                        l['text'] = re.sub(r'\s+\./stories/\S+$', '', text or '')
        if sc['type'] == 'endmodern':
            cmd = sc['command_v'] if layout == 'v' and 'command_v' in sc else sc['command']
            sc['keys'] = human_keys(cmd.replace('\n', ''), sc['type_from'], sc['type_to'])
        if sc['type'] == 'mcchat':
            for l in sc['lines']:
                if 'mc' in l:
                    continue
                text = l.get('text') or find_line(data_lines(spec['data'][l.get('data', 'make')]), l['match'])
                if text is None:
                    continue
                if l.get('strip'):
                    text = re.sub(l['strip'], '', text)
                text = re.sub(r'\s+\./stories/\S+$', '', text)   # the story's file path: the chat has no room
                l['mc'] = mc_term(text)
        if sc['type'] == 'mcmonitor':
            for c in sc['clips']:
                if layout == 'v' and 'toast_v' in c:
                    c['toast'] = c['toast_v']
                if c.get('shot_dir'):
                    c['track'] = raw_track(ROOT / 'runs' / c['shot_dir'], c['in'], c['dur'] * c.get('step', 1))
                else:
                    c['track'] = shot_track(c['run'], c['in'], c['dur'] * c.get('step', 1))
                c['shot'] = c['track'].pop('shot')
        if sc['type'] == 'mcvoice':
            edit = json.loads((ROOT / 'runs' / 'nibs-vs-duke/0012/edit.json').read_text(encoding='utf-8'))
            sc['words'] = [{'w': w['word'].replace('*', ''), 'at': round(dl['at'] + w['start'] - sc['clip']['in'], 3)}
                           for dl in edit['dialogue'] if dl['shot'] == sc['shot'] for w in dl['words']]
        if sc['type'] == 'mcedit':
            sc.update(edit_data('nibs-vs-duke/0012'))
        if sc['type'] == 'mcscores':
            r = json.loads((DATA / spec['data']['review']).read_text(encoding='utf-8'))
            sc['criteria'] = [[k.replace('_', ' '), v] for k, v in r['criteria'].items()]
            sc['climb'] = r['climb']
            if layout == 'v' and 'toast_v' in sc:
                sc['toast'] = sc['toast_v']
        if sc['type'] == 'chat':
            for m in sc['messages']:
                if m['kind'] != 'tool':
                    continue
                lines = []
                for l in m['lines']:
                    text = l.get('text') or find_line(data_lines(spec['data'][l.get('data', 'make')]), l['match'])
                    if text is not None:
                        lines.append({'t': l['t'], 'text': text})
                m['lines'] = lines
        if sc['type'] == 'monitor':
            for c in sc['clips']:
                c['track'] = shot_track(c['run'], c['in'], c['dur'] * c.get('step', 1))
                c['shot'] = c['track'].pop('shot')
        if sc['type'] == 'timeline':
            sc.update(edit_data('nibs-vs-duke/0012'))
        if sc['type'] == 'voice':
            v = json.loads((DATA / spec['data']['voice']).read_text(encoding='utf-8'))
            sc['peaks'] = v['peaks']
            sc['words'] = v['words']
            sc['voice_len'] = v['seconds']
            sc['line_id'] = v['id']
            sc['line_info'] = sc['line_info'].format(**v)
            if v.get('cut'):
                sc['cut'] = v['cut']
            check = data_lines(spec['data']['voice_check'])
            sc['lines'] = [{'t': sc['check_at'] - 0.6, 'text': '$ ' + sc['check_command'], 'typed': True, 'cps': 40}]
            for i, m in enumerate(sc['check']):
                line = find_line(check, m)
                if line is not None:
                    sc['lines'].append({'t': sc['check_at'] + i * sc['check_step'], 'text': line})
        if sc['type'] == 'determinism':
            rows = [l.split(',') for l in data_lines(spec['data']['framemd5']) if l and not l.startswith('#')]
            sc['hashes'] = [[int(r[0]), r[1], r[2]] for r in rows[1:]]
            meta = json.loads((DATA / spec['data']['framemd5_meta']).read_text(encoding='utf-8'))
            sc['total'] = meta['frames']
            sc['step'] = meta['step']
            if meta['identical'] != meta['frames']:
                raise SystemExit('trailer: the two takes do not match; the determinism scene would not be true')
        if sc['type'] == 'review':
            r = json.loads((DATA / spec['data']['review']).read_text(encoding='utf-8'))
            sc['criteria'] = [[k.replace('_', ' '), v] for k, v in r['criteria'].items()]
            sc['rounds'] = [[x['round'], x['average']] for x in r['rounds']]
            sc['average'] = f'{r["average"]:.2f}'
            sc['pass'] = r['pass_line']
        scenes.append(sc)
    return {
        'width': w, 'height': h, 'fps': spec['fps'], 'frames': round(spec['seconds'] * spec['fps']),
        'ffmpeg': tools.ffmpeg(), 'colors': spec['colors'], 'media': media(spec), 'scenes': scenes,
        'chapters': spec.get('chapter', []), 'logo': logo_quads(), 'mc': str(mc_assets()),
    }


def story_line(run='nibs-vs-duke/0012'):
    """One plain line for the agent's story step, counted from the finished run: its shots and voiced lines."""
    rd = ROOT / 'runs' / run
    shots = sum(1 for l in (rd / 'script.toml').read_text(encoding='utf-8').splitlines() if l.strip() == '[[shot]]')
    lines = len(json.loads((rd / 'voice.json').read_text(encoding='utf-8')))
    return f'Story drafted: {shots} shots, {lines} voiced lines.'


def human_keys(text, start, end, seed=7):
    """When each character of `text` is typed, between `start` and `end`: a human rhythm (intervals that vary, a
    pause after each word, a longer one after punctuation), scaled to fit; about 7-8 characters a second."""
    import random
    rnd = random.Random(f'{seed}:{text}')
    gaps = []
    for i, ch in enumerate(text):
        g = rnd.uniform(0.7, 1.35)
        if i and text[i - 1] == ' ':
            g += rnd.uniform(0.6, 1.3)
        if i and text[i - 1] in ',.:;!?':
            g += 1.2
        gaps.append(g)
    scale = (end - start) / sum(gaps)
    out, at = [], start
    for g in gaps:
        at += g * scale
        out.append(round(at, 3))
    return out


def mc_assets():
    """The game's GUI, font, item and map textures, unpacked from the local client jar into runs/trailer/mc/ (read at
    render time, never committed)."""
    root = OUT / 'mc' / 'assets' / 'minecraft' / 'textures'
    if not (root / 'font' / 'ascii.png').exists():
        import zipfile
        jar = Path(os.environ.get('VIDEOCRAFT_CLIENT_JAR') or Path.home() / '.gradle/caches/fabric-loom/26.3/minecraft-client.jar')
        with zipfile.ZipFile(jar) as z:
            for n in z.namelist():
                if n.startswith(('assets/minecraft/textures/gui/', 'assets/minecraft/textures/font/', 'assets/minecraft/font/',
                                 'assets/minecraft/textures/map/', 'assets/minecraft/textures/item/')):
                    z.extract(n, OUT / 'mc')
    return root


def mc_term(text):
    """CLI output in the game's chat colours: the first word dark grey, verdicts green, the rest grey."""
    if text.startswith('$ '):
        return '§8$ §f' + text[2:]
    words = text.split(' ')
    out = []
    for i, w in enumerate(words):
        if w in ('PASS', 'ok', 'locked', 'READY'):
            out.append('§a' + w + '§7')
        elif i == 0 and w.isupper() and len(w) >= 3:
            out.append('§8' + w + '§7')
        else:
            out.append(w)
    return '§7' + ' '.join(out)


def raw_track(shot_dir, start, seconds):
    """The recording monitor's data for a shot's own video (no cut): frames.csv from `start` seconds."""
    fr = {int(r['frame']): r for r in read_csv(shot_dir / 'frames.csv')}
    ac = {}
    if (shot_dir / 'actors.csv').exists():
        for r in read_csv(shot_dir / 'actors.csv'):
            ac.setdefault(int(r['frame']), []).append(r)
    frames, cam, actors = [], [], {}
    for k in range(int(seconds * 30) + 1):
        f = min(max(fr), round((start + k / 30) * 60))
        row = fr[f]
        frames.append(f)
        cam.append([round(float(row['cam_x']), 2), round(float(row['cam_z']), 2), round(float(row['cam_yaw']), 1)])
        for a in ac.get(f, []):
            actors.setdefault(a['actor'], []).append([round(float(a['x']), 2), round(float(a['z']), 2)])
    pts = [p[:2] for p in cam] + [p for ps in actors.values() for p in ps]
    xs, zs = [p[0] for p in pts], [p[1] for p in pts]
    pad = max(4.0, 0.25 * max(max(xs) - min(xs), max(zs) - min(zs)))
    return {'shot': shot_dir.name, 'f': frames, 'c': cam, 'n': len(fr), 'a': [{'id': k, 'p': v} for k, v in actors.items() if k != 'player'],
            'b': [min(xs) - pad, min(zs) - pad, max(xs) + pad, max(zs) + pad]}


def read_csv(path):
    import csv
    with open(path, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def shot_track(run, master_in, seconds):
    """What the recording monitor shows over a clip of a run's cut: the shot and its frame numbers, the camera's
    top-view path and yaw (frames.csv) and every actor's position (actors.csv), sampled every 2nd frame (30 Hz)."""
    rd = ROOT / 'runs' / run
    tl = json.loads((rd / 'cut' / 'timeline.json').read_text(encoding='utf-8'))
    fps = tl['fps']
    frames, cam, actors, shot = [], [], {}, None
    cache = {}
    for k in range(int(seconds * 30) + 1):
        m = round((master_in + k / 30) * fps)
        clip = next((c for c in tl['clips'] if c['kind'] == 'shot' and c['out_start'] <= m < c['out_start'] + c['out_frames']), None)
        if clip is None:
            continue
        shot = shot or clip['shot']
        if clip['shot'] not in cache:
            sd = rd / 'take' / 'shots' / clip['shot']
            fr = {int(r['frame']): r for r in read_csv(sd / 'frames.csv')}
            ac = {}
            if (sd / 'actors.csv').exists():
                for r in read_csv(sd / 'actors.csv'):
                    ac.setdefault(int(r['frame']), []).append(r)
            cache[clip['shot']] = (fr, ac)
        fr, ac = cache[clip['shot']]
        f = clip['src_in'] + round((m - clip['out_start']) * clip.get('speed', 1.0))
        row = fr.get(f) or fr[max(fr)]
        frames.append(f)
        cam.append([round(float(row['cam_x']), 2), round(float(row['cam_z']), 2), round(float(row['cam_yaw']), 1)])
        for a in ac.get(f, []):
            actors.setdefault(a['actor'], []).append([round(float(a['x']), 2), round(float(a['z']), 2)])
    pts = [p[:2] for p in cam] + [p for ps in actors.values() for p in ps]
    xs, zs = [p[0] for p in pts], [p[1] for p in pts]
    pad = max(2.0, 0.12 * max(max(xs) - min(xs), max(zs) - min(zs)))
    n = len(cache[shot][0])
    return {'shot': shot, 'f': frames, 'c': cam, 'n': n, 'b': [min(xs) - pad, min(zs) - pad, max(xs) + pad, max(zs) + pad],
            'a': [{'id': k, 'p': v} for k, v in actors.items() if k != 'player']}


def edit_data(run):
    """The edit of a finished run, as the timeline scene draws it: clips, voice lines, every sound effect, the music
    cues, the bed's duck under voice, and the cuts that land on a word."""
    rd = ROOT / 'runs' / run
    tl = json.loads((rd / 'cut' / 'timeline.json').read_text(encoding='utf-8'))
    edit = json.loads((rd / 'edit.json').read_text(encoding='utf-8'))
    audio = json.loads((rd / 'cut' / 'audio-original.json').read_text(encoding='utf-8'))
    fps = tl['fps']
    clips = [[c['out_start'] / fps, c['out_frames'] / fps, c.get('shot') or '', c['kind']] for c in tl['clips']]
    secs = {d['file']: d['seconds'] for d in edit['dialogue']}
    voice = [[round(v['time'], 3), round(secs.get(v['file'], 1.0), 3)] for v in audio['voice']]
    cuts = []
    for dl in edit['dialogue']:
        if dl.get('cut_on'):
            i = next(i for i, c in enumerate(tl['clips']) if c.get('shot') == dl['shot'])
            c = tl['clips'][i]
            cuts.append([round((c['out_start'] + c['out_frames']) / fps, 3), dl['cut_on']['word']])
    return {'seconds': tl['frames'] / fps, 'clips': clips, 'voice': voice, 'cuts': cuts,
            'sfx': [round(e['time'], 3) for e in audio['events']],
            'music_cues': [[c['time'], c['do']] for c in audio['music'].get('cues', [])],
            'duck_db': float(edit.get('music', {}).get('duck', -9)),
            'facts': f'{run.replace("/", " · ")}  timeline.json\n{len(clips)} clips · {tl["frames"] / fps:.2f} s\n'
                     f'{len(voice)} voiced lines · {len(audio["events"])} sound events\n'
                     f'{len(cuts)} cuts on a spoken word'}


# ---------------------------------------------------------------- picture

def renderer():
    exe = OUT / 'bin' / 'render'
    src = HERE / 'render.swift'
    if not exe.exists() or exe.stat().st_mtime < src.stat().st_mtime:
        exe.parent.mkdir(parents=True, exist_ok=True)
        say('swiftc  trailer/render.swift')
        subprocess.run(['swiftc', '-O', str(src), '-o', str(exe)], check=True)
    return exe


def write_timeline(spec, layout):
    OUT.mkdir(parents=True, exist_ok=True)
    tl = timeline(spec, layout)
    path = OUT / f'timeline-{layout}.json'
    path.write_text(json.dumps(tl), encoding='utf-8')
    return path, tl


def picture(spec, layout):
    path, tl = write_timeline(spec, layout)
    w, h = tl['width'], tl['height']
    out = OUT / f'picture-{layout}.mp4'
    say(f'render  {layout} {w}x{h} {tl["frames"]} frames → {out.relative_to(ROOT)}')
    enc = subprocess.Popen([tools.ffmpeg(), '-y', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'bgra', '-s', f'{w}x{h}',
                            '-r', str(tl['fps']), '-i', '-', '-vf', 'scale=out_color_matrix=bt709:out_range=tv,format=yuv420p',
                            '-c:v', 'libx264', '-preset', 'slow', '-crf', '14', '-tune', 'animation',
                            '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', str(out)],
                           stdin=subprocess.PIPE)
    ren = subprocess.Popen([str(renderer()), str(path)], stdout=enc.stdin)
    ren.wait()
    enc.stdin.close()
    enc.wait()
    if ren.returncode or enc.returncode:
        raise SystemExit(f'trailer: render exit {ren.returncode}, encode exit {enc.returncode}')
    return out


def stills(spec, layout, frames):
    path, _ = write_timeline(spec, layout)
    d = OUT / 'stills' / layout
    d.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(renderer()), str(path), '--png', str(d), '--at', ','.join(map(str, frames))], check=True)
    return [d / f'f{f:05d}.png' for f in frames]


# ---------------------------------------------------------------- sound

def read_wav(path):
    """A wav as float channels at 48 kHz (ffmpeg converts anything else)."""
    p = subprocess.run([tools.ffmpeg(), '-v', 'error', '-i', str(path), '-f', 'f32le', '-ar', str(SR), '-ac', '2', '-'],
                       capture_output=True, check=True)
    buf = array.array('f')
    buf.frombytes(p.stdout)
    return buf[0::2], buf[1::2]


def read_wav_part(path, start, dur):
    p = subprocess.run([tools.ffmpeg(), '-v', 'error', '-ss', f'{start:.4f}', '-t', f'{dur:.4f}', '-i', str(path), '-vn',
                        '-f', 'f32le', '-ar', str(SR), '-ac', '2', '-'], capture_output=True, check=True)
    buf = array.array('f')
    buf.frombytes(p.stdout)
    return buf[0::2], buf[1::2]


def env_gain(points, n):
    """Per-sample linear gain from [(seconds, dB)] keyframes (None or -inf = silent), linear in dB between them."""
    pts = sorted((float(t), (-120.0 if db is None else float(db))) for t, db in points)
    g = array.array('f', bytes(4 * n))
    j = 0
    for i in range(n):
        t = i / SR
        while j + 1 < len(pts) and pts[j + 1][0] <= t:
            j += 1
        if t <= pts[0][0]:
            db = pts[0][1]
        elif j + 1 >= len(pts):
            db = pts[-1][1]
        else:
            (t0, d0), (t1, d1) = pts[j], pts[j + 1]
            db = d0 + (d1 - d0) * (t - t0) / (t1 - t0)
        g[i] = 0.0 if db <= -119 else 10 ** (db / 20)
    return g


# The UI's sounds, as (the game's event, the library's stand-in, dB).
UI = {'send': ('ui.button.click', 'click', -10), 'line': ('block.note_block.hat', 'tick', -26),
      'toast_in': ('ui.toast.in', 'whoosh-fast', -8), 'toast_out': ('ui.toast.out', None, -10),
      'bar': ('entity.experience_orb.pickup', 'tick', -20), 'climb': ('ui.toast.challenge_complete', 'success-chime', -8),
      'end': ('entity.player.levelup', 'sparkle', -10), 'clip': ('block.note_block.hat', 'tick', -24),
      'cut': ('ui.button.click', 'click', -18), 'key': (None, 'click-soft', -24), 'whoosh': (None, 'whoosh', -14),
      'card': (None, 'whoosh-fast', -20)}


def ui_events(spec):
    out = []
    for sc in spec['scene']:
        ty = sc['type']
        if ty == 't3':
            out += [(k, 'key') for k in human_keys(sc['prompt'], sc['type_from'], sc['type_to'])]
            out.append((sc['send_at'], 'send'))
            for m in sc['messages']:
                out += [(l['t'], 'line') for l in m.get('lines', [])]
            out.append((sc['cut_at'] + 0.3, 'whoosh'))
        if ty == 'endmodern':
            out += [(k, 'key') for k in human_keys(sc['command'], sc['type_from'], sc['type_to'])]
            out.append((sc['from'] + 0.2, 'end'))
        if ty == 'card':
            out.append((sc['from'] + 0.15, 'card'))
        if ty == 'mcchat':
            out.append((sc['send_at'], 'send'))
            out += [(l['t'], 'line') for l in sc['lines']]
        if ty == 'mcmonitor':
            for c in sc['clips']:
                if c.get('overlay', 'toast') == 'toast':
                    out += [(c['at'] + 0.15, 'toast_in'), (c['at'] + c['dur'] - 0.5, 'toast_out')]
                if c.get('label'):
                    out.append((c['at'] + 0.2, 'clip'))
        if ty == 'mcedit':
            out += [(sc['slide_at'] + i * 0.04 * 3, 'clip') for i in range(12)]
            ed = edit_data('nibs-vs-duke/0012')
            out += [(edit_reach(sc, c[0]), 'cut') for c in ed['cuts'] if c[0] <= sc['scrub_to']]
        if ty == 'mcscores':
            out += [(sc['panel_at'] + 0.7 + i * 0.35, 'bar') for i in range(4)]
            out.append((sc['panel_at'] + 0.4 + 4 * 0.35 + 0.5, 'climb'))
        if ty == 'mcend':
            out.append((sc['from'] + 0.1, 'end'))
    return out


def edit_reach(sc, sec):
    """When the edit scene's playhead reaches `sec` of the film (it plays at speed, then scrubs on, inOutCubic)."""
    p0 = sc['scrub_at'] - sc['from']
    if sec <= p0:
        return sc['from'] + sec
    lo, hi = 0.0, 1.0
    for _ in range(40):
        mid = (lo + hi) / 2
        u = 4 * mid ** 3 if mid < 0.5 else 1 - (-2 * mid + 2) ** 3 / 2
        lo, hi = (mid, hi) if p0 + u * (sc['scrub_to'] - p0) < sec else (lo, mid)
    return sc['scrub_at'] + sc['scrub_dur'] * lo


def voice_lines(run, start, dur):
    """A take's voiced lines alone (no game sound), as (seconds into the take's cut, wav): the original-audio twin's
    stand-in for the take's own mix."""
    rd = ROOT / run
    tl = json.loads((rd / 'cut' / 'timeline.json').read_text(encoding='utf-8'))
    fps = tl['fps']
    out = []
    for v in json.loads((rd / 'voice.json').read_text(encoding='utf-8')):
        clip = next((c for c in tl['clips'] if c.get('shot') == v['shot']), None)
        if clip is None:
            continue
        at = (clip['out_start'] + v['start_frame'] - clip.get('src_in', 0)) / fps
        if start - 0.05 <= at < start + dur:
            out.append((at - start, ROOT / v['file']))
    return out


def game_sound(event):
    from videocraft.audio import assets
    files = assets.event_files('minecraft:' + event)
    got = assets.decode(files[0], channels=1)
    return got


def sound(spec, variant='game'):
    """The sound track: `game` (the game's music, GUI sounds and the film's own mix) or `original` (a synth bed,
    library sounds and the film's original-audio mix: no Mojang audio)."""
    a = spec['audio']
    n = int(spec['seconds'] * SR)
    left = array.array('f', bytes(4 * n))
    right = array.array('f', bytes(4 * n))
    env = env_gain(a['music'], n)
    if variant == 'game':
        from videocraft.audio import assets, resolve
        file, row, why = resolve.pick_track(a['mood'], seconds=spec['seconds'])
        say(f'music   {file} ({why}) from {row["entry"]:.2f} s')
        l, r = read_wav_part(assets.object_path(assets.sound_key(file)), row['entry'], spec['seconds'])
    else:
        bed = OUT / 'audio' / 'bed.wav'
        if not bed.exists():
            bed.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run([str(ROOT / 'bin' / 'videocraft'), 'audio', 'synth', '-o', str(bed), '--style', a['style'],
                            '--bpm', str(a['bpm']), '--seconds', str(spec['seconds'] + 2), '--seed', str(a['seed'])], check=True)
        l, r = read_wav(bed)
    for i in range(min(n, len(l))):
        left[i] += l[i] * env[i]
        right[i] += r[i] * env[i]
    for t0, what in ui_events(spec):
        event, stand_in, db = UI[what]
        if variant == 'game' and event:
            mono = game_sound(event)
        elif stand_in:
            mono = library.render(stand_in, 1)
        else:
            continue
        place(left, right, mono, t0, db, 0.0)
    for v in a['film']:
        # Each clip's own sound: the film's game mix or its original-audio twin; a take with only a game mix
        # (`game = …`) plays only in the game sound track.
        if 'game' in v:
            if variant != 'game':
                for at, wav in voice_lines(v['voice_run'], v['start'], v['dur']) if v.get('voice_run') else []:
                    l1, r1 = read_wav(wav)
                    place(left, right, l1, v['t'] + at, v.get('db', 0) - 1.0, 0.0)
                continue
            src = ROOT / v['game']
        else:
            src = ROOT / (a['film_game'] if variant == 'game' else a['film_original'])
        fl, fr = read_wav_part(src, v['start'], v['dur'])
        fade = int(0.15 * SR)
        g = 10 ** (v.get('db', 0) / 20)
        start = int(v['t'] * SR)
        for i in range(len(fl)):
            e = min(1.0, i / fade, (len(fl) - i) / fade) * g
            j = start + i
            if 0 <= j < n:
                left[j] += fl[i] * e
                right[j] += fr[i] * e
    raw = OUT / 'audio' / f'mix-{variant}.f32'
    raw.parent.mkdir(parents=True, exist_ok=True)
    inter = array.array('f', bytes(8 * n))
    inter[0::2] = left
    inter[1::2] = right
    raw.write_bytes(inter.tobytes())
    out = OUT / 'audio' / f'master-{variant}.wav'
    m = loudness.master(raw, out, target=a['lufs'], ceiling=a['ceiling'])
    say(f'audio   {out.relative_to(ROOT)}  {m["integrated"]:.1f} LUFS, true peak {m["true_peak"]:.1f} dBTP')
    return out


def place(left, right, mono, t, db, pan):
    g = 10 ** (db / 20)
    gl, gr = g * math.cos((pan + 1) * math.pi / 4) * math.sqrt(2), g * math.sin((pan + 1) * math.pi / 4) * math.sqrt(2)
    start = int(t * SR)
    for i, x in enumerate(mono):
        j = start + i
        if j >= len(left):
            break
        if j >= 0:
            left[j] += x * gl
            right[j] += x * gr


# ---------------------------------------------------------------- exports

def export(spec, layout, pic, audio, suffix=''):
    name = spec['exports'][layout].replace('.mp4', suffix + '.mp4')
    out = OUT / name
    subprocess.run([tools.ffmpeg(), '-y', '-v', 'error', '-i', str(pic), '-i', str(audio), '-map', '0:v', '-map', '1:a',
                    '-c:v', 'copy', '-c:a', 'aac', '-b:a', '256k', '-shortest', '-movflags', '+faststart', str(out)],
                   check=True)
    m = loudness.measure(out)
    say(f'EXPORT  {out.relative_to(ROOT)}  {m["integrated"]:.1f} LUFS, true peak {m["true_peak"]:.1f} dBTP')
    return out


# Where the owner watches the cuts: each new full cut is copied there as soon as it exists.
DELIVER = {'h': ['videocraft-trailer-1080p60.mp4', 'videocraft-films/4-trailer.mp4'],
           'v': ['videocraft-trailer-9x16.mp4', 'videocraft-films/4-trailer-9x16.mp4']}


def deliver(out, layout):
    if os.environ.get('VIDEOCRAFT_TRAILER_NO_DELIVER'):
        return
    for rel in DELIVER[layout]:
        dest = Path.home() / 'Downloads' / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(out, dest)
        say(f'COPY    {dest}')


def poster(spec, layout):
    f = round(spec['poster'] * spec['fps'])
    png = stills(spec, layout, [f])[0]
    out = OUT / spec['exports']['poster']
    shutil.copy(png, out)
    say(f'POSTER  {out.relative_to(ROOT)} (frame {f})')


def strip(spec, layout, a, b, every=4, cols=8):
    fps = spec['fps']
    frames = list(range(round(a * fps), round(b * fps), every))
    pngs = stills(spec, layout, frames)
    w, h = LAYOUTS[layout]
    tw = 480 if layout == 'h' else 270
    th = tw * h // w
    out = OUT / 'stills' / f'strip-{layout}-{a}-{b}.png'
    inputs = []
    for p in pngs:
        inputs += ['-i', str(p)]
    n = len(pngs)
    rows = -(-n // cols)
    graph = ''.join(f'[{i}:v]scale={tw}:{th}[s{i}];' for i in range(n))
    graph += ''.join(f'[s{i}]' for i in range(n)) + f'xstack=inputs={n}:layout=' + '|'.join(
        f'{(i % cols) * tw}_{(i // cols) * th}' for i in range(n)) + f':fill=black[o]'
    subprocess.run([tools.ffmpeg(), '-y', '-v', 'error', *inputs, '-filter_complex', graph, '-map', '[o]', str(out)], check=True)
    say(f'STRIP   {out}  ({n} frames, every {every}, {rows} rows)')
    return out


def need(words):
    """Reading time for a piece of text: 0.5 s and 0.3 s a word, never under 1.5 s."""
    return max(1.5, 0.5 + 0.3 * words)


def pacing(spec):
    """Every text element with the time it is complete on screen against its reading time, and how many elements
    ask to be read in each second. Writes runs/trailer/pacing.md; returns the number of failures."""
    rows = []   # (name, text, complete_from, until)
    def add(name, text, a, b):
        rows.append((name, re.sub(r'§.', '', text), a, b))
    def kin(text, at, stagger=0.08, dur=0.8):   # a kinetic line is complete when its last word has risen
        return at + stagger * (len(text.split()) - 1) + dur * 0.8
    for sc in spec['scene']:
        ty, f0, f1 = sc['type'], sc['from'], sc['to']
        if ty == 'card':
            lines = sc['text'].split('\n')
            add('card', ' '.join(lines), kin(lines[-1], f0 + 0.2 + 0.25 * (len(lines) - 1), dur=0.9), f1 - 0.55)
        if ty == 't3':
            keys = human_keys(sc['prompt'], sc['type_from'], sc['type_to'])
            # Typed, then sent: it stays on screen throughout, moving from the composer to the thread.
            add('prompt', sc['prompt'], keys[-1], sc['cut_at'])
            for m in sc['messages']:
                if m['kind'] == 'text':
                    text = m['text'].format(story=story_line())
                    add('agent reply', text, m['t'] + len(text.split()) / m['wps'], sc['cut_at'])
                else:
                    add('tool call', m['title'] + ' ' + m['command'], m['t'] + 0.3, sc['cut_at'])
                    for l in m['lines']:
                        add('tool output', l.get('text') or l.get('match', ''), l['t'] + 0.3, sc['cut_at'])
        if ty == 'mcmonitor':
            for c in sc['clips']:
                ov = c.get('overlay', 'toast')
                if c.get('label'):
                    add('step label', c['label'], kin(c['label'], c['at'] + 0.15, 0.07, 0.7), c['at'] + c['dur'] - 0.35)
                if 'toast' in ov:
                    add('toast', c['toast_title'] + ' ' + ' '.join(c['toast']), c['at'] + 0.15 + 0.6, c['at'] + c['dur'] - 0.5)
                if 'rec' in ov:
                    add('boss bar (REC)', 'REC frame/frames', c['at'], c['at'] + c['dur'])
                if 'map' in ov:
                    add('map (graphic)', 'top view', c['at'], c['at'] + c['dur'])
        if ty in ('mcedit', 'mcscores') and sc.get('heading'):
            add('heading', sc['heading'], kin(sc['heading'], f0 + 0.15), sc['heading_until'] - 0.2)
        if ty == 'mcedit':
            add('timeline title', sc['title'], sc['slide_at'], f1)
            ed = edit_data('nibs-vs-duke/0012')
            cuts = [c for c in ed['cuts'] if c[0] <= sc['scrub_to']]
            ts = [edit_reach(sc, c[0]) for c in cuts]
            for i, c in enumerate(cuts):
                add('cut chip', f'Cut on "{c[1].strip("*")}"', ts[i] + 0.2, ts[i + 1] if i + 1 < len(cuts) else f1)
        if ty == 'mcscores':
            r = json.loads((DATA / spec['data']['review']).read_text(encoding='utf-8'))['climb']
            at = sc['panel_at']
            add('panel heading', 'REVIEW ROUND 8 → 9 Scored up by fresh reviewers', at + 0.6, f1)
            for i, (name, x, y) in enumerate(r['improved']):
                add('score row', f'{name} {x} → {y}', at + 0.4 + i * 0.35 + 1.1, f1)
            done = at + 0.4 + len(r['improved']) * 0.35
            for c in r['changed']:
                add('what changed', c, done + 1.0, f1)
            add('average / pass line', 'Average 6.28 → 6.61 · Pass line 7.0: not there yet', done + 1.7, f1)
        if ty == 'endmodern':
            end = f1 - 0.8
            add('name', sc['name'], f0 + 1.1, end)
            add('tagline', sc['tagline'], kin(sc['tagline'], f0 + 0.8, 0.05), end)
            add('command', sc['command'], sc['type_to'], end)
            add('url', sc['url'], sc['url_at'] + 0.6, end)
            add('disclaimer', sc['disclaimer'], sc['url_at'] + 1.0, end)
    out = ['| Element | Text | On screen complete | Needs | |', '|:--|:--|--:|--:|:--|']
    fails = 0
    for name, text, a, b in rows:
        n = need(len(text.split()))
        ok = (b - a) >= n - 1e-6
        fails += not ok
        out.append(f'| {name} | {text[:60]} | {a:.2f}-{b:.2f} s = {b - a:.2f} s | {n:.2f} s | {"ok" if ok else "SHORT"} |')
    out += ['', '| Second | Panels with text on screen |', '|--:|--:|']
    worst = 0
    for s in range(int(spec['seconds']) + 1):
        panel = {'prompt': 'app', 'agent reply': 'app', 'tool call': 'app', 'tool output': 'app', 'panel heading': 'scores',
                 'score row': 'scores', 'what changed': 'scores', 'average / pass line': 'scores',
                 'timeline title': 'timeline', 'cut chip': 'timeline', 'name': 'end', 'tagline': 'end', 'command': 'end',
                 'url': 'end', 'disclaimer': 'end'}
        c = len({panel.get(name, name) for name, _, a, b in rows if a <= s + 0.5 <= b})
        worst = max(worst, c)
        out.append(f'| {s} | {c} |')
    (OUT / 'pacing.md').parent.mkdir(parents=True, exist_ok=True)
    (OUT / 'pacing.md').write_text('\n'.join(out) + '\n', encoding='utf-8')
    say(f'PACING  {len(rows)} elements, {fails} short of their reading time; at most {worst} panel(s) asking to be read at '
        f'once; runs/trailer/pacing.md')
    for l in out[2:2 + len(rows)]:
        if 'SHORT' in l:
            say('  ' + l)
    black_fail = 0
    for lay in ('h', 'v'):
        got = near_black(OUT / f'picture-{lay}.mp4')
        if got is None:
            say(f'BLACK   {lay}: not rendered yet (runs/trailer/picture-{lay}.mp4)')
            continue
        total, spans = got
        ok = total < BLACK_TARGET
        black_fail += not ok
        say(f'BLACK   {lay}: {total:.2f} s near-black (target under {BLACK_TARGET} s) {"ok" if ok else "OVER"}: '
            + (', '.join(f'{a:.1f}-{b:.1f}' for a, b in spans) or 'none'))
        (OUT / 'pacing.md').write_text((OUT / 'pacing.md').read_text(encoding='utf-8') +
            f'\nNear-black ({lay}): {total:.2f} s; spans ' + (', '.join(f'{a:.1f}-{b:.1f} s' for a, b in spans) or 'none') + '\n',
            encoding='utf-8')
    return fails + black_fail


BLACK_TARGET = 1.5


def near_black(video, rate=10):
    """Seconds of near-black picture: frames (sampled at `rate` a second) whose brightest pixel is under 80 of 255 in
    video range, i.e. nothing on screen but a dark canvas or a fade. Returns (seconds, [(from, to), …]) or None."""
    if not video.exists():
        return None
    p = subprocess.run([tools.ffmpeg(), '-v', 'error', '-i', str(video), '-vf',
                        f'fps={rate},scale=480:-2,signalstats,metadata=print:key=lavfi.signalstats.YMAX:file=-',
                        '-f', 'null', '-'], capture_output=True, text=True)
    times, dark = [], []
    t = None
    for line in p.stdout.splitlines():
        m = re.search(r'pts_time:([\d.]+)', line)
        if m:
            t = float(m.group(1))
        m = re.search(r'YMAX=([\d.]+)', line)
        if m and t is not None:
            times.append(t)
            dark.append(float(m.group(1)) < 80)
    spans, start = [], None
    for t, k in zip(times, dark):
        if k and start is None:
            start = t
        if not k and start is not None:
            spans.append((start, t))
            start = None
    if start is not None:
        spans.append((start, times[-1] + 1 / rate))
    return sum(dark) / rate, spans


def main(argv):
    if argv[:1] == ['capture']:
        capture(argv[1:])
        return 0
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--layout', choices=['h', 'v', 'both'], default='both')
    ap.add_argument('--stills', help='frame numbers, comma separated')
    ap.add_argument('--strip', help='FROM:TO seconds, every 4th frame')
    ap.add_argument('--every', type=int, default=4)
    ap.add_argument('--audio-only', action='store_true')
    ap.add_argument('--no-audio', action='store_true')
    ap.add_argument('--mux-only', action='store_true', help='reuse runs/trailer/picture-<layout>.mp4')
    ap.add_argument('--check', action='store_true', help='the pacing self-check only (runs/trailer/pacing.md)')
    args = ap.parse_args(argv)
    spec = tomllib.loads((HERE / 'trailer.toml').read_text(encoding='utf-8'))
    layouts = ['h', 'v'] if args.layout == 'both' else [args.layout]
    if argv[:1] == ['check'] or args.check:
        return 1 if pacing(spec) else 0
    if args.stills:
        for lay in layouts:
            for p in stills(spec, lay, [int(x) for x in args.stills.split(',')]):
                say(p)
        return 0
    if args.strip:
        a, b = map(float, args.strip.split(':'))
        for lay in layouts:
            strip(spec, lay, a, b, every=args.every)
        return 0
    audio = None if args.no_audio else {v: sound(spec, v) for v in ('game', 'original')}
    if args.audio_only:
        return 0
    for lay in layouts:
        pic = OUT / f'picture-{lay}.mp4' if args.mux_only else picture(spec, lay)
        if audio:
            out = export(spec, lay, pic, audio['game'])
            export(spec, lay, pic, audio['original'], suffix='-original-audio')
            deliver(out, lay)
    poster(spec, 'h')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
