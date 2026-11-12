# Make the CLI work on Windows
Labels: good first issue, platform: windows, help wanted

## Context

Windows is untested. The CLI already looks for `gradlew.bat` and for JDKs under `Program Files`, but several things
are POSIX-only today:

- the slot lock uses `fcntl.flock` (`game.py`), which does not exist on Windows (`msvcrt.locking` does);
- stopping a client uses `os.killpg` and `SIGKILL`;
- the run store points `runs/<name>/latest` at the newest iteration with a symlink, which needs Developer Mode or
  admin rights on Windows;
- `bin/videocraft` relies on a `#!/usr/bin/env python3` line.

## Acceptance

- [ ] On Windows 11 with JDK 25, ffmpeg and Python 3.11+, `py bin\videocraft compile examples\hello.toml` and
      `python -m unittest discover -s cli/tests` pass.
- [ ] Slot locking, `status` and `stop` work on Windows (a lock primitive chosen by platform in one function).
- [ ] `latest` resolves without symlinks when they are not available (for example a `latest` text file holding the
      iteration number, read by `store.resolve`). The run store layout is a contract: add, do not rename.
- [ ] `paths.is_real_minecraft` refuses `%APPDATA%\.minecraft` (add a unit check that fakes `APPDATA`).
- [ ] The macOS and Linux behaviour does not change (`cli/tests` pass there too). Say whether you also ran a take.

## Pointers

- `cli/videocraft/game.py` (slots, `stop`), `cli/videocraft/store.py` (`latest`), `cli/videocraft/paths.py`
- `cli/videocraft/tools.py` (`find_jdk`), `bin/videocraft`
- `cli/tests/test_slots.py`
