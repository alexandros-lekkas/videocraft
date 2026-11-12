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

NOT_YET = {'lint': 'd', 'review': 'd', 'climb': 'd', 'modpack': 'd'}
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


def cmd_run(args):
    compiled = _compile(args.script)
    if not compiled:
        return 1
    plan, edit = compiled
    if args.port is not None:
        game.check_port(args.port)  # before an iteration is made for a take that cannot start
    it = store.new_iteration(args.script, plan, edit, parent=args.parent)
    say(f'videocraft {__version__}: {plan["name"]} iteration {it.name}, {len(plan["shots"])} shot(s), '
        f'{plan["output"]["width"]}x{plan["output"]["height"]} {plan["output"]["fps"]} fps, hidden' + (' (shown)' if args.show else ''))
    started = time.time()
    window = tuple(int(v) for v in args.window.lower().split('x')) if args.window else None

    def echo(line):
        if 'VIDEOCRAFT ' in line and ('RESULT' in line or 'shot ' in line or 'step ' in line or 'world ' in line) or 'FAILURE' in line or 'error:' in line:
            say('  ' + line[line.find('VIDEOCRAFT') if 'VIDEOCRAFT' in line else 0:])

    try:
        result, code, seconds = game.play(it.take, show=args.show, timeout=args.timeout, window=window, port=args.port,
                                          slot_wait=args.slot_wait, on_line=echo, say=say)
    except SystemExit as e:
        if not isinstance(e.code, str):
            raise
        return _report(it, None, f'no verdict: {e.code}', started)
    if result and plan['world']['save'] is None and not args.keep_world:
        game.discard_world(result.get('level'))
    if result is None:
        return _report(it, None, f'no verdict: the client exited ({code}) without a result; see {it.take / "game.log"}', started)
    if result['verdict'] != 'PASS':
        return _report(it, False, result.get('reason', 'FAIL'), started)
    if args.no_cut:
        return _report(it, True, 'take only (--no-cut)', started)
    from videocraft.edit.cut import cut
    from videocraft.measure import measure
    master = cut(it)
    metrics = measure(it)
    m = metrics['master']
    detail = f'{m["width"]}x{m["height"]} {m["fps"]:g} fps {m["frames"]} frames {m["seconds"]:.2f} s; capture {result.get("captureFps", 0):.1f} fps real time'
    failed = [k for k, v in metrics['checks'].items() if not v]
    return _report(it, not failed, detail + (f'; checks failed: {", ".join(failed)}' if failed else ''), started, master)


def _report(it, verdict, detail, started, video=None):
    word = 'PASS' if verdict else 'FAIL' if verdict is False else 'NONE'
    say(f'RESULT   {word} {detail}')
    if video:
        say(f'VIDEO    {video}')
    say(f'RUN      {it.path}')
    say(f'LOG      {it.take / "game.log"}')
    say(f'TIME     {time.time() - started:.0f} s')
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
    for it in store.iterations(args.name):
        r = it.result() or {}
        meta = it.meta()
        say(f'{it.name}  {r.get("verdict", "-"):4}  {meta["created"]}  parent {meta.get("parent") or "-":5}  {r.get("reason", "")}')
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
    p = sub.add_parser('runs')
    p.add_argument('name')
    p.set_defaults(run=cmd_runs)
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
