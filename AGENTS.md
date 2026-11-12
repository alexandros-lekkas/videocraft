# Working on videocraft (for coding agents and new contributors)

videocraft is agent-directed video for **Minecraft Java 26.3**: a shot script in, a cut and measured video out. Two
parts in one repo: a Fabric mod that plays the script in a hidden client and captures every frame (a dev-time tool;
inert unless the CLI starts it), and a Python CLI that drives everything. Java 25, Fabric Loader 0.19.5, Fabric API
0.161.0+26.3, Loom 1.17, Gradle 9.8 (wrapper checked in), Python 3.11+ standard library only, ffmpeg.

This is the five-minute brief. The architecture and the four workstreams are in [docs/DESIGN.md](docs/DESIGN.md);
the script format is [docs/SCRIPT.md](docs/SCRIPT.md).

## Commands

```sh
export JAVA_HOME=/opt/homebrew/opt/openjdk@25/libexec/openjdk.jdk/Contents/Home   # for raw Gradle; bin/videocraft finds it itself
bin/videocraft doctor                      # JDK 25, ffmpeg/ffprobe/libx264, folders, the three slots, running client
./gradlew build                           # mod jar (build/libs/videocraft-<v>.jar) + plain-JVM checks (PlanChecks, RigChecks)
python3 -m unittest discover -s cli/tests # CLI checks (script compiling); also refreshes cli/tests/plans/hello.plan.json
bin/videocraft compile examples/hello.toml # check a script, print the plan
bin/videocraft run examples/hello.toml     # take → cut → measure as runs/hello/<n>/; about 30 s
bin/videocraft runs hello                  # iterations and verdicts
bin/videocraft cut hello · measure hello   # re-cut / re-measure the latest iteration (or hello/3, or a path)
bin/videocraft status · stop               # this checkout's client, over its control port
bin/videocraft lint x.toml · measure --video f.mp4 --from 0 --to 82.2 --out /tmp/m   # before a take; any video
bin/videocraft review packet x · review run x · score x · compare x/1 x/2 · climb x.toml --budget 3   # docs/REVIEW.md
```

Every run ends like this, so a script or an agent can act on it (exit 0 PASS, 1 FAIL, 2 no verdict):

```text
RESULT   PASS 1920x1080 60 fps 180 frames 3.00 s; capture 79.3 fps real time
VIDEO    <repo>/runs/hello/0002/cut/master.mp4
RUN      <repo>/runs/hello/0002
LOG      <repo>/runs/hello/0002/take/game.log
TIME     27 s
```

Look at frames with `ffmpeg -i <VIDEO> -vf "select='eq(n\,90)'" -fps_mode passthrough /tmp/f.png` (into a temp
directory) and open the PNG. `--show` opens a window (still without taking focus); `--keep-world` keeps the seed's
world in `run-game/saves/`; `--timeout`, `--window WxH`, `--port`, `--parent`, `--no-cut`.

## Project map

| Where | What | Owner |
|:--|:--|:--|
| `src/main/java/io/github/alexandroslekkas/videocraft/api/` | The plugin contract: `VideocraftPlugin`, `Registry`, `Action(Type)`, `CameraRig`/`RigType`, `Pose`, `View`, `Actor`, `ShotContext`, `Params` | a |
| `…/director/` | `Director` (the take's state machine and frame clock), `ShotRun` (one shot, implements `ShotContext`), `Capture` (framebuffer → ffmpeg), `FrameLog`, `Take` (paths, result.json), `WorldBoot`, `Hud`, `ControlServer`, `Registries`, `CoreActions` | a |
| `…/plan/Plan.java` | plan.json, the compiled script | a (+ d for the CLI side) |
| `…/camera/` | `Rigs` (orbit, fixed, first), `Operator` (critically damped follow) | a |
| `…/mixin/` | `ClockMixin` (fixed step), `CameraMixin` (rig moves the camera), `ParkedPlayerMixin` (hide the parked player) | a |
| `…/devmixin/`, `HiddenWindow.java` | Hidden SDL window, no focus, no Dock icon; only with `-Dvideocraft.hidden=true` | a |
| `…/actor/` | `Hand` (human input model, no Minecraft classes), `Cast`, `PlayerActor`, `Actions` | b |
| `…/text/` | `TextLayer` (HUD layer, also over screens), `TextActions` | c |
| `src/smoke/java/` | Plain-JVM `*Checks` run by `./gradlew check`; read fixtures from `cli/tests/plans/` | each owner |
| `cli/videocraft/` | `cli.py` (built-in commands, loads the command groups), `script.py` (TOML → plan), `store.py` (run store), `game.py` (launch, lock, control), `doctor.py`, `tools.py`, `paths.py`, `measure/` (picture, loudness, camera, text rules), `lint.py`, `timeline.py`, `compare.py`, `climb.py`, `modpack.py`, `agents.py` (the one model call: `ask`), `review/` (packets, rubrics, prompts, reviews) | d |
| `cli/videocraft/edit/` | The cut and exports | c |
| `cli/videocraft/<group>/commands.py` | A command group's commands: `register(subparsers)`; groups `edit`, `audio`, `voice`, `sets`, `story`, `review`, `series`, `clips` | the group's owner |
| `examples/` | Scripts that must keep passing | d (text.toml: c) |
| `cli/videocraft/story/`, `cli/videocraft/series/`, `stories/` | The story pipeline (premise → shots.toml), series, `make`; prompts in `story/prompts/` ([docs/STORY.md](docs/STORY.md)) | story |
| `modpack/pack.toml` | The distributable pack definition | d |

A new CLI command lives in its own subpackage's `commands.py` with `register(subparsers)`; do not add commands to
`cli.py`. `cli.py` imports `videocraft.<group>.commands` for each name in `cli.GROUPS` after the built-ins: a
missing group is skipped, one that fails to import is reported on stderr, and a group's command replaces a
not-yet placeholder of the same name (`lint`, `review`, `climb`, `modpack`). A new group name goes into `GROUPS`.

## Hard rules

They protect the owner's machine and game. They are not preferences.

1. **Never touch a real Minecraft directory.** Not `~/Library/Application Support/minecraft*`, `%APPDATA%\.minecraft`,
   `~/.minecraft`, their `options.txt`, worlds or mods. The game runs only in this checkout's `run-game/`
   (`paths.is_real_minecraft` refuses the others).
2. **Hidden, muted, own folder, own port.** Takes go through `bin/videocraft run` (hidden unless `--show`, master
   volume 0 in `run-game/options.txt`, control port 25750–25752 by slot). Never use 25590 (a real game's Minecraft
   MCP port) or T3 Craft's 25611/25680–25690/25720; `--port` refuses them.
3. **No OS input automation, no screen capture, nothing brought to the front.** Frames come from the game's own
   framebuffer.
4. **One client per checkout, at most three per machine.** A take holds one of three machine-wide slots (a lock in
   `/tmp/videocraft-slots-<uid>/`, ports 25750–25752) and waits for a free one when all are busy;
   `bin/videocraft stop` when you are done with one you started.
5. **Never commit Mojang assets** (music, sounds, textures) or anything from `runs/`, `run-game/` or `reference/`.
   Music is read from `~/.gradle/caches/fabric-loom/assets` at export time.
6. **Commit with explicit paths** (never `git add -A`): others work in this checkout (`docs/benchmarks/`, `reference/`).

## Hard-won facts (verified on macOS 26, Apple M4 Pro, OpenGL backend, November 2026)

- **JDK 25.** With JDK 27 as `JAVA_HOME` the build fails: Gradle finds no JDK 25 toolchain, because Homebrew's
  `openjdk@25` is keg-only and not auto-detected. Point `JAVA_HOME` at it (above); `bin/videocraft` does this itself.
- **SDL3, not GLFW.** Minecraft 26.3 windows through SDL3. Hidden means `SDL_WINDOW_HIDDEN` on window creation, ignoring
  focus and iconify events, and `SDL_MAC_BACKGROUND_APP=1` before `SDL_Init` (else a Dock icon and stolen focus).
- **Retina.** A 960×540 window is a 1920×1080 framebuffer on a 2× Mac; the CLI asks for that and the mod checks
  (`WorldBoot.frameSize`) and resizes once if it is wrong.
- **GUI scale is clamped to 4 at 1920×1080** (vanilla needs 320×240 GUI pixels per step), so UI text can only be made
  bigger by an edit push-in, held as an exact nearest-neighbour crop.
- **Capture order.** The clock mixin (`Minecraft.runTick` → `advanceGameTime`) grabs the frame rendered last, then
  advances one fixed step. Capture of 1080p60 runs at 65–85 fps real time; the queue blocks, so a slow encoder slows
  the game instead of dropping frames.
- **The local player and the camera.** Vanilla draws the local player's body only when it is the camera entity, so
  third person keeps the player as camera entity and moves the camera in `CameraMixin`. But a *spectator* local player
  *is* drawn (as a head) once the camera is another entity: the operator's parked spectator showed up in frame until
  `ParkedPlayerMixin` hid it.
- **Slots.** A slot is an exclusive `flock` the CLI holds for the whole take; the OS drops it if the CLI dies. A slot
  whose port something else already listens on (an older client without slots) is skipped. The checkout's
  `run-game/videocraft.pid` records `{pid, port}`, so `status` and `stop` need no flags; `--port` skips the slot
  choice (and still holds that slot's lock if it is one of the three).
- **The control server must stop with the client.** `HttpServer`'s dispatcher is not a daemon thread; left running it
  keeps the JVM alive after `Minecraft.stop()`, the shutdown watchdog writes a crash report and Gradle reports exit 248.
- **Fresh camera positions need a beat.** Right after a camera moves, fog and sections are still settling; each shot
  waits ≥ 60 frames and until `LevelRenderer.hasRenderedAllSections()` before recording.
- **Homebrew's ffmpeg has no `drawtext`** (`bin/videocraft doctor` shows it), so all text is rendered in the game. A
  caption drawn as a Screen cannot overlap another screen, so text is drawn on the HUD layer and again after any
  screen draws (`TextLayer`).
- **Exact push-in holds** need the crop at even offsets and sizes (yuv420p chroma); ffmpeg's `scale=flags=neighbor`
  then equals source index `floor((2x+1)·cw / 2W)` on every plane (`videocraft edit verify` checks it). Sub-pixel
  zooms use `perspective=…:eval=frame` with `in` (ffmpeg 9 has no `n` there).
- **From the [T3 Craft](https://github.com/alexandros-lekkas/t3craft) prototype, not yet re-checked here** (no
  third-person or actor shots exist yet): view bobbing must be off for third-person cameras, and the camera must
  follow a ground reference, not the player's head, or it bobs with steps and jumps; auto-jump must be off (it is, in
  `options.txt` and on arrival); a mouse pointer at rest is frozen to the pixel and clicks only after it has stopped.
- **Layout rules** (DESIGN.md section 5): safe area x 96–1824, y 54–918; one message at a time; text complete on screen
  for `max(1.2 s, 0.5 s + 0.3 s per word)`; capital height under 44 px at 1920 wide does not count as shown at phone
  width.
- **26.3 names.** Mojang names, unobfuscated: `mc.gui.screen()`, `mc.gui.setScreen`, `GuiGraphicsExtractor`,
  gamerules `advance_time` / `advance_weather`. Check real classes with
  `javap -cp ~/.gradle/caches/fabric-loom/26.3/minecraft-merged.jar <class>` (`-p` for private) before assuming an API.
- **Threads.** World edits and commands belong to the server thread (`Director.command` posts them); screens,
  entities and the camera to the render thread. Actions and rigs run on the render thread.
- **Model calls are slow and big.** One `claude -p` draft of a 30-shot shot script took about 10 minutes and came
  back as about 1000 lines of TOML; the story pipeline allows 30 minutes a call (`VIDEOCRAFT_ASK_TIMEOUT`). A
  not-yet placeholder command (`lint`) takes no arguments, so calling it with a file is an argparse usage error
  (exit 2), not a verdict.
- **Uploaded 60 fps video repeats frames.** The benchmark's reference is lower-rate footage in a 60 fps file: about
  one frame in three or four is an exact repeat. A cut detector that takes the local median over every frame
  difference sees those zeros and fires on walking motion. `measure` ignores repeated frames for the local level, and
  so finds 28 shots with a median of 2.59 s on 0:00–1:22.2 (the doc's hand count is 30 and 2.6 s).
- **Frames by number from ffmpeg:** `-vf "select='eq(n,12)+eq(n,90)',scale=640:360,format=rgb24" -fps_mode
  passthrough -f rawvideo -` gives exactly those frames in order. Pass it as one argv item (no shell), so ffmpeg's own
  quotes protect the commas. Review packets and `compare` use this; there is no drawtext, so labels are a built-in
  bitmap font.
- **Reviewers through `claude -p`:** prompt on stdin, `--allowedTools Read --add-dir <packet>` so it can open the PNGs,
  `--output-format json` (the answer is `result`, or `structured_output` with `--json-schema`). A reviewer that is
  told it sees stills only, and is given frames.csv numbers, cites timecodes and gives fixes that can be applied
  (`runs/hello/*/review/camera.json`).
- **Reviewer scores wobble by about a point** between two runs of the same role on the same packet (camera 4, then 5,
  on hello 0001). A climb step that gains one point on one criterion is noise; `climb` keeps ties with the parent.
- **The proposer must see the frames.** The first hello climb spent three takes moving a subject behind the same
  ice spikes, because it read the reviewers' words without the strips; it now gets the contact sheets and strips.

- **Sound log.** `SoundEngine.play` calls its `SoundEventListener`s after it has resolved the variant and *before* it
  drops a zero-volume sound, so a listener logs everything with master volume 0. The variant (and any sampled volume or
  pitch) comes from the instance's own `RandomSource`, which vanilla seeds from the level's or an entity's unseeded
  random: `SoundEngineMixin` swaps in a seeded one at `play` HEAD, else two takes log different files.
- **ffmpeg audio.** Homebrew's ffmpeg has no `soxr` resampler, and `alimiter` delays its output by its attack unless
  `latency=1`; the master uses the default resampler and `latency=1` (`audio events --onsets` checks the delay is 0).
- **The vignette broke determinism.** Vanilla eases its strength once per rendered frame from 1 toward the light at
  the camera, so it depended on how many frames preparation took: two takes differed on every frame of the first
  shots and matched once it had faded. The HUD's `MISC_OVERLAYS` is hidden in filmed shots; with it, two takes of
  `examples/rigs.toml` match frame for frame (framemd5) and byte for byte (`frames.csv`).
- **Spawn moves between takes.** The same world seed spawns the player at a different spot each take (vanilla's
  `respawn_radius`), so `{ anchor = "spawn" }` positions shift by a few blocks: compare logs relative to spawn.
- **Vertical takes.** A hidden 540x960 window gives a 1080x1920 framebuffer on a 2x Mac and the text layer lays every
  caption out for it; `clips cut` passes the window itself. A 9:16 crop of a 16:9 master loses any text outside the
  crop, so re-framing falls back to the whole frame over a blurred fill; re-shooting is the way to keep text.
- **A moving ffmpeg crop:** `sendcmd=f=<file>,crop=…` with one `<t> crop x <px>;` line per change moves the crop
  per frame. The re-frame operator needs about 0.3 s of look-ahead: at 0.15 s a fast-drifting subject left the crop's
  centre 60 % in a fifth of its frames, at 0.3 s in none.
- **argparse:** a positional named `run` in a command group overwrites `set_defaults(run=…)` (TypeError: 'str'
  object is not callable); give it another `dest` and `metavar='run'`.

## Working with agents

- **Orchestrated work.** One orchestrator plans, briefs, reviews and merges. Builders each work in their own git
  worktree and own files that do not overlap (the Owner column of the project map). Visual output is judged by fresh
  reviewer agents, who score it 1 to 10 from frame strips and measurements; they cannot watch video or hear audio,
  and must say so in their review. Reviewers may be a stronger model than the builders (on 2026-11-11 the builders
  were Opus).
- **Probe every account first.** When delegates are spread over more than one model-provider account, send each
  account one small delegate before relying on it. Verified 2026-11-11: on a secondary account the newest top-tier
  model failed at once with "Usage credits are required for this model", while the Opus-tier model on the same
  account worked; that night's delegates therefore all ran on Opus.
- **Each worktree is its own studio.** It has its own `run-game/` and `runs/` (both git-ignored), so takes never share
  a game folder or a run store; the three-slot cap (hard rule 4) is what keeps the machine usable with several running.

## Definition of done

- `./gradlew build` and `python3 -m unittest discover -s cli/tests` pass.
- `bin/videocraft run examples/hello.toml` still ends `RESULT PASS`, and so does every example your change touches. A
  change a viewer can see: look at frames of the result and say what you saw in the commit or PR.
- New script keys or actions are in `docs/SCRIPT.md`; a change to the plan shape changes `Plan.java`, `script.py`
  and `docs/SCRIPT.md` together; run store paths and `frames.csv` columns are only ever added.
- A line in `CHANGELOG.md` under *Unreleased*. Java 25, tabs in Java, 4 spaces in Python, no wildcard imports, no new
  Python dependency.
- One idea per commit, messages that say why, ending with the co-author line the session asks for.
