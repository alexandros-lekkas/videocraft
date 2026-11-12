"""`videocraft story ...` and `videocraft make "<prompt>"` (docs/STORY.md).

  story new "<premise>" [--id ID] [--format short|episode|long] [--vertical] [--from-file premise.md] [--through STAGE]
  story draft <stage> <story> [--note "…"] [--from-file F] [--no-lock]   regenerate a stage from the stages before it
  story revise <stage> <story> --note "…" [--from-file F]                a new revision with the note applied
  story build <story> [--from-file shots.toml]                           shots.toml: compile + lint, up to 3 repairs
  story diff <story> <stage> [r1 r2]   story show <story> [stage] [--rev N]   story lock <story> <stage> <rev>
  story list
  make "<prompt>" [--format …] [--vertical] [--dry-run] [--id ID]        prompt → … → shots.toml → run → cut

Exit codes: 0 done, 1 a stage did not pass its checks (the problems are printed), 2 no model or a usage error.
"""
import difflib
import sys

from videocraft.story import stages
from videocraft.story._ask import AskError
from videocraft.story.store import FILES, FORMATS, STAGES, Store, StoryError, slug


def say(text=''):
    print(text, flush=True)


def _report(outcome, store, sid):
    o = outcome
    state = 'locked' if o.locked else 'kept' if o.ok else 'FAILED'
    say(f'STAGE    {o.stage} r{o.rev} {state}' + (f' after {o.attempts} attempt(s)' if o.attempts > 1 else ''))
    for p in o.problems:
        say(f'  - {p}')
    if o.ok:
        say(f'FILE     {store.path(sid, o.stage) if o.locked else store.revision_path(sid, o.stage, o.rev)}')
    return 0 if o.ok else 1


def _guarded(fn):
    def run(args):
        try:
            return fn(args, Store())
        except StoryError as e:
            say(f'STORY ERROR {e}')
            return 2
        except AskError as e:
            say(f'MODEL ERROR {e}')
            return 2
    return run


def _unique_id(store, base):
    sid, n = base[:48].strip('-'), 2
    while store.exists(sid):
        sid = f'{base[:44].strip("-")}-{n}'
        n += 1
    return sid


def _through(args, store, sid, first, last):
    """Runs stages first..last (inclusive) in order; stops at the first that fails."""
    for stage in STAGES[STAGES.index(first):STAGES.index(last) + 1]:
        o = stages.run_stage(store, sid, stage, lock=not getattr(args, 'no_lock', False), say=say)
        code = _report(o, store, sid)
        if code:
            say(f'STOPPED  at {stage}: fix it with `story revise {stage} {sid} --note "…"` or `--from-file`')
            return code
    return 0


@_guarded
def cmd_new(args, store):
    sid = args.id or _unique_id(store, slug(args.premise))
    store.create(sid, fmt=args.format, vertical=args.vertical, request=args.premise, reference=args.reference)
    say(f'STORY    {sid} ({args.format}{", 9:16" if args.vertical else ""}) in {store.story_dir(sid)}')
    extra = f'Reference form: {args.reference}' if args.reference else ''
    o = stages.run_stage(store, sid, 'premise', from_file=args.from_file, lock=not args.no_lock, say=say,
                         request=args.premise if not extra else f'{args.premise}\n{extra}')
    code = _report(o, store, sid)
    if code or not args.through or args.through == 'premise':
        return code
    return _through(args, store, sid, 'bible', args.through)


@_guarded
def cmd_draft(args, store):
    o = stages.run_stage(store, args.story, args.stage, note=args.note, from_file=args.from_file,
                         lock=not args.no_lock, repairs=args.repairs, say=say)
    return _report(o, store, args.story)


@_guarded
def cmd_revise(args, store):
    if not args.note and not args.from_file:
        raise StoryError('revise needs --note "<what to change>" (or --from-file with the revised file)')
    o = stages.run_stage(store, args.story, args.stage, note=args.note, from_file=args.from_file,
                         lock=not args.no_lock, repairs=args.repairs, say=say, revise=True)
    return _report(o, store, args.story)


@_guarded
def cmd_build(args, store):
    o = stages.run_stage(store, args.story, 'shots', note=args.note, from_file=args.from_file,
                         lock=not args.no_lock, repairs=args.repairs, say=say)
    code = _report(o, store, args.story)
    if not code:
        plan = store.revision_path(args.story, 'shots', o.rev).with_suffix('.plan.json')
        say(f'PLAN     {plan}')
        say(f'NEXT     bin/videocraft run {store.path(args.story, "shots")}')
    return code


@_guarded
def cmd_diff(args, store):
    revs = [r['rev'] for r in store.revisions(args.story, args.stage)]
    if args.r1 is None:
        if len(revs) < 2:
            raise StoryError(f'{args.story} {args.stage} has {len(revs)} revision(s); nothing to compare')
        r1, r2 = revs[-2], revs[-1]
    else:
        r1, r2 = args.r1, args.r2 if args.r2 is not None else revs[-1]
    a, b = store.text(args.story, args.stage, r1), store.text(args.story, args.stage, r2)
    out = difflib.unified_diff(a.splitlines(True), b.splitlines(True), f'{args.stage} r{r1}', f'{args.stage} r{r2}')
    sys.stdout.writelines(out)
    return 0


@_guarded
def cmd_show(args, store):
    meta = store.meta(args.story)
    if args.stage:
        text = store.text(args.story, args.stage, args.rev)
        if text is None:
            raise StoryError(f'{args.story} has no {args.stage} yet')
        sys.stdout.write(text)
        return 0
    say(f'STORY    {meta["id"]}  {meta["format"]}{"  9:16" if meta.get("vertical") else ""}'
        + (f'  episode {meta["episode"]} of {meta["series"]}' if meta.get('series') else '')
        + (f'  series of {len(meta["episodes"])}' if meta.get('episodes') else ''))
    for stage in STAGES:
        owner, _ = store.source_of(args.story, stage)
        if owner != args.story:
            say(f'  {stage:8} from {owner}')
            continue
        revs = store.revisions(args.story, stage)
        cur, locked = store.current(args.story, stage), store.locked(args.story, stage)
        if not revs:
            say(f'  {stage:8} -')
            continue
        stale = store.stale(args.story, stage)
        say(f'  {stage:8} r{cur}{" locked" if locked == cur else ""}  {len(revs)} revision(s)'
            + (f'  STALE: {", ".join(stale)} changed since' if stale else '') + f'  {store.path(args.story, stage)}')
    return 0


@_guarded
def cmd_lock(args, store):
    store.lock(args.story, args.stage, args.rev)
    say(f'LOCKED   {args.story} {args.stage} r{args.rev} → {store.path(args.story, args.stage)}')
    return 0


@_guarded
def cmd_list(args, store):
    for sid in store.ids():
        meta = store.meta(sid)
        done = [s for s in STAGES if store.text(sid, s) is not None]
        say(f'{sid:32} {meta["format"]:8} {done[-1] if done else "-":8} {meta.get("request", "")[:60]}')
    return 0


@_guarded
def cmd_make(args, store):
    sid = args.id or _unique_id(store, slug(args.prompt))
    store.create(sid, fmt=args.format, vertical=args.vertical, request=args.prompt)
    say(f'STORY    {sid} ({args.format}{", 9:16" if args.vertical else ""})')
    o = stages.run_stage(store, sid, 'premise', say=say, request=args.prompt)
    code = _report(o, store, sid) or _through(args, store, sid, 'bible', 'shots')
    if code:
        say(f'RESULT   FAIL stopped before a take; story {sid}')
        return code
    shots = store.path(sid, 'shots')
    if args.dry_run:
        say(f'RESULT   PASS shots.toml compiles (--dry-run: no take)')
        say(f'SHOTS    {shots}')
        return 0
    from videocraft import cli
    return cli.main(['run', str(shots), '--timeout', str(args.timeout)])


def register(sub):
    p = sub.add_parser('story', help='premise → bible → outline → script → shots.toml (docs/STORY.md)',
                       description=__doc__, formatter_class=__import__('argparse').RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest='story_command', required=True)

    def lockable(q):
        q.add_argument('--from-file', help='lock in a hand-written draft instead of asking a model')
        q.add_argument('--no-lock', action='store_true', help='keep the revision without making it the chosen one')
        q.add_argument('--repairs', type=int, default=stages.REPAIRS, help='model repair rounds when checks fail (default 3)')

    q = s.add_parser('new', help='start a story from a premise')
    q.add_argument('premise')
    q.add_argument('--id', help='the story id (default: from the premise)')
    q.add_argument('--format', choices=sorted(FORMATS), default='short')
    q.add_argument('--vertical', action='store_true', help='9:16 (1080x1920)')
    q.add_argument('--reference', help='a form to borrow (e.g. "docs/benchmarks/pinksheep-style.md")')
    q.add_argument('--through', choices=STAGES, help='keep drafting through this stage')
    lockable(q)
    q.set_defaults(run=cmd_new)
    for name, fn, helptext in (('draft', cmd_draft, 'regenerate a stage from the stages before it'),
                               ('revise', cmd_revise, 'a new revision of a stage with a note applied')):
        q = s.add_parser(name, help=helptext)
        q.add_argument('stage', choices=STAGES)
        q.add_argument('story')
        q.add_argument('--note', help='what to change or emphasise')
        lockable(q)
        q.set_defaults(run=fn)
    q = s.add_parser('build', help='draft shots.toml and check it compiles (and lints), with repair rounds')
    q.add_argument('story')
    q.add_argument('--note')
    lockable(q)
    q.set_defaults(run=cmd_build)
    q = s.add_parser('diff', help='unified diff of two revisions (default: the last two)')
    q.add_argument('story')
    q.add_argument('stage', choices=STAGES)
    q.add_argument('r1', nargs='?', type=int)
    q.add_argument('r2', nargs='?', type=int)
    q.set_defaults(run=cmd_diff)
    q = s.add_parser('show', help='the stages of a story, or one stage\'s text')
    q.add_argument('story')
    q.add_argument('stage', nargs='?', choices=STAGES)
    q.add_argument('--rev', type=int)
    q.set_defaults(run=cmd_show)
    q = s.add_parser('lock', help='make a revision the chosen one (copied to stories/<id>/)')
    q.add_argument('story')
    q.add_argument('stage', choices=STAGES)
    q.add_argument('rev', type=int)
    q.set_defaults(run=cmd_lock)
    s.add_parser('list', help='every story in stories/').set_defaults(run=cmd_list)

    p = sub.add_parser('make', help='one prompt to a finished cut: premise → … → shots.toml → run → cut')
    p.add_argument('prompt')
    p.add_argument('--id')
    p.add_argument('--format', choices=sorted(FORMATS), default='short')
    p.add_argument('--vertical', action='store_true')
    p.add_argument('--dry-run', action='store_true', help='stop after shots.toml compiles')
    p.add_argument('--timeout', type=int, default=1800, help='seconds for the take (default 1800)')
    p.set_defaults(run=cmd_make)
