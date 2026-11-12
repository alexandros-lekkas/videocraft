"""Finding the programs videocraft runs: JDK 25, ffmpeg, ffprobe."""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def java_major(home):
    try:
        text = (Path(home) / 'release').read_text()
        return int(re.search(r'JAVA_VERSION="(\d+)', text).group(1))
    except (OSError, AttributeError, ValueError):
        return None


def find_jdk():
    """JAVA_HOME when it is a JDK 25, else the usual install locations. A newer JDK cannot compile the build."""
    candidates = [os.environ.get('JAVA_HOME')]
    if sys.platform == 'darwin':
        try:
            candidates.append(subprocess.run(['/usr/libexec/java_home', '-v', '25'], capture_output=True, text=True, timeout=10).stdout.strip())
        except (OSError, subprocess.SubprocessError):
            pass
        candidates += ['/opt/homebrew/opt/openjdk@25/libexec/openjdk.jdk/Contents/Home', '/usr/local/opt/openjdk@25/libexec/openjdk.jdk/Contents/Home']
        candidates += sorted(str(p / 'Contents/Home') for p in Path('/Library/Java/JavaVirtualMachines').glob('*25*'))
    elif os.name == 'nt':
        for root in filter(None, (os.environ.get('ProgramFiles'), os.environ.get('ProgramFiles(x86)'))):
            for vendor in ('Eclipse Adoptium', 'Java', 'Microsoft', 'Zulu'):
                candidates += sorted(str(p) for p in Path(root, vendor).glob('*25*'))
    else:
        candidates += sorted(str(p) for p in Path('/usr/lib/jvm').glob('*25*'))
        candidates += sorted(str(p) for p in Path.home().glob('.sdkman/candidates/java/25*'))
    for home in candidates:
        if home and java_major(home) == 25 and (Path(home) / 'bin').is_dir():
            return home
    return None


def gradle_env():
    home = find_jdk()
    if not home:
        raise SystemExit('JDK 25 not found. Install one (macOS: brew install openjdk@25; elsewhere: Temurin 25) or point JAVA_HOME at it.')
    env = dict(os.environ, JAVA_HOME=home)
    env['PATH'] = str(Path(home) / 'bin') + os.pathsep + env.get('PATH', '')
    return env


def ffmpeg():
    return os.environ.get('FFMPEG') or shutil.which('ffmpeg') or ('/opt/homebrew/bin/ffmpeg' if Path('/opt/homebrew/bin/ffmpeg').exists() else None)


def ffprobe():
    override = os.environ.get('FFPROBE')
    if override:
        return override
    f = ffmpeg()
    if f and (Path(f).parent / 'ffprobe').exists():
        return str(Path(f).parent / 'ffprobe')
    return shutil.which('ffprobe')
