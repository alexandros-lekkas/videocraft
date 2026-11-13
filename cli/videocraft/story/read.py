"""`story read`: does the script make sense to someone who has never seen it? A cold read by a fresh model.

    transcript(raw, source)  the film as a viewer meets it, in cut order: per shot its name, what is seen (the shot's
                             note, its camera, its action cues), what is heard (sound cues) and shown (on-screen
                             text), and every line of dialogue as `Speaker: line`
    text(entries, cast)      that as plain text (what the reader gets; never the premise, bible or outline)
    read(raw, source, ask)   asks a fresh model to read it cold (prompts/read.md): a 1-10 "makes sense" score and
                             line-by-line issues with fixes
    markdown(result)         story-read.md

The owner, after watching the films: "read the script, it does not make sense". A writer model that drafted the
premise, bible and outline knows what every line means; a viewer does not. So the reader gets only what reaches the
screen and the speakers: lines that do not make sense, a joke or reveal with no setup, a character called by two
names (or two characters by one), a sentence split across shots that reads wrong, non sequiturs, jokes that do not
land. A production needs PASS (8) before it films: `story build` and `make` run it and stop below that.
"""
import json
import re
from pathlib import Path

PASS = 8
KINDS = ('nonsense', 'missing_setup', 'name', 'split_sentence', 'non_sequitur', 'joke', 'unclear_picture', 'other')
TEXT_ACTIONS = {'caption', 'title', 'card', 'lower_third', 'keycap', 'message'}
QUIET = {'place', 'mark', 'wait', 'clear', 'blink', 'command', 'stand_in', 'glide', 'particles', 'ambience', 'tune'}
SCHEMA = {
    'type': 'object',
    'additionalProperties': False,
    'required': ['score', 'understood', 'issues'],
    'properties': {
        'score': {'type': 'integer', 'minimum': 1, 'maximum': 10,
                  'description': 'how well the film makes sense to a first-time viewer, 10 = every line and beat lands'},
        'understood': {'type': 'string', 'description': 'what you, as a viewer, think happens and why it is funny, in 2-4 sentences'},
        'issues': {'type': 'array', 'items': {
            'type': 'object', 'additionalProperties': False,
            'required': ['shot', 'speaker', 'line', 'kind', 'severity', 'problem', 'fix'],
            'properties': {
                'shot': {'type': 'string', 'description': 'the shot name'},
                'speaker': {'type': 'string', 'description': 'who says the line ("" for a picture or text problem)'},
                'line': {'type': 'string', 'description': 'the words quoted exactly as in the transcript ("" if none)'},
                'kind': {'type': 'string', 'enum': list(KINDS)},
                'severity': {'type': 'string', 'enum': ['high', 'medium', 'low']},
                'problem': {'type': 'string', 'description': 'what a viewer does not get, in one sentence'},
                'fix': {'type': 'string', 'description': 'the rewritten line, or exactly what to add or change and where'},
            }}},
    },
}


class ReadError(RuntimeError):
    pass


def _clean(text):
    return ' '.join(t[1:] if t.startswith('*') and len(t) > 1 else t for t in str(text).split())


def _cast(raw, source):
    """The cast for speaker names: [cast] relative to the script, the repository, or any folder above the script
    (a story's `file = "stories/x/cast.toml"` read from another checkout); None if it cannot be read."""
    from videocraft.voice import cast as castmod
    actors = {a['id']: a for a in (raw.get('actor') or []) if isinstance(a, dict) and isinstance(a.get('id'), str)}
    c = raw.get('cast') or {}
    try:
        return castmod.load(c, source, actors)
    except castmod.CastError:
        pass
    if isinstance(c, dict) and c.get('file') and source:
        for parent in Path(source).resolve().parents:
            if (parent / c['file']).exists():
                try:
                    return castmod.load({**c, 'file': str(parent / c['file'])}, source, actors)
                except castmod.CastError:
                    break
    try:
        return castmod.load({k: v for k, v in c.items() if k != 'file'} if isinstance(c, dict) else {}, source, actors)
    except castmod.CastError:
        return None


def _order(raw):
    """Shot names in cut order: [[edit.clip]] when the script has it (black gaps as None), else script order."""
    shots = [s.get('name') for s in raw.get('shot') or [] if isinstance(s, dict)]
    clips = (raw.get('edit') or {}).get('clip') or []
    if not clips:
        return shots
    out = []
    for c in clips:
        if isinstance(c, dict) and 'shot' in c:
            if not out or out[-1] != c['shot']:
                out.append(c['shot'])
        elif isinstance(c, dict) and 'black' in c:
            out.append(None)
    return out


def _who(cue, cast, actors):
    cid = cue.get('character') or cue.get('actor') or '?'
    name = None
    if cast is not None:
        try:
            name = cast.character(cid).name
        except Exception:
            name = None
    name = cue.get('speaker') or name or (actors.get(cid) or {}).get('name') or str(cid).replace('-', ' ').title()
    return cid, name


def _picture(cue, actors):
    do = cue.get('do')
    who = cue.get('actor')
    bits = [f'{who} {do}' if who else str(do)]
    for k in ('state', 'pose', 'gesture', 'what', 'target', 'at_actor', 'item', 'block', 'entity', 'mood'):
        v = cue.get(k)
        if k == do:
            bits[0] = f'{who} {do} {v}' if who else f'{do} {v}'
            continue
        if isinstance(v, (str, int, float)) and not isinstance(v, bool):
            bits.append(f'{k} {v}')
    return ' '.join(bits)


def transcript(raw, source=None):
    """The film as entries in cut order: {shot, note, camera, seen [..], heard [..], shown [..], lines [..]}; a black
    gap is {'black': True}."""
    cast = _cast(raw, source)
    actors = {a['id']: a for a in (raw.get('actor') or []) if isinstance(a, dict) and isinstance(a.get('id'), str)}
    by_name = {s.get('name'): s for s in raw.get('shot') or [] if isinstance(s, dict)}
    out = []
    for name in _order(raw):
        if name is None:
            out.append({'black': True})
            continue
        shot = by_name.get(name)
        if shot is None:
            continue
        cam = shot.get('camera') or {}
        camera = ''
        if isinstance(cam, dict) and cam.get('rig'):
            camera = f'{cam["rig"]}' + (f' on {cam["subject"]}' if cam.get('subject') else '')
        entry = {'shot': name, 'note': str(shot.get('note') or '').strip(), 'camera': camera, 'seen': [], 'heard': [],
                 'shown': [], 'lines': []}
        cues = _timeline(shot.get('cue') or [])
        for c in cues:
            do = c.get('do')
            if do == 'say':
                cid, who = _who(c, cast, actors)
                line = {'character': cid, 'speaker': who, 'text': _clean(c.get('text', ''))}
                if c.get('style'):
                    line['style'] = c['style']
                cut = c.get('cut_on')
                if isinstance(cut, int) and not isinstance(cut, bool):   # a word index of the line
                    words = line['text'].split()
                    cut = words[cut] if 0 <= cut < len(words) else None
                if cut:
                    line['cut_on'] = _clean(cut)
                entry['lines'].append(line)
            elif do in TEXT_ACTIONS:
                words = c.get('text') or c.get('title') or ''
                if isinstance(words, list):
                    words = ' / '.join(map(str, words))
                if c.get('subtitle'):
                    words = f'{words} / {c["subtitle"]}'
                if str(words).strip():
                    entry['shown'].append(f'{do}: {_clean(words)}')
            elif do == 'sound':
                what = c.get('id') or c.get('tag') or c.get('palette') or c.get('library') or c.get('sound')
                if what:
                    entry['heard'].append(str(what).split(':', 1)[-1])
            elif do not in QUIET and do:
                entry['seen'].append(_picture(c, actors))
        out.append(entry)
    return out


def _timeline(cues):
    """A shot's cues in the order they play. A `say` without `at` is packed after the line before it (SCRIPT.md,
    Dialogue), so it sorts just after that line, not at 0; any other cue without `at` is at 0."""
    timed, last = [], None
    for i, c in enumerate(x for x in cues if isinstance(x, dict)):
        at = c.get('at')
        if at is None and c.get('do') == 'say' and last is not None:
            t = last
        else:
            t = float(at or 0)
        if c.get('do') == 'say':
            last = t
        timed.append((t, i, c))
    return [c for _t, _i, c in sorted(timed, key=lambda x: (x[0], x[1]))]


def cast_lines(raw, source=None):
    """`id: on-screen name (engine voice)` for each character with a line."""
    cast = _cast(raw, source)
    speakers = []
    for s in raw.get('shot') or []:
        for c in (s.get('cue') or []) if isinstance(s, dict) else []:
            if isinstance(c, dict) and c.get('do') == 'say':
                speakers.append(c.get('character') or c.get('actor'))
    out = []
    for cid in dict.fromkeys(x for x in speakers if isinstance(x, str)):
        if cast is None:
            out.append(f'{cid}')
            continue
        ch = cast.character(cid)
        out.append(f'{cid}: shown as "{ch.name}", voice {ch.engine} {ch.voice}' + (' (generic: in no cast)' if ch.generic else ''))
    return out


def text(entries, cast=()):
    """The plain transcript the reader gets."""
    L = []
    if cast:
        L += ['Speakers (id: the name on screen, the voice heard):'] + [f'- {c}' for c in cast] + ['']
    n = 0
    for e in entries:
        if e.get('black'):
            L += ['[black]', '']
            continue
        n += 1
        head = f'[{n}. {e["shot"]}]'
        if e['camera']:
            head += f' camera: {e["camera"]}'
        L.append(head)
        if e['note']:
            L.append(f'  picture: {e["note"]}')
        if e['seen']:
            L.append('  action: ' + '; '.join(e['seen']))
        if e['heard']:
            L.append('  sound: ' + ', '.join(e['heard']))
        for s in e['shown']:
            L.append(f'  on screen: {s}')
        for l in e['lines']:
            extra = [x for x in (l.get('style'), f'cut to the next shot on "{l["cut_on"]}"' if l.get('cut_on') else None) if x]
            L.append(f'  {l["speaker"]} [{l["character"]}]: {l["text"]}' + (f'  ({"; ".join(extra)})' if extra else ''))
        L.append('')
    return '\n'.join(L).rstrip() + '\n'


def prompt(raw, source=None):
    from videocraft.story.stages import prompt_file, render
    entries = transcript(raw, source)
    return render(prompt_file('read'), transcript=text(entries, cast_lines(raw, source)), passing=PASS), entries


def parse(reply):
    m = re.findall(r'```json\s*\n(.*?)```', reply, re.S)
    candidate = m[-1] if m else reply.strip()
    if not m and '{' in candidate:
        candidate = candidate[candidate.index('{'):candidate.rindex('}') + 1]
    try:
        out = json.loads(candidate)
    except json.JSONDecodeError as e:
        raise ReadError(f'the reader\'s reply has no JSON ({e}): {reply[:300]}') from e
    if not isinstance(out, dict) or not isinstance(out.get('score'), (int, float)):
        raise ReadError(f'the reader\'s reply has no score: {str(out)[:300]}')
    out['score'] = max(1, min(10, int(round(out['score']))))
    out['issues'] = [i for i in out.get('issues') or [] if isinstance(i, dict)]
    out.setdefault('understood', '')
    return out


def read(raw, source=None, ask=None, model=None):
    """{score, understood, issues, pass, transcript}: one cold read by a fresh model."""
    if ask is None:
        from videocraft.story._ask import ask
    p, entries = prompt(raw, source)
    kw = {'schema': SCHEMA}
    if model:
        kw['model'] = model
    result = parse(ask(p, **kw))
    result['pass'] = result['score'] >= PASS
    result['transcript'] = entries
    result['cast'] = cast_lines(raw, source)
    result['lines'] = sum(len(e.get('lines') or []) for e in entries)
    return result


def note(result):
    """The issues as a revise note for the shots stage."""
    rows = [f'- shot {i.get("shot")}: {i.get("speaker") + ": " if i.get("speaker") else ""}"{i.get("line")}" '
            f'({i.get("kind")}): {i.get("problem")} Fix: {i.get("fix")}' for i in result.get('issues') or []]
    return (f'A cold read by a first-time viewer scored the script {result["score"]}/10 for making sense (it needs '
            f'{PASS}). What the viewer understood: {result.get("understood", "")}\nFix these, keeping everything else:\n'
            + '\n'.join(rows))


def markdown(result, title):
    order = {'high': 0, 'medium': 1, 'low': 2}
    issues = sorted(result.get('issues') or [], key=lambda i: order.get(i.get('severity'), 3))
    L = [f'# Story read: {title}', '',
         f'**{result["score"]}/10 makes sense** ({"PASS" if result["pass"] else "FAIL"}: a production needs {PASS} before it '
         f'films). A fresh model read the dialogue and the picture cues cold, as a first-time viewer; it saw no premise, '
         f'bible or outline, and no frames.', '',
         '## What the viewer understood', '', result.get('understood') or '-', '',
         f'## Issues ({len(issues)})', '']
    if issues:
        L += ['| # | Severity | Shot | Speaker | Line | Kind | Problem | Fix |', '|--:|:--|:--|:--|:--|:--|:--|:--|']
        cell = lambda s: str(s or '').replace('|', '\\|').replace('\n', ' ')
        for k, i in enumerate(issues, 1):
            L.append(f'| {k} | {cell(i.get("severity"))} | {cell(i.get("shot"))} | {cell(i.get("speaker"))} | {cell(i.get("line"))} | '
                     f'{cell(i.get("kind"))} | {cell(i.get("problem"))} | {cell(i.get("fix"))} |')
    else:
        L.append('None.')
    L += ['', '## The transcript the reader saw', '', '```text', text(result['transcript'], result.get('cast')).rstrip(), '```', '']
    return '\n'.join(L)


def write(result, out_dir, title):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    md = out_dir / 'story-read.md'
    md.write_text(markdown(result, title), encoding='utf-8')
    (out_dir / 'story-read.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return md
