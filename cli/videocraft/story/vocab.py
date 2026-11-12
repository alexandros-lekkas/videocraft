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
_ROW_IDS = re.compile(r'`([a-z_][a-z0-9_]*)`')


def _doc(name):
    f = DOCS / name
    return f.read_text(encoding='utf-8') if f.exists() else ''


def script_reference():
    """docs/SCRIPT.md verbatim (what the model is taught), plus docs/SETS.md when the sets workstream wrote it."""
    parts = [_doc('SCRIPT.md')]
    sets = _doc('SETS.md')
    if sets:
        parts.append(sets)
    return '\n\n---\n\n'.join(p for p in parts if p)


def vocabulary(text=None):
    """(actions, rigs) named in SCRIPT.md's tables, plus the contracted ids."""
    text = _doc('SCRIPT.md') if text is None else text
    actions, rigs = set(CONTRACTED_ACTIONS), set(CONTRACTED_RIGS)
    section = ''
    for line in text.splitlines():
        if line.startswith('#'):
            section = line.lower()
            continue
        if not line.startswith('| `'):
            continue
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
