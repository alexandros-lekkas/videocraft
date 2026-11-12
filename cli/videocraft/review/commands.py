"""The review command group: `review packet | add | run` and `score` (docs/REVIEW.md). Owned by workstream (d)."""
import json
import sys
from pathlib import Path

from videocraft import agents, store
from videocraft.review import packet, prompts, reviews, rubric as rubrics


def say(text=''):
    print(text, flush=True)


def _rubric_of(it, ref):
    """The rubric to use: --rubric, else the one the packet was made with, else the general rubric."""
    if ref:
        return rubrics.load(ref)
    manifest = it.review / 'packet' / 'packet.json'
    if manifest.exists():
        return rubrics.load(json.loads(manifest.read_text())['rubric_path'])
    return rubrics.load()


def cmd_packet(args):
    it = store.open_iteration(args.iteration)
    try:
        m = packet.build(it, args.rubric, args.reviewers, args.every, say)
    except rubrics.RubricError as e:
        say(f'RUBRIC ERROR {e}')
        return 2
    out = it.review / 'packet'
    say(f'PACKET   {out}')
    say(f'         {len(m["files"]["strips"])} strips, {len(m["files"]["contact"])} contact sheets, {len(m["files"]["cuts"])} cut pairs; '
        f'rubric {m["rubric"]}; roles {", ".join(m["roles"])}')
    say(f'PROMPTS  {out / "prompts"}')
    return 0


def _add(it, review, rub, reviewer=None):
    review = reviews.validate(review, rub, reviewer)
    path = reviews.store(it, review)
    return review, path


def cmd_add(args):
    it = store.open_iteration(args.iteration)
    rub = _rubric_of(it, args.rubric)
    text = Path(args.file).read_text() if args.file != '-' else sys.stdin.read()
    try:
        review = reviews.extract_json(text)
        review, path = _add(it, review, rub, args.reviewer)
    except reviews.ReviewError as e:
        say(f'REVIEW INVALID {e}')
        return 1
    say(f'REVIEW   {review["reviewer"]}: ' + ', '.join(f'{k} {v}' for k, v in review['scores'].items()) + f' -> {path}')
    return 0


def run_reviews(it, rub, roles=None, model=None, say=say):
    """Runs each role's prompt through agents.ask and stores the valid reviews; returns (stored, failed)."""
    out = it.review / 'packet'
    manifest_file = out / 'packet.json'
    if not manifest_file.exists() or json.loads(manifest_file.read_text())['rubric'] != rub['name']:
        packet.build(it, rub['path'], ','.join(roles) if roles else None, say=say)
    manifest = json.loads(manifest_file.read_text())
    stored, failed = [], []
    for rid in roles or manifest['roles']:
        prompt_file = out / 'prompts' / f'{rid}.md'
        if not prompt_file.exists():
            metrics = json.loads((out / 'metrics.json').read_text())
            prompt_file.write_text(prompts.prompt(rub, rid, manifest, metrics, out))
        images = [out / f for f in prompts.images_for(rub, rid, manifest)]
        say(f'  reviewing as {rid} ({len(images)} images, {agents.backend()}, {agents.model_name(model)})')
        reply = ''
        for attempt in range(2):
            try:
                reply = agents.ask(prompt_file.read_text() + ('' if not attempt else f'\n\nYour last answer was rejected: {error}. Answer again.'),
                                   images, prompts.schema(rub, rid), model)
                review = reviews.extract_json(reply)
                review.setdefault('model', agents.model_name(model))
                review, path = _add(it, review, rub, rid)
                stored.append(review)
                say(f'  {rid}: ' + ', '.join(f'{k} {v}' for k, v in review['scores'].items()))
                break
            except (agents.AgentError, reviews.ReviewError) as e:
                error = str(e)[:400]
                (it.review / f'{rid}.reply.txt').write_text(reply or error)
        else:
            failed.append((rid, error))
            say(f'  {rid}: FAILED {error}')
    return stored, failed


def cmd_run(args):
    it = store.open_iteration(args.iteration)
    if not agents.backend():
        say('No reviewer available: put the `claude` CLI on PATH or set ANTHROPIC_API_KEY (or write reviews and `review add`)')
        return 2
    rub = _rubric_of(it, args.rubric)
    roles = [r.strip() for r in args.reviewers.split(',')] if args.reviewers else None
    stored, failed = run_reviews(it, rub, roles, args.model)
    code = cmd_score(args) if stored else 1
    return 1 if failed else code


def score(it, rub, roles=None):
    found = [r for r in reviews.load_all(it, rub['name']) if not roles or r['reviewer'] in roles]
    result = reviews.aggregate(found, rub)
    (it.path / 'score.json').write_text(json.dumps(result, indent=2) + '\n')
    store.update_index(it.path.parent)
    return result


def cmd_score(args):
    it = store.open_iteration(args.iteration)
    rub = _rubric_of(it, getattr(args, 'rubric', None))
    s = score(it, rub)
    if not s['reviewers']:
        say(f'No reviews for rubric {rub["name"]} in {it.review}')
        return 2
    say(f'SCORE    {"PASS" if s["pass"] else "FAIL"} average {s["average"]} minimum {s["minimum"]} ({len(s["reviewers"])} reviewers, rubric {s["rubric"]})')
    say('         ' + '  '.join(f'{k} {v}' for k, v in s['criteria'].items()))
    if s['reasons']:
        say('         ' + '; '.join(s['reasons']))
    say(f'FILE     {it.path / "score.json"}')
    return 0 if s['pass'] else 1


def _guard(fn):
    def run(args):
        try:
            return fn(args)
        except (rubrics.RubricError, reviews.ReviewError) as e:
            say(f'REVIEW ERROR {e}')
            return 2
    return run


def register(sub):
    p = sub.add_parser('review', help='review packets, reviews and scores (docs/REVIEW.md)')
    rs = p.add_subparsers(dest='review_command', required=True)
    q = rs.add_parser('packet', help='write review/packet/: strips, contact sheets, cut pairs, captions, prompts')
    q.add_argument('iteration')
    q.add_argument('--rubric', help='a rubric file or name (default docs/REVIEW.md, the general rubric)')
    q.add_argument('--reviewers', help='comma-separated roles (default: every role in the rubric)')
    q.add_argument('--every', type=int, help='strip every n-th frame (default: about 12 frames a strip)')
    q.set_defaults(run=_guard(cmd_packet))
    q = rs.add_parser('add', help='validate and store a review (a JSON file, or a reply ending in a ```json block; - for stdin)')
    q.add_argument('iteration')
    q.add_argument('file')
    q.add_argument('--reviewer', help='the role, if the JSON does not say')
    q.add_argument('--rubric')
    q.set_defaults(run=_guard(cmd_add))
    q = rs.add_parser('run', help='run every reviewer role through `claude -p` or the Anthropic API, then score')
    q.add_argument('iteration')
    q.add_argument('--rubric')
    q.add_argument('--reviewers')
    q.add_argument('--model', help=f'default {agents.DEFAULT_MODEL} (or VIDEOCRAFT_MODEL)')
    q.set_defaults(run=_guard(cmd_run))
    p = sub.add_parser('score', help='aggregate review/*.json into score.json (pass rule from the rubric)')
    p.add_argument('iteration')
    p.add_argument('--rubric')
    p.set_defaults(run=_guard(cmd_score))
