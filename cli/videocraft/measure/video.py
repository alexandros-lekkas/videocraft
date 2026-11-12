"""What the picture does, from tiny thumbnails of every frame: shots (scene cuts), black stretches, frozen runs.

One ffmpeg decode per video scales every frame to 64x36 RGB (area average) and pipes it here. From that:

- `full`: mean absolute difference of the 64x36 grey image to the previous frame (0-255),
- `blur`: the same on a 16x9 block average, which ignores walking motion and keeps changes of place,
- `peak`: the brightest 64x36 pixel, so a frame is black when nothing in it is brighter than BLACK_PEAK.

A cut is a frame whose `blur` difference stands out: above CUT_MIN, a local maximum, and CUT_RATIO times the median
of the non-duplicate differences around it (a 60 fps upload of lower-rate footage repeats frames, and those zeros
would drag the local level down). Shots are the stretches between cuts and black runs. Tuned on the benchmark's
reference section (docs/benchmarks/pinksheep-style.md): it finds 28 shots (the doc counts 30 by eye) with a median
of 2.6 s. Owned by workstream (d).
"""
import operator
import statistics
import subprocess

from videocraft import tools

TW, TH = 64, 36            # thumbnail size
BW, BH = 16, 9             # block-averaged ("blurred") size
BLACK_PEAK = 24            # a frame is black when no thumbnail pixel is brighter (0-255)
BLACK_MIN_FRAMES = 2       # shorter black is not a stretch
CUT_MIN = 18.0             # minimum blurred difference for a cut
CUT_RATIO = 2.5            # times the local median of moving differences
CUT_WINDOW = 30            # frames each side for the local median
CUT_GAP = 10               # two cuts closer than this are one (the stronger)
DUPLICATE = 0.6            # a blurred difference below this is a repeated frame, not motion
FROZEN = 0.15              # a full difference below this: the picture did not change
MIN_SHOT_FRAMES = 6        # a shorter piece between boundaries is a fragment, not a shot
FLASH_SECONDS = 0.25       # a piece shorter than this with black on both sides is a flash, not a shot
SHORT_SHOT = 0.6           # montage shots: runs of shots under this
HISTOGRAM = (1.0, 2.0, 4.0, 6.0)  # bins: under 1 s, 1-2, 2-4, 4-6, 6 and over (the benchmark's)


def decode(path, start=None, end=None, ffmpeg=None):
    """Yields 64x36 RGB24 frames of a video (bytes), optionally only from `start` to `end` seconds."""
    ffmpeg = ffmpeg or tools.ffmpeg()
    if not ffmpeg:
        raise SystemExit('ffmpeg not found (brew install ffmpeg, or set FFMPEG)')
    cmd = [ffmpeg, '-v', 'error', '-nostdin']
    if start:
        cmd += ['-ss', f'{start:.3f}']
    cmd += ['-i', str(path)]
    if end is not None:
        cmd += ['-t', f'{end - (start or 0):.3f}']
    cmd += ['-an', '-vf', f'scale={TW}:{TH}:flags=area,format=rgb24', '-fps_mode', 'passthrough', '-f', 'rawvideo', '-']
    size = TW * TH * 3
    with subprocess.Popen(cmd, stdout=subprocess.PIPE) as p:
        while True:
            frame = p.stdout.read(size)
            if len(frame) < size:
                break
            yield frame
        p.wait()


def _grey(f):
    return bytes((f[i] * 299 + f[i + 1] * 587 + f[i + 2] * 114) // 1000 for i in range(0, len(f), 3))


def _blocks(f):
    sx, sy = TW // BW, TH // BH
    out = []
    for by in range(BH):
        for bx in range(BW):
            for c in range(3):
                total = 0
                for y in range(by * sy, by * sy + sy):
                    row = (y * TW + bx * sx) * 3 + c
                    total += sum(f[row:row + sx * 3:3])
                out.append(total // (sx * sy))
    return out


def _mad(a, b):
    return sum(map(abs, map(operator.sub, a, b))) / len(a)


def signals(frames):
    """Per-frame signals of an iterable of 64x36 RGB frames: dict of lists full, blur, peak, luma (frame 0 has 0 diffs)."""
    full, blur, peak, luma = [], [], [], []
    prev_g = prev_b = None
    for f in frames:
        g, b = _grey(f), _blocks(f)
        full.append(_mad(g, prev_g) if prev_g is not None else 0.0)
        blur.append(_mad(b, prev_b) if prev_b is not None else 0.0)
        peak.append(max(g))
        luma.append(sum(g) / len(g))
        prev_g, prev_b = g, b
    return {'full': full, 'blur': blur, 'peak': peak, 'luma': luma}


def runs(flags, min_len=1):
    """[(start, end)] (end exclusive) of the stretches where flags is true, at least min_len long."""
    out, start = [], None
    for i, f in enumerate(list(flags) + [False]):
        if f and start is None:
            start = i
        elif not f and start is not None:
            if i - start >= min_len:
                out.append((start, i))
            start = None
    return out


def black_runs(peak):
    return runs((p < BLACK_PEAK for p in peak), BLACK_MIN_FRAMES)


def cuts(blur, black=(), skip_head=3):
    """Frames that start a new shot by a hard cut (frame i differs from i-1)."""
    dark = set()
    for a, b in black:
        dark.update(range(a, b))
    n, out = len(blur), []
    for i in range(skip_head, n - 1):
        if i in dark or i - 1 in dark:
            continue
        v = blur[i]
        if v <= CUT_MIN or v < blur[i - 1] or v < blur[i + 1]:
            continue
        around = [x for x in blur[max(1, i - CUT_WINDOW):i - 1] + blur[i + 2:i + 2 + CUT_WINDOW] if x > DUPLICATE]
        level = statistics.median(around) if around else 0.0
        if v <= CUT_RATIO * max(level, 0.5):
            continue
        if out and i - out[-1] < CUT_GAP:
            if v > blur[out[-1]]:
                out[-1] = i
            continue
        out.append(i)
    return out


def segments(n, cut_frames, black, fps=60):
    """Shots as [(start, end)] frames between cuts and black stretches, plus fragments and flashes left out."""
    bounds = sorted({0, n, *cut_frames, *(a for a, _ in black), *(b for _, b in black)})
    pieces = [(a, b) for a, b in zip(bounds, bounds[1:]) if not any(ra <= a and b <= rb for ra, rb in black)]
    starts, ends = {b for _, b in black}, {a for a, _ in black}
    shots, dropped = [], []
    for k, (a, b) in enumerate(pieces):
        if b - a < MIN_SHOT_FRAMES and a not in starts and b not in ends:
            if shots and shots[-1][1] == a:          # a sliver after a cut belongs to the shot before it
                shots[-1] = (shots[-1][0], b)
            elif k + 1 < len(pieces) and pieces[k + 1][0] == b:  # the first frames, before a cut: to the next
                pieces[k + 1] = (a, pieces[k + 1][1])
            continue
        if b - a < MIN_SHOT_FRAMES:
            dropped.append({'start': a, 'end': b, 'why': 'fragment'})
        elif a in starts and b in ends and b - a < FLASH_SECONDS * fps:
            dropped.append({'start': a, 'end': b, 'why': 'flash'})
        else:
            shots.append((a, b))
    return shots, dropped


def stats(lengths):
    """Statistics of shot lengths in seconds: count, median, mean, longest, histogram, runs of short shots."""
    if not lengths:
        return {'count': 0}
    bins = [0] * (len(HISTOGRAM) + 1)
    for x in lengths:
        bins[sum(1 for edge in HISTOGRAM if x >= edge)] += 1
    labels = ['<1', '1-2', '2-4', '4-6', '6+']
    short = runs((x < SHORT_SHOT for x in lengths), 2)
    return {'count': len(lengths), 'median': round(statistics.median(lengths), 3), 'mean': round(statistics.mean(lengths), 3),
            'longest': round(max(lengths), 3), 'shortest': round(min(lengths), 3),
            'histogram': dict(zip(labels, bins)), 'over_7_5s': sum(1 for x in lengths if x > 7.5),
            'short_runs': [{'first': a, 'shots': b - a} for a, b in short]}


def frozen_runs(full, black, min_len=3):
    dark = set()
    for a, b in black:
        dark.update(range(a, b))
    still = [i > 0 and full[i] < FROZEN and i not in dark for i in range(len(full))]
    # a run of k identical differences means k+1 identical frames, starting one frame earlier
    return [(a - 1, b) for a, b in runs(still, min_len - 1)]


def analyse(frames, fps, start=0.0):
    """Everything about the picture of one video. Times are seconds from the start of the analysed stretch."""
    sig = signals(frames)
    n = len(sig['peak'])
    black = black_runs(sig['peak'])
    found = cuts(sig['blur'], black)
    shots, dropped = segments(n, found, black, fps)
    frozen = frozen_runs(sig['full'], black)
    t = lambda f: round(f / fps, 3)
    shot_list = [{'index': k, 'start': t(a), 'end': t(b), 'seconds': t(b - a), 'frames': [a, b]} for k, (a, b) in enumerate(shots)]
    lengths = [s['seconds'] for s in shot_list]
    seconds = n / fps
    dup_at_cuts = [c for c in found if c + 1 < n and (sig['full'][c + 1] < FROZEN or sig['full'][c - 1] < FROZEN)
                   and _shot_moves(sig['full'], c)]
    return {
        'frames': n, 'fps': fps, 'seconds': round(seconds, 3), 'from': start,
        'cuts': [{'frame': c, 't': t(c)} for c in found],
        'shots': shot_list,
        'shot_stats': {**stats(lengths), 'per_minute': round(len(lengths) / seconds * 60, 2) if seconds else 0},
        'black': [{'start': t(a), 'end': t(b), 'seconds': t(b - a), 'frames': [a, b]} for a, b in black],
        'black_seconds': t(sum(b - a for a, b in black)),
        'dropped': dropped,
        'frozen': [{'start': t(a), 'end': t(b), 'frames': [a, b]} for a, b in frozen],
        'duplicate_at_cuts': [{'frame': c, 't': t(c)} for c in dup_at_cuts],
        'signals': sig,
    }


def _shot_moves(full, c, span=8):
    """Whether the picture around a cut is otherwise moving (a repeated frame there is then a fault, not a still shot)."""
    near = [x for x in full[max(1, c - span):c - 1] + full[c + 2:c + 2 + span]]
    return bool(near) and statistics.median(near) >= FROZEN * 4


def compare_cuts(found, expected, tolerance=2):
    """Detected cut frames against the cut's own boundaries: (matched, missed, extra), frames."""
    found, matched, missed = list(found), [], []
    for e in expected:
        near = [f for f in found if abs(f - e) <= tolerance]
        if near:
            best = min(near, key=lambda f: abs(f - e))
            matched.append((e, best))
            found.remove(best)
        else:
            missed.append(e)
    return matched, missed, found
