# Changelog

## Unreleased

- Voice (`docs/VOICE.md`): a `say` cue is a spoken line, synthesized locally per character (Qwen3-TTS 1.7B
  CustomVoice on MLX, Kokoro-82M as draft/fallback; cast files in `cast/`), aligned word by word (wav2vec2 CTC, onsets
  snapped to the waveform past pause murmur and unscripted sounds), and resolved at compile time into a caption that
  pops on the word onsets, an `edit.voice` line, an optional bark, and the shot's length (`fit = extend | cut-on |
  none`; `cut_on` ends the shot on a word). Lines are cached by content hash; `voice.json` in each iteration; without a
  voice installed, estimated timings. Commands `voice setup | doctor | say | script | check`; `examples/talk.toml`.
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
