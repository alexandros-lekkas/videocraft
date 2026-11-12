{{craft}}

# Stage 3 of 5: the outline

From the premise and the bible, write `outline.md`: the beats, each with its purpose and an estimated length, and a
comedy pass.

## The premise
{{premise}}

## The bible
```toml
{{bible}}
```

Write Markdown in this shape:

```
# <Title>: outline

Target: <seconds> s, about <n> shots.

## 1. <beat name> (setup, ~6 s)
What happens, where, who. The purpose of the beat in one line.

## 2. ... (escalation, turn, payoff, button: as many beats as the length needs)

## Comedy pass
| Joke | Beat | How it lands (visual / line / sound / cut) | Setup → payoff |
|:--|:--|:--|:--|
```

Every joke the story has must be in the comedy pass table. At least half the jokes land visually or with a sound.

Return only the file, between a line `<<<FILE` and a line `FILE>>>`.
