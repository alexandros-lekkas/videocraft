# Changelog

## Unreleased

- `texture = "x.png"` on a mob actor draws it with a local texture instead of its own (a vanilla texture with a
  painted change); `lens = { barrel = 0.4 }` on an edit clip or look bows the picture like a wide fisheye-like lens,
  filled to the frame; a `crossing` set op paints zebra stripes across a lane; `[[edit.sfx]]` takes `start`,
  `length` and `fade`, so a long sound plays under one stretch of the cut; lint knows a placed set by its `as`.
- The mix is mastered to -2 dBTP (was -1): the AAC encode of the master overshoots the mix by 0.8-0.9 dB, so a
  -1.0 mix measured -0.5 dBTP in `master.mp4`.
- `clips cut --method reshoot` keeps actors' skins: a relative `skin` path is taken as the take resolved it, not
  relative to the run's copy of the script (the vertical take failed with "no skin PNG").
- Text never shrinks under 44 px: the smallest font scale for titles, cards, captions and lower thirds rounds up (7, 49 px), not
  to the nearest (6, 42 px), so a long card line wraps instead of shrinking under the minimum.
- The benchmark film's second climb (`examples/nibs-vs-duke.toml`, log in `docs/benchmarks/nibs-vs-duke-log.md`):
  near-continuous voice (67% of the runtime at 3 words a second), the reference's camera language from the
  side-by-side, Minecraft sounds and a mood-picked track, bigger acting beats; rounds 7-9, best 0012 at 6.61.
- Sounds by meaning, Minecraft first: a committed catalog of all 1991 sound events and 92 music tracks of 26.3 (names,
  tags, measured lengths, tempo, entries and loops; no audio), a comedy palette (`palette = "drumroll"`), `tag = "pop"`
  on sound cues, `[edit.music] mood = "playful"` with `source = "auto"`, `[[edit.sfx]]`, `tag:` patterns in
  `[edit.mix]`, an original library of 79 code-made sounds that original-only exports swap in automatically, five more
  synth bed styles, and `audio find`, `audio play-sheet`, `audio catalog --refresh`, `audio library` (docs/SOUNDS.md).
- Voiced and fast by default. Every say line is paced (`cli/videocraft/voice/pace.py`): silence trimmed to 60 ms
  before and 120 ms after, pauses capped at 0.25 s (0.4 s after a sentence), and a line slower than 0.85 x its pace
  stretched towards it (atempo, at most 1.2x); characters get `pace = 3.2` and qwen3 lines a brisk default delivery.
  Later lines of a shot pack 0.12 s after the previous one (`gap`; `beat = true` keeps a written `at`). lint warns on
  `unvoiced_text`, `slow_line` and `dead_air`; measure reports words a second per line, the voice share and the
  longest silences; the story prompts write every line as `say` with voices in the bible; the pacing and sound
  reviewers judge dialogue pace. talk.toml: Duke 1.62 → 2.96 words a second, Nibs 2.24 → 3.24, the film 15.7 → 12.0 s.
- `compare --side-by-side --video <ref> --run <it> -o <out.mp4>` films a reference video and an iteration side by
  side, shot N against shot N (or in real time with `--align time`), each follower shot stretched or held to the lead
  shot's length, with labels, a shared timecode and per-shot length deltas; it writes `side-by-side.md`/`.json` and a
  contact sheet beside it. `docs/benchmarks/pinksheep-style.shots.toml` holds the benchmark reference's published
  shot timings for it.
- The Talent Night poster on market-lane shows a fox, not a cat: a snow fox sitting in profile toward the trophy, with
  tall pointed ears, a long snout, a white ruff and a bushy grey tail with a white tip.
- `[[edit.export]] audio = "original"` and `cut --original-audio` write `<export>-original-audio.mp4` and
  `master-original-audio.mp4` beside the game-audio files, from a second mix in `cut/audio-original.wav`; the game
  mix in `cut/audio.wav` is never overwritten.
- A walk carried over a cut ends cleanly on the next shot's first movement cue (`turn`, `state`, `pose` brake it in
  0.25 s, a turn follows once it stands; `place` and `walk` replace it), and a `place` rewrites that frame's
  `actors.csv` row, which was logged at the old walk's spot.
- `measure` finds hard cuts in dark, graded footage (a brightness-scaled minimum when the jump stands ten times
  over the stillness around it), and warns of a repeated frame at a cut only when it straddles the cut inside a
  moving shot, not when one side is a locked-off still.
- `review packet` writes a sound sheet for the sound reviewer: `sound.md` (every placed effect, voice word and music
  cue on its master frame, the dips' loudness, per shot the visible actions beside what is heard) and loudness charts
  `sound/loudness-<k>.png`; the sound prompt now judges sync, ducking and silence at the dips from them.
- The benchmark film `examples/nibs-vs-duke.toml` (docs/benchmarks/pinksheep-style.md): thirty shots and an end
  card on market-lane, barn-stage and black-stage with the goat, fox and chicken puppets, voiced lines, the framed
  flashback, dips to black and the six-shot montage cut on the spoken words; production log in
  `docs/benchmarks/nibs-vs-duke-log.md`.
- Shots end on a beat: `until = "<mark>"` stops recording on the frame an action notes that mark, with `duration`
  as the cap; a mark that never comes fails the take with the shot and the label.
- Flying actors: `fly` (a 3-D eased curve, banking into turns, pitching on climbs), `hover` (seeded drift and bob),
  `swarm` (bees on concentric tilting orbits that never touch each other or the body they circle), `land` (on a block,
  or on an actor's shoulder and ride along); `[[actor]]` keys `flying`, `angry`, `buzz_volume`; wings beat by vanilla's
  own animation and fold through the pose blend; buzz through the sound log; `FlightChecks`, `examples/bees.toml`.
  Puppets no longer tick during staging and the sound log seeds by the shot's frame, so two takes with different
  preparation lengths give identical `actors.csv` and `sounds.csv`.
- Docs for people: a README with install, a quickstart timed from a fresh clone (5.5 min first-time setup, then
  about a minute a take), how it works, a docs map and an honest status; `docs/GALLERY.md`; DESIGN.md's status and
  milestones, AGENTS.md's project map and commands, and SCRIPT.md brought up to the code.
- Voice (`docs/VOICE.md`): a `say` cue is a spoken line, synthesized locally per character (Qwen3-TTS 1.7B
  CustomVoice on MLX, Kokoro-82M as draft/fallback; cast files in `cast/`), aligned word by word (wav2vec2 CTC, onsets
  snapped to the waveform past pause murmur and unscripted sounds), and resolved at compile time into a caption that
  pops on the word onsets, an `edit.voice` line, an optional bark, and the shot's length (`fit = extend | cut-on |
  none`; `cut_on` ends the shot on a word). Lines are cached by content hash; `voice.json` in each iteration; without a
  voice installed, estimated timings. Commands `voice setup | doctor | say | script | check`; `examples/talk.toml`.
- Long form and clipping (`docs/CLIPS.md`): `assemble` joins runs or a series into one video with in-game chapter
  cards, YouTube and mp4 chapters, one −14 LUFS master and a timeline back to every source shot; `clips find` ranks
  moments from words, key words, outline beats and jokes, marks, sounds and loudness, never cutting mid-word; `clips
  cut` makes 9:16 shorts by re-shooting the range at 1080x1920 (`[shot.vertical]`) or re-framing the master with a
  look-ahead operator; `clips pack` writes titles, hashtags and a thumbnail frame.
- Sets (`docs/SETS.md`): places to film written as data in `sets/`, built by a stdlib builder into checked vanilla
  commands with marks a script uses as anchors; `[[world.set]]`; `sets list/ops/build/preview/new/skin`. Shipped:
  `market-lane` (ten stretches dressed for a one-block-high wide lens: `kerb`, `bunting`, lane `paint`), `barn-stage`
  (lit night interior, rail seats, note blocks, trophy), `black-stage` (cards on black), `examples/sets.toml`.
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
- Actors: `[[actor]]` `kind = "mob"` (any living entity, with its own variants and states, `tint`, `scale`) and
  `kind = "mannequin"` (a local PNG `skin`) are deterministic client-side puppets on the frame clock; actions
  `place`, `walk`/`run` (gaits, eased, over steps), `stop`, `turn`, `look` (to the lens), `hop`, `state` (fox sit,
  sleep, bow; goat lower; chicken flap...), `hold`, `emit` (an egg), `voice`, `swing`, `nod`, `shake`, `talk`, `pose`;
  their own footsteps and voices through the client's sound system; `shots/<name>/actors.csv`;
  `examples/animals.toml`, `examples/mannequins.toml`; `ActorChecks`.
- Actors read as alive in dense frame strips: vanilla's on/off poses (fox sit and sleep, wolf/cat sit, mannequin sit
  and crouch) ease instead of popping; head and body turns are capped in speed and acceleration by body type; `turn`
  with `follow` really turns the body; `examples/mannequins.toml` is a wide meeting and a closer conversation (wave,
  talk, nod, a cake held and offered, point, shrug, facepalm); the played player walks, jumps, turns and swings
  (`examples/walk.toml`).
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
- First run is no longer silent: while Gradle and Loom set up (about 1 GB of downloads on a fresh machine), `run`
  passes Gradle's download lines through and says a progress line every 30 s after 15 s of silence.
- Game assets (sounds, music) are found under `GRADLE_USER_HOME` when it is set, not only `~/.gradle`
  (`paths.loom_assets`, used by `doctor` and the audio mix).
- Vertical frames keep text clear of TikTok, Shorts and Reels overlays: the safe area of a frame taller than wide is
  x 5-88 %, y 5-75 % (54-950, 96-1440 at 1080x1920), centred text centres on it, a lower third steps its size down to
  fit, a keycap is kept inside it; `measure` checks the same area.
- `examples/sets.toml` films Nibs, the one-horned goat, walking two of market-lane's path marks from the preroll on
  lead tracks (3 blocks, 105°), instead of a stand-in.
- `lint` knows exactly the actions and rigs the mod registers (it had `stand_in` and `glide` missing and seven
  unbuilt player actions listed), warns on an unknown camera `rig`, and a test fails when its lists drift from the
  Java registries.
