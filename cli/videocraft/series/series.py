"""A series: one story split into numbered episodes that each stand alone and continue the last.

Each episode is a story of its own (`<series>-e01`, ...) whose bible is the series story's bible (story.json
`bible_from`), so characters, sets and gags stay stable. Its premise is written from the split (title, logline,
"previously", cold open, payoff, button, beats); its outline, script and shots are drafted as for any story.

    stories/<series>/series.json    {"series", "episodes": [{"n", "id", "title"}]}
"""
import json
import re
from pathlib import Path

from videocraft.story import stages
from videocraft.story.store import FORMATS, STAGES, StoryError

FIELDS = ('title', 'logline', 'cold_open', 'payoff', 'button')


def episode_id(series, n):
    return f'{series}-e{n:02d}'


def parse_split(text, episodes):
    """The model's (or a hand-written file's) JSON list of episodes, checked; problems as a list."""
    m = re.search(r'\[.*\]', text, re.S)
    try:
        data = json.loads(m.group(0) if m else text)
    except json.JSONDecodeError as e:
        return None, [f'the split is not a JSON list of episodes: {e}']
    if not isinstance(data, list):
        return None, ['the split is a JSON list of episode objects']
    problems = []
    if len(data) != episodes:
        problems.append(f'the split has {len(data)} episode(s); {episodes} were asked for')
    for i, ep in enumerate(data, 1):
        if not isinstance(ep, dict):
            problems.append(f'episode {i} is not an object')
            continue
        for key in FIELDS:
            if not isinstance(ep.get(key), str) or not ep[key].strip():
                problems.append(f'episode {i}: "{key}" is required (text)')
        if i > 1 and not str(ep.get('previously', '')).strip():
            problems.append(f'episode {i}: "previously" (one line recalling episode {i - 1}) is required after episode 1')
    return data, problems


def premise_text(series_meta, series_title, ep, n, total, fmt, vertical):
    lo, hi = FORMATS[fmt]
    lines = [f'# {series_title}, episode {n}: {ep["title"].strip()}', '', '## Logline', ep['logline'].strip(), '']
    if n > 1:
        lines += ['## Previously', ep.get('previously', '').strip(), '']
    lines += ['## Tone', f'As the series (stories/{series_meta["id"]}/premise.md).', '',
              '## Format', f'{fmt}, {"9:16" if vertical else "16:9"}, {lo}-{hi} s; stands alone: cold open, own payoff, a button.', '',
              '## Series', f'Episode {n} of {total} of `{series_meta["id"]}`. The bible is the series bible '
              f'(stories/{series_meta["id"]}/bible.toml): same characters, sets and gags.', '',
              '## Cold open', ep['cold_open'].strip(), '', '## Payoff', ep['payoff'].strip(), '',
              '## Button', ep['button'].strip(), '']
    gags = [g for g in ep.get('gags', []) if isinstance(g, str)]
    if gags:
        lines += ['## Recurring gags'] + [f'- {g}' for g in gags] + ['']
    beats = [b for b in ep.get('beats', []) if isinstance(b, str)]
    if beats:
        lines += ['## The story in five beats'] + [f'- {b}' for b in beats] + ['']
    return '\n'.join(lines)


def _title(store, sid):
    premise = store.text(sid, 'premise') or ''
    first = premise.splitlines()[0] if premise else ''
    return first[2:].strip() if first.startswith('# ') else sid


def new(store, sid, episodes, ask=None, from_file=None, fmt=None, say=print):
    """Splits story `sid` into `episodes` episode stories. Returns their ids."""
    if episodes < 2:
        raise StoryError('a series has at least 2 episodes (--episodes N)')
    meta = store.meta(sid)
    for k in ('premise', 'bible', 'outline'):
        if store.text(sid, k) is None:
            raise StoryError(f'{sid}: a series is split from the premise, bible and outline; write {k} first')
    ids = [episode_id(sid, n) for n in range(1, episodes + 1)]
    taken = [e for e in ids if store.exists(e)]
    if taken:
        raise StoryError(f'episode stories exist already: {", ".join(taken)} (remove them from stories/ to split again)')
    fmt = fmt or meta['format']
    if from_file is not None:
        text = Path(from_file).read_text(encoding='utf-8')
        data, problems = parse_split(text, episodes)
    else:
        if ask is None:
            from videocraft.story._ask import ask
        prompt = stages.render(stages.prompt_file('series'), craft=stages.prompt_file('craft'), episodes=episodes,
                               format=fmt, premise=store.text(sid, 'premise'), bible=store.text(sid, 'bible'),
                               outline=store.text(sid, 'outline'), script=store.text(sid, 'script') or '(none)')
        data, problems = None, []
        for attempt in range(stages.REPAIRS + 1):
            say(f'  series: asking the model' + (f' (repair {attempt})' if attempt else ''))
            reply = ask(prompt)
            data, problems = parse_split(reply, episodes)
            if not problems:
                break
            prompt = (prompt + '\n\n# Your last reply had these problems; reply again with the corrected JSON only\n'
                      + '\n'.join(f'- {p}' for p in problems))
    if problems:
        raise StoryError('the split does not pass: ' + '; '.join(problems))
    title = _title(store, sid)
    for n, (eid, ep) in enumerate(zip(ids, data), 1):
        store.create(eid, fmt=fmt, vertical=meta.get('vertical', False), series=sid, episode=n, bible_from=sid,
                     request=f'Episode {n} of {episodes} of {sid}: {ep["title"]}')
        text = premise_text(meta, title, ep, n, episodes, fmt, meta.get('vertical', False))
        rev = store.add(eid, 'premise', text, note=f'split from {sid}', source='series',
                        inputs=store.shas(sid, [f'{sid}:premise', f'{sid}:bible', f'{sid}:outline']))
        store.lock(eid, 'premise', rev)
    meta = store.meta(sid)
    meta['episodes'] = ids
    store.save_meta(sid, meta)
    record = {'series': sid, 'title': title, 'episodes': [{'n': n, 'id': e, 'title': ep['title']} for n, (e, ep) in enumerate(zip(ids, data), 1)]}
    (store.story_dir(sid) / 'series.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    return ids


def status(store, sid):
    """[(n, id, title, {stage: 'r3' | 'r3 stale' | '-' | 'series'})]."""
    f = store.story_dir(sid) / 'series.json'
    if not f.exists():
        raise StoryError(f'{sid} is not a series (no stories/{sid}/series.json); `series new {sid} --episodes N`')
    record = json.loads(f.read_text(encoding='utf-8'))
    rows = []
    for ep in record['episodes']:
        cells = {}
        for stage in STAGES:
            owner, _ = store.source_of(ep['id'], stage)
            if owner != ep['id']:
                cells[stage] = 'series'
                continue
            cur = store.current(ep['id'], stage)
            cells[stage] = '-' if cur is None else f'r{cur}' + (' stale' if store.stale(ep['id'], stage) else '')
        rows.append((ep['n'], ep['id'], ep['title'], cells))
    return record, rows
