"""Word timings for a line whose text is known: wav2vec2 CTC forced alignment, then onsets snapped to the waveform.

Runs in the voice venv (numpy, torch, transformers), never in the CLI core.

    align(wav, tokens)          -> [{word, start, end}] one per token (seconds); CTC (facebook/wav2vec2-base-960h)
    speech(wav)                 -> per-millisecond speech mask with pause fill taken out, and the fill segments
    bursts(wav)                 -> [[on, off]] runs of speech separated by pauses (seconds)
    snap(words, wav)            -> words whose phrase starts and ends sit on burst edges
    orphans(words, wav)         -> bursts of 150 ms or more that no word covers (the TTS said something unaligned)

Why snap: every aligner is 10-500 ms off at phrase onsets (CTC is peaky and lands late on a stretched "Heyyy"), and
at a pause the waveform is the truth. Why the hysteresis in speech(): Qwen3 fills some pauses with a quiet voiced
murmur (-45 to -34 dB re the loud frames; it reads as a breath, but it is periodic, so spectral flatness and voicing
do not tell it from speech), which a plain -40 dB threshold takes for speech, so the next phrase's onset snapped to
the murmur, 100-240 ms early. The murmur never gets loud, and a dip separates it from the word that follows.
"""
import re
import subprocess

import numpy as np

REPO = 'facebook/wav2vec2-base-960h'
SR = 16000
THR_DB = -40.0          # speech: 10 ms RMS above this, re the file's 99th-percentile frame
MIN_GAP = 0.08          # a pause is at least this long
CORE_DB = -25.0         # a run of speech reaches this somewhere (pause murmur does not)
_model = {}


def load16k(path):
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path), '-ac', '1', '-ar', str(SR), '-f', 'f32le', '-'],
                         check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def letters(token):
    """The alignment target of a token: A-Z and apostrophes ('Jump-off!' -> JUMPOFF). Digits are not aligned:
    spell numbers out in the script."""
    return re.sub(r"[^A-Za-z']", '', token).upper()


def _ctc():
    if not _model:
        from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor
        _model['proc'] = Wav2Vec2Processor.from_pretrained(REPO)
        _model['model'] = Wav2Vec2ForCTC.from_pretrained(REPO).eval()
    return _model['proc'], _model['model']


def align(path, tokens):
    """CTC Viterbi over the known letters (the torchaudio forced-alignment tutorial's method, in numpy). Tokens with
    no letters get the time of their neighbours (they are not spoken as such)."""
    import torch
    proc, model = _ctc()
    vocab = proc.tokenizer.get_vocab()
    blank, sep = vocab['<pad>'], vocab['|']
    wav = load16k(path)
    x = proc(wav, sampling_rate=SR, return_tensors='pt').input_values
    with torch.no_grad():
        em = torch.log_softmax(model(x).logits[0], dim=-1).numpy()   # T x V, 20 ms frames
    T = em.shape[0]
    ratio = len(wav) / SR / T
    spoken = [(i, letters(t)) for i, t in enumerate(tokens) if letters(t)]
    seq, owner = [], []
    for n, (i, core) in enumerate(spoken):
        if n:
            seq.append(sep)
            owner.append(-1)
        for ch in core:
            seq.append(vocab[ch])
            owner.append(i)
    spans = {}
    if seq and T >= len(seq):
        J = len(seq)
        tk = np.array(seq)
        tr = np.full((T + 1, J + 1), -np.inf)
        tr[0, 0] = 0
        tr[1:, 0] = np.cumsum(em[:, blank])
        for t in range(T):
            tr[t + 1, 1:] = np.maximum(tr[t, 1:] + em[t, blank], tr[t, :-1] + em[t, tk])
        j, path = J, []
        for t in range(T, 0, -1):
            stay = tr[t - 1, j] + em[t - 1, blank]
            move = tr[t - 1, j - 1] + em[t - 1, seq[j - 1]] if j > 0 else -np.inf
            if j > 0 and move > stay:
                path.append((j - 1, t - 1))
                j -= 1
            if j == 0:
                break
        first, last = {}, {}
        for k, f in reversed(path):
            o = owner[k]
            if o >= 0:
                first.setdefault(o, f)
                last[o] = f
        for i in first:
            f_end = last[i]
            lid = seq[max(k for k in range(J) if owner[k] == i)]
            while f_end + 1 < T and em[f_end + 1].argmax() == lid:
                f_end += 1
            spans[i] = (first[i] * ratio, (f_end + 1) * ratio)
    out, total = [], len(wav) / SR
    for i, t in enumerate(tokens):
        if i in spans:
            s, e = spans[i]
        else:   # not aligned: just after the previous word (or at 0), zero-ish length
            s = out[-1]['end'] if out else 0.0
            e = s
        out.append({'word': t, 'start': round(float(s), 3), 'end': round(float(min(e, total)), 3), 'aligned': i in spans})
    return out


def _envelope(x, hop):
    win = int(0.010 * SR)
    n = max(1, (len(x) - win) // hop)
    idx = np.arange(n) * hop
    c = np.concatenate([[0.0], np.cumsum(x.astype(np.float64) ** 2)])
    rms = np.sqrt(np.maximum(c[idx + win] - c[idx], 0) / win) + 1e-9
    return 20 * np.log10(rms), win


def speech(path_or_wav, core_db=CORE_DB):
    """(mask, fillers, db): mask[k] is True where millisecond k is speech; fillers are [[on, off]] (seconds) of
    sound above THR_DB that never reaches core_db and is cut off from speech by a dip: pause fill, not words.

    Hysteresis: a run of speech must reach core_db somewhere; its edges are traced outwards from there for as long
    as the envelope stays above THR_DB without a break. A weak /θ/ or /h/ leading into a vowel is contiguous with it
    and stays; Qwen3's pause murmur (voiced, -45 to -34 dB, measured on ryan l3) is separated from the next word by
    a dip and goes."""
    x = load16k(path_or_wav) if not isinstance(path_or_wav, np.ndarray) else path_or_wav
    db, _ = _envelope(x, SR // 1000)
    db = db - np.percentile(db, 99)
    above = db > THR_DB
    mask = np.zeros_like(above)
    fillers, i, n = [], 0, len(above)
    while i < n:
        if above[i]:
            j = i
            while j < n and above[j]:
                j += 1
            if db[i:j].max() > core_db:
                mask[i:j] = True
            elif j - i >= 30:
                fillers.append([round(i / 1000 + 0.005, 4), round(j / 1000 + 0.005, 4)])
            i = j
        else:
            i += 1
    return mask, fillers, db


def bursts(path_or_wav, min_gap=MIN_GAP, min_len=0.03, fill=True):
    """Runs of speech (seconds); runs closer than min_gap are merged. fill=False: plain energy bursts (the PoC's)."""
    if fill:
        mask, _, _ = speech(path_or_wav)
    else:
        x = load16k(path_or_wav) if not isinstance(path_or_wav, np.ndarray) else path_or_wav
        db, _ = _envelope(x, SR // 1000)
        mask = (db - np.percentile(db, 99)) > THR_DB
    half = 0.005   # a 1 ms-hop frame k covers [k, k + 10 ms]; its time is its centre
    segs, i, n = [], 0, len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j < n and mask[j]:
                j += 1
            segs.append([i / 1000 + half, j / 1000 + half])
            i = j
        else:
            i += 1
    merged = []
    for s in segs:
        if merged and s[0] - merged[-1][1] < min_gap:
            merged[-1][1] = s[1]
        else:
            merged.append(s)
    return [[round(a, 4), round(b, 4)] for a, b in merged if b - a >= min_len]


def snap(words, path, bs=None):
    """Each word goes to the burst holding most of its aligned span; the first word of a burst starts at its onset,
    the last ends at its offset. Words inside a burst keep the aligner's times (kept in order)."""
    if not words:
        return words
    bs = bursts(path) if bs is None else bs
    if not bs:
        return [dict(w) for w in words]
    out = [dict(w) for w in words]

    def overlap(w, b):
        return max(0.0, min(w['end'], b[1]) - max(w['start'], b[0]))
    owner = []
    for w in out:
        ov = [overlap(w, b) for b in bs]
        if max(ov) > 0:
            owner.append(int(np.argmax(ov)))
        else:
            owner.append(int(np.argmin([min(abs(w['start'] - b[0]), abs(w['start'] - b[1])) for b in bs])))
    for i in range(1, len(owner)):
        owner[i] = max(owner[i], owner[i - 1])
    for k, (on, off) in enumerate(bs):
        idx = [i for i, o in enumerate(owner) if o == k]
        if idx:
            out[idx[0]]['start'] = round(on, 3)
            out[idx[-1]]['end'] = round(off, 3)
    for i in range(len(out)):
        if i:
            out[i]['start'] = max(out[i]['start'], out[i - 1]['start'] + 0.01)
        out[i]['end'] = max(out[i]['end'], out[i]['start'] + 0.02)
        if i + 1 < len(out):
            out[i]['end'] = min(out[i]['end'], max(out[i + 1]['start'], out[i]['start'] + 0.02))
        out[i]['start'], out[i]['end'] = round(out[i]['start'], 3), round(out[i]['end'], 3)
    return out


def orphans(words, path, bs=None, min_len=0.15):
    bs = bursts(path) if bs is None else bs
    return [b for b in bs if b[1] - b[0] >= min_len
            and not any(min(w['end'], b[1]) > max(w['start'], b[0]) for w in words if w.get('aligned', True))]
