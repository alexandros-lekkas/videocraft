"""`blockreel doctor`: is this machine ready to run a take? Every line says what it found and, if not, what to do."""
import socket
import subprocess
import sys
from pathlib import Path

from blockreel import game, tools
from blockreel.paths import CONTROL_PORT, GAME_DIR, ROOT, RUNS, is_real_minecraft


def _line(ok, what, detail, required=True):
    mark = 'ok  ' if ok else ('FAIL' if required else 'warn')
    print(f'  {mark}  {what:<14} {detail}')
    return ok or not required


def doctor(args=None):
    print('blockreel doctor')
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
        _line(True, 'drawtext', ('present' if ' drawtext ' in filters else 'absent (expected: blockreel draws all text in game)'), required=False)
    good &= _line((ROOT / 'gradlew').exists(), 'gradle', str(ROOT / 'gradlew'))
    good &= _line(not is_real_minecraft(GAME_DIR), 'game dir', f'{GAME_DIR} (never a real Minecraft folder)')
    jars = sorted((ROOT / 'build/libs').glob('blockreel-*.jar'))
    _line(bool(jars), 'mod jar', str(jars[-1]) if jars else 'not built yet: ./gradlew build (bin/blockreel run builds it anyway)', required=False)
    assets = Path.home() / '.gradle/caches/fabric-loom/assets'
    _line(assets.exists(), 'game assets', f'{assets} (music for the edit is read from here, never committed)' if assets.exists()
          else 'not downloaded yet: the first run downloads them', required=False)
    pid = game.running_pid()
    _line(pid is None, 'client', 'none running' if pid is None else f'pid {pid} is running: blockreel stop', required=False)
    with socket.socket() as s:
        free = s.connect_ex(('127.0.0.1', CONTROL_PORT)) != 0
    _line(free or pid is not None, 'control port', f'{CONTROL_PORT} ' + ('free' if free else 'in use by something else: set BLOCKREEL_PORT'), required=False)
    print(f'  runs in {RUNS}')
    print('READY' if good else 'NOT READY')
    return 0 if good else 1
