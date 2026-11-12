# Working on blockreel (for coding agents and new contributors)

blockreel is agent-directed video for **Minecraft Java 26.3**: a shot script in, a cut and measured video out. Two
parts in one repo: a Fabric mod that plays the script in a hidden client and captures every frame (a dev-time tool;
inert unless the CLI starts it), and a Python CLI that drives everything. Java 25, Fabric Loader 0.19.5, Fabric API
0.161.0+26.3, Loom 1.17, Gradle 9.8 (wrapper checked in), Python 3.11+ standard library only, ffmpeg.

This is the five-minute brief. The architecture and the four workstreams are in [docs/DESIGN.md](docs/DESIGN.md);
the script format is [docs/SCRIPT.md](docs/SCRIPT.md).

## Commands

```sh
export JAVA_HOME=/opt/homebrew/opt/openjdk@25/libexec/openjdk.jdk/Contents/Home   # for raw Gradle; bin/blockreel finds it itself
bin/blockreel doctor                      # JDK 25, ffmpeg/ffprobe/libx264, folders, control port, running client
./gradlew build                           # mod jar (build/libs/blockreel-<v>.jar) + plain-JVM checks (PlanChecks, RigChecks)
python3 -m unittest discover -s cli/tests # CLI checks (script compiling); also refreshes cli/tests/plans/hello.plan.json
bin/blockreel compile examples/hello.toml # check a script, print the plan
bin/blockreel run examples/hello.toml     # take → cut → measure as runs/hello/<n>/; about 30 s
bin/blockreel runs hello                  # iterations and verdicts
bin/blockreel cut hello · measure hello   # re-cut / re-measure the latest iteration (or hello/3, or a path)
bin/blockreel status · stop               # the running client, over the control port
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
| `src/main/java/dev/blockreel/api/` | The plugin contract: `BlockreelPlugin`, `Registry`, `Action(Type)`, `CameraRig`/`RigType`, `Pose`, `View`, `Actor`, `ShotContext`, `Params` | a |
| `…/director/` | `Director` (the take's state machine and frame clock), `ShotRun` (one shot, implements `ShotContext`), `Capture` (framebuffer → ffmpeg), `FrameLog`, `Take` (paths, result.json), `WorldBoot`, `Hud`, `ControlServer`, `Registries`, `CoreActions` | a |
| `…/plan/Plan.java` | plan.json, the compiled script | a (+ d for the CLI side) |
| `…/camera/` | `Rigs` (orbit, fixed, first), `Operator` (critically damped follow) | a |
| `…/mixin/` | `ClockMixin` (fixed step), `CameraMixin` (rig moves the camera), `ParkedPlayerMixin` (hide the parked player) | a |
| `…/devmixin/`, `HiddenWindow.java` | Hidden SDL window, no focus, no Dock icon; only with `-Dblockreel.hidden=true` | a |
| `…/actor/` | `Hand` (human input model, no Minecraft classes), `Cast`, `PlayerActor`, `Actions` | b |
| `…/text/` | `TextLayer` (HUD layer, also over screens), `TextActions` | c |
| `src/smoke/java/` | Plain-JVM `*Checks` run by `./gradlew check`; read fixtures from `cli/tests/plans/` | each owner |
| `cli/blockreel/` | `cli.py` (commands), `script.py` (TOML → plan), `store.py` (run store), `game.py` (launch, lock, control), `doctor.py`, `measure.py`, `tools.py`, `paths.py`, `review/` | d |
| `cli/blockreel/edit/` | The cut and exports | c |
| `examples/` | Scripts that must keep passing | d (text.toml: c) |
| `modpack/pack.toml` | The distributable pack definition | d |

## Hard rules

They protect the owner's machine and game. They are not preferences.

1. **Never touch a real Minecraft directory.** Not `~/Library/Application Support/minecraft*`, `%APPDATA%\.minecraft`,
   `~/.minecraft`, their `options.txt`, worlds or mods. The game runs only in this checkout's `run-game/`
   (`paths.is_real_minecraft` refuses the others).
2. **Hidden, muted, own folder, own port.** Takes go through `bin/blockreel run` (hidden unless `--show`, master
   volume 0 in `run-game/options.txt`, control port 25750). Never use 25590 (a real game's Minecraft MCP port) or
   T3 Craft's 25611/25680–25690/25720.
3. **No OS input automation, no screen capture, nothing brought to the front.** Frames come from the game's own
   framebuffer.
4. **One Minecraft client at a time** per machine; `bin/blockreel stop` when you are done with one you started.
5. **Never commit Mojang assets** (music, sounds, textures) or anything from `runs/`, `run-game/` or `reference/`.
   Music is read from `~/.gradle/caches/fabric-loom/assets` at export time.
6. **Commit with explicit paths** (never `git add -A`): others work in this checkout (`docs/benchmarks/`, `reference/`).

## Hard-won facts (verified on macOS 26, Apple M4 Pro, OpenGL backend, November 2026)

- **JDK 25.** With JDK 27 as `JAVA_HOME` the build fails: Gradle finds no JDK 25 toolchain, because Homebrew's
  `openjdk@25` is keg-only and not auto-detected. Point `JAVA_HOME` at it (above); `bin/blockreel` does this itself.
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
- **The control server must stop with the client.** `HttpServer`'s dispatcher is not a daemon thread; left running it
  keeps the JVM alive after `Minecraft.stop()`, the shutdown watchdog writes a crash report and Gradle reports exit 248.
- **Fresh camera positions need a beat.** Right after a camera moves, fog and sections are still settling; each shot
  waits ≥ 60 frames and until `LevelRenderer.hasRenderedAllSections()` before recording.
- **Homebrew's ffmpeg has no `drawtext`** (`bin/blockreel doctor` shows it), so all text is rendered in the game. A
  caption drawn as a Screen cannot overlap another screen, so text is drawn on the HUD layer and again after any
  screen draws (`TextLayer`).
- **From the T3 Craft prototype, not yet re-checked here** (no third-person or actor shots exist yet): view bobbing
  must be off for third-person cameras, and the camera must follow a ground reference, not the player's head, or it
  bobs with steps and jumps; auto-jump must be off (it is, in `options.txt` and on arrival); a mouse pointer at rest
  is frozen to the pixel and clicks only after it has stopped.
- **Layout rules** (DESIGN.md section 5): safe area x 96–1824, y 54–918; one message at a time; text complete on screen
  for `max(1.2 s, 0.5 s + 0.3 s per word)`; capital height under 44 px at 1920 wide does not count as shown at phone
  width.
- **26.3 names.** Mojang names, unobfuscated: `mc.gui.screen()`, `mc.gui.setScreen`, `GuiGraphicsExtractor`,
  gamerules `advance_time` / `advance_weather`. Check real classes with
  `javap -cp ~/.gradle/caches/fabric-loom/26.3/minecraft-merged.jar <class>` (`-p` for private) before assuming an API.
- **Threads.** World edits and commands belong to the server thread (`Director.command` posts them); screens,
  entities and the camera to the render thread. Actions and rigs run on the render thread.

## Definition of done

- `./gradlew build` and `python3 -m unittest discover -s cli/tests` pass.
- `bin/blockreel run examples/hello.toml` still ends `RESULT PASS`, and so does every example your change touches. A
  change a viewer can see: look at frames of the result and say what you saw in the commit or PR.
- New script keys or actions are in `docs/SCRIPT.md`; a change to the plan shape changes `Plan.java`, `script.py`
  and `docs/SCRIPT.md` together; run store paths and `frames.csv` columns are only ever added.
- A line in `CHANGELOG.md` under *Unreleased*. Java 25, tabs in Java, 4 spaces in Python, no wildcard imports, no new
  Python dependency.
- One idea per commit, messages that say why, ending with the co-author line the session asks for.
