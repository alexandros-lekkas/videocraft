"""The sound track of a cut: game sound effects on their frames, voice, music, ducking, mastering.

    build(it, original=None) -> Path of cut/audio.wav (48 kHz stereo 16-bit, mastered) or None (no audio wanted)

Called by the picture edit (cli/videocraft/edit) after it has written cut/timeline.json and before it muxes; also by
`videocraft audio mix`. Reads, per shot, take/shots/<name>/sounds.csv (what the client played, on which frame) and
frames.csv (the camera of each frame), and edit.json:

    [edit] audio = "game" | "original" | "none"      original: no byte of game audio (synth bed, stand-ins, voice)
    [edit.music] source = "auto" (mood: a game track by mood when there are assets and game audio, else the synth bed
                 in that mood) | "synth" (style or mood, bpm, key, seed) | "game" (track, start); gain (dB), at,
                 fade_in, fade_out, through_black, duck (the least dB the bed ducks under a line; default -6)
    [[edit.sfx]] shot + at (or time), id | tag | palette | library, source, gain (dB), pan, pitch: a sound placed by
                 the edit itself (a sting on a cut), Minecraft first, the original library in original-only exports
    [[edit.music.cue]] shot, at (or time = seconds in the cut), do = out | in | drop | thin | full | hit, fade, length, gain
    [edit.mix] sfx (dB), voice (dB), duck = ["entity.goat.screaming.*", "tag:scream", …] (sound effects the bed ducks
               under; `tag:<tags>` matches events the catalog tags so), lift = {pattern = dB}; the balance:
               voice_level (-16 LUFS), music_level (-24 LUFS between lines), music_under_voice (-18 LU), game_trim
               (-2 dB on a game track), sfx_ceiling (-3 LU re the voice), sfx_under_line (-6 LU re the line)
    edit.voice = [{ file, shot, at, gain }]           written by the dialogue resolver; `at` in seconds of the shot

Every logged sound is placed at the output time of its frame through the timeline (trims, speed, black gaps), played at
its pitch as playback rate, attenuated by distance from that frame's camera (the game's linear model: 1 - d / range)
and panned by its bearing from the camera's yaw. A sound that started before a cut-in is skipped unless it is long or
looping (then it joins part-way through); every sound stops at the end of its clip. Music categories the game itself
started are ignored.

The balance (dialogue is king), set in LUFS by measuring each bus (balance.py): the voice bus to voice_level; the
effects held under the voice (sfx_ceiling everywhere, sfx_under_line under a line); the bed so that after the
master's gain it plays at music_level between lines; then the bed ducks under each line as deep as that line needs
for the bed's loudest moment under it to sit music_under_voice below the line's voice (never less than `duck`),
down 50 ms before the first word (60 ms linear attack), held 0.25 s through gaps, released over 0.4 s. Then the
master: -14 LUFS integrated, true peak at most -2 dBTP (loudness.py). cut/audio.json lists every placed event
(source, output time, frame, gain, pan), every skipped one with the reason, and `balance`: voice over music per line,
the music between lines, the effects' loudest (measure, lint and the review read it).
"""
import csv
import fnmatch
import json
import math
import os
import subprocess
import time
from array import array
from dataclasses import dataclass, asdict
from itertools import repeat
from pathlib import Path

from videocraft.audio import assets, balance, catalog, dsp, library, loudness, resolve, sfx, synth
from videocraft.audio import timeline as tl
from videocraft import tools
from videocraft.paths import ROOT

SR = dsp.SR
BLOCK = 480  # 10 ms: the resolution of ducking and level curves
MUSIC_REF_DB = -22.0  # bed RMS before `gain` (a first levelling; build() then sets it in LUFS); lines: VOICE_REF_DB
VOICE_REF_DB = -17.0
# The balance (dialogue is king; the owner found the films' music too loud). Levels in LUFS of the master, where the
# voice is about VOICE_LUFS short-term: the bed between lines at MUSIC_LEVEL, under a line MUSIC_UNDER_VOICE LU below
# it (the duck goes as deep as each line needs, at least DUCK); a game track gets GAME_TRIM on top (they are mastered
# hot: dense and bright where speech lives). [edit.mix] voice_level, music_level, music_under_voice, game_trim override.
VOICE_LUFS = -16.0
MUSIC_LEVEL = -24.0
MUSIC_UNDER_VOICE = -18.0
GAME_TRIM = -2.0
DUCK = -6.0           # dB: the least the bed goes down under a line ([edit.music] duck); deeper wherever it must
SFX_CEILING = -3.0    # LU re the voice level: effects never louder than this (momentary), [edit.mix] sfx_ceiling
SFX_UNDER_LINE = -6.0 # LU re the line's voice: effects under a line, [edit.mix] sfx_under_line
DUCK_FLOOR = -40.0    # dB: the most
MARGIN = 1.0          # LU kept spare under the target
ATTACK, LOOKAHEAD, RELEASE, HOLD = 0.06, 0.05, 0.4, 0.25   # seconds: the duck's shape (duck_curve)
HIT_DB = 4.0          # a music `hit` (crash + kick) sits this far over the bed's RMS
FADE_STOP = int(0.004 * SR)  # a sound cut at its clip's end fades over 4 ms instead of clicking


@dataclass
class Placed:
    source: str            # game | synth | stand-in | voice
    event: str
    file: str
    shot: str
    frame: int
    clip: int
    time: float            # seconds in the cut
    offset: float = 0.0    # seconds into the sound (joined part-way through)
    gain: float = 1.0
    pan: float = 0.0
    rate: float = 1.0
    stop: float = 0.0      # seconds in the cut where it is cut off
    looping: bool = False
    duck: bool = False
    stand_in: str = ''     # the original library sound playing instead of a game event (original-only mode)

    def to_json(self):
        d = asdict(self)
        d['time'] = round(self.time, 5)
        d['gain_db'] = round(dsp.db(self.gain), 2)
        del d['gain']
        for k in ('offset', 'pan', 'rate', 'stop'):
            d[k] = round(d[k], 4)
        return d


def _mode(edit, original):
    """game | original | none. `original=True` (or VIDEOCRAFT_AUDIO=original: the whole cut with no game audio) wins."""
    if original or os.environ.get('VIDEOCRAFT_AUDIO', '').strip().lower() == 'original':
        return 'original'
    mode = edit.get('audio', 'game')
    if mode in (False, None) or str(mode).lower() in ('none', 'silent', 'off'):
        return 'none'
    if mode not in ('game', 'original'):
        raise SystemExit(f'[edit] audio = "{mode}": one of game, original, none')
    return mode


def read_sounds(shot_dir):
    f = Path(shot_dir) / 'sounds.csv'
    if not f.exists():
        return []
    rows = []
    with f.open(newline='') as fh:
        for r in csv.DictReader(fh):
            rows.append({'frame': int(r['frame']), 'event': r['event'], 'file': r['file'], 'category': r['category'],
                         'volume': float(r['volume']), 'pitch': float(r['pitch']), 'x': float(r['x']), 'y': float(r['y']),
                         'z': float(r['z']), 'relative': r['relative'] == '1', 'range': float(r.get('attenuation_distance') or 16),
                         'looping': r.get('looping') == '1'})
    return rows


def read_cameras(shot_dir):
    f = Path(shot_dir) / 'frames.csv'
    cams = []
    if f.exists():
        with f.open(newline='') as fh:
            for r in csv.DictReader(fh):
                cams.append((float(r['cam_x']), float(r['cam_y']), float(r['cam_z']), float(r['cam_yaw'])))
    return cams


def spatial(cam, pos, rng, relative):
    """(gain, pan) of a sound at `pos` heard from camera (x, y, z, yaw): linear distance attenuation, bearing pan."""
    if relative or cam is None:
        return 1.0, 0.0
    cx, cy, cz, yaw = cam
    dx, dy, dz = pos[0] - cx, pos[1] - cy, pos[2] - cz
    d = math.sqrt(dx * dx + dy * dy + dz * dz)
    gain = max(0.0, 1.0 - d / max(rng, 1e-6))
    h = math.hypot(dx, dz)
    if h < 0.5:
        return gain, 0.0
    r = math.radians(yaw)
    right = (-math.cos(r), -math.sin(r))  # Minecraft: yaw 0 looks south (+z), so west (-x) is to the right
    pan = (dx * right[0] + dz * right[1]) / h
    return gain, 0.8 * pan


class Sounds:
    """Sound buffers for placed events: game files (decoded assets) or synthesized ones. In original mode a game file
    is never asked for: the test suite checks that by replacing assets.decode with a function that fails.

    Original mode swaps each game sound for an original one: note-block notes for tones at the logged pitch (sfx.py);
    a sound a tagged cue played for its palette's or tag's library sound (`hints` from the plan: once per palette,
    the extra steps of a sequence or roll are dropped); any other event for its catalog stand-in
    (catalog/minecraft.toml `original`), else the old generic stand-ins; else it is left out."""

    def __init__(self, mode, hints=None):
        self.mode = mode
        self.hints = hints or {}
        self.rate_cache = {}

    def stand_in(self, row):
        """(library name or '', reason): the original sound for a game event in original mode."""
        event = row['event']
        name = event.split(':', 1)[-1]
        hint = resolve.match_hint(self.hints, row.get('shot'), event, row.get('frame', 0)) if 'shot' in row else None
        if hint:
            original, part = hint
            return (original, 'hint') if part == 0 else ('', 'a later step of a palette sequence (its original plays once)')
        if name.startswith('block.note_block.'):
            return '', ''
        lib = catalog.original_of(event)
        return (lib, 'catalog') if lib else ('', '')

    def buffer(self, row):
        """(source, mono buffer at rate 1) or (None, reason)."""
        event = row['event']
        if event.startswith('videocraft:lib/'):
            name = event.split('/', 1)[1]
            try:
                return 'synth', library.render(name)
            except library.UnknownSound:
                return None, f'no original library sound {name}'
        if event.startswith('videocraft:'):
            buf = sfx.synth_event(event.split(':', 1)[1])
            return ('synth', buf) if buf is not None else (None, 'unknown synthesized event')
        if self.mode == 'original':
            lib = row.get('stand_in')
            if lib is None:
                lib, why = self.stand_in(row)
                if not lib and why:
                    return None, why
            if lib:
                return 'stand-in', library.render(lib)
            buf = sfx.stand_in(event)
            return ('stand-in', buf) if buf is not None else (None, 'no original stand-in')
        if not row['file']:
            return None, 'no file logged'
        return 'game', assets.decode(row['file'], 1)

    def at_rate(self, key, buf, rate):
        k = (key, round(rate, 4))
        if k not in self.rate_cache:
            self.rate_cache[k] = dsp.resample(buf, rate)
        return self.rate_cache[k]


# Foley lift by event pattern (dB): footsteps are logged at the game's own volume (0.15 for most mobs), which puts
# them some 30 dB under everything else; a video lifts them so a step reads. `[edit.mix] lift` adds or overrides.
LIFT = {'*.step': 9.0}


def matches(name, event, pattern):
    """An event id against a `[edit.mix]` pattern: a glob on the id, or `tag:<tags>` (the catalog's tags)."""
    if pattern.startswith('tag:'):
        row = catalog.event(name)
        return bool(row) and all(t in row.get('tags', ()) for t in catalog.parse_tags(pattern[4:]))
    return fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(event, pattern)


def place_sfx(it, timeline, sounds, duck_patterns=(), lift=None):
    placed, skipped = [], []
    lifts = [(pat, dsp.from_db(float(db))) for pat, db in {**LIFT, **(lift or {})}.items()]
    shots = {c.shot for c in timeline.clips if c.kind == 'shot'}
    fps = timeline.fps
    for shot in sorted(shots):
        shot_dir = it.take / 'shots' / shot
        rows = read_sounds(shot_dir)
        cams = read_cameras(shot_dir)
        clips = timeline.shot_clips(shot)
        for row in rows:
            f = row['frame']
            base = {'shot': shot, 'frame': f, 'event': row['event'], 'file': row['file']}
            if row['category'] == 'music':
                skipped.append({**base, 'reason': 'music the game started'})
                continue
            row = {**row, 'shot': shot}
            stand_in, why = sounds.stand_in(row) if sounds.mode == 'original' and not row['event'].startswith('videocraft:') else ('', '')
            row['stand_in'] = stand_in if stand_in or not why else None
            source, buf = sounds.buffer(row)
            if source is None:
                skipped.append({**base, 'reason': buf})
                continue
            rate = max(0.5, min(2.0, row['pitch'] or 1.0))
            if stand_in:
                # A library sound is made at its own pitch: a tagged cue's suggested pitch was for the game sound.
                rate = 1.0 if why == 'hint' else max(0.85, min(1.2, rate))
            length = math.inf if row['looping'] else len(buf) / SR / rate
            shown = False
            for c in clips:
                if c.contains(f):
                    t, offset = c.out_frame(f) / fps, 0.0
                elif f < c.src_in:
                    lead = (c.src_in - f) / fps
                    if not (row['looping'] or (length >= 1.0 and length - lead >= 0.25)):
                        continue
                    t, offset = c.out_start / fps, lead
                else:
                    continue
                shown = True
                cam = cams[max(0, min(len(cams) - 1, f))] if cams else None
                gain, pan = spatial(cam, (row['x'], row['y'], row['z']), row['range'], row['relative'])
                gain *= max(0.0, min(1.0, row['volume']))
                if gain < 1e-4:
                    skipped.append({**base, 'reason': 'out of earshot of the camera'})
                    continue
                name = row['event'].split(':', 1)[-1]
                for pat, g in lifts:
                    if matches(name, row['event'], pat):
                        gain *= g
                        break
                duck = any(matches(name, row['event'], p) for p in duck_patterns)
                placed.append(Placed(source=source, event=row['event'], file=row['file'], shot=shot, frame=f, clip=c.index, time=t,
                                     offset=offset, gain=gain, pan=pan, rate=rate, stop=c.out_end / fps, looping=row['looping'], duck=duck,
                                     stand_in=stand_in or ''))
            if not shown and not any(c.contains(f) or f < c.src_in for c in clips):
                skipped.append({**base, 'reason': 'trimmed out of the cut'})
            elif not shown:
                skipped.append({**base, 'reason': 'started before the cut-in and short'})
    placed.sort(key=lambda p: (p.time, p.shot, p.frame))
    return placed, skipped


def render_sfx(placed, sounds, n):
    left, right = dsp.zeros(n), dsp.zeros(n)
    for p in placed:
        source, buf = sounds.buffer({'event': p.event, 'file': p.file, 'stand_in': p.stand_in})
        if source is None:
            continue
        played = sounds.at_rate((p.event, p.file, p.stand_in), buf, p.rate)
        start = dsp.seconds_to_samples(p.offset)
        at = dsp.seconds_to_samples(p.time)
        stop_at = dsp.seconds_to_samples(p.stop)
        if p.looping:
            # Loop the sound from its offset until the clip ends.
            pos, length = at, len(played)
            if length == 0:
                continue
            first = start % length
            while pos < stop_at:
                take = min(length - first, stop_at - pos)
                seg = played[first:first + take]
                _add_panned(left, right, seg, pos, p.gain, p.pan, fade_out=FADE_STOP if pos + take >= stop_at else 0)
                pos += take
                first = 0
            continue
        avail = stop_at - at
        if avail <= 0:
            continue
        seg = played[start:start + avail]
        cut = len(played) - start > avail
        _add_panned(left, right, seg, at, p.gain, p.pan, fade_out=FADE_STOP if cut else 0, fade_in=FADE_STOP if start > 0 else 0)
    return left, right


def _add_panned(left, right, seg, at, gain, pan, fade_out=0, fade_in=0):
    if fade_out or fade_in:
        seg = seg[:]
        dsp.fade(seg, fade_in, fade_out)
    gl, gr = dsp.pan_gains(pan)
    dsp.add_into(left, seg, at, gain * gl * math.sqrt(2))
    dsp.add_into(right, seg, at, gain * gr * math.sqrt(2))


def picture_envelope(timeline, n, through_black=False):
    """1 while a shot is on screen, ramping with each clip's fades to/from black, 0 over black gaps (1 if
    `through_black`). Built clip by clip as filled spans, so a hard cut is a hard step."""
    env = dsp.zeros(n)
    fps = timeline.fps
    for c in timeline.clips:
        a = max(0, min(n, dsp.seconds_to_samples(c.out_start / fps)))
        b = max(0, min(n, dsp.seconds_to_samples(c.out_end / fps)))
        if b <= a:
            continue
        if c.kind == 'black':
            if through_black:
                env[a:b] = array('f', repeat(1.0, b - a))
            continue
        env[a:b] = array('f', repeat(1.0, b - a))
        fi = min(b - a, dsp.seconds_to_samples(c.fade_in / fps)) if c.fade_in else 0
        fo = min(b - a, dsp.seconds_to_samples(c.fade_out / fps)) if c.fade_out else 0
        for i in range(fi):
            env[a + i] = i / fi
        for i in range(fo):
            env[b - 1 - i] = min(env[b - 1 - i], i / fo)
    return env


def place_voice(it, timeline, edit):
    voice, out = edit.get('voice') or [], []
    fps = timeline.fps
    for i, v in enumerate(voice):
        f = Path(v['file'])
        path = next((p for p in (f, it.path / f, ROOT / f) if p.exists()), None)
        if path is None:
            raise SystemExit(f'edit.voice[{i}]: no voice file {v["file"]} (looked in {it.path} and {ROOT})')
        clips = timeline.shot_clips(v['shot'])
        if not clips:
            continue
        frame = int(round(float(v.get('at', 0)) * fps))
        clip = next((c for c in clips if c.contains(frame)), clips[0])
        t = max(0.0, clip.out_frame(frame) / fps)
        out.append(Placed(source='voice', event='voice', file=str(path), shot=v['shot'], frame=frame, clip=clip.index, time=t,
                          gain=dsp.from_db(float(v.get('gain', 0))), stop=timeline.seconds))
    return out


def render_voice(placed, n):
    bus = dsp.zeros(n)
    for p in placed:
        buf = assets.decode_path(p.file, 1)
        # Level each line to the same speech level (RMS over its non-silent blocks).
        levels = [x for x in dsp.block_rms(buf, BLOCK) if x > 1e-3]
        level = math.sqrt(sum(x * x for x in levels) / len(levels)) if levels else 0
        norm = dsp.from_db(VOICE_REF_DB) / level if level > 0 else 1.0
        dsp.add_into(bus, buf, dsp.seconds_to_samples(p.time), p.gain * norm)
        p.length = len(buf) / SR
    return bus


def duck_curve(n, keys, depth_db, attack=None, release=None, lookahead=None, hold=None):
    """Per-block gain for the bed: down by `depth_db` (negative) wherever a key is active, or by an interval's own
    depth. `keys` are buses (active where a 10 ms block's RMS is over 0.003) or intervals [(start_s, stop_s, depth_db)].

    The shape: a depth holds `hold` seconds after its key ends (so the bed does not swell between words or between
    packed lines); it is reached `lookahead` seconds before the key starts, ramping linearly in dB over `attack`
    seconds before that (the bed is down before the first word); it recovers with a one-pole release of `release`
    seconds."""
    attack = ATTACK if attack is None else attack
    release = RELEASE if release is None else release
    lookahead = LOOKAHEAD if lookahead is None else lookahead
    hold = HOLD if hold is None else hold
    blocks = n // BLOCK + 1
    target = [0.0] * blocks
    for key in keys:
        if isinstance(key, tuple) and len(key) == 3:
            a, b, d = key
            for i in range(max(0, int(a * SR / BLOCK)), min(blocks, int(math.ceil(b * SR / BLOCK)))):
                target[i] = min(target[i], d)
        else:
            for i, level in enumerate(dsp.block_rms(key, BLOCK)):
                if level > 0.003 and i < blocks:
                    target[i] = min(target[i], depth_db)
    h = int(round(hold * SR / BLOCK))
    if h:
        held = [min(target[max(0, i - h):i + 1]) for i in range(blocks)]
    else:
        held = target
    a_blocks = max(1, int(round(attack * SR / BLOCK)))
    lead = int(round(lookahead * SR / BLOCK))
    span = a_blocks + lead
    pre = []
    for i in range(blocks):
        g = held[i]
        for k in range(1, span + 1):
            if i + k >= blocks:
                break
            t = held[i + k]
            if t < 0:
                g = min(g, t * min(1.0, (span - k) / a_blocks))
        pre.append(g)
    kr = 1 - math.exp(-BLOCK / (release * SR))
    g, out = 0.0, []
    for t in pre:
        g = t if t < g else g + kr * (t - g)
        out.append(dsp.from_db(g))
    return out


def line_ducks(spans, voice_readings, music_readings, under, least, floor=DUCK_FLOOR):
    """Interval keys [(start, end, depth)] that put the bed `under` LU (negative) below each line: the line's voice
    loudness (power mean of its momentary readings) against the loudest momentary reading of the undocked bed under
    it, with MARGIN LU to spare; never shallower than `least` dB, never deeper than `floor`."""
    keys = []
    for a, b, *_ in spans:
        v = balance.power_mean([r[1] for r in balance.inside(voice_readings, a, b)])
        mr = [r[1] for r in balance.inside(music_readings, a, b)]
        m = max(mr) if mr else balance.FLOOR
        if v <= balance.FLOOR or m <= balance.FLOOR:
            keys.append((a, b, least))
            continue
        need = (v + under - MARGIN) - m
        keys.append((a, b, max(floor, min(least, need))))
    return keys


def music_bus(it, timeline, edit, mode, n, picture, report):
    """The bed, levelled by RMS (MUSIC_REF_DB + gain), with its cues, fades and hits, silent over black unless
    `through_black`; not yet ducked (build() levels it in LUFS and ducks it)."""
    music = edit.get('music')
    if not music:
        return None
    music = dict(music)
    fps = timeline.fps
    start_at = float(music.get('at', 0))
    length = max(0.0, timeline.seconds - start_at) + 0.5
    seed = int(music.get('seed', it.plan().get('seed', 1)))
    source, track, style, key, why = choose_music(music, mode, length, seed, report)
    if source == 'synth':
        skip = float(music.get('start', 0))  # seconds into the bed (past its two-bar intro, say)
        bed = synth.render(length + skip, style=style, bpm=music.get('bpm'), key=key, seed=seed)
        first = dsp.seconds_to_samples(skip)
        stems = {k: (v[first:],) * 2 for k, v in bed.stems.items()}  # mono stems: the same array left and right
        beat = bed.beat
        report['music'] = {'source': 'synth', 'style': bed.style, 'bpm': bed.bpm, 'key': bed.key, 'start': skip, 'at': start_at}
    else:
        name = catalog.bare(track)
        files = assets.event_files(name) if '/' not in name else []
        file = files[0] if files else name
        row = catalog.tracks().get(file, {})
        left, right = assets.decode(file, 2)
        start_s = float(music['start']) if 'start' in music else float(row.get('entry', 0)) if music.get('mood') else 0.0
        left, right, looped = _fit_track(left, right, dsp.seconds_to_samples(start_s), dsp.seconds_to_samples(length), row.get('loops') or [])
        stems = {'track': (left, right)}
        measured = row.get('bpm') if row.get('pulse', 0) >= 0.15 else None
        beat = 60.0 / float(music.get('bpm') or measured or 120)
        report['music'] = {'source': 'game', 'file': file, 'start': start_s, 'at': start_at, 'bpm': round(60.0 / beat, 1)}
        if looped:
            report['music']['loop'] = looped
    if why:
        report['music']['picked'] = why
    if music.get('mood'):
        report['music']['mood'] = music['mood']

    # Level the bed: its RMS (all stems) to the reference, then the script's gain.
    total = dsp.zeros(len(next(iter(stems.values()))[0]))
    for l, r in stems.values():
        dsp.add_into(total, l, 0, 0.5)
        dsp.add_into(total, r, 0, 0.5)
    level = dsp.rms(total)
    norm = dsp.from_db(MUSIC_REF_DB + float(music.get('gain', 0))) / level if level > 0 else 1.0

    # Cues: per-stem gain points.
    offset = dsp.seconds_to_samples(start_at)
    state = {k: 1.0 for k in stems}
    points = {k: [(0, 1.0)] for k in stems}
    hits = []
    cues = []
    for i, cue in enumerate(music.get('cue') or []):
        if 'time' in cue:
            t = float(cue['time'])
        else:
            clips = timeline.shot_clips(cue.get('shot'))
            if not clips:
                raise SystemExit(f'edit.music.cue[{i}]: shot = "{cue.get("shot")}" is not in the cut')
            frame = int(round(float(cue.get('at', 0)) * fps))
            clip = next((c for c in clips if c.contains(frame)), clips[0])
            t = clip.out_frame(frame) / fps
        cues.append((t, i, cue))
    cues.sort(key=lambda x: (x[0], x[1]))
    for t, i, cue in cues:
        do = cue.get('do')
        s = dsp.seconds_to_samples(t) - offset
        fade = dsp.seconds_to_samples(float(cue.get('fade', 0.25 if do in ('out', 'in') else 0.05)))
        gain = dsp.from_db(float(cue.get('gain', 0)))
        if do in ('out', 'in', 'full', 'thin'):
            for k in stems:
                new = {'out': 0.0, 'in': gain, 'full': gain, 'thin': (gain if k == 'drums' else 0.0) if 'drums' in stems else 0.35 * gain}[do]
                points[k] += [(s, state[k]), (s + fade, new)]
                state[k] = new
        elif do == 'drop':
            hold = dsp.seconds_to_samples(float(cue.get('length', beat)))
            edge = dsp.seconds_to_samples(0.012)
            for k in stems:
                points[k] += [(s, state[k]), (s + edge, 0.0), (s + hold, 0.0), (s + hold + edge, state[k])]
        elif do == 'hit':
            hits.append(t)
        else:
            raise SystemExit(f'edit.music.cue[{i}]: do = "{do}": one of out, in, drop, thin, full, hit')
    report['music']['cues'] = [{'time': round(t, 4), 'do': c.get('do')} for t, _, c in cues]

    m = len(total)
    fi = dsp.seconds_to_samples(float(music.get('fade_in', 0)))
    fo = dsp.seconds_to_samples(float(music.get('fade_out', 0)))
    # Each stem with its cue envelope (and the bed's fades), placed at the music's start in the cut.
    left, right = dsp.zeros(n), dsp.zeros(n)
    for k, (l, r) in stems.items():
        env = dsp.ramp_envelope(points[k], m)
        if fi:
            dsp.fade(env, fi, 0)
        if fo:
            end = dsp.seconds_to_samples(timeline.seconds) - offset
            for j in range(min(fo, end)):
                if 0 <= end - 1 - j < m:
                    env[end - 1 - j] *= j / fo
        span = min(m, n - offset)
        if span <= 0:
            continue
        ls = dsp.scaled(l[:span], norm)
        dsp.multiply(ls, env[:span])
        dsp.add_into(left, ls, offset)
        if r is l:
            dsp.add_into(right, ls, offset)
        else:
            rs = dsp.scaled(r[:span], norm)
            dsp.multiply(rs, env[:span])
            dsp.add_into(right, rs, offset)
    if hits:
        # A hit is levelled against the bed's own reference, not the track's normalization (a quiet track's norm
        # once put hits at +1 LUFS momentary, and the limiter squashed the whole mix under them).
        crash, kick = sfx.crash(), sfx.kick()
        ref = dsp.from_db(MUSIC_REF_DB + float(music.get('gain', 0)) + HIT_DB)
        hit = dsp.zeros(max(len(crash), len(kick)))
        dsp.add_into(hit, crash, 0, 0.7)
        dsp.add_into(hit, kick, 0, 0.9)
        level = dsp.rms(hit, 0, min(len(hit), int(0.3 * SR)))
        hg = ref / level if level > 0 else 0.0
        for t in hits:
            at = dsp.seconds_to_samples(t)
            dsp.add_into(left, hit, at, hg)
            dsp.add_into(right, hit, at, hg)
    if not music.get('through_black'):
        dsp.multiply(left, picture)
        dsp.multiply(right, picture)
    report['music']['level_db'] = round(MUSIC_REF_DB + float(music.get('gain', 0)), 1)
    return left, right


def choose_music(music, mode, length, seed, report):
    """(source "synth" | "game", track, style, key, why) for [edit.music].

    Without `source`: "game" when a track is named, "synth" when only a style is (as before), else "auto". Auto
    prefers Minecraft: a game track picked by mood from the music map (catalog/music.toml) when the export may use game
    audio and the assets are there; otherwise the synth bed in the mood's style. An original-only mix plays the synth
    bed in the style of the mood of the track it replaces."""
    source = music.get('source') or ('game' if music.get('track') else 'synth' if music.get('style') and not music.get('mood') else 'auto')
    if source not in ('auto', 'synth', 'game'):
        raise SystemExit(f'[edit.music] source = "{source}": one of auto, synth, game')
    mood = music.get('mood')
    if mood is not None and mood not in synth.MOODS:
        raise SystemExit(f'[edit.music] mood = "{mood}": one of {", ".join(synth.MOODS)}')
    if source == 'game' and not music.get('track'):
        raise SystemExit('[edit.music] source = "game" needs track = "<sound file or event>" (e.g. "music/game/wet_hands"), '
                         'or source = "auto" with a mood')
    track, why = music.get('track'), ''
    if source == 'auto':
        mood = mood or 'upbeat'
        if mode == 'game' and assets.available():
            picked = resolve.pick_track(mood, seconds=length, bpm=music.get('bpm'), seed=seed, exclude=tuple(music.get('exclude') or ()),
                                        vocals=bool(music.get('vocals')), rank=int(music.get('rank', 0)))
            if picked:
                track, row, why = picked[0], picked[1], f'{mood}: {picked[0]} ({picked[2]})'
                source = 'game'
        if source == 'auto':
            source = 'synth'
            report['notes'].append(f'music: no game track for {mood} ({"original audio" if mode != "game" else "no game assets"}): '
                                   f'the synth bed in the {mood} style')
    if source == 'game' and mode == 'original':
        row = catalog.tracks().get(catalog.bare(track), {})
        mood = mood or (row.get('mood') or ['upbeat'])[0]
        report['notes'].append(f'original audio: the game music track is replaced by the synth bed ({mood})')
        source = 'synth'
    style, key = music.get('style'), music.get('key')
    if source == 'synth' and not style:
        style, mood_key = synth.style_for(mood or 'upbeat', music.get('bpm'))
        key = key or mood_key
    return source, track, style or 'upbeat', key, why


def _fit_track(left, right, start, need, loops):
    """The track from `start` for `need` samples; when it runs out first, the measured loop (b back to a) repeats
    with a 60 ms crossfade. Returns (left, right, loop or None)."""
    left, right = left[start:], right[start:]
    if len(left) >= need or not loops:
        return left[:need], right[:need], None
    a, b = (dsp.seconds_to_samples(t) - start for t in loops[0][:2])
    if a < 0 or b <= a or b > len(left):
        return left[:need], right[:need], None
    x = int(0.06 * SR)
    outs = []
    for ch in (left, right):
        out = array('f', ch[:b])
        while len(out) < need:
            seg = ch[a:b]
            for i in range(min(x, len(seg), len(out))):
                k = i / x
                out[len(out) - x + i] = out[len(out) - x + i] * (1 - k) + seg[i] * k
            out.extend(seg[x:])
        outs.append(out[:need])
    return outs[0], outs[1], [round(loops[0][0], 2), round(loops[0][1], 2)]


def place_edit_sfx(it, timeline, edit, mode):
    """[[edit.sfx]]: sounds the edit places itself, not logged by the take: (placed, buffers by index). Game audio
    first (a deterministic variant of the event, from the local assets), the original library in original mode or
    when the catalog has no Minecraft sound for it."""
    placed, buffers, fades = [], [], []
    fps = timeline.fps
    for i, entry in enumerate(edit.get('sfx') or []):
        where = f'edit.sfx[{i}]'
        try:
            event, lib, pitch, volume = resolve.edit_sfx_sound(entry, where)
        except (resolve.SoundError, library.UnknownSound) as e:
            raise SystemExit(str(e)) from e
        if 'time' in entry:
            t = float(entry['time'])
        else:
            clips = timeline.shot_clips(entry.get('shot'))
            if not clips:
                raise SystemExit(f'{where}: shot = "{entry.get("shot")}" is not in the cut (or give time = <seconds in the cut>)')
            frame = int(round(float(entry.get('at', 0)) * fps))
            clip = next((c for c in clips if c.contains(frame)), clips[0])
            t = clip.out_frame(frame) / fps
        gain = dsp.from_db(float(entry.get('gain', 0))) * volume
        # `start` seconds into the sound, `length` seconds of it (then a `fade`-second fade out): a record from a
        # jukebox under one stretch of the cut.
        offset = max(0.0, float(entry.get('start', 0)))
        stop = min(timeline.seconds, t + float(entry['length'])) if entry.get('length') is not None else timeline.seconds
        if 'fade' in entry:
            fades.append(float(entry['fade']))
        else:
            fades.append(0.25 if entry.get('length') is not None else 0.0)
        if event and mode == 'game':
            files = assets.event_files(event)
            if files:
                file = files[sfx.hash_name(f'{it.plan().get("seed", 1)}:{i}:{event}') % len(files)]
                buffers.append(assets.decode(file, 1))
                placed.append(Placed(source='game', event=f'minecraft:{event}', file=file, shot=entry.get('shot') or '', frame=-1, clip=-1,
                                     time=t, offset=offset, gain=gain, pan=float(entry.get('pan', 0)), rate=max(0.5, min(2.0, pitch)), stop=stop))
                continue
        if not lib:
            raise SystemExit(f'{where}: no original sound for it in an original-only mix; give library = "<name>" too')
        buffers.append(library.render(lib))
        placed.append(Placed(source='synth', event=f'videocraft:lib/{lib}', file='', shot=entry.get('shot') or '', frame=-1, clip=-1, time=t,
                             offset=offset, gain=gain, pan=float(entry.get('pan', 0)), rate=1.0 if event else max(0.5, min(2.0, pitch)), stop=stop,
                             stand_in=lib if event else ''))
    for p, f in zip(placed, fades):
        p.fade = f
    return placed, buffers


def render_edit_sfx(placed, buffers, n):
    left, right = dsp.zeros(n), dsp.zeros(n)
    for p, buf in zip(placed, buffers):
        played = dsp.resample(buf, p.rate)
        a = dsp.seconds_to_samples(p.offset)
        keep = dsp.seconds_to_samples(max(0.0, p.stop - p.time))
        fade = dsp.seconds_to_samples(getattr(p, 'fade', 0.0))
        if a or keep < len(played) - a:
            played = played[a:a + keep]
            fade = max(fade, FADE_STOP) if keep < len(buf) else fade
        _add_panned(left, right, played, dsp.seconds_to_samples(p.time), p.gain, p.pan, fade_out=min(fade, len(played)))
    return left, right


def _shifted(readings, db):
    return [(t, m + db if m > balance.FLOOR else m, x + db if x > balance.FLOOR else x) for t, m, x in readings]


def _cfg(mixcfg, key, default):
    v = mixcfg.get(key)
    return default if v is None else float(v)


def sfx_keys(readings, voice_level, spans, ceiling, under_line, voice_readings=()):
    """Interval keys [(start, end, dB)] that hold the effects bus under `ceiling` LU re the voice level everywhere and
    `under_line` LU re each line's own voice while it speaks: each momentary reading over its limit pulls its 400 ms
    window down by the excess."""
    limits = []
    for a, b, *_ in spans:
        v = balance.power_mean([r[1] for r in balance.inside(voice_readings, a, b)]) if voice_readings else voice_level
        limits.append((a, b, (v if v > balance.FLOOR else voice_level) + under_line))
    keys = []
    for t, m, _ in readings:
        if m <= balance.FLOOR:
            continue
        w0 = t - balance.WINDOW
        limit = voice_level + ceiling
        for a, b, lim in limits:
            if w0 < b and t > a:
                limit = min(limit, lim)
        if m > limit:
            keys.append((w0, t, limit - m))
    return keys


def level_buses(voice, sfx_pair, music, mixcfg, musiccfg, report, spans=()):
    """The gains that set the balance in LUFS: the voice bus to `voice_level` (+ [edit.mix] voice dB); the bed so
    that, after the master's gain (estimated from voice + effects), it plays at `music_level` (+ [edit.music] gain,
    + GAME_TRIM for a game track) between lines. Returns the gains, the targets and the voice's and the undocked
    bed's momentary readings (for line_ducks)."""
    voice_level = _cfg(mixcfg, 'voice_level', VOICE_LUFS) + float(mixcfg.get('voice', 0) or 0)
    music_level = _cfg(mixcfg, 'music_level', MUSIC_LEVEL)
    under = -abs(_cfg(mixcfg, 'music_under_voice', MUSIC_UNDER_VOICE))
    game_trim = _cfg(mixcfg, 'game_trim', GAME_TRIM) if (report.get('music') or {}).get('source') == 'game' else 0.0
    least = min(0.0, float(musiccfg.get('duck', DUCK)))
    out = {'voice_gain': 1.0, 'music_gain': 1.0, 'voice_readings': [], 'music_readings': [], 'voice_level': voice_level,
           'music_level': music_level, 'music_under_voice': under, 'under': under, 'least': least, 'game_trim': game_trim}
    if voice is not None:
        v = balance.loudness(voice)
        if v['integrated'] is not None and v['integrated'] > balance.FLOOR:
            out['voice_gain'] = dsp.from_db(voice_level - v['integrated'])
            out['voice_readings'] = _shifted(v['readings'], voice_level - v['integrated'])
    # Effects just under the voice: a ceiling over the whole cut, lower under a line.
    if dsp.peak(sfx_pair[0]) > 0 or dsp.peak(sfx_pair[1]) > 0:
        ceiling, under_line = _cfg(mixcfg, 'sfx_ceiling', SFX_CEILING), _cfg(mixcfg, 'sfx_under_line', SFX_UNDER_LINE)
        keys = sfx_keys(balance.loudness(*sfx_pair)['readings'], voice_level, spans, ceiling, under_line, out['voice_readings'])
        if keys:
            n = len(sfx_pair[0])
            env = dsp.block_curve_to_samples(duck_curve(n, keys, 0.0, attack=0.02, lookahead=0.01, hold=0.05, release=0.3), BLOCK, n)
            dsp.multiply(sfx_pair[0], env)
            dsp.multiply(sfx_pair[1], env)
        out['sfx_limited'] = {'stretches': len(keys), 'deepest_db': round(min((k[2] for k in keys), default=0.0), 1),
                              'ceiling': ceiling, 'under_line': under_line}
    # The master's gain, estimated from what is there before the bed (the bed adds a few tenths of a dB).
    est = None
    if voice is not None:
        vs_l, vs_r = array('f', sfx_pair[0]), array('f', sfx_pair[1])
        dsp.add_into(vs_l, voice, 0, out['voice_gain'])
        dsp.add_into(vs_r, voice, 0, out['voice_gain'])
        est = balance.loudness(vs_l, vs_r)['integrated']
    elif dsp.peak(sfx_pair[0]) > 0:
        est = balance.loudness(*sfx_pair)['integrated']
    master_gain = loudness.TARGET - est if est is not None and est > balance.FLOOR else 0.0
    out['master_gain_estimate'] = round(master_gain, 2)
    if music is not None:
        m = balance.loudness(*music)
        if m['integrated'] is not None and m['integrated'] > balance.FLOOR:
            want = music_level + float(musiccfg.get('gain', 0) or 0) + game_trim - master_gain
            out['music_gain'] = dsp.from_db(want - m['integrated'])
            out['music_readings'] = m['readings']
            report['music']['loudness'] = {'measured': m['integrated'], 'target': round(want + master_gain, 1),
                                           'gain_db': round(want - m['integrated'], 2), 'game_trim': game_trim}
    return out


def build(it, original=None, keep_raw=False, name='audio', stems=False):
    """Mixes and masters the iteration's sound track into cut/<name>.wav (report cut/<name>.json); returns its path, or
    None for no audio. The cut asks for name = "audio-original" (original=True) beside the game mix for exports with
    `audio = "original"`. `stems`: also cut/<name>-stems/{voice,music,sfx}.wav, each at the master's gain (no limiter),
    so a person can listen to (or measure) what sits over what."""
    started = time.time()
    plan, edit = it.plan(), it.edit()
    mode = _mode(edit, original)
    if mode == 'none':
        return None
    if mode == 'game':
        assets.index_file()  # names the file it looked for when there are no assets
    it.cut.mkdir(parents=True, exist_ok=True)
    timeline = tl.load(it)
    n = dsp.seconds_to_samples(timeline.seconds)
    mixcfg = edit.get('mix') or {}
    sounds = Sounds(mode, resolve.original_hints(plan) if mode == 'original' else None)
    report = {'mode': mode, 'fps': timeline.fps, 'seconds': timeline.seconds, 'notes': []}

    placed, skipped = place_sfx(it, timeline, sounds, mixcfg.get('duck') or (), mixcfg.get('lift'))
    sfx_l, sfx_r = render_sfx(placed, sounds, n)
    picture = picture_envelope(timeline, n)
    dsp.multiply(sfx_l, picture)
    dsp.multiply(sfx_r, picture)
    sfx_gain = dsp.from_db(float(mixcfg.get('sfx', 0)))

    voices = place_voice(it, timeline, edit)
    voice = render_voice(voices, n) if voices else None

    edit_placed, edit_buffers = place_edit_sfx(it, timeline, edit, mode)
    if edit_placed:
        el, er = render_edit_sfx(edit_placed, edit_buffers, n)
        dsp.add_into(sfx_l, el, 0)
        dsp.add_into(sfx_r, er, 0)
    sfx_l, sfx_r = dsp.scaled(sfx_l, sfx_gain), dsp.scaled(sfx_r, sfx_gain)

    if sfx_gain == 1.0:
        sfx_l, sfx_r = array('f', sfx_l), array('f', sfx_r)   # level_buses limits them in place
    music = music_bus(it, timeline, edit, mode, n, picture, report)
    spans = balance.speech_spans(voices, edit.get('dialogue'))
    levels = level_buses(voice, (sfx_l, sfx_r), music, mixcfg, edit.get('music') or {}, report, spans)
    if voice is not None:
        voice = dsp.scaled(voice, levels['voice_gain'])
    if music is not None:
        music = (dsp.scaled(music[0], levels['music_gain']), dsp.scaled(music[1], levels['music_gain']))
        keys = []
        if voice is not None:
            keys = line_ducks(spans, levels['voice_readings'], _shifted(levels['music_readings'], dsp.db(levels['music_gain'])),
                              levels['under'], levels['least'])
        depth = levels['least']
        for p in placed:
            if p.duck:
                keys.append((p.time, p.time + 0.6, max(depth, -6.0)))
        for p in edit_placed:
            keys.append((p.time, p.time + 0.6, max(depth, -6.0)))
        curve = duck_curve(n, keys, depth)
        env = dsp.block_curve_to_samples(curve, BLOCK, n)
        dsp.multiply(music[0], env)
        if music[1] is not music[0]:
            dsp.multiply(music[1], env)
        report['music']['ducks'] = [{'start': round(a, 3), 'end': round(b, 3), 'db': round(d, 1)} for a, b, d in keys]

    left, right = array('f', sfx_l), array('f', sfx_r)
    if voice is not None:
        dsp.add_into(left, voice, 0)
        dsp.add_into(right, voice, 0)
    if music is not None:
        dsp.add_into(left, music[0], 0)
        dsp.add_into(right, music[1], 0)

    raw = it.cut / f'.{name}-mix.f32'
    out = it.cut / f'{name}.wav'
    dsp.write_f32(raw, left, right)
    measured = loudness.master(raw, out)
    if not keep_raw:
        raw.unlink(missing_ok=True)
    pictured = [(c.out_start / timeline.fps, c.out_end / timeline.fps) for c in timeline.clips if c.kind != 'black']
    report['balance'] = balance.measure(voice, music, (sfx_l, sfx_r), float(measured.get('gain_db') or 0.0), spans, pictured)
    report['balance']['targets'] = {k: levels[k] for k in ('voice_level', 'music_level', 'music_under_voice', 'least', 'game_trim')}
    if levels.get('sfx_limited'):
        report['balance']['sfx']['limited'] = levels['sfx_limited']
    if stems:
        folder = it.cut / f'{name}-stems'
        folder.mkdir(exist_ok=True)
        g = float(measured.get('gain_db') or 0.0)
        for stem, pair in (('voice', (voice, voice) if voice is not None else None), ('music', music), ('sfx', (sfx_l, sfx_r))):
            if pair is not None:
                tmp = folder / f'.{stem}.f32'
                dsp.write_f32(tmp, *pair)
                subprocess.run([tools.ffmpeg(), '-y', '-loglevel', 'error', '-f', 'f32le', '-ar', str(SR), '-ac', '2', '-i', str(tmp),
                                '-af', f'volume={g:.3f}dB', '-c:a', 'pcm_f32le', str(folder / f'{stem}.wav')], check=True)
                tmp.unlink()
    gaps = []
    for c in timeline.clips:
        if c.kind == 'black' and c.out_frames >= 6:
            seg = loudness.measure(out, start=c.out_start / timeline.fps, duration=c.out_frames / timeline.fps)
            gaps.append({'clip': c.index, 'time': round(c.out_start / timeline.fps, 4), 'seconds': round(c.out_frames / timeline.fps, 4),
                         'integrated': seg['integrated']})
    report.update({
        'file': out.name, 'sample_rate': SR, 'channels': 2, 'loudness': measured, 'black_gaps': gaps,
        'events': [p.to_json() for p in placed], 'voice': [p.to_json() for p in voices], 'skipped': skipped,
        'edit_sfx': [p.to_json() for p in edit_placed],
        'game_assets_used': any(p.source == 'game' for p in placed + edit_placed) or report.get('music', {}).get('source') == 'game',
        'build_seconds': round(time.time() - started, 2),
    })
    (it.cut / f'{name}.json').write_text(json.dumps(report, indent=2) + '\n')
    return out
