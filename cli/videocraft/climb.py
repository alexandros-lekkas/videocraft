"""`videocraft climb <script> --budget N`: the hill-climb. Every take counts against the budget.

    1. the best scored iteration of this script (score.json, same rubric, take PASS), or a first take of the script
    2. propose: agents.ask gets the best script, its score (criteria, reasons, the reviewers' fixes), measure's report,
       lint, docs/SCRIPT.md and what this climb already tried; it answers with a whole revised script (```toml) and
       what it changed and why (```markdown). A proposal that does not compile, renames the script or fails lint is
       sent back once with the errors.
    3. run it with --parent <best> (runs/<name>/proposals/<n>.toml is the file), write notes.md, review, score
    4. keep it as the best if review.reviews.better(child, best): no failed gate, the minimum not lowered under 5,
       a higher average; otherwise the next proposal starts from the same best
    5. stop when the budget is spent (or a take fails twice in a row); runs/<name>/climb.json is the log
Owned by workstream (d).
"""
import datetime
import json
import re
from pathlib import Path

from videocraft import agents, lint, script, store
from videocraft.paths import ROOT, RUNS
from videocraft.review import reviews, rubric as rubrics


def _read(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError):
        return None


def best_iteration(name, rub_name):
    best = None
    for it in store.iterations(name):
        s = _read(it.path / 'score.json')
        r = it.result() or {}
        if s and s.get('rubric') == rub_name and r.get('verdict') == 'PASS' and s.get('average') is not None:
            if best is None or reviews.better(s, best[1]):
                best = (it, s)
    return best


def proposal_prompt(script_text, score, report, lint_lines, history, errors=None):
    doc = (ROOT / 'docs/SCRIPT.md').read_text()
    L = ['# Improve a videocraft shot script', '',
         'You are the director in a hill-climb. The script below was filmed in Minecraft, cut, measured and scored by '
         'reviewers. Write the next version: the changes most likely to raise the score, above all the reviewers\' fixes '
         'and the criteria that scored lowest. Keep what works. Change several things at once only if they serve the same '
         'fix. Use only keys and actions documented in the script reference below; the take is filmed for real.', '',
         '## The script now', '', '```toml', script_text.strip(), '```', '',
         '## Its score', '', '```json', json.dumps({k: score.get(k) for k in ('rubric', 'criteria', 'average', 'minimum', 'gates', 'pass', 'reasons')}, indent=1), '```', '',
         '### The reviewers\' fixes', '']
    L += [f'- ({f.get("reviewer")}) {f.get("fix")}: {f.get("why")} [{f.get("shot", "")} {f.get("t", "")}]' for f in score.get('fixes', [])]
    L += ['', '## Measurements of the cut (measure/report.md)', '', report.strip()[:20000], '']
    if lint_lines:
        L += ['## Lint of the script now', ''] + [f'- {x}' for x in lint_lines] + ['']
    if history:
        L += ['## Already tried in this climb (do not repeat what did not help)', '']
        L += [f'- {h["iteration"]}: {h["summary"]} → average {h.get("average")} ({"kept" if h.get("kept") else "not kept"})' for h in history]
        L.append('')
    if errors:
        L += ['## Your last proposal was rejected', '', errors, '', 'Fix these and answer again.', '']
    L += ['## The script reference (docs/SCRIPT.md)', '', doc, '',
          '## Answer', '', 'Reply with exactly two fenced blocks: first ```toml with the **whole** revised script (keep `name` the same), '
          'then ```markdown with what you changed and why, one bullet per change, each naming the fix or criterion it answers.']
    return '\n'.join(L)


def parse_proposal(reply):
    toml = re.findall(r'```toml\s*\n(.*?)```', reply, re.S)
    notes = re.findall(r'```(?:markdown|md)\s*\n(.*?)```', reply, re.S)
    if not toml:
        raise ValueError('no ```toml block in the reply')
    return toml[-1].strip() + '\n', (notes[-1].strip() if notes else 'No notes given.')


def check_proposal(text, name):
    """'' when the proposal is usable, else the errors to send back."""
    import tomllib
    try:
        raw = tomllib.loads(text)
        plan, _ = script.compile_script(raw, 'proposal')
    except (tomllib.TOMLDecodeError, script.ScriptError) as e:
        return f'It does not compile: {e}'
    if plan['name'] != name:
        return f'It renames the script to {plan["name"]!r}; keep name = "{name}"'
    errors = [p for p in lint.lint(raw) if p['severity'] == 'error']
    return '; '.join(f'{p["where"]}: {p["message"]}' for p in errors)


def climb(script_path, budget, rubric_ref=None, reviewers=None, model=None, run_take=None, review=None, say=print):
    """Returns the log. run_take(path, parent) -> (iteration, exit code); review(it, rubric, roles) -> score dict."""
    rub = rubrics.load(rubric_ref)
    roles = [r.strip() for r in reviewers.split(',')] if reviewers else None
    plan, _ = script.compile_script(script.load(script_path), str(script_path))
    name = plan['name']
    project = RUNS / name
    log_path = project / 'climb.json'
    log = {'script': str(Path(script_path).resolve()), 'rubric': rub['name'], 'budget': budget,
           'started': datetime.datetime.now().astimezone().isoformat(timespec='seconds'), 'steps': []}
    spent = 0
    best = best_iteration(name, rub['name'])
    if best is None:
        say(f'climb {name}: no scored iteration for rubric {rub["name"]}; taking the script as it is')
        it, code = run_take(Path(script_path), None)
        spent += 1
        if code != 0:
            log['stopped'] = f'the first take did not pass ({it.name})'
            return _save(log, log_path)
        s = review(it, rub, roles)
        log['steps'].append({'iteration': it.name, 'parent': None, 'average': s.get('average'), 'kept': True, 'summary': 'the script as written'})
        best = (it, s)
    if roles and sorted(best[1].get('reviewers', [])) != sorted(roles):
        say(f'climb {name}: re-reviewing {best[0].name} with {", ".join(roles)} so scores compare')
        best = (best[0], review(best[0], rub, roles))
    say(f'climb {name}: best {best[0].name}, average {best[1].get("average")}')
    failures = 0
    while spent < budget:
        it_best, s_best = best
        script_text = next(it_best.path.glob('script.*')).read_text()
        report = (it_best.measure / 'report.md').read_text() if (it_best.measure / 'report.md').exists() else ''
        try:
            raw_now = script.load(next(it_best.path.glob('script.*')))
            lint_lines = lint.report(lint.lint(raw_now, rub))[1]
        except script.ScriptError:
            lint_lines = []
        history = [h for h in log['steps'] if h.get('parent')]
        errors, proposal, notes = None, None, ''
        for attempt in range(2):
            try:
                reply = agents.ask(proposal_prompt(script_text, s_best, report, lint_lines, history, errors), model=model)
                proposal, notes = parse_proposal(reply)
            except (agents.AgentError, ValueError) as e:
                errors, proposal = str(e), None
                continue
            errors = check_proposal(proposal, name)
            if not errors:
                break
            proposal = None
        if not proposal:
            log['stopped'] = f'no usable proposal: {errors}'
            break
        (project / 'proposals').mkdir(parents=True, exist_ok=True)
        n = len(list((project / 'proposals').glob('*.toml'))) + 1
        path = project / 'proposals' / f'{n:04d}.toml'
        path.write_text(proposal)
        say(f'climb {name}: proposal {path.name} from {it_best.name}')
        it, code = run_take(path, it_best.name)
        spent += 1
        (it.path / 'notes.md').write_text(f'# {it.name} from {it_best.name}\n\n{notes}\n')
        if code != 0:
            failures += 1
            log['steps'].append({'iteration': it.name, 'parent': it_best.name, 'average': None, 'kept': False, 'summary': _first_line(notes),
                                 'failed': True})
            store.update_index(project)
            if failures >= 2:
                log['stopped'] = 'two takes in a row did not pass'
                break
            continue
        failures = 0
        s = review(it, rub, roles)
        kept = reviews.better(s, s_best)
        log['steps'].append({'iteration': it.name, 'parent': it_best.name, 'average': s.get('average'), 'minimum': s.get('minimum'),
                             'kept': kept, 'summary': _first_line(notes)})
        say(f'climb {name}: {it.name} average {s.get("average")} vs {s_best.get("average")}: {"kept" if kept else "not kept"}')
        if kept:
            best = (it, s)
        _save(log, log_path)
    log['best'] = best[0].name
    log['best_average'] = best[1].get('average')
    log['spent'] = spent
    store.update_index(project)
    return _save(log, log_path)


def _first_line(notes):
    for line in notes.splitlines():
        line = line.strip(' -*#')
        if line:
            return line[:160]
    return ''


def _save(log, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(log, indent=2) + '\n')
    return log
