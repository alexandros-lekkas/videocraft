# Review: packets, reviewers, scores and the hill-climb

A cut is judged by reviewer agents that see **stills and numbers**, never motion or sound. This file is the process,
the shape of a review, and the **general rubric** (the TOML block at the end is read by the CLI as-is). Benchmarks
bring their own rubric file (e.g. [benchmarks/pinksheep-style.rubric.toml](benchmarks/pinksheep-style.rubric.toml)).
Owned by workstream (d).

## The loop

```sh
bin/videocraft run x.toml                         # take → cut → measure (measure/metrics.json, measure/report.md)
bin/videocraft review packet x [--rubric pinksheep-style] [--reviewers pacing,camera]   # review/packet/
bin/videocraft review run x                       # each role reviews through `claude -p` or the Anthropic API
bin/videocraft review add x review.json           # … or store a review written elsewhere (validated)
bin/videocraft score x                            # review/*.json → score.json (pass rule from the rubric)
bin/videocraft compare x/3 x/4                    # scores, metric deltas, the same shots side by side
bin/videocraft compare --side-by-side --video ref.mp4 --run x --shots list.toml -o out.mp4   # against a reference film
bin/videocraft climb x.toml --budget 3            # propose → run --parent → keep if better
```

## Side by side with a reference film

A benchmark is judged against the form of a reference video; reviewers see stills, the owner wants to *watch* both.
`compare --side-by-side` makes one 1920x1080 film of the reference (left, or top with `--layout tb`) and an
iteration (right), each a 960x540 pane:

```sh
bin/videocraft compare --side-by-side --video reference/5nksTeAYa8Y.mp4 --from 0 --to 82.2 \
    --run nibs-vs-duke/12 --shots docs/benchmarks/pinksheep-style.shots.toml \
    -o reference/compare/nibs-vs-duke-vs-reference.mp4 [--align shots|time] [--lead ours|ref] \
    [--fit auto|stretch|hold] [--audio ours|ref|none]
```

- **`--align shots`** (default) pairs reference shot N with our shot N, and a dip to black with the dip after the
  same shot. Our shot numbers come from the clip names (`s07-saw` is 7, `s16b-trophy` joins 16, so one reference shot
  can be two of ours); without numbers, shots pair in order and the extras of the longer list go unpaired. The
  reference's shots come from a shot-list TOML (`[section] from/to`, `[[shot]] n, start, seconds, camera`), or from
  `measure`'s cut detection when there is none. A follower never plays backwards: a pair out of order stays unpaired.
- **The lead** (`--lead`, default ours) plays at its own speed and sets the film's clock; each follower shot is fitted
  to the lead shot: `stretch` changes its speed to fill it, `hold` plays it at its own speed and holds its last frame
  (or cuts it short), `auto` stretches within 0.5x-2x and then holds or cuts. A shot with no partner is a black pane
  saying so. **`--align time`** plays both from their start at their own speed instead.
- **Labels** (the built-in bitmap font): the shared timecode, `SHOT n / N`, the pair's length delta (green within
  15 %, yellow within 40 %, red past it), two lanes of each film's shots at its own pace with a cursor each, and under
  each pane its side, shot, camera type, length, play speed, hold or cut, and its own source timecode; for ours also
  the clip, lens and measured subject centre and height.
- **Audio** is ours by default (`--audio ref` fits the reference's sound with `atempo`; `none` for silence).
- **Beside the video:** `side-by-side.md` and `.json` (per pair: both lengths and the delta, the reference's camera
  type, our clip, rig, lens and measured framing, and whether the camera family matches: a lead track or follow
  against a still) and `side-by-side-sheet.jpg`, one row per pair with the middle frame of each. The sheet is the
  quickest read of where the form differs; the video shows the pacing.

A third-party reference stays where it is: write the output into a git-ignored folder (`reference/compare/`), never
commit or upload it. The shot list for the benchmark holds only the timing numbers already published in
[benchmarks/pinksheep-style.md](benchmarks/pinksheep-style.md).

## What a packet holds (`review/packet/`)

| File | What |
|:--|:--|
| `strips/<nn>-<shot>.jpg` | One image per clip: its first, last and every n-th frame, 640x360 each, three across, with the shot name, the shot's own frame, the master frame and the timecode in the cut burnt into the margin. |
| `contact/sheet-<k>.jpg` | The whole cut at 4 frames a second, 320x180 tiles, six across, timecode and shot under each. |
| `cuts/cut-<nn>.jpg` | Every join: the three frames before (top row) and the three after (bottom row). |
| `sound.md`, `sound/loudness-<k>.png` | The sound sheet: every placed effect (master frame `M`, shot frame `S`, event, file, gain), voice lines with word onsets, music cues, the black gaps' loudness, and per shot the script's visible actions beside what is heard. The charts draw the master's momentary loudness and peak level over the clips and joins, with lanes for voice words, game and synth effects and music cues, 15 s a row. Every role that scores `sound` gets them. |
| `captions.md` | Every line of text per shot: from `text.json` (frames, words, cap height) and from the script's cues. |
| `report.md`, `metrics.json` | From measure: shot statistics, black, frozen, loudness, camera, framing, text rules. |
| `script.toml`, `rubric.toml` | The script as authored; the rubric used. |
| `prompts/<role>.md` | One prompt per reviewer role, naming the images and numbers that role should use. |
| `packet.json` | The manifest: run, rubric, roles, every file, the clips and their timecodes. |

Strips are the unit of judgement: big enough to judge composition and read on-screen text, labelled so a note can
cite "shot `s05-snacks`, 0:13.40" exactly.

## What reviewers are told

- They judge **stills and measurements**. They cannot watch motion or hear sound: movement is inferred from frame
  sequences and `frames.csv`-derived numbers (camera speed, jerk, subject framing); sound from the sound sheet (every
  effect and voice word on its frame) and the loudness charts. Where a criterion depends on what they cannot perceive, they say so
  and score from the evidence, not from hope.
- They cite **shot names and timecodes** for every claim.
- They give a **1-10 score per criterion** they are assigned, using the rubric's 5 and 9 anchors; pass/fail on each
  gate; the **three most valuable fixes** (each concrete enough to change in the script); and one strict JSON block.

## A review (`review/<reviewer>.json`)

```json
{
  "reviewer": "pacing",
  "model": "claude-opus-5-5",
  "rubric": "pinksheep-style",
  "scores": {"pacing": 6, "comedic_timing": 5, "energy": 6},
  "gates": {"originality": "pass"},
  "notes": [{"shot": "s21-six", "t": "0:58.50", "text": "the montage cuts are even, not on the drum hits"}],
  "fixes": [{"fix": "shorten s06-notice to 3.5 s", "why": "the longest lead track sags", "shot": "s06-notice", "t": "0:14.60"},
            {"fix": "…", "why": "…"}, {"fix": "…", "why": "…"}],
  "verdict": "one sentence"
}
```

`review add` refuses a review that misses an assigned criterion, scores outside 1-10, has no gate verdict, has
fewer than three fixes, or has notes without a shot or a timecode. `model` is `human` for a person.

## Scores (`score.json`)

Per criterion, the mean over the reviewers who scored it; the **average** of those means; the **minimum**; the gates
(a gate fails when any reviewer fails it). Pass: average ≥ `pass.average`, no criterion under `pass.minimum`, every
gate passing. The hill-climb compares averages and never keeps an iteration that fails a gate or lowers the minimum
below the parent's.

## Roles

The general roles below score one criterion each. A benchmark rubric gives the same roles several of its criteria.

| Role | Looks at | Judges |
|:--|:--|:--|
| story | contact sheets, captions, script | Is there a beginning, a turn and an end; does every shot move it on? |
| camera | strips, camera and framing numbers | Purposeful moves, framing that holds the subject, no wandering or clipping. |
| legibility | strips, captions, text rules | Can every word be read at phone size, in time, without covering faces? |
| pacing | contact sheets, cut pairs, shot statistics, dialogue pace | Shot lengths, rhythm, where the cutting speeds up and slows down; words a second and dead air in dialogue. |
| sound | loudness numbers, the sound events, dialogue pace | Bed, effects on the frame, dips, master level, how much of the film is voiced (by measurement only). |
| technical | strips, cut pairs, format checks | HUD or debug leaks, a wrong frame at a cut, pop-in, frozen or black by mistake. |

## The general rubric

```toml
name = "general"
title = "videocraft general review"

[pass]
average = 7.0
minimum = 5

[[criterion]]
id = "story"
name = "Story"
measures = "A clear premise, a turn and an ending; every shot moves the story on; the viewer always knows where and who"
anchor_5 = "Shots follow each other but could be reordered without loss; the ending stops rather than lands"
anchor_9 = "Setup, escalation and a payoff that reads from the stills alone; no shot could be cut without losing something"
numbers = ["picture.shot_stats"]

[[criterion]]
id = "camera"
name = "Camera"
measures = "Purposeful moves, steady operation, framing that holds the subject, lens choices that suit the shot"
anchor_5 = "The camera mostly works but wanders, lags its subject or repeats one setup; a subject drifts off-centre"
anchor_9 = "Every move has a reason; the subject sits where it should in every frame; no jerk, no clipping, varied setups"
numbers = ["camera", "framing"]

[[criterion]]
id = "legibility"
name = "Legibility"
measures = "Text readable at phone size and in time, never covering a face or the action, one message at a time"
anchor_5 = "Readable on a monitor but small on a phone, or held a little short, or crowding the action"
anchor_9 = "Every word reads at 390 px wide, complete for its reading time, key word highlighted, nothing covered"
numbers = ["text"]

[[criterion]]
id = "pacing"
name = "Pacing"
measures = "Shot lengths and rhythm: variety, acceleration into the climax, holds where a beat needs one"
anchor_5 = "Even, mechanical shot lengths, or one long sag; cuts arrive late; dialogue that drags (lines under 2.6 words a second, dead air between them)"
anchor_9 = "Lengths vary with the story; the cutting speeds up into the climax and holds after the punchline; dialogue brisk (about 3.2 words a second) with no dead air over 0.8 s except deliberate beats"
numbers = ["picture.shot_stats", "picture.black", "cut_check", "dialogue"]

[[criterion]]
id = "sound"
name = "Sound (by measurement)"
measures = "A bed under the picture, effects on the frame of their action, deliberate silence, a sane master level"
anchor_5 = "A music bed only, or uneven loudness, or silence where an action is shown; a story told in silent captions, or slow, gappy voice lines"
anchor_9 = "Integrated about -14 LUFS, no clipping, silence exactly at the dips, effects listed on the frames of their actions; dialogue and narration voiced and brisk, a voice for most of a talking film's runtime"
numbers = ["loudness", "dialogue"]

[[criterion]]
id = "technical"
name = "Technical cleanliness"
measures = "The frame itself: no HUD, hand, chat or debug text, no pop-in, frame-exact cuts, steady 60 fps"
anchor_5 = "An occasional leak (a name tag, a crosshair), a frame of the wrong shot at a cut, or visible pop-in"
anchor_9 = "Every strip is clean; every join is frame-exact; format checks pass; nothing frozen or black by accident"
numbers = ["checks", "picture.frozen", "picture.duplicate_at_cuts"]

[[role]]
id = "story"
name = "Story reviewer"
criteria = ["story"]
images = ["contact"]
focus = "Read the cut as a story: premise, turn, payoff. Use the contact sheets in order and the captions."

[[role]]
id = "camera"
name = "Camera reviewer"
criteria = ["camera"]
images = ["strips"]
focus = "Judge each shot's framing frame by frame in the strips, and its motion from the camera and framing numbers."

[[role]]
id = "legibility"
name = "Legibility reviewer"
criteria = ["legibility"]
images = ["strips"]
focus = "Read every piece of text in the strips as if on a phone 390 px wide; check the text rule table."

[[role]]
id = "pacing"
name = "Pacing reviewer"
criteria = ["pacing"]
images = ["contact", "cuts"]
focus = "Use the shot table, the length histogram and the contact sheets at 4 frames a second; where does it sag or rush? With dialogue, use the dialogue numbers too: words a second per line, the voice share and the dead-air stretches."

[[role]]
id = "sound"
name = "Sound reviewer"
criteria = ["sound"]
images = ["sound", "strips"]
focus = "You cannot hear. Judge from the sound sheet (sound.md: every effect, voice word and music cue on its master frame, and what is heard per shot), the loudness charts and the strips: effects on the frames of their visible actions, the bed ducked under voice, silence at the dips, the master level. With dialogue: the voice share of the runtime, words a second per line and dead air (the dialogue numbers), and whether text that matters is spoken or only shown."

[[role]]
id = "technical"
name = "Technical reviewer"
criteria = ["technical"]
images = ["strips", "cuts"]
focus = "Look for leaks (HUD, hand, crosshair, chat, name tags, debug text), wrong frames at joins, pop-in, black or frozen by accident."
```
