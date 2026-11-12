"""The original sound library: code-made effects (recipes.py), indexed by name and tags in library.toml.

    names() -> sorted names                      index() -> {name: {"tags": [...], "about": str}}
    render(name, seed=1) -> array('f')           mono 48 kHz, levelled (below); same seed, same samples
    find(tags) -> [(score, name)]                library sounds carrying the given tags, best first

Rendered sounds are cached in the git-ignored cache/audio/library/<name>-<seed>-<code>.f32 (and in memory), <code> a
hash of the recipe code, so a changed recipe is rendered again. Nothing here
reads a game asset: these are the sounds an original-only export uses, and the fallback for any tag the Minecraft
catalog has no sound for. A script plays one in the take as `videocraft:lib/<name>` (logged like any sound, rendered
by the mix), or places it in the edit with [[edit.sfx]] library = "<name>".
"""
import os
import random
import tomllib
from array import array
from pathlib import Path

from videocraft.paths import ROOT

HERE = Path(__file__).resolve().parent
CACHE = Path(os.environ.get('VIDEOCRAFT_AUDIO_CACHE') or ROOT / 'cache' / 'audio') / 'library'
PEAK = 0.9          # no sample above this
LEVEL = 10 ** (-16 / 20)  # RMS over the sound's active 10 ms blocks (within 30 dB of its loudest): -16 dBFS

_index = None
_memory = {}


class UnknownSound(KeyError):
    def __str__(self):
        return self.args[0]


def index():
    global _index
    if _index is None:
        _index = tomllib.loads((HERE / 'library.toml').read_text())['sound']
    return _index


def names():
    return sorted(index())


def check(name):
    if name not in index():
        near = [n for n in names() if n.split('-')[0] in name or name.split('-')[0] in n][:8]
        raise UnknownSound(f'no original sound "{name}"' + (f'; similar: {", ".join(near)}' if near else '') +
                           ' (videocraft audio find <words> lists them)')
    return name


def render(name, seed=1):
    """The sound as mono float32 at 48 kHz, levelled so every sound sits at about the same loudness (LEVEL over its
    active part, never above PEAK): a click is peak-limited, an alarm is turned down. Cached on disk and in memory."""
    from videocraft.audio.library import recipes
    check(name)
    key = (name, int(seed))
    if key in _memory:
        return _memory[key]
    cached = CACHE / f'{name}-{int(seed)}-{code_version()}.f32'
    buf = array('f')
    if cached.exists():
        buf.frombytes(cached.read_bytes())
    else:
        samples = recipes.render(name, random.Random(f'videocraft-library:{name}:{int(seed)}'))
        g = level_gain(samples)
        buf = array('f', [x * g for x in samples])
        CACHE.mkdir(parents=True, exist_ok=True)
        tmp = cached.with_suffix('.part')
        tmp.write_bytes(buf.tobytes())
        tmp.replace(cached)
    _memory[key] = buf
    return buf


_version = None


def code_version():
    global _version
    if _version is None:
        import hashlib
        h = hashlib.sha1(f'{PEAK}:{LEVEL}'.encode())
        for f in ('recipes.py', 'dsp2.py'):
            h.update((HERE / f).read_bytes())
        _version = h.hexdigest()[:8]
    return _version


def find(tags):
    """Library sounds by tag overlap: [(score, name)], best first. A name given as a tag matches itself best."""
    want = [t for t in tags if t]
    out = []
    for name, entry in index().items():
        have = set(entry.get('tags', ())) | {name}
        hits = sum(1 for t in want if t in have)
        if hits:
            out.append((hits * 10 + (5 if name in want else 0) - len(have) * 0.01, name))
    return sorted(out, key=lambda x: (-x[0], x[1]))


def level_gain(samples, block=480):
    """The gain that puts `samples` at LEVEL RMS over its active blocks, capped so the peak stays under PEAK."""
    peak = max((abs(x) for x in samples), default=0.0)
    if peak <= 1e-9:
        return 1.0
    blocks = [sum(x * x for x in samples[i:i + block]) / len(samples[i:i + block]) for i in range(0, len(samples), block)]
    loud = max(blocks)
    active = [b for b in blocks if b > loud * 1e-3]
    rms = (sum(active) / len(active)) ** 0.5
    return min(PEAK / peak, LEVEL / rms)
