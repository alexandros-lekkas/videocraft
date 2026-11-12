# The story pipeline

From a one-line premise to a shot script the recorder performs, in five stages. Each stage is a plain file that a
person can read and edit and git can diff, and each one is drafted from the stages before it. A model drafts them
(`videocraft.agents.ask`, or `claude -p` until that module lands), or a person writes them and locks them in with
`--from-file`.

```
 "<premise>" ─▶ premise.md ─▶ bible.toml ─▶ outline.md ─▶ script.md ─▶ shots.toml ─▶ videocraft run ─▶ cut/master.mp4
               logline,       characters,   beats with    scenes,       a shot script:
               tone, format,  sets, gags,   purpose and   dialogue      compile + lint,
               reference      rules         lengths, a    with *key     up to 3 repair
               form                         comedy pass   words, sound  rounds
```

| Stage | File | What it holds | Checked for |
|:--|:--|:--|:--|
| premise | `premise.md` | Title, logline, tone, audience, format (`short` 30-90 s, `episode` 3-8 min, `long` 10-20 min; 16:9 or 9:16), reference form, characters, five beats, rules | a title and the `Logline` and `Format` sections |
| bible | `bible.toml` | `[[character]]` (id, kind `mob` with `entity`/`mannequin` with a `skin` spec/`narrator`, look, personality, voice description, sounds, gestures), `[[set]]` (an existing set or a description), `[[gag]]`, `[rules]` | valid TOML, ids usable as actor ids, mobs have an entity, mannequins a skin |
| outline | `outline.md` | Beats (`## n. name (purpose, ~length)`) and a comedy pass naming every joke and how it lands (visual, line, sound or cut) | at least three beats and the comedy pass |
| script | `script.md` | Scenes, action lines, `NAME: line with *key word` (`(VO)` for narration), `[SOUND: …]`, `[CARD: …]`, `[CAPTION: …]`, `[DIP TO BLACK]` | scene headings, at most one `*key` word per line |
| shots | `shots.toml` | A videocraft shot script ([SCRIPT.md](SCRIPT.md)) named after the story | `videocraft compile`, `videocraft lint` (once it exists), only known actions and rigs, every cue's actor exists, no shot over 7.5 s in a short, the format's length, 1080x1920 when vertical |

## Commands

```sh
bin/videocraft story new "<premise>" [--id ID] [--format short|episode|long] [--vertical] [--reference "<form>"] [--through shots]
bin/videocraft story draft <stage> <story> [--note "…"]        # regenerate a stage from the stages before it
bin/videocraft story revise <stage> <story> --note "…"         # a new revision of the current one with the note applied
bin/videocraft story build <story>                             # draft shots.toml; compile + lint; repair up to 3 times
bin/videocraft story show <story> [stage] [--rev N]            # the stages (current revision, stale marks) or one text
bin/videocraft story diff <story> <stage> [r1 r2]              # unified diff, default the last two revisions
bin/videocraft story lock <story> <stage> <rev>                # choose another revision
bin/videocraft story list
bin/videocraft series new <story> --episodes N [--format …]    # split into episode stories that share the bible
bin/videocraft series status <story>
bin/videocraft make "<prompt>" [--format …] [--vertical] [--dry-run]   # prompt → … → shots.toml → run → cut
```

Every stage command takes `--from-file <file>` (lock in a hand-written draft, no model), `--no-lock` (keep the new
revision without choosing it) and `--repairs N`. Exit codes: 0 done, 1 a stage failed its checks (the problems are
printed, one fix each), 2 no model or a usage error. `make` stops at the first stage that fails and says which;
without `--dry-run` it ends with `videocraft run`'s own `RESULT` lines.

## Where the files are

```
runs/story/<story-id>/            every draft, never committed
  index.json                      per stage: revisions {rev, file, parent, note, source: model|repair|file|series|locked,
                                  created, sha, inputs: the upstream stages' shas it was drafted from}, and `locked`
  premise/0001.md  bible/0001.toml  outline/0002.md  script/0003.md  shots/0004.toml  shots/0004.plan.json
stories/<story-id>/               the chosen revisions, committed: the human-readable source of truth
  story.json                      id, format, vertical, request, series links, each stage's locked rev, sha and inputs
  premise.md  bible.toml  outline.md  script.md  shots.toml
  series.json                     a series story: its episodes
```

Nothing is overwritten: a draft, a revision and every repair round are new revisions, so `story diff` shows what a
note or a repair changed. A draft that passes its checks is locked (copied to `stories/<id>/`); one that fails is
kept but not locked. The next stage reads the locked file. When an upstream stage changes, `story show` marks the
stages drafted from the old one as `STALE`. A fresh clone has `stories/` but no `runs/`: the store imports each
locked file as revision 1 and carries on.

Hand edits are fine: edit `stories/<id>/script.md` and the next `story draft shots` reads it, or run
`story draft script <id> --from-file stories/<id>/script.md` to record the edit as a revision.

## How the model is taught

The prompts are in `cli/videocraft/story/prompts/`. `craft.md` goes into every stage: the benchmark's lessons
(cuts land on words, setup wide and punchline close, the look to the lens, the brag montage, dips to black before
reveals, one message at a time, captions at most 2.5 words a second, a median shot of about 2.6 s, never a shot over
7.5 s, visual jokes), what the recorder can and cannot do, and the originality rule. The shots prompt includes
[SCRIPT.md](SCRIPT.md) verbatim at prompt time (and SETS.md and the sets in `sets/` with their marks once they
exist), plus the actions and rigs this night's workstreams have promised but SCRIPT.md does not document yet; a
draft that uses anything else goes back to the model with the list. A failed check becomes a repair prompt
(`repair.md`) quoting each problem; after three rounds the stage stops and reports.

## Series

`series new <story> --episodes N` splits a story (premise, bible, outline, script if any) into episodes that each
stand alone (a cold open, their own payoff, a button) and continue the last (a "previously" line, the recurring
gags). Each episode is a story `<story>-e01`, `-e02`, … whose premise is written from the split and whose bible *is*
the series bible (`bible_from` in story.json): drafting an episode reads it, and it is revised only in the series
story. An episode's premise records the shas of the series stages it came from, so a changed series premise marks
the episodes stale. `--from-file` takes a hand-written split: a JSON list of
`{title, logline, previously, cold_open, payoff, button, gags: [], beats: []}`.

## Stories in this repository

- `stories/nibs-vs-duke/`: the benchmark's original script ([pinksheep-style.md](benchmarks/pinksheep-style.md)),
  written in by hand: premise, bible, outline and script with every line and key word. Its shot script is the
  production team's.
- Local stories (`.gitignore`'s local section) are the owner's to publish or not.
