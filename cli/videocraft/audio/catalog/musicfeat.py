"""Measures a music track for the music map: tempo, levels, the first downbeat after the intro, energetic sections and
loop points. ffmpeg decodes the file into memory (mono at 11025 Hz, plus a copy high-passed at 1.5 kHz); everything
else is the standard library. Nothing is written to disk.

    measure(path) -> {seconds, bpm, pulse, level_db, dynamics_db, bright_db, onsets_per_s, entry, energetic, loops, quiet_end}

Method (frames of 10 ms):
  onset envelope   half-wave rectified rise of log energy, the high band counted double (attacks are bright), minus
                   its 0.5 s local mean
  tempo            the autocorrelation of the onset envelope over 60-180 bpm, weighted toward 120 bpm (an octave of
                   spread) so a strong half or double time does not win; `pulse` is the normalized peak (0-1)
  entry            the first 1 s window within 3 dB of the median level, snapped to the strongest onset from 0.5 s
                   before it to 1.5 s after
  energetic        8 s windows (1 s steps) by level plus onset density; the best three that do not overlap
  loops            pairs of strong onsets a < b, 12-60 s apart (a whole number of beats when the pulse is steady), whose
                   surroundings match: level and brightness over 1 s before and 2 s after, compared in 100 ms steps
"""
import math
import operator
import subprocess
from array import array

from videocraft import tools

RATE = 11025
HOP = 110                   # samples per frame: 100.2 frames a second
FPS = RATE / HOP
FLOOR = 1e-10
MIN_ONSET = 3.0             # dB of rise (high band counted double) for an attack to count as a note


def decode(path):
    """(full, high) mono float arrays at RATE."""
    graph = (f'[0:a]aformat=channel_layouts=mono,aresample={RATE},aformat=sample_fmts=flt,asplit=2[a][b];'
             '[b]highpass=f=1500,highpass=f=1500,aformat=sample_fmts=flt[h];[a][h]join=inputs=2:channel_layout=stereo[o]')
    out = subprocess.run([tools.ffmpeg(), '-v', 'error', '-i', str(path), '-filter_complex', graph, '-map', '[o]', '-f', 'f32le', '-'],
                         check=True, capture_output=True).stdout
    data = array('f')
    data.frombytes(out)
    return data[0::2], data[1::2]


def frame_energy(x):
    out = []
    for i in range(0, len(x) - HOP + 1, HOP):
        seg = x[i:i + HOP]
        out.append(sum(map(operator.mul, seg, seg)) / HOP)
    return out


def db(e):
    return 10 * math.log10(max(e, FLOOR))


def moving_mean(xs, width):
    half = width // 2
    out, total = [], 0.0
    pre = [0.0]
    for x in xs:
        total += x
        pre.append(total)
    n = len(xs)
    for i in range(n):
        a, b = max(0, i - half), min(n, i + half + 1)
        out.append((pre[b] - pre[a]) / (b - a))
    return out


def onset_envelope(full_db, high_db):
    raw = [0.0]
    for i in range(1, len(full_db)):
        raw.append(max(0.0, high_db[i] - high_db[i - 1]) * 2 + max(0.0, full_db[i] - full_db[i - 1]))
    local = moving_mean(raw, int(0.5 * FPS))
    return [max(0.0, r - m) for r, m in zip(raw, local)]


def tempo(onsets):
    """(bpm, pulse strength 0-1) from the onset envelope."""
    mean = sum(onsets) / max(1, len(onsets))
    o = [x - mean for x in onsets]
    energy = sum(map(operator.mul, o, o))
    if energy <= 0 or len(o) < 4 * FPS:
        return 0.0, 0.0
    lo, hi = int(FPS * 60 / 180), int(FPS * 60 / 60) + 1
    r = {}
    for lag in range(lo - 1, hi + 2):
        r[lag] = sum(map(operator.mul, o, o[lag:])) / energy
    best, best_score = lo, -1e9
    for lag in range(lo, hi + 1):
        bpm = 60 * FPS / lag
        weight = math.exp(-0.5 * (math.log2(bpm / 120)) ** 2)
        score = r[lag] * weight
        if score > best_score and r[lag] >= r[lag - 1] and r[lag] >= r[lag + 1]:
            best, best_score = lag, score
    # Parabolic interpolation of the peak.
    a, b, c = r[best - 1], r[best], r[best + 1]
    shift = 0.5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) != 0 else 0.0
    lag = best + max(-0.5, min(0.5, shift))
    return 60 * FPS / lag, max(0.0, r[best])


def peaks(onsets, min_gap):
    """Indices of local maxima of the onset envelope above its 75th percentile (and MIN_ONSET), at least min_gap frames
    apart, strongest first."""
    if not onsets:
        return []
    srt = sorted(onsets)
    thresh = max(MIN_ONSET, srt[int(0.75 * (len(srt) - 1))])
    cands = [i for i in range(1, len(onsets) - 1) if onsets[i] > thresh and onsets[i] >= onsets[i - 1] and onsets[i] >= onsets[i + 1]]
    cands.sort(key=lambda i: -onsets[i])
    chosen = []
    taken = set()
    for i in cands:
        if any(abs(i - j) < min_gap for j in chosen):
            continue
        chosen.append(i)
        taken.add(i)
    return chosen


def measure(path):
    full, high = decode(path)
    seconds = len(full) / RATE
    ef, eh = frame_energy(full), frame_energy(high)
    fdb = [db(e) for e in ef]
    hdb = [db(e) for e in eh]
    onsets = onset_envelope(fdb, hdb)
    bpm, pulse = tempo(onsets)

    # 1 s levels.
    w = int(FPS)
    secs = [db(sum(ef[i:i + w]) / max(1, len(ef[i:i + w]))) for i in range(0, len(ef), w)]
    loud = sorted(secs)
    median = loud[len(loud) // 2] if loud else -100.0
    p10, p90 = (loud[int(0.1 * (len(loud) - 1))], loud[int(0.9 * (len(loud) - 1))]) if loud else (median, median)
    bright = [h - f for h, f in zip(hdb, fdb) if f > median - 20]
    bright_db = sum(bright) / len(bright) if bright else -30.0
    strong = peaks(onsets, int(0.12 * FPS))
    density = len(strong) / max(1.0, seconds)

    k0 = next((k for k, v in enumerate(secs) if v >= median - 3), 0)
    lo, hi = max(0, int((k0 - 0.5) * FPS)), min(len(onsets), int((k0 + 1.5) * FPS))
    entry_frame = max(range(lo, hi), key=lambda i: onsets[i]) if hi > lo else int(k0 * FPS)
    entry = entry_frame / FPS
    quiet_end = (max((k for k, v in enumerate(secs) if v >= median - 6), default=len(secs) - 1) + 1)

    # Energetic 8 s windows.
    span = 8
    per_sec = [0] * (len(secs) + 1)
    for i in strong:
        per_sec[min(len(per_sec) - 1, int(i / FPS))] += 1
    windows = []
    for s in range(0, max(1, len(secs) - span + 1)):
        lev = sum(secs[s:s + span]) / max(1, len(secs[s:s + span]))
        dens = sum(per_sec[s:s + span]) / span
        windows.append((lev + 3 * dens / max(0.5, density), s))
    windows.sort(reverse=True)
    energetic = []
    for _, s in windows:
        if all(abs(s - e[0]) >= span for e in energetic):
            energetic.append([float(s), float(min(seconds, s + span))])
        if len(energetic) == 3:
            break

    loops = find_loops(fdb, hdb, onsets, strong, bpm, pulse, seconds, entry)
    return {'seconds': round(seconds, 2), 'bpm': round(bpm, 1), 'pulse': round(pulse, 3), 'level_db': round(median, 1),
            'dynamics_db': round(p90 - p10, 1), 'bright_db': round(bright_db, 1), 'onsets_per_s': round(density, 2),
            'entry': round(entry, 2), 'energetic': energetic, 'loops': loops, 'quiet_end': float(min(quiet_end, seconds))}


def find_loops(fdb, hdb, onsets, strong, bpm, pulse, seconds, entry):
    step = int(FPS / 10)  # 100 ms
    coarse_f = [sum(fdb[i:i + step]) / len(fdb[i:i + step]) for i in range(0, len(fdb), step)]
    coarse_b = [sum(h - f for h, f in zip(hdb[i:i + step], fdb[i:i + step])) / len(fdb[i:i + step]) for i in range(0, len(fdb), step)]
    before, after = 10, 20
    cands = sorted(strong[:160])
    cands = [i for i in cands if i / FPS >= max(entry, 1.0) and i / FPS <= seconds - 3]
    beat = 60 / bpm if bpm else 0
    found = []
    for x, a in enumerate(cands):
        for b in cands[x + 1:]:
            gap = (b - a) / FPS
            if gap < 12 or gap > 60:
                continue
            if pulse >= 0.3 and beat:
                beats = gap / beat
                if abs(beats - round(beats)) > 0.06:
                    continue
            ca, cb = int(a / step), int(b / step)
            if ca < before or cb + after > len(coarse_f):
                continue
            diff = 0.0
            for k in range(-before, after):
                diff += abs(coarse_f[ca + k] - coarse_f[cb + k]) + 0.5 * abs(coarse_b[ca + k] - coarse_b[cb + k])
            found.append((diff / (before + after), a / FPS, b / FPS))
    found.sort()
    out = []
    for score, a, b in found:
        if all(abs(a - o[0]) > 4 or abs(b - o[1]) > 4 for o in out):
            out.append([round(a, 2), round(b, 2), round(score, 2)])
        if len(out) == 2:
            break
    return out


def guess_mood(feat):
    """A mood from measurements alone, for a track curated.toml does not list."""
    steady = feat['pulse'] >= 0.3
    if steady and feat['bpm'] >= 115 and feat['bright_db'] > -14:
        return ['upbeat', 'playful']
    if feat['dynamics_db'] > 18 and feat['bright_db'] < -18:
        return ['tense', 'mysterious']
    if feat['bright_db'] < -20:
        return ['mysterious', 'calm']
    return ['calm']
