"""Sounds by meaning: turns `tag`, `palette` and `library` on sound cues into concrete event ids when the script
compiles, picks music by mood for the mix, and finds the original stand-in of a sound for original-only exports.

Script side (called by script.compile_script before the cues are checked):

    [[shot.cue]] do = "sound", tag = "pop"                    the best Minecraft event carrying every tag
    [[shot.cue]] do = "sound", palette = "drumroll"           a comedy palette entry: one event, a sequence or a roll
    [[shot.cue]] do = "sound", library = "slide-whistle-up"   an original library sound (videocraft:lib/<name>)
    source = "auto" (Minecraft first, the library when the catalog has nothing) | "minecraft" | "original"
    vary = true                                               a seeded pick among the best three instead of the first

A resolved cue keeps its `tag`/`palette` and gains `id`, a suggested `pitch`/`volume` when it gave none, `original`
(the library sound that replaces it in an original-only export) and, for the extra steps of a sequence or roll,
`part` (1, 2, …): an original-only export plays the palette's original once, on part 0, and drops the rest. The mod
ignores the extra keys. Nothing here reads a game asset: the catalog is committed (catalog/minecraft.toml).
"""
import copy
import random

from videocraft.audio import catalog, library

SOURCES = ('auto', 'minecraft', 'original')
SOUND_ACTIONS = ('sound', 'ambience')


class SoundError(ValueError):
    pass


def has_tags(raw):
    return any(isinstance(c, dict) and c.get('do') in SOUND_ACTIONS and any(k in c for k in ('tag', 'palette', 'library'))
               for s in raw.get('shot', []) or [] for c in s.get('cue', []) or [])


def resolve(raw, source='script'):
    """The script with every tagged sound cue made concrete (a new dict; the input is not changed)."""
    if not has_tags(raw):
        return raw
    from videocraft.script import ScriptError
    raw = copy.deepcopy(raw)
    seed = int(raw.get('seed', 1))
    for shot in raw.get('shot', []):
        name = shot.get('name', '?')
        duration = float(shot.get('duration', 0) or 0)
        out = []
        for i, cue in enumerate(shot.get('cue', []) or []):
            if not (isinstance(cue, dict) and cue.get('do') in SOUND_ACTIONS and any(k in cue for k in ('tag', 'palette', 'library'))):
                out.append(cue)
                continue
            where = f'shot {name}.cue[{i}]'
            try:
                rnd = random.Random(f'{seed}:{name}:{i}')
                cues = resolve_cue(cue, rnd)
            except (SoundError, library.UnknownSound) as e:
                raise ScriptError(f'{source}: {where}: {e}') from e
            out += [c for c in cues if duration <= 0 or float(c.get('at', 0)) <= duration]
        shot['cue'] = out
    return raw


def _pitch(value, rnd):
    if isinstance(value, (list, tuple)):
        return round(rnd.uniform(float(value[0]), float(value[1])), 3)
    return float(value)


def _source(cue):
    s = str(cue.get('source', 'auto')).lower()
    if s not in SOURCES:
        raise SoundError(f'source = "{s}": one of {", ".join(SOURCES)}')
    return s


def resolve_cue(cue, rnd):
    """One tagged cue -> one or more concrete cues."""
    if sum(k in cue for k in ('tag', 'palette', 'library', 'id')) > 1:
        raise SoundError('give one of id, tag, palette or library')
    source = _source(cue)
    base = dict(cue)
    base.pop('source', None)
    base.pop('vary', None)
    if 'library' in cue:
        lib = library.check(str(cue['library']))
        return [{**base, 'id': f'videocraft:lib/{lib}', 'original': lib}]
    if 'palette' in cue:
        return _palette_cues(base, str(cue['palette']), source, rnd, bool(cue.get('vary')))
    tags = catalog.parse_tags(cue['tag'])
    ids = catalog.candidates(tags) if source != 'original' else []
    lib = original_for_tags(tags, ids[0] if ids else None)
    if source == 'minecraft' and not ids:
        raise SoundError(f'tag = "{cue["tag"]}": no Minecraft sound carries {" + ".join(tags)} (videocraft audio find {" ".join(tags)})')
    if not ids:
        if not lib:
            raise SoundError(f'tag = "{cue["tag"]}": neither the Minecraft catalog nor the original library has {" + ".join(tags)} '
                             f'(videocraft audio find {" ".join(tags)})')
        return [{**base, 'id': f'videocraft:lib/{lib}', 'original': lib}]
    pick = rnd.choice(ids[:3]) if cue.get('vary') else ids[0]
    out = {**base, 'id': f'minecraft:{pick}'}
    if lib:
        out['original'] = lib
    return [out]


def original_for_tags(tags, event=None):
    """The library sound for a tag query: the palette's original when the query names a palette entry, else the
    chosen event's own stand-in, else the best library match."""
    pal = catalog.palette().get('-'.join(tags)) or (catalog.palette().get(tags[0]) if len(tags) == 1 else None)
    if pal and pal.get('original'):
        return pal['original']
    if event and catalog.original_of(event):
        return catalog.original_of(event)
    found = library.find(tags)
    return found[0][1] if found and found[0][0] >= 10 * len(tags) else None


def _palette_cues(base, name, source, rnd, vary):
    pal = catalog.palette().get(name)
    if pal is None:
        near = sorted(p for p in catalog.palette() if p[:3] == name[:3])
        raise SoundError(f'palette = "{name}": no such palette entry' + (f'; similar: {", ".join(near)}' if near else '') +
                         f'; known: {", ".join(sorted(catalog.palette()))}')
    original = pal.get('original')
    steps = []
    if source != 'original':
        if pal.get('pick'):
            choice = rnd.choice(pal['pick']) if vary else pal['pick'][0]
            steps = [{'at': 0.0, **choice}]
        steps += [dict(s) for s in pal.get('sequence', [])]
        if pal.get('roll'):
            steps += roll_steps(pal['roll'], rnd)
    if not steps:
        if source == 'minecraft':
            raise SoundError(f'palette = "{name}" has no Minecraft sound (it is original only: {original})')
        return [{**base, 'id': f'videocraft:lib/{original}', 'original': original}]
    steps.sort(key=lambda s: float(s.get('at', 0)))
    t0 = float(base.get('at', 0))
    out = []
    for k, step in enumerate(steps):
        c = {**base, 'id': f'minecraft:{step["id"]}', 'at': round(t0 + float(step.get('at', 0)), 4)}
        if 'pitch' not in base and 'pitch' in step:
            c['pitch'] = _pitch(step['pitch'], rnd)
        if 'volume' in step:
            c['volume'] = round(float(base.get('volume', 1.0)) * float(step['volume']), 4)
        if original:
            c['original'] = original
        if k:
            c['part'] = k
        out.append(c)
    return out


def roll_steps(roll, rnd):
    """A roll's hits: `rate` a second for `seconds`, seeded jitter, swelling when `crescendo`; then its `end` steps,
    timed from the end of the roll."""
    seconds, rate = float(roll.get('seconds', 1.5)), float(roll.get('rate', 20))
    jitter, volume = float(roll.get('jitter', 0.0)), float(roll.get('volume', 1.0))
    steps, t, gap = [], 0.0, 1.0 / max(1.0, rate)
    while t < seconds:
        g = volume * ((0.25 + 0.75 * (t / seconds) ** 1.5) if roll.get('crescendo') else 1.0)
        at = max(0.0, t + (rnd.uniform(-0.5, 0.5) * jitter * gap if jitter else 0.0))
        steps.append({'at': round(at, 4), 'id': roll['id'], 'pitch': _pitch(roll.get('pitch', 1.0), rnd), 'volume': round(g, 3)})
        t += gap
    for e in roll.get('end', []):
        steps.append({**e, 'at': round(seconds + float(e.get('at', 0)), 4)})
    return steps


# ---- the mix side ----

def original_hints(plan):
    """{(shot, event): [(frame, original, part, repeats)]} from the compiled plan's resolved cues, for original-only
    exports; `repeats` (an ambience) covers every later play of the event in the shot."""
    fps = int(plan.get('output', {}).get('fps', 60))
    hints = {}
    for shot in plan.get('shots', []):
        for cue in shot.get('timeline', []):
            if cue.get('do') in SOUND_ACTIONS and cue.get('original') and str(cue.get('id', '')).startswith('minecraft:'):
                hints.setdefault((shot['name'], cue['id']), []).append((int(round(float(cue.get('at', 0)) * fps)), cue['original'],
                                                                        int(cue.get('part', 0)), cue['do'] == 'ambience'))
    return hints


def match_hint(hints, shot, event, frame, tolerance=3):
    """(original, part) of the resolved cue that played `event` on `frame` of `shot`, or None: the cue nearest in
    frames within `tolerance` (the mod plays a cue on the first frame at or after its time), or an ambience that
    started before it."""
    best = None
    for f, original, part, repeats in hints.get((shot, event if ':' in event else f'minecraft:{event}'), ()):
        d = abs(f - frame)
        if repeats and frame >= f - tolerance:
            d = min(d, tolerance)
        if d <= tolerance and (best is None or d < best[0]):
            best = (d, original, part)
    return best[1:] if best else None


def edit_sfx_sound(entry, where):
    """An [[edit.sfx]] entry -> (minecraft event or None, original library name or None, pitch, gain factor)."""
    source = _source(entry)
    given = [k for k in ('id', 'tag', 'palette', 'library') if k in entry]
    if len(given) != 1:
        raise SoundError(f'{where}: give one of id, tag, palette or library')
    pitch = entry.get('pitch')
    volume = 1.0
    if 'library' in entry:
        return None, library.check(str(entry['library'])), float(pitch or 1.0), volume
    if 'id' in entry:
        ev = catalog.bare(str(entry['id']))
        if ev.startswith('videocraft:lib/'):
            return None, library.check(ev.split('/', 1)[1]), float(pitch or 1.0), volume
        return (None if source == 'original' else ev), catalog.original_of(ev), float(pitch or 1.0), volume
    if 'palette' in entry:
        pal = catalog.palette().get(str(entry['palette']))
        if pal is None:
            raise SoundError(f'{where}: palette = "{entry["palette"]}": known: {", ".join(sorted(catalog.palette()))}')
        pick = (pal.get('pick') or [None])[0]
        if pick and source != 'original':
            rnd = random.Random(f'{where}:{entry["palette"]}')
            return pick['id'], pal.get('original'), float(pitch or _pitch(pick.get('pitch', 1.0), rnd)), float(pick.get('volume', 1.0))
        return None, pal.get('original'), float(pitch or 1.0), volume
    tags = catalog.parse_tags(entry['tag'])
    ids = catalog.candidates(tags) if source != 'original' else []
    lib = original_for_tags(tags, ids[0] if ids else None)
    if not ids and not lib:
        raise SoundError(f'{where}: tag = "{entry["tag"]}": nothing carries {" + ".join(tags)}')
    return (ids[0] if ids else None), lib, float(pitch or 1.0), volume


def pick_track(mood, seconds=None, bpm=None, seed=1, exclude=(), vocals=False, rank=0):
    """The game track for a mood: (file, row, why) or None when the map has none.

    Score: the track's main mood (3) or second mood (2); a steady pulse for upbeat and playful (+1); nearness to `bpm`
    when given (up to +2); long enough from its entry for `seconds` (+1) or loopable (+0.5). Tracks marked not a bed,
    and ones with vocals unless `vocals`, are left out. The best few (within a point) are shuffled by `seed`, so
    different videos of one mood do not all get the same track; `rank` takes the next one down."""
    rows = []
    for f, row in catalog.tracks().items():
        if f in exclude or row.get('bed') is False or (row.get('vocals') and not vocals):
            continue
        moods = row.get('mood', [])
        if mood not in moods:
            continue
        score = 3.0 if moods[0] == mood else 2.0
        why = [f'{mood} ({"main" if moods[0] == mood else "second"} mood)']
        if mood in ('upbeat', 'playful', 'triumphant') and row.get('pulse', 0) >= 0.3:
            score += 1
            why.append('steady pulse')
        if bpm and row.get('bpm'):
            near = min(abs(row['bpm'] - bpm), abs(row['bpm'] * 2 - bpm), abs(row['bpm'] / 2 - bpm))
            score += max(0.0, 2.0 - near / 10)
            why.append(f'{row["bpm"]:g} bpm')
        if seconds:
            if row.get('seconds', 0) - row.get('entry', 0) >= seconds:
                score += 1
            elif row.get('loops'):
                score += 0.5
                why.append('loops to fit')
        rows.append((score, f, row, why))
    if not rows:
        return None
    rows.sort(key=lambda r: (-r[0], r[1]))
    top = [r for r in rows if r[0] >= rows[0][0] - 1.0]
    rnd = random.Random(f'music:{seed}:{mood}')
    rnd.shuffle(top)
    ordered = top + [r for r in rows if r not in top]
    score, f, row, why = ordered[min(rank, len(ordered) - 1)]
    return f, row, ', '.join(why)
