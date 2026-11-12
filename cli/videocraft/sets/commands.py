"""The `sets` command group:

  videocraft sets list                                 the sets in sets/, their time of day and marks
  videocraft sets build <name> [--at X Y Z] [--rotate R] [--commands FILE] [--json]
                                                       commands, counts, bounding box, marks, warnings
  videocraft sets preview <name> [--only TEXT …]       a take from every viewpoint → preview/contact.png
  videocraft sets new <name> --from-description "…"    a set file scaffolded by an agent (or the prompt for one)
  videocraft sets skin <spec.toml> -o skin.png         an original 64x64 player skin from a spec
"""
import json
import sys
from pathlib import Path

from . import SETS_DIR, SetError, build, listing, load, place


def say(text=''):
    print(text, flush=True)


def register(sub):
    p = sub.add_parser('sets', help='sets: places to film, built from data (docs/SETS.md)')
    s = p.add_subparsers(dest='sets_command', required=True)
    q = s.add_parser('list')
    q.set_defaults(run=cmd_list)
    q = s.add_parser('build')
    q.add_argument('name')
    q.add_argument('--at', nargs=3, type=int, default=[0, 160, 0], metavar=('X', 'Y', 'Z'))
    q.add_argument('--rotate', type=int, default=0)
    q.add_argument('--mirror', action='store_true')
    q.add_argument('--commands', help='write the commands to this file, one per line')
    q.add_argument('--json', action='store_true', help='the summary as JSON')
    q.set_defaults(run=cmd_build)
    q = s.add_parser('preview')
    q.add_argument('name')
    q.add_argument('--at', nargs=3, type=int, default=[0, 160, 0], metavar=('X', 'Y', 'Z'))
    q.add_argument('--rotate', type=int, default=0)
    q.add_argument('--only', nargs='*', help='only viewpoints whose name contains one of these')
    q.add_argument('--time', type=int, help='time of day (default: the set\'s own)')
    q.add_argument('--seed', default='videocraft', help='world seed (default videocraft)')
    q.add_argument('--timeout', type=int, default=900)
    q.add_argument('--dry-run', action='store_true', help='write the preview script and list the viewpoints only')
    q.set_defaults(run=cmd_preview)
    q = s.add_parser('new')
    q.add_argument('name')
    q.add_argument('--from-description', required=True, dest='description')
    q.add_argument('--force', action='store_true')
    q.set_defaults(run=cmd_new)
    q = s.add_parser('skin')
    q.add_argument('spec')
    q.add_argument('-o', '--out', required=True)
    q.set_defaults(run=cmd_skin)


def cmd_list(args):
    for s in listing():
        if 'error' in s:
            say(f'{s["name"]:<16} ERROR {s["error"]}')
        else:
            say(f'{s["name"]:<16} time {s["time"]!s:>6}  {s["marks"]:>3} marks  {s["description"]}')
    return 0


def cmd_build(args):
    try:
        built = build(load(args.name))
        placed = place(built, args.at, args.rotate, args.mirror)
    except SetError as e:
        say(f'SET ERROR {e}')
        return 1
    summary = placed.summary()
    if args.commands:
        Path(args.commands).write_text('\n'.join(placed.commands()) + '\n')
    if args.json:
        summary['anchors'] = placed.anchors(built.name)
        say(json.dumps(summary, indent=2))
        return 0
    c = summary['commands']
    say(f'SET      {built.name} at {summary["at"]} rotate {summary["rotate"]}{" mirrored" if args.mirror else ""}')
    say(f'BLOCKS   {summary["blocks"]} in {c["fill"]} fills and {c["setblock"]} setblocks; {summary["entities"]} entities; '
        f'{c["total"]} commands')
    say(f'BOX      {summary["box"]["from"]} to {summary["box"]["to"]} ({"x".join(map(str, summary["size"]))})')
    say(f'LOOK     time {summary["time"]}, {summary["weather"]}, biome {summary["biome"] or "(the world\'s)"}')
    kinds = {}
    for k, v in summary['marks'].items():
        kinds.setdefault(v, []).append(k)
    for kind in ('point', 'path', 'camera'):
        if kind in kinds:
            say(f'MARKS    {kind}: {", ".join(kinds[kind])}')
    for w in summary['warnings']:
        say(f'WARNING  {w}')
    if args.commands:
        say(f'COMMANDS {args.commands}')
    return 0


def cmd_preview(args):
    from . import preview
    from videocraft import cli, store
    try:
        raw, views = preview.script(args.name, tuple(args.at), args.rotate, args.seed, args.only, args.time)
    except SetError as e:
        say(f'SET ERROR {e}')
        return 1
    path = preview.preview_script_path(Path(args.name).stem)
    path.write_text(preview.to_toml(raw))
    for i, (n, v) in enumerate(views):
        say(f'VIEW     {i:02d} {n}  eye {[round(c, 1) for c in v["eye"]]} fov {v["fov"]:g}')
    say(f'SCRIPT   {path}')
    if args.dry_run:
        return 0
    code = cli.main(['run', str(path), '--no-cut', '--timeout', str(args.timeout)])
    it = store.open_iteration(raw['name'])
    from videocraft import tools
    sheet = preview.contact(it.path, views, tools.ffmpeg() or 'ffmpeg')
    say(f'CONTACT  {sheet}' if sheet else 'CONTACT  none (no frames)')
    say(f'FRAMES   {it.path / "preview"}')
    return code


SCHEMA_HINT = """A set file is TOML (docs/SETS.md): name, description, time (ticks), biome, seed, then [[build]] entries
run in order (later wins), each with `do` = one of: {ops}; then [[mark]] entries: points (`at`, `facing`), paths
(`path` or `along` a lane mark with `from`/`to` in blocks), cameras (`eye`, `look`, `fov`). Coordinates are the set's
own: x east, y up, z south; the ground's top layer is y = -1 and feet stand at y = 0. Make it a self-contained island:
a ground plate, a backdrop ring so a camera one block up with a 105-degree lens never sees an edge, and marks for
every place a shot will happen. Only vanilla blocks. Answer with the TOML file only."""


def cmd_new(args):
    from .ops import OPS
    out = SETS_DIR / f'{args.name}.toml'
    if out.exists() and not args.force:
        say(f'SET ERROR {out} exists (use --force to replace it)')
        return 1
    example = (SETS_DIR / 'black-stage.toml').read_text() if (SETS_DIR / 'black-stage.toml').exists() else ''
    prompt = (f'Write a videocraft set file named "{args.name}" for this description:\n\n{args.description}\n\n'
              + SCHEMA_HINT.format(ops=', '.join(sorted(OPS))) + '\n\nA small complete example:\n\n' + example)
    try:
        from videocraft import agents  # the CLI workstream's model call, when it exists
    except ImportError:
        agents = None
    if agents is None or not hasattr(agents, 'ask'):
        say('No agent module (videocraft.agents) here; give this prompt to an agent and save its answer as')
        say(f'{out}, then run `videocraft sets build {args.name}`.\n')
        say(prompt)
        return 2
    text = agents.ask(prompt)
    text = text.strip()
    if text.startswith('```'):
        text = text.split('\n', 1)[1].rsplit('```', 1)[0]
    out.write_text(text.strip() + '\n')
    try:
        built = build(load(str(out)))
    except SetError as e:
        say(f'WROTE    {out}\nSET ERROR {e}\n(fix the file, or run again)')
        return 1
    say(f'WROTE    {out} ({len(built.grid)} blocks, {len(built.marks)} marks)')
    return 0


def cmd_skin(args):
    from .skin import SkinError, load_spec, write
    try:
        out = write(load_spec(args.spec), args.out)
    except SkinError as e:
        say(f'SKIN ERROR {e}')
        return 1
    say(f'SKIN     {out}')
    return 0


if __name__ == '__main__':
    sys.exit(0)
