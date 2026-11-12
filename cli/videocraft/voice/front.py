"""The voice front end: standard library only, lives in the CLI core, never imports a model.

Lines are synthesized by the worker (worker/worker.py) in the voice venv, one process per batch, so the models load
once per `script` or compile. Every line is cached under cache/voice/lines/<key>.{wav,words.json,json}, keyed by a
hash of everything that shapes the audio (engine, model, voice, instruction, seed, speed, pitch, loudness, text and
the worker's version): a re-run is instant and bit-identical.

    synthesize(specs, engine)   -> one result per spec: {file, words, seconds, engine, timing, key, cached}
    engine_for(mode)            -> WorkerEngine, EstimateEngine (reading speed, no audio) or None
    estimate(tokens, speed)     -> word timings at reading speed, for scripts without a voice installed
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from videocraft.paths import ROOT

HERE = Path(__file__).resolve().parent
WORKER = HERE / 'worker' / 'worker.py'
REQUIREMENTS = HERE / 'worker' / 'requirements.txt'
VOICE_DIR = Path(os.environ.get('VIDEOCRAFT_VOICE_DIR') or ROOT / 'cache' / 'voice')
VENV = VOICE_DIR / 'venv'
VENV_PY = Path(os.environ.get('VIDEOCRAFT_VOICE_PY') or VENV / 'bin' / 'python')
LINES = VOICE_DIR / 'lines'
# Bump when the worker's output for the same job changes (synthesis, levelling, alignment, snapping): old cache
# entries are then simply not found.
WORKER_VERSION = 2
WEIGHTS = ('hexgrad/Kokoro-82M', 'facebook/wav2vec2-base-960h', 'mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit')
QWEN_WEIGHTS = WEIGHTS[2]
KOKORO_WEIGHTS = WEIGHTS[0]
JOB_KEYS = ('engine', 'model', 'voice', 'instruct', 'seed', 'speed', 'pitch', 'lufs', 'tokens', 'retries')


class VoiceError(RuntimeError):
    pass


def hf_hub():
    """The user's Hugging Face cache, as huggingface_hub resolves it (HF_HUB_CACHE, HF_HOME/hub, ~/.cache)."""
    if os.environ.get('HF_HUB_CACHE'):
        return Path(os.environ['HF_HUB_CACHE'])
    home = os.environ.get('HF_HOME') or Path(os.environ.get('XDG_CACHE_HOME') or Path.home() / '.cache') / 'huggingface'
    return Path(home) / 'hub'


def weights_cached(repo):
    snaps = hf_hub() / ('models--' + repo.replace('/', '--')) / 'snapshots'
    return snaps.is_dir() and any((s / 'config.json').exists() for s in snaps.iterdir())


def installed():
    return VENV_PY.exists() and all(weights_cached(r) for r in WEIGHTS)


def key_of(spec):
    data = {k: spec.get(k) for k in JOB_KEYS}
    data['v'] = WORKER_VERSION
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:20]


def rel(path):
    """A path as edit.voice keeps it: relative to the repository when it is inside it (the mix looks there)."""
    path = Path(path)
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


# --- reading-speed estimate --------------------------------------------------------------------------------------

def syllables(word):
    w = re.sub(r'[^a-z]', '', word.lower())
    if not w:
        return 1 if re.search(r'\d', word) else 0
    groups = re.findall(r'[aeiouy]+', w)
    n = len(groups)
    if w.endswith('e') and n > 1 and not w.endswith(('le', 'ee')):
        n -= 1
    return max(1, n)


def estimate(tokens, speed=1.0):
    """Word timings at about 2.4 words per second (what the Qwen3 cast measured): 0.17 s per syllable plus 0.06 s per
    word, pauses after punctuation. No audio. Used when no voice is installed, so scripts always compile."""
    t, out = 0.12, []
    for tok in tokens:
        d = (0.06 + 0.17 * max(1, syllables(tok))) / speed
        out.append({'word': tok, 'start': round(t, 3), 'end': round(t + d, 3)})
        t += d
        if tok.endswith(('.', '!', '?')):
            t += 0.32 / speed
        elif tok.endswith((',', ';', ':', '—', '-')):
            t += 0.16 / speed
        else:
            t += 0.03 / speed
    return out


# --- engines -------------------------------------------------------------------------------------------------------

class EstimateEngine:
    name = 'estimate'
    audio = False

    def run(self, specs, outs):
        return [{'words': estimate(s['tokens'], float(s.get('speed') or 1.0)), 'engine': 'estimate', 'timing': 'estimated',
                 'seconds': None} for s in specs]


class WorkerEngine:
    """The voice venv's worker: one process for the whole batch (models load once)."""
    name = 'worker'
    audio = True

    def __init__(self, python=None, log=None):
        self.python = Path(python or VENV_PY)
        self.log = log or (lambda s: print(s, file=sys.stderr, flush=True))

    def run(self, specs, outs):
        jobs = [{**{k: s[k] for k in JOB_KEYS if s.get(k) is not None}, 'out': str(o)} for s, o in zip(specs, outs)]
        env = {**os.environ, 'TOKENIZERS_PARALLELISM': 'false', 'PYTHONWARNINGS': 'ignore'}
        if all(weights_cached(r) for r in WEIGHTS):
            env.setdefault('HF_HUB_OFFLINE', '1')   # else every load asks the Hub (94 s once on a slow network)
        self.log(f'voice: synthesizing {len(jobs)} line(s) in the voice worker')
        p = subprocess.Popen([str(self.python), '-I', str(WORKER)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, env=env)
        out, err = p.communicate(json.dumps(jobs))
        results = {}
        for line in out.splitlines():
            if line.startswith('{'):
                r = json.loads(line)
                results[r.get('out')] = r
        notes = [l for l in err.splitlines() if l.startswith('voice: ')]
        for n in notes:
            self.log(n)
        if p.returncode or len(results) < len(jobs):
            tail = '\n'.join(l for l in err.splitlines()[-25:] if 'Warning' not in l)
            raise VoiceError(f'the voice worker failed (exit {p.returncode}, {len(results)} of {len(jobs)} lines):\n{tail}')
        res = []
        for o in outs:
            r = results[str(o)]
            if 'error' in r:
                raise VoiceError(f'voice line {Path(o).stem}: {r["error"]}')
            res.append(r)
        return res


def engine_for(mode=None, log=None):
    """mode: 'estimate'/'off' (no audio), 'voice' (the worker; an error if it is missing), None/'auto' (the worker
    when installed, else the estimate with a warning). VIDEOCRAFT_VOICE sets the default."""
    mode = (mode or os.environ.get('VIDEOCRAFT_VOICE') or 'auto').lower()
    log = log or (lambda s: print(s, file=sys.stderr, flush=True))
    if mode in ('estimate', 'off', 'none', '0', 'no'):
        return EstimateEngine()
    if installed():
        return WorkerEngine(log=log)
    if mode in ('voice', 'on', 'required'):
        raise VoiceError('no voice installed (cache/voice/venv and the weights): bin/videocraft voice setup')
    log('voice: WARNING no voice installed (bin/videocraft voice setup); timings are estimated at reading speed and '
        'the cut has no voice')
    return EstimateEngine()


def synthesize(specs, engine, cache=None):
    """One result per spec. Lines already in the cache are not synthesized again; the rest go to the engine in one
    batch. A result: {file (None without audio), words, seconds, engine, timing, key, cached}."""
    cache = Path(cache or LINES)
    results, todo = [None] * len(specs), []
    for i, s in enumerate(specs):
        key = key_of(s)
        if engine.audio:
            meta, wav = cache / f'{key}.json', cache / f'{key}.wav'
            if meta.exists() and wav.exists():
                r = json.loads(meta.read_text())
                results[i] = {**r, 'file': str(wav), 'key': key, 'cached': True}
                continue
        todo.append((i, key))
    if todo:
        if engine.audio:
            cache.mkdir(parents=True, exist_ok=True)
        outs = [cache / f'{key}.wav' for _, key in todo]
        got = engine.run([specs[i] for i, _ in todo], outs)
        for (i, key), out, r in zip(todo, outs, got):
            words = [{'word': w['word'], 'start': float(w['start']), 'end': float(w['end'])} for w in r['words']]
            if len(words) != len(specs[i]['tokens']):
                raise VoiceError(f'voice line {key}: {len(words)} word timings for {len(specs[i]["tokens"])} words')
            meta = {'words': words, 'seconds': r.get('seconds'), 'engine': r.get('engine'), 'timing': r.get('timing', 'ok'),
                    'seed': r.get('seed'), 'gain_db': r.get('gain_db'), 'rtf': r.get('rtf'), 'spec': {k: specs[i].get(k) for k in JOB_KEYS}}
            if engine.audio:
                (cache / f'{key}.json').write_text(json.dumps(meta, indent=1) + '\n')
            results[i] = {**meta, 'file': str(out) if engine.audio else None, 'key': key, 'cached': False}
    return results


def copy_line(result, dest):
    """`<dest>.wav` and `<dest>.words.json` from a synthesized line (for `voice say -o` and `voice script -o`)."""
    dest = Path(dest).with_suffix('.wav')
    dest.parent.mkdir(parents=True, exist_ok=True)
    if result.get('file'):
        shutil.copyfile(result['file'], dest)
    dest.with_suffix('.words.json').write_text(json.dumps(result['words'], indent=1) + '\n')
    return dest
