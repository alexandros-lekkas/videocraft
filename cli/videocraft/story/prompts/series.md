{{craft}}

# Split a story into a series

Split the story below into {{episodes}} numbered episodes of format `{{format}}`. Each episode stands alone: a cold
open, its own payoff and a button. Each continues the last: a one-line "previously" (none for episode 1), the
recurring gags from the bible, the same characters and sets. Together they tell the whole story in order.

## The premise
{{premise}}

## The bible
```toml
{{bible}}
```

## The outline
{{outline}}

## The script (if any)
{{script}}

Reply with JSON only: a list of {{episodes}} objects, each
`{"title": "...", "logline": "...", "previously": "... or empty", "cold_open": "...", "payoff": "...",
"button": "...", "gags": ["..."], "beats": ["setup ...", "escalation ...", "turn ...", "payoff ...", "button ..."]}`.
