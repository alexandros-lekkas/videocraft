"""Building blocks for the original sound library: oscillators with a pitch curve, noise, a state-variable filter whose
cutoff can move every sample, envelopes, and a small feedback-delay room. Plain Python lists of floats at 48 kHz;
recipes.py turns them into array('f') at the end. Standard library only, deterministic (randomness comes from the
random.Random each recipe is given).
"""
import math

SR = 48000
TAU = 2 * math.pi


def n_of(seconds):
    return max(1, int(round(seconds * SR)))


def silence(seconds):
    return [0.0] * n_of(seconds)


def times(n):
    return [i / SR for i in range(n)]


def osc(n, freq, shape='sine', phase=0.0, duty=0.5):
    """An oscillator of n samples. `freq` is a number or a function of t (seconds) -> Hz. Shapes: sine, saw, square,
    pulse (with duty), triangle. Band-unlimited (the recipes low-pass what needs it)."""
    out = [0.0] * n
    f = freq if callable(freq) else None
    inc_const = 0.0 if f else freq / SR
    p = phase
    for i in range(n):
        inc = f(i / SR) / SR if f else inc_const
        p += inc
        x = p - math.floor(p)
        if shape == 'sine':
            out[i] = math.sin(TAU * x)
        elif shape == 'saw':
            out[i] = 2 * x - 1
        elif shape == 'square':
            out[i] = 1.0 if x < 0.5 else -1.0
        elif shape == 'pulse':
            out[i] = 2 * (1 - duty) if x < duty else -2 * duty
        elif shape == 'triangle':
            out[i] = 4 * abs(x - 0.5) - 1
        else:
            raise ValueError(shape)
    return out


def noise(n, rnd):
    return [rnd.uniform(-1.0, 1.0) for _ in range(n)]


def svf(xs, cutoff, q=0.7, mode='lp'):
    """Chamberlin state-variable filter. `cutoff` (Hz) is a number or a function of t; mode lp, bp, hp or notch.
    Cutoff is kept under SR/6 so the filter stays stable."""
    f = cutoff if callable(cutoff) else None
    damp = 1.0 / max(0.5, q)
    lo = bd = 0.0
    out = [0.0] * len(xs)
    k_const = 2 * math.sin(math.pi * min(cutoff, SR / 6) / SR) if not f else 0.0
    for i, x in enumerate(xs):
        k = 2 * math.sin(math.pi * min(max(20.0, f(i / SR)), SR / 6) / SR) if f else k_const
        lo += k * bd
        hi = x - lo - damp * bd
        bd += k * hi
        out[i] = lo if mode == 'lp' else bd if mode == 'bp' else hi if mode == 'hp' else hi + lo
    return out


def onepole(xs, cutoff):
    k = 1 - math.exp(-TAU * cutoff / SR)
    y, out = 0.0, [0.0] * len(xs)
    for i, x in enumerate(xs):
        y += k * (x - y)
        out[i] = y
    return out


def highpass(xs, cutoff):
    low = onepole(xs, cutoff)
    return [x - l for x, l in zip(xs, low)]


def env_ad(n, attack, decay):
    """Linear attack over `attack` seconds, then exponential decay with time constant `decay` seconds."""
    a = max(1, int(attack * SR))
    d = max(1e-4, decay) * SR
    return [i / a if i < a else math.exp(-(i - a) / d) for i in range(n)]


def env_adsr(n, attack, decay, sustain, release):
    """Attack, decay to `sustain`, held, released linearly over the last `release` seconds."""
    a, d, r = max(1, int(attack * SR)), max(1, int(decay * SR)), max(1, int(release * SR))
    out = [0.0] * n
    for i in range(n):
        if i < a:
            g = i / a
        elif i < a + d:
            g = 1 - (1 - sustain) * (i - a) / d
        else:
            g = sustain
        if i >= n - r:
            g *= (n - i) / r
        out[i] = g
    return out


def env_points(n, points):
    """Piecewise-linear gain from (seconds, gain) points."""
    pts = sorted(points)
    out = [0.0] * n
    j = 0
    for i in range(n):
        t = i / SR
        while j + 1 < len(pts) and pts[j + 1][0] <= t:
            j += 1
        if t <= pts[0][0]:
            out[i] = pts[0][1]
        elif j + 1 >= len(pts):
            out[i] = pts[-1][1]
        else:
            (t0, g0), (t1, g1) = pts[j], pts[j + 1]
            out[i] = g0 + (g1 - g0) * (t - t0) / max(1e-9, t1 - t0)
    return out


def mul(a, b):
    return [x * y for x, y in zip(a, b)]


def gain(xs, g):
    return [x * g for x in xs]


def mix_into(out, src, at_seconds=0.0, g=1.0):
    """out += src * g starting at `at_seconds`; out grows to fit."""
    start = int(round(at_seconds * SR))
    end = start + len(src)
    if end > len(out):
        out.extend([0.0] * (end - len(out)))
    for i, x in enumerate(src):
        out[start + i] += x * g
    return out


def add(*parts):
    n = max(len(p) for p in parts)
    out = [0.0] * n
    for p in parts:
        for i, x in enumerate(p):
            out[i] += x
    return out


def partials(n, base, ratios, decays, amps=None, attack=0.002):
    """A struck sound: sine partials at base*ratio, each decaying with its own time constant."""
    amps = amps or [1.0] * len(ratios)
    out = [0.0] * n
    a = max(1, int(attack * SR))
    for r, d, amp in zip(ratios, decays, amps):
        w = TAU * base * r / SR
        dd = d * SR
        for i in range(n):
            e = (i / a if i < a else 1.0) * math.exp(-i / dd)
            out[i] += amp * e * math.sin(w * i)
    total = sum(amps)
    return [x / total for x in out]


def room(xs, size=0.5, mix=0.25, decay=0.5):
    """A small feedback-delay room (four combs, prime lengths) for a tail; deterministic."""
    lengths = [int(SR * s * (0.6 + size)) for s in (0.0297, 0.0371, 0.0411, 0.0437)]
    tail = int(SR * decay * 2)
    n = len(xs) + tail
    dry = xs + [0.0] * tail
    wet = [0.0] * n
    fb = 0.55 + 0.35 * min(1.0, decay)
    for L in lengths:
        buf = [0.0] * L
        j = 0
        lp = 0.0
        for i in range(n):
            y = buf[j]
            lp += 0.4 * (y - lp)
            buf[j] = dry[i] + lp * fb
            wet[i] += y
            j += 1
            if j == L:
                j = 0
    return [d + mix * w / len(lengths) for d, w in zip(dry, wet)]


def normalize(xs, peak=0.8):
    m = max((abs(x) for x in xs), default=0.0)
    return [x * peak / m for x in xs] if m > 1e-9 else xs


def fade_edges(xs, fade_in=0.002, fade_out=0.01):
    n = len(xs)
    a, b = min(n, int(fade_in * SR)), min(n, int(fade_out * SR))
    out = list(xs)
    for i in range(a):
        out[i] *= i / a
    for i in range(b):
        out[n - 1 - i] *= i / b
    return out


def trim_tail(xs, floor=1e-4):
    """Drops the silent tail (after the last sample above `floor`), keeping 5 ms."""
    last = len(xs) - 1
    while last > 0 and abs(xs[last]) < floor:
        last -= 1
    return xs[:min(len(xs), last + int(0.005 * SR))]


def vowel(n, f0, formants, rnd, breath=0.08, shape='saw', jitter=0.004):
    """A voiced sound: a saw (or pulse) at pitch curve f0(t) with a little seeded jitter, through band-pass formants
    [(Hz or f(t), q, gain)], plus breath noise through the same formants."""
    wob = [rnd.uniform(-1, 1) for _ in range(64)]

    def pitch(t):
        k = t * 30
        i = int(k) % 63
        j = wob[i] + (wob[i + 1] - wob[i]) * (k - int(k))
        return f0(t) * (1 + jitter * j)

    src = osc(n, pitch, shape)
    br = noise(n, rnd)
    src = [s + breath * b for s, b in zip(src, br)]
    out = [0.0] * n
    for fc, q, g in formants:
        band = svf(src, fc, q, 'bp')
        for i, x in enumerate(band):
            out[i] += g * x
    return out
