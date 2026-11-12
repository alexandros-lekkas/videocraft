# Sets: places to film, written as data

A set is a TOML file in `sets/` that a person or an agent can write and diff. A stdlib builder
(`cli/videocraft/sets/`) turns it into vanilla commands (batched `fill`s, `setblock`s with block states, `summon`s of
display entities) relative to an origin, plus **marks**: named points, paths and camera positions that a shot script
uses as anchors (`market-lane:shot-01`). Everything is original, built from vanilla blocks by code: no schematics, no
downloaded builds, no texture files.

A set is a **self-contained island**: its own ground plate and a backdrop ring (hills, tree lines, far cottages), so
a wide lens one block up never sees an edge or the void, placed by default at y = 230, above the cloud layer, far
from natural terrain. Each set declares its time of day and weather; the first set in a script sets the world's
unless `[world]` says otherwise.

```sh
bin/videocraft sets list                      # the sets, their time of day and marks
bin/videocraft sets ops [kerb]                # the build vocabulary: every `do`, its keys and defaults
bin/videocraft sets build market-lane         # counts, bounding box, marks, warnings (--commands f, --json)
bin/videocraft sets preview market-lane       # a take from every viewpoint → runs/set-<name>/<n>/preview/contact.png
bin/videocraft sets new pier --from-description "a wooden pier at dawn …"   # an agent drafts the file
bin/videocraft sets skin sets/skins/presenter.toml -o /tmp/presenter.png    # an original 64x64 player skin
```

## Shipped sets

| Set | Time | What it is for |
|:--|:--|:--|
| `market-lane` | 11000 (late afternoon) | The benchmark's lead tracks: a 237-block curving lane with ten stretches that each look different at one block up (market stalls and bunting, the bridge, produce, the well, the lantern street, the notice board with the Talent Night poster, the corner, the farm, the cherry orchard, the open end over a valley). Marks `shot-01` … `shot-28`, `spot-1` … `spot-6`, `stall-*`, cameras `poster`, `high-wide`, `valley`. |
| `barn-stage` | 18000 (night) | The flashback: a lit barn with a curtained stage, seven note blocks (`note-1` … `note-7`), a trophy, a rail with four seats (`rail-1` … `rail-4`), bunting, and cameras for shots 10-18 (`cam-*`). |
| `black-stage` | 18000 | Character cards on black: a subject lit by hidden light on an invisible pad, black 24 blocks away on every side (`subject`, cameras `card`, `small`, `close`). |
| `keynote-stage` | 6000 (enclosed) | For the human parody: a dark hall, a stage with a glowing lip and pools of light under hanging spots, a giant screen wall with a `text_display` slide and an original chart, tiered seats with aisle lights (`stage-center`, `podium`, `stage-walk`, `slide`, `seat-front`, cameras `cam-wide`, `cam-presenter`, `cam-side`, `cam-audience`, `cam-screen`). |
| `office` | midday | A small glass-and-concrete office in a green park: desks with monitors, a meeting table before a whiteboard slide, plants and a lounge (`desk-1`, `desk-2`, `door`, seats `meeting-1`/`-2`, standing `meeting-stand-1`/`-2`, `walk-in`, cameras `cam-desk`, `cam-meeting`, `cam-wide`, `cam-outside`, `whiteboard`). |

Skin specs for mannequins are in `sets/skins/` (`presenter`, `engineer`, `manager`): `sets skin <spec> -o x.png`, then
`skin = "x.png"` on a `kind = "mannequin"` actor. All generic: no real company names, products or logos.

## Coordinates

The set's own: x east, y up, z south, whole blocks. **The ground's top layer is y = -1 and feet stand at y = 0.** A
cell (x, y, z) spans [x, x+1] × [y, y+1] × [z, z+1]; marks and entities use the same axes as continuous points, and
a mark written `[x, y, z]` means the middle of that cell's floor (x + 0.5, y, z + 0.5).

Most entries can also place things **along a lane**: `{ along = "lane", d = 40, side = 8 }` is 40 blocks along the
lane mark's centre line from its first point and 8 blocks to the right of walking that way (negative: left).
`facing = "lane"` turns a stall, a house's door or a poster toward the nearest lane (one of the four directions).

## The file

```toml
name = "tiny-yard"
description = "A lane past one stall, for a test"
time = 6000                   # ticks; also weather, biome ("minecraft:plains"), seed (variation), headroom

[[build]]                     # entries run in order; a later one wins where they overlap
do = "ground"
from = [-30, -30]
to = [30, 30]
mix = { grass_block = 12, coarse_dirt = 1 }

[[build]]
do = "lane"
points = [[-28, 0], [0, 3], [28, 0]]
width = 5
mix = { cobblestone = 3, andesite = 1 }
center = { block = "smooth_stone", width = 1 }
mark = "lane"                 # the centre line is now a path mark, and `along = "lane"` works below

[[build]]
do = "stall"
at = { along = "lane", d = 20, side = 4.5 }
facing = "lane"
colors = ["red_wool", "white_wool"]
mark = "stall"

[[build]]
do = "kerb"                   # props right at both kerbs, facing the lane, where nothing stands yet
from = 0
to = 56
lamps = 7
props = { barrels = 2, planter = 2, bench = 1 }

[[build]]
do = "backdrop"               # hills all round the plate: no edge, no void, from anywhere on it
from = [-30, -30]
to = [30, 30]
width = 20
height = [4, 16]

[[mark]]
name = "walk"
along = "lane"
from = 10
to = 30

[[mark]]
name = "wide"
eye = [0, 6, 14]
look = [0, 0, 0]
fov = 70
```

`[[part]]` defines a piece once (`name`, its own `build` list, built facing south); `do = "part"` places it with
`rotate`, `mirror` and a `seed` for variation.

### The vocabulary

`bin/videocraft sets ops` prints every op with its keys and defaults (from the code, so it is never out of date).
In short:

- **Ground and paths:** `ground` (a plate with seeded patches), `paint` (repaint the top layer, an area or a
  stretch of a lane: `along`, `d = [from, to]`, `width`, `only`), `lane` (a smooth curve with a centre line and a
  ragged edge; `mark` exports it), `stream`, `bridge` (straight, or `along` a curving lane), `crops` (`avoid` a lane).
- **Buildings:** `house` (walls with trim and window rhythm, shutters, window boxes, a door on the lane, gabled or
  hipped roof with overhang, chimney, a lit inside), `roof`, `shell` (a room: floor, walls, ceiling, posts, beams,
  windows), `box`, `carve`, `blocks`, `column`.
- **Dressing:** `stall` (counter, striped awning, goods, lantern), `kerb` (a prop every few blocks at both kerbs:
  lamp, barrels, crates, planter, pots, hay, pumpkins, fence, banner, bench, bush, woodpile, sacks, lantern,
  tallflowers), `bunting` (flags across a lane, or between any two points indoors), `fence`, `lamp`, `pile`, `well`,
  `cart`, `pots`, `tree`, `bush`, `scatter`.
- **Light:** `light` (hidden light blocks: fill light with no visible source); lanterns and candles are the
  motivated light.
- **Backdrop:** `backdrop` (a ring of hills with trees and far cottages; `open` turns one side into a valley).
- **Pictures and text:** `poster` (a framed board with `text_display` lines and pixel art drawn as an inline grid of
  block-display "pixels"), `text`, `display` (a block at any size), `item_frame`, `entity`.

Blocks are placed without block updates (strict fills: flowers and lanterns never pop off, water never runs), so the
builder joins fences, walls, panes and stair corners itself, makes leaves persistent, completes two-block plants and
drops stray floating leaf tufts. `sets build` warns about any other block not joined to the ground.

### Marks

| Mark | Keys | In a script |
|:--|:--|:--|
| point | `at`, `facing` (a direction or a yaw) | `{ anchor = "set:mark", offset = [0, 0, 1] }` → `[x, y, z]`; `{ yaw = "set:mark" }` → its yaw |
| path | `path = [[x, y, z], …]`, or `along` a lane with `from`/`to` (blocks), `offset` (to the right), `reverse` | `{ path = "set:mark", from = 0, to = 1, reverse = true }` → points; `{ anchor = "set:mark.end" }` |
| camera | `eye`, `look` (a point or a mark name), `fov` | `camera = { view = "set:mark" }` → a `fixed` rig; `{ anchor = "set:mark.look" }` |

Every mark is also in the plan's `world.anchors` (and `world.paths`, `world.views`) for the runtime.

## In a script

```toml
[[world.set]]
name = "market-lane"          # sets/market-lane.toml
at = [0, 230, 0]              # where its origin goes (default [0, 230, 0])
rotate = 0                    # 0, 90, 180, 270 clockwise from above; mirror = true flips east and west
as = "lane"                   # the prefix of its marks (default: the set's name), to place one set twice
```

The set is built when the script compiles and staged before the script's own stage cues: one batched, checked
`command` cue with the set's box as its `forceload` key (the runtime forceloads it in 256-chunk pieces and waits until
every chunk has loaded), holding every fill, setblock and summon, then a settle wait so the client draws it. The script's own stage cues start after that.
A take whose set has a failed command fails naming the command.

## Previews

`sets preview <name>` films a short fixed shot from: every camera mark; two overviews; for every path mark a low
wide lens (one block up, 105°, pitched 5° down) at its start looking along it and at its end looking back (what a
lead track sees); for every point mark with a facing, a low view from it. One frame of each goes to
`<run>/preview/<nn>-<view>.png` and all of them to `<run>/preview/contact.png` (`views.json` is the legend).
**Look at the low views**: from one block up, only what stands within a few blocks of the path is in frame.

## What the previews taught (November 2026)

- A low wide lens sees the road and whatever stands 3-10 blocks off its centre line, nothing else. The first
  market-lane put stalls 6 and cottages 13-20 blocks off a 7-wide lane, and every lead-track view was grass verge
  and cobbles. Now the lane is 5 wide, stall fronts are at 4.5, `kerb` props at 3.5-4, cottage doors at 7-8.
- Stretches must differ in what is beside the lens, not in what is far away: each has its own props, colours and
  lane surface (`paint` along the lane). `dirt_path` sits lower than its neighbours and reads as a trench in a mix;
  use it whole or not at all.
- A straight `bridge` across a curving lane put the lead track's camera on a rail; build it `along` the lane.
- A `crops` rectangle between two lane points crosses the lane at a bend; give it `avoid = "lane"`.
- At night inside, light 8 fill reads as a dim brown room; 11 every four blocks with 15 keys on the stage and the
  audience reads every face and still looks like night (dark windows, warm pools).
- Black concrete with no light still measures about 3-10 of 255 behind a lit subject; that is the block's own
  colour, and it is black enough for a card.
