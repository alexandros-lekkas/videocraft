# Add a set to the set library
Labels: good first issue, sets

## Context

Scripts stage their world with `[[world.set]] name = "...", at = [x, y, z]`: a set is a small, reusable build that
expands at compile time into staging commands and declares named **marks** (positions and paths) that shots anchor
to, such as `{ anchor = "market-lane:stall-1" }`. The library needs more variety: a riverside dock, a farm plot with a
fence, a small classroom, a snowy clearing.

## Acceptance

- [ ] One new set, built only from vanilla blocks through commands (no saved world, no downloaded schematic, nothing
      from a real Minecraft folder).
- [ ] At least four marks: an entrance, two places to stand, and a camera position that frames the set well; a path
      if characters walk through it.
- [ ] It fits within the area the set format allows and places cleanly on flat ground at any `at`.
- [ ] An example script that places it and films one shot from a mark; `RESULT PASS`; the PR includes a frame
      and says what it shows (readable silhouette at phone size, nothing floating, light is good).
- [ ] Documented in the set list (see the sets section of `docs/SCRIPT.md`) and a `CHANGELOG.md` line.

## Pointers

- The set format and existing sets: the sets section of `docs/SCRIPT.md` and the set library folder it names (both
  land with the sets workstream; read them first).
- `cli/videocraft/script.py` (how sets expand), `examples/`
