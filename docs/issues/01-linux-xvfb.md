# Run takes on Linux under `xvfb-run`
Labels: good first issue, platform: linux, help wanted

## Context

Takes are verified on macOS only (docs/DESIGN.md, "Known gaps"). On Linux the client needs a display to create its
OpenGL context even though videocraft never shows the window. The usual answer is a virtual X server:
`xvfb-run -s "-screen 0 1920x1080x24" ...`. Minecraft 26.3 windows through SDL3, so the hidden flag
(`SDL_WINDOW_HIDDEN`) still applies; the macOS-only parts (`SDL_MAC_BACKGROUND_APP`, Retina scaling) must not.

## Acceptance

- [ ] On a Linux machine with Mesa (llvmpipe is fine) or a GPU, `bin/videocraft run examples/hello.toml` ends
      `RESULT PASS 1920x1080 60 fps 180 frames`, with or without an existing `DISPLAY`.
- [ ] When there is no `DISPLAY` and `xvfb-run` is installed, the CLI wraps the Gradle command in it (one place in
      `game.py`); when neither exists, it fails early with a message naming `xvfb-run`.
- [ ] `bin/videocraft doctor` reports the display situation on Linux (`DISPLAY`, `WAYLAND_DISPLAY`, `xvfb-run`).
- [ ] The framebuffer is 1920×1080 (the window is asked for 1920×1080 on non-Mac platforms; `WorldBoot.frameSize`
      checks it).
- [ ] Two frames of the result look the same as a Mac run of the same plan (attach them), and the capture speed is
      in the PR.
- [ ] Optional: a CI job that runs the hello take under `xvfb-run` with Mesa, if it fits in the CI time budget.

## Pointers

- `cli/videocraft/game.py` (`default_window`, `play`, the Gradle command), `cli/videocraft/doctor.py`
- `src/main/java/io/github/alexandroslekkas/videocraft/HiddenWindow.java`, `src/main/java/io/github/alexandroslekkas/videocraft/devmixin/`
- `src/main/java/io/github/alexandroslekkas/videocraft/director/WorldBoot.java` (`frameSize`)
- AGENTS.md, "Hard-won facts" (SDL3, Retina)
