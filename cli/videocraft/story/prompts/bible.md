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
voice = "<a voice description for the voice tool: age, pitch, pace, accent-free, energy>"
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

Return only the file, between a line `<<<FILE` and a line `FILE>>>`.
