## What and why

<!-- One idea per pull request. What changes for someone writing a shot script, and why. Link the issue. -->

## What I saw in the frames

<!--
For anything a viewer can see: run the example it touches, pull frames out of the result and look at them.
  mkdir -p /tmp/vc && ffmpeg -i <VIDEO> -vf "select='eq(n\,90)'" -fps_mode passthrough /tmp/vc/f90.png
Say what you saw (and attach a frame or two). "Tests pass" is not enough for a visual change.
Write "Not visual" if nothing on screen changes.
-->

## Run

<!-- The RESULT ... TIME lines of `bin/videocraft run examples/hello.toml` and of every example this touches. -->

```text
RESULT
TIME
```

## Definition of done

- [ ] `./gradlew build` passes (the jar and the plain-JVM `*Checks`)
- [ ] `python3 -m unittest discover -s cli/tests` passes and the refreshed fixtures in `cli/tests/plans/` are committed
- [ ] `bin/videocraft run examples/hello.toml` ends `RESULT PASS`, and so does every example this change touches
- [ ] Visual change: I looked at frames of the result and described them above
- [ ] New script keys or actions are documented in `docs/SCRIPT.md`
- [ ] A change to the plan shape changes `Plan.java`, `script.py` and `docs/SCRIPT.md` together
- [ ] Run store paths and `frames.csv` columns are only added, never renamed or removed
- [ ] A line in `CHANGELOG.md` under *Unreleased*
- [ ] Java 25, tabs in Java, 4 spaces in Python, no wildcard imports, no new Python dependency
- [ ] Nothing from a real Minecraft folder, no game assets (textures, sounds, music), nothing from `runs/`, `run-game/` or `reference/`
- [ ] Commits are one idea each, with messages that say why
