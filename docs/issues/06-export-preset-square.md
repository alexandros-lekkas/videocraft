# Add a square 1080×1080 export preset
Labels: good first issue, edit

## Context

The cut writes `cut/master.mp4` (H.264, CRF 18, BT.709, the plan's size and rate) and exports to
`cut/<export>.mp4`. A square export is what several feeds show best. Because all text is drawn in the game inside
the safe area (x 96–1824, y 54–918 at 1920×1080), a centre crop of a 1920×1080 master would cut captions, so the
preset needs a rule for where the crop sits.

## Acceptance

- [ ] An export preset `square` (1080×1080, same rate as the master) selectable from the script's `[edit]` table
      and from the cut command, written to `cut/square.mp4` (a new path, nothing renamed).
- [ ] The crop is centred by default and can follow a per-clip horizontal offset, so a subject or caption off centre
      stays in frame. Document the key.
- [ ] Text that falls outside the crop is reported by `measure` (or a warning from the cut) rather than silently
      lost.
- [ ] `ffprobe` of the result shows 1080×1080, the right frame count and BT.709 tags; the PR includes two frames.
- [ ] `docs/SCRIPT.md` (`[edit]`) and a `CHANGELOG.md` line.

## Pointers

- `cli/videocraft/edit/` (`cut.py` and the export code), `cli/videocraft/measure.py`
- docs/DESIGN.md section 5 (layout rules), section 4 (run store)
