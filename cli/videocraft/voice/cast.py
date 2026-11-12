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
    pace = 3.2                         # words a second the lines aim at (default 3.2; 0 = no pacing); pace.py
    bark = "minecraft:entity.goat.ambient"  # optional: the game sound played on the line's first word
    draft = { engine = "kokoro", voice = "am_fenrir", speed = 1.1 }   # VIDEOCRAFT_VOICE=draft: fast takes

    [styles]                           # optional: delivery words -> instruction (adds to / replaces STYLES)
    shout = "Shouting, loud and urgent."

Every line is paced (pace.py): silence trimmed, pauses capped, a slow line stretched towards `pace`; a qwen3 line
also gets the project's default delivery (DELIVERY: brisk) unless its style is a slow one (pace.SLOW_STYLES).

A character the cast does not name is looked up in every committed cast file, then given a generic voice (with a
warning), so a generated script always compiles.

Different people have different voices (the owner, on the first films): lint() is an error when two speaking
characters share engine, preset and instruction (the same voice), and a warning when they share a preset (an
instruction alone does not make a second person), when one is speaking in a generic voice, when two have one
display name, or when their draft voices collide; each names a free preset of the same kind, by measured pitch.
"""
import math
import tomllib
import zlib
from dataclasses import dataclass, field
from pathlib import Path

from videocraft.paths import ROOT
from videocraft.voice import pace as pace_mod

CAST_DIR = ROOT / 'cast'
ENGINES = ('qwen3', 'kokoro')
CHARACTER_KEYS = {'id', 'name', 'color', 'engine', 'voice', 'instruct', 'seed', 'speed', 'pitch', 'lufs', 'bark',
                  'bark_volume', 'draft', 'model', 'description', 'pace'}
# The project-wide delivery: every qwen3 line is asked to be brisk (the first films' lines ran 1.2-3.5 words a
# second with dead air, and the owner found them "super slow"). Not added for the slow styles.
DELIVERY = 'Brisk and snappy: a quick conversational pace, words tumbling out, no long pauses.'
# Delivery (a say cue's `style`): for qwen3, a sentence added to the character's instruction; for kokoro (no style
# control), a speed factor. A style that is not listed is used as the instruction sentence itself.
STYLES = {
    'shout': ('Shouting at the top of the lungs, loud and urgent.', 1.06),
    'whisper': ('Whispering, hushed and breathy, as if sharing a secret.', 0.92),
    'deadpan': ('Flat and deadpan, completely unimpressed, no emotion at all.', 0.95),
    'excited': ('Thrilled and fast, the voice rising with excitement.', 1.1),
    'proud': ('Proud and grand, announcing it to the world.', 0.97),
    'smug': ('Smug and pleased with itself, a sly grin in the voice.', 1.0),
    'sad': ('Sad and deflated, quiet and slow.', 0.88),
    'angry': ('Angry, clipped and hard.', 1.04),
    'scared': ('Scared, shaky and breathless.', 1.08),
    'sleepy': ('Sleepy and drowsy, yawning through the words, very slow.', 0.82),
    'question': ('Puzzled, asking, the pitch rising at the end.', 1.0),
    'sing': ('Sing-song and playful, almost singing.', 0.95),
}
GENERIC = [('qwen3', 'ryan'), ('qwen3', 'aiden')]
COLORS = ['#ffd166', '#a0e8ff', '#ff9ec7', '#b8f2a0', '#d7b8ff']


# Every preset, by engine: (kind, median f0 in Hz) on one neutral line ("Well, I told you the bridge would hold...",
# seed 7, no pacing; qwen3 with the instruction "Natural, conversational."), measured by autocorrelation on
# 2026-11-12 (docs/VOICE.md). Nobody listened. A suggestion for another voice is an unused preset of the same kind
# as far in pitch from the clashing one as there is. Note ryan 130 and aiden 128: alike unless instructions part them.
PRESETS = {
    'qwen3': {'ryan': ('male', 130.4), 'aiden': ('male', 127.7), 'eric': ('male', 173.9),
              'dylan': ('male', 144.6), 'uncle_fu': ('male', 226.4), 'serena': ('female', 230.8),
              'vivian': ('female', 237.6), 'ono_anna': ('female', 260.9), 'sohee': ('female', 240.0)},
    'kokoro': {'am_adam': ('male', 121.2), 'am_echo': ('male', 113.2), 'am_eric': ('male', 148.1),
               'am_fenrir': ('male', 122.4), 'am_liam': ('male', 117.6), 'am_michael': ('male', 115.4),
               'am_onyx': ('male', 88.2), 'am_puck': ('male', 108.6), 'am_santa': ('male', 162.2),
               'bm_daniel': ('male', 129.0), 'bm_fable': ('male', 146.3), 'bm_george': ('male', 142.9),
               'bm_lewis': ('male', 99.2), 'af_alloy': ('female', 139.5), 'af_aoede': ('female', 169.0),
               'af_bella': ('female', 200.0), 'af_heart': ('female', 193.5), 'af_jessica': ('female', 206.9),
               'af_kore': ('female', 134.8), 'af_nicole': ('female', 148.1), 'af_nova': ('female', 160.0),
               'af_river': ('female', 176.5), 'af_sarah': ('female', 181.8), 'af_sky': ('female', 153.8),
               'bf_alice': ('female', 222.2), 'bf_emma': ('female', 179.1), 'bf_isabella': ('female', 193.5),
               'bf_lily': ('female', 169.0)},
}


def kind_of(engine, voice):
    """'male' | 'female' | None for a preset."""
    row = PRESETS.get(engine, {}).get(voice)
    if row:
        return row[0]
    if engine == 'kokoro' and len(voice) > 2 and voice[1] in 'mf':
        return 'male' if voice[1] == 'm' else 'female'
    return None


APART = 3.0         # semitones (a minor third): two characters' measured voices closer than this sound alike


def semitones(a, b):
    return abs(12 * math.log2(a / b)) if a and b else None


ENGLISH = {'qwen3': ('ryan', 'aiden')}    # the English-native presets (kokoro: all of a* and b*); the others are
                                           # Chinese, Japanese or Korean voices and read English with an accent


def _english(engine, voice):
    return voice in ENGLISH[engine] if engine in ENGLISH else voice[:1] in 'ab'


def suggest(engine, voice, used):
    """Another voice for a character that sounds like `voice`: an unused English preset of the same kind, the most
    distinct in measured pitch from `voice` and every voice already `used` ((engine, preset) pairs; counting at most 6
    semitones), as the TOML to write: 'voice = "x"', or 'engine = "kokoro", voice = "x"' when the engine has none
    left; None if there is none."""
    kind = kind_of(engine, voice)
    taken = [PRESETS[e][v][1] for e, v in set(used) | {(engine, voice)} if v in PRESETS.get(e, {})]
    for eng in dict.fromkeys((engine, 'kokoro')):
        presets = PRESETS.get(eng, {})
        free = [(v, row) for v, row in presets.items() if (eng, v) not in used and v != voice and _english(eng, v)
                and (kind is None or row[0] == kind)]
        if not free:
            continue
        if taken:
            v = max(free, key=lambda x: (min(min(semitones(x[1][1], f) for f in taken), 6.0), -abs(semitones(x[1][1], taken[0]) - 5)))[0]
        else:
            v = free[0][0]
        return f'voice = "{v}"' if eng == engine else f'engine = "{eng}", voice = "{v}"'
    return None


def lint(cast, speakers, draft=True, pitches=None):
    """Problems ({severity, rule, where, message}) with the voices of the speaking characters `speakers` (ids in
    order): see the module's docstring. `pitches` {id: median f0 of its synthesized lines} adds "sound alike"
    warnings for characters less than APART semitones apart (voice/pitch.py measures them)."""
    out = []

    def add(severity, who, message):
        out.append({'severity': severity, 'rule': 'cast_voice', 'where': f'cast {who}', 'message': message})

    chars = [cast.character(c) for c in dict.fromkeys(list(cast.characters) + list(speakers))]
    used = {(c.engine, c.voice) for c in chars}
    for c in chars:
        if c.generic:
            add('warn', c.id, f'"{c.id}" is in no cast and speaks in a generic {c.engine} {c.voice} voice: give it its own '
                              f'voice in [cast] ({suggest(c.engine, c.voice, used) or "see docs/VOICE.md"})')
    for i, a in enumerate(chars):
        for b in chars[i + 1:]:
            if (a.engine, a.voice) != (b.engine, b.voice):
                continue
            other = suggest(b.engine, b.voice, used)
            hint = f'; give {b.id} another preset, e.g. {other}' if other else ''
            if (a.instruct or '').strip().lower() == (b.instruct or '').strip().lower():
                add('error', b.id, f'{a.id} and {b.id} speak with the same voice ({a.engine} {a.voice}, the same instruction): '
                                   f'every speaking character needs its own{hint}')
            else:
                add('warn', b.id, f'{a.id} and {b.id} share the {a.engine} preset {a.voice}: an instruction alone does not '
                                  f'make a second person{hint}')
    measured = {k: v for k, v in (pitches or {}).items() if v}
    for i, a in enumerate(chars):
        for b in chars[i + 1:]:
            d = semitones(measured.get(a.id), measured.get(b.id))
            if d is None or d >= APART or (a.engine, a.voice) == (b.engine, b.voice):
                continue
            other = suggest(b.engine, b.voice, used)
            how = (f'pull the instructions apart (one bright and high, one low and gruff), set pitch = '
                   f'{"-2" if measured[b.id] <= measured[a.id] else "2"} on {b.id}, or give it another voice'
                   if b.engine == 'qwen3' else f'give {b.id} another voice')
            add('warn', b.id, f'{a.id} ({a.engine} {a.voice}, {measured[a.id]:.0f} Hz) and {b.id} ({b.engine} {b.voice}, '
                              f'{measured[b.id]:.0f} Hz) sound alike: their lines measure {d:.2f} semitones apart (under '
                              f'{APART:g}); {how}' + (f', e.g. {other}' if other else ''))
    names = {}
    for c in chars:
        names.setdefault(c.name.strip().lower(), []).append(c.id)
    for name, ids in names.items():
        if len(ids) > 1:
            add('warn', ids[1], f'{", ".join(ids)} are all called "{cast.character(ids[0]).name}" on screen: one name for two '
                                'people reads as one person with two voices; give each its own name')
    if draft:
        seen = {}
        for c in chars:
            d = {**{'engine': c.engine, 'voice': c.voice}, **(c.draft or {})}
            key = (d.get('engine'), d.get('voice'))
            if key in seen and (c.engine, c.voice) != (seen[key].engine, seen[key].voice):
                add('warn', c.id, f'in draft takes (VIDEOCRAFT_VOICE=draft) {seen[key].id} and {c.id} both speak as '
                                  f'{key[0]} {key[1]}: give one another draft voice')
            seen.setdefault(key, c)
    return out


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
    pace: float = pace_mod.PACE
    bark: str | None = None
    bark_volume: float = 1.0
    model: str | None = None
    draft: dict = field(default_factory=dict)
    generic: bool = False

    def spec(self, tokens, style=None, speed=1.0, styles=None, draft=False, pace=None, beat=False):
        """The worker job for a line (without `out`): everything that shapes its audio, so also its cache key; plus
        `pace` (not part of the key): how front.paced tightens it. `pace` is the cue's words a second (None: the
        character's; 0 or False: no pacing and no brisk delivery); `beat` keeps the line's own pauses."""
        base = {'engine': self.engine, 'voice': self.voice, 'instruct': self.instruct, 'speed': self.speed,
                'pitch': self.pitch, 'model': self.model}
        if draft and self.draft:
            base = {**base, 'instruct': '', 'model': None, **self.draft}
        instruct, factor = base['instruct'] or '', 1.0
        wps = self.pace if pace is None else (0.0 if pace is False else float(pace))
        slow = style in pace_mod.SLOW_STYLES
        if wps > 0 and not slow and base['engine'] == 'qwen3':
            instruct = f'{instruct} {DELIVERY}'.strip()
        if style:
            sentence, factor = (styles or STYLES).get(style, STYLES.get(style, (style, 1.0)))
            instruct = f'{instruct} {sentence}'.strip()
        s = float(base['speed'] or 1.0) * float(speed or 1.0)
        if base['engine'] == 'kokoro':
            s *= factor   # kokoro has no style control: delivery is only a pace
            instruct = ''
        return {'engine': base['engine'], 'voice': base['voice'], 'instruct': instruct or None, 'seed': int(self.seed),
                'speed': round(s, 4), 'pitch': float(base.get('pitch') or 0.0), 'lufs': float(self.lufs),
                'model': base.get('model'), 'tokens': list(tokens), 'retries': 2,
                'pace': {'wps': wps, 'caps': style != 'deadpan' and not beat, 'stretch': not slow} if wps > 0 else None}


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
                     pace=float(table.get('pace', pace_mod.PACE) or 0.0),
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
