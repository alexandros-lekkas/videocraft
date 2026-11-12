"""`videocraft doctor`: is this machine ready to run a take? Every line says what it found and, if not, what to do."""
import subprocess
import sys
from pathlib import Path

from videocraft import game, tools
from videocraft.paths import GAME_DIR, PORT_OVERRIDE, ROOT, RUNS, SLOT_DIR, SLOT_PORTS, is_real_minecraft


def _line(ok, what, detail, required=True):
    mark = 'ok  ' if ok else ('FAIL' if required else 'warn')
    print(f'  {mark}  {what:<14} {detail}')
    return ok or not required


def _extras():
    """The pieces after the take: sound assets, the reviewers' model, then whatever each command group reports."""
    import json
    import os
    import shutil
    assets = Path.home() / '.gradle/caches/fabric-loom/assets'
    indexes = sorted((assets / 'indexes').glob('*.json')) if assets.exists() else []
    sounds = 0
    if indexes:
        try:
            objects = json.loads(indexes[-1].read_text()).get('objects', {})
            sounds = sum(1 for k in objects if k.startswith('minecraft/sounds/'))
        except (OSError, ValueError):
            pass
    _line(sounds > 0, 'game sounds', f'{sounds} sound files in {indexes[-1].name} (sound effects and music for the mix)' if sounds
          else 'no asset index with sounds yet: the first run downloads it; the mix needs it (or --silent)', required=False)
    cache = ROOT / 'cache'
    for name, what in (('audio', 'decoded sounds'), ('voice', 'voice tool')):
        d = cache / name
        _line(True, f'cache/{name}', f'{d} ({what}; git-ignored)' if d.exists() else f'{d} not made yet ({what}; made on first use)', required=False)
    venv = next((p for p in (cache / 'voice/venv/bin/python', cache / 'voice/.venv/bin/python', ROOT / '.venv-voice/bin/python') if p.exists()), None)
    _line(venv is not None, 'voice venv', str(venv) if venv else 'none: dialogue uses estimated reading timings (the voice group installs one)', required=False)
    claude = shutil.which('claude')
    key = bool(os.environ.get('ANTHROPIC_API_KEY'))
    from videocraft import agents
    _line(bool(claude or key), 'reviewers', (f'claude CLI {claude}' if claude else '') + (' and ' if claude and key else '')
          + ('ANTHROPIC_API_KEY set' if key else '') + (f'; model {agents.model_name()}' if claude or key else
          'no `claude` CLI and no ANTHROPIC_API_KEY: review run and climb are off (review add still works)'), required=False)
    _groups()


def _groups():
    """Each command group may define doctor() -> [(ok, what, detail)] in videocraft.<group>.commands or its package."""
    import importlib
    from videocraft.cli import GROUPS
    for name in GROUPS:
        for module_name in (f'videocraft.{name}', f'videocraft.{name}.commands'):
            try:
                module = importlib.import_module(module_name)
            except Exception:
                continue
            check = getattr(module, 'doctor', None)
            if callable(check):
                try:
                    for ok, what, detail in check() or []:
                        _line(ok, what, detail, required=False)
                except Exception as e:
                    _line(False, name, f'its doctor() failed: {e!r}', required=False)
                break


def doctor(args=None):
    print('videocraft doctor')
    good = True
    good &= _line(sys.version_info >= (3, 11), 'python', f'{sys.version.split()[0]} (3.11+ for tomllib)')
    jdk = tools.find_jdk()
    good &= _line(bool(jdk), 'jdk 25', jdk or 'not found: brew install openjdk@25 (a newer JDK cannot compile the build)')
    ffmpeg, ffprobe = tools.ffmpeg(), tools.ffprobe()
    good &= _line(bool(ffmpeg), 'ffmpeg', ffmpeg or 'not found: brew install ffmpeg')
    good &= _line(bool(ffprobe), 'ffprobe', ffprobe or 'not found (ships with ffmpeg)')
    if ffmpeg:
        filters = subprocess.run([ffmpeg, '-hide_banner', '-filters'], capture_output=True, text=True).stdout
        encoders = subprocess.run([ffmpeg, '-hide_banner', '-encoders'], capture_output=True, text=True).stdout
        good &= _line('libx264' in encoders, 'libx264', 'present' if 'libx264' in encoders else 'missing: the capture and the cut encode H.264 with it')
        _line(True, 'drawtext', ('present' if ' drawtext ' in filters else 'absent (expected: videocraft draws all text in game)'), required=False)
    good &= _line((ROOT / 'gradlew').exists(), 'gradle', str(ROOT / 'gradlew'))
    good &= _line(not is_real_minecraft(GAME_DIR), 'game dir', f'{GAME_DIR} (never a real Minecraft folder)')
    jars = sorted((ROOT / 'build/libs').glob('videocraft-*.jar'))
    _line(bool(jars), 'mod jar', str(jars[-1]) if jars else 'not built yet: ./gradlew build (bin/videocraft run builds it anyway)', required=False)
    assets = Path.home() / '.gradle/caches/fabric-loom/assets'
    _line(assets.exists(), 'game assets', f'{assets} (music for the edit is read from here, never committed)' if assets.exists()
          else 'not downloaded yet: the first run downloads them', required=False)
    client = game.running()
    _line(client is None, 'client', 'none running in this checkout' if client is None
          else f'pid {client[0]} on port {client[1]} is running: videocraft stop', required=False)
    free = 0
    for index, port in enumerate(SLOT_PORTS):
        holder = game.slot_holder(index)
        if holder:
            pid, _, checkout = holder.partition(' ')
            here = ' (this checkout)' if checkout == str(ROOT) else ''
            detail = f'{port} held by a take: pid {pid} in {checkout or "?"}{here}'
        elif not game.port_free(port):
            detail = f'{port} in use by something else (an older client without slots?); takes skip it'
        else:
            detail, free = f'{port} free', free + 1
        _line(True, f'slot {index}', detail, required=False)
    _line(free > 0, 'slots', f'{free} of {len(SLOT_PORTS)} free ({SLOT_DIR})' + ('' if free else '; a take waits for one'), required=False)
    _extras()
    if PORT_OVERRIDE is not None:
        _line(True, 'port', f'VIDEOCRAFT_PORT={PORT_OVERRIDE}: takes skip the slot choice', required=False)
    print(f'  runs in {RUNS}')
    print('READY' if good else 'NOT READY')
    return 0 if good else 1
