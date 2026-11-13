# The videocraft trailer

An 84-second launch trailer for the CLI: a calm, modern motion-graphics wrapper (kinetic type in the trailer's own
face, eased moves, one idea per beat, every beat dissolving into the next over footage, never through an empty
canvas) around Minecraft-native footage and overlays, at a human pace. One world throughout, Nibs vs Duke's barn:

| Time | Beat |
|:--|:--|
| 0-3.6 s | "Ask for a film." over the barn at dusk. |
| 3.0-23.4 s | A rebuild of the T3 Code window: the prompt typed at about 7.5 characters a second with word pauses; the reply streaming at reading speed; one plain line for the story ("Story drafted: 32 shots, 28 voiced lines.", counted from the run); the take's real tool call, drawn small and normal weight; a live "Working… 0:08" line; a slow push-in; then a dive into the line where the game starts recording. |
| 22.9-39.4 s | The take opens out of that line, each step named in plain words with a four-tick strip: "Builds the set" (the set going up, its script key as a toast), "Flies the camera" (REC as a boss bar), "Actors to marks" (the held map), "Rolls the take". |
| 39.0-51.2 s | "Then it edits." over the film, then its timeline (clips, voice, the ducked bed, sounds) with a large "Cut on “word”" chip popping as each cut on a word lands. |
| 50.8-61.8 s | "Then it reviews itself." over the film, then a side panel: the four criteria review round 9 scored up from round 8, before → after; what changed between the two takes; the average against the pass line it has not reached. |
| 61.5-75.6 s | The jump-off: the challenge and Duke's comeback, Nibs' leap, Duke's pounce into the flowers, "Huh. Flowers." |
| 75.1-84.4 s | The name over the barn at sunset, one line, the command, the repository; the whole lockup held five seconds. |

`python3 trailer/make.py --check` lists every text element's time fully on screen against its reading time
(0.5 s + 0.3 s a word, at least 1.5 s) and how many panels ask to be read each second (`runs/trailer/pacing.md`);
once the pictures are rendered it also measures the seconds of near-black in each cut (sampled at 10 fps: a frame
whose brightest pixel is under 80 in video range) against a target under 1.5 s, and fails over it.

The font (the game's bitmap glyphs, their shadow, the caption outline) and the GUI sprites (toasts, boss bars, the map,
the menu chrome) are drawn by `render.swift` from the local client jar, unpacked into `runs/trailer/mc/` at build time;
nothing of the game's is committed. The main sound track is the game's own (music picked by the mood map, the GUI's
sounds, the takes' own mixes); every export has an `-original-audio` twin with a synth bed and library sounds instead.

```sh
python3 trailer/footage.py            # the trailer's own takes (the set going up, the keynote, bees with captions)
python3 trailer/make.py               # both layouts, the sound track, the exports and the poster (about 11 min)
python3 trailer/make.py --layout h --stills 600,1500       # PNG stills (runs/trailer/stills/h/)
python3 trailer/make.py --layout h --strip 28:32          # every 4th frame between two times
python3 trailer/review.py --round 1   # fresh reviewers on the exports (trailer/rubric.toml)
```

Outputs, all in the git-ignored `runs/trailer/`: `videocraft-trailer-1080p60.mp4` (1920x1080, 60 fps),
`videocraft-trailer-9x16.mp4` (1080x1920, laid out for its own frame: the type, terminal and panels move; the
footage is the tool's own 9:16 re-frames), `videocraft-trailer-poster.png`, `timeline-<h|v>.json`, `review/<n>/`.

## How it is made

| File | What |
|:--|:--|
| `trailer.toml` | The timeline: scenes with their times, every on-screen line, the footage clips and their script chips, colours, the sound (bed stems by section, effects, the voice lines), the trailer's own takes. |
| `make.py` | Reads the timeline and `data/`, writes `runs/trailer/timeline-<layout>.json`, compiles and runs the renderer into x264, mixes and masters the sound (`videocraft.audio.loudness`: −14 LUFS, true peak under −1.5 dBTP), muxes the exports. Standard library only. |
| `render.swift` | The frames: the game's font and GUI sprites drawn pixel-crisp at GUI scale 4 with CoreGraphics (nearest-neighbour), footage decoded by ffmpeg pipes into the same frame, raw BGRA frames to stdout. The `mc*` scenes are the trailer; the older scene types stay for reuse. Every scene is a function of time, so any frame renders alone. `swiftc -O trailer/render.swift -o runs/trailer/bin/render` (make.py does it). |
| `footage.py`, `footage/keynote.toml` | The takes the finished runs did not have: a set built on camera from its own commands, the keynote set with a presenter, and a copy of `examples/bees.toml` with the game's own captions (the owner wants every clip in that caption style). |
| `review.py`, `rubric.toml` | A packet of stills (contact sheets of both cuts, strips of 16 consecutive frames at every entrance, facts), one `claude -p` reviewer per role through `videocraft.agents.ask`, a score. |
| `data/` | Real command output and measurements, local paths shortened to `./` and `~` by `make.py capture <file>`. |

## Where every number on screen comes from

| On screen | Source | Made by |
|:--|:--|:--|
| The prompt | `stories/nibs-vs-duke/story.json` | the story's own `request` |
| The agent's output | `data/story-show.txt`, `data/game-log.txt` | `bin/videocraft story show nibs-vs-duke`; the take's `game.log` (`runs/nibs-vs-duke/0012`) |
| REC frame counters, the maps | each clip's `frames.csv` and `actors.csv` | mapped from the cut's time through `cut/timeline.json`, or the shot's own frames for raw shots |
| Toasts | each shot's script | the real keys of the shot (shortened to fit a toast) |
| The subtitle box | `runs/nibs-vs-duke/0012/edit.json` | the s01 lines' word onsets (Qwen3-TTS, the aligner) |
| The edit | `runs/nibs-vs-duke/0012`: `cut/timeline.json`, `edit.json`, `cut/audio-original.json` | 34 clips, 28 voiced lines, 124 sound events, the −9 dB duck, 4 cuts on a word |
| Scores and the climb | `data/review.json` | `runs/nibs-vs-duke/0012/score.json` (round 9); rounds 1-9 and the round 8 → 9 criteria and changes (`climb`) from `docs/benchmarks/nibs-vs-duke-log.md` |
| "Story drafted: 32 shots, 28 voiced lines." | `runs/nibs-vs-duke/0012` | its `script.toml` shots and `voice.json` lines |

## The runs it needs (under `runs/`, never committed)

`nibs-vs-duke/0012` (a copy of the finished Nibs vs Duke iteration), and the footage unit's barn-world takes:
`fu-build-barn-stage/0003` (the set built on camera), `fu-flyin/0003`, `fu-marks/0006`, `fu-take/0002`,
`fu-beauty/0002`, their true 9:16 re-shoots `fu-take-v/0003` and `fu-beauty-v/0002`, and the jump-off
(`footage-unit/jump.toml` → `fu-jump/0002`, `jump-v.toml --window 540x960` → `fu-jump-v/0001`; Nibs vs Duke has no
shot where anyone jumps). The 9:16 cut plays the true vertical takes where they exist and a subject-centred
full-height crop (`fx`) of the takes with no text in them. The original-audio twin plays the takes' voiced lines alone
(placed from each run's `voice.json`), so it holds no game sound. Paths are in `trailer.toml [media]`. `footage.py` and `footage/*.toml` film the
trailer's own earlier takes (`trailer-panorama`, `trailer-keynote`, `trailer-bees`, `trailer-build`).

## Rules it keeps

- **Real data only.** Every command, output line, path, hash, score and timing is captured, not typed in.
- **No third-party marks.** The only logo is videocraft's own pixel block (`assets/icon.svg`, read as pixels and
  assembled); no Anthropic, Claude, Mojang or Minecraft marks. The end card says it is unofficial.
- **The game's assets are read, never committed.** Textures, font and sounds come from the local game install at
  render time; the `-original-audio` exports contain no Mojang audio at all.
- **Captions are the game's.** Clips are chosen with their in-game captions on screen; every other word is the
  game's own font, drawn from its bitmap at render time.
