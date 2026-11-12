# Gallery

Videos made with videocraft, each with the script that made it, so anyone can run it again and get the same take.
Videos are hosted outside the repository (GitHub releases); `runs/` is never committed.

| Video | Script | What it shows | Made with |
|:--|:--|:--|:--|
| [Nibs vs Duke](https://github.com/alexandros-lekkas/videocraft/releases/download/demo-nibs-vs-duke-1/nibs-vs-duke-720p30.mp4) (73 s, [1080p60](https://github.com/alexandros-lekkas/videocraft/releases/download/demo-nibs-vs-duke-1/nibs-vs-duke-1080p60.mp4)) | [examples/nibs-vs-duke.toml](../examples/nibs-vs-duke.toml) | The benchmark comedy short: two sets, mob actors, lead tracks, flashback, montage, voices, captions; reviewed 6.6/10 ([log](benchmarks/nibs-vs-duke-log.md)) | `b155b7d`, take 12 |

To add one: link the published video, the script (in `examples/`, `stories/<id>/shots.toml`, or a gist), one line
on what it shows, and the videocraft commit it was made with (`meta.json` in the run records it). Only original
content: no third-party footage, characters or audio, and no Mojang assets beyond what the game draws in its frames
([CREDITS.md](../CREDITS.md)).

## Run them yourself

Every script in [`examples/`](../examples/) is a working take with a comment at the top saying what it shows:

| Script | Shows |
|:--|:--|
| `hello.toml` | A 3 s orbit around spawn at 1080p60: the smallest take |
| `rigs.toml` | Every camera rig once, on stand-ins |
| `animals.toml` | Mob actors: a strutting goat, a snow fox that sits, bows and sleeps, a chicken that lays an egg |
| `mannequins.toml` | Two skinned mannequins meet and talk with their hands |
| `walk.toml` | The played player walks, jumps and turns with a human hand |
| `talk.toml` | Dialogue: four lines, word-timed captions, a cut on a word |
| `text.toml` | Every text action |
| `edit.toml` | The frame-exact edit: pushes, a dip to black, a framed flashback, a speed ramp, exports |
| `sound.toml` | Logged game sounds, a note-block tune, ambience, a synth bed |
| `sets.toml` | A set from `sets/`, walked on lead tracks |
| `clips/reframe.toml` | The fixture for vertical re-framing |
