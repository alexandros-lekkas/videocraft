"""How the camera moves and where the subject sits in frame, from a shot's frames.csv (and actors.csv).

Minecraft's conventions: yaw 0 faces south (+Z) and grows clockwise seen from above (90 faces west, -X); pitch is
positive looking down; `fov` in frames.csv is the vertical field of view in degrees. A point is projected through the
camera pose to frame fractions: x 0 (left) to 1 (right), y 0 (top) to 1 (bottom). Owned by workstream (d).
"""
import csv
import math
import statistics

# Standing height in blocks of the entities a subject can be, for the head point when actors.csv has only the feet.
HEIGHTS = {'player': 1.8, 'mannequin': 1.8, 'minecraft:goat': 1.3, 'minecraft:fox': 0.7, 'minecraft:chicken': 0.7,
           'minecraft:sheep': 1.3, 'minecraft:cow': 1.4, 'minecraft:pig': 0.9, 'minecraft:wolf': 0.85, 'minecraft:cat': 0.7,
           'minecraft:villager': 1.95, 'minecraft:bee': 0.6, 'minecraft:iron_golem': 2.7, 'minecraft:armor_stand': 1.975}
MIDDLE = (1 / 3, 2 / 3)
SIZE_CHANGE = 0.15
FOLLOW_RIGS = {'lead', 'chase', 'track', 'locked', 'two_shot', 'face'}


def read_csv(path):
    with open(path, newline='') as f:
        return [{k: _num(v) for k, v in row.items()} for row in csv.DictReader(f)]


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return v


def basis(yaw, pitch):
    """Forward, right and up unit vectors of a camera with Minecraft yaw and pitch in degrees."""
    y, p = math.radians(yaw), math.radians(pitch)
    f = (-math.sin(y) * math.cos(p), -math.sin(p), math.cos(y) * math.cos(p))
    r = (-math.cos(y), 0.0, -math.sin(y))
    u = (r[1] * f[2] - r[2] * f[1], r[2] * f[0] - r[0] * f[2], r[0] * f[1] - r[1] * f[0])
    return f, r, u


def project(point, cam, yaw, pitch, fov, aspect=16 / 9):
    """(x, y) frame fractions of a world point, or None when it is behind the camera."""
    f, r, u = basis(yaw, pitch)
    d = (point[0] - cam[0], point[1] - cam[1], point[2] - cam[2])
    z = d[0] * f[0] + d[1] * f[1] + d[2] * f[2]
    if z <= 1e-6:
        return None
    t = math.tan(math.radians(fov) / 2)
    x = (d[0] * r[0] + d[1] * r[1] + d[2] * r[2]) / z / (t * aspect)
    y = (d[0] * u[0] + d[1] * u[1] + d[2] * u[2]) / z / t
    return (x + 1) / 2, (1 - y) / 2


def _unwrap(angles):
    out, prev = [], None
    for a in angles:
        if prev is not None:
            while a - prev > 180:
                a -= 360
            while a - prev < -180:
                a += 360
        out.append(a)
        prev = a
    return out


def _diff(values, dt):
    return [(b - a) / dt for a, b in zip(values, values[1:])]


def _summary(values):
    if not values:
        return None
    s = sorted(values)
    return {'median': round(statistics.median(s), 4), 'p95': round(s[min(len(s) - 1, int(0.95 * len(s)))], 4), 'max': round(s[-1], 4)}


def _step_diff(values, h, dt):
    """Differences over h frames, per second: (v[i+h] - v[i]) / (h dt), for tuples or numbers."""
    if values and isinstance(values[0], tuple):
        return [tuple((b[k] - a[k]) / (h * dt) for k in range(len(a))) for a, b in zip(values, values[h:])]
    return [(b - a) / (h * dt) for a, b in zip(values, values[h:])]


def kinematics(rows, fps):
    """Camera speed (blocks/s) per frame; acceleration (blocks/s²) and jerk (blocks/s³), overall and vertical, over
    0.1 s steps; view turn rate (degrees/s) and its jerk the same way. frames.csv rounds positions to 1e-4 blocks and
    angles to 1e-3 degrees, so frame-to-frame third differences would be rounding noise (1e-3 x 60³ = 216 °/s³);
    0.1 s steps divide that noise by 216 and keep any jerk a viewer could see. Summaries: median, p95, max."""
    if len(rows) < 4:
        return {'frames': len(rows)}
    dt = 1 / fps
    h = max(1, round(fps / 10))
    pos = [(r['cam_x'], r['cam_y'], r['cam_z']) for r in rows]
    vel = _step_diff(pos, 1, dt)
    vel_h = _step_diff(pos, h, dt)
    acc = _step_diff(vel_h, h, dt)
    jerk = _step_diff(acc, h, dt)
    mag = lambda v: math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
    yaw, pitch = _unwrap([r['cam_yaw'] for r in rows]), [r['cam_pitch'] for r in rows]
    turn = [math.hypot(a, b) for a, b in zip(_diff(yaw, dt), _diff(pitch, dt))]
    yaw_acc = _step_diff(_step_diff(yaw, h, dt), h, dt)
    turn_jerk = [abs(x) for x in _step_diff(yaw_acc, h, dt)]
    travel = sum(mag(v) * dt for v in vel)
    return {'frames': len(rows), 'travel': round(travel, 3), 'step_frames': h,
            'speed': _summary([mag(v) for v in vel]), 'acceleration': _summary([mag(a) for a in acc]),
            'jerk': _summary([mag(j) for j in jerk]), 'vertical_jerk': _summary([abs(j[1]) for j in jerk]),
            'turn': _summary(turn), 'turn_jerk': _summary(turn_jerk),
            'yaw_range': round(max(yaw) - min(yaw), 3), 'pitch_range': round(max(pitch) - min(pitch), 3),
            'fov': sorted({r['fov'] for r in rows})[:1] + sorted({r['fov'] for r in rows})[-1:]}


def subject_track(frames, actors, subject, height, aspect=16 / 9):
    """Per frame: (frame, x, y, h) of the subject's feet-to-head line in frame fractions, x and y of its middle, h its
    height as a fraction of the frame height; None for frames where it is behind the camera or not logged."""
    feet = {}
    for row in actors:
        if str(row.get('actor')) == subject:
            feet[int(row['frame'])] = (row['x'], row['y'], row['z'])
    out = []
    for r in frames:
        n = int(r['frame'])
        if subject == 'player' and n not in feet and 'player_x' in r:
            feet[n] = (r['player_x'], r['player_y'], r['player_z'])
        p = feet.get(n)
        if p is None:
            out.append((n, None))
            continue
        cam, yaw, pitch, fov = (r['cam_x'], r['cam_y'], r['cam_z']), r['cam_yaw'], r['cam_pitch'], r['fov']
        a = project(p, cam, yaw, pitch, fov, aspect)
        b = project((p[0], p[1] + height, p[2]), cam, yaw, pitch, fov, aspect)
        if a is None or b is None:
            out.append((n, None))
            continue
        out.append((n, ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, abs(a[1] - b[1]))))
    return out


def framing(track, rig=None):
    """Summary and flags of a subject track: centre, height, frames outside the middle third, size change."""
    seen = [v for _, v in track if v is not None]
    if not seen:
        return {'frames': len(track), 'seen': 0}
    xs, ys, hs = [v[0] for v in seen], [v[1] for v in seen], [v[2] for v in seen]
    in_frame = [v for v in seen if 0 <= v[0] <= 1 and 0 <= v[1] <= 1]
    outside_middle = sum(1 for x in xs if not MIDDLE[0] <= x <= MIDDLE[1])
    median_h = statistics.median(hs)
    size_change = (max(hs) - min(hs)) / median_h if median_h > 0 else 0.0
    flags = []
    if outside_middle:
        flags.append(f'leaves the middle third in {outside_middle} of {len(seen)} frames')
    if rig == 'lead' and size_change > SIZE_CHANGE:
        flags.append(f'size changes {size_change:.0%} in a lead track (over {SIZE_CHANGE:.0%})')
    if len(in_frame) < len(seen):
        flags.append(f'out of frame in {len(seen) - len(in_frame)} frames')
    if len(seen) < len(track):
        flags.append(f'behind the camera or not logged in {len(track) - len(seen)} frames')
    r = lambda v: round(v, 4)
    return {'frames': len(track), 'seen': len(seen), 'x': {'median': r(statistics.median(xs)), 'min': r(min(xs)), 'max': r(max(xs))},
            'y': {'median': r(statistics.median(ys)), 'min': r(min(ys)), 'max': r(max(ys))},
            'height': {'median': r(median_h), 'min': r(min(hs)), 'max': r(max(hs))}, 'size_change': r(size_change),
            'outside_middle_third': outside_middle, 'flags': flags}


def subject_of(shot):
    camera = shot.get('camera') or {}
    subject = camera.get('subject')
    if isinstance(subject, str):
        return subject
    if camera.get('rig') in FOLLOW_RIGS | {'first'}:
        return 'player' if camera.get('rig') != 'first' else None
    return None


def height_of(subject, plan):
    for actor in plan.get('actors', []):
        if actor.get('id') == subject:
            if 'height' in actor:
                return float(actor['height'])
            return HEIGHTS.get(actor.get('entity') or actor.get('kind'), 1.8) * float(actor.get('scale', 1) or 1)
    return HEIGHTS['player']
