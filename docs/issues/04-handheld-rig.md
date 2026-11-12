# Add a `handheld` camera rig
Labels: good first issue, camera

## Context

The built-in rigs are perfectly steady (`fixed`, `orbit`; `chase`, `track`, `dolly`, `crane` are planned by the
runtime workstream). Comedy and reaction shots often want the opposite: a camera that is *held*, with a slow,
small drift and breathing, so a static two-shot does not look like a security camera. It must be deterministic:
the same plan and seed give the same frames.

```toml
camera = { rig = "handheld", eye = [10, 70, 4], at = [12, 69, 10], amount = 1.0, seed = 7, fov = 60 }
```

## Acceptance

- [ ] `handheld` is registered in `Rigs.register` with `eye`, `at` (positions, as `fixed`), `amount` (1.0 =
      a gentle hand: about 2-4 cm of position drift and under 0.5° of rotation; 0 = `fixed`), `seed` (default:
      the plan's seed), `fov`.
- [ ] The motion is smooth, low-frequency noise (sum of a few seeded sines, or value noise with smooth
      interpolation) as a function of `shot.seconds()` only. No per-frame random draws, no jitter.
- [ ] Bad parameters fail the take with a message naming the key (`amount` < 0 or > 5).
- [ ] `RigChecks` gains cases: `amount = 0` equals `fixed`; the same seed gives the same pose at the same time;
      the frame-to-frame change stays under a bound (no visible jumps at 60 fps).
- [ ] An example shot uses it; the run ends `RESULT PASS`; the PR says what the motion looks like when played
      (natural, not seasick) and includes the camera columns of `frames.csv` plotted or summarised.
- [ ] The rigs table in `docs/SCRIPT.md` and a `CHANGELOG.md` line.

## Pointers

- `src/main/java/io/github/alexandroslekkas/videocraft/camera/Rigs.java` (`Fixed`), `src/main/java/io/github/alexandroslekkas/videocraft/api/CameraRig.java`, `src/main/java/io/github/alexandroslekkas/videocraft/api/Pose.java`, `src/main/java/io/github/alexandroslekkas/videocraft/api/Params.java`
- `src/smoke/java/io/github/alexandroslekkas/videocraft/RigChecks.java`
- CONTRIBUTING.md, "Adding an action or a rig"
