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
| `save` | | Instead of `seed`: a copy of a saved world (the CLI copies it into `run-game/saves/` for the take) [a]. |
| `gamemode` | `creative` | `survival`, `creative`, `adventure`, `spectator`: the player's mode in player shots. |
| `time` | `6000` | Time of day; the daylight cycle is stopped. |
| `weather` | `clear` | `clear`, `rain`, `thunder`; the weather cycle is stopped. |
| `settle` | `4.0` | Seconds after arrival before staging, and then until every section in view is drawn. |
| `[[world.stage]]` | | Cues (below) run once before the first shot, never recorded. |

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
| `[[shot.cue]]` | | The timeline. |

Before recording, each shot waits at least one second of game time and until the world around the camera is drawn.

## Cues

`at` (seconds into the shot, default 0), `do` (the action id), `actor` (default `player`), then the action's own keys.
Cues at the same time start in the order written.

| `do` | Keys | Status |
|:--|:--|:--|
| `command` | `command = "…"` or `commands = […]` | **Implemented.** Runs on the integrated server, output suppressed. |
| `mark` | `label` | **Implemented.** Notes the frame in `marks.json` for the edit and measure. |
| `wait` | `seconds` | **Implemented.** Holds a staging block. |
| `walk`, `run`, `look`, `turn`, `jump`, `crouch`, `swing`, `use`, `break`, `place`, `select`, `type`, `open`, `close`, `point`, `click`, `pose` | see DESIGN.md | [b] |
| `caption`, `title`, `keycap`, `lower_third`, `clear` | see DESIGN.md | [c] |
| `<modid>:<name>` | the plugin's | Another mod's action ([DESIGN.md](DESIGN.md#6-extension-point)). |
| `sound`, `tune`, `ambience`, `particles` | see [Audio](#audio) | **Implemented** (audio). |

## Positions

`[x, y, z]`, or `{ anchor = "spawn", offset = [x, y, z] }`. `spawn` is the player's feet on arrival.

## Camera rigs

| `rig` | Keys | Status |
|:--|:--|:--|
| `orbit` | `center` (position), `radius` (8), `height` (3, above the center), `from` (0°, south of the center), `sweep` (90°, clockwise from above), `look` (position, default the center), `ease` (`linear`, `smooth`, `out`), `fov` (70) | **Implemented.** |
| `fixed` | `eye`, `at` (positions), `fov` | **Implemented.** |
| `first` | `fov` | **Implemented** (the player's eyes; needs actor actions to be interesting). |
| `chase`, `track`, `dolly`, `crane`, `locked`, `two_shot` | | [a] |

## `[edit]`

Today: `[[edit.clip]]` with `shot` and `trim = [head, tail]` (frames), in order; default all shots in script order.
The master export is `cut/master.mp4` (H.264, CRF 18, BT.709, the plan's size and rate). Push-ins, speed ramps,
music, sound effects and export presets: [c], see DESIGN.md.

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
| `tune` | `blocks` (a list of positions) or `block` (one), `notes`, `bpm` (120), `step` (0.5 beats per token), `instrument` (the block's own, else `harp`), `volume` (3, as a note block), `particles` (true) | A melody on note blocks: note *i* plays on block *i* mod *n*, on its frame, with the instrument's real sound at the note's pitch and the note particle rising from the block (as vanilla's note block). |
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
| `[edit.music]` | none | `source = "synth"` (`style` = `upbeat`, `sneaky`, `tense`, `triumphant`; `bpm`; `key` such as `"a minor"`; `seed`, default the script's) or `source = "game"` (`track`: a sound file `music/game/wet_hands` or an event; `start` seconds into it). `gain` (dB, 0 is about −21 dBFS RMS), `at` (seconds in the cut where it starts), `fade_in`, `fade_out` (s), `duck` (−9 dB under voice), `through_black` (false: silent over black gaps and fading with the picture). |
| `[[edit.music.cue]]` | | `shot` and `at` (seconds in the shot), or `time` (seconds in the cut); `do` = `out` (fade to silence), `in`, `drop` (silent for `length`, default one beat, then back), `thin` (drums only), `full` (all stems; `gain` in dB to come back harder), `hit` (a crash and kick on the beat); `fade` (s). |
| `[edit.mix]` | | `sfx`, `voice` (dB), `duck` = event patterns the bed ducks under (`["entity.goat.screaming.*"]`). |
| `voice` | | `[{ file, shot, at, gain }]`, written by the dialogue resolver: each line placed at `at` seconds into the shot (dB `gain`), levelled, never cut at a clip end. |

Each logged sound lands at the output time of its frame (through trims, speed and black gaps), at its pitch, quieter
with distance from that frame's camera (the game's linear model, `1 − d / attenuation_distance`) and panned by its
bearing from the camera's yaw. A sound that started before a clip's first frame joins part-way only if it is long
(≥ 1 s) or looping; every sound stops at the end of its clip. The master is −14 LUFS integrated with true peak at
most −1 dBTP; `cut/audio.json` lists every placed and skipped event and the measured loudness.

Commands: `videocraft audio mix <run> [--original] [--mux]`, `videocraft audio events <run> [--onsets]` (what was
logged and where it was placed; `--onsets` measures each onset in a render against its frame, ±1 frame),
`videocraft audio synth -o bed.wav --style sneaky --seconds 30 [--stems]`.
