"""The original sound library's recipes: every sound made from oscillators, noise, filters and envelopes, nothing
recorded. Each recipe takes a seeded random.Random and returns mono floats at 48 kHz; the same seed gives the same
samples. library.toml indexes them by name with tags; library/__init__.py renders and caches them.

They are stand-ins in the cartoon sense (a slide whistle, a clown honk, a wah-wah trombone), and the original-only
export's replacements for the Minecraft sounds the catalog maps to them (docs/SOUNDS.md).
"""
import math

from videocraft.audio.library.dsp2 import (
    SR, TAU, add, env_ad, env_adsr, env_points, fade_edges, gain, highpass, mix_into, mul, n_of, noise, onepole, osc,
    partials, room, silence, svf, trim_tail, vowel)

RECIPES = {}


def recipe(name):
    def wrap(fn):
        RECIPES[name] = fn
        return fn
    return wrap


def jit(rnd, amount=0.02):
    """A seeded detune factor, so two seeds of one sound are siblings, not copies."""
    return 1 + rnd.uniform(-amount, amount)


# ---- springs, pops and drops ----

@recipe('boing')
def boing(rnd, base=200.0, seconds=0.8):
    n = n_of(seconds)
    b = base * jit(rnd)
    f = lambda t: b * (1 + 0.7 * math.exp(-t * 7)) * (1 + 0.22 * math.exp(-t * 3.5) * math.sin(TAU * 11 * t))
    body = osc(n, f, 'sine')
    over = osc(n, lambda t: 2.01 * f(t), 'sine')
    env = env_ad(n, 0.003, seconds / 3.2)
    return mul(add(body, gain(over, 0.25)), env)


@recipe('boing-low')
def boing_low(rnd):
    return boing(rnd, base=95.0, seconds=0.9)


@recipe('spring')
def spring(rnd):
    n = n_of(0.9)
    b = 330 * jit(rnd)
    out = [0.0] * n
    for ratio, amp in ((1.0, 1.0), (2.37, 0.5), (3.91, 0.3)):
        f = lambda t, r=ratio: b * r * (1 + 0.12 * math.exp(-t * 4) * math.sin(TAU * 17 * t))
        out = add(out, gain(osc(n, f, 'sine'), amp))
    return mul(out, env_ad(n, 0.001, 0.22))


@recipe('pop')
def pop(rnd, top=900.0, low=180.0, seconds=0.08):
    n = n_of(seconds)
    t0 = top * jit(rnd, 0.05)
    tone = osc(n, lambda t: t0 * math.exp(-t * 32) + low, 'sine')
    click = mul(highpass(noise(n, rnd), 2000), env_ad(n, 0.0005, 0.003))
    return add(mul(tone, env_ad(n, 0.001, seconds / 3)), gain(click, 0.35))


@recipe('pop-high')
def pop_high(rnd):
    return pop(rnd, top=1700.0, low=420.0, seconds=0.06)


@recipe('cork-pop')
def cork_pop(rnd):
    n = n_of(0.25)
    burst = mul(svf(noise(n, rnd), 1400, 3, 'bp'), env_ad(n, 0.0005, 0.012))
    tone = mul(osc(n, lambda t: 520 * math.exp(-t * 9) + 250, 'sine'), env_ad(n, 0.001, 0.05))
    return add(gain(burst, 1.6), gain(tone, 0.6))


@recipe('plop')
def plop(rnd, base=320.0):
    # A water drop: the bubble's resonance rises as it closes.
    n = n_of(0.16)
    b = base * jit(rnd, 0.06)
    tone = osc(n, lambda t: b * (1 + 9 * t / 0.16) ** 0.9, 'sine')
    return mul(tone, env_points(n, [(0, 0), (0.004, 1), (0.05, 0.6), (0.16, 0)]))


@recipe('bubble')
def bubble(rnd):
    out = silence(0.9)
    t = 0.0
    while t < 0.7:
        mix_into(out, plop(rnd, base=rnd.uniform(380, 900)), t, rnd.uniform(0.35, 0.8))
        t += rnd.uniform(0.05, 0.14)
    return out


@recipe('gulp')
def gulp(rnd):
    n = n_of(0.35)
    f = lambda t: 140 + 220 * math.sin(math.pi * min(1.0, t / 0.18))
    body = svf(osc(n, f, 'triangle'), 600, 1.2, 'lp')
    return mul(body, env_points(n, [(0, 0), (0.02, 1), (0.2, 0.7), (0.35, 0)]))


# ---- bells, chimes and rewards ----

def bell(rnd, base, seconds=1.4, decay=0.45):
    # Inharmonic partials of a small bell.
    n = n_of(seconds)
    return partials(n, base * jit(rnd, 0.005), [1.0, 2.0, 2.76, 5.40, 8.93], [decay, decay * 0.8, decay * 0.5, decay * 0.25, decay * 0.12],
                    [1.0, 0.45, 0.5, 0.18, 0.08])


@recipe('ding')
def ding(rnd):
    return bell(rnd, 1318.5)


@recipe('ding-double')
def ding_double(rnd):
    out = silence(1.4)
    mix_into(out, bell(rnd, 1568.0, 1.0, 0.25), 0.0, 0.8)
    mix_into(out, bell(rnd, 1568.0, 1.2, 0.35), 0.16, 1.0)
    return out


@recipe('cash-register')
def cash_register(rnd):
    out = silence(1.5)
    # The drawer: a rattle of small metallic ticks, then the bell.
    t = 0.0
    while t < 0.22:
        tick = mul(svf(noise(n_of(0.012), rnd), rnd.uniform(3000, 5000), 6, 'bp'), env_ad(n_of(0.012), 0.0005, 0.003))
        mix_into(out, tick, t, 0.9)
        t += rnd.uniform(0.012, 0.03)
    clunk = mul(svf(noise(n_of(0.08), rnd), 500, 2, 'bp'), env_ad(n_of(0.08), 0.001, 0.02))
    mix_into(out, clunk, 0.24, 1.2)
    mix_into(out, bell(rnd, 2093.0, 1.1, 0.35), 0.27, 0.9)
    return out


@recipe('success-chime')
def success_chime(rnd):
    out = silence(1.5)
    for k, f in enumerate((1046.5, 1318.5, 1568.0, 2093.0)):
        mix_into(out, bell(rnd, f, 1.0, 0.3), k * 0.09, 0.6 + 0.1 * k)
    return out


@recipe('level-up')
def level_up(rnd):
    out = silence(0.9)
    notes = (523.25, 659.25, 783.99, 1046.5, 1318.5, 1568.0)
    for k, f in enumerate(notes):
        n = n_of(0.16 if k < len(notes) - 1 else 0.45)
        tone = svf(osc(n, f, 'pulse', duty=0.25), 5000, 0.7, 'lp')
        mix_into(out, mul(tone, env_ad(n, 0.002, 0.08 if k < len(notes) - 1 else 0.2)), k * 0.06, 0.4)
    return out


@recipe('fanfare')
def fanfare(rnd):
    out = silence(1.6)

    def brass(freqs, seconds):
        n = n_of(seconds)
        s = [0.0] * n
        for f in freqs:
            s = add(s, osc(n, lambda t, f=f: f * (1 + 0.004 * math.sin(TAU * 5.5 * t)), 'saw'))
        s = svf(s, lambda t: 900 + 2600 * min(1.0, t / 0.06), 0.9, 'lp')
        return mul(s, env_adsr(n, 0.015, 0.1, 0.75, 0.08))

    mix_into(out, brass((392.0, 493.9, 587.3), 0.16), 0.0, 0.3)
    mix_into(out, brass((392.0, 493.9, 587.3), 0.16), 0.2, 0.3)
    mix_into(out, brass((523.25, 659.25, 783.99), 0.9), 0.4, 0.34)
    return room(out, 0.4, 0.25, 0.5)


@recipe('sparkle')
def sparkle(rnd):
    out = silence(1.1)
    t = 0.0
    while t < 0.8:
        f = rnd.uniform(2500, 6500)
        ping = partials(n_of(0.25), f, [1.0, 2.0], [0.06, 0.03], [1.0, 0.3])
        mix_into(out, ping, t, rnd.uniform(0.2, 0.5) * (1 - t))
        t += rnd.uniform(0.02, 0.07)
    return out


@recipe('magic')
def magic(rnd):
    n = n_of(1.3)
    shimmer = osc(n, lambda t: 700 + 1600 * t + 90 * math.sin(TAU * 7 * t), 'triangle')
    trem = [0.6 + 0.4 * math.sin(TAU * 19 * i / SR) for i in range(n)]
    body = mul(mul(shimmer, trem), env_points(n, [(0, 0), (0.15, 0.6), (0.9, 0.5), (1.3, 0)]))
    return add(gain(body, 0.5), sparkle(rnd))


# ---- air ----

@recipe('whoosh')
def whoosh(rnd, seconds=0.55, lo=300.0, hi=3800.0):
    n = n_of(seconds)
    src = noise(n, rnd)
    band = svf(src, lambda t: lo + (hi - lo) * math.sin(math.pi * min(1.0, t / seconds)) ** 1.5, 1.4, 'bp')
    return mul(band, [math.sin(math.pi * i / n) ** 2 * 1.6 for i in range(n)])


@recipe('whoosh-fast')
def whoosh_fast(rnd):
    return whoosh(rnd, 0.24, 500.0, 5000.0)


@recipe('swish')
def swish(rnd):
    n = n_of(0.2)
    band = svf(noise(n, rnd), lambda t: 6000 - 22000 * t, 1.2, 'bp')
    return mul(band, env_points(n, [(0, 0), (0.03, 1.4), (0.2, 0)]))


@recipe('zap')
def zap(rnd):
    n = n_of(0.35)
    f0 = 2200 * jit(rnd)
    tone = osc(n, lambda t: f0 * math.exp(-t * 9) + 120, 'square')
    ring = osc(n, 57, 'sine')
    return mul(mul(svf(tone, 4500, 0.7, 'lp'), [0.5 + 0.5 * r for r in ring]), env_ad(n, 0.001, 0.12))


@recipe('teleport')
def teleport(rnd):
    n = n_of(0.9)
    tone = osc(n, lambda t: 300 * 2 ** (t * 3.2) * (1 + 0.06 * math.sin(TAU * 23 * t)), 'triangle')
    trem = [0.5 + 0.5 * math.sin(TAU * 31 * i / SR) for i in range(n)]
    return mul(mul(tone, trem), env_points(n, [(0, 0), (0.08, 0.8), (0.7, 0.6), (0.9, 0)]))


# ---- hits ----

@recipe('thud')
def thud(rnd):
    n = n_of(0.2)
    body = osc(n, lambda t: 70 + 60 * math.exp(-t * 30), 'sine')
    dirt = onepole(noise(n, rnd), 700)
    return mul(add(gain(body, 0.9), gain(dirt, 2.2)), env_ad(n, 0.001, 0.045))


@recipe('bonk')
def bonk(rnd):
    # A hollow wooden knock with a pitch that drops: the cartoon head bonk.
    n = n_of(0.3)
    b = 620 * jit(rnd)
    out = [0.0] * n
    for r, d, a in ((1.0, 0.07, 1.0), (2.3, 0.03, 0.4), (0.5, 0.05, 0.5)):
        out = add(out, gain(mul(osc(n, lambda t, r=r: b * r * (1 - 0.25 * min(1.0, t / 0.2)), 'sine'), env_ad(n, 0.0005, d)), a))
    return out


@recipe('splat')
def splat(rnd):
    n = n_of(0.4)
    src = noise(n, rnd)
    wet = svf(src, lambda t: 2400 * math.exp(-t * 9) + 200, 2.5, 'lp')
    burble = [1 + 0.6 * math.sin(TAU * 38 * i / SR) for i in range(n)]
    return mul(mul(wet, burble), env_points(n, [(0, 0), (0.003, 1.3), (0.06, 0.6), (0.4, 0)]))


@recipe('click')
def click(rnd):
    n = n_of(0.02)
    return mul(svf(noise(n, rnd), 3500 * jit(rnd), 2, 'bp'), env_ad(n, 0.0002, 0.0018))


@recipe('click-soft')
def click_soft(rnd):
    n = n_of(0.03)
    return mul(svf(noise(n, rnd), 1500, 2, 'bp'), env_ad(n, 0.0005, 0.004))


@recipe('tick')
def tick(rnd):
    n = n_of(0.03)
    return mul(add(svf(noise(n, rnd), 6000, 8, 'bp'), gain(osc(n, 3200, 'sine'), 0.3)), env_ad(n, 0.0002, 0.003))


@recipe('knock')
def knock(rnd):
    out = silence(0.45)
    for t in (0.0, 0.18):
        n = n_of(0.12)
        k = add(mul(svf(noise(n, rnd), 240, 4, 'bp'), env_ad(n, 0.0005, 0.02)),
                gain(mul(osc(n, 180 * jit(rnd), 'sine'), env_ad(n, 0.0005, 0.03)), 0.3))
        mix_into(out, k, t, 2.0)
    return out


@recipe('explosion')
def explosion(rnd):
    n = n_of(2.2)
    src = noise(n, rnd)
    body = svf(src, lambda t: 1800 * math.exp(-t * 2.5) + 90, 0.8, 'lp')
    rumble = osc(n, lambda t: 45 + 20 * math.exp(-t * 6), 'sine')
    crackle = [x if rnd.random() < 0.002 * math.exp(-i / SR * 2) else 0.0 for i, x in enumerate(src)]
    env = env_points(n, [(0, 0), (0.005, 1), (0.25, 0.6), (2.2, 0)])
    return mul(add(gain(body, 2.0), gain(rumble, 0.6), gain(crackle, 3.0)), env)


@recipe('shatter')
def shatter(rnd):
    # Glass: a bright noise crack, then a shower of small high inharmonic shards.
    out = mul(svf(noise(n_of(0.12), rnd), 5000, 0.8, 'hp'), env_ad(n_of(0.12), 0.0005, 0.025))
    out = out + [0.0] * n_of(0.8)
    t = 0.01
    while t < 0.6:
        f = rnd.uniform(2500, 7000)
        shard = partials(n_of(0.12), f, [1.0, 1.73, 2.61], [0.03, 0.02, 0.012], [1.0, 0.5, 0.3])
        mix_into(out, shard, t, rnd.uniform(0.2, 0.6) * (1 - t / 0.7))
        t += rnd.uniform(0.008, 0.05)
    return out


@recipe('rumble')
def rumble(rnd):
    n = n_of(2.4)
    low = svf(noise(n, rnd), 110, 0.8, 'lp')
    return mul(gain(low, 5.0), env_points(n, [(0, 0), (0.6, 1), (1.6, 0.8), (2.4, 0)]))


@recipe('heartbeat')
def heartbeat(rnd):
    out = silence(1.0)
    for t, g in ((0.0, 1.0), (0.22, 0.7)):
        n = n_of(0.18)
        beat = mul(osc(n, lambda tt: 55 + 25 * math.exp(-tt * 25), 'sine'), env_ad(n, 0.004, 0.05))
        mix_into(out, beat, t, g)
    return out


@recipe('splash')
def splash(rnd):
    n = n_of(0.9)
    body = svf(noise(n, rnd), lambda t: 3500 * math.exp(-t * 3) + 400, 0.8, 'lp')
    out = mul(gain(body, 1.6), env_points(n, [(0, 0), (0.01, 1), (0.15, 0.5), (0.9, 0)]))
    t = 0.08
    while t < 0.7:
        mix_into(out, plop(rnd, base=rnd.uniform(500, 1200)), t, rnd.uniform(0.1, 0.3))
        t += rnd.uniform(0.03, 0.09)
    return out


@recipe('munch')
def munch(rnd):
    out = silence(0.75)
    for k in range(3):
        n = n_of(0.12)
        crunch = [x if rnd.random() < 0.35 else 0.0 for x in noise(n, rnd)]
        bite = mul(svf(crunch, 2200, 1.0, 'lp'), env_points(n, [(0, 0), (0.01, 1), (0.12, 0)]))
        mix_into(out, bite, k * 0.22 + rnd.uniform(0, 0.03), 1.5)
    return out


# ---- footsteps ----

def step(rnd, centre, q, seconds, grains=0.0, body=0.0, body_hz=150.0):
    n = n_of(seconds)
    src = noise(n, rnd)
    if grains:
        src = [x if rnd.random() < grains else 0.0 for x in src]
    out = mul(svf(src, centre * jit(rnd, 0.08), q, 'bp'), env_points(n, [(0, 0), (0.004, 1), (seconds * 0.35, 0.5), (seconds, 0)]))
    if body:
        out = add(gain(out, 1.5), gain(mul(osc(n, body_hz * jit(rnd), 'sine'), env_ad(n, 0.001, 0.02)), body))
    return gain(out, 1.5)


@recipe('footstep-wood')
def footstep_wood(rnd):
    return step(rnd, 900, 2.5, 0.09, body=0.5, body_hz=170)


@recipe('footstep-stone')
def footstep_stone(rnd):
    return step(rnd, 2600, 1.6, 0.07, body=0.2, body_hz=300)


@recipe('footstep-grass')
def footstep_grass(rnd):
    return step(rnd, 2200, 0.9, 0.11, grains=0.3)


@recipe('footstep-sand')
def footstep_sand(rnd):
    return step(rnd, 1300, 0.8, 0.14, grains=0.6)


@recipe('footstep-snow')
def footstep_snow(rnd):
    return step(rnd, 1800, 1.0, 0.13, grains=0.12)


@recipe('footstep-metal')
def footstep_metal(rnd):
    n = n_of(0.25)
    ring = partials(n, 780 * jit(rnd), [1.0, 1.63, 2.58, 3.4], [0.05, 0.04, 0.025, 0.015])
    return add(step(rnd, 3000, 2, 0.06), gain(ring, 0.6))


# ---- squeaks, buzzes and alarms ----

@recipe('squeak')
def squeak(rnd):
    n = n_of(0.18)
    b = 2200 * jit(rnd, 0.06)
    tone = osc(n, lambda t: b * (1 + 0.35 * math.sin(math.pi * t / 0.18)), 'sine')
    return mul(tone, env_points(n, [(0, 0), (0.02, 0.8), (0.14, 0.6), (0.18, 0)]))


@recipe('buzz')
def buzz(rnd):
    n = n_of(0.6)
    tone = svf(osc(n, 110, 'saw'), 2500, 0.8, 'lp')
    trem = [0.7 + 0.3 * math.sin(TAU * 30 * i / SR) for i in range(n)]
    return mul(mul(tone, trem), env_adsr(n, 0.005, 0.05, 0.9, 0.03))


@recipe('error-buzz')
def error_buzz(rnd):
    out = silence(0.6)
    for k, f in enumerate((220.0, 165.0)):
        n = n_of(0.2)
        tone = svf(osc(n, f, 'square'), 2000, 0.7, 'lp')
        mix_into(out, mul(tone, env_adsr(n, 0.004, 0.02, 0.9, 0.02)), k * 0.24, 0.5)
    return out


@recipe('alarm')
def alarm(rnd):
    n = n_of(1.6)
    tone = osc(n, lambda t: 880 if (t * 4) % 1 < 0.5 else 660, 'square')
    return mul(svf(tone, 3000, 0.7, 'lp'), env_adsr(n, 0.01, 0.05, 0.9, 0.05))


@recipe('honk')
def honk(rnd, f0=330.0, seconds=0.35):
    # A clown horn: a reedy pulse through two nasal formants, a little bend at the start.
    n = n_of(seconds)
    b = f0 * jit(rnd, 0.03)
    src = osc(n, lambda t: b * (0.92 + 0.08 * min(1.0, t / 0.04)), 'pulse', duty=0.3)
    voice = add(gain(svf(src, 900, 4, 'bp'), 1.0), gain(svf(src, 2400, 5, 'bp'), 0.6))
    return mul(voice, env_adsr(n, 0.008, 0.05, 0.85, 0.05))


@recipe('honk-double')
def honk_double(rnd):
    out = silence(0.7)
    mix_into(out, honk(rnd, 330.0, 0.18), 0.0)
    mix_into(out, honk(rnd, 330.0, 0.3), 0.24)
    return out


# ---- stings and drums ----

def drum(rnd, top, low, seconds, decay, noise_amt=0.3, noise_hz=1500):
    n = n_of(seconds)
    body = osc(n, lambda t: low + (top - low) * math.exp(-t * 22), 'sine')
    snap = mul(svf(noise(n, rnd), noise_hz, 1, 'bp'), env_ad(n, 0.0005, 0.015))
    return add(mul(body, env_ad(n, 0.001, decay)), gain(snap, noise_amt))


@recipe('drum-hit')
def drum_hit(rnd):
    return drum(rnd, 190, 95, 0.5, 0.12)


@recipe('kick')
def kick(rnd):
    return drum(rnd, 160, 48, 0.4, 0.11, 0.15, 3000)


@recipe('snare')
def snare(rnd):
    n = n_of(0.25)
    rattle = mul(highpass(noise(n, rnd), 1800), env_ad(n, 0.001, 0.05))
    tone = mul(osc(n, 190, 'sine'), env_ad(n, 0.001, 0.03))
    return add(gain(rattle, 0.9), gain(tone, 0.5))


@recipe('cymbal')
def cymbal(rnd):
    n = n_of(2.0)
    hiss = mul(highpass(noise(n, rnd), 5000), env_ad(n, 0.002, 0.5))
    ring = partials(n, 3200, [1.0, 1.41, 1.93, 2.47], [0.4, 0.3, 0.2, 0.15])
    return add(gain(hiss, 0.9), gain(ring, 0.15))


@recipe('snare-roll')
def snare_roll(rnd):
    # A drumroll: hits at about 28 a second, swelling, then a hit and a cymbal.
    out = silence(2.6)
    t, length = 0.0, 1.7
    hit = snare(rnd)
    while t < length:
        g = 0.18 + 0.55 * (t / length) ** 1.6
        mix_into(out, hit[:n_of(0.06)], t, g * rnd.uniform(0.85, 1.0))
        t += 1 / 28 * rnd.uniform(0.9, 1.1)
    mix_into(out, snare(rnd), length, 1.0)
    mix_into(out, drum(rnd, 160, 48, 0.4, 0.11, 0.15, 3000), length, 1.0)
    mix_into(out, cymbal(rnd), length, 0.7)
    return out


@recipe('rimshot')
def rimshot(rnd):
    # Ba-dum-tss.
    out = silence(1.6)
    mix_into(out, drum(rnd, 260, 160, 0.3, 0.08), 0.0, 0.9)
    mix_into(out, drum(rnd, 200, 110, 0.3, 0.1), 0.17, 0.9)
    mix_into(out, kick(rnd), 0.34, 0.7)
    mix_into(out, cymbal(rnd), 0.34, 0.8)
    return out


@recipe('sting-dramatic')
def sting_dramatic(rnd):
    # Dun, dun, DUN: low minor stabs, the last held over a timpani roll.
    out = silence(2.6)

    def stab(freqs, seconds, level):
        n = n_of(seconds)
        s = [0.0] * n
        for f in freqs:
            s = add(s, osc(n, f, 'saw'), gain(osc(n, f * 0.5, 'square'), 0.5))
        s = svf(s, 1400, 0.8, 'lp')
        return gain(mul(s, env_adsr(n, 0.01, 0.15, 0.6, seconds * 0.4)), level)

    chord = (146.83, 174.61, 220.0)
    mix_into(out, stab(chord, 0.3, 0.25), 0.0)
    mix_into(out, stab([f * 0.94 for f in chord], 0.3, 0.25), 0.4)
    mix_into(out, stab([f * 0.89 for f in chord], 1.6, 0.32), 0.85)
    t = 0.85
    while t < 2.2:
        mix_into(out, drum(rnd, 110, 62, 0.4, 0.15, 0.1), t, 0.25 * (2.3 - t))
        t += 0.05
    return room(out, 0.7, 0.3, 0.8)


@recipe('sting-rise')
def sting_rise(rnd):
    n = n_of(1.6)
    up = svf(noise(n, rnd), lambda t: 300 * 2 ** (t * 3.5), 2.0, 'bp')
    saw = svf(osc(n, lambda t: 110 * 2 ** (t * 2), 'saw'), 3000, 0.7, 'lp')
    env = env_points(n, [(0, 0), (1.4, 1), (1.6, 0)])
    return mul(add(gain(up, 1.6), gain(saw, 0.35)), env)


@recipe('sting-spooky')
def sting_spooky(rnd):
    n = n_of(2.2)
    s = [0.0] * n
    for f in (233.08, 246.94, 349.23):
        s = add(s, osc(n, lambda t, f=f: f * (1 + 0.01 * math.sin(TAU * 5 * t)), 'triangle'))
    trem = [0.55 + 0.45 * math.sin(TAU * 9 * i / SR) for i in range(n)]
    return room(mul(mul(gain(s, 0.4), trem), env_points(n, [(0, 0), (0.3, 1), (1.6, 0.8), (2.2, 0)])), 0.8, 0.35, 0.9)


@recipe('fail-trombone')
def fail_trombone(rnd):
    # Wah, wah, wah, waaah: four falling notes with a closing "wah" filter, the last one wobbling.
    out = silence(2.4)
    notes = ((293.66, 0.32), (277.18, 0.32), (261.63, 0.32), (246.94, 1.1))
    t = 0.0
    for k, (f, seconds) in enumerate(notes):
        n = n_of(seconds)
        last = k == len(notes) - 1
        pitch = (lambda tt, f=f: f * (1 - 0.04 * min(1.0, tt / 0.6)) * (1 + 0.02 * math.sin(TAU * 6 * tt))) if last else (lambda tt, f=f: f)
        src = osc(n, pitch, 'saw')
        wah = svf(src, (lambda tt: 500 + 1300 * math.sin(math.pi * min(1.0, tt / 0.3))) if not last else
                  (lambda tt: 500 + 1300 * (0.5 + 0.5 * math.sin(TAU * 3 * tt + math.pi / 2))), 2.5, 'bp')
        mix_into(out, mul(wah, env_adsr(n, 0.02, 0.05, 0.85, 0.06)), t, 0.6)
        t += seconds + 0.04
    return out


# ---- crowd ----

@recipe('crowd-murmur')
def crowd_murmur(rnd):
    # Many people talking: band-limited noise through drifting vowel formants, with syllable-rate wobble.
    n = n_of(3.0)
    out = [0.0] * n
    for v in range(6):
        src = noise(n, rnd)
        f1 = rnd.uniform(400, 800)
        f2 = rnd.uniform(1100, 2200)
        rate = rnd.uniform(3, 6)
        ph = rnd.uniform(0, TAU)
        syll = [0.3 + 0.7 * max(0.0, math.sin(TAU * rate * i / SR + ph)) ** 2 for i in range(n)]
        voice = add(svf(src, lambda t, f1=f1: f1 * (1 + 0.2 * math.sin(TAU * 0.7 * t)), 6, 'bp'),
                    gain(svf(src, lambda t, f2=f2: f2 * (1 + 0.15 * math.sin(TAU * 0.9 * t)), 8, 'bp'), 0.6))
        out = add(out, mul(voice, syll))
    return mul(gain(out, 0.9), env_points(n, [(0, 0), (0.5, 1), (2.4, 1), (3.0, 0)]))


def clap(rnd):
    n = n_of(0.04)
    centre = rnd.uniform(900, 2400)
    src = noise(n, rnd)
    # A clap is three or four very fast reflections of a burst.
    out = [0.0] * n
    for k, g in ((0, 1.0), (int(0.006 * SR), 0.6), (int(0.011 * SR), 0.4)):
        for i in range(n - k):
            out[i + k] += src[i] * g * math.exp(-i / (0.004 * SR))
    return svf(out, centre, 1.2, 'bp')


@recipe('applause')
def applause(rnd):
    out = silence(3.4)
    claps = [clap(rnd) for _ in range(24)]
    for _ in range(1300):
        t = rnd.uniform(0, 3.0)
        density = min(1.0, t / 0.4) * (1.0 if t < 2.2 else max(0.0, 1 - (t - 2.2) / 0.8))
        if rnd.random() < density:
            mix_into(out, rnd.choice(claps), t, rnd.uniform(0.25, 0.7))
    return room(out, 0.6, 0.3, 0.5)


@recipe('cheer')
def cheer(rnd):
    n = n_of(2.4)
    out = [0.0] * n
    for v in range(5):
        f0 = rnd.uniform(220, 420)
        out = add(out, gain(vowel(n, lambda t, f0=f0: f0 * (1 + 0.25 * math.sin(math.pi * min(1.0, t / 0.8))), [(700, 5, 1.0), (1200, 6, 0.6), (2600, 8, 0.25)],
                                  rnd, breath=0.6, jitter=0.02), 0.3))
    out = add(out, gain(applause(rnd)[:n], 0.6))
    return mul(out, env_points(n, [(0, 0), (0.15, 1), (1.6, 0.8), (2.4, 0)]))


# ---- cartoon motion ----

@recipe('slide-whistle-up')
def slide_whistle_up(rnd, lo=420.0, hi=1700.0, seconds=0.7):
    n = n_of(seconds)
    tone = osc(n, lambda t: (lo * (hi / lo) ** (t / seconds)) * (1 + 0.012 * math.sin(TAU * 7 * t)), 'sine')
    breath = svf(noise(n, rnd), lambda t: lo * (hi / lo) ** (t / seconds), 12, 'bp')
    return mul(add(tone, gain(breath, 0.3)), env_points(n, [(0, 0), (0.04, 0.9), (seconds - 0.05, 0.9), (seconds, 0)]))


@recipe('slide-whistle-down')
def slide_whistle_down(rnd):
    return slide_whistle_up(rnd, lo=1700.0, hi=380.0, seconds=0.75)


@recipe('cartoon-fall')
def cartoon_fall(rnd):
    out = silence(2.2)
    mix_into(out, slide_whistle_up(rnd, lo=1900.0, hi=300.0, seconds=1.5), 0.0, 0.8)
    mix_into(out, thud(rnd), 1.55, 1.6)
    return out


@recipe('record-scratch')
def record_scratch(rnd):
    # A hand moving a record back and forth: a tone and noise whose playback speed swings through zero.
    n = n_of(0.55)
    speed = lambda t: math.sin(TAU * 4.2 * t) * (1 - 0.3 * t)
    tone = osc(n, lambda t: 40 + 900 * abs(speed(t)), 'saw')
    hiss = svf(noise(n, rnd), lambda t: 300 + 4500 * abs(speed(t)), 2.0, 'bp')
    amp = [min(1.0, abs(speed(i / SR)) * 1.6) for i in range(n)]
    return mul(add(gain(svf(tone, 2500, 1.0, 'lp'), 0.5), gain(hiss, 1.2)), amp)


@recipe('typewriter')
def typewriter(rnd):
    out = silence(1.9)
    t = 0.0
    for _ in range(12):
        n = n_of(0.03)
        key = add(mul(svf(noise(n, rnd), rnd.uniform(1800, 3200), 3, 'bp'), env_ad(n, 0.0003, 0.004)),
                  gain(mul(osc(n, 180, 'sine'), env_ad(n, 0.0005, 0.006)), 0.4))
        mix_into(out, key, t, 1.6)
        t += rnd.uniform(0.07, 0.13)
    mix_into(out, bell(rnd, 2349.0, 0.6, 0.18), t + 0.08, 0.7)
    return out


@recipe('door-creak')
def door_creak(rnd):
    # Stick-slip: a train of tiny pulses whose rate wanders, through two wooden resonances.
    n = n_of(1.2)
    out = [0.0] * n
    phase = 0.0
    for i in range(n):
        t = i / SR
        rate = 60 + 140 * (0.5 + 0.5 * math.sin(TAU * 0.8 * t + 1)) + 25 * math.sin(TAU * 5 * t)
        phase += rate / SR
        if phase >= 1.0:
            phase -= 1.0
            out[i] = 1.0
    body = add(svf(out, 700, 6, 'bp'), gain(svf(out, 1600, 8, 'bp'), 0.6))
    return mul(gain(body, 3.0), env_points(n, [(0, 0), (0.1, 1), (1.0, 0.8), (1.2, 0)]))


@recipe('crickets')
def crickets(rnd):
    # Awkward silence: a few chirps of three 14 ms pulses of a 4.6 kHz tone.
    out = silence(2.4)
    t = 0.1
    while t < 2.1:
        n = n_of(0.11)
        chirp = [math.sin(TAU * 4600 * i / SR) * (math.sin(math.pi * ((i / SR) % 0.033) / 0.014) if (i / SR) % 0.033 < 0.014 else 0.0) for i in range(n)]
        mix_into(out, chirp, t, 0.4)
        t += rnd.uniform(0.45, 0.7)
    return out


# ---- voices: original animal and people stand-ins ----

@recipe('bleat')
def bleat(rnd):
    # A goat or sheep: a nasal "meh" with a fast goat tremolo.
    n = n_of(0.75)
    f0 = 300 * jit(rnd, 0.05)
    trill = lambda t: f0 * (1 + 0.06 * math.sin(TAU * 9 * t)) * (1 - 0.1 * t)
    v = vowel(n, trill, [(650, 6, 1.0), (1700, 8, 0.7), (2500, 10, 0.3)], rnd, breath=0.15)
    return mul(gain(v, 1.4), env_points(n, [(0, 0), (0.04, 1), (0.55, 0.8), (0.75, 0)]))


@recipe('cluck')
def cluck(rnd):
    out = silence(0.7)
    for k in range(3):
        n = n_of(0.08)
        f0 = 520 * jit(rnd, 0.06)
        v = vowel(n, lambda t, f0=f0: f0 * (1 - 1.5 * t), [(900, 5, 1.0), (2000, 6, 0.6)], rnd, breath=0.3)
        mix_into(out, mul(v, env_ad(n, 0.003, 0.025)), k * 0.15 + rnd.uniform(0, 0.03), 1.6)
    return out


@recipe('yip')
def yip(rnd):
    # A fox's bark: a short high "yip" that jumps up and falls.
    n = n_of(0.22)
    f0 = 700 * jit(rnd, 0.05)
    v = vowel(n, lambda t: f0 * (1 + 0.6 * math.sin(math.pi * min(1.0, t / 0.12))), [(1000, 5, 1.0), (2400, 7, 0.6)], rnd, breath=0.25)
    return mul(gain(v, 1.5), env_points(n, [(0, 0), (0.01, 1), (0.12, 0.6), (0.22, 0)]))


@recipe('moo')
def moo(rnd):
    n = n_of(1.2)
    f0 = 120 * jit(rnd, 0.04)
    v = vowel(n, lambda t: f0 * (1 + 0.15 * math.sin(math.pi * min(1.0, t / 1.0))), [(lambda t: 350 + 300 * min(1.0, t / 0.4), 4, 1.0), (900, 5, 0.5)],
              rnd, breath=0.08)
    return mul(gain(v, 1.3), env_points(n, [(0, 0), (0.15, 1), (0.9, 0.9), (1.2, 0)]))


@recipe('oink')
def oink(rnd):
    n = n_of(0.3)
    f0 = 210 * jit(rnd, 0.05)
    v = vowel(n, lambda t: f0 * (1 + 0.2 * math.sin(TAU * 18 * t)), [(800, 4, 1.0), (1500, 5, 0.6)], rnd, breath=0.5, shape='pulse')
    return mul(gain(v, 1.3), env_points(n, [(0, 0), (0.02, 1), (0.2, 0.7), (0.3, 0)]))


@recipe('meow')
def meow(rnd):
    n = n_of(0.6)
    f0 = 600 * jit(rnd, 0.05)
    v = vowel(n, lambda t: f0 * (1 + 0.3 * math.sin(math.pi * min(1.0, t / 0.4))),
              [(lambda t: 500 + 900 * math.sin(math.pi * min(1.0, t / 0.6)), 4, 1.0), (2600, 8, 0.3)], rnd, breath=0.12)
    return mul(gain(v, 1.4), env_points(n, [(0, 0), (0.03, 0.8), (0.4, 1), (0.6, 0)]))


@recipe('woof')
def woof(rnd):
    n = n_of(0.25)
    f0 = 260 * jit(rnd, 0.05)
    v = vowel(n, lambda t: f0 * (1.2 - 0.6 * t / 0.25), [(600, 3, 1.0), (1300, 4, 0.5)], rnd, breath=0.5)
    return mul(gain(v, 1.4), env_points(n, [(0, 0), (0.01, 1), (0.1, 0.6), (0.25, 0)]))


@recipe('hmm')
def hmm(rnd):
    # A thoughtful "hmm" from a nasal voice: closed-mouth hum that dips and rises.
    n = n_of(0.7)
    f0 = 150 * jit(rnd, 0.04)
    v = vowel(n, lambda t: f0 * (1 - 0.08 * math.sin(math.pi * t / 0.7)), [(260, 3, 1.0), (2200, 8, 0.15)], rnd, breath=0.05)
    return mul(gain(v, 1.6), env_points(n, [(0, 0), (0.06, 1), (0.55, 0.85), (0.7, 0)]))


@recipe('grunt')
def grunt(rnd):
    n = n_of(0.5)
    f0 = 95 * jit(rnd, 0.05)
    v = vowel(n, lambda t: f0 * (1 - 0.2 * t), [(450, 3, 1.0), (1000, 4, 0.6)], rnd, breath=0.6, shape='pulse', jitter=0.03)
    return mul(gain(v, 1.4), env_points(n, [(0, 0), (0.03, 1), (0.35, 0.7), (0.5, 0)]))


@recipe('hiss')
def hiss(rnd):
    n = n_of(0.8)
    return mul(svf(noise(n, rnd), 4500, 1.0, 'bp'), env_points(n, [(0, 0), (0.08, 1), (0.6, 0.8), (0.8, 0)]))


@recipe('yelp')
def yelp(rnd):
    # Hurt: a quick rising-then-falling "ow".
    n = n_of(0.32)
    f0 = 420 * jit(rnd, 0.05)
    v = vowel(n, lambda t: f0 * (1 + 0.5 * math.sin(math.pi * min(1.0, t / 0.18))), [(800, 5, 1.0), (1300, 6, 0.6)], rnd, breath=0.2)
    return mul(gain(v, 1.4), env_points(n, [(0, 0), (0.01, 1), (0.2, 0.7), (0.32, 0)]))


@recipe('scream')
def scream(rnd):
    # A cartoon scream: loud, high, shaking, a long "aaah".
    n = n_of(1.2)
    f0 = 620 * jit(rnd, 0.04)
    v = vowel(n, lambda t: f0 * (1 + 0.25 * math.sin(math.pi * min(1.0, t / 0.2))) * (1 + 0.035 * math.sin(TAU * 8 * t)),
              [(900, 4, 1.0), (1400, 5, 0.7), (2800, 8, 0.4)], rnd, breath=0.3, jitter=0.02)
    return mul(gain(v, 1.3), env_points(n, [(0, 0), (0.03, 1), (0.9, 0.9), (1.2, 0)]))


def render(name, rnd):
    """The named recipe's samples (mono floats at 48 kHz), edges faded, the silent tail dropped."""
    out = RECIPES[name](rnd)
    return fade_edges(trim_tail(out))
