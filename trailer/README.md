# The videocraft trailer

A 68-second launch trailer for the CLI in a calm motion-graphics style: a terminal that types real commands and
prints their real output, the pipeline lighting up file by file, full-bleed footage filmed by videocraft, the
determinism proof, a voiced line on its waveform, the review scores and the climb, and the logo. Everything is drawn
by code; nothing is screen-captured.

```sh
python3 trailer/footage.py            # the trailer's own takes (keynote, bees and rigs with captions; rigs twice)
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
| `footage.py`, `footage/keynote.toml` | The takes the finished runs did not have: the keynote set with a presenter, and copies of `examples/bees.toml` and `examples/rigs.toml` with the game's own captions on every shot (the owner wants every clip in that caption style). |
| `review.py`, `rubric.toml` | A packet of stills (contact sheets of both cuts, strips of 16 consecutive frames at every entrance, facts), one `claude -p` reviewer per role through `videocraft.agents.ask`, a score. |
| `data/` | Real command output and measurements, local paths shortened to `./` and `~` by `make.py capture <file>`. |

## Where every number on screen comes from

| On screen | Source (`data/`) | Made by |
|:--|:--|:--|
| The `make` transcript | `make.txt` | `bin/videocraft make "a goat challenges a fox to a jump-off" --dry-run` (14 min 49 s, 2 attempts at the shot list) |
| The `run` of that story | `run-story2.txt` | `bin/videocraft run stories/a-goat-challenges-a-fox-to-a-jump-off-2/shots.toml` after one hand fix recorded as a story revision (`story draft shots … --from-file`: a `hop` of 5.5 blocks, over the 3-block limit, set to 3; take 0001 had failed on it). The trailer's chip says so. |
| The film from the prompt | — | `runs/a-goat-challenges-a-fox-to-a-jump-off-2/0002/cut/master.mp4`, 25 shots, 55.13 s, `RESULT PASS` |
| `2460 / 2460 frames identical`, the hashes | `framemd5.csv`, `framemd5.json` | two takes of the captioned rigs script (`footage.py rigs` twice), `ffmpeg -i … -map 0:v -f framemd5 -`; all 10 `frames.csv` files byte-identical |
| The waveform, word ticks, cut at frame 346 | `voice-talk.json` | `runs/talk/0001/voice.json` (Qwen3-TTS voice `ryan`, word timings from the aligner), peaks from the line wavs placed at their times in the master |
| The `voice check` lines | `voice-check.txt` | `bin/videocraft voice check talk` |
| Scores, rounds, the quote | `review.json` | `runs/nibs-vs-duke/0012/score.json` (round 9) and the round table in `docs/benchmarks/nibs-vs-duke-log.md`; the quote is the pacing reviewer's note on s21-s26 |
| The 9:16 re-frames | `clips-cut.txt`, `clips-v.txt` | `bin/videocraft clips cut <run> --method reframe --from … --to …` |

## The runs it needs (under `runs/`, never committed)

`nibs-vs-duke/0012` (a copy of the finished Nibs vs Duke iteration; its `clips/r1-r5` are the re-frames),
`talk/0001` (and its voice lines in `cache/voice/lines/`), `trailer-keynote/0002`, `trailer-bees/0001`,
`trailer-rigs/0001` and `0002`, `a-goat-challenges-a-fox-to-a-jump-off-2/0002`. Paths are in `trailer.toml [media]`.

## Rules it keeps

- **Real data only.** Every command, output line, path, hash, score and timing is captured, not typed in.
- **No third-party marks.** The only logo is videocraft's own pixel block (`assets/icon.svg`, read as pixels and
  assembled); no Anthropic, Claude, Mojang or Minecraft marks. The end card says it is unofficial.
- **No Mojang audio.** The bed is `videocraft audio synth --style keynote --bpm 120`, the effects come from the
  original library (`audio library`), the voices are the tool's local TTS. Footage audio is never used.
- **Captions are the game's.** Clips are chosen with their in-game captions on screen; the clean sans-serif and the
  monospace are for titles and chrome only.
- System fonts (SF Pro, SF Mono) are used to render; no font file is shipped.
