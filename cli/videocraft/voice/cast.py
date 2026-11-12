"""The cast: who speaks with which voice. A cast file (cast/<name>.toml) or an inline `[cast]` in the script.

    [[character]]                      # in a cast file; inline it is [[cast.character]]
    id = "nibs"                        # the say cue's actor (or its `character`)
    name = "Nibs"                      # the caption's speaker tag (default: the id, capitalised)
    color = "#ffd166"                  # the tag's colour
    engine = "qwen3"                   # qwen3 (Qwen3-TTS 1.7B CustomVoice) or kokoro (Kokoro-82M)
    voice = "ryan"                     # the engine's preset
    instruct = "Cocky, brash and bright…"   # qwen3: how the character talks (style instruction)
    seed = 7                           # fixed: the same line is the same take
    speed = 1.0                        # kokoro: its own rate; qwen3: a time stretch (keep 0.9-1.1)
    pitch = 0                          # semitones, post-process (moves formants; keep within +-2)
    lufs = -20                         # each line's loudness before the mix
    bark = "minecraft:entity.goat.ambient"  # optional: the game sound played on the line's first word
    draft = { engine = "kokoro", voice = "am_fenrir", speed = 1.1 }   # VIDEOCRAFT_VOICE=draft: fast takes

    [styles]                           # optional: delivery words -> instruction (adds to / replaces STYLES)
    shout = "Shouting, loud and urgent."

A character the cast does not name is looked up in every committed cast file, then given a generic voice (with a
warning), so a generated script always compiles.
"""
import tomllib
import zlib
from dataclasses import dataclass, field
from pathlib import Path

from videocraft.paths import ROOT

CAST_DIR = ROOT / 'cast'
ENGINES = ('qwen3', 'kokoro')
CHARACTER_KEYS = {'id', 'name', 'color', 'engine', 'voice', 'instruct', 'seed', 'speed', 'pitch', 'lufs', 'bark',
                  'bark_volume', 'draft', 'model', 'description'}
# Delivery (a say cue's `style`): for qwen3, a sentence added to the character's instruction; for kokoro (no style
# control), a speed factor. A style that is not listed is used as the instruction sentence itself.
STYLES = {
    'shout': ('Shouting at the top of the lungs, loud and urgent.', 1.06),
    'whisper': ('Whispering, hushed and breathy, as if sharing a secret.', 0.92),
    'deadpan': ('Flat and deadpan, completely unimpressed, no emotion at all.', 0.95),
    'excited': ('Thrilled and fast, the voice rising with excitement.', 1.1),
    'proud': ('Proud and grand, announcing it to the world.', 0.97),
    'smug': ('Smug and pleased with itself, savouring every word.', 0.92),
    'sad': ('Sad and deflated, quiet and slow.', 0.88),
    'angry': ('Angry, clipped and hard.', 1.04),
    'scared': ('Scared, shaky and breathless.', 1.08),
    'sleepy': ('Sleepy and drowsy, yawning through the words, very slow.', 0.82),
    'question': ('Puzzled, asking, the pitch rising at the end.', 1.0),
    'sing': ('Sing-song and playful, almost singing.', 0.95),
}
GENERIC = [('qwen3', 'ryan'), ('qwen3', 'aiden')]
COLORS = ['#ffd166', '#a0e8ff', '#ff9ec7', '#b8f2a0', '#d7b8ff']


class CastError(ValueError):
    pass


@dataclass
class Character:
    id: str
    name: str
    color: str
    engine: str = 'qwen3'
    voice: str = 'ryan'
    instruct: str = ''
    seed: int = 7
    speed: float = 1.0
    pitch: float = 0.0
    lufs: float = -20.0
    bark: str | None = None
    bark_volume: float = 1.0
    model: str | None = None
    draft: dict = field(default_factory=dict)
    generic: bool = False

    def spec(self, tokens, style=None, speed=1.0, styles=None, draft=False):
        """The worker job for a line (without `out`): everything that shapes its audio, so also its cache key."""
        base = {'engine': self.engine, 'voice': self.voice, 'instruct': self.instruct, 'speed': self.speed,
                'pitch': self.pitch, 'model': self.model}
        if draft and self.draft:
            base = {**base, 'instruct': '', 'model': None, **self.draft}
        instruct, factor = base['instruct'] or '', 1.0
        if style:
            sentence, factor = (styles or STYLES).get(style, STYLES.get(style, (style, 1.0)))
            instruct = f'{instruct} {sentence}'.strip()
        s = float(base['speed'] or 1.0) * float(speed or 1.0)
        if base['engine'] == 'kokoro':
            s *= factor   # kokoro has no style control: delivery is only a pace
            instruct = ''
        return {'engine': base['engine'], 'voice': base['voice'], 'instruct': instruct or None, 'seed': int(self.seed),
                'speed': round(s, 4), 'pitch': float(base.get('pitch') or 0.0), 'lufs': float(self.lufs),
                'model': base.get('model'), 'tokens': list(tokens), 'retries': 2}


def _character(table, where):
    if not isinstance(table, dict) or not isinstance(table.get('id'), str):
        raise CastError(f'{where}: a character is a table with id = "<actor id>"')
    extra = sorted(set(table) - CHARACTER_KEYS)
    if extra:
        raise CastError(f'{where}: unknown key(s) {", ".join(extra)}; allowed: {", ".join(sorted(CHARACTER_KEYS))}')
    engine = table.get('engine', 'qwen3')
    if engine not in ENGINES:
        raise CastError(f'{where}: engine is one of {", ".join(ENGINES)} (got {engine!r})')
    cid = table['id']
    return Character(id=cid, name=table.get('name') or cid.replace('-', ' ').title(),
                     color=table.get('color') or COLORS[zlib.crc32(cid.encode()) % len(COLORS)], engine=engine,
                     voice=table.get('voice') or ('am_michael' if engine == 'kokoro' else 'ryan'),
                     instruct=table.get('instruct', ''), seed=int(table.get('seed', 7)), speed=float(table.get('speed', 1.0)),
                     pitch=float(table.get('pitch', 0.0)), lufs=float(table.get('lufs', -20.0)), bark=table.get('bark'),
                     bark_volume=float(table.get('bark_volume', 1.0)), model=table.get('model'), draft=dict(table.get('draft') or {}))


def read_file(path):
    path = Path(path)
    try:
        data = tomllib.loads(path.read_text(encoding='utf-8'))
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise CastError(f'cast file {path}: {e}') from e
    chars = {}
    for i, c in enumerate(data.get('character', [])):
        ch = _character(c, f'{path.name} character[{i}]')
        chars[ch.id] = ch
    styles = {k: (v, 1.0) if isinstance(v, str) else (v.get('instruct', k), float(v.get('speed', 1.0)))
              for k, v in (data.get('styles') or {}).items()}
    return chars, styles


class Cast:
    def __init__(self, characters=None, styles=None, actors=None, log=None):
        self.characters = dict(characters or {})
        self.styles = {**STYLES, **(styles or {})}
        self.actors = actors or {}
        self.log = log or (lambda s: None)
        self._library = None

    def _from_library(self, cid):
        if self._library is None:
            self._library = {}
            for f in sorted(CAST_DIR.glob('*.toml')) if CAST_DIR.is_dir() else []:
                try:
                    chars, _ = read_file(f)
                except CastError:
                    continue
                for k, v in chars.items():
                    self._library.setdefault(k, v)
        return self._library.get(cid)

    def character(self, cid):
        if cid in self.characters:
            return self.characters[cid]
        ch = self._from_library(cid)
        if ch is None:
            engine, voice = GENERIC[zlib.crc32(cid.encode()) % len(GENERIC)]
            actor = self.actors.get(cid) or {}
            ch = Character(id=cid, name=actor.get('name') or cid.replace('-', ' ').title(),
                           color=COLORS[zlib.crc32(cid.encode()) % len(COLORS)], engine=engine, voice=voice, generic=True)
            self.log(f'voice: WARNING "{cid}" is in no cast; a generic {engine} {voice} voice speaks it (add it to [cast])')
        self.characters[cid] = ch
        return ch


def load(raw_cast, source=None, actors=None, log=None):
    """The script's [cast]: `file = "cast/x.toml"` (relative to the script, else to the repository) and/or inline
    [[cast.character]] tables (which win over the file's)."""
    raw_cast = raw_cast or {}
    if not isinstance(raw_cast, dict):
        raise CastError('cast: a table: [cast] file = "cast/<name>.toml", and/or [[cast.character]] id = "...", ...')
    extra = sorted(set(raw_cast) - {'file', 'character', 'styles'})
    if extra:
        raise CastError(f'cast: unknown key(s) {", ".join(extra)}; allowed: character, file, styles')
    chars, styles = {}, {}
    if raw_cast.get('file'):
        f = Path(raw_cast['file'])
        candidates = [f] if f.is_absolute() else [p / f for p in ([Path(source).parent] if source else []) + [ROOT]]
        path = next((p for p in candidates if p.exists()), None)
        if path is None:
            raise CastError(f'cast.file: no cast file {raw_cast["file"]} (looked in {", ".join(str(c.parent) for c in candidates)})')
        chars, styles = read_file(path)
    for i, c in enumerate(raw_cast.get('character', [])):
        ch = _character(c, f'cast.character[{i}]')
        chars[ch.id] = ch
    for k, v in (raw_cast.get('styles') or {}).items():
        styles[k] = (v, 1.0) if isinstance(v, str) else (v.get('instruct', k), float(v.get('speed', 1.0)))
    return Cast(chars, styles, actors, log)
