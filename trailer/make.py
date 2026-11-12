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
        if sc['type'] == 'voice':
            v = json.loads((DATA / spec['data']['voice']).read_text(encoding='utf-8'))
            sc['peaks'] = v['peaks']
            sc['words'] = v['words']
            sc['voice_len'] = v['seconds']
            sc['line_id'] = v['id']
            sc['line_info'] = sc['line_info'].format(**v)
            sc['cut'] = v.get('cut')
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
        'chapters': spec.get('chapter', []), 'logo': logo_quads(),
    }


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


def sound(spec):
    a = spec['audio']
    n = int(spec['seconds'] * SR)
    left = array.array('f', bytes(4 * n))
    right = array.array('f', bytes(4 * n))
    bed = OUT / 'audio' / 'bed.wav'
    if not bed.exists() or a.get('rebuild_bed'):
        bed.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([str(ROOT / 'bin' / 'videocraft'), 'audio', 'synth', '-o', str(bed), '--style', a['style'],
                        '--bpm', str(a['bpm']), '--seconds', str(spec['seconds'] + 2), '--seed', str(a['seed']), '--stems'],
                       check=True)
    for stem, points in a['stems'].items():
        l, r = read_wav(bed.with_name(f'bed-{stem}.wav'))
        g = env_gain(points, n)
        for i in range(min(n, len(l))):
            left[i] += l[i] * g[i]
            right[i] += r[i] * g[i]
    events = list(a.get('sfx', [])) + scene_sounds(spec)
    # Typing: one soft click per character of the typed command (two alternating seeds, a little level wobble).
    for sc in spec['scene']:
        if sc['type'] == 'make':
            cmd = '$ ' + sc['command']
            for k in range(2, len(cmd)):
                if cmd[k] == ' ':
                    continue
                events.append({'t': sc['type_at'] + k / sc['cps'], 'sound': 'click-soft', 'db': a['type_db'] - (k % 3) * 1.5,
                               'seed': 1 + k % 3, 'pan': ((k * 7) % 5 - 2) * 0.06})
    for e in events:
        mono = library.render(e['sound'], e.get('seed', 1))
        place(left, right, mono, e['t'], e.get('db', -12), e.get('pan', 0.0))
    for v in a.get('voice', []):
        f = ROOT / v['file']
        if not f.exists():
            say(f'audio   voice {v["file"]} missing: the voice section plays without it')
            continue
        l, _ = read_wav(f)
        place(left, right, l, v['t'], v.get('db', 0), 0.0)
    raw = OUT / 'audio' / 'mix.f32'
    inter = array.array('f', bytes(8 * n))
    inter[0::2] = left
    inter[1::2] = right
    raw.write_bytes(inter.tobytes())
    out = OUT / 'audio' / 'master.wav'
    m = loudness.master(raw, out, target=a['lufs'], ceiling=a['ceiling'])
    say(f'audio   {out.relative_to(ROOT)}  {m["integrated"]:.1f} LUFS, true peak {m["true_peak"]:.1f} dBTP')
    return out


def scene_sounds(spec):
    """The small sounds that follow the picture: a pop as each pipeline step lights, ticks while the frame counter
    runs (slowing with it), a click per voice-check line, a tick per review bar."""
    out = []
    for sc in spec['scene']:
        if sc['type'] == 'make':
            out += [{'t': n['t'], 'sound': 'pop-high', 'db': -19, 'seed': 1 + i % 3} for i, n in enumerate(sc['nodes'])]
        if sc['type'] == 'determinism':
            # The counter eases out (1 - (1-u)^3): a tick at every 1/16 of the count lands where the count does.
            run, done = sc['run'], sc['done']
            for k in range(1, 16):
                u = 1 - (1 - k / 16) ** (1 / 3)
                out.append({'t': run + u * (done - run), 'sound': 'tick', 'db': -26})
        if sc['type'] == 'voice':
            out += [{'t': sc['check_at'] + i * sc['check_step'], 'sound': 'click-soft', 'db': -17} for i in range(len(sc['check']))]
        if sc['type'] == 'review':
            out += [{'t': sc['from'] + 0.6 + i * 0.08, 'sound': 'tick', 'db': -24} for i in range(9)]
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

def export(spec, layout, pic, audio):
    name = spec['exports'][layout]
    out = OUT / name
    subprocess.run([tools.ffmpeg(), '-y', '-v', 'error', '-i', str(pic), '-i', str(audio), '-map', '0:v', '-map', '1:a',
                    '-c:v', 'copy', '-c:a', 'aac', '-b:a', '256k', '-shortest', '-movflags', '+faststart', str(out)],
                   check=True)
    m = loudness.measure(out)
    say(f'EXPORT  {out.relative_to(ROOT)}  {m["integrated"]:.1f} LUFS, true peak {m["true_peak"]:.1f} dBTP')
    return out


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
    args = ap.parse_args(argv)
    spec = tomllib.loads((HERE / 'trailer.toml').read_text(encoding='utf-8'))
    layouts = ['h', 'v'] if args.layout == 'both' else [args.layout]
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
    audio = None if args.no_audio else sound(spec)
    if args.audio_only:
        return 0
    for lay in layouts:
        pic = OUT / f'picture-{lay}.mp4' if args.mux_only else picture(spec, lay)
        if audio:
            export(spec, lay, pic, audio)
    poster(spec, 'h')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
