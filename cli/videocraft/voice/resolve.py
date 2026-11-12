"""The dialogue resolver: `say` cues in, captions on the words, voice in the mix and shot lengths that fit the lines.

script.compile_script calls resolve(raw, source) before compiling, only when the script has a `say` cue. Each line
is synthesized (or read from the cache; front.py) and replaced in its shot by

  (a) a `caption` cue whose words pop at the aligned word onsets (`words = [{ w, at }]`; the `*` key word kept;
      speaker tag and colour from the cast),
  (b) an `edit.voice` entry { file, shot, at, gain } that the mix places and levels,
  (c) with the cast's `bark`, a `sound` cue with the character's game sound on the first word,

and the shot's duration is set by the line's `fit`:

  extend   (default) the shot lasts at least to the line's last word + `tail` (0.25 s); a shot of dialogue may
           leave `duration` out
  cut-on   the shot ends on the onset of the word `cut_on`, so the next cut lands on it; the rest of the caption
           carries into the next shot (script order) while the voice plays on over the cut
  none     the duration is left as written; a line that runs past the shot's end carries its whole caption into
           the next shot(s), the words already said settled, the rest popping on their onsets

Lines are packed: the first line of a shot starts at its `at`; every later line (fit extend or cut-on) follows the
previous one after `gap` (GAP, 0.12 s; the previous line's `pause_after`, or the line's own `gap`, sets it), and an
`at` written on a later line is replaced by the packed time (a note on stderr says so), unless the line is marked
`beat = true` (a deliberate pause before it) or has fit = "none". Lines are paced before they are timed (pace.py:
silence trimmed, pauses capped, a slow line stretched towards the character's `pace`); the cue's `pace` overrides
the character's (0 or false: as synthesized). The lines and their
timings go into edit.dialogue (the run store writes it to voice.json) and a short table on stderr.
With no voice installed (or VIDEOCRAFT_VOICE=estimate) the same pass runs on reading-speed estimates, with no audio.
"""
import copy
import math
import os
import re
import sys

from videocraft.voice import cast as castmod
from videocraft.voice import front
from videocraft.voice import pace

SAY_KEYS = {'do', 'at', 'actor', 'character', 'text', 'style', 'speed', 'pause_after', 'fit', 'cut_on', 'tail', 'gain',
            'caption', 'speaker', 'bark', 'id', 'position', 'size', 'hold', 'shade', 'key_color', 'color', 'carry',
            'pace', 'beat', 'gap'}
CAPTION_KEYS = ('position', 'size', 'hold', 'shade', 'key_color', 'color')
FITS = ('extend', 'cut-on', 'none')
TAIL = 0.25
GAP = 0.12            # between packed lines (was PAUSE_AFTER = 0.2 before pacing)
PAUSE_AFTER = GAP


def has_say(raw):
    return any(isinstance(c, dict) and c.get('do') == 'say'
               for s in (raw.get('shot') or []) if isinstance(s, dict) for c in (s.get('cue') or []))


def _error(msg):
    from videocraft.script import ScriptError
    return ScriptError(msg)


def _bare(token):
    return re.sub(r"[^a-z0-9']", '', token.lower().lstrip('*'))


def _stderr(s):
    print(s, file=sys.stderr, flush=True)


class Line:
    def __init__(self, shot, cue, where, display, tokens, character, spec):
        self.shot, self.cue, self.where = shot, cue, where
        self.display, self.tokens, self.character, self.spec = display, tokens, character, spec
        self.result = None


def _lines(raw, cast, draft):
    lines = []
    for i, c in enumerate((raw.get('world') or {}).get('stage') or []):
        if isinstance(c, dict) and c.get('do') == 'say':
            raise _error(f'world.stage[{i}]: a say cue belongs in a recorded [[shot]], not in staging')
    for si, shot in enumerate(raw.get('shot') or []):
        sname = shot.get('name', f'#{si}')
        for ci, cue in enumerate(shot.get('cue') or []):
            if not isinstance(cue, dict) or cue.get('do') != 'say':
                continue
            where = f'shot {sname}.cue[{ci}] (say)'
            extra = sorted(set(cue) - SAY_KEYS)
            if extra:
                raise _error(f'{where}: unknown key(s) {", ".join(extra)}; allowed: {", ".join(sorted(SAY_KEYS))}')
            text = cue.get('text')
            if not isinstance(text, str) or not text.split():
                raise _error(f'{where}: text = "<the line>" is required (a word starting * is the key word)')
            display = text.split()
            tokens = [t[1:] if t.startswith('*') and len(t) > 1 else t for t in display]
            cid = cue.get('character') or cue.get('actor')
            if not isinstance(cid, str) or not cid:
                raise _error(f'{where}: actor = "<who speaks>" (a character of the cast) is required')
            fit = cue.get('fit', 'extend')
            if fit not in FITS:
                raise _error(f'{where}: fit is one of {", ".join(FITS)} (got {fit!r})')
            if fit == 'cut-on' and 'cut_on' not in cue:
                raise _error(f'{where}: fit = "cut-on" needs cut_on = "<a word of the line>"')
            if 'cut_on' in cue and fit not in ('cut-on',):
                if 'fit' in cue:
                    raise _error(f'{where}: cut_on goes with fit = "cut-on" (got fit = {fit!r})')
                cue = {**cue, 'fit': 'cut-on'}
            if 'cut_on' in cue:
                _cut_index(cue['cut_on'], tokens, where)
            if 'at' in cue and (not isinstance(cue['at'], (int, float)) or isinstance(cue['at'], bool) or cue['at'] < 0):
                raise _error(f'{where}: at = <seconds into the shot, >= 0>')
            for k in ('gap', 'pause_after'):
                if k in cue and (not isinstance(cue[k], (int, float)) or isinstance(cue[k], bool) or cue[k] < 0):
                    raise _error(f'{where}: {k} = <seconds of silence, >= 0>')
            p = cue.get('pace')
            if p is not None and p is not False and (not isinstance(p, (int, float)) or isinstance(p, bool) or p < 0):
                raise _error(f'{where}: pace = <words a second> (0 or false: no pacing)')
            try:
                ch = cast.character(cid)
                spec = ch.spec(tokens, cue.get('style'), cue.get('speed', 1.0), cast.styles, draft=draft,
                               pace=cue.get('pace'), beat=bool(cue.get('beat')))
            except castmod.CastError as e:
                raise _error(f'{where}: {e}') from e
            lines.append(Line(shot, cue, where, display, tokens, ch, spec))
    return lines


def _cut_index(cut_on, tokens, where):
    if isinstance(cut_on, int) and not isinstance(cut_on, bool):
        if 0 <= cut_on < len(tokens):
            return cut_on
        raise _error(f'{where}: cut_on = {cut_on} is not a word index of the line (0 to {len(tokens) - 1})')
    want = _bare(str(cut_on))
    hits = [i for i, t in enumerate(tokens) if _bare(t) == want]
    if not hits:
        raise _error(f'{where}: cut_on = "{cut_on}" is not a word of the line; words: {", ".join(tokens)}')
    return hits[0]


def _speaker(cue, ch):
    sp = cue.get('speaker', True)
    if sp is False:
        return None
    if sp is True or sp is None:
        return {'name': ch.name, 'color': ch.color}
    if isinstance(sp, str):
        return {'name': sp, 'color': ch.color}
    return sp


def _caption(line, at, words, actor, cue, ch, first, settled=False):
    """A caption cue for `words` [(display, start)] at shot time `at`. `settled`: words before the cue keep their
    negative times (the caption carried over a cut: words said in the shot before are on screen, already landed)."""
    cap = {'do': 'caption', 'at': round(at, 4), 'actor': actor, 'voiced': line.cue.get('id') or line.where,
           'words': [{'w': d, 'at': round(s if settled else max(0.0, s), 4)} for d, s in words]}
    sp = _speaker(cue, ch)
    if sp:
        cap['speaker'] = sp
    for k in CAPTION_KEYS:
        if k in cue:
            cap[k] = cue[k]
    if isinstance(cue.get('caption'), dict):
        cap.update({k: v for k, v in cue['caption'].items() if k not in ('do', 'at', 'words', 'text')})
    return cap


def resolve(raw, source='script', engine=None, log=None, cache=None):
    """The script with every `say` replaced (a deep copy; the input is not changed). Raises ScriptError."""
    log = log or _stderr
    raw = copy.deepcopy(raw)
    fps = int((raw.get('output') or {}).get('fps', 60))
    actors = {a['id']: a for a in (raw.get('actor') or []) if isinstance(a, dict) and isinstance(a.get('id'), str)}
    src = source if source and os.path.exists(str(source)) else None
    try:
        cast = castmod.load(raw.get('cast'), src, actors, log)
    except castmod.CastError as e:
        raise _error(str(e)) from e
    mode = (os.environ.get('VIDEOCRAFT_VOICE') or 'auto').lower()
    lines = _lines(raw, cast, draft=mode == 'draft')
    if not lines:
        return raw
    try:
        engine = engine or front.engine_for(None if mode == 'draft' else mode, log=log)
        results = front.synthesize([l.spec for l in lines], engine, cache)
    except front.VoiceError as e:
        raise _error(f'voice: {e}\n(VIDEOCRAFT_VOICE=estimate compiles with estimated timings and no voice)') from e
    for l, r in zip(lines, results):
        l.result = r

    edit = raw.setdefault('edit', {})
    voice = list(edit.get('voice') or [])
    report = []
    queue = list(lines)   # in script order; a line's cue may be a normalised copy (cut_on without fit)
    shots = raw.get('shot') or []
    carry = None
    # A caption never carries over a black gap of the edit (into the shot after the dip).
    order = [c for c in (edit.get('clip') or []) if isinstance(c, dict)]
    before_black = {order[i - 1].get('shot') for i, c in enumerate(order) if i and 'black' in c}
    for si, shot in enumerate(shots):
        sname = shot.get('name')
        new, prev_end, need_end, cut = [], None, 0.0, None
        prev_gap = GAP
        written = float(shot.get('duration') or 0)
        onward = None   # a fit = "none" caption that runs past this shot too
        if carry:
            new.append(carry['caption'])
            if carry.get('extend', True):
                need_end = max(need_end, carry['end'] + carry['tail'])
            prev_end = carry['end']   # the shot's first line waits for the carried words
            prev_gap = carry['pause_after']
            carry['entry'].setdefault('carried_to', sname)
            if not carry.get('extend', True):
                carry['entry'].setdefault('carried_through', []).append(sname)
                onward = _carry_on(carry, written, si + 1 < len(shots) and sname not in before_black)
            carry = None
        n = 0
        for cue in shot.get('cue') or []:
            if not (isinstance(cue, dict) and cue.get('do') == 'say'):
                new.append(cue)
                continue
            line = queue.pop(0)
            c, ch, r = line.cue, line.character, line.result
            n += 1
            ws = r['words']
            packed = None
            if prev_end is not None:
                packed = prev_end + float(c['gap']) if 'gap' in c else prev_end + prev_gap
            if 'at' not in c or (packed is not None and c.get('fit', 'extend') != 'none' and not c.get('beat')):
                at = max(0.0, packed - ws[0]['start']) if packed is not None else 0.0   # the voice, not the file, follows
                if 'at' in c and abs(at - float(c['at'])) > 0.02:
                    log(f'voice: {line.where}: packed at {at:.2f} s after the previous line (at = {float(c["at"]):g} '
                        'written; beat = true keeps it)')
            else:
                at = float(c['at'])
            end = at + ws[-1]['end']
            prev_end = end
            prev_gap = float(c.get('pause_after', GAP))
            tail = float(c.get('tail', TAIL))
            actor = c['actor'] if c.get('actor') in actors else 'player'
            fit = c.get('fit', 'extend')
            words = [(d, w['start']) for d, w in zip(line.display, ws)]
            entry = {'id': c.get('id') or f'{sname}-{n}', 'character': ch.id, 'shot': sname, 'at': round(at, 4),
                     'start_frame': round(at * fps), 'text': c['text'], 'style': c.get('style'), 'fit': fit,
                     'file': front.rel(r['file']) if r.get('file') else None, 'seconds': r.get('seconds'),
                     'engine': r.get('engine'), 'timing': r.get('timing'), 'cached': r.get('cached'), 'key': r.get('key'),
                     'voice': ch.voice if not ch.generic else f'{ch.voice} (generic)',
                     'wps': pace.words_per_second(ws), 'pace': r.get('pace'), 'beat': bool(c.get('beat')),
                     'words': [{'word': d, 'start': w['start'], 'end': w['end']} for d, w in zip(line.display, ws)]}
            shown = words
            if fit == 'cut-on':
                if cut is not None:
                    raise _error(f'{line.where}: one cut-on line per shot (the shot already ends on "{cut["word"]}")')
                k = _cut_index(c['cut_on'], line.tokens, line.where)
                onset = at + ws[k]['start']
                frame = max(1, round(onset * fps))
                cut = {'word': line.display[k], 'onset': round(onset, 4), 'frame': frame, 'where': line.where}
                entry['cut_on'] = {'word': line.display[k], 'index': k, 'onset': round(onset, 4), 'frame': frame}
                shown = words[:k]
                rest = words[k:]
                if rest and c.get('carry', True):
                    t0 = frame / fps
                    nxt = shots[si + 1] if si + 1 < len(shots) else None
                    if nxt is None:
                        log(f'voice: WARNING {line.where}: cut_on "{line.display[k]}" in the last shot: the words from it on are not shown')
                    else:
                        carry = {'caption': _caption(line, 0.0, [(d, at + s - t0) for d, s in rest],
                                                     c['actor'] if c.get('actor') in actors else 'player', c, ch, False),
                                 'end': end - t0, 'tail': tail, 'entry': entry,
                                 'pause_after': float(c.get('pause_after', GAP))}
                        carry['caption']['words'][0]['at'] = 0.0
            elif fit == 'extend':
                need_end = max(need_end, end + tail)
            elif fit == 'none' and written > 0 and si + 1 < len(shots) and c.get('carry', True) and sname not in before_black:
                # A line written to run over the cut (the shot keeps its length): its caption goes on in the next
                # shot(s), the whole line, the words already said there settled and the rest popping on their onsets;
                # a line that ends just before the cut stays up there for the rest of LINGER.
                k = next((i for i, (d, s) in enumerate(words) if at + s >= written - 1e-9), None)
                if k is not None or end + LINGER > written + 1e-9:
                    if k is not None:
                        shown = words[:k]
                    cap = _caption(line, 0.0, [(d, at + s - written) for d, s in words], actor, c, ch, False, settled=True)
                    if k is None and 'hold' not in cap:
                        cap['hold'] = round(end - (at + words[-1][1]) + LINGER, 4)
                    carry = {'caption': cap, 'end': end - written, 'tail': tail, 'entry': entry, 'extend': False,
                             'pause_after': float(c.get('pause_after', GAP))}
            if shown and c.get('caption', True) is not False:
                new.append(_caption(line, at, shown, actor, c, ch, True))
            bark = c.get('bark', ch.bark)
            if bark:
                snd = {'do': 'sound', 'at': round(at + ws[0]['start'], 4), 'id': bark if isinstance(bark, str) else ch.bark,
                       'volume': ch.bark_volume, 'actor': actor}
                if actor == 'player':
                    snd['relative'] = True
                new.append(snd)
            if r.get('file'):
                voice.append({'file': entry['file'], 'shot': sname, 'at': round(at, 4), 'gain': float(c.get('gain', 0.0))})
            report.append(entry)
        if carry is None:
            carry = onward
        shot['cue'] = new
        if cut is not None:
            dur = cut['frame'] / fps
            late = [cc for cc in new if isinstance(cc.get('at'), (int, float)) and cc['at'] > dur + 1e-9 and cc.get('do') != 'sound']
            if late:
                raise _error(f'{cut["where"]}: the shot now ends on "{cut["word"]}" at {dur:.3f} s, but a {late[0]["do"]} cue is at {late[0]["at"]} s')
            shot['duration'] = dur
            new[:] = [cc for cc in new if not (cc.get('do') == 'sound' and cc['at'] > dur)]
        elif need_end > written:
            shot['duration'] = math.ceil(need_end * fps - 1e-6) / fps
        elif written <= 0 and any(e['shot'] == sname for e in report):
            raise _error(f'shot {sname}: duration = <seconds> is required (its lines have fit = "none")')
    if voice:
        edit['voice'] = voice
    edit['dialogue'] = report
    _table(report, engine, log)
    return raw


LINGER = 0.8   # seconds a finished line's caption stays up after its last word when a cut comes first


def _carry_on(carry, written, more):
    """The carried caption of a fit = "none" line trimmed to the words that start inside this shot; returns the carry
    into the shot after when words remain past this one's end (a line over a run of short shots) or the line ended
    less than LINGER before it (its caption then holds to LINGER after the last word), else None."""
    cap = carry['caption']
    if written <= 0 or not more:
        return None
    k = next((i for i, w in enumerate(cap['words']) if w['at'] >= written - 1e-9), None)
    if k is None and carry['end'] + LINGER <= written + 1e-9:
        return None
    words = cap['words']
    if k is not None:
        cap['words'] = words[:k]
    nxt = {**cap, 'words': [{**w, 'at': round(w['at'] - written, 4)} for w in words]}
    if k is None and 'hold' not in nxt:
        nxt['hold'] = round(carry['end'] - words[-1]['at'] + LINGER, 4)
    return {**carry, 'caption': nxt, 'end': carry['end'] - written}


def _table(report, engine, log):
    log(f'VOICE    {len(report)} line(s), {engine.name}' + ('' if engine.audio else ' (estimated timings, no audio)'))
    for e in report:
        cut = f'  cut on "{e["cut_on"]["word"]}" f{e["cut_on"]["frame"]}' if e.get('cut_on') else ''
        dur = e['words'][-1]['end'] if e['words'] else 0
        timing = e.get('timing') or ''
        log(f'  {e["id"]:<16} {e["character"]:<8} {e["shot"]:<12} at {e["at"]:6.2f}  {dur:5.2f} s  '
            f'{"cached" if e.get("cached") else (e.get("engine") or ""):<8} {timing if timing != "ok" else ""}{cut}')


SPOKEN_MIN = 1.0   # a spoken caption is still up at least this long, first word to last frame (subtitle practice)


def lint_spoken(problems, resolved):
    """Lint's reading rules are for text read without sound (max(1.2 s, 0.5 + 0.3 s a word) after the caption is
    complete, at most 2.5 words a second). A caption the voice speaks is a subtitle: the viewer hears it as it pops,
    so those become notes, unless the caption is up for less than SPOKEN_MIN in all."""
    voiced, line_up = {}, {}
    for shot in resolved.get('shot') or []:
        cues = shot.get('cue') or []
        for k, c in enumerate(cues):
            if c.get('do') == 'caption' and c.get('voiced'):
                later = [x['at'] for x in cues if x.get('do') in ('caption', 'title', 'card', 'lower_third') and x['at'] > c['at']]
                end = min(later + [float(shot.get('duration') or 0)])
                up = end - c['at'] - max(0.0, c['words'][0]['at'])
                voiced[f'shot {shot.get("name")}.cue[{k}]'] = c['voiced']
                line_up[c['voiced']] = line_up.get(c['voiced'], 0.0) + up   # a caption carried over cuts: all its shots
    voiced = {where: line_up[v] for where, v in voiced.items()}
    out = []
    for p in problems:
        up = voiced.get(p.get('where'))
        if up is not None and p.get('rule') in ('reading', 'words_per_second') and up >= SPOKEN_MIN:
            p = {**p, 'severity': 'info', 'message': p['message'] + ' (spoken: the voice carries it)'}
        out.append(p)
    return out
