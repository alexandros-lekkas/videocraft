"""Re-framing a 16:9 master to 9:16: a crop window that follows the subject like a camera operator.

Per clip of the range (a cut resets the operator; nothing pans across a cut):
  1. the subject's track: actors.csv / frames.csv projected through each frame's camera (measure.camera), or a world
     point, mapped through the clip's push-ins into master pixels; frames where it is not seen hold the last target;
  2. the operator: a critically damped follow of the target, looking LEAD seconds ahead (we know the future), with a
     dead zone (it holds while the subject stays near the centre), and velocity and acceleration clamps (no jitter,
     no whip pans), kept inside the frame;
  3. the layout: `follow` (the crop, scaled to 1080x1920) or `fit` (the whole 16:9 frame across the width over a
     blurred, darkened fill of itself) when two subjects are further apart than the crop holds, or text the take drew
     is wider than the crop (re-framing cannot re-lay text; a re-shoot can, which is why it is preferred).

`path(...)`, `operator(...)` and `layout(...)` are pure (unit tested); `render(...)` writes the ffmpeg graph.
"""
import math

LEAD = 0.3            # seconds the operator looks ahead
DEAD = 0.12            # dead zone, a fraction of the crop width either side of the centre
BAND = 0.30            # the subject is wanted within +-BAND of the crop width from the crop centre (the centre 60 %)
OMEGA = 7.0            # natural frequency of the follow (1/s): critically damped
VMAX = 1.5            # most speed, crop widths per second
AMAX = 6.0             # most acceleration, crop widths per second squared


def crop_size(width, height, aspect=(9, 16)):
    """The crop window of a vertical aspect in a landscape frame: full height, even width."""
    cw = int(round(height * aspect[0] / aspect[1] / 2)) * 2
    return min(cw, width), height


def operator(targets, fps, cw, width, lead=LEAD, dead=DEAD, omega=OMEGA, vmax=VMAX, amax=AMAX, start=None):
    """Crop centres (pixels) for one clip. `targets` is one x (pixels) per frame or None (not seen: hold)."""
    n = len(targets)
    if n == 0:
        return []
    known = [t for t in targets if t is not None]
    half = cw / 2
    lo, hi = half, width - half
    if not known:
        return [min(hi, max(lo, width / 2 if start is None else start))] * n
    # Fill unseen frames with the last seen target (the first seen one before it).
    filled, last = [], known[0]
    for t in targets:
        last = t if t is not None else last
        filled.append(last)
    k = max(0, int(round(lead * fps)))
    ahead = [filled[min(n - 1, i + k)] for i in range(n)]
    dt = 1.0 / fps
    vmax_px, amax_px, dead_px = vmax * cw, amax * cw, dead * cw
    # Start where the first 0.3 s of the subject sits on average: a cut lands framed, no settle.
    first = filled[:max(1, int(0.3 * fps))]
    x = min(hi, max(lo, sum(first) / len(first) if start is None else start))
    v = 0.0
    out = []
    for i in range(n):
        err = ahead[i] - x
        if abs(err) <= dead_px:
            err = 0.0
        else:
            err -= math.copysign(dead_px, err)
        a = omega * omega * err - 2 * omega * v
        a = max(-amax_px, min(amax_px, a))
        v = max(-vmax_px, min(vmax_px, v + a * dt))
        x += v * dt
        if x < lo or x > hi:
            x = min(hi, max(lo, x))
            v = 0.0
        out.append(x)
    return out


def stats(centres, subjects, fps, cw):
    """Measured: speed and acceleration of the crop (crop widths/s, /s²), and how often the subject is inside the
    crop and inside its centre 60 %."""
    dt = 1 / fps
    vel = [(b - a) / dt for a, b in zip(centres, centres[1:])]
    acc = [(b - a) / dt for a, b in zip(vel, vel[1:])]
    seen = [(c, s) for c, s in zip(centres, subjects) if s is not None]
    inside = sum(1 for c, s in seen if abs(s - c) <= cw / 2)
    centre = sum(1 for c, s in seen if abs(s - c) <= BAND * cw + 1e-9)
    r = lambda v: round(v, 4)
    return {'frames': len(centres), 'seen': len(seen), 'inside_crop': r(inside / len(seen)) if seen else None,
            'inside_centre_60': r(centre / len(seen)) if seen else None,
            'max_speed': r(max((abs(v) for v in vel), default=0) / cw), 'max_acceleration': r(max((abs(a) for a in acc), default=0) / cw)}


def push_map(pieces, width, height):
    """A function (source frame, x pixels) -> x pixels in the cut, through the clip's push-in pieces (timeline.json)."""
    from videocraft.edit.timeline import ease

    def at(frame, x):
        for p in pieces or []:
            if not p['from'] <= frame < p['to']:
                continue
            if p['kind'] == 'plain':
                return x
            if p['kind'] == 'hold':
                cw, ch, left, top = p['window']
                return (x - left) * width / cw
            n = p['to'] - p['from']
            k = min(1.0, (frame - p['from'] + 1) / n) if p['kind'] == 'ramp' else (frame - p['from']) / max(1, n - 1)
            e = ease(p.get('ease', 'smooth'), k)
            z = p['z0'] * (p['z1'] / p['z0']) ** e if p['z1'] != p['z0'] else p['z0']
            return p['fx'] + (x - p['fx']) * z
        return x
    return at


def layout(spread, text_width, cw, fit_spread=0.8, fit_text=0.92):
    """'follow' or 'fit' for a clip: fit when its subjects spread wider than `fit_spread` of the crop, or the widest
    text box on screen is wider than `fit_text` of it."""
    if spread is not None and spread > fit_spread * cw:
        return 'fit', f'two subjects {spread:.0f} px apart (the crop is {cw} px)'
    if text_width and text_width > fit_text * cw:
        return 'fit', f'text {text_width:.0f} px wide on screen (the crop is {cw} px)'
    return 'follow', None


def sendcmd(centres, cw, width, fps):
    """sendcmd lines that set crop x on every frame (relative to the clip's own start)."""
    lines = []
    prev = None
    for i, c in enumerate(centres):
        x = int(round(min(width - cw, max(0, c - cw / 2))))
        if x != prev:
            lines.append(f'{i / fps:.6f} crop x {x};')
            prev = x
    return '\n'.join(lines) + '\n'


def fit_chain(src, width, height, ow, oh, label):
    """The whole frame across the width over a blurred, darkened, cover-scaled copy of itself."""
    fh = int(round(height * ow / width / 2)) * 2
    return (f'{src}split=2[{label}a][{label}b];'
            f'[{label}a]scale=-2:{oh},crop={ow}:{oh},boxblur=24:3,eq=brightness=-0.18:saturation=0.8[{label}bg];'
            f'[{label}b]scale={ow}:{fh}:flags=lanczos[{label}fg];'
            f'[{label}bg][{label}fg]overlay=(W-w)/2:(H-h)/2,setsar=1,format=yuv420p')
