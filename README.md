# videocraft

Agent-directed video for Minecraft Java. Write a shot list, run one command, get a cut video: a hidden game, a camera
crew, a player that moves like a person, and reviewers that score the result.

```sh
bin/videocraft doctor
bin/videocraft run examples/hello.toml      # → runs/hello/<n>/cut/master.mp4, 1920x1080 at 60 fps
```

The game never shows a window, takes focus or plays sound, and runs in its own folder (`run-game/`). Needs JDK 25,
Python 3.11+ and ffmpeg. How it works: [docs/DESIGN.md](docs/DESIGN.md). The script format: [docs/SCRIPT.md](docs/SCRIPT.md).
Working on it: [AGENTS.md](AGENTS.md).

Two parts: a Fabric mod (a dev-time tool that does nothing unless the CLI starts it) and the CLI that drives it. A
modpack definition for others is in `modpack/pack.toml`.

## Credits

The hidden window, the fixed-step frame clock, framebuffer capture, the camera operator spring and the human input
model were first written for the launch video of [T3 Craft](https://github.com/alexandros-lekkas/t3craft) (MIT, by
Maxwell Young and Alexandros Lekkas) and rewritten here to be generic. Minecraft is Mojang's; no Mojang assets are in
this repository, and music is read from the local game install only at export time.

MIT licensed.
