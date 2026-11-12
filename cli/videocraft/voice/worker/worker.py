"""The voice worker: runs inside the voice venv (cache/voice/venv), never imported by the CLI core.

    python -I worker.py < jobs.json      one JSON line per job on stdout, as each finishes
    python -I worker.py --prefetch       download the weights into the HF cache (setup)
    python -I worker.py --check          import everything, say which weights are cached (doctor)

A job: {out, tokens, engine, voice, instruct?, speed?, pitch?, seed?, lufs?, model?, retries?}. `tokens` is the line
split on whitespace with the script's * marks removed; the result has one timing per token, in order:
{out, words: [{word, start, end}], seconds, rtf, timing ("ok" or "suspect: ..."), seed, gain_db, engine}.

Per job: synthesize (one model load per process) -> speed/pitch (ffmpeg) -> one static gain to `lufs` (default -20
LUFS, sample peak <= -1 dBFS) -> 48 kHz mono PCM16 `<out>.wav` -> wav2vec2 CTC alignment of the known tokens ->
phrase onsets and ends snapped to the waveform (align.py) -> `<out>.words.json`. A line whose audio has speech no
word covers (an orphan: the autoregressive TTS said something that is not in the text, or the aligner lost a word)
is re-rolled with seed + 1, up to `retries` (2) times; the best take is kept and flagged if it is still suspect.
"""
import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))   # -I leaves the script's folder off sys.path

import numpy as np  # noqa: E402

import align  # noqa: E402

OUT_SR = 48000
QWEN = 'mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit'
KOKORO = 'hexgrad/Kokoro-82M'
WEIGHTS = (KOKORO, align.REPO, QWEN)
_models = {}


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def kokoro(job, seed):
    import torch
    from kokoro import KPipeline
    torch.manual_seed(seed)   # the vocoder's sine source draws noise: seeded, a take repeats bit for bit
    lang = job['voice'][0]
    key = ('kokoro', lang)
    if key not in _models:
        _models[key] = KPipeline(lang_code=lang, repo_id=KOKORO)
    chunks = [r.audio.numpy() for r in _models[key](' '.join(job['tokens']), voice=job['voice'], speed=float(job.get('speed', 1.0)))]
    return np.concatenate(chunks).astype(np.float32), 24000


def qwen3(job, seed):
    import mlx.core as mx
    from mlx_audio.tts.utils import load_model
    repo = job.get('model') or QWEN
    if repo not in _models:
        _models[repo] = load_model(repo)
    m = _models[repo]
    mx.random.seed(seed)      # bit-identical PCM on a re-run (verified)
    kw = {'text': ' '.join(job['tokens']), 'voice': job['voice'], 'lang_code': 'english'}
    if job.get('instruct'):
        kw['instruct'] = job['instruct']
    wav = np.concatenate([np.asarray(r.audio, dtype=np.float32) for r in m.generate(**kw)])
    return wav, int(getattr(m, 'sample_rate', 24000))


ENGINES = {'kokoro': kokoro, 'qwen3': qwen3}


def ffmpeg_f32(wav, sr, af, out_sr=None):
    cmd = ['ffmpeg', '-v', 'error', '-f', 'f32le', '-ar', str(sr), '-ac', '1', '-i', '-']
    if af:
        cmd += ['-af', af]
    if out_sr:
        cmd += ['-ar', str(out_sr)]
    p = subprocess.run(cmd + ['-f', 'f32le', '-'], input=wav.astype(np.float32).tobytes(), capture_output=True, check=True)
    return np.frombuffer(p.stdout, dtype=np.float32).copy()


def post(wav, sr, job):
    """Speed (Qwen3; Kokoro has its own) and pitch: asetrate raises pitch and tempo together, atempo undoes the tempo
    and applies the speed. No rubberband here, so the formants move too: keep pitch within +-2 semitones."""
    pitch = float(job.get('pitch', 0.0))
    speed = 1.0 if job['engine'] == 'kokoro' else float(job.get('speed', 1.0))
    if pitch == 0 and speed == 1.0:
        return wav
    f = 2 ** (pitch / 12)
    return ffmpeg_f32(wav, sr, f'asetrate={int(round(sr * f))},aresample={sr},atempo={speed / f:.6f}')


def level(wav, sr, target, ceiling_db=-1.0):
    """One static gain: integrated loudness to `target` (EBU R128), never a sample peak above ceiling_db. Qwen3
    lines of one voice measured 5-7 LU apart."""
    p = subprocess.run(['ffmpeg', '-nostats', '-f', 'f32le', '-ar', str(sr), '-ac', '1', '-i', '-', '-af', 'ebur128',
                        '-f', 'null', '-'], input=wav.astype(np.float32).tobytes(), capture_output=True)
    err = p.stderr.decode()
    m = re.search(r'I:\s+(-?[\d.]+) LUFS', err[err.rfind('Summary:'):])
    if not m:
        return wav, 0.0
    peak = 20 * np.log10(float(np.max(np.abs(wav))) + 1e-9)
    gain = min(target - float(m.group(1)), ceiling_db - peak)
    return (wav * 10 ** (gain / 20)).astype(np.float32), round(float(gain), 2)


def write_wav(path, wav, sr):
    import soundfile as sf
    sf.write(str(path), np.clip(wav, -1, 1), sr, subtype='PCM_16')


def take(job, seed):
    t0 = time.time()
    wav, sr = ENGINES[job['engine']](job, seed)
    wav = post(wav, sr, job)
    wav, gain = level(wav, sr, float(job.get('lufs', -20.0)))
    wav = ffmpeg_f32(wav, sr, None, OUT_SR) if sr != OUT_SR else wav
    out = Path(job['out'])
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + f'.{seed}.wav')
    write_wav(tmp, wav, OUT_SR)
    ctc = align.align(tmp, job['tokens'])
    bs = align.bursts(tmp)
    lost = [w['word'] for w in ctc if not w['aligned'] and align.letters(w['word'])]
    orphans = align.orphans(ctc, tmp, bs)
    problems = ([f'unaligned {lost}'] if lost else []) + ([f'speech no word covers at {orphans}'] if orphans else [])
    words = [{k: w[k] for k in ('word', 'start', 'end')} for w in align.snap(ctc, tmp, bs)]
    seconds = len(wav) / OUT_SR
    return {'tmp': tmp, 'words': words, 'ctc': ctc, 'seconds': round(seconds, 3), 'gain_db': gain, 'seed': seed,
            'problems': problems, 'wall': time.time() - t0}


def run(job):
    seed = int(job.get('seed', 7))
    takes = []
    for k in range(int(job.get('retries', 2)) + 1):
        t = take(job, seed + k)
        takes.append(t)
        if not t['problems']:
            break
        log(f'voice: {Path(job["out"]).name} seed {seed + k}: {"; ".join(t["problems"])}' + ('; re-rolling' if k < int(job.get('retries', 2)) else ''))
    best = min(takes, key=lambda t: (len(t['problems']), t['seed']))
    out = Path(job['out'])
    best['tmp'].replace(out)
    for t in takes:
        if t is not best:
            t['tmp'].unlink(missing_ok=True)
    out.with_suffix('.words.json').write_text(json.dumps(best['words'], indent=1) + '\n')
    wall = sum(t['wall'] for t in takes)
    return {'out': str(out), 'words': best['words'], 'ctc': best['ctc'], 'seconds': best['seconds'], 'engine': job['engine'],
            'seed': best['seed'], 'gain_db': best['gain_db'], 'takes': len(takes),
            'timing': 'ok' if not best['problems'] else 'suspect: ' + '; '.join(best['problems']),
            'rtf': round(wall / max(best['seconds'], 1e-3), 3)}


def cached(repo):
    from huggingface_hub import try_to_load_from_cache
    return isinstance(try_to_load_from_cache(repo, 'config.json'), str)


def main():
    if '--prefetch' in sys.argv:
        from huggingface_hub import snapshot_download
        for repo in WEIGHTS:
            log(f'fetch {repo}')
            print(json.dumps({'repo': repo, 'path': snapshot_download(repo)}), flush=True)
        return 0
    if '--check' in sys.argv:
        import importlib.metadata as md
        info = {'python': sys.version.split()[0], 'packages': {}, 'weights': {}}
        for name in ('mlx-audio', 'kokoro', 'torch', 'transformers', 'numpy', 'soundfile'):
            try:
                info['packages'][name] = md.version(name)
            except md.PackageNotFoundError:
                info['packages'][name] = None
        for repo in WEIGHTS:
            info['weights'][repo] = cached(repo)
        print(json.dumps(info), flush=True)
        return 0
    jobs = json.load(sys.stdin)
    for job in jobs:
        try:
            print(json.dumps(run(job), default=float), flush=True)
        except Exception as e:   # one bad line must not lose the others: report it and go on
            print(json.dumps({'out': job.get('out'), 'error': f'{type(e).__name__}: {e}'}), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
