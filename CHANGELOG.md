# Changelog

## Unreleased

- Text in the game (`caption`, `title`, `card`, `lower_third`, `keycap`, `clear`): sizes in 1080-line pixels on any
  frame aspect, inside the safe area, one message at a time, words popping on exact frames (explicit `words` times
  for a voice timeline), `shots/<name>/text.json` for measure; `examples/text.toml`.
- The picture edit: clips by `in`/`out` (marks) and `length`, exact to the frame; slow pushes and push-ins whose hold
  is an exact nearest-neighbour crop; speed ramps; fades and `black` gaps; `[[edit.look]]` frames and grades;
  `cut/timeline.json`; the audio mix muxed when present; exports `x-1080p60`, `readme-720p30`, `gif`, `poster`;
  `videocraft edit cut|timeline|verify`; `examples/edit.toml`.
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
