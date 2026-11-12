# videocraft design

> Agent-directed video for Minecraft Java 26.3. A person or a coding agent writes a shot script. One command
> launches a hidden game, performs the shots, captures the frames from the game, cuts and exports the video,
> measures it and has reviewer agents score it. Every stage writes its output to disk, so an agent can compare
> iterations and keep the best ("hill-climb").

The system was prototyped as the launch-video recorder in T3 Craft (`DemoRecorder`, `DemoHand`, `DemoOverlay`,
`scripts/demo/*.sh`). videocraft is the generic version: nothing in it knows about T3 Craft.

```
 script.toml ──compile──▶ plan.json ──mod: take──▶ shots/<name>/video.mp4 + frames.csv + marks.json
   (author)     (CLI)                 (hidden game)                         │
                                                                            ▼
 score.json ◀──review── review/*.json ◀── measure/metrics.json ◀──measure── cut/master.mp4 ◀──cut── (CLI + ffmpeg)
     │                    (agents)                                 (CLI)
     └──── hill-climb: the agent edits the script, runs again with --parent, compares the scores ────┘
```

## 1. Decisions

| Decision | Choice | Why, in one line |
|:--|:--|:--|
| Script format | **TOML**, compiled by the CLI to canonical **JSON** (`plan.json`) | Comments, no indentation errors or `no`/`on` coercions (YAML's failure modes for agents), Python reads it with stdlib `tomllib`, and one cue per `[[shot.cue]]` block makes diffs between iterations one hunk per change. |
| What the mod reads | `plan.json` only, with every default filled in | The mod parses one shape with Gson and never guesses; two scripts that mean the same compile to the same plan. |
| CLI language | **Python 3.11+, standard library only** | Nothing to install (`bin/videocraft` runs from a checkout); tomllib, json, subprocess and http are all stdlib; T3 Craft's `scripts/mc` already proved it. |
| Mod ↔ CLI | **Take directory + system properties** for the take; a **loopback HTTP control port** (127.0.0.1:25750) for status and quit | A take is a batch job: a file in, files out, a verdict in `result.json` is the simplest thing that is reproducible and inspectable. The control port is for a running client (status, clean stop now; a warm client that takes several plans later). |
| Time | **Fixed step per captured frame** (1/fps of game time per frame) | Video is steady however slow capture is; the take is a function of the script and the seed, not of the machine. |
| Capture | **Framebuffer → raw RGBA → ffmpeg child per shot**, near-lossless (CRF 12) | No screen capture, no window; the cut re-encodes once. Proven at 1080p60 (65–85 fps real time on an M4 Pro). |
| Text | **Drawn in the game**, on a HUD layer that also draws over screens | Homebrew ffmpeg has no `drawtext`; the game's font matches the game; a Screen-based caption cannot overlap another screen. |
| Camera | **videocraft's own rigs** through a camera mixin; no camera mod dependency | No camera mod is both on Fabric 26.3 and scriptable (section 7). |
| Extension | **Fabric entrypoint `"videocraft"`** + a small `io.github.alexandroslekkas.videocraft.api` package | Another mod adds actions and rigs without videocraft depending on it, and without itself depending on videocraft at runtime. |
| Java package | `io.github.alexandroslekkas.videocraft`, one subpackage per workstream | The old package named a domain we do not own; `io.github.<user>` is the conventional namespace for a GitHub-hosted project, with the hyphen of `alexandros-lekkas` dropped because a package name cannot contain one. Packages are the ownership boundary; cross-package API is `public`, the rest package-private. |

## 2. The shot script

Full reference: [SCRIPT.md](SCRIPT.md). The shape:

```toml
name = "hello"            # lowercase-dash; the run store folder
seed = 1                  # the take's random seed: hand jitter, reaction times, NPC choices

[output]                  # framebuffer pixels and frames per second (defaults shown)
width = 1920
height = 1080
fps = 60

[world]
seed = "videocraft"        # a new world from this seed …
# save = "castle"         # … or a copy of cache/worlds/castle (never both)
time = 1000               # the daylight and weather cycles are stopped for the take
weather = "clear"
gamemode = "creative"
settle = 4.0              # seconds to let chunks load and draw after arrival

[[world.stage]]           # staging: actions run before the first shot, never recorded
do = "command"
commands = ["fill ~-3 ~-1 ~-3 ~3 ~-1 ~3 grass_block", "summon minecraft:mannequin ~2 ~ ~"]

[[actor]]                 # someone besides the player (workstream b)
id = "alex"
kind = "mannequin"
at = { anchor = "spawn", offset = [3, 0, 0] }
skin = "skins/alex.png"

[[shot]]
name = "arrive"
duration = 4.0
camera = { rig = "chase", subject = "player", distance = 4, height = 1.6, lag = 0.3 }

[[shot.cue]]
at = 0.0
do = "walk"
actor = "player"
path = [{ anchor = "spawn" }, { anchor = "spawn", offset = [8, 0, 3] }]
sprint = true

[[shot.cue]]
at = 0.4
do = "caption"
text = ["Build *anything."]

[[shot.cue]]
at = 3.2
do = "mark"
label = "landed"

[edit]
music = { track = "minecraft:music/game/wet_hands", start = 13.4, loudness = -16 }

[[edit.clip]]
shot = "arrive"
trim = [0, 12]            # frames off the head and tail
push = [{ at = "landed", zoom = 1.5, x = 600, y = 300, hold = 40 }]

[[edit.export]]
preset = "x-1080p60"      # also readme-720p30, gif, poster
```

What it expresses, and who implements it:

| Part | Keys | Workstream |
|:--|:--|:--|
| World | `world.seed` or `world.save`, `time`, `weather`, `gamemode`, `settle`, `world.stage` cues (any action, typically `command`: blocks, entities, inventory via `item replace`) | a |
| Actors | `[[actor]]`: the player is always there; `kind = "mannequin"` NPCs; `skin` (a local PNG) | b |
| Shots | `[[shot]]`: `name`, `duration`, `camera` (rig + parameters), `hud`, `bob`, `[[shot.cue]]` timeline | a (shot, rigs), b (actor cues), c (text cues) |
| Cues | `at` (seconds into the shot), `do` (an action id), `actor`, the action's own parameters | whoever owns the action |
| Marks | `do = "mark"` or any action calling `ShotContext.mark`; written to `marks.json` in frames | a (mechanism), everyone (use) |
| Edit | `[edit]`: `[[edit.clip]]` order, `trim`, `push` (push-ins), `speed` (ramps), `music`, `sfx`, `[[edit.export]]` | c |

**End conditions.** v1: every shot ends on `duration`. Planned (a): `until = "<mark label>"` with `duration` as the
upper bound, so a shot can end when an action reports its beat (a walk arriving) without guessing seconds; a shot
whose `until` never comes fails the take.

**Positions** everywhere are `[x, y, z]` or `{ anchor = "<name>", offset = [x, y, z] }`. `spawn` (the player's feet on
arrival) always exists; actions can define more (`ShotContext.anchor(name, at)`), and plugins define their own
(T3 Craft: `t3craft:desk/3`).

**Actions v1 (built-in ids).** Runtime: `command`, `mark`, `wait`. Actors: `walk`, `run`, `look`, `turn`, `jump`,
`crouch`, `swing`, `use`, `break`, `place`, `select`, `type`, `open`, `close`, `point`, `click`, `pose`. Text:
`caption`, `title`, `keycap`, `lower_third`, `clear`. Rigs: `orbit`, `fixed`, `first` (built), `chase`, `track`,
`dolly`, `crane`, `locked`, `two_shot` (planned). Every action validates its parameters when created and fails the
take with a message naming the script location.

**Actors: realistic and out of scope.** The player is played, not animated: held movement keys through a scripted
`ClientInput`, the view turned by the hand model, so acceleration, view bobbing, sprint FOV and the walk cycle are
the game's own. NPCs are vanilla **Mannequins** (player-shaped, skinnable via a profile, posable, no AI; T3 Craft uses
them for its agents), moved by videocraft each tick with the walk animation driven by a mixin. Skins: the player's via
a mixin on the local skin lookup reading a PNG; Mannequins via their profile. **Out of scope:** fake players with
network connections, pathfinding (paths are given in the script), mob AI direction beyond vanilla commands, multiplayer
servers, other dimensions mid-take, recording sound from the game (audio is mixed in the edit).

## 3. The boundary between mod and CLI

The mod is a **dev-time tool**: inert unless started with `-Dvideocraft.take=<dir>`. The CLI is the only thing that
starts it.

```
bin/videocraft run x.toml
  ├─ compile x.toml → runs/x/0007/plan.json (+ edit.json); copy to take/plan.json
  ├─ prepare run-game/ (muted options.txt, never a real Minecraft folder), take the one-client pid lock
  ├─ ./gradlew runClient -Ptake=<take dir> -PgameDir=run-game -Pffmpeg=<path> -PcontrolPort=25750 -Pwidth=960 -Pheight=540
  │     the mod: Director plays plan.json, writes take/{result.json, shots/*}, quits
  │     the CLI: streams the log to take/game.log, enforces --timeout (POST /quit, then kill the process group)
  ├─ cut (edit.json + take/) → cut/master.mp4, poster.png
  ├─ measure → measure/metrics.json
  └─ prints RESULT / VIDEO / RUN / LOG / TIME; exit 0 PASS, 1 FAIL, 2 no verdict
```

System properties (set by `build.gradle` from `-P` properties): `videocraft.take`, `videocraft.hidden`,
`videocraft.port`, `videocraft.ffmpeg`. The control port (`ControlServer`) is loopback only, refuses a non-loopback
`Host` and any `Origin` (browsers), and today serves `GET /status` and `POST /quit`. Planned (a): `POST /take` to
play another plan in the same warm client (skips the ~10 s boot and world creation for each hill-climb step) and
`POST /command`.

**Inside a take** (`Director`): `BOOT` (title screen; checks the framebuffer is the planned size and resizes the
window once if not) → `WORLD` (create from seed, or open the save the CLI copied in) → `ARRIVE` (anchor `spawn`,
game options, time and weather frozen, actors staged) → `SETTLE` (wall-clock settle, until every section is drawn)
→ the clock becomes fixed → `STAGE` (world.stage cues) → `SHOTS` (each: prepare ≥ 60 frames and until drawn, then
record exactly `duration × fps` frames) → `FINISH` (encoders exit) → `result.json` → quit.

**Frame alignment** (do not break it): the clock mixin runs once per frame before ticking and rendering. It first
grabs the frame rendered last, then advances the shot by one frame, then returns `+1/fps` of game time. So row `n`
of `frames.csv`, the `n`th frame of `video.mp4` and `ShotContext.frame() == n` are the same frame.

## 4. The run store

```
runs/<script name>/
  index.json                 every iteration: verdict, scores, parent (rewritten by each stage)        (d)
  latest -> 0007
  0007/
    meta.json                iteration, parent, created, script and plan hashes, videocraft commit      (d)
    script.toml              the script as authored                                                    (d)
    plan.json                what the mod played                                                       (d)
    edit.json                the edit as compiled                                                      (d)
    take/                                                                                              (a)
      plan.json  result.json  game.log
      shots/<name>/video.mp4     the shot as captured
      shots/<name>/frames.csv    frame,seconds,cam_x,cam_y,cam_z,cam_yaw,cam_pitch,fov,player_x,…,on_ground
      shots/<name>/marks.json    [{label, frame, value?}] in frames of this shot
      shots/<name>/ffmpeg.log
      shots/<name>/text.json     every text item: frame range, box in pixels, cap height, words   (c, planned)
    cut/master.mp4  cut/<export>.mp4  cut/poster.png  cut/graph.txt  cut/cut.json                    (c)
    measure/metrics.json     format checks; motion, text and safe-area metrics                         (d)
    measure/contact.png      a contact sheet of the cut for reviewers                                  (d)
    lint.json                script lint before the take                                               (d)
    review/<reviewer>.json   {reviewer, model, scores: {criterion: 1-10}, notes: [{t, text}], verdict}  (d)
    score.json               the aggregate the hill-climb compares                                     (d)
    notes.md                 what changed from the parent and why (written by the agent)
cache/worlds/<name>/         pristine saved worlds for world.save; copied into run-game/saves per take  (a)
```

Paths are a contract: add, never rename. `frames.csv` columns: add at the end only.

## 5. Text, layout and the edit (rules that are measured)

From the prototype, enforced by `lint`/`measure` (d) and honoured by the text actions (c):

- Safe area: x 96–1824, y 54–918 at 1920×1080. Nothing important outside it.
- One message at a time: captions never share the screen with a toast, a card or a speech bubble.
- A message is complete on screen for at least `max(1.2 s, 0.5 s + 0.3 s per word)`.
- Capital height under 44 px at 1920 wide does not count as shown at phone width.
- The GUI scale is clamped to 4 at a 1920×1080 framebuffer, so UI text can only be enlarged by an edit push-in;
  the held part of a push-in is an exact crop scaled with nearest neighbour, so the pixel font stays crisp.
- A mouse pointer at rest is frozen to the pixel and clicks only after it has stopped.
- Music is read from the local game asset cache (`~/.gradle/caches/fabric-loom/assets`) at export time, levelled to
  about −16 LUFS. Mojang audio is never committed.

## 6. Extension point

```java
// In the other mod. fabric.mod.json: "entrypoints": { "videocraft": ["com.example.t3craft.T3Shots"] }
// build.gradle: modCompileOnly + modLocalRuntime on the videocraft jar (dev only; players never need it).
public final class T3Shots implements io.github.alexandroslekkas.videocraft.api.VideocraftPlugin {
	@Override public void register(Registry r) {
		r.action("t3craft:open_card", (params, shot) -> s -> { /* … */ return true; });
		r.rig("t3craft:desk", (params, shot) -> new DeskRig(params, shot));
	}
}
```

`io.github.alexandroslekkas.videocraft.api` is the whole contract: `VideocraftPlugin`, `Registry`,
`ActionType`/`Action`, `RigType`/`CameraRig`, `Pose`, `View`, `Actor`, `ShotContext`, `Params`. Plugin ids must be namespaced with the plugin's mod id; videocraft
refuses a bare id from a plugin and a duplicate from anyone. The API is versioned with the plan (`Plan.VERSION`);
breaking it needs a DECISIONS entry. T3 Craft is the first customer: its office staging (`/_qa` fixture calls, agent
poses, desk anchors, opening a card) becomes a plugin in T3 Craft's repository.

## 7. Existing mods (checked on Modrinth, 2026-11-11, Fabric 26.3)

| Mod | 26.3 Fabric | Verdict |
|:--|:--|:--|
| Fabric API | 0.166.2+26.3 (build uses 0.161.0+26.3) | Required. |
| Flashback | 0.43.6 (2026-09-21); "do not redistribute" | Not used. Its exporter is the right model (fixed timestep, exact tick math, RNG reset) and videocraft copies the idea, but it is driven from its ImGui editor, has no command or API for scripted cameras or export, and records a replay first. |
| ReplayMod | 26.3-2.6.28; GPL-3.0 | Not used: GUI-only render queue, records then renders. |
| CMDCam / CinematicTools | No Fabric build for 26.3 (NeoForge only) | Out. Its command-driven paths were the closest match. |
| Camera Traveling, Free Camera, CineCam, Zocular | Not on 26.3, or not scriptable | Out; videocraft's rigs cover it. |
| Freecam | 1.5.1; MIT; keybind-driven | Out: nothing for a hidden client. |
| Axiom | 6.1.5; editor UI | Out; a builder's tool, not capture. Staging uses commands and saved worlds. |
| Sodium | mc26.3-0.9.2-fabric; PolyForm Shield | Not in the pack until capture parity (frame grab, HUD layer, camera mixin) is verified with it. Capture is already faster than real time without it. |
| Lithium, FerriteCore, ImmediatelyFast | mc26.3-0.26.3, 9.0.0, 1.17.1+26.3; LGPL/MIT | In the pack: server tick, memory, HUD text speed; none touches the frame path. |
| ModernFix | No Fabric 26.x | Out. |

The pack is defined in `modpack/pack.toml`; `videocraft modpack` (d) turns it into a Modrinth `.mrpack` that
references those downloads and carries only videocraft's jar in `overrides/`.

## 8. Known gaps (decide before they bite)

- **The integrated server runs in real time.** The client is fixed-step, the server is not: when capture runs faster
  or slower than real time, server-side motion (NPCs moved on the server, mobs, block updates) drifts against the
  video. Workstream (a) locks the server to the frame clock (freeze the tick-rate manager and step one server tick per
  `fps/20` captured frames). Until then, move NPCs client-side.
- **Window scale.** The CLI asks for 960×540 points on a Mac (2× displays) and 1920×1080 elsewhere; the mod checks the
  framebuffer and resizes once (`WorldBoot.frameSize`). Verified on a 2× Mac only.
- **Platforms.** Verified on macOS (Apple silicon, OpenGL backend). Linux needs `xvfb-run`; Windows is untested.

## 9. Workstreams

Four people (or agents) start in parallel from this commit. Ownership is by path; anything outside your paths is a
change request to its owner (or a one-line hook you add and tell them about). Shared files: `build.gradle`,
`src/main/resources/*.json`, `AGENTS.md`, `CHANGELOG.md` — small edits only, rebase often.

### (a) Mod runtime: capture, clock, hidden window, interpreter, camera rigs

- **Goal.** Takes are deterministic and robust: the same plan and seed give the same frames; every failure is a
  `FAIL` with a reason an agent can act on. A rich set of camera rigs that move like an operator.
- **Owns.** `src/main/java/io/github/alexandroslekkas/videocraft/{Videocraft,VideocraftLog,HiddenWindow}.java`,
  `director/`, `camera/`, `plan/`, `mixin/`, `devmixin/`, `api/` (the contract: additive changes; tell everyone), `src/smoke/java/**/Rig*`,
  `PlanChecks`, `build.gradle`, `src/main/resources/{fabric.mod.json,videocraft*.mixins.json}`, `cache/worlds/` logic.
- **Builds.** Server tick lockstep; `until` end conditions; rigs `chase`, `track`, `dolly`, `crane`, `locked`,
  `two_shot` following a ground reference through `Operator` (never the head: no bob on steps or jumps); saved-world
  takes (`world.save` copied from `cache/worlds/`); a warm client (`POST /take`); `hud`, `bob` per shot; fail fast on
  an unknown action or rig before the world loads.
- **Depends on.** Nothing new. Provides `ShotContext`, `Registry` and `Actor` to b and c.
- **Acceptance.** `./gradlew build` passes with new `RigChecks` cases for every rig. Two takes of the same plan give
  byte-identical `frames.csv` and frame-for-frame identical video (compare `framemd5` of `video.mp4`); a plan with a
  bogus rig fails in under 20 s with a message naming the shot. A 10 s `chase` shot of a player walking has camera
  vertical jerk below a threshold (d measures) while the player jumps.

### (b) Actors: the human input model, movement and actions, NPCs

- **Goal.** A player that moves like a person and NPCs that can share the frame with it.
- **Owns.** `src/main/java/io/github/alexandroslekkas/videocraft/actor/` (`Hand`, `Cast`, `PlayerActor`, `Actions`, new
  files), its smoke checks (`src/smoke/java/**/Actor*Checks.java`, `Hand*Checks.java`), and any actor mixins under `mixin/actor/`
  (add them to `videocraft.mixins.json`; tell a).
- **Builds.** `PlayerActor` with a scripted `ClientInput` (held keys) and `Hand.Look` turning the view every frame
  (port the prototype's `Walk`: look-ahead path following, sprint released before forward, arrive facing a target,
  jump what a sprint cannot clear, never a door); actions `walk`, `run`, `look`, `turn`, `jump`, `crouch`, `swing`,
  `use`, `break`, `place`, `select`, `type`, `open`, `close`, `point`, `click`; the drawn pointer's hand model and real
  clicks into screens (hand the pointer's drawing to c's `TextLayer`); Mannequin NPCs (`kind = "mannequin"`: spawn,
  skin, `walk` along a path with the walk animation, `look`, `pose`); the player's skin from a PNG.
- **Depends on.** `api.Actor`, `api.ShotContext`, `api.Registry` (a); `TextLayer.add` for the pointer (c).
- **Acceptance.** An example `examples/walk.toml` (player walks a bent path, jumps a block, turns 120° to face an
  NPC that waves) passes; `frames.csv` shows the turn as one primary movement plus at most two corrections, peak speed
  in the first half; key times for typing are reproducible per seed (`HandChecks`); the walk never stalls (horizontal
  speed > 3 blocks/s except at the start and the end).

### (c) Text and edit: overlay text, the cut and export pipeline, music and sound

- **Goal.** Text that reads on a phone, and a cut that looks edited by a person.
- **Owns.** `src/main/java/io/github/alexandroslekkas/videocraft/text/`, `cli/videocraft/edit/`, `examples/text.toml`,
  `docs/SCRIPT.md` sections "Text" and "Edit".
- **Builds.** Text actions `caption` (words pop in with stagger, `*key` word highlighted and pulsing; whole on frame
  0 when asked), `title`, `keycap`, `lower_third`, `clear`, drawn at 1080-line pixel sizes whatever the GUI scale,
  inside the safe area, one message at a time; `text.json` per shot (frame range, box, cap height, words) for
  measure; the cut: order, trims, push-ins (ramp in, exact nearest-neighbour hold, pan, ramp out), speed ramps, music
  from the local asset index (track and start, −16 LUFS, fades), sound effects from the same index, exports
  `x-1080p60` (< 25 MB), `readme-720p30` (< 10 MB), `gif`, `poster`; `--silent`.
- **Depends on.** `api.ShotContext`, `api.Registry` (a); `marks.json` and the run store layout (a, d).
- **Acceptance.** `examples/text.toml` passes and its `text.json` satisfies every layout rule in section 5; a push-in
  hold is pixel-exact against the source crop; exports meet their size limits; music loudness measures −16 ± 1 LUFS;
  with no game assets present the edit names the file it looked for and stops (or `--silent`).

### (d) CLI, run store, measure and lint, reviewer prompts, the hill-climb

- **Goal.** An agent can write a script, run it, read why it is weak, change it, and prove the change helped.
- **Owns.** `bin/`, `cli/videocraft/` except `edit/`, `cli/tests/`, `pyproject.toml`, `modpack/`, `docs/SCRIPT.md`
  (except Text and Edit), `docs/REVIEW.md`, `examples/` (except `text.toml`).
- **Builds.** `lint` (script problems before a take: unknown actions, cues past the end, text that cannot meet the
  reading rule, two messages at once); `measure` (camera speed and jerk from `frames.csv`, frozen and black frames,
  text against section 5 from `text.json`, loudness, contact sheet); reviewer prompts (story, camera, legibility,
  pacing) and `review` writing `review/<reviewer>.json` (Claude via the Anthropic API or a local agent CLI; the
  scoring rubric in `docs/REVIEW.md`); `score` (aggregate) and `index.json`; `climb` (propose, run with `--parent`,
  keep if better, stop on budget); `runs`/`compare`; `modpack` (`.mrpack` from `modpack/pack.toml`); world cache
  commands with a.
- **Depends on.** `result.json`, `frames.csv`, `marks.json` (a); `text.json`, `cut/` (c).
- **Acceptance.** `python3 -m unittest discover -s cli/tests` passes; `videocraft lint` catches each rule on a fixture
  script; `videocraft climb examples/hello.toml --budget 3` runs three iterations, writes `score.json` for each and
  `index.json` shows the parent chain; `videocraft modpack` writes an `.mrpack` that the Modrinth app imports.

## 10. Milestones

1. **Foundation** (this commit): hidden window, fixed clock, capture, director, orbit/fixed/first rigs, plan format,
   CLI `doctor`/`compile`/`run`/`cut`/`measure`, `examples/hello.toml` → a real 1080p60 mp4.
2. **One person on camera** (a + b): a player walks, jumps and looks, filmed by `chase` and `track`; server lockstep.
3. **Words and a cut** (c + d): captions and a title with measured layout; cut with push-ins and music; lint and
   measure.
4. **Judged** (d): reviewers, scores, the hill-climb loop on `examples/`.
5. **First customer**: T3 Craft's launch video re-made as a videocraft script plus a T3 Craft plugin.
