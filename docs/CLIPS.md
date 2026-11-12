# Long form and clipping

Finished runs become two more kinds of video: **long form** (several runs joined into one video with chapter cards
and chapters) and **vertical shorts** (9:16, at most 60 s, cut from a moment of a run or an assembly). The code is
`cli/videocraft/clips/`; the fixture is `examples/clips/reframe.toml`.

```sh
bin/videocraft assemble <series-id | run run ...> -o <name> [--title "…" ...] [--cards game|plain|none] [--cold-open]
bin/videocraft clips find <run> [--min 15] [--max 60] [--ask]            # rank moments → clips/moments.json
bin/videocraft clips cut <run> --moment N | --from s --to s [--method auto|reshoot|reframe] [--aspect 9:16]
                                [--subject <actor id | x,y,z>] [--hook "…" | --hook none] [--pull 1.2] [--from-start]
bin/videocraft clips pack <run> [--ask]                                   # title, description, hashtags, thumbnail
```

`<run>` is an iteration as everywhere (`<name>`, `<name>/<n>`, a path); a bare `<name>` means its best finished
iteration (index.json's best, else the latest that passed and has a master). Every command ends with `RESULT`,
`VIDEO` and the folder it wrote, like `run`; `clips cut` exits 1 when a check failed.

## Long form: `assemble`

Parts are a series story id (`stories/<id>/series.json`: each episode's best run under `runs/<episode-id>/`) or a
list of runs. Each part's master is joined in order, a chapter card before each (none before the first with
`--cold-open`). The assembly is its own iteration, `runs/<name>/<NNNN>/` with `kind = "assembly"` in `meta.json`:

| File | What |
|:--|:--|
| `cut/master.mp4` | the whole: H.264 + AAC 192k, mp4 chapters (ffprobe `-show_chapters` lists them) |
| `cut/chapters.txt` | YouTube's description format, `0:00 Title` (H:MM:SS past an hour) |
| `cut/chapters.ffmeta` | ffmpeg's FFMETADATA1 chapters, the same as muxed |
| `cut/timeline.json` | `fps`, `width`, `height`, `frames`, `parts` [{index, kind `card`/`part`, title, run, out_start, out_frames, part}], `chapters`, and `clips`: every part's own timeline clips shifted into assembly frames, each with its source `run` and `part` |
| `cut/audio.wav` | the mix: each part levelled to −14 LUFS on its own (at most 12 dB up; silence stays silence), cards silent, then the whole mastered to −14 LUFS integrated, true peak ≤ −1 dBTP (`audio/loudness.py`) |
| `cut/assembly.json` | parts, per-part loudness before and inside the master, chapter problems YouTube would refuse (fewer than 3 chapters, one under 10 s, not starting at 0:00) |
| `measure/` | `measure --video` of the master |

Cards: `game` (default) draws each card in the game, one full-frame `card` shot per chapter (the title drops in,
"Part n" under it, `--label` changes the word), in one small take that is cached in `runs/chapter-cards/` and reused
while the titles and frame size are the same; `plain` draws them with the review packets' bitmap font (no take);
`none` joins the parts back to back. Parts of another size or rate are scaled and padded into the first part's
frame and resampled to its rate.

## Moments: `clips find`

Nothing watches the video. Every signal the run already holds is mapped into master time through the timeline
(`clips/timemap.py`; an assembly maps through its parts to their own runs):

| Signal | From | Counts as |
|:--|:--|:--|
| words and lines | `text.json` caption words (a word lasts until the next of its line; a line's last word 0.35 s), voice timings in `edit.json` `voice[].words` when the dialogue resolver writes them | a line start is a setup; no range starts or ends inside a word |
| key words | the `*key` words | payoffs |
| outline beats | `stories/<id>/outline.md`: `## n. name (purpose, ~length, shots a-b)`; shot n is a shot whose name carries n, else the n-th | a setup/turn/escalation beat start is a setup, a payoff/button beat end a payoff |
| jokes | the outline's comedy pass table (joke, beat, how it lands) | a range that holds a whole beat holds its jokes |
| marks | `marks.json`; labels with `payoff`, `punch`, `reveal`, `button`, `scream`, `egg`, `hit`, `end`, ... | payoffs |
| sound events | `sounds.csv`: a goat's scream, an egg, a level-up, an explosion, a ram, a hit (footsteps and ambience do not count) | payoffs |
| loudness | 100 ms levels of the master's audio; peaks ≥ 8 dB over the median | payoffs |
| cuts | the master's clip boundaries | where ranges like to start and end; cut density |
| a reviewer (`--ask`) | `agents.ask` over the review packet's contact sheets (if any), the outline and the candidates | its 1-10 score (half weight), a better title and hook |

A candidate starts on a setup and ends on a payoff plus a beat (0.8 s), 15 to 60 s long (`--min`, `--max`); its
start snaps back to a shot boundary within 1.5 s (else the start of the line it is in), its end forward to one
(else the end of the word it is in). Scores add what the range holds (divided by √(length/10) so long ranges do not
win by size), a strong payoff in its last 1.5 s, a setup at its start, cut density, and a penalty outside 20-35 s.
Overlapping candidates (over half of the shorter) are suppressed. `clips/moments.json` holds the ranked moments
(`n`, `start`, `end`, `frames`, `score`, `reasons`, `title`, `cold`, `hook`, `shots`) and every event it scored. A
master shorter than `--min` is one moment, the whole of it. A moment is **cold** when it neither starts the video
nor starts on a setup beat; a cold moment gets a hook (from its joke, beat or line; none when it has only sounds).

## Vertical shorts: `clips cut`

Into `clips/<n>/` (the moment's number, or `r1`, `r2`, ... for `--from/--to` ranges): `short-1080x1920.mp4`
(H.264 high, AAC 192k, under 50 MB: the quality steps down if not), `clip.json` (method, range, checks, per-clip
layout and subject measurements, text problems, loudness), `audio.wav`, and the method's own files.

**Re-shoot** (the default when the run has its script; the one only this tool can do): the shots in the range are
taken again at 1080x1920 from the same script, so the performance is the same and the game lays the text out for
the vertical frame itself. Per shot, `[shot.vertical]` adjusts the camera for 9:16 (below); `--pull` scales every
rig's `radius`, `distance` and `min_distance`; only the shots in the range are taken, or with `--from-start` every
shot from the first up to the last one needed (when a shot leaves state the next one starts from); captions without a `size` get 77 (the default is 63); screen
positions (`x`, `y` of a keycap or other text) keep their place in the frame. A `fixed` shot (with no `[shot.vertical]` camera) whose
staged subject leaves the 9:16 window of the landscape frame in over a tenth of the range is re-shot as `locked` on
that subject from the same eye: a locked-off vertical frame cannot hold a subject that crosses a wide one, so the
camera pans, as an operator shooting vertical would (`clip.json` notes say which shots). The edit is the same edit cut to the
range: each clip's `in`/`out` frames, its speed, look and frame; push-in points are mapped into the vertical frame;
a fade is kept only where the range keeps that clip's edge. The vertical take is an ordinary iteration of
`runs/<name>-vertical/` (its script is `clips/<n>/vertical.json`). Its text is checked against the vertical safe
area (x 54-1026, y 96-1632): `captions_in_safe_area` in `clip.json`. A re-shoot that fails falls back to re-framing
when `--method auto`, and says so.

**Re-frame** (assemblies, runs without a script, or `--method reframe`): a 608x1080 crop of the 16:9 master scaled to
1080x1920 that follows the subject, cut by cut (a cut resets it; nothing pans across a cut):

- the subject: `--subject` (an actor id, or `x,y,z` a world point), else the shot's `[shot.vertical] subject`, else the
  rig's subject (frames.csv logs it), else actors.csv's actors; projected through each frame's camera
  (`measure/camera.py`) and through the clip's push-ins into master pixels; frames where it is not seen hold;
- the operator: a critically damped follow (ω 7/s) looking 0.3 s ahead, with a dead zone of ±12 % of the crop (it
  holds while the subject stays near the centre), at most 1.5 crop widths a second and 6 a second²; it starts each
  clip already framed on the subject's first 0.3 s;
- the layout: `follow`, or `fit` (the whole frame across the width over a blurred, darkened fill of itself) when two
  subjects are further apart than 0.8 of the crop (or a two-shot whose second subject is not logged), or the take drew text wider than the crop or outside the crop's
  path (re-framing cannot re-lay text, so it never cuts words off).

`clip.json` `subject` measures what it got: frames seen, inside the crop, inside its centre 60 %, the crop's
greatest speed and acceleration; `subject_in_crop` passes at 98 %.

Both methods: the sound is the master's own mix over exactly the same frames (the vertical take is the same
performance), faded 15 ms at both ends and re-mastered to −14 LUFS (`loudness` is checked unless the source is
silent; a peaky slice gets up to eight passes). A short never dips to black at its end: it ends on the payoff plus a beat, so it loops. A cold moment's
hook (`--hook` to set it, `--hook none` to drop it) is drawn in the first second: in the game as a `title` at the
top when re-shot (the next caption replaces it, one message at a time), as a bitmap-font band when re-framed.

### `[shot.vertical]`

| Key | Meaning |
|:--|:--|
| `camera` | Camera keys applied over the shot's `camera` when the script's output is taller than wide (a vertical re-shoot), e.g. `[shot.vertical] camera = { distance = 3.5, fov = 60 }`. A landscape take ignores them. |
| `subject` | Re-frame only: what the crop follows in this shot (an actor id or `[x, y, z]`). |
| `note` | Free text. |

## Packing: `clips pack`

For each `clips/<n>/clip.json`: `meta.json` with `title` (the moment's joke, beat or key line, else the biggest text on
the thumbnail, at most 60 characters), `description` (its longest line quoted, the story's logline, "Filmed entirely
inside Minecraft."), `hashtags` (`#minecraft #shorts #minecraftanimation`, the bible's character names, key words),
and `thumbnail` (`thumbnail.png`): every 6th frame is scored from the logs: the biggest complete text on screen and a
key word on it, the subject's size and whether its head faces the camera (actors.csv), and the frame's contrast; a
dark frame never wins. `--ask` has a model rewrite the title, description and hashtags from the same facts and the
thumbnail.
