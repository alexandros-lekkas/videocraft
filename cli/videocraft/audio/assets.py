"""The user's own game sounds, read from the local asset cache that Loom downloaded for the dev client.

    ~/.gradle/caches/fabric-loom/assets/indexes/<version>.json   {"objects": {"minecraft/sounds/mob/goat/step3.ogg": {"hash": …}}}
    ~/.gradle/caches/fabric-loom/assets/objects/<aa>/<hash>       the file itself

Decoded sounds are kept as 48 kHz float32 in the git-ignored cache/audio/. Nothing from here is ever written into the
repository or next to an export: game audio only ends up mixed into cut/audio.wav (and the cut's video files).
"""
import hashlib
import json
import os
import subprocess
from pathlib import Path

from videocraft import tools
from videocraft.audio import dsp
from videocraft.paths import ROOT

ASSETS = Path(os.environ.get('VIDEOCRAFT_ASSETS') or Path.home() / '.gradle/caches/fabric-loom/assets')
CACHE = Path(os.environ.get('VIDEOCRAFT_AUDIO_CACHE') or ROOT / 'cache' / 'audio')


class MissingAssets(SystemExit):
    """No game asset to read; the message names the file looked for."""


_index = None
_sounds = None
_decoded = {}


def index_file():
    files = sorted((ASSETS / 'indexes').glob('*.json'), key=lambda p: p.stat().st_mtime) if (ASSETS / 'indexes').is_dir() else []
    if not files:
        raise MissingAssets(f'No game asset index: looked for {ASSETS / "indexes" / "*.json"} (run ./gradlew runClient once '
                            f'so Loom downloads the assets, or export with original audio only: [edit] audio = "original")')
    return files[-1]


def available():
    try:
        index_file()
        return True
    except MissingAssets:
        return False


def objects():
    global _index
    if _index is None:
        _index = json.loads(index_file().read_text())['objects']
    return _index


def object_path(key):
    entry = objects().get(key)
    if not entry:
        raise MissingAssets(f'No {key} in the game asset index {index_file()}')
    h = entry['hash']
    path = ASSETS / 'objects' / h[:2] / h
    if not path.exists():
        raise MissingAssets(f'Missing game asset {key}: looked for {path}')
    return path


def sound_key(file):
    """`mob/goat/step3` or `ns:path` (a resolved sound file, as sounds.csv logs it) as an asset index key."""
    ns, _, path = file.rpartition(':')
    return f'{ns or "minecraft"}/sounds/{path}.ogg'


def sounds_json():
    """minecraft's sounds.json: event name -> {"sounds": [...]}."""
    global _sounds
    if _sounds is None:
        _sounds = json.loads(object_path('minecraft/sounds.json').read_text())
    return _sounds


def event_files(event, depth=0):
    """The sound files an event can play (`music.game`, `minecraft:entity.goat.step`), following event references."""
    name = event.split(':', 1)[1] if event.startswith('minecraft:') else event
    entry = sounds_json().get(name)
    if not entry or depth > 4:
        return []
    out = []
    for s in entry.get('sounds', []):
        s = {'name': s} if isinstance(s, str) else s
        if s.get('type') == 'event':
            out += event_files(s['name'], depth + 1)
        else:
            out.append(s['name'])
    return out


def decode(file, channels=1):
    """A sound file (`mob/goat/step3`) as 48 kHz float32, mono (channels=1) or (left, right). Cached on disk and in memory."""
    key = (file, channels)
    if key in _decoded:
        return _decoded[key]
    source = object_path(sound_key(file))
    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE / f'{source.name}-{channels}.f32'
    if not cached.exists():
        tmp = cached.with_suffix('.part')
        subprocess.run([tools.ffmpeg(), '-y', '-loglevel', 'error', '-i', str(source), '-ac', str(channels), '-ar', str(dsp.SR),
                        '-f', 'f32le', str(tmp)], check=True)
        tmp.replace(cached)
    _decoded[key] = dsp.read_f32(cached, channels)
    return _decoded[key]


def decode_path(path, channels=1):
    """Any audio file the user gave (a voice line) as 48 kHz float32; cached by path, size and time."""
    path = Path(path)
    st = path.stat()
    key = (str(path.resolve()), st.st_size, int(st.st_mtime), channels)
    if key in _decoded:
        return _decoded[key]
    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE / f'file-{hashlib.sha1(repr(key).encode()).hexdigest()[:16]}.f32'
    if not cached.exists():
        tmp = cached.with_suffix('.part')
        subprocess.run([tools.ffmpeg(), '-y', '-loglevel', 'error', '-i', str(path), '-ac', str(channels), '-ar', str(dsp.SR),
                        '-f', 'f32le', str(tmp)], check=True)
        tmp.replace(cached)
    _decoded[key] = dsp.read_f32(cached, channels)
    return _decoded[key]
