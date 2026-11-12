{{craft}}

# Stage 5 of 5: the shot script

From the script, write `shots.toml`: a **videocraft shot script** the recorder performs. It must compile with
`videocraft compile`. Use only actions, rigs and keys from the reference below; anything not in it fails the take.

## The story id (the script's `name`)
`{{id}}`

## Output
{{output}}

## The bible
```toml
{{bible}}
```

## The cast (paste this `[cast]` block into shots.toml as it is: it gives every character its voice)
```toml
{{cast}}
```

## The script
{{script}}

## Sets that exist (`[[world.set]] name = "<set>"`, marks as anchors `{ anchor = "<set>:<mark>" }`)
{{sets}}

## The shot script reference (docs/SCRIPT.md, verbatim; this is the whole vocabulary)
{{reference}}

## How to write it
- `name = "{{id}}"`; one `[[actor]]` per bible character that appears (`id` from the bible; `kind = "mob"` with
  `entity`, or `kind = "mannequin"`), placed on set marks.
- One `[[shot]]` per shot, in order, each with a `name` (lowercase-dash, unique), a `duration` (never over 7.5 s
  for a short; a shot of dialogue may leave it out and lasts as long as its lines), a `camera` (a rig from the
  reference with its parameters), and `[[shot.cue]]` blocks: actor actions at the seconds they start, a `say` cue
  for each spoken line (`actor`, `text` with its `*key` word), `sound` for effects.

## Voiced and fast (lint warns on each of these, and the warnings come back to you)
- **Every word of dialogue and narration is a `say` cue**; its caption (the subtitle) comes with it. Never a
  `caption` for spoken words. `caption`, `title` and `card` only for writing in the world or on screen (a sign, a
  post, a card); when that writing matters to the joke, a voice also reads it aloud in a `say` (the narrator or a
  character; `caption = false` on the say when the sign already shows the words). lint: `unvoiced_text`.
- **Brisk lines**: 3.0-3.8 words a second. Short, punchy lines; no `speed` under 1; `style = "deadpan"` (slow on
  purpose) at most once or twice a film. lint: `slow_line` (under 2.6 words a second).
- **Near-continuous talk** for a comedy short: give only the first `say` of a shot an `at`; the next lines follow
  0.12 s after the previous one by themselves (`gap` to change it). A cut on a word (`cut_on`) carries the line on
  over the cut. No more than 0.8 s without a voice inside a run of dialogue shots, except a dip to black before a
  reveal or a pause that is the joke: mark the line after that pause `beat = true`. lint: `dead_air`.
- `[edit]` with `[[edit.clip]]` in order; dips to black and the music as the reference allows.
- If a set does not exist, stage what you need with `[[world.stage]]` `command` cues (fill, setblock, summon), small.
- Comments (`# ...`) say which script line each shot films.

Return only the file, between a line `<<<FILE` and a line `FILE>>>`.
