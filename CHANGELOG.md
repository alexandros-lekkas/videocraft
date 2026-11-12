# Changelog

## Unreleased

- `measure` sees what a reviewer needs, on a run or any video (`--video f --from s --to s --out dir`): shots by scene
  detection, cuts per minute, the length histogram, runs of sub-0.6 s shots, detected cuts against the edit's own
  joins, black and frozen stretches, repeated frames at cuts, EBU R128 loudness, camera speed/acceleration/jerk,
  subject framing projected from `frames.csv` + `actors.csv`, and the section 5 text rules from `text.json`;
  `measure/report.md` and `measure/signals.csv` join `metrics.json`. `review packet` (strips, contact sheets, cut
  pairs, captions, prompts), `review add`, `review run` (`claude -p` or the Anthropic API through `agents.ask`),
  `score`, `compare`, `notes`, `lint` (also written as `lint.json` before every take), `climb`, `modpack`
  (an `.mrpack`), `runs` with scores, and `index.json` with the parent chain. Rubrics: `docs/REVIEW.md` (general) and
  `docs/benchmarks/pinksheep-style.rubric.toml`. `doctor` also checks game sounds, the voice venv and the reviewers,
  and runs a `doctor()` from any command group that defines one.
- `AGENTS.md`: a "Working with agents" section (orchestrator, builders in worktrees, reviewer agents, probing
  accounts); T3 Craft is linked by its public repository.
- Command groups: `cli.py` loads `videocraft.<group>.commands` (`register(subparsers)`) for `edit`, `audio`, `voice`,
  `sets`, `story`, `review`, `series` and `clips`, so new commands land in their own files instead of `cli.py`.
- Takes in several checkouts at once: each take holds one of three machine-wide slots (control ports
  25750–25752) and waits (`--slot-wait`, default 1800 s) when all are busy; the checkout's pid file records the port,
  so `status` and `stop` find its client; `--port` refuses the ports of other tools; `doctor` shows the slots.
- Renamed from blockreel to videocraft: Java package `io.github.alexandroslekkas.videocraft`, mod id, CLI
  (`bin/videocraft`), system properties (`videocraft.*`), log prefix `VIDEOCRAFT`, world folders `videocraft-*`.
- The foundation: a Fabric mod for Minecraft 26.3 that plays a compiled shot script in a hidden client on a fixed
  frame clock and captures every frame to ffmpeg; the `videocraft` CLI (`doctor`, `compile`, `run`, `cut`, `measure`,
  `runs`, `status`, `stop`); the run store; `examples/hello.toml` (an orbit around spawn, 1080p60).
