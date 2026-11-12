"""An original chiptune bed, generated in pure Python: square-wave melody, triangle bass, noise drums.

    render(seconds, style='upbeat', bpm=None, key=None, seed=1) -> Bed(stems={'melody', 'bass', 'drums'}, bpm, beat, bars)

Deterministic per seed. A style fixes the scale, chord progressions, rhythms, drum pattern and timbres; the seed picks
the melody (phrases A A' B A …, so it sounds written rather than random). The stems stay separate so music cues can
thin the bed to drums, drop it for a beat and bring it back. This is what makes an export shareable without any
game audio.
"""
import math
import random
from array import array
from dataclasses import dataclass, field

from videocraft.audio import dsp, sfx

SR = dsp.SR
NAMES = {'c': 0, 'd': 2, 'e': 4, 'f': 5, 'g': 7, 'a': 9, 'b': 11}
MAJOR, MINOR = (0, 2, 4, 5, 7, 9, 11), (0, 2, 3, 5, 7, 8, 10)

# Per style: scale, default bpm and key, progressions for the A and B sections (chord root semitones above the key and
# quality), melody rhythms (16th-note steps per bar: 1 = a note starts, 0 = hold or rest), drum patterns (16 steps),
# bass pattern (step: octave offset or None), timbre.
STYLES = {
    'upbeat': dict(scale=MAJOR, bpm=128, key='c', a=[(0, 'maj'), (7, 'maj'), (9, 'min'), (5, 'maj')],
                   b=[(5, 'maj'), (7, 'maj'), (4, 'min'), (9, 'min')],
                   rhythms=['1010101010101010', '1010001010100010', '1001001010101000', '1011001010110010'],
                   kick='1000001010000000', snare='0000100000001000', hat='1010101010101010',
                   bass={0: 0, 2: 12, 4: 0, 6: 12, 8: 0, 10: 12, 12: 0, 14: 12}, duty=0.25, legato=0.7, swing=0.0),
    'sneaky': dict(scale=MINOR, bpm=104, key='a', a=[(0, 'min'), (5, 'min'), (0, 'min'), (7, 'maj')],
                   b=[(8, 'maj'), (7, 'maj'), (0, 'min'), (7, 'maj')],
                   rhythms=['0010001000100010', '0010000000101000', '1000001000100000', '0010001010000010'],
                   kick='1000000010000000', snare='0000100000001001', hat='0010001000100010',
                   bass={0: 0, 4: 7, 8: 12, 12: 7}, duty=0.125, legato=0.3, swing=0.12),
    'tense': dict(scale=MINOR, bpm=140, key='d', a=[(0, 'min'), (1, 'maj'), (0, 'min'), (1, 'maj')],
                  b=[(8, 'maj'), (7, 'maj'), (8, 'maj'), (11, 'dim')],
                  rhythms=['1000000010000000', '1000100010000000', '1000000000000000', '1000001000001000'],
                  kick='1000100010001000', snare='0000000010000000', hat='1111111111111111',
                  bass={i: 0 for i in range(16)}, duty=0.5, legato=0.95, swing=0.0),
    'triumphant': dict(scale=MAJOR, bpm=112, key='f', a=[(0, 'maj'), (5, 'maj'), (7, 'maj'), (0, 'maj')],
                       b=[(9, 'min'), (5, 'maj'), (2, 'min'), (7, 'maj')],
                       rhythms=['1000100010101000', '1000001010001000', '1010100010000000', '1000100010001010'],
                       kick='1000001010000000', snare='0000100000001011', hat='1010101010101010',
                       bass={0: 0, 6: 7, 8: 0, 14: 7}, duty=0.5, legato=0.85, swing=0.0),
}
QUALITY = {'maj': (0, 4, 7), 'min': (0, 3, 7), 'dim': (0, 3, 6)}
LEVELS = {'melody': 0.22, 'bass': 0.34, 'kick': 0.62, 'snare': 0.34, 'hat': 0.10}


@dataclass
class Bed:
    stems: dict
    bpm: float
    beat: float
    bars: int
    style: str
    key: str
    notes: list = field(default_factory=list)


def parse_key(key):
    """'c', 'f#', 'bb', 'a minor', 'am' -> (tonic semitone 0-11, minor or None for the style's own)."""
    k = key.strip().lower().replace(' ', '')
    minor = None
    for suffix, is_minor in (('minor', True), ('min', True), ('major', False), ('maj', False), ('m', True)):
        if k.endswith(suffix) and len(k) > len(suffix):
            k, minor = k[:-len(suffix)], is_minor
            break
    if not k or k[0] not in NAMES:
        raise ValueError(f'key = "{key}": write a note name like c, f#, bb, optionally with "minor"')
    semi = NAMES[k[0]] + (1 if k[1:] == '#' else -1 if k[1:] == 'b' else 0)
    if k[1:] not in ('', '#', 'b'):
        raise ValueError(f'key = "{key}": write a note name like c, f#, bb, optionally with "minor"')
    return semi % 12, minor


def midi_freq(m):
    return 440.0 * 2 ** ((m - 69) / 12)


_note_cache = {}


def _square_note(freq, n, level, duty):
    key = ('sq', round(freq, 3), n, level, duty)
    if key not in _note_cache:
        inc = freq / SR
        attack, release = min(n, int(0.003 * SR)), min(n, int(0.02 * SR))
        decay = 0.6 * SR
        raw = [(1.0 if (i * inc) % 1.0 < duty else -1.0) for i in range(n)]
        # A gentle low-pass takes the edge off the naive square (it aliases above a few kHz).
        k = 1 - math.exp(-2 * math.pi * 5200 / SR)
        y, out = 0.0, array('f', bytes(4 * n))
        for i, x in enumerate(raw):
            y += k * (x - y)
            env = (i / attack if i < attack else 0.55 + 0.45 * math.exp(-(i - attack) / decay))
            if i >= n - release:
                env *= (n - i) / release
            out[i] = y * env * level
        _note_cache[key] = out
    return _note_cache[key]


def _triangle_note(freq, n, level):
    key = ('tri', round(freq, 3), n, level)
    if key not in _note_cache:
        inc = freq / SR
        attack, release = min(n, int(0.004 * SR)), min(n, int(0.015 * SR))
        out = array('f', [(4 * abs((i * inc) % 1.0 - 0.5) - 1) * level for i in range(n)])
        for i in range(attack):
            out[i] *= i / attack
        for i in range(release):
            out[n - 1 - i] *= i / release
        _note_cache[key] = out
    return _note_cache[key]


def _melody(style, rnd, tonic, scale, bars_a, bars_b):
    """Two phrases (A and B) of four bars: (bar, step, length in steps, midi) per note."""
    rhythms = style['rhythms']
    base = 60 + tonic + (12 if tonic < 5 else 0)
    # Scale tones over two octaves, as midi numbers.
    tones = [base + o * 12 + s for o in (-1, 0, 1) for s in scale]

    def phrase(chords, motif=None):
        notes, prev = [], base + scale[2]
        bar_rhythms = motif or [rnd.choice(rhythms) for _ in range(4)]
        for bar, (root, quality) in enumerate(chords):
            chord = {(tonic + root + q) % 12 for q in QUALITY[quality]}
            pattern = bar_rhythms[bar % len(bar_rhythms)]
            starts = [i for i, c in enumerate(pattern) if c == '1']
            for j, step in enumerate(starts):
                length = (starts[j + 1] if j + 1 < len(starts) else 16) - step
                strong = step % 4 == 0
                pool = [t for t in tones if (t % 12 in chord or not strong) and abs(t - prev) <= (7 if strong else 4) and base - 3 <= t <= base + 16]
                if not pool:
                    pool = [t for t in tones if t % 12 in chord and base - 3 <= t <= base + 16]
                # Prefer small steps: weight by closeness.
                weights = [1.0 / (1 + abs(t - prev)) ** 1.3 for t in pool]
                pitch = rnd.choices(pool, weights)[0]
                notes.append((bar, step, length, pitch))
                prev = pitch
        return notes, bar_rhythms

    a, motif = phrase(bars_a)
    a2, _ = phrase(bars_a, motif)
    a_var = a[:len(a) - len([n for n in a if n[0] == 3])] + [n for n in a2 if n[0] == 3]
    b, _ = phrase(bars_b)
    return a, a_var, b


def render(seconds, style='upbeat', bpm=None, key=None, seed=1, level=1.0):
    if style not in STYLES:
        raise ValueError(f'music style "{style}": one of {", ".join(STYLES)}')
    st = STYLES[style]
    bpm = float(bpm or st['bpm'])
    if not 40 <= bpm <= 240:
        raise ValueError(f'music bpm = {bpm}: 40 to 240')
    tonic, minor = parse_key(key or st['key'])
    scale = st['scale'] if minor is None else (MINOR if minor else MAJOR)
    rnd = random.Random(f'{seed}:{style}:{bpm}:{tonic}')
    beat = 60.0 / bpm
    step_s = beat / 4
    bar_s = beat * 4
    n = dsp.seconds_to_samples(seconds)
    bars = int(math.ceil(seconds / bar_s)) + 1
    a, a_var, b = _melody(st, rnd, tonic, scale, st['a'], st['b'])
    # Song form: two bars of drums and bass, then A A' B A' and around again.
    form = ['intro', 'intro'] + ['A'] * 4 + ['A2'] * 4 + ['B'] * 4 + ['A2'] * 4
    while len(form) < bars:
        form += ['A'] * 4 + ['A2'] * 4 + ['B'] * 4 + ['A2'] * 4
    stems = {'melody': dsp.zeros(n), 'bass': dsp.zeros(n), 'drums': dsp.zeros(n)}
    drums = {'kick': sfx.kick(1.0), 'snare': sfx.snare(1.0), 'hat': sfx.hat(1.0)}
    swing = st['swing']
    placed = []

    def at(bar, step):
        t = bar * bar_s + step * step_s
        if swing and step % 2 == 1:
            t += swing * step_s
        return dsp.seconds_to_samples(t)

    for bar in range(bars):
        section = form[bar]
        # Every section after the two intro bars runs four bars, so the bar within the phrase is (bar - 2) % 4.
        index = bar % 4 if section == 'intro' else (bar - 2) % 4
        chords = st['b'] if section == 'B' else st['a']
        root, quality = chords[index]
        # Bass: the chord root two octaves down, on the style's pattern.
        bass_root = 36 + (tonic + root) % 12
        for step, octave in st['bass'].items():
            length = max(1, min(4, 16 - step))
            nn = int(length * step_s * SR * (0.9 if style != 'sneaky' else 0.45))
            dsp.add_into(stems['bass'], _triangle_note(midi_freq(bass_root + octave), nn, LEVELS['bass']), at(bar, step))
        # Drums.
        for name in ('kick', 'snare', 'hat'):
            pattern = st[name]
            for step, c in enumerate(pattern):
                if c == '1':
                    accent = 1.0 if step % 4 == 0 else 0.7
                    dsp.add_into(stems['drums'], drums[name], at(bar, step), LEVELS[name] * accent)
        # Melody.
        if section == 'intro':
            continue
        notes = {'A': a, 'A2': a_var, 'B': b}[section]
        for (nbar, step, length, pitch) in notes:
            if nbar != index:
                continue
            nn = max(int(0.03 * SR), int(length * step_s * SR * st['legato']))
            dsp.add_into(stems['melody'], _square_note(midi_freq(pitch), nn, LEVELS['melody'], st['duty']), at(bar, step))
            placed.append((round(bar * bar_s + step * step_s, 4), pitch))
    if level != 1.0:
        for k in stems:
            stems[k] = dsp.scaled(stems[k], level)
    return Bed(stems=stems, bpm=bpm, beat=beat, bars=bars, style=style, key=key or st['key'], notes=placed)


def mixdown(bed):
    out = dsp.zeros(len(bed.stems['melody']))
    for s in bed.stems.values():
        dsp.add_into(out, s, 0)
    return out
