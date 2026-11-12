# Benchmark: a PinkSheep-style comedic short

Status: draft from the research pass, 2026-11-11. Owner of the numbers: this file. The reference video and every
frame, clip and analysis file made from it stay in `reference/` (git-ignored) and are never committed.

## What this benchmark is

One test of whether blockreel is good: given a shot list, can it produce a short, funny Minecraft video with the
**form** of a well-known Minecraft comedy channel at its peak? Form means structure, shot count and lengths, camera
language, staging, character acting, pacing, on-screen text and energy.

The output is an **original** video. It must not use PinkSheep's character or skin (a pink sheep with a moustache),
the rival character (Purple Shep), the creator's voice, audio, music, jokes, title or thumbnail, or any footage. Our
video has its own characters and its own script ([below](#the-original-benchmark-script-nibs-vs-duke)). Reviewers
score it against the reference's form ([rubric](#scoring-rubric)), not its content.

## The reference

| | |
|:--|:--|
| Title | PINK SHEEP vs PURPLE SHEP (Minecraft RAP BATTLE) |
| Channel | PinkSheep |
| URL | https://www.youtube.com/watch?v=5nksTeAYa8Y |
| Published | 2017-03-11 · 4:03 · about 2.39 million views when fetched |
| Section used | **0:00.0 to 1:22.2**: the scripted cold open, up to the cut onto the rap stage |
| Local copy | `reference/5nksTeAYa8Y.mp4` (720p60) and auto-captions `reference/5nksTeAYa8Y.en.vtt`, for study only |

**Why this one.** It is one of the channel's most-viewed videos (the top ten of 589), from its peak years, and the
cold open is everything a scripted recorder should be able to do: a built city set and a built interior, three
characters, no improvised play, no first-person footage, a camera that moves with purpose, cuts timed to the words,
a cut-in gag, a framed flashback, a rapid brag montage, dips to black and graphic cards. It is fully scripted
machinima, not a recording of someone playing.

The rest of the video (1:22 to 4:03) is the rap itself: mostly 2D cartoon character cards and a rendered character
over an audio visualiser, driven entirely by the vocals. It is out of scope; it tests a motion-graphics editor, not a
game recorder.

**Runners-up, and why not.**

1. *AM I REALLY THAT UGLY?! | Minecraft* (2016, 10:05, about 2.4M views, `YHZKMAtq-XA`). The most representative of
   the channel's everyday format: a creative-server build tour on a flat world, first person, live commentary, chat on
   screen, an inserted stock photo as a gag. Passed on because it is ten minutes of improvised first-person play at
   about 5 cuts a minute, and every joke is in the voice. It would test the human input model, not staging, camera
   language or acting. A good *second* benchmark for the first-person side once voice exists.
2. *Minecraft In 5 Years* (2019, 3:03, `YFdEn940pC0`). Short and fast (about 37 cuts a minute), but most of it is stock
   photos, meme images, spreadsheets and a 2D avatar; there is very little game footage. It tests a meme editor.

Also looked at and dropped: *KILLER SHEEPS ON THE LOOSE?!* (server minigame play, not stageable), and the channel's
recent uploads (2019 on: mostly talking-avatar commentary on YouTube drama, Roblox, or not Minecraft at all).

### How it was analysed

All from the local copy with ffmpeg: scene-change scores (`select=gt(scene,…)` and `scdet` on the full frame and on a
blurred 32×18 copy, which ignores walking motion and keeps location changes), contact sheets at 2 to 6 frames a
second over the section, before/after frame pairs at every doubtful cut, momentary loudness (EBU R128) per second, and
the auto-captions' word timings. I cannot listen to audio, so what the audio does is inferred from the captions and the
loudness curve. Cut times are good to about ±0.1 s for hard cuts and ±0.3 s for the jump cuts inside the walking
passages, which change location without much change in the picture.

## Shot-by-shot breakdown (0:00 to 1:22)

Camera types used below:

- **Lead track**: the camera travels backwards in front of a character walking towards it, at about the
  character's head height (roughly one block up), pitched slightly down, with a very wide lens (straight road lines
  bow strongly, as with a high FOV or a lens-distortion shader). The character stays near the centre and at a fixed
  size while the street flows past. This one move is half the section.
- **Static**: a locked-off camera, no movement.
- **ECU / cut-in**: an extreme close-up inserted for a single word.
- **Insert**: a close-up of an object or a hand.
- **Graphic**: a full-frame 2D card (not game footage).

The world is shaded throughout (warm light, soft shadows, slight depth-of-field blur on close-ups). The hero is a
player model swapped for a sheep model (a morph or model mod) with a custom skin; it walks at walking pace, never
sprints. Narration is the creator's voice-over. "VO" below quotes the auto-captions (which mishear "Shep" as "Chef").

| # | Start | Len (s) | Camera | Framing | Action | Staged | Text / graphics | Audio |
|--:|--:|--:|:--|:--|:--|:--|:--|:--|
| 1 | 0:00.0 | 7.04 | Lead track, slight yaw drift | Wide; hero about 1/5 of frame height, starts close to a parked pink car | Hero walks towards camera down a curving street | City set: asphalt road with dashed centre line, kerbs, pavements, houses, pink buildings, trees, lamp posts, benches, parked car | none | VO greeting and setup ("so today I was watching one of my old videos…"); music bed under the voice |
| 2 | 0:07.0 | 1.35 | ECU cut-in with a small punch-in step | Face fills the frame: eyes, moustache | Holds | none | none | VO "…un-fleek my **moustache**": the cut lands on the brag word |
| 3 | 0:08.4 | 1.90 | Lead track | Wide | Walks across a zebra crossing | Crossing, benches, mailbox | none | VO "…and how handsome I really am" |
| 4 | 0:10.3 | 3.54 | Lead track (jump cut, new street) | Wide | Walks on | New stretch of street | none | VO "anyway, so when the video was done…" |
| 5 | 0:13.8 | 2.69 | Lead track, closer | Medium; hero about 45% of frame height | Walks, then **turns its head and body to look at the lens** | Street | none | VO "…the kitchen to get some burritos…": cut lands on "kitchen" |
| 6 | 0:16.5 | 5.38 | Lead track | Wide | Walks the length of a block | Street, a TNT-branded shop front | none | VO "when I came back I realised I forgot to disable autoplay…" |
| 7 | 0:21.9 | 3.14 | Lead track (jump cut) | Wide | Walks past houses | Crossing, shop front | none | VO "I sat down and looked at it" |
| 8 | 0:25.0 | 2.49 | Graphic insert | A YouTube search-result row (thumbnail, title, views) on black | none | none | The video page itself | VO "…one of **ExplodingTNT's** Christmas videos": cut on the name |
| 9 | 0:27.5 | 2.97 | Lead track, then **dip to black** | Wide | Walks on | Street | none | VO "I watched the video until this part played"; then about 1 s of near-silence |
| 10 | 0:31.4 | 0.65 | Static, fades up from black | Medium on a Santa character | Santa stands | **Flashback frame starts**: everything until shot 18 sits inside a thick pink glowing border, as a video-within-the-video | Pink border | Music enters |
| 11 | 0:32.1 | 1.28 | Static, high | Wide room | Santa walks to a jukebox | Interior set at night: wood-panelled room, windows with snow outside, fireplace, wrapped presents (custom heads), jukebox | Border | Music |
| 12 | 0:33.3 | 1.37 | Insert | Close on Santa's hand and a music disc | Puts the disc in | Jukebox | Border | Music |
| 13 | 0:34.7 | 3.07 | Static | Medium; present in the foreground | Santa beside a present | Room | Border | Music, louder (about −8 LUFS momentary, up from about −15 under narration) |
| 14 | 0:37.8 | 5.01 | Static | Medium on the jukebox | none: the music "comes from" the jukebox | Jukebox | Border | Rival character's rap begins ("yo yo yo, it's your child Purple Shep…"), in-world voice |
| 15 | 0:42.8 | 4.88 | Insert with slow push-in | Close on the jukebox speaker grille | none | Jukebox | Border | Rap continues |
| 16 | 0:47.7 | 5.98 | Static, high, longest flashback shot | Wide room; present big in the foreground, Santa small by the window | Santa stands, turns | Room | Border | Rival: "Hey kid, guess what, I'm giving you a toy… you were expecting a…" |
| 17 | 0:53.6 | 3.03 | Static | Medium close-up, Santa facing the lens | Santa delivers the punchline to camera | Room | Border | "…you were expecting a **toaster**, weren't you": the cut to the face lands on the first word of the punchline line and holds through it |
| 18 | 0:56.7 | 2.90 | Static | Wide room, fireplace, presents | Santa among presents | Room | Border ends with the shot | "Thing is, Purple Shep always comes through" |
| 19 | 0:59.6 | 5.10 | Lead track | Wide | Back on the street, walking | Street | none | VO "when I heard it again it reminded me that I'm much better than Purple Shep" |
| 20 | 1:04.7 | 1.46 | Lead track with a camera swing | Wide | Walks across a crossing | Street | none | VO "so if he can rap that means I'm at least…" |
| 21–26 | 1:06.1 | 0.53, 0.20, 0.55, 0.37, 0.55, 0.18 | Lead track, closer, six jump cuts | Medium close-up, hero about half the frame height, each in a different place on the street | Hero struts at the lens | Six spots on the street | none | VO "**43 times** better than him at rapping": the montage starts on "43" |
| 27 | 1:08.5 | 1.87 | Lead track | Wide | Walks | Street | none | VO "so today your boy is going to…" |
| 28 | 1:10.4 | 5.20 | Lead track (jump cut), then **dip to black** | Wide, the camera swings round as the hero turns to the lens | Walks, turns to camera | New street, park | none | VO "…**challenge** Purple Shep to a rap battle. It is going to be lit, let's just get right into—": cut on "challenge"; dip to black on the last word; about 1 s of near-silence (below −60 LUFS) |
| 29 | 1:16.6 | 3.40 | Graphic | 2D cartoon face of the rival, centred on black, fades up and down | none | none | Character card | "…it" |
| 30 | 1:19.7 | 1.20 | Graphic (game render on black) | The rival's 3D model, small and centred on black | Stands | none | none | Beat drops on "yo yo yo"; 1.3 s of black follows, then the hard cut to the rap stage at 1:22.2 |

### The aggregate picture

| Measure | Value |
|:--|:--|
| Shots in 82.2 s | **30** (plus three stretches of black totalling 2.9 s) |
| Shots per minute | **21.9** (17.5 without the six-shot montage). The whole 4-minute video: about 20 per minute at the same detection threshold |
| Shot length | median **2.6 s**, mean 2.6 s; median 3.0 s outside the montage; longest 7.0 s (the opening) |
| Distribution | under 1 s: 7 · 1 to 2 s: 7 · 2 to 4 s: 9 · 4 to 6 s: 6 · 6 s and over: 1 |
| Camera mix by screen time | lead track **52%** · static **27%** · close inserts 8% · graphics 9% · ECU cut-in 2% · black 3% |
| Camera mix by shots | lead track 17 · static 7 · inserts 2 · graphics 3 · ECU 1 |
| Not used at all | first person, over the shoulder, orbit, crane, handheld shake, split screen |
| Sets | 2: an exterior city street (never the same stretch twice in a row) and one interior room at night |
| Characters on screen | hero (17 shots), rival in disguise (9 shots), rival card and model (2) |
| Voice | on about 85% of the section: the creator's narration for 0:00 to 0:30 and 1:00 to 1:16, the rival's in-world voice for 0:38 to 1:00 |
| Music | a bed under the narration (between phrases the loudness floor stays around −18 to −25 LUFS instead of falling to silence; inferred, not heard), louder in the flashback, cut to silence for each dip to black |
| On-screen text | **none** in the section: no captions, no titles. Graphics are a captured web page, a 2D character card and a coloured flashback border. The video's end screen (3:38 on) has "PREVIOUS VIDEO / SUBSCRIBE" |

How the comedy is timed:

- **Cuts land on words.** All 13 hard cuts on the street fall within 0.2 s of a word's first syllable, and 12 of them
  on a key word or the first word of a new sentence: "fleek" (moustache cut-in), "anyway", "kitchen", "when",
  "exploding" (insert), "I watched", "43" (montage), "challenge". The picture illustrates the word the instant it
  is said.
- **Brag beats get a visual exaggeration.** The moustache cut-in (1.35 s) and the six-shot strut montage (2.4 s for six
  shots) are both the hero praising itself. The montage is the only run of sub-second shots in the section.
- **Setup wide, punchline close.** In the flashback the camera sits wide and still while the joke is set up (shot 16,
  the longest at 6 s), then cuts to a close-up facing the lens for the punchline (17).
- **Looking at the lens** is the acting: the hero turns to the camera twice (shots 5 and 28) at the ends of sentences.
- **Dips to black** mark the two scene changes (into the flashback, into the battle) and give a beat of silence before
  each reveal.
- Acting is minimal otherwise: walking, turning, standing. The energy is in the voice, the cutting and the moving
  camera, not in the body.

## Capability checklist for blockreel

Status: **done in prototype** (T3 Craft's launch-video recorder did it: `scripts/demo/`, `DemoRecorder`, `DemoHand`,
`DemoOverlay`, `DemoCameraMixin`, `DemoClockMixin`), **partial** (the prototype has the base, blockreel needs more),
**build** (nothing yet), **out of scope for now** (with the reason).

### Capture and timing

| Capability | Status | Note |
|:--|:--|:--|
| Hidden client, frames from the game's framebuffer, no window or OS input | done in prototype | `DemoRecorder` pipes raw RGBA to ffmpeg per shot |
| Fixed clock: exactly 1/60 s of game time per captured frame | done in prototype | `DemoClockMixin` |
| A shot that fails to stage fails the take with a reason | done in prototype | `DEMO RESULT FAIL …` |
| Beat marks inside a shot, for the edit | done in prototype | `marks.txt` |
| Cut on a word: shot boundaries placed from the caption (or voice) timeline, to ±2 frames | build | The prototype marks beats in the game; it needs the reverse: the script's timeline decides where the beat must fall |

### Camera

| Capability | Status | Note |
|:--|:--|:--|
| Camera operator following a subject with lag (damped spring) | done in prototype | `DemoHand.Operator`, third-person and cinematic rigs |
| **Lead track**: camera backs away in front of a walking subject at its head height, holding its size in frame | partial | Same operator, but placed in front and facing back, at low height, path-aware so it does not hit lamp posts |
| Lens control: wide FOV (around 100 to 110) for the lead track, narrow for close-ups | build | The prototype pins the game's default FOV |
| Locked-off static shot | done in prototype | Cinematic camera with no follow |
| Extreme close-up of a character's face without clipping into it | build | Camera inside a block of the subject needs near-plane handling; or shoot medium and crop |
| Punch-in zoom in post | done in prototype | `edit.sh` zoompan crops, nearest-neighbour scaled |
| Swing: the camera turns to follow a character turning to the lens | partial | The operator follows aim; needs a cue to swing |
| First person with a human hand on the mouse | done in prototype | Not used by this benchmark (the reference has no first person) |

### Characters and acting

| Capability | Status | Note |
|:--|:--|:--|
| Several scripted actors at once, walking with leg swing and body turning into the heading | done in prototype | Humanoid Mannequins (`OfficeResidents`) |
| Custom skins on humanoid actors | done in prototype | `AgentAppearance` |
| A small pose vocabulary: wave, stretch, sip, speak, listen, type, look at someone | done in prototype | `AgentLife.Activity`, `AgentPose` |
| **Non-humanoid actors**: a mob (goat, fox, chicken…) as a scripted character: walk a path, stop on a mark, turn its head to a point, play its own animations on cue | build | The reference's hero and rival are not humanoids; ours will not be either |
| Custom texture for one actor (a recoloured mob) | build | Fallback: vanilla variants and states (snow fox, a goat with one horn) |
| Look at the lens on cue | partial | `AgentPose` looks at the player; the camera is not the player |
| Hold an item, hand an item over | build | Fox holds items in its mouth natively; needs a cue |
| Player-driven hero (real input: walk, sprint, jump, sneak) | done in prototype | `DemoRecorder.Keys`; this benchmark can use actors only |

### Staging

| Capability | Status | Note |
|:--|:--|:--|
| Place a designed building from data, at an origin and rotation | done in prototype | `OfficeDesign` / `OfficePlacement` |
| **Set library**: load an exterior street and an interior room from structure or schematic files, several takes in different stretches of one set | build | The reference never shows the same stretch of street twice running |
| Time of day, lamps on, night through windows | done in prototype | The dusk title shot |
| Props: jukebox, note blocks, player heads as presents, signs, map-art posters, item frames | partial | Item frames and text displays exist in the prototype; heads and map art do not |
| Particles and effects on cue (notes, hearts, smoke, a burst) | build | The prototype only switches particles on or off |
| Clean frame: no HUD, hand, crosshair, chat, name tags unless wanted | done in prototype | |
| Shader look (warm light, soft shadows, depth of field) | out of scope for now | Iris/shader integration in a hidden client is a large risk for v1; the rubric scores readability, not lighting style |

### Edit, text and graphics

| Capability | Status | Note |
|:--|:--|:--|
| Shots cut in story order with head and tail trims | done in prototype | `edit.sh` |
| Sub-second shots (0.2 to 0.6 s) in a montage, frame-accurate | partial | Trims exist; needs the cut-on-word timeline |
| **Dip to black / fade up from black** | build | The prototype only fades audio |
| **Framed flashback**: a coloured border or vignette and a grade over a run of shots | build | |
| **Full-frame graphic insert**: a 2D image, a card, a captured page | build | |
| Word-by-word captions with a highlighted key word, in the game's font, outlined | done in prototype | `DemoOverlay` |
| Title and end cards | done in prototype | `DemoOverlay` title card |

### Audio

| Capability | Status | Note |
|:--|:--|:--|
| A music bed for the whole cut, with fades | done in prototype | One Minecraft track from the local assets (`edit.sh`) |
| **Game sound effects in the cut**: footsteps, mob sounds, note blocks, jukebox, on the frame they happen | build | The prototype records muted (`-an`); either capture the game's mixer or rebuild an SFX track from an event log the recorder writes |
| Mixing: duck the music under lines and SFX, loudness-normalise the master (−14 LUFS integrated) | build | |
| Positional, in-world music (a jukebox or note blocks "playing" in the room) | build | Follows from SFX capture |
| Voice-over (synthetic voice) | out of scope for now | No voice in v1; see [what that costs](#what-no-voice-costs) and where it slots in |

### The five capabilities blockreel most needs that it does not have

1. **A sound track**: capture or reconstruct the game's own sound effects, put them on the frames they belong to, and
   mix them with a ducked music bed. Without a voice, SFX carry the jokes.
2. **Non-humanoid actors**: mobs as scripted characters with marks, paths, head turns, their own animations on cue and
   an optional custom texture.
3. **The camera vocabulary of the reference**: the low wide-lens lead track, lens (FOV) per shot, close-ups of faces
   without clipping, a swing to follow a turn.
4. **Sets**: load an exterior and an interior from files and stage takes at different spots in them.
5. **Edit grammar beyond hard cuts, timed from the script**: cut on a caption word, dips to black, a framed and graded
   flashback, full-frame graphic cards, sub-second montage shots.

## The hard problems

**Comedy without a voice-over.** The reference is about 85% voice. Its jokes are lines ("you were expecting a
toaster") and the picture illustrates them. With captions only, the joke has to be readable in the picture and the
caption must be short enough to read before the cut. Reading speed caps a caption at about 2.5 words a second with a
minimum hold of a second, against the reference's spoken 2.7 words a second; so captions carry roughly 40% fewer
words, and the cut has to wait for the reader, which pushes shots longer. Ways back: put the punchline in the action
(a reaction, an object, a sound) rather than in a line; give each character a "voice" from its own game sounds (a
bleat or a fox yip on the first word of each of its captions); highlight the one key word of each caption, and cut on
that word's appearance instead of on a spoken syllable.

**Several acting characters.** The reference only needs a hero that walks and turns and a rival that stands, but in
two different places at once in the cut. Two mobs need marks, timing relative to each other, looks at each other and
at the lens, and their natural AI switched off without freezing their idle life (breathing, ear and tail motion).

**Custom looks.** The reference's hero is a custom model and skin. Ours must be visibly its own character at a glance
and from far away, which for a mob means a texture or a distinctive vanilla state, and a consistent look between the
3D actor and any 2D card of it. The 2D cartoon card (shot 29) needs original art; blockreel can avoid drawing by
rendering the actor's own model on black as the card.

**Sound effects.** The game is muted in every hidden run today. Recording what the game plays (or logging every sound
event with its frame and rebuilding the track) is the single biggest gap between the prototype and something that
feels like a YouTube video.

**Sets.** The reference's street is a large detailed build. We need original builds (or permissively licensed ones,
with credits) that read clearly on a wide lens: strong lines on the ground, colour, depth, landmarks that tell the
viewer the hero is moving through a place.

### What no voice costs

Against this reference, captions-only gives up the most important channel. Expect it to cap these rubric criteria:
comedic timing (punchlines arrive by reading, a beat later than speech), pacing (shots must be held for reading) and
energy. A fair target for the first version is **7 on comedic timing and pacing, not 9**. Where a synthetic voice
track slots in later: every narration caption in the script below is written as a spoken line and marked **VO**; a
text-to-speech pass reads them on the same timeline, the captions stay as subtitles, the music ducks under it, and
cut points move from "caption word appears" to "word is spoken". The rival's lines (marked **DUKE**) would be a second
voice.

## Scoring rubric

Reviewer agents score each criterion from 1 to 10 against the reference's form. The numeric targets come from the
breakdown above and can be measured on our export with the same tools (`ffmpeg … scdet`, `ebur128`, contact sheets).
Each criterion says what a 5 and a 9 look like. The benchmark passes at an average of **7 or more with nothing under
5**, and the originality gate.

| # | Criterion | What it measures | A 5 looks like | A 9 looks like |
|--:|:--|:--|:--|:--|
| 0 | **Originality gate** (pass/fail) | No PinkSheep character, skin, rival, voice, audio, music, jokes, title, thumbnail or footage | — | Pass. A fail fails the benchmark whatever else scores |
| 1 | **Pacing match** | Shot count, length distribution, rhythm | 20 to 24 shots in 60 to 75 s, or 30 shots but evenly spaced at about 2.5 s each: no long opening, no montage, the rhythm is mechanical | 28 to 32 shots; median 2.3 to 3.0 s; a 5 to 7 s opening; one montage of at least five shots under 0.6 s; no shot over 7.5 s; the cutting speeds up on the brag and slows into the flashback |
| 2 | **Camera language and variety** | The reference's mix and moves | Mostly one camera type; the follow shots are behind the subject, not leading it; static shots wander; one close-up or none | Lead track about half the screen time, statics about a quarter, at least one face cut-in and two close inserts and two graphic cards; lead tracks hold the subject's size and centre; wide lens on tracks, tighter on close-ups; nothing passes through geometry |
| 3 | **Staging and sets** | Do the places read and serve the jokes | One set, or sets that read as test worlds (flat, empty, repeated); props placed but not used | Two distinct sets that read at a glance (a street that changes as the hero walks, an interior with a clear stage and lighting); every prop on screen pays off; no repeated stretch in consecutive shots; no unloaded chunks or void |
| 4 | **Acting readability** | Can you tell what each character feels and wants with the sound off and the captions covered | Characters move from mark to mark; turns and stops look scripted or robotic; one gesture repeated | Every beat reads without text: the strut, the look to the lens, the reaction; mobs keep idle life between beats; actions start and stop with human-like timing, not on round frames |
| 5 | **Comedic timing** | Do the cuts and reactions land the jokes | Jokes exist in the captions but the picture does not help them; cuts fall between words; the punchline shot arrives late | Cuts land within 2 frames of the key word's appearance; setups wide, punchlines close and to the lens; a beat of hold after each punchline; at least four separate laughs in 70 s, two of them visual only |
| 6 | **Text use** | Captions and cards | Captions readable but long (over two lines), on screen too briefly or covering the action; no key-word emphasis | One or two lines, under 2.5 words a second, never under 1 s; key word highlighted and timed to the cut; text never covers a face or the gag; cards are clean and consistent with the characters |
| 7 | **Sound** | Music bed, effects, mix | A music bed only, or effects that are late or missing on visible actions; uneven loudness | Bed under everything, ducked under character sounds; every visible action that should make a sound makes it on the right frame; silence used deliberately at the dips; master at −14 LUFS (±1) with no clipping |
| 8 | **Technical cleanliness** | The frame itself | Occasional judder, a HUD element or name tag leak, a frame of the wrong shot at a cut, chunk pop-in, a camera clipping into a wall | 1080p (or more) at a steady 60 fps; no HUD, hand, crosshair, chat or debug text; no pop-in or flicker; cuts frame-exact; colours consistent across shots; reproducible from the same shot list and seed |
| 9 | **Energy** | Does it feel like a YouTube comedy short rather than a demo | Competent but flat: it plays like a showcase of the tool | Watched cold, a viewer would believe a channel made it; it keeps moving, builds to the reveal and ends on a button |

## The original benchmark script: *Nibs vs Duke*

### The characters

- **Nibs**, the hero: a goat with a slate-blue-grey coat and **one horn** (the other one is gone; a goat that has lost a
  horn is a vanilla state). Cocky, loud, sure it is the best jumper in the valley. Its "voice" is the goat's own
  bleat, and at the big moment the screaming goat's scream. Clearly not a sheep, not pink, no moustache.
  *Fallback if custom textures are not ready:* a vanilla goat with its left horn missing.
- **Duke**, the rival: a **snow fox** (the white vanilla variant). Smug, unbothered, three-time champion of the village
  Talent Night. Its "voice" is the fox's yips and screech. Native business we can use: sitting, sleeping, the
  crouch-and-head-tilt, holding an item in its mouth.
- **The audience**: four chickens on a fence rail. One of them lays an egg.

### Premise

Nibs is strutting down the village market lane, telling us (in captions) how magnificent it is, when it passes the
notice board: the poster for Talent Night, champion three years running: Duke. Dip to black and into last year's show,
framed like a memory: Duke in the barn, a note-block solo, a golden trophy carried in its mouth, a crowd of chickens
whose only applause is one egg. Back on the lane, Nibs decides it is at least six times more goat than that fox,
challenges Duke to a jump-off, and screams it at the sky. Cut to Duke's card. Cut to Duke himself on black, who hears
the challenge, yawns, and lies down to sleep.

### Form

Thirty shots in 71.8 s, matching the reference shot for shot in order, camera type and relative length (the
reference's lengths times about 0.88), then a 2 s end card outside the measured section. Same two sets in the same
order: an exterior lane for shots 1 to 9 and 19 to 28, an interior for the framed flashback 10 to 18, graphic cards 8,
29 and 30. Same devices at the same places: the face cut-in on the brag (2), the look to the lens (5, 28), the page
insert (8), dips to black before each reveal, setup wide and punchline close in the flashback (16, 17), the six-shot
brag montage (21 to 26).

### Sets and staging

- **Market Lane** (exterior, late afternoon, clear sky): an original build, not a city street. A curving lane of
  path blocks and cobblestone with a strong pale centre line of smooth stone (so the wide lens has lines to bend),
  market stalls with coloured wool awnings, lanterns on fence posts, barrels and flower pots, cottages behind, a
  well, and a notice board (a sign wall with a map-art poster). It must offer at least eight stretches that look
  different, so no two consecutive lead tracks show the same place.
- **The Barn Stage** (interior, night): a wooden barn with hay bales, a low stage of spruce planks, a row of note blocks
  across the front, lanterns and a few candles, windows showing moonlight, a fence rail with four chickens as the
  audience, and a golden trophy (a gold block on a fence post, or a golden item Duke can carry).
- **Flashback frame**: a warm amber border with a soft inner glow and a slight sepia grade over shots 10 to 18 (our
  colour, not the reference's pink).

### Captions

White game-font words with a dark outline, popping in word by word (the style of T3 Craft's
`DemoOverlay`), one key word per caption in yellow, at most two lines, kept out of the faces. **Bold** in the script marks the
key word; the cut lands when it appears. "VO" lines are Nibs' narration (spoken by a voice track later); "DUKE"
lines are the rival's. Each Nibs caption starts on a bleat, each Duke caption on a yip.

### Shot list

Times are from the first frame. Lengths are targets; ±10% per shot is fine if the total stays within 70 to 74 s.

| # | Start | Len (s) | Camera | Action | Staging | Text | Sound |
|--:|--:|--:|:--|:--|:--|:--|:--|
| 1 | 0:00.0 | 6.2 | Lead track, wide lens (about 105°), camera about 1 block up, pitched 5° down, yaw drifting a few degrees | Nibs struts towards the lens up the curving lane, head high | Lane, first stretch: stalls both sides, lanterns, a cart | VO "Hey. It's me. **Nibs.**" then "Best jumper in the whole valley." | Music bed (upbeat, light) starts on frame 1; goat footsteps; bleat on each caption |
| 2 | 0:06.2 | 1.2 | ECU cut-in, punch-in from 1.0× to 1.15× over the shot | Nibs' face and its single horn fill the frame; holds still, one blink | none | VO "This **horn.**" | Bleat; a tiny "ding" from a note block (a bell) on the key word |
| 3 | 0:07.4 | 1.7 | Lead track | Nibs crosses a small plank bridge | Bridge over a stream | VO "One's plenty." | Footsteps change to wood |
| 4 | 0:09.1 | 3.1 | Lead track (new stretch) | Nibs walks past a stall | Stall with an awning, villager-free | VO "Anyway. I was heading to the **market**…" | Bleat; bed |
| 5 | 0:12.2 | 2.4 | Lead track, closer: Nibs at about 45% of frame height | Nibs walks, then stops and turns its head to the lens, deadpan | Lane by the well | VO "…for **snacks.**" | Bleat; one beat of music dropout as it looks at the lens |
| 6 | 0:14.6 | 4.7 | Lead track | Nibs walks on past the well and a lantern | Lane, well, flower pots | VO "Then I walked past the **notice board.**" | Footsteps; bed |
| 7 | 0:19.3 | 2.8 | Lead track (jump cut, new angle) | Nibs slows down, head turning right as it passes something | The notice board edging into frame on the right | VO "And I saw it." | Bed thins to drums |
| 8 | 0:22.1 | 2.3 | Graphic insert: full-frame, straight-on view of the poster | none | Map-art poster: "TALENT NIGHT · Champion 3 years running: DUKE" with a drawing of a white fox and a trophy (original art) | The poster's own text; caption VO "**Duke.** Again." | A low note-block "dun" on "Duke" |
| 9 | 0:24.4 | 2.6, then 0.8 black | Lead track, then dip to black over the last 0.4 s | Nibs stares at the board, then walks out of frame | Notice board | VO "I remember last year's show…" | Bed fades out with the picture; 0.8 s of silence |
| 10 | 0:27.8 | 0.6 | Static, fade up from black | Duke sits centre stage, chin up | Barn stage, lanterns; **flashback frame begins** (amber border, sepia grade) | none | Barn ambience: crickets, a creak |
| 11 | 0:28.4 | 1.1 | Static, high and wide | Duke trots across the stage to the note blocks | Barn, stage, chickens on the rail | none | Fox footsteps on wood |
| 12 | 0:29.5 | 1.2 | Insert, close | Duke dips its head to the first note block, which plays on that frame (triggered by the script) | Note block row | none | First note of Duke's solo |
| 13 | 0:30.7 | 2.7 | Static, medium, trophy in the foreground | Duke sits beside the trophy, smug | Gold trophy on a post | DUKE "Hit it." | Yip; the solo starts properly (an original note-block melody, about 120 bpm) |
| 14 | 0:33.4 | 4.4 | Static, medium on the note block row | Note blocks play on their own, note particles rising from each in time | Note blocks | none | The melody, in-world and positional |
| 15 | 0:37.8 | 4.3 | Insert with a slow push-in (1.0× to 1.2×) | Close on one note block as its particles rise | One note block | none | Melody's big phrase |
| 16 | 0:42.1 | 5.3 | Static, high, wide; chickens big in the foreground, Duke small on stage | Duke finishes, bows (crouch), picks up the trophy in its mouth and waits for applause; the chickens do nothing | Barn, chickens, stage | DUKE "Thank you. Thank **you.**" | Melody ends; total silence for 1.5 s apart from crickets |
| 17 | 0:47.4 | 2.7 | Static, medium close-up of one chicken facing the lens | The chicken blinks, then lays an egg (it pops out beside it) | Fence rail | none: the joke is the egg | The egg plop, then one cluck. Leave 0.5 s after it |
| 18 | 0:50.1 | 2.6 | Static, wide | Duke on stage with the trophy in its mouth, tail up, satisfied; **flashback frame ends** with the shot | Barn | DUKE "A **standing** ovation." | A slow yip; fade the ambience |
| 19 | 0:52.7 | 4.5 | Lead track | Back in the lane: Nibs walking, head down, then lifting it with resolve | Lane, new stretch | VO "That fox can't even **jump.**" | Bed returns, harder (drums in) |
| 20 | 0:57.2 | 1.3 | Lead track with a camera swing as Nibs takes a corner | Nibs rounds the corner | Corner of the lane | VO "I'm at least…" | Bleat |
| 21 | 0:58.5 | 0.5 | Lead track, medium close-up (montage begins) | Nibs struts at the lens | Spot 1: in front of a stall | VO "**SIX**" | Each montage shot starts on a kick drum hit |
| 22 | 0:59.0 | 0.25 | Same | Nibs struts | Spot 2: lanterns | "**TIMES**" | Hit |
| 23 | 0:59.25 | 0.5 | Same | Nibs struts | Spot 3: the well | "**MORE**" | Hit |
| 24 | 0:59.75 | 0.35 | Same | Nibs struts | Spot 4: flower pots | "**GOAT**" | Hit |
| 25 | 1:00.1 | 0.5 | Same | Nibs does a small hop at the lens | Spot 5: the bridge | "**THAN**" | Hit; hop sound |
| 26 | 1:00.6 | 0.25 | Same | Nibs struts | Spot 6: the cart | "**HIM**" | Hit |
| 27 | 1:00.85 | 1.6 | Lead track, wide | Nibs walks on, very pleased | Lane | VO "So today…" | Bed |
| 28 | 1:02.45 | 4.6, then 0.6 black | Lead track (jump cut); camera swings as Nibs turns to the lens, then dip to black on the scream | Nibs walks, **stops, turns to the lens, lowers its head as if to ram, then lifts it and screams** | Open end of the lane, valley behind | VO "…I **challenge** Duke to a jump-off!" | The screaming goat scream, full; cut to silence on black |
| 29 | 1:07.65 | 3.0 | Graphic: a card of Duke on black | Duke's own model rendered in a front three-quarter pose, centred, fading up; a slow 1.0× to 1.05× push | Black background | "DUKE · 3× champion" | A note-block sting |
| 30 | 1:10.65 | 1.1 | Game render on black | Duke, small and centred on black, yawns and lies down to sleep | Black void, one light | DUKE "**zzz**" | A tiny fox snore; music button |
| end | 1:11.75 | 2.0 | End card | Title card | Black | "NIBS vs DUKE · The Jump-Off" | Bed's final hit, then out |

Total 73.75 s with the end card; the measured section (shots 1 to 30 and the two dips) is 71.75 s.

### Checks the engineers can run on the export

- Scene detection on shots 1 to 30 finds 30 shots (±2), median length 2.3 to 3.0 s, and six shots under 0.6 s
  between 0:58 and 1:01.
- Shots 1 to 9 and 19 to 28 are lead tracks: Nibs' bounding box stays within the middle third horizontally and changes
  height by less than 15% across each shot (except shot 5's turn and the montage, which are closer).
- Two stretches of black of at least 0.5 s, at about 0:27 and 1:07.
- Captions: no more than 2.5 words a second, each at least 1 s on screen (montage words excepted, which are one word a
  shot).
- Audio: integrated loudness −14 LUFS ±1; silence below −50 LUFS at both dips; the egg plop and the scream are within
  2 frames of the frame they happen in.
