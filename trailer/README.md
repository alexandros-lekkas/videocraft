# The videocraft trailer

A 66-second launch trailer for the CLI in a calm motion-graphics style, told as the owner asked: **a prompt typed into
an agent chat → the film made inside Minecraft → the agent at work**. A generic, code-drawn chat (no real product's
UI or marks) takes the prompt and prints the agent's real `videocraft make` and `run` output; the line where the
hidden game starts recording match-cuts into the game; a recording monitor (REC, the frame counter from
`frames.csv`, a top view of the camera and every actor from `frames.csv` and `actors.csv`) rides over real takes: a
set built block by block, the goat walking to his mark, a camera flying down an aisle, a lead track, a swarm; a voice
line on its waveform with the game's own captions; the edit timeline of a finished run assembling from its
`timeline.json` (clips, voice lines, the bed ducked −9 dB under every line, every sound event, the cuts that land on a
word); the review scores and the climb; the finished film with its own sound; the command line and the repo.
Everything is drawn by code; nothing is screen-captured.

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
| `render.swift` | The motion graphics: CoreGraphics and CoreText (SF Pro and SF Mono, vector and antialiased), footage decoded by ffmpeg pipes into the same frame, raw BGRA frames to stdout. Every scene is a function of time, so any frame renders alone. `swiftc -O trailer/render.swift -o runs/trailer/bin/render` (make.py does it). |
| `footage.py`, `footage/keynote.toml` | The takes the finished runs did not have: a set built on camera from its own commands, the keynote set with a presenter, and a copy of `examples/bees.toml` with the game's own captions (the owner wants every clip in that caption style). |
| `review.py`, `rubric.toml` | A packet of stills (contact sheets of both cuts, strips of 16 consecutive frames at every entrance, facts), one `claude -p` reviewer per role through `videocraft.agents.ask`, a score. |
| `data/` | Real command output and measurements, local paths shortened to `./` and `~` by `make.py capture <file>`. |

## Where every number on screen comes from

| On screen | Source | Made by |
|:--|:--|:--|
| The agent's `make` output | `data/make.txt` | `bin/videocraft make "a goat challenges a fox to a jump-off" --dry-run` (14 min 49 s, 2 attempts at the shot list) |
| The agent's `run` output | `data/run-story2.txt` | `bin/videocraft run stories/a-goat-challenges-a-fox-to-a-jump-off-2/shots.toml` after one hand fix recorded as a story revision (`story draft shots … --from-file`: a `hop` of 5.5 blocks, over the 3-block limit, set to 3; take 0001 had failed on it) |
| The set going up | `runs/trailer-build/0001` | `footage.py build`: the `keynote-stage` set's own 132 build commands (as `[[world.set]]` expands them), 7 in staging and 86 as timed `command` cues in one filmed shot (light blocks and the ceiling left out), played at 2x |
| REC frame counters, the top views | each clip's `take/shots/<shot>/frames.csv` and `actors.csv` | mapped from the cut's time through `cut/timeline.json` |
| The waveform and word ticks | `data/voice-nibs.json` | `runs/talk/0001/voice.json` (Qwen3-TTS voice `ryan`, word timings from the aligner) and the line's wav |
| The `voice check` lines | `data/voice-check.txt` | `bin/videocraft voice check talk` |
| The edit timeline | `runs/nibs-vs-duke/0012`: `cut/timeline.json`, `edit.json`, `cut/audio-original.json` | 34 clips, 28 voiced lines, 124 sound events, the music cues, the duck (−9 dB, the mix's default), 4 cuts on a word |
| Scores, rounds, the quote | `data/review.json` | `runs/nibs-vs-duke/0012/score.json` (round 9) and the round table in `docs/benchmarks/nibs-vs-duke-log.md` |
| The 9:16 footage | `data/clips-cut.txt`, `data/clips-v.txt` | `bin/videocraft clips cut <run> --method reframe --from … --to …` |

The finished film at the end is **Nibs vs Duke** (the same premise, climbed for 12 iterations), not the prompt's
own first take; its chip says so. It plays with its own original-audio track (synth bed, library sounds, its voices).

## The runs it needs (under `runs/`, never committed)

`nibs-vs-duke/0012` (a copy of the finished Nibs vs Duke iteration; its `clips/r1-r5` are the re-frames),
`talk/0001` (and its voice line in `cache/voice/lines/`), `trailer-build/0001`, `trailer-keynote/0002`,
`trailer-bees/0001`, `a-goat-challenges-a-fox-to-a-jump-off-2/0002`. Paths are in `trailer.toml [media]`.

## Rules it keeps

- **Real data only.** Every command, output line, path, hash, score and timing is captured, not typed in.
- **No third-party marks.** The only logo is videocraft's own pixel block (`assets/icon.svg`, read as pixels and
  assembled); no Anthropic, Claude, Mojang or Minecraft marks. The end card says it is unofficial.
- **No Mojang audio.** The bed is `videocraft audio synth --style keynote --bpm 120`, the effects come from the
  original library (`audio library`), the voices are the tool's local TTS. Footage audio is never used.
- **Captions are the game's.** Clips are chosen with their in-game captions on screen; the clean sans-serif and the
  monospace are for titles and chrome only.
- System fonts (SF Pro, SF Mono) are used to render; no font file is shipped.
