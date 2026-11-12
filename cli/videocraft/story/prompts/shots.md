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
  for a short), a `camera` (a rig from the reference with its parameters), and `[[shot.cue]]` blocks: actor actions
  at the seconds they start, a `say` cue for each spoken line (`actor`, `text` with its `*key` word) at the moment
  the line starts, `caption`/`title`/`card` for on-screen text that is not spoken, `sound` for effects.
- `[edit]` with `[[edit.clip]]` in order; dips to black and the music as the reference allows.
- If a set does not exist, stage what you need with `[[world.stage]]` `command` cues (fill, setblock, summon), small.
- Comments (`# ...`) say which script line each shot films.

Return only the file, between a line `<<<FILE` and a line `FILE>>>`.
