# The shot script

A shot script is a TOML file (or JSON with the same shape). `bin/videocraft compile <file>` checks it and prints the
plan the mod will play; every error names where it is and what is allowed. The design behind it is in
[DESIGN.md](DESIGN.md#2-the-shot-script). **Implemented** marks what works today; the rest is planned and owned by the
workstream in brackets.

## Top level

| Key | Default | Meaning |
|:--|:--|:--|
| `name` | required | Lowercase, dash or underscore, up to 48 characters. The folder under `runs/`. |
| `seed` | `1` | The take's random seed (hand, reaction times, NPC choices). Same script and seed, same take. |
| `description` | | Free text for people and reviewers. |
| `[output]` | `width = 1920`, `height = 1080`, `fps = 60` | Framebuffer pixels and frames per second. **Implemented.** |

## `[world]` (implemented)

| Key | Default | Meaning |
|:--|:--|:--|
| `seed` | random | A new world from this seed (text or number, as on the Create World screen). |
| `save` | | Instead of `seed`: a copy of the saved world `cache/worlds/<save>/` (git-ignored), made fresh for every take, so no take sees what the last one built [a]. |
| `gamemode` | `creative` | `survival`, `creative`, `adventure`, `spectator`: the player's mode in player shots. |
| `time` | `6000` | Time of day; the daylight cycle is stopped. |
| `weather` | `clear` | `clear`, `rain`, `thunder`; the weather cycle is stopped. |
| `settle` | `4.0` | Seconds after arrival before staging, and then until every section in view is drawn. |
| `preset` | `default` | For a seed world: `default`, `flat` (grass to the horizon) or `void` (nothing but a small platform at the origin); `flat` and `void` have no structures, so they make stages [a]. |
| `[[world.stage]]` | | Cues (below) run once before the first shot, never recorded. |

On arrival the world is made to hold still: mob spawning, random ticks (leaf decay, crops), fire spread, vines,
raids, traders and advancement toasts are off, new chunks generate without their animals, and the player is put on
the world spawn point (the `spawn` anchor is the same in every take of one seed).

## `[[actor]]` [b]

`id` (required), `kind` (`mannequin`), `at` (a position), `skin` (a PNG path), `name` (a tag, or none). The player is
always there as `player`.

## `[[shot]]` (implemented)

| Key | Default | Meaning |
|:--|:--|:--|
| `name` | required | Unique in the script; `stage` is reserved. |
| `duration` | required | Seconds; exactly `duration × fps` frames are recorded. |
| `camera` | required | `{ rig = "<id>", … }`, the rig's parameters below. |
| `hud` | `true` | First-person shots only: draw the hotbar, hearts and crosshair. |
| `bob` | `true` | First-person shots only: view bobbing. Always off for camera and third-person rigs. |
| `preroll` | `0` | Seconds the timeline and the rig run before frame 0, unrecorded: the shot opens with the subject already walking and the operator settled. Cues may have `at` down to `-preroll` [a]. |
| `time` | the world's | Time of day for this shot (ticks), set when it starts preparing [a]. |
| `weather` | the world's | `clear`, `rain`, `thunder` for this shot, at once (no easing in) [a]. |
| `[shot.vertical]` | | `camera` keys applied over `camera` when the output is taller than wide (a vertical re-shoot), and the re-frame `subject` (an actor id or `[x, y, z]`): [CLIPS.md](CLIPS.md#shotvertical). **Implemented** (clips). |
| `[[shot.cue]]` | | The timeline. |

Before recording, each shot waits at least one second of game time and until the world around the camera is drawn:
every chunk in reach has arrived, nothing is left to compile, the weather is at its target and the drawn section
count has held for half a second. Then the client is put back to a known state (game time, randoms, animation
frames), so the same plan gives the same `frames.csv`.

**The whole plan is checked before the world loads** [a]: unknown actions and rigs, actors that are not staged
(`[[actor]]`, a `stand_in`, or `player`), cue times outside their shot, and every rig's and action's own parameter
checks. The take fails in seconds with the first problem, naming its shot and cue (`shots.lead.camera: fov is 30.0
to 110.0 degrees, not 150.0`); the rest are in `game.log`.

## Cues

`at` (seconds into the shot, default 0), `do` (the action id), `actor` (default `player`), then the action's own keys.
Cues at the same time start in the order written.

| `do` | Keys | Status |
|:--|:--|:--|
| `command` | `command = "…"` or `commands = […]` | **Implemented.** Runs on the integrated server, output suppressed. |
| `mark` | `label` | **Implemented.** Notes the frame in `marks.json` for the edit and measure. |
| `wait` | `seconds` | **Implemented.** Holds a staging block. |
| `command` (long lists) | `commands = […]`, `forceload = [x1, z1, x2, z2]`, `strict` (`true`) | **Implemented** [a]. Runs in batches of 30 ms of server time per frame, positioned at the `spawn` anchor (so `~ ~ ~` is there); `forceload` loads the area first and waits for it; the take fails with the first command that errors (its index and the game's message) unless `strict = false`. |
| `stand_in` | `id`, `place` (position), `facing` (0), `entity` (`minecraft:mannequin`) | **Implemented** [a]. A subject for checking camera rigs, in `[[world.stage]]`: a client-side entity the runtime moves exactly. Not a character (no gait). |
| `glide` | `actor` (a stand-in), `path` (positions), `speed` (1.4), `ease` (0.5 s), `mark` | **Implemented** [a]. Along a smooth curve through the points at a steady speed, easing in and out, facing the way it goes. Its first point is where the stand-in is put on the cue's frame. |
| `walk`, `run`, `look`, `turn`, `jump`, `crouch`, `swing`, `use`, `break`, `place`, `select`, `type`, `open`, `close`, `point`, `click`, `pose` | see DESIGN.md | [b] |
| `caption`, `title`, `card`, `lower_third`, `keycap`, `clear` | see [Text](#text) | **Implemented.** |
| `<modid>:<name>` | the plugin's | Another mod's action ([DESIGN.md](DESIGN.md#6-extension-point)). |
| `sound`, `tune`, `ambience`, `particles` | see [Audio](#audio) | **Implemented** (audio). |

## Text

All text is drawn in the game (ffmpeg here has no `drawtext`), in the game's font, white with a dark round outline
and a drop shadow so it reads on any background, and captured with the frame. **Sizes are capital heights in
layout pixels**: pixels of a frame whose short side is 1080, so a size means the same at 1920x1080 and 1080x1920
(and 1280x720). They are rounded to a multiple of 7 (the font's capitals are 7 font pixels), which keeps the bitmap
letters on whole frame pixels. Nothing smaller than 44 px is allowed (it does not read on a phone). Everything sits
inside the safe area: 5% at the sides and top, 15% at the bottom (x 96–1824, y 54–918 at 1920x1080; x 54–1026,
y 96–1632 at 1080x1920). **One message at a time**: a `caption`, `title`, `card` or `lower_third` replaces the one on
screen on its own frame; a `keycap` has its own slot. Everything leaves with the cut. A message whose text does not
fit fails the take, naming the cue.

Each recorded shot with text writes `shots/<name>/text.json`: frame size, safe area (frame pixels), and per item its
`kind`, `cue`, `text`, `lines`, `first_frame`/`last_frame` (inclusive, frames of the shot's video), `shown_frame` (the
first frame with every word on screen), `complete_seconds`, `reading_seconds` (max(1.2, 0.5 + 0.3 per word)),
`box` and `cap_height` in frame pixels, how it `ended` (`hold`, `replaced`, `clear`, `cut`), and for captions every
word with its `frame` and `box`.

| `do` | Keys (defaults) |
|:--|:--|
| `caption` | `text` (a string, wrapped and balanced over at most two lines, or a list of lines); a word starting `*` is the key word (yellow, breathes). Or `words = [{ w = "Hey.", at = 0.0 }, …]`: each word pops on the frame nearest cue `at` + its `at` (seconds), exactly (the voice timeline's way in); `br = true` breaks the line before a word. `style` (`pop`: words pop in, `stagger` 0.12 s apart; `whole`: all on the first frame, no animation), `position` (`bottom`, `top`, `center`), `size` (63), `hold` (seconds after the last word lands; default until replaced or the cut; ends with a 5-frame fade), `speaker` (a name, or `{ name, color }`: a coloured tag above), `color` (`#ffffff`), `key_color` (`#ffe23b`), `shade` (false: a dark gradient behind). |
| `title` | `text` (big centred words with depth; `*` key words), `subtitle`, `style` (`pop`, `drop`: letters drop in one after another and bounce, `whole`), `position` (`center`, `top`, `bottom`), `size` (112, shrinks to fit one line, then two), `subtitle_size` (56), `color`, `subtitle_color`, `shade` (false; true or an opacity draws a soft band behind), `hold`, `fade_in`, `fade_out` (seconds). |
| `card` | A full-frame card: `background` (`#000000`), `opacity` (1.0; less lets the picture through), `title`, `subtitle`, `style` (`whole`), `fade_in`, `fade_out` (seconds; without `hold` the fade out ends on the cut), `hold`, and the sizes and colours of `title`. For end cards and graphic inserts. |
| `lower_third` | `text` (a name), `subtitle` (a line under it), `color` (the bar, `#ffe23b`), `side` (`left`, `right`), `size` (56), `hold` (slides out at its end). Slides in from the side on a dark panel at the bottom of the safe area. |
| `keycap` | `key` (its label), `press` (0.5 s after the cue: it goes down, yellow), `hold` (0.7 s after the press, then fades), `x`, `y` (its centre in layout pixels; default centred, 62% down), `size` (56, the label). |
| `clear` | `what` (`all`, `message`, `keycap`): takes it off on this frame. |

## Positions

`[x, y, z]`, or `{ anchor = "spawn", offset = [x, y, z] }`. `spawn` is the player's feet on arrival. Or on an actor,
where it stands when the position is read: `{ actor = "nibs", offset = [x, y, z] }` (world axes) or
`{ actor = "nibs", front = 3, right = 0.5, up = 1.2 }` (along the way it faces).

## Camera rigs

Every rig takes `fov` (degrees, 30 to 110; or `fov = [from, to]` eased over the shot with `fov_ease`) and `drift`
(0 to 3 degrees of slow, seeded handheld wander in yaw and pitch; default 0). Rigs that film a `subject` (an actor
id) follow where its feet are on the ground, never its head, so steps and jumps do not bob the camera; they trail it
by `lag` seconds through a critically damped operator (no overshoot), pull in front of blocks between them and the
subject (and rise a little if they would come very close) instead of passing through them, and pick the subject up at
once when a cue puts it somewhere new. All [a], **implemented**, checked in `RigMoveChecks` and `examples/rigs.toml`.

| `rig` | Keys (defaults) |
|:--|:--|
| `lead` | The lead track: the camera travels backwards in front of a subject walking toward it. `subject`, `distance` (4, in front along its smoothed heading), `height` (1.0 above its feet), `pitch` (5, down), `fov` (105), `side` (0, lateral offset to the camera's right), `yaw_drift` (0, degrees the camera swings round the subject over the shot), `swing` (false: true lets the camera arc round when the subject turns where it stands), `lag` (0.25). Holds the subject's centre and size; eases to a stop with it. |
| `chase` | Behind the subject looking over it: `subject`, `distance` (4), `height` (1.6), `look` (1.0, aim height above its feet), `side` (0), `fov` (70), `lag` (0.3). |
| `track` | Alongside, moving parallel: `subject`, `side` (`right` or `left`), `distance` (4), `height` (1.2), `look` (0.9), `ahead` (0, forward along its way), `fov` (70), `lag` (0.3). |
| `dolly` | The eye moves `from` → `to` (positions) over the shot (`ease`: `smooth`, `linear`, `out`), looking at `at` (a position) or a `subject` (with `look`, `lag` 0.4). `fov` (70). |
| `crane` | From `eye`, rises by `rise` (3; negative comes down) or moves to `to`, looking at `at` or a `subject`. `ease`, `fov` (70). |
| `locked` | A tripod at `eye` that pans and tilts to keep a `subject`, trailing by `lag` (0.5). `look`, `fov` (70). |
| `two_shot` | Two subjects in one frame: `subjects = ["a", "b"]`; the camera stands off the line between them (`side` 1 or -1) far enough that both fit side by side and head to feet with `margin` (1.0) around them, at least `min_distance` (2.5); `height` (1.4), `look` (0.8), `lag` (0.4), `fov` (60). |
| `face` | A close-up: `distance` (1.2) in front of the subject's eyes on its heading, `angle` (0, degrees round to its right), `height` (0, above the eyes), `fov` (30), `lag` (0.3). The lens never comes nearer the head than the model reaches. |
| `orbit` | `center` (position), `radius` (8), `height` (3, above the center), `from` (0°, south of the center), `sweep` (90°, clockwise from above), `look` (position, default the center), `ease` (`linear`, `smooth`, `out`), `fov` (70). |
| `fixed` | `eye`, `at` (positions; either may be on an actor, read when the shot starts), `fov`. |
| `first` | The player's own eyes; `fov`. |

Camera rigs draw a clean frame: no hotbar, hand, crosshair, chat, name tags, boss bars, toasts or held item.

## `[edit]`

`edit.json` → `cut/timeline.json` → `cut/master.mp4` (H.264, CRF 18, BT.709, the plan's size and rate) → exports,
all in `cut/`. The edit is resolved to frames before anything is encoded and written to `cut/timeline.json` (the
audio mix and measure read it); `videocraft edit timeline <run>` prints it, `videocraft edit verify <run>` proves
it (plain stretches are the source frames themselves, push-in holds are the exact nearest-neighbour crop, retimed
clips show the frames `src_map` names; `cut/verify.json`). **Frames and seconds**: where a key takes frames, an
integer is frames and a number with a decimal point is seconds.

`[[edit.clip]]`, in order (default: every shot, whole, in script order):

| Key | Meaning |
|:--|:--|
| `shot` | The shot. A shot can be used by several clips (a montage from one take). |
| `trim = [head, tail]` | Frames off the head and tail. |
| `in`, `out` | Instead of trim: the first frame and the end (exclusive): a frame, seconds, a mark label (`"landed"`), or `{ mark = "landed", offset = -6 }`. |
| `length` / `frames` | Instead of `out`: seconds or frames of source from `in`. `length = 0.25` is exactly 15 frames at 60 fps. |
| `push` | A slow push over the clip: `{ from = 1.0, to = 1.15, x, y, ease = "linear", at, until }`; `x`, `y` (source pixels, default the centre) is the point that stays put while the picture grows around it; `at`/`until` limit it to part of the clip. Or push-ins: `[{ at = "<mark or frame>", zoom = 1.5, x, y, ramp = 7, hold = 40, out = 9, cut = false }]`: a smooth zoom of `ramp` frames into a window centred on `x`, `y` (kept inside the frame), held for `hold` frames as an **exact crop scaled with nearest neighbour** (the pixel font stays crisp), then `out` frames back; without `hold` it holds to the end of the clip; `cut = true` jumps in without a ramp. |
| `speed` | A number (`2.0` double, `0.5` half), or keys `[{ at = <frame, seconds or mark>, speed = 0.4 }, …]`, linear in source frames between keys. Frames are repeated or dropped whole; `src_map` in the timeline lists the source frame of each output frame. |
| `fade_in`, `fade_out` | Frames from / to black at the clip's ends. |
| `black` | Instead of `shot`: a gap of black, in seconds. "Dip to black, hold, fade up" is `fade_out` on a clip, `black = 0.8`, `fade_in` on the next. |
| `frame`, `grade`, `label` | A look on this clip alone (below); a label for people. |

`[[edit.look]]` puts a look over a run of clips: `from`, `to` (shot names: the first clip of `from` to the last of
`to`; or clip indices from 0), `frame = { color = "#e8a23a", width = 28, glow = 12, opacity = 1.0 }` (a border with a
soft inner glow, sizes in 1080-line pixels: the flashback frame) and `grade` (`sepia`, `warm`, `cool`, `crush`,
`mono`, or `{ saturation, contrast, brightness, gamma, tint = "#rrggbb", amount }`). Grades are worked in RGB with
the BT.709 matrix. Fades include the look (a framed flashback fades up from black, frame and all).

`[[edit.export]]` with `preset`; all work for landscape and vertical masters (sizes are on the short side):

| `preset` | Output | Keys |
|:--|:--|:--|
| `x-1080p60` | `cut/x-1080p60.mp4`: 1080p, up to 60 fps, under 25 MB (quality steps down only if needed), AAC 192k | `name` |
| `readme-720p30` | `cut/readme-720p30.mp4`: 720p, 30 fps, under 10 MB, AAC 128k | `name` |
| `gif` | `cut/preview.gif`: silent loop, 640 px on the long side, smaller until under `max_mb` (6) | `from`, `seconds` (5), `max_mb`, `name` |
| `poster` | `cut/poster.png` (always written, half a second before the end) | `at` (seconds), `name` |

**Sound.** After `timeline.json` the cut calls the audio workstream's `videocraft.audio.mix.build(it)` while the
picture encodes and muxes the `cut/audio.wav` it returns as AAC 192k, cut or padded to the picture's length. With
no audio module, `[edit] audio = "none"`, `VIDEOCRAFT_SILENT=1` or `videocraft edit cut <run> --silent`, the master
has no audio stream. Music, effects and voice keys are in the audio section.

## Audio

The game is muted. Every sound the client starts while a shot is prepared or recorded is logged to
`take/shots/<name>/sounds.csv`, and the edit rebuilds the sound track from your own game assets (read from
`~/.gradle/caches/fabric-loom/assets`, decoded into the git-ignored `cache/audio/`). So anything that should be heard
must be played through the client's sound system on its frame: the actions below do that, and so must actors (their
footsteps and voices). **Implemented.**

`sounds.csv` columns (add at the end only): `frame` (the shot's frame; negative: started while the shot was being
prepared, the last 20 s are kept), `event` (`minecraft:entity.goat.step`, or `videocraft:<name>` for a synthesized
one), `file` (the variant actually chosen, `mob/goat/step3`; the same in every take of the plan), `category`
(`music` is the game's own music, ignored by the mix), `volume`, `pitch`, `x`, `y`, `z`, `relative` (1: not
positional), `attenuation_distance` (blocks), `looping`.

### Actions

Positions are `pos` (the cue's `at` is its time); without `pos` a sound is at the cue's `actor` (default the player),
or not positional with `relative = true`. Bad ids, instruments, notes or categories fail the take naming the cue.

| `do` | Keys (defaults) | |
|:--|:--|:--|
| `sound` | `id` (an event: `minecraft:entity.chicken.egg`, `block.note_block.bell`, or `videocraft:<name>`), `pos` / `relative`, `volume` (1), `pitch` (1, playback rate 0.5–2), `category` (`neutral`; `master` if relative) | One sound, on the cue's frame. |
| `tune` | `blocks` (a list of positions) or `block` (one), `notes`, `bpm` (120), `step` (0.5 beats per token), `instrument` (the block's own, else `harp`), `volume` (3, as a note block), `particles` (true), `mark` (a label noted in `marks.json` on each note's frame, for cuts on the beat) | A melody on note blocks: note *i* plays on block *i* mod *n*, on its frame, with the instrument's real sound at the note's pitch and the note particle rising from the block (as vanilla's note block). |
| `ambience` | `id`, `pos` / `relative` / actor, `every` (0.8 s mean gap), `jitter` (0.5 of the gap), `spread` (4 blocks), `volume` (0.5), `pitch` (1), `pitch_jitter` (0.1), `duration` (to the end of the shot), `category` (`ambient`) | A bed of one event repeated with seeded jitter in time, pitch, volume and place (crickets: `videocraft:cricket`). |
| `particles` | `id` (a simple particle: `heart`, `note`, `poof`, `happy_villager`, `cloud`, `flame`, `smoke`, `crit`, `angry_villager`, `splash`…), `pos` or actor, `offset` ([0, 0, 0]), `count` (8), `spread` (0.4 or [x, y, z]), `speed` (0), `every` (0: one burst), `duration` | A burst, or a stream every `every` seconds. Seeded. |

`notes`: one token per step, `-` a rest, `c4*2` a note held two steps, `c4+e4+g4` a chord; names at harp pitch
within a note block's range, `f#3` to `f#5` (or the block's note value 0–24).

Synthesized events (no game sound; the mix makes them, and they are original audio): `videocraft:kick`, `snare`,
`hat`, `crash`, `ding` (a bell), `dun` (a low sting), `sting` (a rising stab), `cricket`, `pop`, `whoosh`, `boing`.

### The mix: `[edit]` keys

| Key | Default | Meaning |
|:--|:--|:--|
| `audio` | `"game"` | `"game"`: logged game sounds from your assets. `"original"`: no byte of game audio: synthesized stand-ins for logged sounds (footstep ticks, note-block tones at the logged pitch, plops, thuds; others are left out), the synth bed instead of a game track, voice. `"none"`: no audio stream. |
| `[edit.music]` | none | `source = "synth"` (`style` = `upbeat`, `sneaky`, `tense`, `triumphant`; `bpm`; `key` such as `"a minor"`; `seed`, default the script's; `start` seconds into the bed, e.g. one bar's worth to skip the drums-only intro) or `source = "game"` (`track`: a sound file `music/game/wet_hands` or an event; `start` seconds into it). `gain` (dB, 0 is about −22 dBFS RMS), `at` (seconds in the cut where it starts), `fade_in`, `fade_out` (s), `duck` (−9 dB under voice), `through_black` (false: silent over black gaps and fading with the picture). |
| `[[edit.music.cue]]` | | `shot` and `at` (seconds in the shot), or `time` (seconds in the cut); `do` = `out` (fade to silence), `in`, `drop` (silent for `length`, default one beat, then back), `thin` (drums only), `full` (all stems; `gain` in dB to come back harder), `hit` (a crash and kick on the beat); `fade` (s). |
| `[edit.mix]` | | `sfx`, `voice` (dB), `duck` = event patterns the bed ducks under (`["entity.goat.screaming.*"]`), `lift` = dB by event pattern (`{ "*.step" = 9 }` is the default: the game logs footsteps some 30 dB under everything else). |
| `voice` | | `[{ file, shot, at, gain }]`, written by the dialogue resolver: each line placed at `at` seconds into the shot (dB `gain`), levelled, never cut at a clip end. |

Each logged sound lands at the output time of its frame (through trims, speed and black gaps), at its pitch, quieter
with distance from that frame's camera (the game's linear model, `1 − d / attenuation_distance`) and panned by its
bearing from the camera's yaw. A sound that started before a clip's first frame joins part-way only if it is long
(≥ 1 s) or looping; every sound stops at the end of its clip. The master is −14 LUFS integrated with true peak at
most −1 dBTP; `cut/audio.json` lists every placed and skipped event and the measured loudness.

Recipes (the benchmark's sound column):

- A character's "voice" on each caption: a `sound` cue (or the actor's `voice` action) at the caption's `at`, e.g.
  `id = "minecraft:entity.goat.ambient"` at the actor.
- One beat of dropout as someone looks at the lens: `[[edit.music.cue]] do = "drop"` at that moment (`length` in s).
- The bed thins to drums, then returns harder: `do = "thin"`, later `do = "full", gain = 3`.
- Silence before a reveal: a `black = 0.8` clip (the bed and effects are silent there; a `fade_out` on the clip
  before it fades the bed with the picture).
- A montage cut on drum hits: a `videocraft:kick` `sound` cue at `at = 0` of each montage shot, or a music `hit`.
- In-world music: `tune` on real note blocks (positional: panned and quieter with distance from the camera);
  `do = "out"` on the bed while it plays.
- A button at the end: `do = "hit"` then `do = "out"`.

Commands: `videocraft audio mix <run> [--original] [--mux]`, `videocraft audio events <run> [--onsets]` (what was
logged and where it was placed; `--onsets` measures each onset in a render against its frame, ±1 frame),
`videocraft audio synth -o bed.wav --style sneaky --seconds 30 [--stems]`.

## Appendix: commands that write shot scripts

| Command | What it does |
|:--|:--|
| `story` | `story new "<premise>"`, `draft`, `revise`, `build`, `show`, `diff`, `lock`, `list`: premise → bible → outline → script → a shot script (`stories/<id>/shots.toml`, named after the story) that compiles; every revision kept. [STORY.md](STORY.md) |
| `series` | `series new <story> --episodes N`, `series status <story>`: episode stories that share the story's bible. [STORY.md](STORY.md#series) |
| `make` | `make "<prompt>" [--format short\|episode\|long] [--vertical] [--dry-run]`: every story stage, then `run` (take, cut, measure); stops at the first stage that fails. [STORY.md](STORY.md) |
| `clips cut` | `clips cut <run> --moment N --method reshoot`: the range's shots as a vertical script (`clips/<n>/vertical.json`, 1080x1920, `[shot.vertical]` applied), taken and cut to a short. [CLIPS.md](CLIPS.md) |
## Checking a script (`videocraft lint`)

`bin/videocraft lint x.toml [--rubric pinksheep-style]` lists every problem at once (`compile` stops at the first);
`run` writes the same list to `lint.json` before each take. Errors: unknown keys, a cue outside its shot, an
unknown actor or camera subject, an anchor naming a set no `[[world.set]]` places, text that cannot be complete for
`max(1.2 s, 0.5 s + 0.3 s a word)` before the next text or the end of the shot, and two different kinds of text
up at once (a caption replacing a caption is fine). Warnings: an action that is not built in and not namespaced,
over 2.5 words a second, a shot longer than the rubric's `max_shot_seconds` (7.5 s for the benchmark), and `until`
or an edit clip's `in`/`out` naming a mark no cue makes. Notes: one-word montage text under the reading time, and
anchors that are not built in. The rules are in `cli/videocraft/lint.py`; the measured counterparts on the cut
are in `measure/report.md` (docs/REVIEW.md).
