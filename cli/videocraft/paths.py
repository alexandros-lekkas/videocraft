"""Where everything lives. The game only ever runs in GAME_DIR; never in a real Minecraft folder."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GAME_DIR = Path(os.environ.get('VIDEOCRAFT_GAME_DIR') or ROOT / 'run-game')
RUNS = Path(os.environ.get('VIDEOCRAFT_RUNS') or ROOT / 'runs')
CONTROL_PORT = int(os.environ.get('VIDEOCRAFT_PORT') or 25750)
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
