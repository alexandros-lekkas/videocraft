"""Sound effects made from nothing: the `videocraft:*` events a script can play, and the stand-ins the original-only
mode uses for logged game sounds (footstep ticks from filtered noise, note-block notes as tones at the logged pitch, a
few generic hits and plops). Original audio, deterministic, no game asset involved.

EVENTS must match sound/Synth.java in the mod.
"""
import fnmatch
import math
import random
from array import array

from videocraft.audio import dsp

SR = dsp.SR
EVENTS = ('kick', 'snare', 'hat', 'crash', 'ding', 'dun', 'sting', 'cricket', 'pop', 'whoosh', 'boing')

_cache = {}


def _noise(n, seed):
    r = random.Random(seed)
    return [r.uniform(-1.0, 1.0) for _ in range(n)]


def _env(n, attack, decay):
    """Attack (samples) then exponential decay with time constant `decay` samples."""
    a = max(1, attack)
    return [i / a if i < a else math.exp(-(i - a) / decay) for i in range(n)]


def _onepole(xs, cutoff):
    """One-pole low-pass at `cutoff` Hz."""
    k = 1 - math.exp(-2 * math.pi * cutoff / SR)
    y, out = 0.0, []
    for x in xs:
        y += k * (x - y)
        out.append(y)
    return out


def _highpass(xs, cutoff):
    low = _onepole(xs, cutoff)
    return [x - l for x, l in zip(xs, low)]


def kick(level=0.9):
    n = int(0.35 * SR)
    phase, out = 0.0, []
    for i in range(n):
        t = i / SR
        f = 45 + 110 * math.exp(-t * 28)
        phase += 2 * math.pi * f / SR
        out.append(math.sin(phase) * math.exp(-t * 9) * level)
    click = _env(int(0.004 * SR), 1, 30)
    for i, c in enumerate(click):
        out[i] += 0.3 * c * level
    return array('f', out)


def snare(level=0.55):
    n = int(0.22 * SR)
    noise = _highpass(_noise(n, 11), 1500)
    env = _env(n, 24, 0.045 * SR)
    tone = [math.sin(2 * math.pi * 185 * i / SR) * math.exp(-i / (0.03 * SR)) for i in range(n)]
    return array('f', [(0.8 * a * e + 0.45 * b) * level for a, e, b in zip(noise, env, tone)])


def hat(level=0.25, length=0.05):
    n = int(length * SR)
    noise = _highpass(_noise(n, 23), 7000)
    env = _env(n, 8, length * SR / 4)
    return array('f', [a * e * level for a, e in zip(noise, env)])


def crash(level=0.45):
    n = int(1.4 * SR)
    noise = _highpass(_noise(n, 31), 4000)
    env = _env(n, 30, 0.35 * SR)
    return array('f', [a * e * level for a, e in zip(noise, env)])


def tone(freq, length, level=0.5, partials=((1, 1.0),), attack=0.004, decay=0.25):
    n = int(length * SR)
    env = _env(n, int(attack * SR), decay * SR)
    out = [0.0] * n
    for mult, amp in partials:
        w = 2 * math.pi * freq * mult / SR
        for i in range(n):
            out[i] += amp * math.sin(w * i)
    total = sum(a for _, a in partials)
    return array('f', [o / total * e * level for o, e in zip(out, env)])


def square(freq, length, level=0.3, duty=0.5, decay=0.2, cutoff=6000):
    n = int(length * SR)
    inc = freq / SR
    raw = [1.0 if (i * inc) % 1.0 < duty else -1.0 for i in range(n)]
    env = _env(n, int(0.003 * SR), decay * SR)
    return array('f', [x * e * level for x, e in zip(_onepole(raw, cutoff), env)])


def cricket(level=0.35):
    """One chirp: three 14 ms pulses of a 4.6 kHz tone."""
    n = int(0.11 * SR)
    out = []
    for i in range(n):
        t = i / SR
        pulse = (t % 0.033) < 0.014
        env = math.sin(math.pi * (t % 0.033) / 0.014) if pulse else 0.0
        out.append(math.sin(2 * math.pi * 4600 * t) * env * level)
    return array('f', out)


def pop(level=0.6):
    n = int(0.07 * SR)
    phase, out = 0.0, []
    for i in range(n):
        t = i / SR
        f = 900 * math.exp(-t * 30) + 180
        phase += 2 * math.pi * f / SR
        out.append(math.sin(phase) * math.exp(-t * 45) * level)
    return array('f', out)


def whoosh(level=0.4):
    n = int(0.5 * SR)
    noise = _noise(n, 41)
    out = []
    k_lo = 1 - math.exp(-2 * math.pi * 300 / SR)
    y = 0.0
    for i, x in enumerate(noise):
        t = i / n
        k = k_lo + (1 - math.exp(-2 * math.pi * (300 + 3500 * math.sin(math.pi * t)) / SR) - k_lo)
        y += k * (x - y)
        out.append(y * math.sin(math.pi * t) ** 2 * level)
    return array('f', out)


def boing(level=0.5):
    n = int(0.55 * SR)
    phase, out = 0.0, []
    for i in range(n):
        t = i / SR
        f = 220 * (1 + 0.6 * math.exp(-t * 6)) * (1 + 0.04 * math.sin(2 * math.pi * 14 * t))
        phase += 2 * math.pi * f / SR
        out.append(math.sin(phase) * math.exp(-t * 4) * level)
    return array('f', out)


def ding(level=0.5):
    return tone(1318.5, 1.2, level, partials=((1, 1.0), (2.0, 0.35), (3.01, 0.12)), attack=0.002, decay=0.35)


def dun(level=0.6):
    a = square(98, 0.7, level * 0.6, 0.5, 0.25, cutoff=1200)
    b = tone(98, 0.7, level, partials=((1, 1.0), (2, 0.3)), attack=0.005, decay=0.3)
    return array('f', [x + y for x, y in zip(a, b)])


def sting(level=0.45):
    out = dsp.zeros(int(0.8 * SR))
    for k, f in enumerate((523.25, 659.25, 783.99, 1046.5)):
        dsp.add_into(out, square(f, 0.7, level / 3, 0.25, 0.3), int(k * 0.035 * SR))
    return out


_MAKERS = {'kick': kick, 'snare': snare, 'hat': hat, 'crash': crash, 'ding': ding, 'dun': dun, 'sting': sting,
           'cricket': cricket, 'pop': pop, 'whoosh': whoosh, 'boing': boing}


def synth_event(name):
    """A `videocraft:<name>` event's sound (mono), or None."""
    if name not in _MAKERS:
        return None
    key = ('event', name)
    if key not in _cache:
        _cache[key] = _MAKERS[name]()
    return _cache[key]


# ---- Original-only stand-ins for logged game sounds ----

# A note block sample's own pitch at playback rate 1 (note value 12): F#4 for most, octaves apart for some.
_NOTE_BASE = {'harp': 369.99, 'pling': 369.99, 'banjo': 369.99, 'bit': 369.99, 'iron_xylophone': 369.99, 'cow_bell': 739.99,
              'bass': 92.5, 'didgeridoo': 92.5, 'guitar': 185.0, 'flute': 739.99, 'bell': 1479.98, 'chime': 1479.98,
              'xylophone': 1479.98}
_STEP_BRIGHT = {'wood': 2200, 'stone': 3500, 'gravel': 2800, 'grass': 1500, 'sand': 1200, 'snow': 1000, 'wool': 700,
                'metal': 4500, 'ladder': 2200}


def _step(event):
    key = ('step', event)
    if key not in _cache:
        bright = next((v for k, v in _STEP_BRIGHT.items() if k in event), 1800)
        n = int(0.06 * SR)
        noise = _onepole(_highpass(_noise(n, hash_name(event)), 200), bright)
        env = _env(n, 30, 0.012 * SR)
        _cache[key] = array('f', [x * e * 0.9 for x, e in zip(noise, env)])
    return _cache[key]


def _note(instrument):
    key = ('note', instrument)
    if key not in _cache:
        base = _NOTE_BASE.get(instrument, 369.99)
        if instrument in ('bell', 'chime', 'xylophone', 'iron_xylophone', 'cow_bell'):
            s = tone(base, 1.0, 0.5, partials=((1, 1.0), (2.0, 0.3), (3.0, 0.1)), decay=0.25 if instrument != 'xylophone' else 0.1)
        elif instrument in ('bit', 'guitar', 'banjo'):
            s = square(base, 0.6, 0.3, 0.25 if instrument == 'bit' else 0.5, 0.18, cutoff=5000)
        elif instrument in ('bass', 'didgeridoo'):
            s = tone(base, 0.8, 0.6, partials=((1, 1.0), (2, 0.5), (3, 0.2)), decay=0.3)
        elif instrument == 'flute':
            s = tone(base, 0.8, 0.45, partials=((1, 1.0), (2, 0.15)), attack=0.03, decay=0.4)
        else:
            s = tone(base, 0.9, 0.5, partials=((1, 1.0), (2, 0.4), (3, 0.15), (4, 0.08)), attack=0.002, decay=0.22)
        _cache[key] = s
    return _cache[key]


def hash_name(text):
    h = 2166136261
    for c in text.encode():
        h = (h ^ c) * 16777619 & 0xffffffff
    return h


def thud(level=0.6):
    key = ('thud', level)
    if key not in _cache:
        n = int(0.12 * SR)
        noise = _onepole(_noise(n, 53), 600)
        env = _env(n, 20, 0.03 * SR)
        body = [math.sin(2 * math.pi * 90 * i / SR) for i in range(n)]
        _cache[key] = array('f', [(2.5 * x + 0.6 * b) * e * level for x, b, e in zip(noise, body, env)])
    return _cache[key]


def yell(level=0.45):
    key = ('yell', level)
    if key not in _cache:
        n = int(1.1 * SR)
        phase, out = 0.0, []
        for i in range(n):
            t = i / SR
            f = 520 + 160 * math.sin(math.pi * min(1.0, t / 0.25)) + 25 * math.sin(2 * math.pi * 7 * t)
            phase += f / SR
            saw = 2 * (phase % 1.0) - 1
            env = min(1.0, t / 0.03) * (1 if t < 0.8 else max(0.0, 1 - (t - 0.8) / 0.3))
            out.append(saw * env * level)
        _cache[key] = array('f', _onepole(out, 2500))
    return _cache[key]


def stand_in(event):
    """A synthesized stand-in (mono, at playback rate 1) for a logged game event, or None to leave it out.
    Note-block notes are played at the logged pitch by the caller, as game sounds are."""
    name = event.split(':', 1)[1] if ':' in event else event
    if name.startswith('block.note_block.'):
        instrument = name.rsplit('.', 1)[1]
        return {'basedrum': kick(0.8), 'snare': snare(), 'hat': hat()}.get(instrument) or _note(instrument)
    if name.endswith('.step') or fnmatch.fnmatch(name, 'block.*.step'):
        return _step(name)
    if fnmatch.fnmatch(name, '*egg*') or name.endswith('.pickup') or name.endswith('.drop') or 'plop' in name:
        return pop()
    if fnmatch.fnmatch(name, '*scream*'):
        return yell()
    if any(fnmatch.fnmatch(name, p) for p in ('*.hurt', '*.hit', '*attack*', '*.land', '*.fall', '*.place', '*.break')):
        return thud()
    if name.endswith('.jump'):
        return boing(0.3)
    return None
