# Voice

Dialogue in videocraft is a `say` cue: who speaks, what they say, when. At compile time each line is synthesized on
this machine by an open-weights text-to-speech model with the character's voice, aligned word by word, and turned
into a caption whose words pop on their onsets, a voice line in the mix, and a shot that is exactly as long as its
line, or that ends on a chosen word so the cut lands on it. Nothing leaves the machine; no account or key is needed.
The script keys are in [SCRIPT.md](SCRIPT.md#dialogue).

```sh
bin/videocraft voice setup                       # once: cache/voice/venv (1.3 GB) and the weights (3.8 GB, HF cache)
bin/videocraft voice doctor                      # what is installed; exactly what is missing
bin/videocraft voice say --character nibs "Hey. It's me. *Nibs." -o /tmp/hey.wav    # hey.wav + hey.words.json
bin/videocraft voice script examples/talk.toml   # every line of a script (cached), its timings, the shot lengths
bin/videocraft run examples/talk.toml            # the take: lines are synthesized (or read from the cache) first
bin/videocraft voice check talk                  # caption words, cut-on cuts and the voice in the master, measured
```

Without the voice installed (or with `VIDEOCRAFT_VOICE=estimate`) every script still compiles and runs: the same
resolver works on reading-speed estimates (about 2.4 words a second, pauses at punctuation), captions pop on those,
the cut has no voice, and a warning says so. `VIDEOCRAFT_VOICE=draft` uses each character's `draft` voice (Kokoro, 5x
faster) for quick takes; `VIDEOCRAFT_VOICE=voice` makes a missing voice an error.

## Engines and voices

| | Engine | Code / weights | Use |
|:--|:--|:--|:--|
| Default | [Qwen3-TTS 12Hz 1.7B CustomVoice](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice), 8-bit MLX ([mlx-community](https://huggingface.co/mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit)) through [mlx-audio](https://github.com/Blaizzy/mlx-audio) 0.6.5 | Apache-2.0 / Apache-2.0 | Acted characters: a preset voice (`ryan`, `aiden` are the English-native ones) steered by an instruction. Apple silicon only. |
| Fallback | [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M), PyTorch `kokoro` 0.9.4 on the CPU | Apache-2.0 / Apache-2.0 | Drafts, narration, a third male voice. No style control: a style is a pace. |
| Timings | [wav2vec2-base-960h](https://huggingface.co/facebook/wav2vec2-base-960h) CTC forced alignment of the known text | Apache-2.0 (transformers) / Apache-2.0 | Every engine. |

The cast of the benchmark is [cast/nibs-vs-duke.toml](../cast/nibs-vs-duke.toml): Nibs is `ryan` + "cocky, brash and
bright", Duke `aiden` + "smug, low and brisk" (it was "slow, smug and low" until pacing: see below), both seed 7 (measured in the voice lab: median f0 225 Hz against
131 Hz, 9.4 semitones apart; 0 ASR errors in 52 words). The research behind these choices (19 engines surveyed by
licence, 3 run here, the timing measurements) was done in a separate voice lab on 2026-11-11; its findings are
summarised here and in the code comments.

**Voices must not imitate real people.** Every voice here is a model preset or a description; none is cloned from
anyone. Do not add a character whose voice copies a real person (cloning from a recording of someone, or an
instruction naming them). The preset names (`ryan`, `aiden`, `am_fenrir`, ...) are the models' own labels, not
people.

VoiceDesign (a voice from a description) is not used: it does not hold a character from line to line (the lab's
"smug fox" came out at 119, 67 and 74 Hz on three lines). Chatterbox is retired and watermarks its output; F5-TTS,
XTTS-v2, Fish S2, Voxtral and Breeze are non-commercial; Piper's good voices are non-commercial. None are used.

## The cast file

```toml
[[character]]
id = "nibs"                    # the say cue's actor (or its `character`)
name = "Nibs"                  # the caption's speaker tag (default: the id, capitalised)
color = "#a8c8ff"              # the tag's colour
engine = "qwen3"               # qwen3 or kokoro
voice = "ryan"                 # the engine's preset
instruct = "Cocky, brash and bright. A fast-talking show-off who loves the sound of his own voice, grinning the whole time."
seed = 7                       # fixed: the same line is the same take, bit for bit
speed = 1.0                    # kokoro: its own rate; qwen3: a time stretch (keep 0.9-1.1)
pitch = 0                      # semitones, post-process (moves the formants too: keep within +-2)
lufs = -20                     # each line's loudness before the mix
bark = "minecraft:entity.goat.ambient"   # optional: the character's game sound on each line's first word
bark_volume = 0.6
draft = { engine = "kokoro", voice = "am_fenrir", speed = 1.1 }   # VIDEOCRAFT_VOICE=draft

[styles]                       # optional: your own delivery words
gloat = "Gloating, drawn out, savouring the win."
```

A script names its cast with `[cast] file = "cast/<name>.toml"` (relative to the script, then to the repository)
and/or inline `[[cast.character]]` tables. A character the script's cast does not name is looked up in every file in
`cast/`, then given a generic voice with a warning, so a generated script always compiles.

**Delivery** (`style` on a say cue): `shout`, `whisper`, `deadpan`, `excited`, `proud`, `smug`, `sad`, `angry`,
`scared`, `sleepy`, `question`, `sing`, or any sentence. For Qwen3 it is a sentence added to the character's
instruction ("Flat and deadpan, completely unimpressed, no emotion at all."); for Kokoro, a pace (`sleepy` 0.82x,
`excited` 1.1x). The list is `STYLES` in `cli/videocraft/voice/cast.py`.

## How a line is made

The CLI core stays standard-library only: `cli/videocraft/voice/` never imports a model. It runs
`worker/worker.py` in the voice venv with a batch of jobs on stdin, so the models load once per compile.

1. **Synthesize** with the character's engine, voice, instruction and seed (Qwen3: `mx.random.seed`; Kokoro:
   `torch.manual_seed`, because its vocoder draws noise).
2. **Speed and pitch** with ffmpeg (`asetrate,aresample,atempo`; there is no rubberband here).
3. **Level** with one static gain to −20 LUFS (EBU R128), sample peak at most −1 dBFS: Qwen3 lines of one voice
   measured 5-7 LU apart. The mix levels voice again to its speech reference.
4. **Resample** to 48 kHz mono PCM16.
5. **Align** the known words with wav2vec2 CTC (a numpy Viterbi; letters only, so spell numbers out).
6. **Snap** phrase starts and ends to the waveform at pauses (below).
7. **Check**: speech that no word covers (the autoregressive TTS said something that is not in the text, or the
   aligner lost a word), a word the aligner cannot place, or an unscripted sound before a word. Any of them re-rolls
   the line with seed + 1, up to twice; the best take is kept, and flagged `suspect` in the table if it still fails.
8. **Cache** under `cache/voice/lines/<key>.{wav,words.json,json}`, the key a hash of engine, model, voice,
   instruction, seed, speed, pitch, loudness, words and the worker's version. A re-compile reads the cache (0.1 s for
   the talk example against 30-60 s to synthesize it).
9. **Pace** (in the CLI core, `cli/videocraft/voice/pace.py`, standard library): the line is tightened and cached
   beside the raw one as `<key>.p<hash>.{wav,json}`, so changing the pacing never re-synthesizes. Below.

## Pacing: voiced and fast by default

The owner's verdict on the first two films: voiced lines are "significantly better" than captions, and the lines
were "super slow" (measured 1.2-3.5 words a second, with dead air between them). So every line is brisk unless a
script asks otherwise, and this is the tool's default, not a per-film fix:

- **Delivery.** Every qwen3 line's instruction gets the project's default delivery sentence (`cast.DELIVERY`:
  "Brisk and snappy: a quick conversational pace, words tumbling out, no long pauses."), except with a slow style
  (`deadpan`, `sleepy`, `sad`) or `pace = 0`. Cast instructions never ask for slow or drawling delivery.
- **Trim.** Silence before the first word is cut to 60 ms and after the last to 120 ms. Only quiet audio is cut
  (10 ms blocks 30 dB under the line's loud level, the 95th percentile): an aligned word end can be 80-160 ms early,
  so the tail keeps the last word's decay (up to 0.4 s after its aligned end).
- **Pauses.** A pause inside a line (the quiet run that ends at the next word's onset) is capped at 0.25 s after a
  comma or inside a phrase, 0.4 s after `.`, `!`, `?` or an ellipsis; the cut is taken from the middle of the pause
  with 5 ms fades. Not for `style = "deadpan"` or a line marked `beat = true`.
- **Stretch.** A line of 3 words or more still slower than `pace x 0.85` words a second is time-stretched towards
  its `pace` (ffmpeg `atempo`, pitch kept), by at most 1.2x. Not for the slow styles.
- **Pace.** `pace = 3.2` words a second is every character's default (cast `pace`; a say cue's `pace` overrides it;
  `0` or `false` leaves the line as synthesized). Words a second is `words / (last end - first start)`, the same
  measure lint and measure use.

Word timings stay exact: a cut moves every later time back by its length (a time inside a cut lands on its start),
a stretch divides every time by the factor. Re-aligning the paced talk lines with wav2vec2 found the trimmed lines'
onsets within 0-3 ms of the moved times and the 1.2x line within 16 ms (atempo smears an onset by about 15 ms; under
a frame). voice.json records per line `wps` (after) and `pace` = `{wps_raw, wps, stretch, trimmed, cuts, target}`.

On `examples/talk.toml` (Qwen3, words a second before → after): nibs 2.24 → 3.24 (the brisk delivery), challenge
(`excited`) 2.63 → 2.76, duke 1.62 → 2.96 (the new instruction 2.38, then stretched 1.2x), reply (`deadpan`, exempt)
2.34 → 2.34; the film went from 15.7 s to 12.0 s, a voice for 84 % of it, the longest silence between lines 0.68 s.
With no voice installed the estimate is paced the same way (the estimate's 2.4-3.0 words a second become 2.9-3.0).

### Word timings: what to trust

Onsets after a pause are cut-grade; ends are not. Measured on the voice lab's 39 takes (three lines, Qwen3 and
Kokoro voices), each phrase onset against the energy onset of the waveform (10 ms RMS above −30 dB re the loud
frames, pauses of 100 ms or more):

| Engine | Method | n | Median abs | p90 abs | Max abs |
|:--|:--|--:|--:|--:|--:|
| Qwen3 | CTC alone | 22 | 74 ms | 424 ms | 755 ms |
| Qwen3 | CTC + plain −40 dB snap (the lab's) | 22 | 7 ms | 61 ms | 108 ms |
| Qwen3 | **CTC + snap with hysteresis (now)** | 22 | **6 ms** | **15 ms** | **26 ms** |
| Kokoro | CTC alone | 28 | 40 ms | 81 ms | 192 ms |
| Kokoro | CTC + plain −40 dB snap | 28 | 10 ms | 50 ms | 192 ms |
| Kokoro | **CTC + snap with hysteresis (now)** | 28 | **9 ms** | **35 ms** | 192 ms |

The Kokoro maximum is the one onset with no pause before it ("Hey. It's" run together at speed 1.1), where the
scorer itself has no ground truth. What changed from the lab: Qwen3 fills some pauses with a quiet *voiced* murmur
(−45 to −34 dB; it reads as a breath, but it is periodic, so spectral flatness and voicing do not separate it from
speech, which was the first idea tried). A plain −40 dB threshold counted it as speech and snapped the next phrase
100-240 ms early. Now a run of sound counts as speech only if it reaches −25 dB somewhere, traced outwards while it
stays above −40 dB without a break. A weak /θ/ or /h/ leading into its vowel is contiguous and stays; the murmur is
cut off from the next word by a dip and goes.

A second case found in the talk example: Qwen3's deadpan reading scoffed for a second before "That" (ASR skips
non-words, so the round trip was clean). The burst snap pulled the word onto the scoff. Now, when the aligner puts a
burst's first word at least 0.25 s into it and a dip (5 ms below −40 dB) comes before it, the word starts at that dip,
and the take is re-rolled because the sound is not in the script. The lab corpus scores did not change.

Inside a phrase, word starts keep the aligner's times: expect about ±25 ms median, 50 ms p90 (two methods
disagreeing in the lab). Caption pops are fine at that; hard cuts should be on phrase starts or stressed words.
Word ends are 80-160 ms off at p90: never cut on an end without looking.

## The say resolver

`script.compile_script` calls `videocraft.voice.resolve.resolve(raw, source)` first, only when the script has a
`say` cue. Each line becomes:

- a `caption` cue at the line's `at`, with `words = [{ w, at }]` from the alignment (the `*` key word kept), the
  speaker tag and colour from the cast, and any of `position`, `size`, `hold`, `shade`, `key_color`, `color` or a
  `caption = { … }` table passed through;
- an `edit.voice` entry `{ file, shot, at, gain }` (the mix places it at the shot time `at`, levels it, and lets it
  play over the cut);
- with a `bark`, a `sound` cue on the first word's onset, at the actor if it is an `[[actor]]`, else not positional;
- the shot's duration by `fit`: `extend` (default; the shot lasts at least to the last word + `tail` 0.25 s, so a
  dialogue shot may leave `duration` out), `cut-on` (the shot ends on the onset frame of `cut_on`; the words from it
  on carry into the next shot in script order as a caption at 0, while the voice plays on), `none`.

**Packing.** The first line of a shot starts at its `at`; every later line (fit `extend` or `cut-on`) starts its
first word `gap` after the previous line's last word: 0.12 s by default, the previous line's `pause_after` or the
line's own `gap` to change it. A later line's written `at` is replaced by the packed time (stderr notes it) unless
the line is `beat = true` (the pause before it is the joke) or `fit = "none"`. The shot's first line after a cut-on
carry follows the carried words the same way. Every line goes into `edit.dialogue`, which the run store writes to
`voice.json`: `{id, character, shot, at, start_frame, text, style, fit, file, seconds, engine, timing, cached, key,
voice, wps, pace, beat, words: [{word, start, end}], cut_on?: {word, index, onset, frame}, carried_to?}` (times in
seconds of the line; `at` and `onset` in seconds of the shot). A short table goes to stderr.

lint (`unvoiced_text`, `slow_line`, `dead_air`) and measure (`dialogue` in metrics.json, "Dialogue pace" in
report.md: words a second per line, the share of the runtime with a voice, the longest silences) hold scripts and
cuts to the same rules ([SCRIPT.md](SCRIPT.md#checking-a-script-videocraft-lint)).

## `voice check`

`bin/videocraft voice check <iteration>` writes `measure/voice.json` and passes when, within 2 frames:

- **captions**: every caption word's frame in `take/shots/<shot>/text.json` equals `round((at + start) × fps)`;
- **cuts**: for each cut-on line, the next clip in `cut/timeline.json` starts on the word's onset in the cut;
- **voice**: each line is found in the master's sound track where `cut/audio.json` placed it (its 5 ms loudness
  envelope cross-correlated with the master's: lag within 33 ms, correlation at least 0.5), with the master's
  loudness while it speaks.

On `examples/talk.toml` (iteration 2): captions 0 frames off for all 29 words, the cut on "Duke" 0.14 frames after
its onset, every line at 0 ms lag with r 0.98-1.00, the master at −14.1 LUFS and −13.1 to −15.0 LUFS while lines play.

## Setup in detail

`voice setup` runs `uv venv -p 3.12 cache/voice/venv` (torch has no wheels for newer Pythons yet; without uv it
uses a `python3.12` on PATH), `uv pip install -r cli/videocraft/voice/worker/requirements.txt` (direct pins; the full
working freeze is `requirements.lock.txt`), then `worker.py --prefetch`, which downloads Kokoro-82M (0.33 GB),
wav2vec2-base-960h (0.38 GB) and Qwen3-TTS CustomVoice 8-bit (3.1 GB) into your Hugging Face cache (`HF_HOME` or
`~/.cache/huggingface`). Later runs set `HF_HUB_OFFLINE=1` when the weights are there (otherwise every load asks the
Hub). System tools: ffmpeg and espeak-ng (`brew install espeak-ng`; Kokoro's fallback for unknown words). Peak
memory while synthesizing is about 6.4 GB. Weights and the venv are never committed (`/cache/` is git-ignored).
