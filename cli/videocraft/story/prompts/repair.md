# Repair round {{round}} of {{rounds}}

The `{{file}}` you wrote does not pass the checks. Fix exactly these problems and return the whole corrected file.
Do not change anything the problems do not need. Use only the actions, rigs and keys the reference allows.
Problems starting `voice:` are about voiced, brisk dialogue: voice text that is only a caption with a `say` cue,
speed up or shorten a slow line, and close dead air (drop a later line's `at` so it packs, shorten the shot, or mark
a deliberate pause `beat = true`).

## Problems
{{problems}}

## The file you wrote
{{current}}

Return only the file, between a line `<<<FILE` and a line `FILE>>>`.
