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
| 3 | 0009 | 8.0 | 6.5 | 7.0 | 5.5 | 6.5 | 6.5 | 6.0 | 7.0 | 6.5 | **6.61** | 5.5 | pass |
| 4 | 0010 | 8.0 | 7.0 | 7.0 | 5.0 | 6.0 | 7.0 | 6.0 | 7.0 | 6.5 | **6.61** | 5 | pass |
| 5 | 0011 | 8.0 | 7.5 | 7.0 | 5.0 | 6.0 | 6.5 | 6.0 | 7.0 | 6.0 | **6.56** | 5 | pass |
| 6 | 0012 | 8.0 | 7.0 | 7.0 | 5.5 | 6.5 | 6.5 | 6.0 | 6.5 | 6.5 | **6.61** | 5.5 | pass |
| 7 | 0003 (second climb) | 8.0 | 7.0 | 6.5 | 5.5 | 6.0 | 6.0 | **7.0** | 6.5 | 6.0 | **6.50** | 5.5 | pass |
| 8 | 0010 | 7.0 | 7.0 | 6.5 | 4.5 | 6.5 | 5.5 | 7.0 | 6.5 | 6.0 | **6.28** | 4.5 | pass |
| 9 | 0012 | 8.0 | 7.0 | 6.5 | 5.0 | 7.0 | 5.5 | **8.0** | 6.0 | 6.5 | **6.61** | 5 | pass |

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

Take 0008 found the master's true peak at +0.1 dBTP although the mastered wav measured -1.2: the AAC encode of a
dense, limited mix overshoots. Fixed in `audio/loudness.py` (limit 1 dB under the ceiling): 0009 measures -1.6 dBTP.
0009 also dropped the slow push on the bow, which cropped the top caption. 0009: 30 shots, median 2.25 s, longest
7.25 s, loudness range 7.7 LU, 70.1 s without the end card.

Round 3 held the average (6.61): technical +0.5 and text +0.5, camera -1.0, within the documented reviewer wobble.
Every reviewer named s16-bow: 5.9 s wide with Duke at 10% of the frame, the banner cut through by the top caption.
Others: "A standing ovation." needs the seated hens big and to the lens; the street tracks are one composition;
Nibs' anger in s19 has no gesture; the look to the lens in s05 is not a turn (he already faces it); the face
cut-in's horn sits on dark leaves. And a bug found in the strip: Nibs' s01 walk carried on into s02 over its
`place` (actors.csv), so the cut-in framed the goat by luck. Applied for 0010: s16 split into a 3.8 s medium of the
bow (Duke at about a third of the frame, caption at the bottom) and a 2.1 s s16b of Duke trotting in and taking
the trophy; s18 a medium on the four hens on the rail, all to the lens, Duke's line over them; `stop` before the
s02 `place` and the lens low, looking up, so the horn is against the sky; s05 from the side; s19 stops on "jump",
shakes its head and looks to the lens; s06 3.6 s; s10 2.0 s with a chin-up; s11 0.9 s; s17 and s18 a beat longer.

Round 4 (0010, 31 shots in the edit) held the average again: text +0.5, camera +0.5, acting -0.5, comedic timing
-0.5. Two reviewers traced the strut tracks' judder to the numbers (turn jerk 40-56 against about 1 on walk tracks):
the lead rig followed the puppet's body yaw, which the strut sways; fixed in `camera/Follow.java` (the axis follows
the subject's travel while it moves). Others: captions start 11-41 frames after their cuts; the challenge is
delivered in the same walking wide as nine other shots; the snap zoom read as a camera jump; the flashback speeds
up after the dip; the trophy grab is hidden behind the post; two hens are cut by the frame; the bed still drops out
(s05's scripted dropout, the silent wait). Applied for 0011: every line starts on its cut; Nibs halts at the board
(s07); s19 3.6 s; s28 stops early, turns square and a slow optical push (fov 84 to 50) replaces the snap zoom;
s10 2.6 s, s11 1.4 s, s12 1.6 s, s14 2.2 s, s18 2.5 s; the grab on the camera side of the post with a ding; all four
hens in frame, one getting bored; the bed under everything but the two black dips; more preroll on s09/s19/s20.

0011: silence only at the two dips; strut-track turn rates fell from p95 7-25 to 1-2 °/s with the Follow fix; camera
scored 8 from one reviewer for the first time. Round 5 (6.56) is inside the wobble of the plateau. The notes that
remain are about acting: the button (s30) is a 13%-high blob; "the best jumper in the valley" never jumps; no double
take at the board; the trophy vanishes without visibly reaching the mouth. Applied for 0012: Nibs jumps on "jumper"
(s01) and on "jump" (s19, now a closer side lead), a dead stop and double take at the board (s07, closer), s16b
tight on Duke's head at the post, s30 close on Duke facing the lens, s26 a 1 s beat, s29 2.6 s.

Round 6 (0012) is again 6.61, minimum 5.5: four rounds inside ±0.05 of the same average, so the climb stopped
there. **Best iteration: 0012** (tied for the best average with 0007, 0009 and 0010; the highest minimum; the only one
with every multi-word caption up for its reading time). 0013 is the script as committed (Duke's "zzz" moved above
him) and passes; its frames.csv and actors.csv match 0012's byte for byte where nothing changed.

## The second climb (night build, after round 6)

Rounds 3-6 sat inside ±0.05 of 6.61, so small tweaks were exhausted; this climb makes bigger moves on the weakest
criteria (acting, comedic timing, sound, energy, text). Iterations restart at 0001 in the production worktree; changed
shots were first checked in short test takes of only those shots (about a minute each) before a full take.

| Run | What changed | Measured | Seen |
|--:|:--|:--|:--|
| 0001 | Acting: a crouch before each jump; Nibs sniffs and bites at the produce stall (s04), skips and glances to the lens (s06), a dead stop and a glance-away-snap-back double take at the board with a whoosh (s07), a look to the lens on "plenty" and "snacks", head away to the valley then snapped to the lens on "Duke", a ram wind-up with the goat's prepare-ram sound, a stamp and the scream (s28, no swing). Duke: a fade-up wide of the hall, a panning trot (`locked`), steps onto note 1, trots along the tops of the seven note blocks (flush with the stage) as each plays under him, hops on one block for the big phrase, a crouch-and-climb onto the trophy's pedestal, a tilt-yawn-stretch-sleep button. The hens look four ways and snap to the lens together on "standing". Edit: the montage at the reference's exact lengths (0.5/0.25/0.5/0.35/0.5/0.25 s), a gesture per word, 140 px words at the top; punch-ins on "Nibs", "plenty", "jump" and the scream; one-frame head trims at the four joins that repeated a frame. Sound: a music drop on the look to the lens, full silence for the double take, the bed out with the picture at the dip, a sting and hit on Duke's card, a 1.8 s fade at the end, whooshes, boings, the fox's bite on the trophy | PASS 73.58 s | s14's walk along the note row reads at once; the hens' snap reads; s02 framed the chest, s15 too close to see the block, s16 from behind the rail made the hens white blobs, s16b's hop left the frame, the montage's last pushes put the lens on the goat |
| 0002 | Test takes: s02 head-on (`face`), s15 back and low in profile, s16 a medium, s16b up onto the pedestal on purpose (the anchor is the block centre; `face = "camera"` on the climb), gentler montage pushes | PASS; 29 shots (s14-s16 merge: three frames on the same red curtain, 9.7 s); silence between crickets in the bow | Every new beat reads |
| 0003 | s16 over Duke's shoulder to the hens (a new background for the detector; the bow plays to the unmoved audience); crickets every 0.35 s through s16-s17 | PASS 73.58 s; **30 shots**, median 2.39 s, longest 6.2 s; six under 0.6 s; black 0:26.15-0:27.03 and 1:05.37-1:06.03; silence only at the dips; −14.2 LUFS, −1.5 dBTP | Reviewed: round 7 |
| 0004 | Round 7's fixes: the montage cut on the voice's word onsets (23/28/22/21/17 frames after SIX, HIM held 0.5 s), words in the lower band and Nibs to the lens on each; s16 the bow in profile along the note row (barn windows behind, not the curtain); s11 pan lag 0.7; no punch-in on the s19 jump (it cropped the head) and a wider lead; Nibs stops and looks to the lens on "Nibs." then struts on; the stamp on "jump-off!"; one hen's lone flap-hop is the whole ovation; the goat's own eat and long-jump sounds; crickets under s12 | PASS 73.58 s; 29 shots (s14/s15 and s17/s18 joins not seen), median 2.40 s; six under 0.6 s; −14.2 LUFS | Stop on "Nibs.", the flap, the stamp read in the frames |
| 0005-0006 | s14 2.5 s at 3 blocks/s, s15 three hops filmed from the stage toward the audience (a new background), s17 the hen glances at her egg, quieter crickets; then a 0.7 s second dip and the card's sting 0.15 s in | PASS; 0005 measured 69.98 s without the end card (under 70) and its second dip not silent; 0006 72.6 s, both dips silent | |
| 0007-0008 | **The voice pass** (the owner: "prefer voices over captions", "you go super slow with the voice lines"): narration over every walking shot and the flashback, the narrator on Duke's card and the end card, commas where the TTS paused a second, cut_on into the horn and onto "Duke", every action retimed to the new onsets; then main's pace pass (lines trimmed, packed 0.12 s apart, 3.2 words/s target) and joke pauses marked `beat = true` | 0008: PASS 72.88 s, 29 shots, median 2.32 s; **26 voiced lines, a voice for 62% of the runtime, median 3.06 words a second, no dead air inside dialogue** (0006: 17 lines, about a third voiced, Nibs 1.9-4.4 and Duke 1.5-1.7 words a second) | |
| 0009 | **The side-by-side pass** (shot-by-shot against the reference): lead tracks pitched 20° down from 1.5 blocks at 108°; s02 a true face cut-in; s12 and s15 inserts with the block filling the frame; s16 and s18 from just behind the hens' heads, Duke small on the stage; s07, s19 wide; the montage three-quarter from near the ground; Duke large on the cards; s10 0.8 s, s26 0.25 s, s30 1.9 s; s06, s07, s14, s15, s19 longer. Sound: a mood-picked Minecraft track (`mood = "playful"`), a record-scratch on the poster, a rimshot after "standing ovation", a dramatic sting on the scream, the game's dings, boings, whooshes and bass drums | | |
| 0010 | The scream's sting moved from `[[edit.sfx]]` into the shot (an edit sound is not silenced over black, so it rang through the second dip); s18's caption back to the bottom | PASS 78.58 s; **33 shots** (the adaptive detector sees nearly every join), median 2.50 s; six under 0.6 s; both dips silent; −14.2 LUFS; 65% voiced, median 3.06 words/s, no dead air; bed `music/game/swamp/firebugs` (playful) | Reviewed: round 8 |
| 0011 | Round 8's framing faults: s02 head-on at eye level; s06 a side-on `track`; s11 fixed (the locked pan stepped); s12 from the side; s14 wider; s15's lens off Duke's path; s18 far enough back for all four hens; s19 keeps walking and makes a real 1.3-block jump on "fly" with a dazed landing; the montage looks up so the horn stays in | PASS 77.78 s; 32 shots; 66% voiced; true peak −0.4 dBTP (over −1) | The jump, the four hens, the profile step read |
| 0012 | Every spoken caption whole for its line (complete while spoken); s12 and s18 captions at the top; s16 on 30°; s07's hold with drift and a head move; s30 one eased sit-to-sleep; crickets only from the bow on; Nibs deadpans over the egg ("Meanwhile, the crowd went... mild.") | PASS 76.87 s; **30 shots**, median 2.51 s, longest 6.02 s; six under 0.6 s (1:01.20-1:02.77); both dips −70 LUFS; −14.2 LUFS, mix −1.7 dBTP (AAC master −0.9); 28 voiced lines, 67% of the runtime, median 3.06 words/s, no dead air | Reviewed: round 9, **best of the second climb** |

Words a second per line on 0008 (from voice.json: words over first onset to last end):

| Shot | Who | Line | Words | Words/s |
|:--|:--|:--|--:|--:|
| s01-nibs | nibs | Hey, it's me, Nibs. | 4 | 3.42 |
| s01-nibs | nibs | Best jumper in the whole valley. | 6 | 3.40 |
| s01-nibs | nibs | Ask anyone, nobody jumps like me. | 6 | 2.92 |
| s01-nibs | nibs | This horn. Look at it. | 5 | 2.94 |
| s03-bridge | nibs | One's plenty. | 2 | 2.28 |
| s04-market | nibs | Anyway, I was heading to the market... | 7 | 2.81 |
| s05-snacks | nibs | ...for snacks, obviously. | 3 | 2.47 |
| s06-notice | nibs | Then I strolled past the notice board, totally normal day. | 10 | 3.09 |
| s07-saw | nibs | And then I saw it. | 5 | 4.88 |
| s07-saw | nibs | Duke, again, three years running. | 5 | 2.42 |
| s09-remember | nibs | I remember last year's show like it was yesterday. | 9 | 3.06 |
| s10-duke | nibs | There he was, the champ. | 5 | 2.79 |
| s11-trot | nibs | Strutting around like he owns it. | 6 | 3.58 |
| s13-hit | duke | Hit it. | 2 | 6.62 |
| s14-notes | nibs | Then he played the notes, with his feet. | 8 | 3.58 |
| s15-note-one | nibs | Total show-off. | 2 | 2.29 |
| s16-bow | duke | Thank you, thank you, you're too kind. | 7 | 3.04 |
| s16b-trophy | nibs | Then he just took the trophy. | 6 | 4.25 |
| s18-ovation | duke | A standing ovation. | 3 | 3.09 |
| s19-jump | nibs | That fox can't even jump. | 5 | 2.93 |
| s19-jump | nibs | Watch me fly. | 3 | 3.47 |
| s20-least | nibs | Honestly? I'm at least six times more goat than him! | 10 | 3.14 |
| s27-today | nibs | So today, in front of everyone, | 6 | 2.86 |
| s28-challenge | nibs | I challenge Duke to a jump-off! | 6 | 2.89 |
| s29-card | narrator | Duke, three-time Talent Night champion. | 5 | 3.06 |
| end | narrator | Nibs versus Duke, the Jump-Off. | 5 | 3.12 |

Round 7 (0003 of the second climb, the first with the sound sheet in the packet): sound 7 for the first time
(the reviewer could check every effect against its frame: "sharp hits on jumps, hops, the egg and the trophy"),
pacing 8, camera 7; staging, timing and energy 6-6.5, so the average is flat (6.50). What they agreed on: the
montage words cut 7-15 frames off their spoken words and covered Nibs' head; the bow read from behind as a cropped
back; Nibs' first act is still one walk to the lens; the trophy climb, the egg, the jump and the sleep read without
text. Applied in 0004 and 0005 (table above).

Round 8 (0010: the voice pass and the side-by-side pass together) fell to 6.28 with acting 4.5, under the pass
line. The camera reviewer counted half the screen time in lead tracks "held dead centre" and the shot mix "nearly
the reference's"; pacing found 32 shots, a 2.5 s median and the montage "cut on each word's onset". What cost
points: the reference's framing made several beats too small or too close to read (Duke at 9% of the frame for the
bow and 6% for the ovation, the s15 insert under Duke's belly, the horn as a grey slab in the face cut-in), the
lead tracks still read as one repeated walk-in, "watch me fly" had no flight, and the subtitles, now at speech pace
(about 3 words a second), build word by word too fast to read (text 5.5). The side-by-side brief and the reviewers
pull in opposite directions on s16/s18 (high and wide with Duke small, against Duke at a quarter of the frame);
0011-0012 keep the reference's composition and tighten the lens.

Round 9 (0012, the final round of the second climb): 6.61, minimum 5.0, the best average of the climb and level with
rounds 2-6, with sound 8 (the reviewer checked every effect against its frame on the sound sheet) and pacing 8 /
comedic timing 8 from the pacing reviewer ("the montage cut on each word's onset", the poster cut on the frame
"Duke" is spoken). Still under 7: acting 5 (Nibs' own jokes, the horn, the snacks and the fly, are told more than
shown; Duke and the hens carry the visual laughs), text 5.5 (subtitles at speech pace break the 2.5 words/s and
reading-time rules by construction, the trade the owner asked for: voices over captions), technical 6. The
independent read with the stronger model (claude-fable-5-2) was not possible: the account answered HTTP 429 "You've
reached your Fable limit", so it was skipped. One Opus reviewer hung for 76 minutes after the network outage and
was stopped; the round was finished with the other five roles and the story review it had already written.

## Where it stands

**Best iteration of the second climb: 0012** (round 9, 6.61, minimum 5.0). Measured on 0012 against the benchmark's
checks:

| Check | Benchmark | 0012 |
|:--|:--|:--|
| Shots found by scene detection (1-30) | 30 ±2 | 30 (32 clips in the edit) |
| Median shot length | 2.3-3.0 s | 2.51 s |
| Opening | 5-7 s | 6.02 s |
| Shots over 7.5 s | none | none (longest 6.02 s) |
| Montage shots under 0.6 s | six, 0:58-1:01 | six, 1:01.20-1:02.77, each cut on its word's onset in the voice (16/21/15/15/12/15 frames) |
| Black stretches ≥ 0.5 s | two, about 0:27 and 1:07 | 0:28.13-0:29.02 and 1:09.25-1:10.12 |
| Lead tracks: Nibs centred, size steady | middle third, < 15% change | x 0.46-0.55 on every lead and track; size change 0-10% except s01 (39%) and s19 (35%), their jumps, s06 (17%, the side track) and s28 (51%, the optical push) |
| Captions | ≤ 2.5 words/s, ≥ 1 s | spoken subtitles at speech pace: 10 lines over 2.5 words/s, 8 under reading time, the montage's one-word cards 0.20-0.35 s; every spoken caption shown whole for its line |
| Loudness | −14 ±1 LUFS, no clipping | −14.2 LUFS; mix −1.7 dBTP, AAC master −0.9 dBTP; original-audio x export −14.1 LUFS / −1.7 dBTP |
| Silence at the dips | < −50 LUFS | −70 LUFS integrated over both black gaps |
| Egg plop and scream on their frames | ±2 frames | egg 7 ms from its frame; the scream is placed on its frame (68.267 s) but the onset check cannot separate it from the dramatic sting that starts on the same frame |
| Running time | 70-74 s + 2 s card | 74.57 s + 2.3 s card (the side-by-side pass lengthened shots toward the reference's 82.2 s) |
| Voice | (owner: near-continuous, ~3 words/s) | 28 lines, a voice for 67% of the runtime, median 3.06 words/s, no dead air inside dialogue |

Side-by-side against the reference (`videocraft compare --side-by-side`, the sheet and table outside the repo): 30
paired shots, the same camera family on every one; 9 within ±15% of the reference's length; ours 76.87 s against
82.20 s. Lead tracks now match its look (road in the lower two thirds, almost no sky, a 108° bend); the face cut-in
fills the frame; the montage is three-quarter from the ground at about half the frame height; Duke is 0.48-0.55 of
the frame on both cards.

What still holds the score under 7, by the reviewers' repeated notes: acting (5: puppets with no faces, and Nibs'
brags are spoken rather than shown), text (5.5: subtitles at speech pace), the reference's small-Duke compositions
for the bow and the ovation (Duke 9% and 6% of the frame; one reviewer asks for 25%), and technical 6 (two frozen
holds, the s30 pose changes).
