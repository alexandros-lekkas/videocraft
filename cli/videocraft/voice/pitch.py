"""The pitch of a voice line: median f0 of its voiced frames, standard library only, cached beside the line.

    median_f0(wav) -> Hz or None      a 48 kHz mono line (the voice cache's), decimated to 8 kHz; 30 ms frames every
                                      20 ms over 55-450 Hz; a frame counts when it is within 26 dB of the line's
                                      peak and its normalised autocorrelation is over 0.6
    character_pitches(dialogue)       {character: median over its lines} for edit.dialogue entries with audio

Used by lint (cast_voice: two characters whose lines measure under 3 semitones apart sound alike). On the presets'
neutral line it agrees with a YIN estimate within about a semitone. Each line's value is cached as <wav>.f0.json,
so a second lint costs nothing.
"""
import json
import statistics
from pathlib import Path

RATE = 8000
FRAME, HOP = 0.03, 0.02
LO, HI = 55.0, 450.0
CLARITY = 0.6
VERSION = 2
MAX_LINES = 8       # per character: enough for a median, bounded time


def _decode(path):
    from videocraft.audio import assets
    buf = assets.decode_path(str(path), 1)
    step = 48000 // RATE
    return buf[::step]


def f0_frames(x, rate=RATE):
    n, hop = int(FRAME * rate), int(HOP * rate)
    lo, hi = int(rate / HI), int(rate / LO)
    peak = max(max(x, default=0.0), -min(x, default=0.0)) or 1.0
    gate = (0.05 * peak) ** 2
    out = []
    for i in range(0, len(x) - n - hi, hop):
        f = x[i:i + n + hi]
        head = f[:n]
        e0 = sum(v * v for v in head)
        if e0 / n < gate:
            continue
        corr = []
        for L in range(lo, hi + 1):
            e1 = sum(v * v for v in f[L:L + n])
            c = sum(a * b for a, b in zip(head, f[L:L + n]))
            corr.append(c / (e0 * e1) ** 0.5 if e0 > 0 and e1 > 0 else 0.0)
        best = max(corr, default=0.0)
        if best <= CLARITY:
            continue
        # The shortest lag that nearly matches the best: a period's multiples correlate as well (octave errors).
        k = next(i for i, c in enumerate(corr) if c >= 0.9 * best and (i + 1 >= len(corr) or c >= corr[i + 1]))
        out.append(rate / (lo + k))
    return out


def median_f0(wav):
    wav = Path(wav)
    side = wav.with_name(wav.name + '.f0.json')
    if side.exists():
        try:
            data = json.loads(side.read_text())
            if data.get('v') == VERSION:
                return data.get('f0')
        except (OSError, json.JSONDecodeError):
            pass
    frames = f0_frames(_decode(wav))
    f0 = round(statistics.median(frames), 1) if len(frames) >= 5 else None
    try:
        side.write_text(json.dumps({'v': VERSION, 'f0': f0, 'frames': len(frames)}) + '\n')
    except OSError:
        pass
    return f0


def character_pitches(dialogue, root=None):
    """{character: median f0 of its lines} from edit.dialogue (entries with a `file` that exists)."""
    from videocraft.paths import ROOT
    by = {}
    for d in dialogue or []:
        f = d.get('file')
        if not f or not d.get('character'):
            continue
        p = Path(f) if Path(f).is_absolute() else Path(root or ROOT) / f
        if p.exists() and len(by.setdefault(d['character'], [])) < MAX_LINES:
            by[d['character']].append(p)
    out = {}
    for cid, files in by.items():
        vals = [v for v in (median_f0(p) for p in files) if v]
        out[cid] = round(statistics.median(vals), 1) if vals else None
    return out
