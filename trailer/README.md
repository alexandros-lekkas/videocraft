# The videocraft trailer

A 90-second launch trailer for the CLI: a calm, modern motion-graphics wrapper (a warm charcoal canvas, large type,
eased moves, one idea per beat) around Minecraft-native footage and overlays, at a human pace. One world throughout,
Nibs vs Duke's barn and market lane:

| Time | Beat |
|:--|:--|
| 0-3.6 s | Card: "Ask for a film." |
| 3.3-24.6 s | A rebuild of the T3 Code window (sidebar, thread, composer): the prompt typed at about 7.5 characters a second with word pauses and a think-pause before Enter; the agent's reply streaming at reading speed; its two real tool calls (`story show nibs-vs-duke`, `run examples/nibs-vs-duke.toml`). The window pushes into the line where the game starts recording. |
| 24-43.5 s | The take opens out of that line: the barn set built block by block (a toast with its script key), the camera flying in (REC and the frame count as a boss bar), five actors walking to their marks (the held map), a take with voiced captions (REC). One overlay besides the game's captions. |
| 43.5-56.9 s | Card "Then it edits.", then the film scrubbing under its timeline (clips, voice, the ducked bed, sounds, cuts on words). |
| 56.9-71.3 s | Card "Then it reviews itself.", then each criterion as a boss bar, then the climb's best step as a toast. |
| 71.3-81.8 s | The finished film with its own sound. |
| 81.8-89.6 s | The name, one line, the command typed, the repository. |

`python3 trailer/make.py --check` lists every text element's time fully on screen against its reading time
(0.5 s + 0.3 s a word, at least 1.5 s) and how many panels ask to be read each second (`runs/trailer/pacing.md`).

The font (the game's bitmap glyphs, their shadow, the caption outline) and the GUI sprites (toasts, boss bars, the map,
the menu chrome) are drawn by `render.swift` from the local client jar, unpacked into `runs/trailer/mc/` at build time;
nothing of the game's is committed. The main sound track is the game's own (music picked by the mood map, the GUI's
sounds, the films' own mixes); every export has an `-original-audio` twin with a synth bed and library sounds instead.

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
| Scores and the climb | `data/review.json` | `runs/nibs-vs-duke/0012/score.json` (round 9); rounds 1-9 from `docs/benchmarks/nibs-vs-duke-log.md` |

## The runs it needs (under `runs/`, never committed)

`nibs-vs-duke/0012` (a copy of the finished Nibs vs Duke iteration, with its `clips/` re-frames), and the footage
unit's barn-world takes: `fu-build-barn-stage/0003` (the set built on camera), `fu-flyin/0003`, `fu-marks/0006`,
`fu-take/0002`, `fu-beauty/0002`. Paths are in `trailer.toml [media]`. `footage.py` and `footage/*.toml` film the
trailer's own earlier takes (`trailer-panorama`, `trailer-keynote`, `trailer-bees`, `trailer-build`).

## Rules it keeps

- **Real data only.** Every command, output line, path, hash, score and timing is captured, not typed in.
- **No third-party marks.** The only logo is videocraft's own pixel block (`assets/icon.svg`, read as pixels and
  assembled); no Anthropic, Claude, Mojang or Minecraft marks. The end card says it is unofficial.
- **The game's assets are read, never committed.** Textures, font and sounds come from the local game install at
  render time; the `-original-audio` exports contain no Mojang audio at all.
- **Captions are the game's.** Clips are chosen with their in-game captions on screen; every other word is the
  game's own font, drawn from its bitmap at render time.
