"""Checks that sounds start where the mix put them: onset detection in the rendered audio, per placed event.

The check renders the effects bus alone (the same placement code as the mix, without music or voice, which would hide
onsets), finds each event's onset in a window around its planned time (first 1 ms step whose energy jumps well above
the level just before it) and compares. With `master` it also finds the master's delay against that render by
cross-correlation, so a limiter that shifted the whole track would show.
"""
import math

from videocraft.audio import dsp

HOP = 48  # 1 ms


def energy(buf):
    return [sum(x * x for x in buf[i:i + HOP]) for i in range(0, len(buf), HOP)]


def detect(env, t, before=0.025, after=0.05, ratio=3.0, floor=1e-7):
    """The onset nearest `t` between `t - before` and `t + after` in an energy curve (1 ms steps): a step whose energy
    is `ratio` times the level of the few milliseconds before it (so the tail of a ringing sound does not hide the
    next one). Nearest, not first: another sound's syllable just before `t` is not this sound starting."""
    a = max(6, int(round((t - before) * 1000)))
    b = min(len(env) - 1, int(round((t + after) * 1000)))
    found = [i for i in range(a, b + 1) if env[i] > floor and env[i] > ratio * max(env[i - 5:i - 1]) + floor
             and not (env[i - 1] > floor and env[i - 1] > ratio * max(env[i - 6:i - 2]) + floor)]
    return min(found, key=lambda i: abs(i / 1000.0 - t)) / 1000.0 if found else None


def check(placed, mono, fps, tolerance_frames=1.0):
    """[(event, planned time, measured onset or None, error ms, ok)] for every placed event that starts at its
    own beginning (events joined part-way are left out) and is not within 30 ms after another one."""
    env = energy(mono)
    rows, last = [], -1.0
    for p in sorted(placed, key=lambda p: p.time):
        if p.offset > 0:
            continue
        crowded = p.time - last < 0.03
        last = p.time
        if crowded:
            continue
        onset = detect(env, p.time)
        err = None if onset is None else (onset - p.time) * 1000
        rows.append((p, onset, err, err is not None and abs(err) <= tolerance_frames * 1000 / fps))
    return rows


def lag(reference, signal, max_ms=50):
    """The delay of `signal` against `reference` in samples (cross-correlation over ±max_ms around the loudest part)."""
    n = min(len(reference), len(signal))
    if n < dsp.SR // 10:
        return 0
    block = dsp.SR // 2
    levels = dsp.block_rms(reference[:n], block)
    i = max(range(len(levels)), key=levels.__getitem__)
    a, b = i * block, min(n, i * block + block)
    m = int(max_ms * dsp.SR / 1000)
    ref = reference[a:b]
    best, best_lag = -math.inf, 0
    for d in range(-m, m + 1, 2):
        if a + d < 0 or b + d > n:
            continue
        seg = signal[a + d:b + d]
        c = sum(x * y for x, y in zip(ref[::4], seg[::4]))
        if c > best:
            best, best_lag = c, d
    return best_lag
