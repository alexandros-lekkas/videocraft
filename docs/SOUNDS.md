# Sounds by meaning: the Minecraft map and the original library

A script asks for a sound by what it means (`tag = "pop"`, `palette = "drumroll"`, `[edit.music] mood = "playful"`)
and gets the best real Minecraft sound first. The same script also makes an export with no game audio in it, because
every Minecraft sound it leans on has an original stand-in made by code. This page explains how that works; the keys
are in [SCRIPT.md](SCRIPT.md#audio).

## Why no game audio is committed

Minecraft's sounds and music are Mojang's. They are never committed, distributed with the mod, or written next to an
export (AGENTS.md hard rule 5; [CREDITS.md](../CREDITS.md)). What the repository holds is a **map**: the names of the
game's sounds and tracks, what they mean, how long they are and what they measure like. The audio itself stays in your
own game install (the assets Loom downloads into `~/.gradle/caches/fabric-loom/assets` for the dev client), and the
mix reads it from there at export time, decoding into the git-ignored `cache/audio/`. A machine without those assets
can still compile and lint every script, because the map is committed.

## The map

| File | What | Made by |
|:--|:--|:--|
| `cli/videocraft/audio/catalog/minecraft.toml` | Every sound event (1991 in 26.3): usual category, variant count, measured length, tags, the original stand-in; `[best]` ranks per tag; the comedy palette | generated |
| `cli/videocraft/audio/catalog/music.toml` | Every music track (92 in 26.3: game, creative, menu, end, nether, discs): events, length, moods, measured tempo and pulse, levels, entry, energetic windows, loop points | generated |
| `cli/videocraft/audio/catalog/curated.toml` | The hand curation: `[best]` per tag, the comedy palette, music moods and notes | by hand |
| `cli/videocraft/audio/catalog/rules.py` | Tag rules on the event id: family, mob, mood, surface, curated meanings; which library sound stands in | by hand |
| `cli/videocraft/audio/library/library.toml` | The original library: name, tags, a line about each | by hand |

`videocraft audio catalog --refresh` rebuilds the two generated files from the local `sounds.json` and asset index
(edit `curated.toml` or `rules.py`, then refresh; a new game version is a refresh). Lengths come from each Ogg file's
own header (the last granule position over the sample rate: a few kilobytes read per sound, and they match ffprobe).
Music is decoded by ffmpeg into memory and measured with the standard library (`catalog/musicfeat.py`):

- **tempo**: the autocorrelation of an onset envelope (rises in log energy, the band above 1.5 kHz counted double)
  over 60-180 bpm, weighted toward 120 so a half or double time does not win. **pulse** is the normalized peak:
  steady from 0.3 (`records/wait` 0.66, `records/mall` 0.61), loose 0.15-0.3, free below (most of the ambient game
  music: there `bpm` is a hint, and the mix falls back to 120 for beat-length cues).
- **entry**: the first downbeat after the intro (the first 1 s window within 3 dB of the median level, snapped to the
  strongest onset near it): where a mood-picked track starts.
- **energetic**: the three best non-overlapping 8 s windows by level and onset density.
- **loops**: two strong onsets 12-60 s apart (a whole number of beats when the pulse is steady) whose surroundings
  match in level and brightness; the mix repeats b back to a when a track is shorter than the cut.

Moods (calm, upbeat, tense, sad, triumphant, mysterious, playful) are hand-assigned in `curated.toml`; a track it does
not list gets a mood guessed from its measurements (`mood_by = "measured"`). Discs that are not music beds (11, 13,
5) say `bed = false`, and a sung track says `vocals = true` (Lava Chicken); auto-pick leaves both out.

**Nobody listened.** The catalog, the palette and the moods were built by an agent that cannot hear: event choices come
from names, the curated meanings and measured lengths; moods from knowledge of the tracks and the measurements.
`videocraft audio play-sheet <tag>` writes the candidates one after another into a wav so a person can re-rank them
by ear (in `curated.toml`).

## Tags

A tag query is one or more words; an event must carry all of them (`tag = "footstep wood"`, `tag = "goat hurt"`). The
words come from:

- the family and mob: `entity`, `block`, `item`, `ui`, `ambient`; `goat`, `fox`, `villager`, `chicken`… (variants answer
  to the base name: `wolf_angry` is a `wolf`; `baby` is a tag), `mob`, `monster`;
- the mood of a voice: `ambient`, `hurt`, `death`, `angry`, `happy`, `sad`, `scream`, `yes`, `no`, `hmm`, plus `voice`;
- the surface of a footstep: `footstep` and `footstep-wood`, `-stone`, `-grass`, `-sand`, `-gravel`, `-snow`, `-wool`,
  `-metal`, `-glass`, `-leaves`, `-mud`, `-slime`;
- curated meanings: `pop`, `plop`, `ding`, `boing`, `whoosh`, `swish`, `click`, `impact`, `bonk`, `thud`, `explosion`,
  `splash`, `splat`, `fail`, `error`, `success`, `levelup`, `xp`, `sparkle`, `magic`, `teleport`, `crowd`, `cheer`,
  `applause`, `sting`, `dramatic`, `spooky`, `scrape`, `horn`, `honk`, `alarm`, `bell`, `eating`, `drink`, `door`, `chest`,
  `fuse`, `thunder`, `glass`, `crash`, `note`, `drum`… (`videocraft audio find <words>` shows what a word finds);
- the palette names.

The first event of a query is the curated `[best]` entry for it, then the events whose tags say most about the query,
then the shorter id. `vary = true` on a cue picks one of the best three by the script's seed.

## The comedy palette

`palette = "<name>"` plays a named effect built from real Minecraft events, with pitch and volume suggestions (a cue's
own `pitch` wins). An entry is one **pick** (alternatives, the first is the default), a **sequence** (every step at its
offset) or a **roll** (hits at a rate, swelling, seeded jitter, then end hits). Selected entries:

| Palette | Minecraft | Original stand-in |
|:--|:--|:--|
| `boing` | `entity.slime.jump` pitched 1.05-1.25 | `boing` |
| `pop` | `entity.item.pickup` pitched 1.3-1.8 | `pop` |
| `plop` | `entity.chicken.egg` | `plop` |
| `ding` | `entity.experience_orb.pickup`, `block.note_block.bell` | `ding` |
| `levelup`, `success`, `ta-da` | `entity.player.levelup`; `ui.toast.challenge_complete`; a rising pling arpeggio | `level-up`, `success-chime`, `fanfare` |
| `fail`, `wah-wah`, `error` | `entity.villager.no`; four falling didgeridoo notes; `block.crafter.fail` | `fail-trombone`, `error-buzz` |
| `drumroll` | a 1.7 s roll of note-block snares, ending on a kick, a snare and a hat | `snare-roll` |
| `rimshot` | ba-dum-tss on note blocks | `rimshot` |
| `record-scratch` | `block.grindstone.use` pitched up (Minecraft has no scratch; this is the closest) | `record-scratch` |
| `dramatic-sting`, `dun-dun-dun`, `spooky` | `entity.elder_guardian.curse`; low note-block bass and didgeridoo; `ambient.cave` | `sting-dramatic`, `sting-spooky` |
| `crowd`, `applause`, `cheer` | villagers celebrating, rolled with pitch jitter (over a patter of note-block hats for applause) | `crowd-murmur`, `applause`, `cheer` |
| `whoosh`, `swish`, `thud`, `bonk`, `impact`, `splat`, `explosion`, `splash` | the sweep attack, falls, the anvil, a slime squish… | the same names |
| `honk`, `alarm`, `scream`, `hmm`, `yes`, `no`, `gulp`, `munch`, `squeak`, `door`, `fuse`, `cash-register`, `sparkle`, `magic`, `teleport`, `click` | goat horns pitched up, the raid horn, the screaming goat, villager voices… | matching library sounds |
| `slide-whistle-up`, `slide-whistle-down`, `cartoon-fall`, `crickets`, `typewriter` | none: original only | the same names |

`videocraft audio find <word>` lists the palette with the rest; the whole palette is `[palette.*]` in
`catalog/minecraft.toml`.

## The original library

`cli/videocraft/audio/library/` makes 79 effects from oscillators, noise, a state-variable filter (its cutoff can move
every sample), envelopes and a small feedback-delay room, in plain Python: boings and springs, pops, plops, bubbles,
dings, a cash register, chimes, a level-up arpeggio, a fanfare, sparkles, whooshes and swishes, thuds, bonks, splats,
clicks, knocks, an explosion, glass, footsteps on wood, stone, grass, sand, snow and metal, squeaks, buzzers, an alarm,
clown honks, drums, a cymbal, a drumroll, a rimshot, stings, a sad trombone, a crowd murmur, applause (1300 seeded
claps), a cheer, slide whistles, a cartoon fall, a record scratch, a typewriter, a door creak, crickets, and animal and
people voices (bleat, cluck, yip, moo, oink, meow, woof, hmm, grunt, hiss, yelp, scream) from a sawtooth through
formant filters.

Each sound is deterministic per seed, levelled to about −16 dBFS RMS over its active part (peaks under −0.9 dBFS),
and rendered on demand into the git-ignored `cache/audio/library/` (keyed by a hash of the recipe code, so a changed
recipe renders again); no wav is committed. `videocraft audio library --render` renders and measures them all (about
six seconds). A script plays one with `library = "<name>"` (the take logs `videocraft:lib/<name>`, the mix renders it)
or in the edit with `[[edit.sfx]] library = "<name>"`.

The synth music bed (`audio/synth.py`) has nine styles: `upbeat`, `sneaky`, `tense`, `triumphant`, `comedy-chase`,
`suspense`, `keynote`, `lullaby`, `heroic`. Each mood maps to its beds: calm → lullaby (keynote near its tempo), upbeat →
upbeat, tense → suspense (tense near 140 bpm), sad → lullaby in A minor, triumphant → heroic, mysterious → sneaky,
playful → comedy-chase.

## Minecraft first, and how an original export swaps

`source = "auto"` is the default for tagged sounds and for music with a mood:

1. **In the take**, a tagged cue always plays the Minecraft event (the game is muted; the sound is logged). Only a tag
   the catalog has no event for, a palette entry that is original only, or `source = "original"` plays a library sound.
2. **The game mix** (`cut/audio.wav`) reads the logged sounds from your assets. Music with a mood is a game track picked
   from the music map: main mood 3 points, second mood 2, a steady pulse for upbeat or playful +1, nearness to a
   requested `bpm` up to +2, long enough from its entry +1 (or loopable +0.5); the best within a point are shuffled by
   the script's seed, so videos of one mood do not all get one track. It starts at the track's measured entry.
3. **The original mix** (`[edit] audio = "original"`, an export with `audio = "original"`, or `cut --original-audio`:
   `cut/audio-original.wav`) reads no game asset at all (the test suite proves it by making every asset reader fail).
   Each compiled cue carries the library sound that replaces it (`original` in plan.json), so a tagged pop becomes the
   library pop and a palette's drumroll of 41 note-block hits becomes one library drumroll (the later steps carry
   `part` and are dropped). Any other logged game sound is swapped for its catalog stand-in (a goat's voice for the
   bleat, a wooden footstep for the wooden step, a villager for the hmm); note-block notes become tones at the logged
   pitch; what has no stand-in is left out and listed in `audio-original.json` with the reason. Game music becomes the
   synth bed in the style of the mood (of the script, or of the named track).

So one script makes both exports: `cut/<export>.mp4` with your game's sounds and `cut/<export>-original-audio.mp4`
with none, both mastered to −14 LUFS. On `examples/sound.toml` (three shots, 13.3 s, run 2): the game mix placed 71
logged sounds (65 of 65 onsets within ±1 frame of their frames) and `records/blocks` (playful, steady pulse, started at
its 7.1 s entry) and measured −14.6 LUFS, −1.8 dBTP; the original mix swapped 7 tagged cues and 2 chicken voices,
dropped 43 later palette steps, played the comedy-chase bed and measured −14.1 LUFS, −1.9 dBTP (AAC exports: −14.9 and
−14.2 LUFS). Those are measurements; nobody listened.

## The balance: dialogue is king

The owner, on the first finished films: "the audio balance is bad, music is too loud". The master's integrated
loudness says nothing about what is heard over what, so the mix now measures its own buses (EBU R128 momentary
readings of the voice, music and effects buses at the master's gain; `cli/videocraft/audio/balance.py`) and sets
the balance by those numbers, by default, for every film:

| | Default | `[edit.mix]` key |
|:--|:--|:--|
| Voice bus | −16 LUFS before the master (the master's −14 integrated then puts it near −15 short-term: it is most of the program) | `voice_level`, `voice` (dB trim) |
| Music between lines | −24 LUFS at the master (`[edit.music] gain` trims it), measured on the undocked bed | `music_level` |
| A game track | a further −2 dB (they are dense and bright where speech lives) | `game_trim` |
| Music under a line | its loudest momentary reading at least 18 LU under the line's voice (+1 LU spare) | `music_under_voice` |
| The duck | as deep as each line needs for that, at least `[edit.music] duck` (−6 dB), at most −40; fully down 50 ms before the first word (60 ms linear attack), held 0.25 s through gaps and packed lines, 0.4 s release | `[edit.music] duck` |
| Effects | held 3 LU under the voice level everywhere and 6 LU under a line's voice while it speaks (a fast limiter on the effects bus) | `sfx_ceiling`, `sfx_under_line` |
| Master | −14 LUFS integrated, true peak ≤ −2 dBTP | |

A music `hit` (crash and kick) is levelled against the bed's own reference: it used to be scaled by the track's
normalization, which for a quiet C418 track put hits at +1 LUFS momentary, and the limiter then pulled the whole mix
down around them. `cut/audio.json` gets a `balance` block (per line: voice, music, effects and `ratio` = LU the music
sits under the voice; the music between lines, mean and 95th percentile; the effects' loudest; the targets); measure
copies it into `metrics.json` and a "Mix balance" table in `report.md`, the review's sound sheet prints it, and measure
warns on a line whose music is less than 12 LU under the voice, or music between lines louder than `music_level` + 3.
lint warns (`mix_balance`) on settings that would allow either. `audio mix <run> --stems` also writes
`cut/audio-stems/{voice,music,sfx}.wav` at the master's gain.

Measured on the two finished films, the same takes re-mixed (stem loudness at the master's gain; nobody listened):

| Mix | Voice short-term median | Music under lines | Music between lines (mean / p95) | Voice over music (median / least) | Lines under 12 LU | Effects max | Integrated | True peak |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| Nibs vs Duke, before | −15.3 | −25.3 | −8.8 / −0.4 (the hits) | 23.5 / 0.4 LU | 6 of 28 | −10.4 | −14.2 | −2.7 |
| Nibs vs Duke, now | −14.4 | −41.8 | −37.1 / −31.0 | 36.5 / 19.8 LU | 0 | −16.2 | −14.2 | −3.0 |
| A second film (a local story), before | −14.9 | −25.4 | −20.6 / −16.5 | 13.0 / 9.2 LU | 14 of 29 | −12.8 | −14.0 | −3.0 |
| The second film, now | −15.0 | −34.7 | −29.3 / −24.6 | 21.2 / 19.0 LU | 0 | −17.8 | −14.2 | −3.0 |

Nibs vs Duke's bed (C418's `firebugs`) is piano that decays from about −32 to silence every eight seconds, so the
music under most of its lines is far below the 18 LU line; its script also asks for `gain = -3`, `duck = -9`.

## Tools

```sh
bin/videocraft audio find goat hurt        # palette, Minecraft events, library and music matches, with sources
bin/videocraft audio find playful          # music by mood, and the bed an original export would play
bin/videocraft audio play-sheet boing      # cache/audio/sheets/boing.wav: every candidate, levelled alike, listed
bin/videocraft audio catalog --refresh     # rebuild minecraft.toml and music.toml from your game assets (~3 min)
bin/videocraft audio library --render      # the original library, rendered and measured
```
