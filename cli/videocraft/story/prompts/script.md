{{craft}}

# Stage 4 of 5: the script

From the outline, write `script.md`: scenes with dialogue, action lines, sound cues and captions/cards.

## The premise
{{premise}}

## The bible
```toml
{{bible}}
```

## The outline
{{outline}}

Write Markdown in this shape:

```
# <Title>: script

## Scene 1: <set name>, <time of day>

> Action lines in plain sentences: what we see. One shot idea per paragraph.

NIBS (VO): Hey. It's me. *Nibs.
DUKE: Hit it.

[SOUND: minecraft:entity.goat.ambient on "Nibs"]
[CARD: "TALENT NIGHT · Champion 3 years running: DUKE"]
[CAPTION: words that are on screen but not spoken]
[DIP TO BLACK]
```

Rules: every spoken line starts with the speaker's name in capitals (add `(VO)` for narration over a shot it is not
in), marks its key word with `*` (at most one per line: the word the cut lands on; most lines have one), and is short enough to read at 2.5 words a second within its
shot. Write the lines as speech: the voice tool reads them aloud.

Return only the file, between a line `<<<FILE` and a line `FILE>>>`.
