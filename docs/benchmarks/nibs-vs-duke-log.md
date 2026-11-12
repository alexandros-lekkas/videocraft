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

## Review rounds

Reviewers are fresh `claude -p` agents (claude-opus-5-5) through `videocraft review run --rubric pinksheep-style`;
they see strips, contact sheets, cut pairs and measurements, and say they cannot watch motion or hear sound.

| Round | Run | pacing | camera | staging | acting | comedic timing | text | sound | technical | energy | Average | Min | Gate |
|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--|
| 1 | 0006 | 8.0 | 7.0 | 7.0 | 5.0 | 6.5 | 6.5 | 6.0 | 6.0 | 6.5 | **6.5** | 5 | pass |
| 2 | 0007 | 8.0 | 7.5 | 7.0 | 5.5 | 6.5 | 6.0 | 6.0 | 6.5 | 6.5 | **6.61** | 5.5 | pass |

Round 1's agreed fixes (all six reviewers named at least one): the flashback's middle sags (s14 and s15, 8.7 s of
nearly static note blocks with Duke at 8% and 0% of the frame); Duke's bow and ovation are specks (3-4% of the
frame), so the flashback's payoff reads only from the captions; the scream's zoom crops the caption. Also: hens
frozen like props, Nibs' identical walk-to-lens setups, judder on the s20 corner (yaw drift on top of the swing),
the s25 hop leaving the frame, silence on Duke's entrance after the dip, the end card fading up over Duke's head.
Applied for 0007: Duke plays behind the note row (s14) and peeks over the one block as notes rise (s15), both a
little shorter (4.0 s, 3.9 s); the bow through the hens' heads on a 30° lens (s16); the ovation as a 42° medium on
Duke with the trophy (s18); sit switched off before Duke walks (he trotted sitting); hen glances; Nibs nods, glances
and hops; Duke yips on the cut into the barn; a yawn before the sleep and 2.0 s on the button; end card over the
black wall; the bed back under Duke's card.

Take 0007 measured 30 shots (s14 and s15 still merge in the detector: 7.9 s), median 2.30 s, loudness range 8.2 LU
(11 before). Round 2's agreed fixes: the montage words sit on the horn and face; Nibs' beats all read as one strut;
s14-s15 is still 7.9 s with nothing to read; the scream's zoom lands on Nibs in profile; the bed drops out mid-scene
and the stingers are hot; "A standing ovation." needs the audience in the frame; candles flare on in the first
frames of every barn shot; the end card fades up over the world. Also: the poster's fox portrait reads as a cat
(a request to the sets builder). Applied for 0008: montage words in the lower third and a different gesture on each
kick; s14 2.8 s and s15 2.4 s down the row from the side, the time given to the silent wait in s16 (the hens turn to
the lens, unimpressed) and to Duke at full brightness in s10; Nibs faces the lens before the zoom (push at frame
214, scream at 3.6 s); the bed in C (the melody's key), drums under the flashback, out for the wait, a crash on
"it"; s18 over Duke's shoulder onto the four motionless hens; a second of preroll on the barn shots; the end card
opaque; s07 cut to 2.2 s so the poster lands on the line; lead tracks varied in side, height and drift.
