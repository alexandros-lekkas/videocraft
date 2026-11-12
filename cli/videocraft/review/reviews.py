"""Reviews: validate one (review/<reviewer>.json), store it, and aggregate them into score.json. Owned by (d).

Pass rule (docs/REVIEW.md): the mean of each criterion over the reviewers who scored it; the average of those
means ≥ pass.average, no criterion mean under pass.minimum, every gate passing (one reviewer's fail fails a gate).
"""
import datetime
import json
import re

from videocraft.review import rubric as rubrics

TIMECODE = re.compile(r'^\d+:\d{1,2}(\.\d+)?$|^\d+(\.\d+)?\s*s?$')


class ReviewError(ValueError):
    pass


def extract_json(text):
    """The last fenced ```json block of a reply (or the whole reply if it is JSON)."""
    blocks = re.findall(r'```json\s*\n(.*?)```', text, re.S)
    candidate = blocks[-1] if blocks else text.strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as e:
        raise ReviewError(f'the reply has no parseable ```json block ({e})') from e


def validate(review, rub, reviewer=None):
    """Returns the review, normalised; raises ReviewError naming every problem at once."""
    problems = []
    if not isinstance(review, dict):
        raise ReviewError('a review is a JSON object')
    rid = review.get('reviewer') or reviewer
    try:
        assigned = [c['id'] for c in rubrics.criteria_of(rub, rid)]
    except rubrics.RubricError as e:
        raise ReviewError(str(e)) from e
    scores = review.get('scores')
    if not isinstance(scores, dict):
        problems.append('`scores` must be an object of criterion: 1-10')
        scores = {}
    for c in assigned:
        v = scores.get(c)
        if not isinstance(v, int) or isinstance(v, bool) or not 1 <= v <= 10:
            problems.append(f'scores.{c} must be an integer 1-10 (got {v!r})')
    known = {c['id'] for c in rub['criterion']}
    extra = set(scores) - known
    if extra:
        problems.append(f'scores has criteria not in rubric {rub["name"]}: {sorted(extra)}')
    gates = review.get('gates') or {}
    for g in rub['gate']:
        if gates.get(g['id']) not in ('pass', 'fail'):
            problems.append(f'gates.{g["id"]} must be "pass" or "fail" (got {gates.get(g["id"])!r})')
    fixes = review.get('fixes')
    if not isinstance(fixes, list) or len(fixes) < 3:
        problems.append('`fixes` must list the three most valuable fixes')
    else:
        for i, f in enumerate(fixes):
            if not isinstance(f, dict) or not str(f.get('fix', '')).strip() or not str(f.get('why', '')).strip():
                problems.append(f'fixes[{i}] needs `fix` and `why`')
    notes = review.get('notes', [])
    if not isinstance(notes, list):
        problems.append('`notes` must be a list')
        notes = []
    for i, n in enumerate(notes):
        if not isinstance(n, dict) or not str(n.get('text', '')).strip():
            problems.append(f'notes[{i}] needs `text`')
        elif not (n.get('shot') or (n.get('t') and TIMECODE.match(str(n['t']).strip()))):
            problems.append(f'notes[{i}] must cite a shot or a timecode (m:ss.ss)')
    if problems:
        raise ReviewError('; '.join(problems))
    out = dict(review)
    out['reviewer'] = rid
    out['rubric'] = rub['name']
    out['scores'] = {c: scores[c] for c in assigned}
    out.setdefault('model', 'unknown')
    out.setdefault('created', datetime.datetime.now().astimezone().isoformat(timespec='seconds'))
    return out


def store(it, review):
    it.review.mkdir(parents=True, exist_ok=True)
    path = it.review / f'{review["reviewer"]}.json'
    path.write_text(json.dumps(review, indent=2) + '\n')
    return path


def load_all(it, rubric_name=None):
    out = []
    for p in sorted(it.review.glob('*.json')) if it.review.exists() else []:
        try:
            r = json.loads(p.read_text())
        except json.JSONDecodeError:
            continue
        if isinstance(r, dict) and 'scores' in r and (rubric_name is None or r.get('rubric') == rubric_name):
            out.append(r)
    return out


def aggregate(reviews, rub):
    """score.json content from validated reviews."""
    per = {}
    for r in reviews:
        for c, v in r['scores'].items():
            per.setdefault(c, []).append(v)
    criteria = {c['id']: (round(sum(per[c['id']]) / len(per[c['id']]), 2) if per.get(c['id']) else None) for c in rub['criterion']}
    scored = [v for v in criteria.values() if v is not None]
    gates = {}
    for g in rub['gate']:
        verdicts = [r.get('gates', {}).get(g['id']) for r in reviews if g['id'] in r.get('gates', {})]
        gates[g['id']] = 'fail' if 'fail' in verdicts else 'pass' if verdicts else None
    rule = rub['pass']
    average = round(sum(scored) / len(scored), 3) if scored else None
    minimum = min(scored) if scored else None
    missing = [c for c, v in criteria.items() if v is None]
    reasons = []
    if missing:
        reasons.append(f'not scored: {", ".join(missing)}')
    if average is not None and average < rule['average']:
        reasons.append(f'average {average} under {rule["average"]}')
    if minimum is not None and minimum < rule['minimum']:
        reasons.append(f'{", ".join(c for c, v in criteria.items() if v is not None and v < rule["minimum"])} under {rule["minimum"]}')
    for g, v in gates.items():
        if v != 'pass':
            reasons.append(f'gate {g} {v or "not judged"}')
    fixes = [dict(f, reviewer=r['reviewer']) for r in reviews for f in r.get('fixes', [])]
    return {'rubric': rub['name'], 'reviewers': sorted(r['reviewer'] for r in reviews), 'criteria': criteria,
            'spread': {c: (max(v) - min(v)) for c, v in per.items() if len(v) > 1},
            'average': average, 'minimum': minimum, 'gates': gates, 'pass': not reasons and bool(scored),
            'reasons': reasons, 'fixes': fixes,
            'created': datetime.datetime.now().astimezone().isoformat(timespec='seconds')}


def better(child, parent):
    """Whether score `child` beats `parent` for the hill-climb: no failed gate, minimum not lowered under the pass
    floor, and a higher average (ties go to the parent)."""
    if not child or child.get('average') is None:
        return False
    if any(v == 'fail' for v in child.get('gates', {}).values()):
        return False
    if not parent or parent.get('average') is None:
        return True
    if (child.get('minimum') or 0) < min(parent.get('minimum') or 0, 5):
        return False
    return child['average'] > parent['average']
