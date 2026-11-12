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
  none     the duration is left as written

A `say` without `at` follows the previous line of its shot after its `pause_after` (0.2 s). The lines and their
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

SAY_KEYS = {'do', 'at', 'actor', 'character', 'text', 'style', 'speed', 'pause_after', 'fit', 'cut_on', 'tail', 'gain',
            'caption', 'speaker', 'bark', 'id', 'position', 'size', 'hold', 'shade', 'key_color', 'color', 'carry'}
CAPTION_KEYS = ('position', 'size', 'hold', 'shade', 'key_color', 'color')
FITS = ('extend', 'cut-on', 'none')
TAIL = 0.25
PAUSE_AFTER = 0.2


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
            try:
                ch = cast.character(cid)
                spec = ch.spec(tokens, cue.get('style'), cue.get('speed', 1.0), cast.styles, draft=draft)
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


def _caption(line, at, words, actor, cue, ch, first):
    """A caption cue for `words` [(display, start)] at shot time `at`."""
    cap = {'do': 'caption', 'at': round(at, 4), 'actor': actor, 'voiced': line.cue.get('id') or line.where,
           'words': [{'w': d, 'at': round(max(0.0, s), 4)} for d, s in words]}
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
    for si, shot in enumerate(shots):
        sname = shot.get('name')
        new, prev_end, need_end, cut = [], None, 0.0, None
        if carry:
            new.append(carry['caption'])
            need_end = max(need_end, carry['end'] + carry['tail'])
            prev_end = carry['end'] + carry['pause_after']   # a line without `at` waits for the carried words
            carry['entry']['carried_to'] = sname
            carry = None
        n = 0
        for cue in shot.get('cue') or []:
            if not (isinstance(cue, dict) and cue.get('do') == 'say'):
                new.append(cue)
                continue
            line = queue.pop(0)
            c, ch, r = line.cue, line.character, line.result
            n += 1
            at = float(c['at']) if 'at' in c else (prev_end if prev_end is not None else 0.0)
            ws = r['words']
            end = at + ws[-1]['end']
            prev_end = end + float(c.get('pause_after', PAUSE_AFTER))
            tail = float(c.get('tail', TAIL))
            actor = c['actor'] if c.get('actor') in actors else 'player'
            fit = c.get('fit', 'extend')
            words = [(d, w['start']) for d, w in zip(line.display, ws)]
            entry = {'id': c.get('id') or f'{sname}-{n}', 'character': ch.id, 'shot': sname, 'at': round(at, 4),
                     'start_frame': round(at * fps), 'text': c['text'], 'style': c.get('style'), 'fit': fit,
                     'file': front.rel(r['file']) if r.get('file') else None, 'seconds': r.get('seconds'),
                     'engine': r.get('engine'), 'timing': r.get('timing'), 'cached': r.get('cached'), 'key': r.get('key'),
                     'voice': ch.voice if not ch.generic else f'{ch.voice} (generic)',
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
                                 'pause_after': float(c.get('pause_after', PAUSE_AFTER))}
                        carry['caption']['words'][0]['at'] = 0.0
            elif fit == 'extend':
                need_end = max(need_end, end + tail)
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
        shot['cue'] = new
        written = float(shot.get('duration') or 0)
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
    voiced = {}
    for shot in resolved.get('shot') or []:
        cues = shot.get('cue') or []
        for k, c in enumerate(cues):
            if c.get('do') == 'caption' and c.get('voiced'):
                later = [x['at'] for x in cues if x.get('do') in ('caption', 'title', 'card', 'lower_third') and x['at'] > c['at']]
                end = min(later + [float(shot.get('duration') or 0)])
                voiced[f'shot {shot.get("name")}.cue[{k}]'] = end - c['at'] - c['words'][0]['at']
    out = []
    for p in problems:
        up = voiced.get(p.get('where'))
        if up is not None and p.get('rule') in ('reading', 'words_per_second') and up >= SPOKEN_MIN:
            p = {**p, 'severity': 'info', 'message': p['message'] + ' (spoken: the voice carries it)'}
        out.append(p)
    return out
