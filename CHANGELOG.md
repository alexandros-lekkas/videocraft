# Changelog

## Unreleased

- Long form and clipping (`docs/CLIPS.md`): `assemble` joins runs or a series into one video with in-game chapter
  cards, YouTube and mp4 chapters, one −14 LUFS master and a timeline back to every source shot; `clips find` ranks
  moments from words, key words, outline beats and jokes, marks, sounds and loudness, never cutting mid-word; `clips
  cut` makes 9:16 shorts by re-shooting the range at 1080x1920 (`[shot.vertical]`) or re-framing the master with a
  look-ahead operator; `clips pack` writes titles, hashtags and a thumbnail frame.
- Camera rigs for the benchmark: `lead` (the lead track), `chase`, `track`, `dolly`, `crane`, `locked`, `two_shot`,
  `face`, with `fov` (or eased `[from, to]`), seeded `drift`, block avoidance and positions on actors; shot keys
  `preroll`, `time`, `weather`; `world.preset` (`flat`, `void`) and `world.save` from `cache/worlds/`; batched,
  checked staging commands; `stand_in`/`glide` subjects; the whole plan checked before the world loads;
  `examples/rigs.toml` films every rig.
- The story pipeline (`docs/STORY.md`): `story new/draft/revise/build/show/diff/lock/list`, `series new/status`
  and `make "<prompt>"`: premise → bible → outline → script → a shot script that compiles, every revision kept in
  `runs/story/`, the chosen ones in `stories/`; `--from-file` for hand-written stages; model repairs on failed checks.
  `stories/nibs-vs-duke/` holds the benchmark's script.
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
- Sound: the muted client logs every sound a shot plays to `shots/<name>/sounds.csv` (frame, event, the variant
  chosen, volume, pitch, position; deterministic per seed); actions `sound`, `tune` (a melody on note blocks with
  their particles), `ambience`, `particles`; `cli/videocraft/audio` mixes them onto their frames with distance and
  pan from the camera, voice, an original chiptune bed with stems and cues (`out`, `in`, `drop`, `thin`, `full`,
  `hit`), ducking, silence over black, mastered to −14 LUFS / −1 dBTP; `[edit] audio = "original"` uses no game
  audio; commands `audio mix`, `audio events --onsets`, `audio synth`; `examples/sound.toml`.
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
