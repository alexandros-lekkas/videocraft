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

