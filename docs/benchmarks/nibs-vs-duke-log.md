# Nibs vs Duke: production log

The benchmark film ([pinksheep-style.md](pinksheep-style.md)), script `examples/nibs-vs-duke.toml`. Each iteration is
`runs/nibs-vs-duke/<n>/` (git-ignored); this log keeps what was filmed, what was seen and what changed.

## Iterations

| Run | What changed | Measured | Seen |
|--:|:--|:--|:--|
| 0001-0002 | First draft: 30 shots + end card on market-lane, barn-stage, black-stage; voice for every VO and DUKE line | — | Failed at staging: `forceload add` refuses over 256 chunks, then "No chunks were marked" when already loaded (fixed in `Commands.java`) |
| 0003 | (same script) | PASS, 73.85 s; 25 of 30 shots detected (barn statics merge in sepia); median 2.30 s; montage 6 under 0.6 s; black 0.88 s + 0.67 s; −14.2 LUFS; lead tracks centred (x 0.50) at constant size (1%); 10 caption reading problems | Sets, flashback frame, poster, cards and captions read. Face cut-in is a cheek; montage goat in profile; shot 28 camera still swinging at frame 0 (goat placed facing the wrong way); the ram and scream too small to read |
| 0004 | Goat placed facing its path; fixed face cut-in; montage preroll 1.4 s at 2.4 blocks, fov 70; shot 28 closer; shorter captions; lighter sepia | PASS 74.60 s; 25 shots (barn cuts still missed); reading problems 10 → 2 | Montage now centred and facing the lens. Face cut-in looks down on the forehead. The egg drops unseen behind the hen |
| 0005 | Hen three-quarter at fov 30; face cut-in at eye level; snap zoom 1.4× on the scream; slow push over shot 16; flashback grade lifted (gamma 1.25, contrast 1.12) | PASS 74.60 s; **28 shots**, median 2.35 s, none over 7.5 s; montage 6 under 0.6 s; −14.2 LUFS; egg plop, kicks and scream 0 frames off | Egg in sight, horn and eye read. The zoom crops the bottom caption in half |
| 0006 | Shot 28's caption at the top | Same numbers; only the one-word montage captions under reading time | The top caption is still half in frame under the zoom (fixed for 0007: zoom centre y 660) |
