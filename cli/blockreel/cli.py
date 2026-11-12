"""blockreel: agent-directed video for Minecraft Java.

  blockreel doctor                         is this machine ready (JDK 25, ffmpeg, folders, ports)
  blockreel compile <script.toml>          check a script and print the plan the mod would play
  blockreel run <script.toml> [--show]     take → cut → measure, as a new iteration under runs/<name>/
  blockreel cut <iteration>                re-cut an iteration (`<name>`, `<name>/<n>` or a path)
  blockreel measure <iteration>            re-measure an iteration
  blockreel runs <name>                    the iterations of a script and their verdicts
  blockreel status | stop                  the running client, over the control port

Exit codes: 0 PASS, 1 FAIL (a verdict), 2 no verdict (build error, timeout, crash, not implemented).
"""
import argparse
import json
import sys
import time

from blockreel import __version__, game, script, store
from blockreel.paths import CONTROL_PORT

NOT_YET = {'lint': 'd', 'review': 'd', 'climb': 'd', 'modpack': 'd'}


def say(text=''):
    print(text, flush=True)


def cmd_doctor(args):
    from blockreel.doctor import doctor
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
    it = store.new_iteration(args.script, plan, edit, parent=args.parent)
    say(f'blockreel {__version__}: {plan["name"]} iteration {it.name}, {len(plan["shots"])} shot(s), '
        f'{plan["output"]["width"]}x{plan["output"]["height"]} {plan["output"]["fps"]} fps, hidden' + (' (shown)' if args.show else ''))
    started = time.time()
    window = tuple(int(v) for v in args.window.lower().split('x')) if args.window else None

    def echo(line):
        if 'BLOCKREEL ' in line and ('RESULT' in line or 'shot ' in line or 'step ' in line or 'world ' in line) or 'FAILURE' in line or 'error:' in line:
            say('  ' + line[line.find('BLOCKREEL') if 'BLOCKREEL' in line else 0:])

    result, code, seconds = game.play(it.take, show=args.show, timeout=args.timeout, window=window, port=args.port, on_line=echo)
    if result and plan['world']['save'] is None and not args.keep_world:
        game.discard_world(result.get('level'))
    if result is None:
        return _report(it, None, f'no verdict: the client exited ({code}) without a result; see {it.take / "game.log"}', started)
    if result['verdict'] != 'PASS':
        return _report(it, False, result.get('reason', 'FAIL'), started)
    if args.no_cut:
        return _report(it, True, 'take only (--no-cut)', started)
    from blockreel.edit.cut import cut
    from blockreel.measure import measure
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
    from blockreel.edit.cut import cut
    say(str(cut(store.open_iteration(args.iteration))))
    return 0


def cmd_measure(args):
    from blockreel.measure import measure
    metrics = measure(store.open_iteration(args.iteration))
    say(json.dumps(metrics, indent=2))
    return 0 if metrics['pass'] else 1


def cmd_runs(args):
    for it in store.iterations(args.name):
        r = it.result() or {}
        meta = it.meta()
        say(f'{it.name}  {r.get("verdict", "-"):4}  {meta["created"]}  parent {meta.get("parent") or "-":5}  {r.get("reason", "")}')
    return 0


def cmd_status(args):
    try:
        say(json.dumps(game.control('/status', port=args.port)))
        return 0
    except OSError:
        say(f'No client answers on 127.0.0.1:{args.port}')
        return 1


def cmd_stop(args):
    pid = game.running_pid()
    try:
        game.control('/quit', 'POST', port=args.port)
        say('Asked the client to quit')
    except OSError:
        if pid:
            game.kill_tree(pid)
            say(f'Stopped pid {pid}')
        else:
            say('No client running')
    return 0


def not_yet(name):
    def run(args):
        say(f'`blockreel {name}` is not implemented yet (workstream {NOT_YET[name]}, docs/DESIGN.md)')
        return 2
    return run


def main(argv=None):
    parser = argparse.ArgumentParser(prog='blockreel', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--version', action='version', version=f'blockreel {__version__}')
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
    p.add_argument('--port', type=int, default=CONTROL_PORT, help=f'control port (default {CONTROL_PORT})')
    p.add_argument('--parent', help='the iteration this one improves on (for the hill-climb)')
    p.add_argument('--no-cut', action='store_true', help='take only')
    p.add_argument('--keep-world', action='store_true', help='keep the world a seed created (in run-game/saves)')
    p.set_defaults(run=cmd_run)
    for name, fn in (('cut', cmd_cut), ('measure', cmd_measure)):
        p = sub.add_parser(name)
        p.add_argument('iteration')
        p.set_defaults(run=fn)
    p = sub.add_parser('runs')
    p.add_argument('name')
    p.set_defaults(run=cmd_runs)
    for name, fn in (('status', cmd_status), ('stop', cmd_stop)):
        p = sub.add_parser(name)
        p.add_argument('--port', type=int, default=CONTROL_PORT)
        p.set_defaults(run=fn)
    for name in NOT_YET:
        sub.add_parser(name).set_defaults(run=not_yet(name))
    args = parser.parse_args(argv)
    return args.run(args)
