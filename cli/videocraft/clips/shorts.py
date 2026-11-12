"""Vertical shorts: `cut(it, moment=N | start, end, method)` -> clips/<n>/short-1080x1920.mp4 and clips/<n>/clip.json.

Two methods (docs/CLIPS.md):
  reshoot  the same script's shots in the range, taken again at 1080x1920 (the plan is deterministic: the same
           performance), each shot's `[shot.vertical]` camera keys applied by the compiler and `--pull` scaling every
           rig's radius/distance; captions are drawn by the game for the vertical frame (and larger: SHORT_CAPTION);
           then cut through the same edit (trims, push-ins mapped into the vertical frame, speed, looks).
  reframe  a crop of the 16:9 master that follows the subject (clips/reframe.py), or the whole frame over a blurred
           fill where the crop cannot hold the subjects or the text.
Either way the sound is the master's own mix over exactly the same frames (the take is the same performance), re-
mastered to -14 LUFS with 15 ms fades at both ends so the short loops without a click. No dip to black at the end:
it ends on the payoff plus a beat and loops. A cold start gets a hook in the first second (in the game when
re-shot, a bitmap-font band when re-framed).
"""
import copy
import json
import re
import statistics
import subprocess
from pathlib import Path

from videocraft import script as script_, tools
from videocraft.audio import loudness
from videocraft.clips import reframe, runs, timemap
from videocraft.measure import camera as cam, probe, text as text_

LONGEST = 60.0
LIMIT_MB = 50.0
SHORT_CAPTION = 77          # caption capital height in a vertical re-shoot (the default is 63)
HOOK_SECONDS = 1.4
OUT_W, OUT_H = 1080, 1920
SIZE_KEYS = ('radius', 'distance', 'min_distance')
TEXT_ACTIONS = ('caption', 'title', 'card', 'lower_third', 'keycap')


# ---- The range ----

def pick_range(it, m, moment=None, start=None, end=None):
    """(start, end, moment or None) in master seconds: a moment from clips/moments.json, or --from/--to snapped so it
    starts and ends on a cut or between words; at most LONGEST seconds."""
    words = timemap.words(m)
    cuts = m.boundaries()
    mo = None
    if moment is not None:
        f = it.path / 'clips' / 'moments.json'
        if not f.exists():
            raise SystemExit(f'No moments for {it.path}: videocraft clips find {it.path} first')
        found = {x['n']: x for x in json.loads(f.read_text())['moments']}
        if moment not in found:
            raise SystemExit(f'No moment {moment} in {f} (moments: {sorted(found)})')
        mo = found[moment]
        s, e = mo['start'], mo['end']
    else:
        s = timemap.snap_start(max(0.0, start or 0.0), cuts, words, tolerance=0.4)
        e = timemap.snap_end(min(m.seconds, end if end is not None else m.seconds), cuts, words, tolerance=0.4, ceiling=m.seconds)
    if e - s > LONGEST:
        limit = s + LONGEST
        options = [c for c in cuts if s < c <= limit] + [w.end for w in words if s < w.end <= limit]
        e = max(options) if options else limit
    if e - s <= 0:
        raise SystemExit(f'The range {s:.2f}-{e:.2f} s is empty')
    return s, e, mo


def folder_for(it, moment):
    base = it.path / 'clips'
    base.mkdir(exist_ok=True)
    if moment is not None:
        return base / str(moment['n'])
    k = 1 + max([int(p.name[1:]) for p in base.glob('r*') if p.name[1:].isdigit()], default=0)
    return base / f'r{k}'


# ---- Re-shoot ----

def map_point(x, y, width, height, ow=OUT_W, oh=OUT_H):
    """A landscape pixel to the vertical frame of a take with the same vertical field of view: the same scale on
    both axes, about the centre, clamped into the frame."""
    s = oh / height
    return min(ow, max(0.0, (x - width / 2) * s + ow / 2)), min(oh, max(0.0, y * s))


def _map_push(push, width, height):
    if isinstance(push, dict):
        push = dict(push)
        if 'x' in push or 'y' in push:
            push['x'], push['y'] = map_point(float(push.get('x', width / 2)), float(push.get('y', height / 2)), width, height)
        return push
    if isinstance(push, list):
        return [_map_push(p, width, height) for p in push]
    return push


def vertical_script(raw, plan, edit, timeline, pieces, name, hook=None, pull=1.0, fps=60, from_start=False, auto=None,
                    hook_in_game=True):
    """The vertical re-shoot of `pieces` ([(segment, src_in, src_out, frames)]) as a script dict."""
    width, height = plan['output']['width'], plan['output']['height']
    needed = [s.shot for s, *_ in pieces if s.kind == 'shot']
    if from_start and needed:    # every shot up to the last one needed: state a shot leaves for the next is kept
        names = [s.get('name') for s in raw.get('shot', [])]
        last = max(names.index(n) for n in needed if n in names)
        needed = names[:last + 1]
    out = copy.deepcopy({k: v for k, v in raw.items() if k not in ('shot', 'edit', 'output')})
    out['name'] = name
    out['output'] = {'width': OUT_W, 'height': OUT_H, 'fps': fps}
    shots = []
    for shot in raw.get('shot', []):
        if shot.get('name') not in needed:
            continue
        shot = copy.deepcopy(shot)
        if (auto or {}).get(shot['name']):
            shot['camera'] = copy.deepcopy(auto[shot['name']])
        cam_ = shot.get('camera') or {}
        if pull != 1.0:
            for key in SIZE_KEYS:
                if isinstance(cam_.get(key), (int, float)):
                    cam_[key] = round(cam_[key] * pull, 4)
        for cue in shot.get('cue', []) or []:
            if cue.get('do') == 'caption' and 'size' not in cue:
                cue['size'] = SHORT_CAPTION
            if cue.get('do') in TEXT_ACTIONS:   # screen positions (layout pixels) keep their place in the frame
                for key, a, b in (('x', width, OUT_W), ('y', height, OUT_H)):
                    if isinstance(cue.get(key), (int, float)):
                        cue[key] = round(cue[key] / (a / min(width, height) * 1080) * (b / min(OUT_W, OUT_H) * 1080), 1)
        shots.append(shot)
    clips, raw_clips = [], edit.get('clip') or []
    tl_clips = {c['index']: c for c in timeline.get('clips', [])}
    for k, (seg, src_in, src_out, frames) in enumerate(pieces):
        if seg.kind != 'shot':
            clips.append({'black': round(frames / fps, 4)})
            continue
        src = raw_clips[seg.clip] if seg.clip < len(raw_clips) else {'shot': seg.shot}
        clip = {'shot': seg.shot, 'in': int(src_in), 'out': int(src_out)}
        for key in ('speed', 'grade', 'frame', 'label', 'note'):
            if key in src:
                clip[key] = copy.deepcopy(src[key])
        if 'push' in src:
            clip['push'] = _map_push(copy.deepcopy(src['push']), width, height)
        look = (tl_clips.get(seg.clip) or {}).get('look') or {}
        for key in ('grade', 'frame'):
            if key in look and key not in clip:
                clip[key] = copy.deepcopy(look[key])
        full = tl_clips.get(seg.clip) or {}
        if 'fade_in' in src and src_in == full.get('src_in'):
            clip['fade_in'] = src['fade_in']
        if 'fade_out' in src and src_out == full.get('src_out'):
            clip['fade_out'] = src['fade_out']
        clips.append(clip)
    if hook and shots and hook_in_game:
        first = next((p for p in pieces if p[0].kind == 'shot'), None)
        if first:
            target = next(s for s in shots if s['name'] == first[0].shot)
            cue = {'at': round(first[1] / fps, 4), 'do': 'title', 'text': hook, 'position': 'top', 'style': 'pop', 'size': 84,
                   'hold': HOOK_SECONDS, 'shade': True}
            target.setdefault('cue', []).insert(0, cue)
    out['shot'] = shots
    out['edit'] = {'clip': clips, 'audio': 'none'}
    return out


def auto_vertical(plan, raw, m, pieces):
    """{shot: camera} for `fixed` shots (with no [shot.vertical] camera) whose staged subject leaves the vertical
    window of the landscape frame in over a tenth of the range: a locked-off camera cannot hold it in 9:16, so the
    re-shoot pans from the same eye (`locked` on the subject), as an operator shooting vertical would."""
    width, height = m.width, m.height
    half = reframe.crop_size(width, height)[0] / 2
    staged = {a.get('id') for a in plan.get('actors', [])}
    out = {}
    for seg, src_in, src_out, _ in pieces:
        if seg.kind != 'shot' or seg.shot in out:
            continue
        raw_shot = next((s for s in raw.get('shot', []) if s.get('name') == seg.shot), {})
        camera = raw_shot.get('camera') or {}
        if camera.get('rig') != 'fixed' or ((raw_shot.get('vertical') or {}).get('camera')) or 'eye' not in camera:
            continue
        xs, primary = subject_xs(seg, plan, raw_shot, None, width, height)
        if primary not in staged:
            continue
        seen = [f for f in range(src_in, src_out) if xs.get(f)]
        outside = sum(1 for f in seen if abs(xs[f][0] - width / 2) > 0.8 * half)
        if seen and outside > 0.1 * len(seen):
            locked = {'rig': 'locked', 'eye': camera['eye'], 'subject': primary, 'lag': 0.5,
                      'look': round(0.55 * cam.height_of(primary, plan), 2)}
            for key in ('fov', 'fov_ease', 'drift'):
                if key in camera:
                    locked[key] = camera[key]
            out[seg.shot] = locked
    return out


def reshoot(it, m, pieces, folder, hook, pull, say, timeout, from_start=False, notes=None):
    """Takes the vertical script; returns (picture path, vertical iteration)."""
    raw = script_.load(it.path / 'script.toml') if (it.path / 'script.toml').exists() else script_.load(it.path / 'script.json')
    plan, edit = it.plan(), it.edit()
    timeline = json.loads((it.cut / 'timeline.json').read_text()) if (it.cut / 'timeline.json').exists() else {'clips': []}
    name = re.sub(r'[^a-z0-9_-]', '-', f'{plan["name"][:39]}-vertical')
    auto = auto_vertical(plan, raw, m, pieces)
    for shot, camera in auto.items():
        line = f'shot {shot}: fixed -> locked on {camera["subject"]} (it leaves a 9:16 window of the landscape frame)'
        say('  re-shoot: ' + line)
        if notes is not None:
            notes.append(line)
    in_game = not text_at_start(pieces, m.fps)
    if hook and not in_game and notes is not None:
        notes.append('text is on screen in the first second: the hook is a band over the picture, not a game title')
    vs = vertical_script(raw, plan, edit, timeline, pieces, name, hook, pull, m.fps, from_start, auto, in_game)
    path = folder / 'vertical.json'
    path.write_text(json.dumps(vs, indent=2) + '\n')
    script_.compile_script(script_.load(path), str(path))   # fails here, not in the game, if the vertical script is wrong
    say(f'  re-shoot: {len(vs["shot"])} shot(s) at {OUT_W}x{OUT_H} ({path})')
    vit, code = runs.take(path, say=say, timeout=timeout)
    if code != 0 or not vit or not (vit.cut / 'master.mp4').exists():
        raise RuntimeError(f'the vertical take did not pass (exit {code}); see {vit.take / "game.log" if vit else path}')
    return vit.cut / 'master.mp4', vit, in_game


def text_at_start(pieces, fps):
    """Whether the take shows any text in the short's first HOOK_SECONDS (a game title there would replace it)."""
    left = int(HOOK_SECONDS * fps)
    for seg, src_in, src_out, frames in pieces:
        if left <= 0:
            break
        if seg.kind == 'shot':
            last = src_in + min(frames, left)
            if any(a <= last and b >= src_in for a, b, _, _ in text_boxes(seg, src_in, src_out)):
                return True
        left -= frames
    return False


# ---- Re-frame ----

def _rows(path):
    return cam.read_csv(path) if Path(path).exists() else []


def _point(text):
    try:
        x, y, z = (float(v) for v in str(text).split(','))
        return (x, y, z)
    except ValueError:
        return None


def subject_xs(seg, plan, raw_shot, subject, width, height):
    """{source frame: [x pixels of each subject seen]} for one clip's shot, primary subject first, and the subject's id."""
    d = timemap.shot_dir(seg)
    frames = _rows(d / 'frames.csv')
    actors = _rows(d / 'actors.csv')
    shot = next((s for s in plan['shots'] if s['name'] == seg.shot), {})
    hint = subject or ((raw_shot or {}).get('vertical') or {}).get('subject')
    point = _point(hint) if isinstance(hint, str) and ',' in hint else (tuple(hint) if isinstance(hint, list) and len(hint) == 3 else None)
    aspect = width / height
    if point:
        out = {}
        for r in frames:
            fov = r['lens_fov'] if isinstance(r.get('lens_fov'), float) else r['fov']
            p = cam.project(point, (r['cam_x'], r['cam_y'], r['cam_z']), r['cam_yaw'], r['cam_pitch'], fov, aspect)
            if p and 0 <= p[0] <= 1:
                out[int(r['frame'])] = [p[0] * width]
        return out, f'point {point}'
    named = [hint] if isinstance(hint, str) else []
    subjects = (shot.get('camera') or {}).get('subjects')
    if not named and isinstance(subjects, list):         # a two-shot: both, so the layout can tell they are apart
        named += [str(x) for x in subjects]
    main = cam.subject_of(shot) if not named else None   # the rig's subject (follow rigs: the player)
    if main:
        named.append(main)
    who = list(dict.fromkeys(named + [str(a['actor']) for a in actors]))
    tracks = {}
    for w in who:
        seen = {n: v for n, v in cam.subject_track(frames, actors, w, cam.height_of(w, plan), aspect)
                if v is not None and 0 <= v[0] <= 1 and 0 <= v[1] <= 1}
        if seen:
            tracks[w] = seen
    if not tracks:
        return {}, None
    size = {w: statistics.median(v[2] for v in t.values()) for w, t in tracks.items()}
    total = max(1, len(frames))
    # The primary: the named subject when it is in frame a third of the time, else the actor biggest in frame.
    primary = next((w for w in named if w in tracks and len(tracks[w]) >= total / 3), None) or max(size, key=size.get)
    # Others count (for "two subjects too far apart") only when named, or near the primary's size in frame.
    others = [w for w in tracks if w != primary and (w in named or size[w] >= 0.5 * size[primary])]
    out = {}
    for w in [primary] + others:
        for n, v in tracks[w].items():
            if w == primary or n in out:
                out.setdefault(n, []).append(v[0] * width)
    return out, primary


def text_boxes(seg, src_in, src_out):
    """[(first, last (inclusive), x0, x1)] of the text the take drew on frames of [src_in, src_out)."""
    data = timemap._json(timemap.shot_dir(seg) / 'text.json') or {}
    out = []
    for item in data.get('items', []):
        a, b = item.get('first_frame'), item.get('last_frame')
        if a is None or b is None or b < src_in or a >= src_out or not item.get('box'):
            continue
        out.append((a, b, item['box'][0], item['box'][2]))
    return out


def text_cut(boxes, frames_src, centres, cw):
    """Whether any text box leaves the crop on a frame it is on screen (re-framing would cut the words)."""
    for f, c in zip(frames_src, centres):
        for a, b, x0, x1 in boxes:
            if f is not None and a <= f <= b and (x0 < c - cw / 2 - 1 or x1 > c + cw / 2 + 1):
                return f'text "{x0}-{x1}" leaves the crop on source frame {f}'
    return None


def reframe_plan(it, m, pieces, subject=None):
    """Per clip: layout, crop centres per output frame, the subject's x per output frame and stats."""
    width, height = m.width, m.height
    cw, ch = reframe.crop_size(width, height)
    raws, plans, timelines = {}, {}, {}
    out = []
    for seg, src_in, src_out, frames in pieces:
        if seg.kind != 'shot':
            out.append({'kind': seg.kind, 'frames': frames, 'layout': 'fit', 'why': seg.kind, 'seg': seg, 'src_in': src_in})
            continue
        run = seg.run
        if run not in plans:
            plans[run] = json.loads((Path(run) / 'plan.json').read_text())
            try:
                raws[run] = script_.load(Path(run) / 'script.toml')
            except (OSError, script_.ScriptError):
                raws[run] = {}
            tf = Path(run) / 'cut' / 'timeline.json'
            timelines[run] = {c['index']: c for c in json.loads(tf.read_text()).get('clips', [])} if tf.exists() else {}
        raw_shot = next((s for s in raws[run].get('shot', []) if s.get('name') == seg.shot), None)
        xs, who = subject_xs(seg, plans[run], raw_shot, subject, width, height)
        pieces_of = (timelines[run].get(seg.clip) or {}).get('push') or []
        to_cut = reframe.push_map(pieces_of, width, height)
        enter = seg.out_start + src_in_offset(seg, src_in)    # the master frame where the range enters this clip
        targets, spreads, srcs = [], [], []
        for k in range(frames):
            f = seg.src_frame(enter + k)
            srcs.append(f)
            seen = [to_cut(f, x) for x in xs.get(f, [])] if f is not None else []
            seen = [x for x in seen if 0 <= x <= width]
            targets.append(seen[0] if seen else None)
            if len(seen) > 1:
                spreads.append(max(seen) - min(seen))
        spread = sorted(spreads)[len(spreads) // 2] if len(spreads) > len(targets) * 0.3 else None
        boxes = text_boxes(seg, src_in, src_out)
        layout, why = reframe.layout(spread, max((x1 - x0 for _, _, x0, x1 in boxes), default=0), cw)
        shot_cam = next((s.get('camera') or {} for s in plans[run]['shots'] if s['name'] == seg.shot), {})
        if layout == 'follow' and isinstance(shot_cam.get('subjects'), list) and len(shot_cam['subjects']) > 1 and not spreads:
            layout, why = 'fit', 'a two-shot whose second subject is not logged (no actors.csv): both are kept'
        centres = reframe.operator(targets, m.fps, cw, width) if layout == 'follow' else [width / 2] * frames
        if layout == 'follow' and boxes:
            why = text_cut(boxes, srcs, centres, cw)
            if why:
                layout, centres = 'fit', [width / 2] * frames
        out.append({'kind': 'shot', 'shot': seg.shot, 'frames': frames, 'layout': layout, 'why': why, 'subject': who,
                    'centres': centres, 'targets': targets, 'seg': seg, 'src_in': src_in,
                    'stats': reframe.stats(centres, targets, m.fps, cw) if layout == 'follow' else None})
    return out, cw


def src_in_offset(seg, src_in):
    """Master frames from the clip's start to where the range enters it."""
    if seg.src_map:
        import bisect
        return bisect.bisect_left(seg.src_map, src_in)
    return int(round((src_in - seg.src_in) / (seg.speed or 1.0)))


def reframe_render(it, m, a, plan, cw, folder):
    """The re-framed picture (no audio) of master frames [a, a + sum of frames)."""
    width, height, fps = m.width, m.height, m.fps
    graph = [f'[0:v]split={len(plan)}' + ''.join(f'[in{k}]' for k in range(len(plan)))]
    at = a
    for k, clip in enumerate(plan):
        n = clip['frames']
        head = f'[in{k}]trim=start_frame={at}:end_frame={at + n},setpts=PTS-STARTPTS,'
        if clip['layout'] == 'follow':
            cmd = folder / f'crop-{k}.cmd'
            cmd.write_text(reframe.sendcmd(clip['centres'], cw, width, fps))
            x0 = int(round(min(width - cw, max(0, clip['centres'][0] - cw / 2))))
            graph.append(head + f'sendcmd=f={cmd.name},crop={cw}:{height}:{x0}:0,scale={OUT_W}:{OUT_H}:flags=lanczos,setsar=1,format=yuv420p[v{k}]')
        else:
            graph.append(reframe.fit_chain(head, width, height, OUT_W, OUT_H, f'f{k}') + f'[v{k}]')
        at += n
    graph.append(''.join(f'[v{k}]' for k in range(len(plan))) + f'concat=n={len(plan)}:v=1:a=0,setpts=N/({fps}*TB)[v]')
    (folder / 'graph.txt').write_text(';\n'.join(graph) + '\n')
    picture = folder / 'picture.mp4'
    subprocess.run([tools.ffmpeg(), '-y', '-loglevel', 'error', '-i', str(it.cut / 'master.mp4'), '-filter_complex', ';'.join(graph),
                    '-map', '[v]', '-r', str(fps), '-c:v', 'libx264', '-preset', 'medium', '-crf', '17', '-pix_fmt', 'yuv420p', '-an',
                    picture.name], check=True, cwd=folder)
    return picture


def hook_band(path, text, width=OUT_W):
    """A dark band with the hook in the bitmap font (re-frame only: a re-shoot draws its hook in the game)."""
    from videocraft.review.image import Canvas, text_width as tw
    scale = 8
    while tw(text.upper(), scale) > width * 0.86 and scale > 3:
        scale -= 1
    h = 7 * scale + 64
    c = Canvas(width, h, (16, 16, 20))
    c.fill(0, h - 6, width, 6, (255, 226, 59))
    c.text((width - tw(text.upper(), scale)) // 2, 32, text.upper(), scale, (255, 255, 255))
    c.png(path)
    return path, h


# ---- Sound, export, checks ----

def audio_slice(master, start, seconds, out_wav, has_audio):
    """The master's mix over [start, start + seconds), faded 15 ms at both ends, re-mastered to -14 LUFS."""
    if not has_audio:
        return None
    raw = Path(out_wav).with_suffix('.f32')
    fade = 0.015
    subprocess.run([tools.ffmpeg(), '-y', '-v', 'error', '-ss', f'{start:.6f}', '-i', str(master), '-t', f'{seconds:.6f}', '-vn',
                    '-af', f'apad,atrim=0:{seconds:.6f},afade=t=in:d={fade},afade=t=out:st={max(0.0, seconds - fade):.6f}:d={fade}',
                    '-ac', '2', '-ar', '48000', '-f', 'f32le', str(raw)], check=True)
    result = loudness.master(raw, out_wav)
    gain, passes = result.get('gain_db', 0.0), result.get('passes', 1)
    while result.get('before') is not None and abs(loudness.TARGET - result['integrated']) > 0.3 and passes < 8:
        # A peaky slice (one loud hit over a quiet bed) needs more passes than the master's three to settle.
        gain = min(40.0, gain + loudness.TARGET - result['integrated'])
        loudness._render(raw, out_wav, gain, loudness.CEILING)
        passes += 1
        result = {**loudness.measure(out_wav), 'gain_db': round(gain, 2), 'passes': passes, 'before': result['before']}
    raw.unlink()
    return result


def export(picture, wav, frames, fps, out, hook=None):
    """picture (+ wav) -> out, exactly `frames` frames, H.264 high under LIMIT_MB (the quality steps down if not)."""
    seconds = frames / fps
    inputs = ['-i', str(picture)] + (['-i', str(wav)] if wav else [])
    vf = f'tpad=stop_mode=clone:stop=30,trim=end_frame={frames},setpts=N/({fps}*TB)'
    if hook:
        png, h, y = hook
        inputs += ['-loop', '1', '-framerate', str(fps), '-i', str(png)]
        hk = 2 if wav else 1
        graph = (f'[0:v]{vf}[b];[{hk}:v]format=yuv420p[h];'
                 f'[b][h]overlay=0:{y}:enable=\'lt(t,{HOOK_SECONDS})\':shortest=1,format=yuv420p[v]')
    else:
        graph = f'[0:v]{vf},format=yuv420p[v]'
    for crf in (18, 20, 23, 26, 29):
        subprocess.run([tools.ffmpeg(), '-y', '-loglevel', 'error', *inputs, '-filter_complex', graph, '-map', '[v]',
                        *(['-map', '1:a', '-c:a', 'aac', '-b:a', '192k'] if wav else ['-an']), '-r', str(fps), '-t', f'{seconds:.6f}',
                        '-c:v', 'libx264', '-preset', 'slow', '-crf', str(crf), '-profile:v', 'high', '-pix_fmt', 'yuv420p',
                        '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-movflags', '+faststart', str(out)], check=True)
        if out.stat().st_size <= LIMIT_MB * 1e6:
            return crf
    return crf


def vertical_text(vit, shots, fps):
    """Text layout problems of the vertical take's text.json (the 1080x1920 safe area and the rest)."""
    table, problems = [], []
    for shot in shots:
        f = vit.take / 'shots' / shot / 'text.json'
        if f.exists():
            items, size = text_.load(f, fps)
            t, p = text_.check(items, fps, size[0] or OUT_W, size[1] or OUT_H, shot)
            table += t
            problems += p
    return table, problems


def cut(it, moment=None, start=None, end=None, method='auto', aspect='9:16', subject=None, hook=None, pull=1.0, say=print, timeout=900,
        from_start=False):
    if aspect != '9:16':
        raise SystemExit('only --aspect 9:16 is made today')
    if not (it.cut / 'master.mp4').exists():
        raise SystemExit(f'{it.path} has no cut/master.mp4 to clip')
    m = timemap.load(it)
    s, e, mo = pick_range(it, m, moment, start, end)
    a, b = timemap.frame_range(s, e, m.fps)
    pieces = timemap.sub_timeline(m.segments, a, b)
    folder = folder_for(it, mo)
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob('crop-*.cmd'):
        old.unlink()
    is_assembly = bool(m.parts)
    has_script = (it.path / 'script.toml').exists() or (it.path / 'script.json').exists()
    chosen = method if method != 'auto' else ('reshoot' if has_script and not is_assembly else 'reframe')
    hook_text = None if hook == 'none' else (hook or (mo or {}).get('hook'))
    if mo is None and hook is None and s > 0.05:
        hook_text = None    # an explicit range gets a hook only when asked
    say(f'videocraft clips cut: {it.path.parent.name}/{it.name} {s:.2f}-{e:.2f} s ({b - a} frames) by {chosen}'
        + (f', hook "{hook_text}"' if hook_text else '') + f' -> {folder}')
    record = {'run': str(it.path), 'moment': mo, 'start': s, 'end': e, 'frames': b - a, 'fps': m.fps, 'aspect': aspect,
              'width': OUT_W, 'height': OUT_H, 'requested': method, 'hook': hook_text, 'pull': pull, 'notes': []}
    vit, plan, cw, hook_in_game = None, None, None, False
    if chosen == 'reshoot':
        try:
            picture, vit, hook_in_game = reshoot(it, m, pieces, folder, hook_text, pull, say, timeout, from_start, record['notes'])
            record['reshoot'] = str(vit.path)
        except (RuntimeError, script_.ScriptError, SystemExit) as err:
            if method == 'reshoot':
                raise SystemExit(f're-shoot failed: {err}')
            record['notes'].append(f're-shoot failed ({err}); re-framed instead')
            say(f'  re-shoot failed ({err}); re-framing the master instead')
            chosen = 'reframe'
    if chosen == 'reframe':
        plan, cw = reframe_plan(it, m, pieces, subject)
        picture = reframe_render(it, m, a, plan, cw, folder)
    record['method'] = chosen
    info = probe(it.cut / 'master.mp4')
    wav = folder / 'audio.wav'
    record['loudness'] = audio_slice(it.cut / 'master.mp4', s, (b - a) / m.fps, wav, info['audio'])
    hook_overlay = None
    if hook_text and (chosen == 'reframe' or not hook_in_game):
        png, h = hook_band(folder / 'hook.png', hook_text)
        hook_overlay = (png, h, int(OUT_H * 0.16))
    out = folder / 'short-1080x1920.mp4'
    record['crf'] = export(picture, wav if record['loudness'] else None, b - a, m.fps, out, hook_overlay)
    picture.unlink(missing_ok=True)
    got = probe(out)
    checks, text = {}, []
    checks['size'] = (got['width'], got['height']) == (OUT_W, OUT_H)
    checks['frames'] = got['frames'] == b - a
    checks['at_most_60s'] = got['seconds'] <= LONGEST + 0.05
    checks['under_50mb'] = got['bytes'] <= LIMIT_MB * 1e6
    if record['loudness'] and (record['loudness'].get('before') or -120) > -60:   # a silent source makes a silent short
        checks['loudness'] = abs(record['loudness']['integrated'] - loudness.TARGET) <= 1.0
    if vit:
        table, problems = vertical_text(vit, [p[0].shot for p in pieces if p[0].kind == 'shot'], m.fps)
        record['text'] = {'items': len(table), 'problems': problems}
        checks['captions_in_safe_area'] = not any(p['rule'] == 'safe_area' for p in problems)
        text = [f'{len(table)} text item(s), {sum(1 for p in problems if p["rule"] == "safe_area")} outside the vertical safe area']
    if plan:
        record['clips'] = [{k: v for k, v in c.items() if k not in ('centres', 'targets', 'seg')} for c in plan]
        follow = [c for c in plan if c['layout'] == 'follow' and c['stats'] and c['stats']['seen']]
        if follow:
            seen = sum(c['stats']['seen'] for c in follow)
            inside = sum(c['stats']['inside_crop'] * c['stats']['seen'] for c in follow) / seen
            centre = sum(c['stats']['inside_centre_60'] * c['stats']['seen'] for c in follow) / seen
            record['subject'] = {'frames_seen': seen, 'inside_crop': round(inside, 4), 'inside_centre_60': round(centre, 4),
                                 'max_speed': max(c['stats']['max_speed'] for c in follow),
                                 'max_acceleration': max(c['stats']['max_acceleration'] for c in follow)}
            checks['subject_in_crop'] = inside >= 0.98
            text.append(f'subject inside the crop {inside:.1%}, inside its centre 60% {centre:.1%}')
        fits = [c for c in plan if c['layout'] == 'fit']
        if fits:
            text.append(f'{len(fits)} of {len(plan)} clip(s) fit over a blurred fill ({fits[0]["why"]})')
    record.update(checks=checks, video=str(out), folder=str(folder), bytes=got['bytes'], seconds=got['seconds'],
                  pass_=all(checks.values()))
    record['pass'] = record.pop('pass_')
    record['checks_text'] = [f'{got["frames"]} frames {got["bytes"] / 1e6:.1f} MB'] + text + \
        ([f'{record["loudness"]["integrated"]:.1f} LUFS'] if record['loudness'] else ['silent']) + \
        [f'failed: {", ".join(k for k, v in checks.items() if not v)}'] * (not record['pass'])
    (folder / 'clip.json').write_text(json.dumps(record, indent=2, default=str) + '\n')
    return record
