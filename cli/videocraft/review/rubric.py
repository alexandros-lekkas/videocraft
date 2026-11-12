"""Rubrics: what reviewers score, who scores what, and the pass rule. A rubric is a TOML file, or a Markdown file
whose first ```toml fenced block is the rubric (docs/REVIEW.md is both the general rubric and its explanation).

    name = "general"                 # lowercase-dash
    title = "…"
    [pass]   average = 7.0, minimum = 5, max_shot_seconds = 7.5 (optional, lint uses it)
    [[gate]]       id, name, measures                          pass/fail; one fail fails the review
    [[criterion]]  id, name, measures, anchor_5, anchor_9, numbers = ["picture.shot_stats", …] (metrics to read)
    [[role]]       id, name, focus, criteria = [ids], images = ["strips", "contact", "cuts", "sound"]

Every criterion must be scored by at least one role. Owned by workstream (d).
"""
import re
import tomllib
from pathlib import Path

from videocraft.paths import ROOT

DEFAULT = ROOT / 'docs/REVIEW.md'
IMAGE_SETS = {'strips', 'contact', 'cuts', 'sound'}
ID = re.compile(r'^[a-z][a-z0-9_]{0,31}$')


class RubricError(ValueError):
    pass


def resolve(ref=None):
    """A rubric path from a path or a short name (`pinksheep-style` finds docs/benchmarks/pinksheep-style.rubric.toml)."""
    if not ref or ref == 'general':
        return DEFAULT
    p = Path(ref)
    if p.exists():
        return p
    for candidate in (ROOT / 'docs/benchmarks' / f'{ref}.rubric.toml', ROOT / 'docs' / f'{ref}.rubric.toml'):
        if candidate.exists():
            return candidate
    raise RubricError(f'No rubric {ref} (a path, or a name under docs/benchmarks/<name>.rubric.toml)')


def load(ref=None):
    path = resolve(ref)
    text = path.read_text(encoding='utf-8')
    if path.suffix == '.md':
        m = re.search(r'```toml\n(.*?)```', text, re.S)
        if not m:
            raise RubricError(f'{path}: a Markdown rubric needs a ```toml fenced block')
        text = m.group(1)
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise RubricError(f'{path}: {e}') from e
    data['path'] = str(path)
    check(data)
    return data


def check(r):
    where = r.get('path', 'rubric')
    for key in ('name', 'criterion', 'role'):
        if not r.get(key):
            raise RubricError(f'{where}: `{key}` is required')
    ids = [c.get('id') for c in r['criterion']]
    for c in r['criterion']:
        if not ID.match(str(c.get('id'))):
            raise RubricError(f'{where}: criterion id {c.get("id")!r} must be lowercase_with_underscores')
        for key in ('name', 'measures', 'anchor_5', 'anchor_9'):
            if not c.get(key):
                raise RubricError(f'{where}: criterion {c["id"]} needs `{key}`')
    if len(set(ids)) != len(ids):
        raise RubricError(f'{where}: criterion ids repeat')
    covered = set()
    for role in r['role']:
        if not ID.match(str(role.get('id'))):
            raise RubricError(f'{where}: role id {role.get("id")!r} must be lowercase_with_underscores')
        unknown = set(role.get('criteria', [])) - set(ids)
        if unknown or not role.get('criteria'):
            raise RubricError(f'{where}: role {role["id"]} scores unknown or no criteria {sorted(unknown)}; criteria: {ids}')
        bad = set(role.get('images', [])) - IMAGE_SETS
        if bad:
            raise RubricError(f'{where}: role {role["id"]} asks for unknown image sets {sorted(bad)}; known: {sorted(IMAGE_SETS)}')
        covered |= set(role['criteria'])
    if set(ids) - covered:
        raise RubricError(f'{where}: no role scores {sorted(set(ids) - covered)}')
    rule = r.setdefault('pass', {})
    rule.setdefault('average', 7.0)
    rule.setdefault('minimum', 5)
    r.setdefault('gate', [])
    return r


def role(r, rid):
    for x in r['role']:
        if x['id'] == rid:
            return x
    raise RubricError(f'No role {rid} in rubric {r["name"]}; roles: {[x["id"] for x in r["role"]]}')


def criteria_of(r, rid):
    wanted = set(role(r, rid)['criteria'])
    return [c for c in r['criterion'] if c['id'] in wanted]
