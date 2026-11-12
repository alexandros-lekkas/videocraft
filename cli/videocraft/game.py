"""Launching the hidden game for one take, and talking to it over the control port.

Every client is hidden (no window, no Dock icon, no focus), muted, in its own game directory (run-game/), on
videocraft's own control port, and bounded by a timeout. One client at a time: a pid file guards it.
"""
import json
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

from videocraft import tools
from videocraft.paths import CONTROL_PORT, GAME_DIR, ROOT, is_real_minecraft

PID_FILE = GAME_DIR / 'videocraft.pid'
# `version` is 26.3's data version, so the game does not run old-format upgrades over these lines.
OPTIONS = {
    'version': '5023', 'soundCategory_master': '0.0', 'pauseOnLostFocus': 'false', 'onboardAccessibility': 'false',
    'skipMultiplayerWarning': 'true', 'joinedFirstServer': 'true', 'tutorialStep': 'none', 'narrator': '0',
    'maxFps': '260', 'enableVsync': 'false', 'renderDistance': '12', 'simulationDistance': '8', 'autoJump': 'false',
    'inactivityFpsLimit': '"minimized"',
}
# Enforced on every run, whatever a previous run or a person left in the file.
ENFORCED = ('soundCategory_master', 'pauseOnLostFocus', 'autoJump', 'onboardAccessibility', 'enableVsync')


def prepare_game_dir():
    if is_real_minecraft(GAME_DIR):
        raise SystemExit(f'Refusing to run the game in {GAME_DIR}: that is a real Minecraft folder.')
    GAME_DIR.mkdir(parents=True, exist_ok=True)
    options = GAME_DIR / 'options.txt'
    lines = options.read_text().splitlines() if options.exists() else [f'{k}:{v}' for k, v in OPTIONS.items()]
    keep = [line for line in lines if line.split(':', 1)[0] not in ENFORCED]
    options.write_text('\n'.join(keep + [f'{k}:{OPTIONS[k]}' for k in ENFORCED]) + '\n')


def alive(pid):
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def running_pid():
    try:
        pid = int(PID_FILE.read_text().strip())
    except (OSError, ValueError):
        return None
    if alive(pid):
        return pid
    PID_FILE.unlink(missing_ok=True)
    return None


def kill_tree(pid):
    if os.name == 'nt':
        subprocess.run(['taskkill', '/T', '/F', '/PID', str(pid)], capture_output=True)
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pid, sig)
        except (ProcessLookupError, PermissionError):
            return
        for _ in range(50):
            if not alive(pid):
                return
            time.sleep(0.1)


def control(path, method='GET', port=CONTROL_PORT, timeout=2):
    request = urllib.request.Request(f'http://127.0.0.1:{port}{path}', method=method, data=b'' if method == 'POST' else None)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def default_window():
    """Window size in points for a 1920x1080 framebuffer. Macs are assumed 2x; the mod resizes if the guess is wrong."""
    return (960, 540) if sys.platform == 'darwin' else (1920, 1080)


def play(take: Path, *, show=False, timeout=900, window=None, port=CONTROL_PORT, gradle_args=(), on_line=None):
    """Runs one take to the end. Returns (result dict or None, exit code of the client, seconds)."""
    if running_pid():
        raise SystemExit(f'A videocraft client is already running (pid {running_pid()}). `videocraft stop` first; one client at a time.')
    ffmpeg = tools.ffmpeg()
    if not ffmpeg:
        raise SystemExit('ffmpeg not found (brew install ffmpeg, or set FFMPEG)')
    prepare_game_dir()
    w, h = window or default_window()
    props = {'take': str(take.resolve()), 'gameDir': str(GAME_DIR), 'ffmpeg': ffmpeg, 'controlPort': str(port), 'width': str(w), 'height': str(h)}
    if show:
        props['show'] = 'true'
    gradlew = ROOT / ('gradlew.bat' if os.name == 'nt' else 'gradlew')
    command = [str(gradlew), 'runClient', '--console=plain', '-q'] + [f'-P{k}={v}' for k, v in props.items()] + list(gradle_args)
    log_path = take / 'game.log'
    started = time.time()
    (take / 'result.json').unlink(missing_ok=True)
    with open(log_path, 'w') as log:
        process = subprocess.Popen(command, cwd=ROOT, env=tools.gradle_env(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                   start_new_session=os.name != 'nt')
        PID_FILE.write_text(str(process.pid))
        def pump():
            for line in process.stdout:
                log.write(line)
                log.flush()
                if on_line:
                    on_line(line.rstrip('\n'))

        reader = threading.Thread(target=pump, daemon=True)
        reader.start()
        try:
            while process.poll() is None and time.time() < started + timeout:
                time.sleep(0.5)
            if process.poll() is None:
                try:
                    control('/quit', 'POST', port)
                    process.wait(timeout=20)
                except Exception:
                    pass
        finally:
            if process.poll() is None:
                kill_tree(process.pid)
            process.wait()
            reader.join(timeout=5)
            PID_FILE.unlink(missing_ok=True)
    result_file = take / 'result.json'
    result = json.loads(result_file.read_text()) if result_file.exists() else None
    return result, process.returncode, time.time() - started


def discard_world(level_id):
    """Deletes a world a take created from a seed (only videocraft-* folders under run-game/saves)."""
    import shutil
    if not level_id or not level_id.startswith('videocraft-'):
        return
    saves = (GAME_DIR / 'saves').resolve()
    target = (saves / level_id).resolve()
    if target.parent == saves and target.is_dir():
        shutil.rmtree(target)
