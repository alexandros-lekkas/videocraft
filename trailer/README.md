# The videocraft trailer

A 60-second launch trailer for the CLI, in **Minecraft's own visual language** and told as the owner asked: a prompt
typed into the game's chat → the film made inside Minecraft → the agent at work. One world throughout, Nibs vs Duke's:

| Time | What | How it looks |
|:--|:--|:--|
| 0-5 s | The prompt (that story's real request) typed in the vanilla chat over the barn at dusk; the agent answers with real `story show` and `run` output | the game's chat and edit line, the game font, CLI colours as chat colours |
| 5-25 s | The chat closes on the world: the barn set built block by block, the camera flying in, five actors walking to their marks, a take with voiced captions, then the film's own takes | REC and the frame count from frames.csv as a boss bar; the script line as a toast; the camera and actors on a held map |
| 25-30 s | A voiced line | the game's subtitle box listing each word on its onset (real word timings) |
| 30-40 s | The edit, over the film scrubbing | timeline.json's clips in dye colours, voice lines, the bed ducked under each line, every sound, cuts on words |
| 40-45 s | The review and the climb | each criterion a boss bar filling to its score; the climb's best step (6.50 → 6.61) as a toast |
| 45-55 s | The finished film with its own sound | nothing over it |
| 55-60 s | The command line and the repository over the barn at sunset | the game font, the chat's edit line |

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
