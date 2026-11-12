# Write the plugin guide and an example plugin
Labels: good first issue, documentation

## Context

Another mod can add its own actions and camera rigs through the `"videocraft"` entrypoint (`VideocraftPlugin`), and
keep videocraft a dev-only dependency. DESIGN.md section 6 sketches it in ten lines; there is no step-by-step guide
and no example a modder can copy.

## Acceptance

- [ ] `docs/PLUGINS.md`: depending on the videocraft jar (`modCompileOnly` + `modLocalRuntime`), the entrypoint
      in `fabric.mod.json`, namespaced ids, writing an `Action` (instant and multi-frame, `stop` clean-up) and a
      `CameraRig`, validating `Params` with good error messages, threads (render thread; `shot.command` for the
      server), determinism (`shot.seconds()`, never wall time), and how to film a test take of your own mod.
- [ ] A minimal example plugin under `examples/plugin/` (its own tiny Gradle project, not part of the main build)
      registering one action and one rig; the guide's code is taken from it.
- [ ] Following the guide from a clean checkout, the example's script ends `RESULT PASS` (say how you checked).
- [ ] Linked from CONTRIBUTING.md and the README.

## Pointers

- `src/main/java/io/github/alexandroslekkas/videocraft/api/` (the whole contract), `src/main/java/io/github/alexandroslekkas/videocraft/director/Registries.java` (namespacing rules)
- docs/DESIGN.md section 6, CONTRIBUTING.md "Adding an action or a rig"
