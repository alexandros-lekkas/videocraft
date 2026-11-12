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
in), marks its key word with `*` (at most one per line: the word the cut lands on; most lines have one), and is
written as speech: a voice reads every line aloud, briskly, at about 3.2 words a second.

**Voiced, not captioned.** A voiced line is far better than a caption (the owner's verdict on the first films). So:
- Everything the audience must know is said by a voice: a character, or `NARRATOR (VO):` for exposition. The
  subtitles come with the voice automatically; never write a `[CAPTION]` for words someone says.
- `[CAPTION]` and `[CARD]` are only for writing that exists in the world or on screen: a sign, a post, a notice, a
  title card. When that writing matters to the joke, a voice reads it aloud too (the narrator, or a character
  reading it: `NIBS: "Talent Night. Tonight." Oh, that's *me.`).
- Talk is near-continuous: line follows line with no dead air. Silence only on purpose: a dip to black before a
  reveal, or a beat that is the joke (write `[BEAT]` before the line that lands after it).
- Keep lines short and punchy (3-12 words); split a long speech into several lines over several shots.

Return only the file, between a line `<<<FILE` and a line `FILE>>>`.
