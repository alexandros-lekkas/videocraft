"""`videocraft lint <script>`: problems in a script before a take, all at once (compile stops at the first).

Rules (each problem: severity error | warn | info, rule, where, message):
  unknown_key       top-level, [world], [[actor]], [[shot]] keys the compiler does not allow (its allow-lists)
  cue_outside       a cue's `at` past the shot's end or before -preroll
  unknown_action    a `do` that is not built in and not namespaced (`<modid>:<name>`)
  unknown_rig       a camera `rig` that is not built in and not namespaced
  unknown_actor     a cue's `actor` or a camera's `subject` that is not `player` or an [[actor]] id
  reading           text that cannot be complete on screen for max(1.2 s, 0.5 s + 0.3 s a word) before the next
                    text or the end of the shot (one-word montage text: info)
  words_per_second  more than 2.5 words a second over the time the text can be up
  two_messages      two text items of different kinds on screen at once (a caption replacing a caption is fine)
  long_shot         a shot longer than the rubric's max_shot_seconds (the benchmark: 7.5 s), with --rubric
  anchor            `{ anchor = "set:mark" }` naming a set that [[world.set]] does not place; an anchor that is
                    not built in (info: actions may define it during the take)
  mark              `until` or an edit clip's `in`/`out` naming a mark no cue in that shot makes (warn)
  unvoiced_text     in a script with a cast or say lines: a caption, title or lower_third of 3 or more words no
                    voice speaks (warn: voice it with `say`; on-screen text is for signs, cards and posts)
  slow_line         a voiced line of 3 or more words under 2.6 words a second (warn; info for a slow style)
  dead_air          more than 0.8 s without a voice between two lines inside a run of dialogue shots (warn; not over
                    black, not across a shot without lines, not before a `beat = true` line)
Owned by workstream (d).
"""
import json
from pathlib import Path

from videocraft import script

TEXT_ACTIONS = {'caption', 'title', 'lower_third', 'keycap', 'card', 'say'}
# Exactly what the mod registers (r.action / r.rig in src/main/java; test_lint checks they have not drifted), plus
# `say`, which the compiler resolves into captions before the take.
COMPILED = {'say'}
BUILT_IN = COMPILED | {
    'command', 'mark', 'stand_in', 'glide', 'wait',                                         # director/CoreActions
    'place', 'walk', 'run', 'stop', 'turn', 'look', 'hop', 'jump', 'state', 'crouch', 'hold', 'emit', 'voice',
    'swing', 'nod', 'shake', 'talk', 'point', 'pose', 'blink',                                # actor/Actions
    'fly', 'hover', 'swarm', 'land',                                                          # actor/FlightActions
    'caption', 'title', 'card', 'lower_third', 'keycap', 'clear',                             # text/TextActions
    'sound', 'tune', 'ambience', 'particles',                                                 # sound/SoundActions
}
BUILT_IN_RIGS = {'orbit', 'fixed', 'lead', 'chase', 'track', 'dolly', 'crane', 'locked', 'two_shot', 'face', 'first'}
BUILT_IN_ANCHORS = {'spawn'}
STAGGER = 0.12          # seconds between popped words when the cue gives no explicit word times
WPS_MAX = 2.5


def reading_seconds(words):
    return max(1.2, 0.5 + 0.3 * words)


def _words(cue):
    if isinstance(cue.get('words'), list) and cue['words']:
        times = [float(w.get('at', 0)) if isinstance(w, dict) else 0.0 for w in cue['words']]
        return len(cue['words']), max(times)
    text = cue.get('text') or cue.get('title') or ''
    if isinstance(text, list):
        text = ' '.join(str(t) for t in text)
    n = len(str(text).replace('*', '').split())
    if cue.get('style') == 'whole' or cue.get('do') != 'caption':
        return n, 0.0
    return n, STAGGER * max(0, n - 1)


def _positions(value, where):
    """Every { anchor = … } inside a value, with where it is."""
    if isinstance(value, dict):
        if 'anchor' in value:
            yield value['anchor'], where
        for k, v in value.items():
            yield from _positions(v, f'{where}.{k}')
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from _positions(v, f'{where}[{i}]')


def lint(raw, rubric=None):
    from videocraft.voice import resolve as dialogue  # lint what the take plays: say lines resolved (voice group)
    if dialogue.has_say(raw):
        try:
            resolved = dialogue.resolve(raw, log=lambda line: None)
        except script.ScriptError as e:
            return [{'severity': 'error', 'rule': 'say', 'where': 'dialogue', 'message': str(e)}]
        return dialogue.lint_spoken(lint(resolved, rubric), resolved) + voice_rules(resolved)
    problems = []

    def add(severity, rule, where, message):
        problems.append({'severity': severity, 'rule': rule, 'where': where, 'message': message})

    def keys(table, allowed, where):
        if isinstance(table, dict):
            for k in sorted(set(table) - set(allowed)):
                add('error', 'unknown_key', where, f'unknown key `{k}`; allowed: {", ".join(sorted(allowed))}')

    keys(raw, script.TOP, 'top level')
    world = raw.get('world', {}) or {}
    keys(world, script.WORLD, 'world')
    actor_keys = getattr(script, 'ACTOR', None)
    actors = {'player'}
    for i, a in enumerate(raw.get('actor', []) or []):
        if actor_keys:
            keys(a, actor_keys, f'actor[{i}]')
        if a.get('id'):
            actors.add(str(a['id']))
    # A placed set's marks go by its `as` prefix, else its name (a set given by path: the file's stem).
    sets = {str(s.get('as') or (Path(str(s.get('name'))).stem if str(s.get('name')).endswith('.toml') else s.get('name')))
            for s in (world.get('set') or []) if isinstance(s, dict)}
    max_shot = (rubric or {}).get('pass', {}).get('max_shot_seconds')

    def anchors(value, where):
        for anchor, at in _positions(value, where):
            anchor = str(anchor)
            if ':' in anchor:
                name = anchor.split(':', 1)[0]
                if name not in sets and not _plugin_namespace(name):
                    add('error', 'anchor', at, f'anchor "{anchor}" names set "{name}", which no [[world.set]] places; sets: {sorted(sets) or "none"}')
            elif anchor not in BUILT_IN_ANCHORS:
                add('info', 'anchor', at, f'anchor "{anchor}" is not built in; it must be defined by an action before it is used')

    for i, cue in enumerate(world.get('stage', []) or []):
        _cue_checks(cue, f'world.stage[{i}]', None, 0.0, actors, add)
        anchors(cue, f'world.stage[{i}]')
    for i, a in enumerate(raw.get('actor', []) or []):
        anchors(a, f'actor[{i}]')

    marks_by_shot = {}
    for i, shot in enumerate(raw.get('shot', []) or []):
        name = shot.get('name', f'#{i}')
        where = f'shot {name}'
        keys(shot, script.SHOT, where)
        duration = float(shot.get('duration', 0) or 0)
        preroll = float(shot.get('preroll', 0) or 0)
        if max_shot and duration > max_shot:
            add('warn', 'long_shot', where, f'{duration:g} s is longer than {max_shot:g} s ({(rubric or {}).get("name")} rubric)')
        camera = shot.get('camera') or {}
        rig = camera.get('rig') if isinstance(camera, dict) else None
        if isinstance(rig, str) and rig not in BUILT_IN_RIGS and ':' not in rig:
            add('warn', 'unknown_rig', f'{where}.camera', f'`rig = "{rig}"` is not a built-in rig ({", ".join(sorted(BUILT_IN_RIGS))}); '
                'a plugin rig is "<modid>:<name>"')
        subject = camera.get('subject')
        if isinstance(subject, str) and subject not in actors:
            add('error', 'unknown_actor', f'{where}.camera', f'subject "{subject}" is not an actor; actors: {sorted(actors)}')
        anchors(camera, f'{where}.camera')
        cues = sorted(enumerate(shot.get('cue', []) or []), key=lambda c: float(c[1].get('at', 0) or 0))
        marks = {str(c.get('label')) for _, c in cues if c.get('do') == 'mark'}
        marks_by_shot[name] = marks
        texts = []
        for k, cue in cues:
            at = f'{where}.cue[{k}]'
            _cue_checks(cue, at, duration, preroll, actors, add)
            anchors(cue, at)
            if cue.get('do') in TEXT_ACTIONS:
                texts.append((float(cue.get('at', 0) or 0), cue, at))
        for j, (start, cue, at) in enumerate(texts):
            n, last_word = _words(cue)
            nxt = next((s for s, c, _ in texts[j + 1:] if s > start), duration)
            end = min(nxt, duration)
            if 'hold' in cue:
                end = min(end, start + last_word + float(cue['hold']))
            complete = end - (start + last_word)
            need = reading_seconds(n)
            if n and complete + 1e-9 < need:
                add('info' if n == 1 else 'error', 'reading', at,
                    f'{n} word(s) complete for {complete:.2f} s before the {"next text" if nxt < duration else "end of the shot"}; needs {need:.2f} s')
            up = end - start
            if n > 1 and up > 0 and n / up > WPS_MAX + 1e-9:
                add('warn', 'words_per_second', at, f'{n} words in {up:.2f} s is {n / up:.1f} a second (at most {WPS_MAX})')
            hold_end = start + last_word + float(cue.get('hold', 1e9))
            for s2, c2, at2 in texts[j + 1:]:
                if s2 < hold_end and s2 < duration and c2.get('do') != cue.get('do') and 'clear' not in (c2.get('do'),):
                    add('error', 'two_messages', at2, f'{c2.get("do")} starts at {s2:g} s while the {cue.get("do")} from {start:g} s is up')
                    break
        until = shot.get('until')
        if until and str(until) not in marks:
            add('warn', 'mark', where, f'until = "{until}" but no mark cue in this shot makes it (an action may)')
    for i, clip in enumerate(((raw.get('edit') or {}).get('clip') or [])):
        for key in ('in', 'out'):
            label = clip.get(key)
            if isinstance(label, str) and label not in marks_by_shot.get(clip.get('shot'), set()):
                add('warn', 'mark', f'edit.clip[{i}].{key}', f'mark "{label}" is not made by a mark cue in shot {clip.get("shot")}')
    if raw.get('cast') and 'dialogue' not in (raw.get('edit') or {}):
        problems += voice_rules(raw)   # a cast but no say line yet (with say lines, the resolved branch adds them)
    return problems


UNVOICED_MIN = 3


def voice_rules(resolved):
    """Voiced and fast is the default (the owner: voiced lines are "significantly better" than captions, and the
    first films' lines were too slow): unvoiced text, slow lines and dead air, on the resolved script."""
    from videocraft.measure import dialogue as pace
    out = []
    fps = int((resolved.get('output') or {}).get('fps', 60))
    for shot in resolved.get('shot') or []:
        for k, c in enumerate(shot.get('cue') or []):
            if not isinstance(c, dict) or c.get('do') not in ('caption', 'title', 'lower_third') or c.get('voiced'):
                continue
            n = _words(c)[0] + len(str(c.get('subtitle') or '').split())
            if n >= UNVOICED_MIN:
                out.append({'severity': 'warn', 'rule': 'unvoiced_text', 'where': f'shot {shot.get("name")}.cue[{k}]',
                            'message': f'{c["do"]} of {n} words that no voice speaks: voice it with `say` (the caption '
                                       'comes with it); keep silent on-screen text for signs, cards and posts'})
    lines, segments, shots, _ = pace.script_lines(resolved, fps)
    for l in pace.slow(lines):
        out.append({'severity': 'info' if l['slow_style'] else 'warn', 'rule': 'slow_line', 'where': f'line {l["id"]}',
                    'message': f'{l["words"]} words at {l["wps"]:.2f} words a second (under {pace.SLOW_WPS}; the default '
                               'pace is 3.2): shorten it, drop a slow style, or raise the character\'s pace'
                               + (f' ({l["style"]}: slow on purpose)' if l['slow_style'] else '')})
    for g in pace.dead_air(lines, segments, shots):
        out.append({'severity': 'warn', 'rule': 'dead_air', 'where': f'line {g["before"]}',
                    'message': f'{g["seconds"]:.2f} s without a voice after {g["after"]} (at {g["start"]:.2f}-{g["end"]:.2f} s '
                               f'of the cut; over {pace.DEAD_AIR} s): drop the at so the line packs, shorten the shot, '
                               'or mark the line beat = true if the pause is the joke'})
    return out


def _plugin_namespace(name):
    return '.' in name or name in ('t3craft',)


def _cue_checks(cue, at, duration, preroll, actors, add):
    if not isinstance(cue, dict) or 'do' not in cue:
        add('error', 'unknown_action', at, 'a cue is a table with `do` (the action) and `at` (seconds)')
        return
    do = str(cue['do'])
    if do not in BUILT_IN and ':' not in do:
        add('warn', 'unknown_action', at, f'`do = "{do}"` is not a built-in action; a plugin action is "<modid>:<name>"')
    t = float(cue.get('at', 0) or 0)
    if duration is not None and (t > duration + 1e-9 or t < -preroll - 1e-9):
        add('error', 'cue_outside', at, f'at = {t:g} is outside the shot ({-preroll if preroll else 0:g} to {duration:g} s)')
    actor = cue.get('actor')
    if isinstance(actor, str) and actor not in actors:
        add('error', 'unknown_actor', at, f'actor "{actor}" is not declared; actors: {sorted(actors)}')
    for key in ('target', 'to', 'at_actor'):
        v = cue.get(key)
        if isinstance(v, str) and v not in actors and v not in ('camera', 'lens') and key != 'to':
            add('warn', 'unknown_actor', at, f'{key} "{v}" is not an actor')


def report(problems):
    counts = {s: sum(1 for p in problems if p['severity'] == s) for s in ('error', 'warn', 'info')}
    lines = [f'{p["severity"].upper():5} {p["rule"]:<16} {p["where"]}: {p["message"]}' for p in problems]
    return counts, lines


def write(it, problems):
    counts, _ = report(problems)
    (it.path / 'lint.json').write_text(json.dumps({'counts': counts, 'problems': problems}, indent=2) + '\n')
