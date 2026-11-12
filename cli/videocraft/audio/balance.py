"""The mix's balance, measured stem by stem: dialogue is king.

    loudness(left, right)             EBU R128 of a stem: {integrated, readings [(t, momentary, short-term)]}
    speech_spans(voices, dialogue)    (start, end, line id, character) of each placed voice line in the cut
    measure(voice, music, sfx, gain, spans, picture=None) -> the `balance` block of cut/audio.json

The master's loudness says nothing about what is heard over what, so the mix measures its own buses (with the
mastering gain applied, so the numbers are the master's): per dialogue line, the voice's loudness and the music's
under it (the power mean of the momentary readings whose 400 ms window sits inside the line) and their difference,
`ratio` (LU the music sits under the voice); the music between lines (readings that touch no line, over picture); the
effects' loudest momentary; the voice's short-term median. measure/ copies the block into metrics.json and report.md,
the review sound sheet prints it, and both warn on a line whose music is less than RATIO_WARN LU under the voice.
"""
import math
import re
import statistics
import subprocess
import tempfile
from pathlib import Path

from videocraft import tools
from videocraft.audio import dsp

RATIO_WARN = 12.0       # LU: music under a line closer to the voice than this is a warning (lint, measure, review)
BETWEEN_TARGET, BETWEEN_SLACK = -24.0, 3.0   # LUFS: music between lines louder than target + slack is a warning
FLOOR = -70.0           # LUFS: a momentary reading at or under this counts as nothing playing
WINDOW = 0.4            # seconds: the momentary window
_LINE = re.compile(r'\bt:\s*([\d.]+)\s.*?\bM:\s*(-?[\d.]+|-?inf|nan)\s+S:\s*(-?[\d.]+|-?inf|nan)')
_I = re.compile(r'\bI:\s*(-?[\d.]+|-?inf)\s+LUFS')


def _num(s):
    try:
        v = float(s)
    except ValueError:
        return FLOOR
    return FLOOR if not math.isfinite(v) or v < FLOOR else v


def parse(text):
    """(readings [(t, M, S)], integrated or None) from ebur128's framelog=verbose output."""
    readings = []
    for line in text.splitlines():
        if 'Parsed_ebur128' in line and ' t:' in line:
            m = _LINE.search(line)
            if m:
                readings.append((float(m.group(1)), _num(m.group(2)), _num(m.group(3))))
    summary = text[text.rfind('Summary:'):] if 'Summary:' in text else ''
    m = _I.search(summary)
    integrated = _num(m.group(1)) if m else None
    return readings, integrated


def loudness(left, right=None, gain_db=0.0):
    """EBU R128 of a stem (mono: the same signal in both channels, as the mix plays it)."""
    right = left if right is None else right
    with tempfile.TemporaryDirectory(prefix='videocraft-balance-') as tmp:
        raw = Path(tmp) / 'stem.f32'
        dsp.write_f32(raw, left, right)
        cmd = [tools.ffmpeg(), '-hide_banner', '-nostdin', '-v', 'verbose', '-f', 'f32le', '-ar', str(dsp.SR), '-ac', '2',
               '-i', str(raw), '-af', f'volume={gain_db:.3f}dB,ebur128=framelog=verbose', '-f', 'null', '-']
        text = subprocess.run(cmd, capture_output=True, text=True).stderr
    readings, integrated = parse(text)
    return {'integrated': integrated, 'readings': readings}


def power_mean(values):
    """The loudness of a run of readings taken together (mean of their powers), FLOOR when there are none."""
    vals = [v for v in values if v is not None]
    if not vals:
        return FLOOR
    return round(10 * math.log10(sum(10 ** (v / 10) for v in vals) / len(vals)), 1)


def inside(readings, start, end):
    """The momentary readings whose 400 ms window lies in [start, end]; for a line shorter than the window, the one
    reading centred nearest its middle."""
    out = [r for r in readings if r[0] - WINDOW >= start - 0.05 and r[0] <= end + 0.05]
    if out or not readings:
        return out
    mid = (start + end) / 2
    return [min(readings, key=lambda r: abs(r[0] - WINDOW / 2 - mid))]


def speech_spans(voices, dialogue=None):
    """(start, end, id, character) in seconds of the cut for each placed voice line (mix.Placed with source voice).
    The words' times from edit.dialogue when they can be matched by file name, else the line file's sounding span."""
    by_file = {}
    for d in dialogue or []:
        if d.get('file') and d.get('words'):
            by_file.setdefault(Path(d['file']).name, d)
    spans = []
    for v in voices:
        d = by_file.get(Path(v.file).name)
        if d:
            a, b = d['words'][0]['start'], d['words'][-1]['end']
            spans.append((round(v.time + a, 3), round(v.time + b, 3), d.get('id') or v.shot, d.get('character')))
        else:
            length = getattr(v, 'length', None) or 0.0
            spans.append((round(v.time, 3), round(v.time + length, 3), v.shot, None))
    return spans


def measure(voice, music, sfx, gain_db, spans, picture_spans=None):
    """The balance block: stems are (left, right) or a mono array (voice); `gain_db` is the mastering gain;
    `spans` from speech_spans; `picture_spans` [(start, end)] where a shot is on screen (music over black is not
    'between lines')."""
    v = loudness(voice, None, gain_db) if voice is not None else None
    m = loudness(*music, gain_db=gain_db) if music is not None else None
    s = loudness(*sfx, gain_db=gain_db) if sfx is not None else None
    lines = []
    for a, b, lid, who in spans:
        vr = inside(v['readings'], a, b) if v else []
        mr = inside(m['readings'], a, b) if m else []
        vl, ml = power_mean([r[1] for r in vr]), power_mean([r[1] for r in mr])
        sl = power_mean([r[1] for r in inside(s['readings'], a, b)]) if s else FLOOR
        lines.append({'id': lid, 'character': who, 'start': a, 'end': b, 'voice': vl, 'music': ml, 'sfx': sl,
                      'ratio': round(vl - ml, 1) if m else None})
    between = []
    if m:
        for t, mom, _ in m['readings']:
            w0 = t - WINDOW
            if any(w0 < b + 0.1 and t > a - 0.1 for a, b, _, _ in spans):
                continue
            if picture_spans is not None and not any(p0 <= w0 and t <= p1 for p0, p1 in picture_spans):
                continue
            if mom > FLOOR:
                between.append(mom)
    short = [r[2] for r in v['readings'] if r[2] > -40] if v else []
    ratios = [l['ratio'] for l in lines if l['ratio'] is not None and l['voice'] > FLOOR]
    return {
        'gain_db': round(gain_db, 2),
        'voice': {'integrated': v['integrated'] if v else None,
                  'short_term_median': round(statistics.median(short), 1) if short else None,
                  'short_term_max': round(max(short), 1) if short else None},
        'music': {'integrated': m['integrated'] if m else None,
                  'under_voice': power_mean([l['music'] for l in lines]) if m and lines else None,
                  'between_lines': power_mean(between) if between else None,
                  'between_lines_p95': round(sorted(between)[int(0.95 * (len(between) - 1))], 1) if between else None},
        'sfx': {'integrated': s['integrated'] if s else None,
                'momentary_max': round(max((r[1] for r in s['readings']), default=FLOOR), 1) if s else None},
        'ratio': {'median': round(statistics.median(ratios), 1) if ratios else None, 'min': min(ratios) if ratios else None,
                  'warn_under': RATIO_WARN, 'close': [l['id'] for l in lines if l['ratio'] is not None and l['voice'] > FLOOR
                                                      and l['ratio'] < RATIO_WARN]},
        'lines': lines,
    }


def warnings(balance):
    """Warnings for measure and the review: music under a line less than RATIO_WARN LU below the voice."""
    out = []
    for l in (balance or {}).get('lines', []):
        if l.get('ratio') is not None and l['voice'] > FLOOR and l['ratio'] < RATIO_WARN:
            out.append(f'music under line {l["id"]} ({l["start"]:.2f}-{l["end"]:.2f} s) is {l["ratio"]:.1f} LU under the voice '
                       f'(less than {RATIO_WARN:g}): voice {l["voice"]}, music {l["music"]} LUFS')
    between = ((balance or {}).get('music') or {}).get('between_lines')
    level = ((balance or {}).get('targets') or {}).get('music_level', BETWEEN_TARGET)
    if between is not None and between > level + BETWEEN_SLACK:
        out.append(f'music between lines at {between} LUFS (louder than {level:g} + {BETWEEN_SLACK:g})')
    return out
