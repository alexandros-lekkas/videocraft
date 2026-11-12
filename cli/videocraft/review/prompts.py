"""One prompt per reviewer role, written into review/packet/prompts/<role>.md. The prompt is the whole brief: what the
reviewer can and cannot perceive, its criteria with the 5 and 9 anchors, the gates, which images and numbers to use,
and the exact JSON to return (validated by review.reviews.validate). Owned by workstream (d)."""
import json

from videocraft.review import rubric as rubrics


def dig(metrics, dotted):
    v = metrics
    for part in dotted.split('.'):
        if not isinstance(v, dict) or part not in v:
            return None
        v = v[part]
    return v


def numbers_for(rub, rid, metrics):
    keys = ['checks', 'picture.shot_stats']
    for c in rubrics.criteria_of(rub, rid):
        keys += c.get('numbers', [])
    out = {}
    for k in dict.fromkeys(keys):
        v = dig(metrics, k)
        if v is not None:
            out[k] = v
    return out


def images_for(rub, rid, manifest):
    files = []
    for kind in rubrics.role(rub, rid).get('images', []):
        files += manifest['files'].get(kind, [])
    return files


def schema(rub, rid):
    crit = [c['id'] for c in rubrics.criteria_of(rub, rid)]
    return {
        'type': 'object', 'additionalProperties': False,
        'required': ['reviewer', 'scores', 'gates', 'notes', 'fixes', 'verdict'],
        'properties': {
            'reviewer': {'type': 'string', 'enum': [rid]},
            'scores': {'type': 'object', 'additionalProperties': False, 'required': crit,
                       'properties': {c: {'type': 'integer', 'minimum': 1, 'maximum': 10} for c in crit}},
            'gates': {'type': 'object', 'additionalProperties': False, 'required': [g['id'] for g in rub['gate']],
                      'properties': {g['id']: {'type': 'string', 'enum': ['pass', 'fail']} for g in rub['gate']}},
            'notes': {'type': 'array', 'items': {'type': 'object', 'additionalProperties': False, 'required': ['shot', 't', 'text'],
                                                 'properties': {'shot': {'type': 'string'}, 't': {'type': 'string'}, 'text': {'type': 'string'}}}},
            'fixes': {'type': 'array', 'minItems': 3, 'maxItems': 3,
                      'items': {'type': 'object', 'additionalProperties': False, 'required': ['fix', 'why', 'shot', 't'],
                                'properties': {'fix': {'type': 'string'}, 'why': {'type': 'string'}, 'shot': {'type': 'string'}, 't': {'type': 'string'}}}},
            'verdict': {'type': 'string'},
        },
    }


def prompt(rub, rid, manifest, metrics, packet_dir):
    role = rubrics.role(rub, rid)
    crits = rubrics.criteria_of(rub, rid)
    images = images_for(rub, rid, manifest)
    L = [f'# Review of {manifest["run"]}: {role.get("name", rid)}', '',
         f'You are the **{role.get("name", rid)}** on a panel reviewing a short video made inside Minecraft by videocraft '
         f'(a scripted, hidden game client that films a shot script). Rubric: **{rub.get("title", rub["name"])}**.', '',
         '## What you can and cannot perceive', '',
         '- You see **still frames and numbers only**. You cannot watch motion and you cannot hear sound.',
         '- Motion is evidenced by frame sequences in the strips (first, last and every n-th frame of each clip) and by '
         'the camera and framing numbers measured from the game\'s own per-frame log. Sound is evidenced only by the '
         'loudness numbers and by the sound events the script and the logs list.',
         '- Where a criterion depends on something you cannot perceive, say so in a note and score from the evidence you '
         'have; do not give the benefit of the doubt, and do not punish what you cannot see either.',
         '- Labels in the images: `0:12.34` is the timecode in the cut, `M` the frame of the cut, `S` the frame of the shot.',
         '', '## Your focus', '', role.get('focus', ''), '', '## Your criteria (score each 1-10)', '']
    for c in crits:
        L += [f'### `{c["id"]}`: {c["name"]}', '', f'What it measures: {c["measures"]}.', '',
              f'- **A 5 looks like:** {c["anchor_5"]}', f'- **A 9 looks like:** {c["anchor_9"]}', '']
    if rub['gate']:
        L += ['## Gates (pass or fail)', '']
        for g in rub['gate']:
            L.append(f'- `{g["id"]}`: {g["name"]}. {g.get("measures", "")}')
        L.append('')
    L += ['## The evidence', '', f'The cut is {manifest["seconds"]:.2f} s ({manifest["frames"]} frames at {manifest["fps"]} fps), '
          f'{sum(1 for c in manifest["clips"] if c["kind"] == "shot")} clips:', '', '| # | Clip | Kind | Cut in | Cut out |', '|--:|:--|:--|--:|--:|']
    for c in manifest['clips']:
        L.append(f'| {c["index"] + 1} | {c["shot"] or "black"} | {c["kind"]} | {c["start"]} | {c["end"]} |')
    L += ['', '### Images', '']
    if images:
        L.append('Look at every one of these (paths are relative to the packet folder ' f'`{packet_dir}`):')
        L += [f'- `{f}`' for f in images]
    else:
        L.append('No images for this role: judge from the numbers, the captions and the script.')
    L += ['', 'Also in the packet: `captions.md` (every caption per shot), `report.md` (all measurements), `script.toml` (the script).',
          '', '### Numbers (from measure/metrics.json)', '', '```json', json.dumps(numbers_for(rub, rid, metrics), indent=1)[:60000], '```', '',
          '## What to return', '',
          'Write your reasoning first if you like, then end with **one** fenced ```json block, exactly this shape and nothing '
          'else inside it:', '',
          '- `reviewer`: `"' + rid + '"`',
          '- `scores`: an integer 1-10 for each of ' + ', '.join(f'`{c["id"]}`' for c in crits),
          '- `gates`: ' + (', '.join(f'`{g["id"]}`: `"pass"` or `"fail"`' for g in rub['gate']) or '`{}`'),
          '- `notes`: the observations behind the scores, each `{"shot": "<clip name>", "t": "<m:ss.ss>", "text": "…"}`; cite what you saw',
          '- `fixes`: **exactly three**, the most valuable changes first, each `{"fix": "<a change to the script>", "why": "…", "shot": "…", "t": "…"}`',
          '- `verdict`: one sentence', '',
          'Be strict: a 9 is the anchor above, not "good for a tool". Use the whole scale.', '']
    return '\n'.join(L)
