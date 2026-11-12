"""Launching the hidden game for one take, and talking to it over the control port.

Every client is hidden (no window, no Dock icon, no focus), muted, in its own game directory (run-game/), on
videocraft's own control port, and bounded by a timeout.

One client per checkout: a pid file in run-game/ guards it and records the client's port, so `status` and `stop`
in that checkout find it. At most three per machine: a take holds one of three slots (an exclusive flock on
SLOT_DIR/slot-<n>.lock, held by this process for the whole take and dropped by the OS if it dies); slot n is
control port 25750+n.
"""
import json
import os
import socket
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

from videocraft import tools
from videocraft.paths import GAME_DIR, PORT_OVERRIDE, RESERVED_PORTS, ROOT, SLOT_DIR, SLOT_PORTS, is_real_minecraft

if os.name == 'nt':
    import msvcrt
else:
    import fcntl

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


def running():
    """This checkout's client as (pid, port), or None. The pid file is JSON {"pid", "port"}; a bare pid is port 25750."""
    try:
        text = PID_FILE.read_text().strip()
        record = json.loads(text) if text.startswith('{') else {'pid': int(text)}
        pid, port = int(record['pid']), int(record.get('port') or SLOT_PORTS[0])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if alive(pid):
        return pid, port
    PID_FILE.unlink(missing_ok=True)
    return None


def running_pid():
    client = running()
    return client[0] if client else None


def check_port(port):
    """An explicit port must not be one that belongs to another tool on this machine."""
    if port in RESERVED_PORTS:
        raise SystemExit(f'Port {port} belongs to another tool on this machine (25590, 25611, 25680-25690 and 25720 are '
                         f'never used); videocraft uses {SLOT_PORTS[0]}-{SLOT_PORTS[-1]}.')
    if not 1024 <= port <= 65535:
        raise SystemExit(f'Port {port} is not a usable control port (1024-65535)')
    return port


def port_free(port):
    """Nothing listens on 127.0.0.1:<port> (an old client without a slot, or another program)."""
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(('127.0.0.1', port)) != 0


class Slot:
    """One of the machine's three take slots, held until release() (or this process ends)."""

    def __init__(self, index, port, fd):
        self.index, self.port, self._fd = index, port, fd

    def release(self):
        if self._fd is not None:
            os.close(self._fd)  # closing the descriptor drops the lock
            self._fd = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.release()


def _lock(fd):
    try:
        if os.name == 'nt':
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def try_slot(index, *, lock_dir=None, ports=SLOT_PORTS, is_free=port_free):
    """Slot <index> if its lock is free and nothing else listens on its port, else None."""
    lock_dir = Path(lock_dir or SLOT_DIR)
    lock_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(lock_dir / f'slot-{index}.lock', os.O_RDWR | os.O_CREAT, 0o600)
    if not _lock(fd):
        os.close(fd)
        return None
    if not is_free(ports[index]):
        os.close(fd)
        return None
    if os.name != 'nt':  # who holds it, for `videocraft doctor` (Windows locks the byte this would write)
        os.ftruncate(fd, 0)
        os.write(fd, f'{os.getpid()} {ROOT}\n'.encode())
    return Slot(index, ports[index], fd)


def slot_holder(index, lock_dir=None):
    """What a held slot's lock file says ("<pid> <checkout>"), or '' if it is free or unreadable."""
    path = Path(lock_dir or SLOT_DIR) / f'slot-{index}.lock'
    try:
        fd = os.open(path, os.O_RDWR)
    except OSError:
        return ''
    try:
        if _lock(fd):
            return ''
        return path.read_text().strip()
    except OSError:
        return ''
    finally:
        os.close(fd)


def acquire_slot(*, wait=1800, poll=2.0, say=print, lock_dir=None, ports=SLOT_PORTS, is_free=port_free, only=None):
    """The first free slot (or slot <only>); if none is free, says so once and polls for up to <wait> seconds, then
    exits with why."""
    indices = range(len(ports)) if only is None else [only]
    busy = (f'All {len(ports)} videocraft slots (ports {ports[0]}-{ports[-1]}) are busy' if only is None
            else f'Slot {only} (port {ports[only]}) is busy')
    deadline = time.monotonic() + wait
    waiting = False
    while True:
        for index in indices:
            slot = try_slot(index, lock_dir=lock_dir, ports=ports, is_free=is_free)
            if slot:
                return slot
        if time.monotonic() >= deadline:
            raise SystemExit(f'{busy} after {wait:g} s of waiting: at most {len(ports)} clients run on this machine. '
                             '`videocraft stop` in a checkout that is done, or raise --slot-wait.')
        if not waiting:
            say(f'{busy}; waiting up to {wait:g} s for a free one')
            waiting = True
        time.sleep(max(0.0, min(poll, deadline - time.monotonic())))


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


def control(path, method='GET', port=SLOT_PORTS[0], timeout=2):
    request = urllib.request.Request(f'http://127.0.0.1:{port}{path}', method=method, data=b'' if method == 'POST' else None)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def default_window():
    """Window size in points for a 1920x1080 framebuffer. Macs are assumed 2x; the mod resizes if the guess is wrong."""
    return (960, 540) if sys.platform == 'darwin' else (1920, 1080)


def play(take: Path, *, show=False, timeout=900, window=None, port=None, slot_wait=1800, gradle_args=(), on_line=None, say=print):
    """Runs one take to the end. Returns (result dict or None, exit code of the client, seconds).

    Without a port (and without VIDEOCRAFT_PORT) the take waits for one of the three slots and uses its port; an
    explicit port skips the slot choice, but still holds that slot's lock if it is one of the three.
    """
    client = running()
    if client:
        raise SystemExit(f'A videocraft client is already running in this checkout (pid {client[0]}, port {client[1]}). '
                         '`videocraft stop` first; one client per checkout.')
    ffmpeg = tools.ffmpeg()
    if not ffmpeg:
        raise SystemExit('ffmpeg not found (brew install ffmpeg, or set FFMPEG)')
    prepare_game_dir()
    port = port if port is not None else PORT_OVERRIDE
    if port is None:
        slot = acquire_slot(wait=slot_wait, say=say)
    elif port in SLOT_PORTS:
        slot = acquire_slot(wait=slot_wait, say=say, only=SLOT_PORTS.index(port))
    else:
        slot = None
        if not port_free(check_port(port)):
            # A /quit on timeout would reach whatever listens there, perhaps another checkout's client.
            raise SystemExit(f'Port {port} is already in use; pick another or leave --port out to get a free slot')
    say(f'  control port {slot.port} (slot {slot.index} of {len(SLOT_PORTS)})' if slot else f'  control port {port} (no slot)')
    try:
        return _play(take, show, timeout, window, slot.port if slot else port, gradle_args, on_line, ffmpeg)
    finally:
        if slot:
            slot.release()


def _play(take, show, timeout, window, port, gradle_args, on_line, ffmpeg):
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
        PID_FILE.write_text(json.dumps({'pid': process.pid, 'port': port}) + '\n')
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
