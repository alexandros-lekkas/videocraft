# Nibs vs Duke: production log

The benchmark film ([pinksheep-style.md](pinksheep-style.md)), script `examples/nibs-vs-duke.toml`. Each iteration is
`runs/nibs-vs-duke/<n>/` (git-ignored); this log keeps what was filmed, what was seen and what changed.

## Iterations

| Run | What changed | Measured | Seen |
|--:|:--|:--|:--|
| 0001-0002 | First draft: 30 shots + end card on market-lane, barn-stage, black-stage; voice for every VO and DUKE line | — | Failed at staging: `forceload add` refuses over 256 chunks, then "No chunks were marked" when already loaded (fixed in `Commands.java`) |
| 0003 | (same script) | PASS, 73.85 s; 25 of 30 shots detected (barn statics merge in sepia); median 2.30 s; montage 6 under 0.6 s; black 0.88 s + 0.67 s; −14.2 LUFS; lead tracks centred (x 0.50) at constant size (1%); 10 caption reading problems | Sets, flashback frame, poster, cards and captions read. Face cut-in is a cheek; montage goat in profile; shot 28 camera still swinging at frame 0 (goat placed facing the wrong way); the ram and scream too small to read |
