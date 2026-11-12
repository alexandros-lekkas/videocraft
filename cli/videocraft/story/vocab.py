"""What the recorder can perform: the action and rig ids, read from docs/SCRIPT.md at prompt time.

The shots stage gives the model docs/SCRIPT.md verbatim and refuses a draft that uses an action or rig the recorder
does not know (the error goes back to the model in a repair round), so the model never invents one.
"""
import re

from videocraft.paths import ROOT

DOCS = ROOT / 'docs'
# Ids the night build's workstreams contract to deliver (docs/DESIGN.md, the cross-workstream contracts), accepted
# even before their rows reach docs/SCRIPT.md. SCRIPT.md is authoritative for everything else.
CONTRACTED_ACTIONS = {
    'command', 'mark', 'wait',                                                   # runtime
    'walk', 'run', 'stop', 'look', 'turn', 'jump', 'hop', 'crouch', 'state', 'hold', 'emit', 'voice', 'swing',
    'nod', 'shake', 'blink', 'pose', 'use', 'break', 'place', 'select', 'type', 'open', 'close', 'point', 'click',  # actors
    'caption', 'title', 'keycap', 'lower_third', 'card', 'clear',                  # text
    'say',                                                                         # dialogue (voice resolver)
    'sound', 'tune',                                                               # audio
}
CONTRACTED_RIGS = {'orbit', 'fixed', 'first', 'lead', 'chase', 'track', 'dolly', 'crane', 'locked', 'two_shot', 'face'}
# What each contracted id takes, from the workstreams' briefs. Shown to the model only for ids SCRIPT.md does not
# document yet; the mod validates the parameters when the take starts, so SCRIPT.md wins once it has the row.
CONTRACT_NOTES = {
    'lead': 'rig: the camera travels backwards in front of a walking subject. subject, distance, height (1.0), pitch (5 down), fov (105), side, yaw_drift, lag, swing (true: arc round when the subject turns)',
    'chase': 'rig: behind the subject. subject, distance, height, lag, fov',
    'track': 'rig: alongside the subject. subject, distance, side, height, fov',
    'dolly': 'rig: the eye moves from a to b. from, to (positions), look (a position or subject), ease, fov',
    'crane': 'rig: rises or falls while looking. from, to, look, fov',
    'locked': 'rig: fixed eye that pans/tilts to follow a subject. eye, subject, lag, fov',
    'two_shot': 'rig: frames two subjects. subjects = ["a", "b"], distance, height, fov',
    'face': 'rig: a close-up in front of a subject\'s head. subject, distance, angle (off-axis degrees), fov (30)',
    'walk': 'actor: path = [positions], speed (blocks/s) or gait = "walk"|"strut"|"trot"|"run", arrive (easing)',
    'stop': 'actor: stop walking, easing out',
    'turn': 'actor: to = a yaw, a position, an actor id or "camera"',
    'look': 'actor (head only): at = a position, an actor id or "camera"; hold (seconds); back (true/false)',
    'hop': 'actor: a small jump on the spot',
    'state': 'actor: the entity\'s own pose: fox sit/sleep/crouch/pounce; goat lower_head/raise_head/scream; chicken flap; generic sneak/sit/sleep',
    'hold': 'actor: item = "minecraft:<item>" in mouth or hand, or "none"',
    'emit': 'actor: item = "minecraft:egg" pops out beside the actor with its sound (a chicken lays an egg)',
    'voice': 'actor: sound = "ambient"|"hurt"|"scream" or a sound id; pitch',
    'nod': 'actor: a head nod', 'shake': 'actor: a head shake', 'blink': 'actor: a blink where the model has one',
    'pose': 'mannequin: pose = "wave"|"point"|"shrug"|"sit"|"crouch"|"cheer"|"facepalm"|"type"|"talk"; hold (seconds)',
    'say': 'dialogue: actor, text = "line with one *key word"; the voice tool speaks it, captions and cut points follow the words',
    'caption': 'text: text = "words, *key word highlighted" (or a list of lines), hold (seconds), style = "pop"|"whole", at most two lines',
    'title': 'text: text, hold', 'card': 'text: a full-frame card: text, hold, background', 'lower_third': 'text: text, hold',
    'keycap': 'text: key, hold', 'clear': 'text: removes the text on screen',
    'sound': 'audio: sound = "minecraft:<sound id>", at the actor or a position, volume, pitch',
    'tune': 'audio: note-block notes: notes = [...], bpm, instrument',
}
_ROW_IDS = re.compile(r'`([a-z_][a-z0-9_]*)`')


def _doc(name):
    f = DOCS / name
    return f.read_text(encoding='utf-8') if f.exists() else ''


def script_reference():
    """docs/SCRIPT.md verbatim (what the model is taught), the contracted ids it does not document yet, and
    docs/SETS.md when the sets workstream wrote it."""
    parts = [_doc('SCRIPT.md')]
    documented_actions, documented_rigs = vocabulary(parts[0], contracted=False)
    pending = {k: v for k, v in CONTRACT_NOTES.items() if k not in documented_actions | documented_rigs}
    if pending:
        parts.append('## Also available tonight (being added to SCRIPT.md; exactly these keys)\n\n'
                     + '\n'.join(f'- `{k}`: {v}' for k, v in pending.items()))
    sets = _doc('SETS.md')
    if sets:
        parts.append(sets)
    return '\n\n---\n\n'.join(p for p in parts if p)


def vocabulary(text=None, contracted=True):
    """(actions, rigs) named in SCRIPT.md's tables, plus the contracted ids."""
    text = _doc('SCRIPT.md') if text is None else text
    actions, rigs = (set(CONTRACTED_ACTIONS), set(CONTRACTED_RIGS)) if contracted else (set(), set())
    section = ''
    for line in text.splitlines():
        if line.startswith('#'):
            section = line.lower()
            continue
        if not line.startswith('| `'):
            continue
        if not contracted and ('see DESIGN.md' in line or re.search(r'\|\s*\[[a-z]\]\s*\|\s*$', line)):
            continue  # a planned row ("[b]", "see DESIGN.md"): named, but its keys are not documented yet
        first = line.split('|')[1]
        ids = set(_ROW_IDS.findall(first))
        if 'rig' in section:
            rigs |= ids
        elif 'cue' in section or 'action' in section:
            actions |= ids
    return actions, rigs


def sets_available():
    """{set name: [mark names]} from sets/*.toml (the sets workstream's files), read leniently."""
    import tomllib
    out = {}
    for f in sorted((ROOT / 'sets').glob('*.toml')) if (ROOT / 'sets').exists() else []:
        marks = []
        try:
            data = tomllib.loads(f.read_text(encoding='utf-8'))
        except (OSError, tomllib.TOMLDecodeError):
            data = {}
        for key in ('mark', 'marks', 'path', 'paths', 'camera', 'cameras'):
            value = data.get(key)
            if isinstance(value, list):
                marks += [m['name'] for m in value if isinstance(m, dict) and isinstance(m.get('name'), str)]
            elif isinstance(value, dict):
                marks += [k for k in value]
        out[f.stem] = marks
    return out
