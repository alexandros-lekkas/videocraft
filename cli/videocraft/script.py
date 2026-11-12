"""The shot script: read the authored TOML (or JSON), check it, and compile it to plan.json for the mod.

The format is docs/SCRIPT.md. Compiling fills in every default, so the mod reads one canonical shape (Plan.java)
and two scripts that mean the same thing compile to the same plan. The `edit` table stays on the CLI side.
Owned by workstream (d); a change to the plan shape changes Plan.java and docs/SCRIPT.md in the same commit.
"""
import json
import re
import tomllib
from pathlib import Path

PLAN_VERSION = 1
NAME = re.compile(r'^[a-z0-9][a-z0-9_-]{0,47}$')
TOP = {'name', 'seed', 'output', 'world', 'actor', 'shot', 'edit', 'description', 'cast'}
WORLD = {'seed', 'save', 'gamemode', 'time', 'weather', 'settle', 'stage', 'preset'}
SHOT = {'name', 'duration', 'camera', 'cue', 'hud', 'bob', 'note', 'preroll', 'time', 'weather', 'vertical'}
GAMEMODES = {'survival', 'creative', 'adventure', 'spectator'}
WEATHER = {'clear', 'rain', 'thunder'}


class ScriptError(ValueError):
    """A problem in the script, phrased so an agent can fix it: where it is, what is wrong, what is allowed."""


def load(path):
    path = Path(path)
    text = path.read_text(encoding='utf-8')
    try:
        if path.suffix == '.json':
            return json.loads(text)
        if path.suffix == '.toml':
            return tomllib.loads(text)
    except (tomllib.TOMLDecodeError, json.JSONDecodeError) as e:
        raise ScriptError(f'{path}: {e}') from e
    raise ScriptError(f'{path}: a shot script is .toml (or .json with the same shape)')


def _unknown(table, allowed, where):
    extra = sorted(set(table) - allowed)
    if extra:
        raise ScriptError(f'{where}: unknown key(s) {", ".join(extra)}; allowed: {", ".join(sorted(allowed))}')


def _cues(cues, where, duration=None, preroll=0.0):
    out = []
    for i, cue in enumerate(cues or []):
        at = f'{where}[{i}]'
        if not isinstance(cue, dict) or 'do' not in cue:
            raise ScriptError(f'{at}: a cue is a table with at least `do` (the action) and `at` (seconds)')
        cue = dict(cue)
        cue.setdefault('at', 0.0)
        cue['at'] = float(cue['at'])
        if cue['at'] < -preroll or (duration is not None and cue['at'] > duration):
            raise ScriptError(f'{at}: at = {cue["at"]} is outside the shot ({-preroll} to {duration} s; negative needs preroll)')
        cue.setdefault('actor', 'player')
        out.append(cue)
    return sorted(out, key=lambda c: c['at'])


def compile_script(raw, source='script'):
    """Returns (plan, edit): plan is what the mod plays, edit is the cut (order, trims, music, exports)."""
    if not isinstance(raw, dict):
        raise ScriptError(f'{source}: the script is a table')
    _unknown(raw, TOP, source)
    from videocraft.voice import resolve as dialogue  # `say` cues -> captions on the words, edit.voice, shot lengths
    if dialogue.has_say(raw):
        raw = dialogue.resolve(raw, source)
    name = raw.get('name')
    if not isinstance(name, str) or not NAME.match(name):
        raise ScriptError(f'{source}: name = "<lowercase-dash-name>" is required (got {name!r})')
    output = {'width': 1920, 'height': 1080, 'fps': 60, **raw.get('output', {})}
    _unknown(output, {'width', 'height', 'fps'}, 'output')
    world = dict(raw.get('world', {}))
    _unknown(world, WORLD, 'world')
    if world.get('seed') is not None and world.get('save') is not None:
        raise ScriptError('world: give a seed (a new world) or a save (a copy of a saved world), not both')
    world = {'seed': None, 'save': None, 'gamemode': 'creative', 'time': 6000, 'weather': 'clear', 'settle': 4.0, **world}
    if world['seed'] is not None:
        world['seed'] = str(world['seed'])
    if world['gamemode'] not in GAMEMODES:
        raise ScriptError(f'world.gamemode is one of {sorted(GAMEMODES)}')
    if world['weather'] not in WEATHER:
        raise ScriptError(f'world.weather is one of {sorted(WEATHER)}')
    world['time'] = int(world['time'])
    world['settle'] = float(world['settle'])
    world['stage'] = _cues(world.get('stage'), 'world.stage')

    actors = []
    for i, actor in enumerate(raw.get('actor', [])):
        if 'id' not in actor or not NAME.match(str(actor['id'])):
            raise ScriptError(f'actor[{i}]: id = "<name>" is required')
        actors.append({'kind': 'npc', **actor})
        if isinstance(actor.get('skin'), str) and Path(source).is_file():  # a skin PNG is relative to the script
            actors[-1]['skin'] = str((Path(source).parent / actor['skin']).resolve())

    shots, names = [], set()
    for i, shot in enumerate(raw.get('shot', [])):
        where = f'shot[{i}]'
        _unknown(shot, SHOT, where)
        sname = shot.get('name')
        if not isinstance(sname, str) or not NAME.match(sname):
            raise ScriptError(f'{where}: name = "<lowercase-dash-name>" is required')
        if sname in names or sname == 'stage':
            raise ScriptError(f'{where}: the shot name "{sname}" is used twice (or reserved)')
        names.add(sname)
        duration = float(shot.get('duration', 0))
        if duration <= 0:
            raise ScriptError(f'shot {sname}: duration = <seconds> is required and > 0')
        camera = shot.get('camera')
        if not isinstance(camera, dict) or 'rig' not in camera:
            raise ScriptError(f'shot {sname}: camera = {{ rig = "orbit", ... }} is required')
        vertical = shot.get('vertical') or {}  # [shot.vertical]: camera keys for a vertical take (docs/CLIPS.md)
        _unknown(vertical, {'camera', 'subject', 'note'}, f'shot {sname}.vertical')
        if output['height'] > output['width'] and isinstance(vertical.get('camera'), dict):
            camera = {**camera, **vertical['camera']}
        preroll = float(shot.get('preroll', 0))
        if preroll < 0:
            raise ScriptError(f'shot {sname}: preroll = <seconds> is >= 0')
        out = {'name': sname, 'duration': duration, 'camera': camera, 'timeline': _cues(shot.get('cue'), f'shot {sname}.cue', duration, preroll)}
        if preroll:
            out['preroll'] = preroll
        for key in ('hud', 'bob'):
            if key in shot:
                out[key] = bool(shot[key])
        for key in ('time', 'weather'):
            if key in shot:
                out[key] = shot[key]
        shots.append(out)
    if not shots:
        raise ScriptError(f'{source}: at least one [[shot]] is required')

    plan = {'version': PLAN_VERSION, 'name': name, 'seed': int(raw.get('seed', 1)), 'output': output, 'world': world,
            'actors': actors, 'shots': shots}

    edit = dict(raw.get('edit', {}))
    clips = edit.get('clip') or [{'shot': s['name']} for s in shots]
    for i, clip in enumerate(clips):
        if clip.get('shot') not in names and 'black' not in clip:  # a black gap has no shot (edit/timeline.py)
            raise ScriptError(f'edit.clip[{i}]: shot = "{clip.get("shot")}" is not a shot in this script; shots: {sorted(names)}')
    edit['clip'] = clips
    from videocraft.edit import timeline  # the edit's own grammar: trims, push-ins, speed, looks, exports
    try:
        timeline.check(edit, names, fps=output['fps'])
    except timeline.EditError as e:
        raise ScriptError(str(e)) from e
    return plan, edit


def write_plan(plan, path):
    Path(path).write_text(json.dumps(plan, indent=2, sort_keys=False) + '\n', encoding='utf-8')
