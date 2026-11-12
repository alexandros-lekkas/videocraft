# `videocraft doctor --json`
Labels: good first issue, cli

## Context

`bin/videocraft doctor` prints one line per check (JDK 25, ffmpeg, ffprobe, libx264, folders, slots, the running
client) and ends `READY` or not. Agents and CI parse it today by matching text. A machine-readable form makes the
bug report form and automated set-up checks reliable.

## Acceptance

- [ ] `bin/videocraft doctor --json` prints one JSON object: `{"ready": bool, "checks": [{"name", "status":
      "ok"|"warn"|"fail", "detail"}]}`, and nothing else on stdout; the exit code is the same as without `--json`.
- [ ] The text output does not change.
- [ ] A unit check in `cli/tests/` that runs doctor's check list with stubbed tools and validates the JSON shape.
- [ ] Mentioned in `AGENTS.md` commands and a `CHANGELOG.md` line.

## Pointers

- `cli/videocraft/doctor.py` (`_line`), `cli/videocraft/cli.py` (argument wiring), `cli/videocraft/tools.py`
