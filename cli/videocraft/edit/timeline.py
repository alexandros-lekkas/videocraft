"""The edit resolved to frames: which source frames each clip takes, where it lands in the cut, how long it is.

Pure functions (no ffmpeg), so the cut and its tests agree on every frame. `resolve(plan, edit, shots)` returns the
timeline that cut/timeline.json holds (docs/SCRIPT.md, "Edit"):

    {"fps": 60, "width": 1920, "height": 1080, "frames": N, "clips": [
        {"index": 0, "kind": "shot", "shot": "s1", "src_in": 12, "src_out": 300, "out_start": 0, "out_frames": 288,
         "speed": 1.0, "fade_in": 0, "fade_out": 0, ...},
        {"index": 1, "kind": "black", "shot": null, "out_start": 288, "out_frames": 48, ...}]}

Frames: src_* are frames of the shot's own video (src_out exclusive); out_start + out_frames is exclusive too.
"""
import math

CLIP_KEYS = {'shot', 'trim', 'in', 'out', 'length', 'frames', 'push', 'speed', 'fade_in', 'fade_out', 'black', 'label',
             'frame', 'grade', 'note'}
LOOK_KEYS = {'from', 'to', 'frame', 'grade', 'note'}
GRADES = {'sepia', 'cool', 'warm', 'crush', 'mono', 'none'}
EASES = {'linear', 'smooth', 'in', 'out'}


class EditError(ValueError):
    """A problem in the [edit] table, phrased so an agent can fix it: where, what is wrong, what is allowed."""


def frames_of(value, fps, where):
    """An integer is frames; a number with a decimal point is seconds (rounded to the nearest frame)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EditError(f'{where}: frames (an integer) or seconds (a number with a decimal point), got {value!r}')
    return int(value) if isinstance(value, int) else int(math.floor(value * fps + 0.5))


def ease(kind, k):
    k = min(1.0, max(0.0, k))
    if kind == 'linear':
        return k
    if kind == 'in':
        return k * k
    if kind == 'out':
        return 1 - (1 - k) * (1 - k)
    return k * k * (3 - 2 * k)


# ---- Checking the edit (called when the script compiles, so a bad edit fails before the take) ----

def check(edit, shots, durations=None, fps=60):
    """Raises EditError for an [edit] that cannot be cut. `shots` are the script's shot names."""
    names = set(shots)
    for i, clip in enumerate(edit.get('clip') or []):
        where = f'edit.clip[{i}]'
        if not isinstance(clip, dict):
            raise EditError(f'{where}: a clip is a table: {{ shot = "<name>" }} or {{ black = <seconds> }}')
        extra = sorted(set(clip) - CLIP_KEYS)
        if extra:
            raise EditError(f'{where}: unknown key(s) {", ".join(extra)}; allowed: {", ".join(sorted(CLIP_KEYS))}')
        if 'black' in clip:
            if 'shot' in clip:
                raise EditError(f'{where}: a clip is a shot or a black gap, not both')
            if not isinstance(clip['black'], (int, float)) or isinstance(clip['black'], bool) or clip['black'] <= 0:
                raise EditError(f'{where}: black = <seconds> > 0 (a gap of black)')
            continue
        if clip.get('shot') not in names:
            raise EditError(f'{where}: shot = "{clip.get("shot")}" is not a shot in this script; shots: {sorted(names)}')
        if 'trim' in clip and ('in' in clip or 'out' in clip):
            raise EditError(f'{where}: give trim = [head, tail] or in/out, not both')
        if 'length' in clip and 'frames' in clip:
            raise EditError(f'{where}: give length (seconds) or frames, not both')
        if ('length' in clip or 'frames' in clip) and 'out' in clip:
            raise EditError(f'{where}: give out or a length, not both')
        push = clip.get('push')
        if push is not None and not isinstance(push, (dict, list)):
            raise EditError(f'{where}.push: a slow push {{ from = 1.0, to = 1.15 }} or a list of push-ins [{{ at = "<mark>", zoom = 1.5, hold = 40 }}]')
        if isinstance(push, dict) and not ('from' in push or 'to' in push):
            raise EditError(f'{where}.push: a slow push needs from and/or to (zoom factors, e.g. from = 1.0, to = 1.15)')
        if isinstance(push, dict) and push.get('ease', 'linear') not in EASES:
            raise EditError(f'{where}.push.ease is one of {sorted(EASES)}')
        for key in ('fade_in', 'fade_out'):
            if key in clip:
                frames_of(clip[key], fps, f'{where}.{key}')
        _check_look(clip, where)
    for i, look in enumerate(edit.get('look') or []):
        where = f'edit.look[{i}]'
        extra = sorted(set(look) - LOOK_KEYS)
        if extra:
            raise EditError(f'{where}: unknown key(s) {", ".join(extra)}; allowed: {", ".join(sorted(LOOK_KEYS))}')
        for key in ('from', 'to'):
            v = look.get(key)
            if v is None or (isinstance(v, str) and v not in names) or not isinstance(v, (str, int)) or isinstance(v, bool):
                raise EditError(f'{where}: {key} = "<shot name>" (or a clip index from 0); shots: {sorted(names)}')
        _check_look(look, where)
    for i, export in enumerate(edit.get('export') or []):
        from videocraft.edit.export import PRESETS
        if export.get('preset') not in PRESETS:
            raise EditError(f'edit.export[{i}]: preset is one of {", ".join(PRESETS)}')


def _check_look(table, where):
    grade = table.get('grade')
    if grade is not None and not (isinstance(grade, dict) or grade in GRADES):
        raise EditError(f'{where}.grade is one of {sorted(GRADES)} or {{ saturation, contrast, brightness, tint, amount }}')
    if isinstance(grade, dict):
        extra = sorted(set(grade) - {'saturation', 'contrast', 'brightness', 'gamma', 'tint', 'amount'})
        if extra:
            raise EditError(f'{where}.grade: unknown key(s) {", ".join(extra)}; allowed: saturation, contrast, brightness, gamma, tint, amount')
    frame = table.get('frame')
    if frame is not None:
        if not isinstance(frame, dict):
            raise EditError(f'{where}.frame = {{ color = "#e8a23a", width = 28, glow = 12 }}')
        extra = sorted(set(frame) - {'color', 'width', 'glow', 'opacity'})
        if extra:
            raise EditError(f'{where}.frame: unknown key(s) {", ".join(extra)}; allowed: color, width, glow, opacity')


# ---- Resolving ----

def _mark(value, marks, shot, where, fps):
    """A source frame: an integer frame, seconds (float), a mark label, or {mark = "<label>", offset = <frames>}."""
    if isinstance(value, str):
        value = {'mark': value}
    if isinstance(value, dict):
        label = value.get('mark')
        found = [m['frame'] for m in marks.get(shot, []) if m.get('label') == label]
        if not found:
            known = sorted({m.get('label') for m in marks.get(shot, [])})
            raise EditError(f'{where}: the shot {shot} has no mark "{label}" in its marks.json; marks: {known}')
        return found[0] + frames_of(value.get('offset', 0), fps, where + '.offset')
    return frames_of(value, fps, where)


def resolve(plan, edit, shots, marks=None):
    """The timeline. `shots` maps shot name to its captured frame count; `marks` maps shot name to its marks.json list."""
    out = plan['output']
    fps, width, height = out['fps'], out['width'], out['height']
    marks = marks or {}
    clips = edit.get('clip') or [{'shot': name} for name in shots]
    check({**edit, 'clip': clips}, list(shots), fps=fps)
    timeline, at = [], 0
    for i, clip in enumerate(clips):
        where = f'edit.clip[{i}]'
        entry = {'index': i, 'label': clip.get('label')}
        if 'black' in clip:
            n = max(1, int(math.floor(float(clip['black']) * fps + 0.5)))
            entry.update(kind='black', shot=None, src_in=None, src_out=None, out_start=at, out_frames=n, speed=None,
                         fade_in=0, fade_out=0)
            timeline.append(entry)
            at += n
            continue
        shot = clip['shot']
        total = shots[shot]
        if 'in' in clip or 'out' in clip:
            src_in = _mark(clip['in'], marks, shot, where + '.in', fps) if 'in' in clip else 0
            src_out = _mark(clip['out'], marks, shot, where + '.out', fps) if 'out' in clip else total
        else:
            head, tail = clip.get('trim') or [0, 0]
            src_in, src_out = frames_of(head, fps, where + '.trim'), total - frames_of(tail, fps, where + '.trim')
        if 'length' in clip:
            src_out = src_in + max(1, frames_of(float(clip['length']), fps, where + '.length'))
        elif 'frames' in clip:
            src_out = src_in + int(clip['frames'])
        if not 0 <= src_in < src_out <= total:
            raise EditError(f'{where}: the clip takes frames {src_in} to {src_out} of {shot}, which has {total} '
                            f'(0 to {total}); check trim, in, out and length')
        speed = speed_stamps(clip.get('speed'), src_in, src_out, marks, shot, where, fps)
        keys, stamps = speed or (None, None)
        n = stamps[-1] if stamps else src_out - src_in
        fade_in = frames_of(clip.get('fade_in', 0), fps, where + '.fade_in')
        fade_out = frames_of(clip.get('fade_out', 0), fps, where + '.fade_out')
        if fade_in + fade_out > n:
            raise EditError(f'{where}: fade_in + fade_out ({fade_in + fade_out} frames) is longer than the clip ({n} frames)')
        entry.update(kind='shot', shot=shot, src_in=src_in, src_out=src_out, out_start=at, out_frames=n,
                     speed=round((src_out - src_in) / n, 6), fade_in=fade_in, fade_out=fade_out)
        if stamps:
            entry['speed_keys'] = [list(k) for k in keys]
            entry['src_map'] = src_map(stamps, src_in, n)
        entry['push'] = resolve_push(clip.get('push'), src_in, src_out, width, height, marks, shot, where, fps)
        timeline.append(entry)
        at += n
    _apply_looks(timeline, edit.get('look') or [], clips)
    return {'fps': fps, 'width': width, 'height': height, 'frames': at, 'clips': timeline,
            'conventions': 'frames; src_out and out_start + out_frames are exclusive; src_* are frames of the shot video'}


def _apply_looks(timeline, looks, clips):
    for clip, raw in zip(timeline, clips):
        look = {k: raw[k] for k in ('frame', 'grade') if k in raw}
        if look:
            clip['look'] = look
    for i, look in enumerate(looks):
        def index(ref, last):
            if isinstance(ref, int):
                if not 0 <= ref < len(timeline):
                    raise EditError(f'edit.look[{i}]: clip index {ref} is outside 0 to {len(timeline) - 1}')
                return ref
            found = [c['index'] for c in timeline if c['shot'] == ref]
            if not found:
                raise EditError(f'edit.look[{i}]: the shot {ref} is not in the cut')
            return found[-1] if last else found[0]
        a, b = index(look['from'], False), index(look['to'], True)
        if b < a:
            raise EditError(f'edit.look[{i}]: to comes before from in the cut')
        for clip in timeline[a:b + 1]:
            if clip['kind'] == 'shot':
                clip['look'] = {**{k: look[k] for k in ('frame', 'grade') if k in look}, **clip.get('look', {})}


# ---- Speed ----

def speed_stamps(speed, src_in, src_out, marks, shot, where, fps):
    """(keys, output slot of each source frame of the clip and one past the end), or None at speed 1.

    `speed` is a number (constant) or a list of keys [{ at = <frame | seconds | mark>, speed = 0.5 }, ...]: the speed
    is linear in source frames between keys and constant before the first and after the last. Source frame N starts at
    output time T(N) = integral of 1 / speed; it is shown from slot floor(T(N) + 0.5) until the next frame's slot.
    """
    if speed is None or speed == 1 or speed == 1.0:
        return None
    if isinstance(speed, (int, float)) and not isinstance(speed, bool):
        if speed <= 0:
            raise EditError(f'{where}.speed: a speed is > 0 (0.5 is half speed)')
        keys = [(src_in, float(speed))]
    elif isinstance(speed, list) and speed:
        keys = []
        for j, k in enumerate(speed):
            if not isinstance(k, dict) or 'at' not in k or 'speed' not in k or float(k['speed']) <= 0:
                raise EditError(f'{where}.speed[{j}]: a key is {{ at = <frame, seconds or mark>, speed = <factor > 0> }}')
            keys.append((_mark(k['at'], marks, shot, f'{where}.speed[{j}].at', fps), float(k['speed'])))
        keys.sort()
    else:
        raise EditError(f'{where}.speed: a number (2.0 is double speed) or a list of keys [{{ at = "<mark>", speed = 0.5 }}]')
    base = _time(keys, src_in)
    stamps = [int(math.floor(_time(keys, n) - base + 0.5)) for n in range(src_in, src_out + 1)]
    if stamps[-1] <= 0:
        raise EditError(f'{where}.speed: the clip would last no frames at this speed')
    return keys, stamps


def _time(keys, n):
    """Output frames from the first key to source frame n (may be negative before it)."""
    def segment(a, b, va, vb, x):  # integral of 1/v over [a, x], v linear from va at a to vb at b
        if abs(vb - va) < 1e-12 or b == a:
            return (x - a) / va
        slope = (vb - va) / (b - a)
        return math.log((va + slope * (x - a)) / va) / slope
    a0, v0 = keys[0]
    if n <= a0:
        return (n - a0) / v0
    t = 0.0
    for (a, va), (b, vb) in zip(keys, keys[1:]):
        if n <= b:
            return t + segment(a, b, va, vb, n)
        t += segment(a, b, va, vb, b)
    a, v = keys[-1]
    return t + (n - a) / v


def src_map(stamps, src_in, frames):
    """The source frame shown on each output frame of the clip: the last source frame whose slot is at or before it."""
    out, n = [], 0
    for j in range(frames):
        while n + 1 < len(stamps) - 1 and stamps[n + 1] <= j:
            n += 1
        out.append(src_in + n)
    return out


def time_expr(keys, src_in):
    """_time(keys, src_in + N) - _time(keys, src_in) as an ffmpeg expression of N (the frame number in the clip)."""
    x = f'({src_in}+N)'

    def seg(a, b, va, vb, at):
        if abs(vb - va) < 1e-12 or b == a:
            return f'(({at})-{a})/{va!r}'
        slope = (vb - va) / (b - a)
        return f'log(({va!r}+{slope!r}*(({at})-{a}))/{va!r})/{slope!r}'

    a0, v0 = keys[0]
    # From the last key backwards: after the last key, constant speed; each segment adds to the time at its start.
    t, ends = 0.0, []
    for (a, va), (b, vb) in zip(keys, keys[1:]):
        ends.append((a, b, va, vb, t))
        t += _time(keys, b) - _time(keys, a)
    a_last, v_last = keys[-1]
    expr = f'({t!r}+({x}-{a_last})/{v_last!r})'
    for a, b, va, vb, t0 in reversed(ends):
        expr = f'if(lte({x},{b}),{t0!r}+{seg(a, b, va, vb, x)},{expr})'
    expr = f'if(lte({x},{a0}),({x}-{a0})/{v0!r},{expr})'
    return f'({expr})-({_time(keys, src_in)!r})'


# ---- Push-ins ----

def window(width, height, zoom, x, y):
    """The held crop of a push-in: even size, even offsets, centred on (x, y) and kept inside the frame."""
    cw = int(round(width / zoom / 2)) * 2
    ch = int(round(height / zoom / 2)) * 2
    left = int(round((x - cw / 2) / 2)) * 2
    top = int(round((y - ch / 2) / 2)) * 2
    left = min(max(0, left), width - cw)
    top = min(max(0, top), height - ch)
    return cw, ch, left, top


def resolve_push(push, src_in, src_out, width, height, marks, shot, where, fps):
    """Push-ins as pieces over the clip's source frames: [{kind, from, to, ...}] covering [src_in, src_out) in order.

    kinds: 'plain' (the frame as captured), 'hold' (an exact crop scaled with nearest neighbour: zoom, window),
    'ramp' (a smooth zoom about a fixed point from one zoom to another: z0, z1, fx, fy, ease), 'slow' (the same over a
    longer stretch, for a slow push).
    """
    if not push:
        return [{'kind': 'plain', 'from': src_in, 'to': src_out}]
    if isinstance(push, dict):
        z0, z1 = float(push.get('from', 1.0)), float(push.get('to', 1.0))
        if z0 < 1 or z1 < 1:
            raise EditError(f'{where}.push: zoom factors are >= 1 (1.0 is the whole frame)')
        a = _mark(push['at'], marks, shot, where + '.push.at', fps) if 'at' in push else src_in
        b = _mark(push['until'], marks, shot, where + '.push.until', fps) if 'until' in push else src_out
        a, b = max(src_in, a), min(src_out, b)
        if b <= a:
            raise EditError(f'{where}.push: at/until leave no frames of the clip')
        fx, fy = float(push.get('x', width / 2)), float(push.get('y', height / 2))
        pieces = []
        if a > src_in:
            pieces.append(_held_or_plain(src_in, a, z0, fx, fy, width, height))
        pieces.append({'kind': 'slow', 'from': a, 'to': b, 'z0': z0, 'z1': z1, 'fx': fx, 'fy': fy, 'ease': push.get('ease', 'linear')})
        if b < src_out:
            pieces.append(_held_or_plain(b, src_out, z1, fx, fy, width, height))
        return pieces
    pieces, at, zoom, held = [], src_in, 1.0, None
    for j, step in enumerate(push):
        w = f'{where}.push[{j}]'
        if not isinstance(step, dict) or 'at' not in step or 'zoom' not in step:
            raise EditError(f'{w}: a push-in is {{ at = "<mark or frame>", zoom = 1.5, x = 960, y = 540, hold = 40 }}')
        z = float(step['zoom'])
        if z < 1:
            raise EditError(f'{w}: zoom is >= 1')
        start = max(at, min(src_out, _mark(step['at'], marks, shot, w + '.at', fps)))
        ramp = 0 if step.get('cut') else frames_of(step.get('ramp', 7), fps, w + '.ramp')
        out_ramp = frames_of(step.get('out', 9), fps, w + '.out')
        cw, ch, left, top = window(width, height, z, float(step.get('x', width / 2)), float(step.get('y', height / 2)))
        if start > at:
            pieces.append(_hold(at, start, held) if held else {'kind': 'plain', 'from': at, 'to': start})
        # Zoom about the fixed point that ends exactly on the held window.
        fx = left / (1 - cw / width) if cw < width else width / 2
        fy = top / (1 - ch / height) if ch < height else height / 2
        if held and ramp:
            raise EditError(f'{w}: a push-in from one held window to another needs cut = true (or ramp out first with hold)')
        ramp_end = min(src_out, start + ramp)
        if ramp_end > start:
            pieces.append({'kind': 'ramp', 'from': start, 'to': ramp_end, 'z0': zoom, 'z1': z, 'fx': fx, 'fy': fy, 'ease': 'smooth'})
        held = {'zoom': z, 'window': [cw, ch, left, top], 'fx': fx, 'fy': fy}
        zoom, at = z, ramp_end
        if 'hold' in step:
            hold_end = min(src_out, at + frames_of(step['hold'], fps, w + '.hold'))
            if hold_end > at:
                pieces.append(_hold(at, hold_end, held))
            out_end = min(src_out, hold_end + out_ramp)
            if out_end > hold_end:
                pieces.append({'kind': 'ramp', 'from': hold_end, 'to': out_end, 'z0': z, 'z1': 1.0, 'fx': fx, 'fy': fy, 'ease': 'smooth'})
            held, zoom, at = None, 1.0, out_end
        if at >= src_out:
            break
    if at < src_out:
        pieces.append(_hold(at, src_out, held) if held else {'kind': 'plain', 'from': at, 'to': src_out})
    return pieces


def _hold(a, b, held):
    return {'kind': 'hold', 'from': a, 'to': b, 'zoom': held['zoom'], 'window': held['window']}


def _held_or_plain(a, b, zoom, fx, fy, width, height):
    if zoom <= 1.0:
        return {'kind': 'plain', 'from': a, 'to': b}
    # Before/after a slow push the zoom is held about the same fixed point (smoothly, not cropped to even pixels).
    return {'kind': 'slow', 'from': a, 'to': b, 'z0': zoom, 'z1': zoom, 'fx': fx, 'fy': fy, 'ease': 'linear'}
