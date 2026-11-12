{{craft}}

# Stage 2 of 5: the bible

From the premise, write `bible.toml`: the characters, sets, gags and rules, stable across a series.

## The premise
{{premise}}

## Sets that already exist (use these names when one fits; describe a new one otherwise)
{{sets}}

Write TOML in exactly this shape (add as many entries as the story needs, no more):

```toml
title = "<title>"
logline = "<one sentence>"

[[character]]
id = "nibs"                       # lowercase-dash; the actor id in the shot script
name = "Nibs"
kind = "mob"                      # "mob" (a vanilla entity) or "mannequin" (player-shaped) or "narrator" (voice only)
entity = "minecraft:goat"         # mob only
look = { left_horn = false }      # mob: entity data (variant, baby, horns, ...); mannequin: skin spec below
# skin = { tone = "#c58c6a", hair = "short", hair_color = "#9a9a9a", top = "tee", top_color = "#111111",
#          jacket = "leather", jacket_color = "#1a1a1a", trousers_color = "#202020", shoes_color = "#0d0d0d" }
personality = "<two or three traits that drive the jokes>"
voice = { engine = "qwen3", preset = "ryan", instruct = "<how it talks: age, pitch, energy; always brisk>", pace = 3.4 }
sounds = ["minecraft:entity.goat.ambient"]   # signature game sounds
gestures = ["<signature moves the recorder can do>"]

[[set]]
name = "market-lane"              # an existing set name, or a new lowercase-dash name
exists = true                     # false: describe it so the sets tool can build it
description = "<what it looks like, time of day, the landmarks the story uses>"

[[gag]]
name = "<short name>"
description = "<the running gag and how it pays off>"

[rules]
world = ["<rules of this world>"]
off_limits = ["<what the story never does>"]
```

## Voices (every character speaks with one)
- Every character gets a `voice` table: `engine` (`"qwen3"`, the acted default, or `"kokoro"`), `preset` (qwen3:
  `ryan` bright and young, `aiden` low and dry; kokoro: `am_fenrir`, `am_onyx`, `am_michael`, `am_puck`, `af_heart`,
  `af_bella`, `af_nicole`, `bf_emma`, `bm_george`, `bm_lewis`), `instruct` (qwen3: how it talks) and `pace` (words a
  second, 3.0-3.8). Two characters who talk to each other get different presets.
- Delivery is **brisk**: smug, dry, bored or grand, but fast. Never write "slow", "drawling", "unhurried" or "leaves
  pauses" in an instruction; a slow voice kills a comedy short. A deadpan beat is a line's style, not a character's.
- `voice = "none"` only for a character that never says a word (it still has its game sounds).
- A narrator is always available as actor `"narrator"` (the cast library's, a steady British male voice); add a
  `[[character]] id = "narrator", kind = "narrator"` with its own voice table to give it another.

Return only the file, between a line `<<<FILE` and a line `FILE>>>`.
