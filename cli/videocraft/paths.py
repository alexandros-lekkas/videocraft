"""Where everything lives. The game only ever runs in GAME_DIR; never in a real Minecraft folder."""
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GAME_DIR = Path(os.environ.get('VIDEOCRAFT_GAME_DIR') or ROOT / 'run-game')
RUNS = Path(os.environ.get('VIDEOCRAFT_RUNS') or ROOT / 'runs')
# Control ports. A take holds one of three machine-wide slots; slot n uses port SLOT_PORTS[n] (game.acquire_slot).
SLOT_PORTS = (25750, 25751, 25752)
# Other tools on this machine: a real game's Minecraft MCP port, T3 Craft's ports. Never used, even when asked.
RESERVED_PORTS = frozenset([25590, 25611, *range(25680, 25691), 25720])
# VIDEOCRAFT_PORT pins the port like --port does (no slot choice).
PORT_OVERRIDE = int(os.environ['VIDEOCRAFT_PORT']) if os.environ.get('VIDEOCRAFT_PORT') else None
# The slot locks. Not tempfile.gettempdir(): a harness may give each agent its own TMPDIR, and every checkout of every
# agent on this machine must see the same three locks. Per user, so another account's takes are not counted.
SLOT_DIR = Path(os.environ.get('VIDEOCRAFT_SLOT_DIR') or (
    Path('/tmp') / f'videocraft-slots-{os.getuid()}' if os.name != 'nt' else Path(tempfile.gettempdir()) / 'videocraft-slots'))
# Real Minecraft folders: refuse to run a game in or under any of them.
REAL_MINECRAFT = [Path.home() / 'Library/Application Support/minecraft', Path.home() / '.minecraft',
                  Path(os.environ.get('APPDATA', '/nonexistent')) / '.minecraft']


def is_real_minecraft(path: Path) -> bool:
    path = path.resolve()
    for real in REAL_MINECRAFT:
        try:
            if path == real or path.is_relative_to(real) or path.name.startswith('minecraft') and path.parent == real.parent:
                return True
        except OSError:
            continue
    return False
