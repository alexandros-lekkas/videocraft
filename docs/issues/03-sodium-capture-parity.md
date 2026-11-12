# Check capture parity with Sodium
Labels: good first issue, rendering, investigation

## Context

Sodium (`mc26.3-0.9.2-fabric`) replaces the chunk renderer. It is left out of the modpack until capture is verified
with it (docs/DESIGN.md, "Existing mods"; `modpack/pack.toml`): the frame grab, the HUD text layer drawn over
screens, the camera mixin and the "all sections rendered" wait before recording could each behave differently.
Capture is already faster than real time without it, so the question is correctness first, speed second.

## Acceptance

- [ ] A short write-up (in the PR, and a line in AGENTS.md "Hard-won facts") answering, for `examples/hello.toml`
      and one example with text and a moving camera:
  - does the take end `RESULT PASS` with Sodium in the dev runtime?
  - are frames identical or visibly equivalent to a run without Sodium (attach the same frame numbers from both;
    compare `framemd5` of each shot's `video.mp4`)?
  - does the shot still wait for all sections (`LevelRenderer.hasRenderedAllSections()` or Sodium's equivalent)?
  - capture fps real time with and without.
- [ ] If anything breaks: the smallest fix, or a clear issue per problem.
- [ ] Sodium is added only as a dev runtime dependency for the experiment (`modLocalRuntime`), behind a Gradle
      property, so the default build does not change. Its licence (PolyForm Shield) means it is never bundled.

## Pointers

- `src/main/java/io/github/alexandroslekkas/videocraft/director/Capture.java`, `src/main/java/io/github/alexandroslekkas/videocraft/director/ShotRun.java` (the settle wait)
- `src/main/java/io/github/alexandroslekkas/videocraft/mixin/CameraMixin.java`, `src/main/java/io/github/alexandroslekkas/videocraft/text/TextLayer.java`
- `build.gradle`, `modpack/pack.toml`
