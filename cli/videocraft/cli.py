"""videocraft: agent-directed video for Minecraft Java.

  videocraft doctor                         is this machine ready (JDK 25, ffmpeg, folders, ports)
  videocraft compile <script.toml>          check a script and print the plan the mod would play
  videocraft run <script.toml> [--show]     take → cut → measure, as a new iteration under runs/<name>/
  videocraft cut <iteration>                re-cut an iteration (`<name>`, `<name>/<n>` or a path)
  videocraft measure <iteration>            re-measure an iteration
  videocraft runs <name>                    the iterations of a script and their verdicts
  videocraft status | stop                  this checkout's client, over its control port

Takes run in parallel across checkouts: each holds one of three machine-wide slots (control ports 25750-25752)
and waits for a free one when all three are busy. One client per checkout.

Exit codes: 0 PASS, 1 FAIL (a verdict), 2 no verdict (build error, timeout, crash, not implemented).
"""
import argparse
import importlib
import json
import sys
import time
from pathlib import Path

from videocraft import __version__, game, script, store
from videocraft.paths import PORT_OVERRIDE, SLOT_PORTS

NOT_YET = {'review': 'd'}  # placeholders for commands a missing group would provide
# Optional command groups: videocraft.<name>.commands with register(subparsers), loaded after the built-ins. A new
# command lives in its own subpackage's commands.py, so parallel work does not collide in this file.
GROUPS = ('edit', 'audio', 'voice', 'sets', 'story', 'review', 'series', 'clips')


def say(text=''):
    print(text, flush=True)


def cmd_doctor(args):
    from videocraft.doctor import doctor
    return doctor(args)


def _compile(path):
    try:
        return script.compile_script(script.load(path), str(path))
    except script.ScriptError as e:
        say(f'SCRIPT ERROR {e}')
        return None


def cmd_compile(args):
    compiled = _compile(args.script)
    if not compiled:
        return 1
    plan, edit = compiled
    say(json.dumps({'plan': plan, 'edit': edit}, indent=2))
    return 0


def run_take(path, parent=None, show=False, timeout=900, window=None, port=None, slot_wait=1800, no_cut=False, keep_world=False):
    """One iteration: lint, take, cut, measure. Returns (iteration or None, exit code: 0 PASS, 1 FAIL, 2 no verdict)."""
    compiled = _compile(path)
    if not compiled:
        return None, 1
    plan, edit = compiled
    if port is not None:
        game.check_port(port)  # before an iteration is made for a take that cannot start
    it = store.new_iteration(path, plan, edit, parent=parent)
    from videocraft import lint
    problems = lint.lint(script.load(path))
    lint.write(it, problems)
    counts, lines = lint.report(problems)
    say(f'videocraft {__version__}: {plan["name"]} iteration {it.name}, {len(plan["shots"])} shot(s), '
        f'{plan["output"]["width"]}x{plan["output"]["height"]} {plan["output"]["fps"]} fps, hidden' + (' (shown)' if show else ''))
    if counts['error'] or counts['warn']:
        say(f'  lint: {counts["error"]} error(s), {counts["warn"]} warning(s) (lint.json)')
        for line in lines[:8]:
            if not line.startswith('INFO'):
                say('    ' + line)
    started = time.time()
    window = tuple(int(v) for v in window.lower().split('x')) if window else None

    def echo(line):
        if 'VIDEOCRAFT ' in line and ('RESULT' in line or 'shot ' in line or 'step ' in line or 'world ' in line) or 'FAILURE' in line or 'error:' in line:
            say('  ' + line[line.find('VIDEOCRAFT') if 'VIDEOCRAFT' in line else 0:])

    try:
        result, code, seconds = game.play(it.take, show=show, timeout=timeout, window=window, port=port,
                                          slot_wait=slot_wait, on_line=echo, say=say)
    except SystemExit as e:
        if not isinstance(e.code, str):
            raise
        return it, _report(it, None, f'no verdict: {e.code}', started)
    if result and plan['world']['save'] is None and not keep_world:
        game.discard_world(result.get('level'))
    if result is None:
        return it, _report(it, None, f'no verdict: the client exited ({code}) without a result; see {it.take / "game.log"}', started)
    if result['verdict'] != 'PASS':
        return it, _report(it, False, result.get('reason', 'FAIL'), started)
    if no_cut:
        return it, _report(it, True, 'take only (--no-cut)', started)
    from videocraft.edit.cut import cut
    from videocraft.measure import measure
    master = cut(it)
    metrics = measure(it)
    m = metrics['master']
    detail = f'{m["width"]}x{m["height"]} {m["fps"]:g} fps {m["frames"]} frames {m["seconds"]:.2f} s; capture {result.get("captureFps", 0):.1f} fps real time'
    failed = [k for k, v in metrics['checks'].items() if not v]
    return it, _report(it, not failed, detail + (f'; checks failed: {", ".join(failed)}' if failed else ''), started, master)


def cmd_run(args):
    it, code = run_take(args.script, args.parent, args.show, args.timeout, args.window, args.port, args.slot_wait, args.no_cut, args.keep_world)
    return code


def _report(it, verdict, detail, started, video=None):
    word = 'PASS' if verdict else 'FAIL' if verdict is False else 'NONE'
    say(f'RESULT   {word} {detail}')
    if video:
        say(f'VIDEO    {video}')
    say(f'RUN      {it.path}')
    say(f'LOG      {it.take / "game.log"}')
    say(f'TIME     {time.time() - started:.0f} s')
    store.update_index(it.path.parent)
    return 0 if verdict else 1 if verdict is False else 2


def cmd_cut(args):
    from videocraft.edit.cut import cut
    say(str(cut(store.open_iteration(args.iteration))))
    return 0


def cmd_measure(args):
    from videocraft import measure
    if args.video:
        out = args.out or 'measure'
        metrics = measure.measure_video(args.video, args.start, args.end, out)
        say((Path(out) / 'report.md').read_text())
        say(f'METRICS  {Path(out).resolve() / "metrics.json"}')
        return 0
    if not args.iteration:
        say('measure needs an iteration (`<name>`, `<name>/<n>` or a path) or --video <file>')
        return 2
    it = store.open_iteration(args.iteration)
    metrics = measure.measure(it)
    say((it.measure / 'report.md').read_text())
    say(f'METRICS  {it.measure / "metrics.json"}')
    return 0 if metrics['pass'] else 1


def cmd_runs(args):
    its = store.iterations(args.name)
    if not its:
        say(f'No iterations of {args.name} in {store.RUNS / args.name}')
        return 1
    index = store.update_index(its[0].path.parent)
    say(f'{"it":4}  {"take":4}  {"score":>5}  {"min":>4}  {"pass":5}  {"shots":>5}  {"median":>6}  {"parent":6}  created')
    for row in index['iterations']:
        fmt = lambda v, spec: format(v, spec) if isinstance(v, (int, float)) else '-'
        say(f'{row["iteration"]}  {row["verdict"] or "-":4}  {fmt(row["score"], "5.2f"):>5}  {fmt(row["minimum"], "4.1f"):>4}  '
            f'{str(row["pass"]) if row["pass"] is not None else "-":5}  {fmt(row["shots"], "d"):>5}  {fmt(row["medianShot"], "6.2f"):>6}  '
            f'{row["parent"] or "-":6}  {row["created"]}' + ('  *' if row['iteration'] == index['best'] else '') + (f'  {row["reason"]}' if row['reason'] else ''))
    say(f'best {index["best"] or "-"} (highest scored passing take); INDEX {its[0].path.parent / "index.json"}')
    return 0


def cmd_lint(args):
    from videocraft import lint
    try:
        raw = script.load(args.script)
    except script.ScriptError as e:
        say(f'SCRIPT ERROR {e}')
        return 1
    rub = None
    if args.rubric:
        from videocraft.review import rubric
        rub = rubric.load(args.rubric)
    problems = lint.lint(raw, rub)
    counts, lines = lint.report(problems)
    for line in lines:
        if args.all or not line.startswith('INFO'):
            say(line)
    compiled = _compile(args.script) if not counts['error'] else None
    say(f'LINT     {counts["error"]} error(s), {counts["warn"]} warning(s), {counts["info"]} note(s)' + ('' if compiled or counts['error'] else ' (and it does not compile)'))
    return 1 if counts['error'] or not compiled else 0


def cmd_compare(args):
    from videocraft.compare import compare
    out, data = compare(store.open_iteration(args.a), store.open_iteration(args.b))
    say((out / 'compare.md').read_text())
    say(f'COMPARE  {out}')
    return 0


def cmd_notes(args):
    it = store.open_iteration(args.iteration)
    path = it.path / 'notes.md'
    if args.text:
        path.write_text(' '.join(args.text).strip() + '\n' if not path.exists() else path.read_text() + ' '.join(args.text).strip() + '\n')
        store.update_index(it.path.parent)
    say(path.read_text() if path.exists() else f'No notes in {it.path}')
    return 0


def cmd_climb(args):
    from videocraft import agents, climb
    from videocraft.review import commands as review
    if not agents.backend():
        say('climb needs a model: put the `claude` CLI on PATH or set ANTHROPIC_API_KEY')
        return 2

    def take(path, parent):
        return run_take(path, parent, timeout=args.timeout, slot_wait=args.slot_wait)

    def judge(it, rub, roles):
        review.run_reviews(it, rub, roles, args.model)
        return review.score(it, rub)

    log = climb.climb(args.script, args.budget, args.rubric, args.reviewers, args.model, take, judge, say)
    say(f'CLIMB    best {log.get("best")} average {log.get("best_average")} after {log.get("spent", 0)} take(s)' + (f'; stopped: {log["stopped"]}' if log.get('stopped') else ''))
    say(f'LOG      {store.RUNS / script.compile_script(script.load(args.script))[0]["name"] / "climb.json"}')
    return 0 if log.get('best') else 1


def cmd_modpack(args):
    from videocraft import modpack
    try:
        target, data = modpack.build(args.pack, args.jar, args.out)
    except (modpack.PackError, OSError) as e:
        say(f'MODPACK ERROR {e}')
        return 1
    say(f'MODPACK  {target} ({len(data["files"])} mods from Modrinth + the videocraft jar; Minecraft {data["dependencies"]["minecraft"]}, Fabric Loader {data["dependencies"]["fabric-loader"]})')
    return 0


def _target(args):
    """(pid or None, port or None): this checkout's client, or the client on an explicit --port / VIDEOCRAFT_PORT.
    Without either, nothing: never guess a port, it may be another checkout's client."""
    client = game.running()
    port = args.port if args.port is not None else PORT_OVERRIDE
    if port is None:
        return client if client else (None, None)
    game.check_port(port)
    return (client[0] if client and client[1] == port else None), port


def cmd_status(args):
    pid, port = _target(args)
    if port is None:
        say('No client running in this checkout (--port <n> asks another one)')
        return 1
    try:
        say(json.dumps(game.control('/status', port=port)))
        return 0
    except OSError:
        say(f'No client answers on 127.0.0.1:{port}' + (f' (pid {pid} is running; still starting?)' if pid else ''))
        return 1


def cmd_stop(args):
    pid, port = _target(args)
    if port is None:
        say('No client running in this checkout')
        return 0
    try:
        game.control('/quit', 'POST', port=port)
        say(f'Asked the client on port {port} to quit')
    except OSError:
        if pid:
            game.kill_tree(pid)
            say(f'Stopped pid {pid}')
        else:
            say(f'No client answers on port {port}')
    return 0


def not_yet(name):
    def run(args):
        say(f'`videocraft {name}` is not implemented yet (workstream {NOT_YET[name]}, docs/DESIGN.md)')
        return 2
    return run


def load_groups(sub, groups=None):
    """Calls register(sub) of every group that exists. A missing group is skipped; a broken one is reported (stderr)
    and skipped, so one group's bug does not take down every command."""
    for name in GROUPS if groups is None else groups:
        module_name = f'videocraft.{name}.commands'
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as e:
            if e.name in (f'videocraft.{name}', module_name):
                continue
            print(f'videocraft: command group {name} failed to load: {e!r}', file=sys.stderr)
            continue
        except Exception as e:
            print(f'videocraft: command group {name} failed to load: {e!r}', file=sys.stderr)
            continue
        register = getattr(module, 'register', None)
        if not callable(register):
            continue
        try:
            register(sub)
        except Exception as e:
            print(f'videocraft: command group {name} failed to register: {e!r}', file=sys.stderr)


def build_parser():
    parser = argparse.ArgumentParser(prog='videocraft', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--version', action='version', version=f'videocraft {__version__}')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('doctor').set_defaults(run=cmd_doctor)
    p = sub.add_parser('compile')
    p.add_argument('script')
    p.set_defaults(run=cmd_compile)
    p = sub.add_parser('run')
    p.add_argument('script')
    p.add_argument('--show', action='store_true', help='open a window (still without taking focus)')
    p.add_argument('--timeout', type=int, default=900, help='seconds before the client is stopped (default 900)')
    p.add_argument('--window', help='window size in points, WxH (default: 960x540 on a Mac, 1920x1080 elsewhere)')
    p.add_argument('--port', type=int, help=f'control port, skipping the slot choice (default: the first free slot, '
                   f'{SLOT_PORTS[0]}-{SLOT_PORTS[-1]})')
    p.add_argument('--slot-wait', type=float, default=1800, help='seconds to wait for a free slot when all three are busy (default 1800)')
    p.add_argument('--parent', help='the iteration this one improves on (for the hill-climb)')
    p.add_argument('--no-cut', action='store_true', help='take only')
    p.add_argument('--keep-world', action='store_true', help='keep the world a seed created (in run-game/saves)')
    p.set_defaults(run=cmd_run)
    p = sub.add_parser('cut')
    p.add_argument('iteration')
    p.set_defaults(run=cmd_cut)
    p = sub.add_parser('measure', help='measure an iteration, or any video file with --video')
    p.add_argument('iteration', nargs='?')
    p.add_argument('--video', help='measure this video file instead of an iteration')
    p.add_argument('--from', dest='start', type=float, help='with --video: start of the stretch, seconds')
    p.add_argument('--to', dest='end', type=float, help='with --video: end of the stretch, seconds')
    p.add_argument('--out', help='with --video: folder for metrics.json and report.md (default ./measure)')
    p.set_defaults(run=cmd_measure)
    p = sub.add_parser('runs', help='the iterations of a script: take verdicts, scores, parents')
    p.add_argument('name')
    p.set_defaults(run=cmd_runs)
    p = sub.add_parser('lint', help='problems in a script before a take (all of them)')
    p.add_argument('script')
    p.add_argument('--rubric', help='also check the rubric\'s limits (e.g. pinksheep-style: shots at most 7.5 s)')
    p.add_argument('--all', action='store_true', help='also print notes (info)')
    p.set_defaults(run=cmd_lint)
    p = sub.add_parser('compare', help='scores, measured deltas and the same shots side by side, into <b>/compare/')
    p.add_argument('a')
    p.add_argument('b')
    p.set_defaults(run=cmd_compare)
    p = sub.add_parser('notes', help='show (or append to) an iteration\'s notes.md')
    p.add_argument('iteration')
    p.add_argument('text', nargs='*')
    p.set_defaults(run=cmd_notes)
    p = sub.add_parser('climb', help='hill-climb a script: propose, run with --parent, review, keep if better')
    p.add_argument('script')
    p.add_argument('--budget', type=int, default=3, help='takes to spend, the first included (default 3)')
    p.add_argument('--rubric', help='default docs/REVIEW.md (general); e.g. pinksheep-style')
    p.add_argument('--reviewers', help='comma-separated roles (default: all of the rubric\'s)')
    p.add_argument('--model', help='for proposals and reviews (default claude-opus-5-5)')
    p.add_argument('--timeout', type=int, default=900)
    p.add_argument('--slot-wait', type=float, default=1800)
    p.set_defaults(run=cmd_climb)
    p = sub.add_parser('modpack', help='modpack/pack.toml → build/modpack/<name>-<version>.mrpack')
    p.add_argument('--pack', help='default modpack/pack.toml')
    p.add_argument('--jar', help='default the newest build/libs/videocraft-*.jar')
    p.add_argument('--out', help='default build/modpack/')
    p.set_defaults(run=cmd_modpack)
    for name, fn in (('status', cmd_status), ('stop', cmd_stop)):
        p = sub.add_parser(name)
        p.add_argument('--port', type=int, help="another client's control port (default: this checkout's client)")
        p.set_defaults(run=fn)
    load_groups(sub)
    for name in NOT_YET:
        if name not in sub.choices:  # a group that implements it replaces the placeholder
            sub.add_parser(name).set_defaults(run=not_yet(name))
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.run(args)
