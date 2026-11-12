"""The five stages: each one drafted from the stages before it, checked, and repaired by the model when it fails.

    premise.md → bible.toml → outline.md → script.md → shots.toml (a videocraft shot script; compiles)

`draft` regenerates a stage from its upstream stages, `revise` applies a note to the current revision, and
`--from-file` (here: `from_file`) locks in a hand-written draft without a model. Every model attempt, including each
failed repair round, is kept as a revision; only a draft that passes its checks is locked.
"""
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

from videocraft import script as shotscript
from videocraft.paths import ROOT
from videocraft.story import vocab
from videocraft.story.store import EXT, FILES, FORMATS, STAGES, StoryError

PROMPTS = Path(__file__).resolve().parent / 'prompts'
REPAIRS = 3
KINDS = {'mob', 'mannequin', 'narrator', 'player'}
MAX_SHOT = 7.5  # seconds: the comedy-short rule (docs/benchmarks/pinksheep-style.md)
LENGTH = 'the shots add up to'


def prompt_file(name):
    return (PROMPTS / f'{name}.md').read_text(encoding='utf-8')


def render(template, **values):
    """`{{key}}` placeholders (single braces stay literal: TOML and JSON in prompts are full of them)."""
    def sub(m):
        key = m.group(1)
        if key not in values:
            raise KeyError(f'prompt placeholder {{{{{key}}}}} has no value')
        return str(values[key])
    return re.sub(r'\{\{(\w+)\}\}', sub, template)


def extract(reply):
    """The file in a model reply: between <<<FILE and FILE>>>, else the one fenced block, else the whole reply."""
    m = re.search(r'^<<<FILE[^\n]*\n(.*?)^FILE>>>', reply, re.S | re.M)
    if m:
        return m.group(1).strip('\n') + '\n'
    fences = re.findall(r'^```[a-zA-Z]*\n(.*?)^```', reply, re.S | re.M)
    if len(fences) == 1:
        return fences[0].strip('\n') + '\n'
    return reply.strip('\n') + '\n'


def upstream(stage):
    return list(STAGES[:STAGES.index(stage)])


# Checks ---------------------------------------------------------------------------------------------------------

def check(stage, text, story, store=None, path=None, drafted=True):
    """Problems with a draft, each phrased as a fix. Empty: it passes. A hand-written file (`drafted` false) is
    trusted on its total length (a teaser or a test fixture may be short on purpose); a model draft is not."""
    if not text.strip():
        return [f'{FILES[stage]} is empty']
    problems = CHECKS[stage](text, story, store, path)
    return problems if drafted else [p for p in problems if not p.startswith(LENGTH)]


def _check_premise(text, story, store, path):
    low = text.lower()
    problems = [f'premise.md needs a "## {s}" section' for s in ('Logline', 'Format') if f'## {s.lower()}' not in low]
    if not text.lstrip().startswith('# '):
        problems.append('premise.md starts with a "# <Title>" line')
    return problems


def _check_bible(text, story, store, path):
    try:
        bible = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        return [f'bible.toml is not valid TOML: {e}']
    problems, ids = [], set()
    chars = bible.get('character')
    if not isinstance(chars, list) or not chars:
        problems.append('bible.toml needs at least one [[character]]')
        chars = []
    for i, c in enumerate(chars):
        where = f'character[{i}]'
        cid = c.get('id') if isinstance(c, dict) else None
        if not isinstance(cid, str) or not shotscript.NAME.match(cid):
            problems.append(f'{where}: id = "<lowercase-dash>" is required (it becomes the actor id)')
            continue
        if cid in ids:
            problems.append(f'{where}: id "{cid}" is used twice')
        ids.add(cid)
        kind = c.get('kind')
        if kind not in KINDS:
            problems.append(f'character {cid}: kind is one of {", ".join(sorted(KINDS))} (got {kind!r})')
        if kind == 'mob' and not str(c.get('entity', '')).startswith('minecraft:'):
            problems.append(f'character {cid}: a mob needs entity = "minecraft:<entity>"')
        if kind == 'mannequin' and not isinstance(c.get('skin'), (dict, str)):
            problems.append(f'character {cid}: a mannequin needs skin = {{ ... }} (a skin spec) or a PNG path')
    sets = bible.get('set', [])
    if not isinstance(sets, list):
        problems.append('bible.toml: sets are [[set]] tables with a name')
        sets = []
    for i, s in enumerate(sets):
        if not isinstance(s, dict) or not isinstance(s.get('name'), str):
            problems.append(f'set[{i}]: name = "<set name>" is required')
    return problems


def _check_outline(text, story, store, path):
    beats = [l for l in text.splitlines() if l.startswith('## ') and 'comedy pass' not in l.lower()]
    problems = []
    if len(beats) < 3:
        problems.append(f'outline.md has {len(beats)} beat(s) ("## " headings); a story needs at least setup, turn and payoff')
    if 'comedy pass' not in text.lower():
        problems.append('outline.md needs a "## Comedy pass" table naming every joke and how it lands')
    return problems


SPEAKER = re.compile(r'^([A-Z][A-Z0-9 .\'-]*?)(?: \((VO|V\.O\.|O\.S\.)\))?: (.+)$')


def dialogue(text):
    """[(speaker, line)] of a script.md."""
    return [(m.group(1).strip(), m.group(3).strip()) for m in map(SPEAKER.match, text.splitlines()) if m]


def _check_script(text, story, store, path):
    problems = []
    if not any(l.startswith('## ') for l in text.splitlines()):
        problems.append('script.md needs scene headings ("## Scene 1: <set>, <time>")')
    for speaker, line in dialogue(text):
        if re.search(r'\w\*', line):
            problems.append(f'{speaker}: "{line}": mark a key word with a leading * only (*word, not *word*)')
        elif line.count('*') > 1:
            problems.append(f'{speaker}: "{line}" has {line.count("*")} *key words; at most one (the word the cut lands on)')
    return problems


def _check_shots(text, story, store, path):
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        return [f'shots.toml is not valid TOML: {e}']
    try:
        plan, edit = shotscript.compile_script(raw, 'shots.toml')
    except shotscript.ScriptError as e:
        return [f'videocraft compile: {e}']
    problems = []
    if plan['name'] != story['id']:
        problems.append(f'name = "{plan["name"]}": the shot script of story {story["id"]} is name = "{story["id"]}"')
    actions, rigs = vocab.vocabulary()
    actors = {'player'} | {a['id'] for a in plan['actors']}
    cues = [(f'world.stage[{i}]', c) for i, c in enumerate(plan['world']['stage'])]
    for shot in plan['shots']:
        rig = shot['camera'].get('rig')
        if ':' not in str(rig) and rig not in rigs:
            problems.append(f'shot {shot["name"]}: rig "{rig}" is not a videocraft rig; rigs: {", ".join(sorted(rigs))}')
        if story.get('format') == 'short' and shot['duration'] > MAX_SHOT:
            problems.append(f'shot {shot["name"]}: {shot["duration"]:g} s; a short never holds a shot over {MAX_SHOT} s (split it)')
        cues += [(f'shot {shot["name"]} cue at {c["at"]:g}', c) for c in shot['timeline']]
    for where, cue in cues:
        do = cue['do']
        if ':' not in do and do not in actions:
            problems.append(f'{where}: do = "{do}" is not a videocraft action; actions: {", ".join(sorted(actions))}')
        if cue.get('actor', 'player') not in actors:
            problems.append(f'{where}: actor "{cue["actor"]}" is not an [[actor]] (actors: {", ".join(sorted(actors))})')
        if do == 'say' and (not isinstance(cue.get('text'), str) or cue['text'].count('*') > 1):
            problems.append(f'{where}: a say cue has text = "<the line, with at most one *key word>"')
    out = plan['output']
    if story.get('vertical') and not out['width'] < out['height']:
        problems.append(f'[output] is {out["width"]}x{out["height"]}; this story is vertical: width = 1080, height = 1920')
    lo, hi = FORMATS.get(story.get('format'), (0, 1e9))
    total = sum(s['duration'] for s in plan['shots'])
    if not lo * 0.8 <= total <= hi * 1.1:
        problems.append(f'the shots add up to {total:.1f} s; a {story.get("format")} is {lo}-{hi} s')
    problems += lint(path, text)
    return problems


def lint(path, text):
    """`videocraft lint` (the CLI workstream's) on the draft, when it is implemented: its output when it fails."""
    tmp = None
    if path is None:
        import tempfile
        tmp = tempfile.NamedTemporaryFile('w', suffix='.toml', delete=False, encoding='utf-8')
        tmp.write(text)
        tmp.close()
        path = tmp.name
    try:
        done = subprocess.run([sys.executable, '-m', 'videocraft', 'lint', str(path)], cwd=ROOT / 'cli',
                              capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as e:
        return [f'videocraft lint could not run: {e}']
    finally:
        if tmp:
            Path(tmp.name).unlink(missing_ok=True)
    out = (done.stdout + done.stderr).strip()
    # Not there yet: the placeholder (exit 2, "not implemented yet"; it takes no file, so argparse's usage error comes
    # first) or no such command. A usage error is our call being wrong, not the script: never sent to the model.
    if done.returncode == 0 or 'not implemented yet' in out or 'invalid choice' in out or \
            done.returncode == 2 and out.startswith('usage:'):
        return []
    return [f'videocraft lint: {line}' for line in out.splitlines() if line.strip()][:30]


CHECKS = {'premise': _check_premise, 'bible': _check_bible, 'outline': _check_outline, 'script': _check_script,
          'shots': _check_shots}


# Prompts --------------------------------------------------------------------------------------------------------

def _sets_text():
    sets = vocab.sets_available()
    if not sets:
        return '(none yet: describe new sets, and in shots.toml stage what you need with world.stage commands)'
    return '\n'.join(f'- `{name}`' + (f': marks {", ".join(marks)}' if marks else '') for name, marks in sets.items())


def _output_text(story):
    if story.get('vertical'):
        return '9:16 vertical: `[output] width = 1080, height = 1920, fps = 60`.'
    return '16:9: the default `[output]` (1920x1080, 60 fps).'


def stage_prompt(stage, store, sid, request=None, extra=''):
    story = store.meta(sid)
    ctx = {k: store.text(sid, k) or '(not written yet)' for k in upstream(stage)}
    lo, hi = FORMATS[story['format']]
    values = {'craft': prompt_file('craft'), 'id': sid, 'format': story['format'], 'length': f'{lo}-{hi} s',
              'aspect': '9:16 vertical' if story.get('vertical') else '16:9', 'request': request or story.get('request', ''),
              'extra': extra, 'sets': _sets_text(), 'output': _output_text(story), **ctx}
    if stage == 'shots':
        values['reference'] = vocab.script_reference()
    return render(prompt_file(stage), **values)


def _stage_rules(stage):
    """The shape part of a stage's own prompt, for revisions."""
    text = prompt_file(stage)
    head, _, rest = text.partition('Write ')
    return 'Write ' + rest if rest else text


def revise_prompt(stage, store, sid, note):
    story = store.meta(sid)
    ups = '\n\n'.join(f'### {FILES[k]}\n{store.text(sid, k) or "(not written yet)"}' for k in upstream(stage)) or '(nothing: this is the first stage)'
    values = {'craft': prompt_file('craft'), 'file': FILES[stage], 'note': note, 'upstream': ups,
              'current': store.text(sid, stage) or '(empty)'}
    rules = _stage_rules(stage)
    if stage == 'shots':
        rules = rules.replace('{{reference}}', vocab.script_reference())
    lo, hi = FORMATS[story['format']]
    rules = render(rules.replace('{{craft}}', ''), **{k: v for k, v in {
        'id': sid, 'output': _output_text(story), 'sets': _sets_text(), 'format': story['format'], 'length': f'{lo}-{hi} s',
        'aspect': '9:16 vertical' if story.get('vertical') else '16:9', 'request': story.get('request', ''),
        'extra': '', 'reference': vocab.script_reference(),
        **{k: '(above)' for k in STAGES}}.items()})
    values['stage_rules'] = rules
    return render(prompt_file('revise'), **values)


# Drafting -------------------------------------------------------------------------------------------------------

class Outcome:
    def __init__(self, stage, rev, locked, problems, attempts):
        self.stage, self.rev, self.locked, self.problems, self.attempts = stage, rev, locked, problems, attempts

    @property
    def ok(self):
        return not self.problems


def _check_path(store, sid, stage, rev):
    return store.revision_path(sid, stage, rev) if stage == 'shots' else None


def _after(store, sid, stage, rev):
    """Side outputs of a passing revision: a shots draft keeps its compiled plan next to it."""
    if stage != 'shots':
        return
    p = store.revision_path(sid, stage, rev)
    plan, edit = shotscript.compile_script(shotscript.load(p), str(p))
    p.with_suffix('.plan.json').write_text(json.dumps({'plan': plan, 'edit': edit}, indent=2) + '\n', encoding='utf-8')


def _guard(store, sid, stage):
    if stage not in STAGES:
        raise StoryError(f'stage "{stage}": one of {", ".join(STAGES)}')
    owner, _ = store.source_of(sid, stage)
    if owner != sid:
        raise StoryError(f'{sid} reads its bible from the series story {owner}: draft or revise it there '
                         f'(`story revise bible {owner} --note ...`)')
    missing = [k for k in upstream(stage) if store.text(sid, k) is None]
    if missing:
        raise StoryError(f'{sid}: {stage} is drafted from {", ".join(upstream(stage))}; write {missing[0]} first '
                         f'(`story draft {missing[0]} {sid}`, or --from-file)')


def run_stage(store, sid, stage, ask=None, note=None, from_file=None, lock=True, repairs=REPAIRS, say=print,
              request=None, revise=False):
    """Drafts (or revises) one stage. Returns an Outcome; the last passing revision is locked when `lock`."""
    if from_file is None:
        _guard(store, sid, stage)
    elif stage not in STAGES:
        raise StoryError(f'stage "{stage}": one of {", ".join(STAGES)}')
    story = store.meta(sid)
    inputs = store.shas(sid, upstream(stage))
    parent = store.current(sid, stage)
    if from_file is not None:
        text = Path(from_file).read_text(encoding='utf-8')
        rev = store.add(sid, stage, text, parent=parent, note=note or f'from {Path(from_file).name}', source='file', inputs=inputs)
        problems = check(stage, text, story, store, _check_path(store, sid, stage, rev), drafted=False)
        if not problems:
            _after(store, sid, stage, rev)
            if lock:
                store.lock(sid, stage, rev)
        return Outcome(stage, rev, lock and not problems, problems, 1)
    if ask is None:
        from videocraft.story._ask import ask
    if revise:
        if store.text(sid, stage) is None:
            raise StoryError(f'{sid}: no {stage} to revise yet; `story draft {stage} {sid}` first')
        prompt = revise_prompt(stage, store, sid, note)
    else:
        prompt = stage_prompt(stage, store, sid, request=request,
                              extra=f'A note from the director: {note}' if note else '')
    rev, problems, attempt = None, [], 0
    for attempt in range(1, repairs + 2):
        say(f'  {stage}: asking the model' + (f' (repair {attempt - 1} of {repairs})' if attempt > 1 else ''))
        text = extract(ask(prompt))
        source = 'model' if attempt == 1 else 'repair'
        rev = store.add(sid, stage, text, parent=parent if attempt == 1 else rev, inputs=inputs, source=source,
                        note=note if attempt == 1 else f'repair {attempt - 1}: ' + '; '.join(problems)[:300])
        problems = check(stage, text, story, store, _check_path(store, sid, stage, rev))
        if not problems:
            break
        say(f'  {stage} r{rev}: {len(problems)} problem(s): ' + problems[0])
        if attempt > repairs:
            break
        prompt = render(prompt_file('repair'), round=attempt, rounds=repairs, file=FILES[stage],
                        problems='\n'.join(f'- {p}' for p in problems), current=text)
        if stage == 'shots':  # the reference again: repairs must stay inside the vocabulary
            prompt += '\n\n## The shot script reference (docs/SCRIPT.md)\n' + vocab.script_reference()
    if not problems:
        _after(store, sid, stage, rev)
        if lock:
            store.lock(sid, stage, rev)
    return Outcome(stage, rev, lock and not problems, problems, attempt)


def ext(stage):
    return EXT[stage]
