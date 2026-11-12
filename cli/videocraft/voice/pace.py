"""Pacing: every synthesized line is tightened before it is used, so dialogue is brisk by default (docs/VOICE.md).

The owner's verdict on the first films: voiced lines beat captions, and the lines were far too slow (1.2-3.5 words
a second, with dead air). So, per line, after synthesis (or after the estimate) and before the resolver times it:

  1. trim    silence before the first word to at most HEAD (60 ms) and after the last to at most TAIL (120 ms);
             only quiet audio is cut, never a word's decay (an aligned word end can be 80-160 ms early)
  2. caps    a pause inside the line to at most COMMA (0.25 s) after a comma-like mark or inside a phrase, SENTENCE
             (0.4 s) after . ! ? or an ellipsis; skipped for `style = "deadpan"` and lines marked `beat = true`
  3. stretch a line still slower than pace x TRIGGER (0.85) words a second is time-stretched (ffmpeg atempo, pitch
             kept) towards `pace` (the character's, default PACE = 3.2), by at most MAX_STRETCH (1.2x)

Word timings are carried through exactly: a cut moves every later time back by the cut's length (a time inside a cut
lands on its start), a stretch divides every time by the factor. atempo smears onsets by about 15 ms (under a frame
at 60 fps). Audio is PCM16 mono WAV, cut on quiet stretches with 5 ms fades, all in the standard library; the paced
line is cached beside the raw one (cache/voice/lines/<key>.p<hash>.wav) so the raw synthesis is never redone.

Words a second is len(words) / (last end - first start), the same measure lint and measure use.
"""
import array
import hashlib
import json
import math
import subprocess
import wave
from pathlib import Path

PACE = 3.2            # words a second a character aims at (cast `pace`)
TRIGGER = 0.85        # stretch when a line is slower than pace x this
MAX_STRETCH = 1.2
MIN_WORDS = 3         # a line this short has no meaningful rate: never stretched
HEAD = 0.06
TAIL = 0.12
TAIL_MAX = 0.4        # a word's decay is kept, but never more than this after its aligned end
COMMA = 0.25
SENTENCE = 0.4
BLOCK = 0.01          # envelope block (s)
QUIET_DB = -30.0      # a block this far under the line's loud level is pause (Qwen3's murmurs are -45 to -34)
FADE = 0.005
VERSION = 1           # bump when the paced output for the same raw line changes
SLOW_STYLES = ('deadpan', 'sleepy', 'sad')   # never stretched; deadpan also keeps its pauses
SENTENCE_END = ('.', '!', '?', '…', '...')
CLAUSE_END = (',', ';', ':', '—', '–', '-')


def words_per_second(words):
    if not words:
        return None
    span = words[-1]['end'] - words[0]['start']
    return round(len(words) / span, 3) if span > 0 else None


def cap_for(word):
    w = word.rstrip('"\')]*')
    return SENTENCE if w.endswith(SENTENCE_END) else COMMA


def options(spec_pace):
    """The spec's pace dict with defaults: {wps, caps, stretch} (cast.Character.spec turns caps off for deadpan and
    `beat` lines and stretch off for SLOW_STYLES). None: no pacing at all."""
    if spec_pace is None or spec_pace is False:
        return None
    p = dict(spec_pace) if isinstance(spec_pace, dict) else {'wps': float(spec_pace)}
    return {'wps': float(p.get('wps') or 0.0), 'caps': bool(p.get('caps', True)), 'stretch': bool(p.get('stretch', True))}


# --- the edit list -------------------------------------------------------------------------------------------------

def remap(t, cuts):
    """A time in the cut audio: earlier cuts removed, a time inside a cut moved to its start."""
    shift = 0.0
    for s, e in cuts:
        if t >= e:
            shift += e - s
        elif t > s:
            return s - shift
        else:
            break
    return t - shift


def remap_words(words, cuts):
    return [{**w, 'start': round(remap(w['start'], cuts), 4), 'end': round(remap(w['end'], cuts), 4)} for w in words]


def _merge(cuts):
    out = []
    for s, e in sorted(c for c in cuts if c[1] - c[0] > 1e-4):
        if out and s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def cuts_from_words(words, duration, caps=True):
    """The edit list from word timings alone (the estimate, or a line without audio): the same rules as the audio
    path, with every gap taken as silence."""
    if not words:
        return []
    cuts = []
    if words[0]['start'] > HEAD:
        cuts.append((0.0, words[0]['start'] - HEAD))
    if caps:
        for a, b in zip(words, words[1:]):
            gap, cap = b['start'] - a['end'], cap_for(a['word'])
            if gap > cap + 0.01:
                mid = (a['end'] + b['start']) / 2
                cuts.append((mid - (gap - cap) / 2, mid + (gap - cap) / 2))
    if duration is not None and duration - words[-1]['end'] > TAIL:
        cuts.append((words[-1]['end'] + TAIL, duration))
    return _merge(cuts)


def envelope(samples, sr, block=BLOCK):
    """dB per block (RMS re full scale), and the line's loud level (its 95th percentile)."""
    n = max(1, int(round(sr * block)))
    db = []
    for i in range(0, len(samples), n):
        seg = samples[i:i + n]
        s = sum(x * x for x in seg) / max(1, len(seg))
        db.append(10 * math.log10(s / (32768.0 ** 2) + 1e-12))
    ref = sorted(db)[int(0.95 * (len(db) - 1))] if db else -120.0
    return db, ref


def cuts_from_audio(words, db, ref, duration, caps=True, block=BLOCK):
    """The edit list for a line with audio: like cuts_from_words, but only blocks under ref + QUIET_DB are cut."""
    if not words:
        return []
    quiet = [d < ref + QUIET_DB for d in db]
    nb = len(quiet)

    def q(i):
        return 0 <= i < nb and quiet[i]

    def blk(t):
        return min(nb, max(0, int(t / block)))

    cuts = []
    # head: everything quiet from 0 up to HEAD before the first word (and before any sound)
    first = blk(words[0]['start'])
    i = 0
    while i < first and q(i):
        i += 1
    head_end = min(words[0]['start'] - HEAD, i * block - 0.02)
    if head_end > 0.01:
        cuts.append((0.0, head_end))
    # pauses: the quiet run that ends at the next word's onset
    if caps:
        for a, b in zip(words, words[1:]):
            cap = cap_for(a['word'])
            lo = blk(a['start'] + 0.05)
            j = blk(b['start']) - 1
            while j > lo and not q(j) and blk(b['start']) - 1 - j < 3:   # an onset a block or two late
                j -= 1
            k = j
            while k >= lo and q(k):
                k -= 1
            run_s, run_e = (k + 1) * block, (j + 1) * block
            run_e = min(run_e, b['start'])
            length = run_e - run_s
            if length > cap + 0.01:
                mid = (run_s + run_e) / 2
                cuts.append((mid - (length - cap) / 2, mid + (length - cap) / 2))
    # tail: keep TAIL after the last word, or its decay (the last loud block), at most TAIL_MAX
    last = words[-1]['end']
    loud_end = last
    for k in range(blk(last), min(nb, blk(last + TAIL_MAX))):
        if not q(k):
            loud_end = (k + 1) * block
    keep = min(max(last + TAIL, loud_end + 0.03), last + TAIL_MAX)
    if duration - keep > 0.01:
        cuts.append((keep, duration))
    return _merge(cuts)


def stretch_factor(words, opts):
    if not opts or not opts['stretch'] or opts['wps'] <= 0 or len(words) < MIN_WORDS:
        return 1.0
    r = words_per_second(words)
    if not r or r >= opts['wps'] * TRIGGER:
        return 1.0
    return round(min(MAX_STRETCH, opts['wps'] / r), 4)


def scale_words(words, f):
    if f == 1.0:
        return [dict(w) for w in words]
    return [{**w, 'start': round(w['start'] / f, 4), 'end': round(w['end'] / f, 4)} for w in words]


# --- audio ---------------------------------------------------------------------------------------------------------

def read_wav(path):
    with wave.open(str(path), 'rb') as w:
        if w.getsampwidth() != 2 or w.getnchannels() != 1:
            raise ValueError(f'{path}: pacing reads 16-bit mono WAV')
        sr = w.getframerate()
        a = array.array('h')
        a.frombytes(w.readframes(w.getnframes()))
    return a, sr


def write_wav(path, samples, sr):
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(samples.tobytes())


def apply_cuts(samples, sr, cuts, fade=FADE):
    """The samples with every cut removed; 5 ms fades on both sides of each join (both sides are quiet)."""
    out = array.array('h')
    nf = max(1, int(sr * fade))
    pos = 0
    bounds = [(int(round(s * sr)), int(round(e * sr))) for s, e in cuts]
    for s, e in bounds + [(len(samples), len(samples))]:
        s, e = min(s, len(samples)), min(e, len(samples))
        seg = samples[pos:s]
        if pos > 0:   # fade in after a join
            for i in range(min(nf, len(seg))):
                seg[i] = int(seg[i] * i / nf)
        if s < len(samples):   # fade out before a join
            for i in range(min(nf, len(seg))):
                j = len(seg) - 1 - i
                seg[j] = int(seg[j] * i / nf)
        out.extend(seg)
        pos = e
    return out


def atempo(src, dst, f, ffmpeg='ffmpeg'):
    subprocess.run([ffmpeg, '-v', 'error', '-y', '-i', str(src), '-af', f'atempo={f:.4f}', '-ac', '1', '-c:a', 'pcm_s16le',
                    str(dst)], check=True)


def pace_words(words, duration, opts):
    """Estimated timings (no audio): trim, caps, stretch, on the words alone. -> (words, info)."""
    raw = words_per_second(words)
    cuts = cuts_from_words(words, duration, bool(opts and opts['caps']))
    w = remap_words(words, cuts)
    f = stretch_factor(w, opts)
    w = scale_words(w, f)
    return w, _info(raw, w, cuts, f, opts)


def _info(raw, words, cuts, f, opts):
    return {'wps_raw': raw, 'wps': words_per_second(words), 'stretch': f, 'trimmed': round(sum(e - s for s, e in cuts), 3),
            'cuts': len(cuts), 'target': opts['wps'] if opts else None, 'version': VERSION}


def pace_key(key, opts):
    data = {'key': key, 'opts': opts, 'v': VERSION,
            'k': [PACE, TRIGGER, MAX_STRETCH, MIN_WORDS, HEAD, TAIL, TAIL_MAX, COMMA, SENTENCE, QUIET_DB]}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:12]


def pace_file(wav, words, opts, out, ffmpeg='ffmpeg'):
    """A synthesized line, paced: writes `out` (WAV) and returns (words, seconds, info)."""
    samples, sr = read_wav(wav)
    duration = len(samples) / sr
    raw = words_per_second(words)
    db, ref = envelope(samples, sr)
    cuts = cuts_from_audio(words, db, ref, duration, bool(opts and opts['caps']))
    cut = apply_cuts(samples, sr, cuts)
    w = remap_words(words, cuts)
    f = stretch_factor(w, opts)
    out = Path(out)
    tmp = out.with_name(out.stem + '.cut.wav')
    write_wav(tmp if f != 1.0 else out, cut, sr)
    seconds = len(cut) / sr
    if f != 1.0:
        atempo(tmp, out, f, ffmpeg)
        tmp.unlink(missing_ok=True)
        with wave.open(str(out), 'rb') as r:
            seconds = r.getnframes() / r.getframerate()
        w = scale_words(w, f)
    end = seconds - 1e-3
    w = [{**x, 'start': min(x['start'], end), 'end': min(x['end'], end)} for x in w]
    return w, round(seconds, 3), _info(raw, w, cuts, f, opts)
