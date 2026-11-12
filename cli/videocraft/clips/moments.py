"""Moments for shorts, found from what the run already knows (nothing here watches the video):

    words and key words    every caption's words (text.json) and voice timings, mapped into master time (timemap)
    marks                  marks.json labels; `payoff`, `punch`, `reveal`, `button` ... count as payoffs
    the outline            stories/<id>/outline.md beats (`## n. name (purpose, ~len, shots a-b)`) and the comedy pass
                           table (joke, beat, how it lands): a beat's start is a setup, a payoff/button beat's end a payoff
    loudness               peaks of the master's short-term level (100 ms RMS) well over its median
    cuts                   the master's own clip boundaries (cut density; where a short may start and end)
    sound events           sounds.csv: a goat's scream, an egg plop, a level-up, a hit; footsteps and ambience do not count
    a reviewer (--ask)     agents.ask over the review packet's contact sheet, the outline and the candidates

A moment is a range that starts on a setup (a beat start, a line start, a shot boundary) and ends on a payoff plus a
beat (BEAT seconds), SHORTEST to LONGEST seconds long, its ends snapped to shot boundaries and word ends (never
mid-word). Candidates are scored, overlapping ones suppressed, and the rest written ranked with their reasons to
clips/moments.json. A master shorter than SHORTEST is one moment: the whole of it.
"""
import fnmatch
import json
import math
import re
import statistics
import subprocess
from array import array
from pathlib import Path

from videocraft import tools
from videocraft.clips import timemap
from videocraft.paths import ROOT

BEAT = 0.8
SHORTEST, LONGEST = 15.0, 60.0
IDEAL = (20.0, 35.0)
# Sound events worth a short (glob on the event id) and their weight; anything else does not count.
SALIENT = [('*goat.screaming*', 3.0), ('*scream*', 2.5), ('*chicken.egg*', 2.5), ('*entity.item.pickup*', 0.3),
           ('*player.levelup*', 2.0), ('*generic.explode*', 2.5), ('*anvil.land*', 2.0), ('*.hurt*', 1.0), ('*.death*', 1.5),
           ('*ui.toast*', 1.0), ('*bell.use*', 1.5), ('*goat.ram_impact*', 2.5), ('*horn*', 1.5), ('*note_block*', 0.25),
           ('*.ambient*', 0.4), ('*.yes*', 0.8), ('*.no*', 0.8), ('*cat.purr*', 0.5), ('*fox.sleep*', 1.0), ('*fox.*', 0.5)]
PAYOFF_MARKS = ('payoff', 'punch', 'reveal', 'button', 'scream', 'laugh', 'joke', 'egg', 'hit', 'end')
SETUP_PURPOSES = ('setup', 'turn', 'escalation', 'flashback')
PAYOFF_PURPOSES = ('payoff', 'button', 'punchline', 'climax')


def salience(event):
    for pattern, weight in SALIENT:
        if fnmatch.fnmatch(event, pattern):
            return weight
    return 0.0


# ---- The outline ----

BEAT_RE = re.compile(r'^##\s*(\d+)\.\s*(.+?)\s*(?:\((.*)\))?\s*$')


def parse_outline(text):
    """{beats: [{n, name, purpose, length, shots: (a, b) or None, jokes: []}], jokes: [{joke, beat, lands, pair}]}."""
    beats, jokes = [], []
    for line in text.splitlines():
        m = BEAT_RE.match(line.strip())
        if m:
            inner = m.group(3) or ''
            parts = [p.strip() for p in inner.split(',')]
            shots = re.search(r'shots?\s+(\d+)\s*(?:-|–|to)\s*(\d+)', inner) or re.search(r'shots?\s+(\d+)', inner)
            length = re.search(r'~\s*([\d.]+)\s*s', inner)
            beats.append({'n': int(m.group(1)), 'name': m.group(2).strip(), 'purpose': parts[0].lower() if parts and parts[0] else '',
                          'length': float(length.group(1)) if length else None,
                          'shots': (int(shots.group(1)), int(shots.group(2) if shots.lastindex and shots.lastindex > 1 else shots.group(1))) if shots else None,
                          'jokes': []})
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip('|').split('|')] if line.strip().startswith('|') else []
        if len(cells) >= 2 and cells[1].isdigit():
            joke = {'joke': cells[0], 'beat': int(cells[1]), 'lands': cells[2] if len(cells) > 2 else '', 'pair': cells[3] if len(cells) > 3 else ''}
            jokes.append(joke)
            for b in beats:
                if b['n'] == joke['beat']:
                    b['jokes'].append(joke['joke'])
    return {'beats': beats, 'jokes': jokes}


def shot_for_number(plan_shots, number):
    """The plan's shot for an outline shot number: a name carrying that number (s19, 19-brag, shot-19), else the n-th."""
    for s in plan_shots:
        nums = re.findall(r'\d+', s['name'])
        if nums and int(nums[0]) == number:
            return s['name']
    return plan_shots[number - 1]['name'] if 0 < number <= len(plan_shots) else None


def outline_of(run):
    """(outline dict, path) of the story a run was made from: stories/<name>/outline.md, or None."""
    name = Path(run).parent.name
    for candidate in (name, re.sub(r'-(vertical|v)$', '', name)):
        f = ROOT / 'stories' / candidate / 'outline.md'
        if f.exists():
            return parse_outline(f.read_text()), f
    return None, None


# ---- Events in master time ----

def _csv(path):
    import csv
    try:
        with open(path, newline='') as fh:
            return list(csv.DictReader(fh))
    except OSError:
        return []


def events(m):
    """Every signal, as {t, kind, weight, what, (end)} in master seconds, sorted. Kinds: line, key, sound, mark, peak,
    beat_start, beat_end, joke."""
    out = []
    words = timemap.words(m)
    lines = {}
    for w in words:
        lines.setdefault(w.line, []).append(w)
    for line, ws in lines.items():
        text = ' '.join(w.text for w in ws)
        out.append({'t': ws[0].start, 'end': ws[-1].end, 'kind': 'line', 'weight': 0.5, 'what': text})
        for w in ws:
            if w.key:
                out.append({'t': w.start, 'end': w.end, 'kind': 'key', 'weight': 1.0, 'what': f'key word "{w.text}" ({text[:40]})'})
    seen = set()
    for s in m.segments:
        if s.kind != 'shot' or (s.run, s.shot) in seen or not s.run:
            continue
        seen.add((s.run, s.shot))
        d = timemap.shot_dir(s)
        for row in _csv(d / 'sounds.csv'):
            weight = salience(row.get('event', ''))
            if weight <= 0:
                continue
            for t in m.to_master(s.run, s.shot, int(row['frame'])):
                out.append({'t': t, 'kind': 'sound', 'weight': weight, 'what': row['event'].replace('minecraft:', '')})
        marks = timemap._json(d / 'marks.json') or []
        for mark in marks if isinstance(marks, list) else []:
            label = str(mark.get('label', ''))
            for t in m.to_master(s.run, s.shot, int(mark.get('frame', 0))):
                payoff = any(k in label.lower() for k in PAYOFF_MARKS)
                out.append({'t': t, 'kind': 'mark', 'weight': 1.5 if payoff else 0.2, 'what': f'mark "{label}"', 'payoff': payoff})
    out += beat_events(m)
    for t, db in peaks(m):
        out.append({'t': t, 'kind': 'peak', 'weight': 0.6, 'what': f'loudness peak {db:+.1f} dB over the median'})
    return sorted(out, key=lambda e: e['t'])


def beat_events(m):
    out = []
    runs = []
    for s in m.segments:
        if s.run and s.run not in runs and s.kind == 'shot':
            runs.append(s.run)
    for run in runs:
        outline, _ = outline_of(run)
        if not outline:
            continue
        try:
            plan_shots = json.loads((Path(run) / 'plan.json').read_text())['shots']
        except (OSError, ValueError, KeyError):
            continue
        for beat in outline['beats']:
            if not beat['shots']:
                continue
            names = {shot_for_number(plan_shots, n) for n in range(beat['shots'][0], beat['shots'][1] + 1)} - {None}
            times = [(sg.out_start / m.fps, sg.out_end / m.fps) for sg in m.segments if sg.run == run and sg.shot in names]
            if not times:
                continue
            a, b = min(t[0] for t in times), max(t[1] for t in times)
            purpose = beat['purpose']
            setup = any(p in purpose for p in SETUP_PURPOSES)
            payoff = any(p in purpose for p in PAYOFF_PURPOSES)
            out.append({'t': a, 'end': b, 'kind': 'beat_start', 'weight': 1.5 if setup else 0.8, 'what': f'beat {beat["n"]} "{beat["name"]}" ({purpose}) starts',
                        'beat': beat['n'], 'name': beat['name'], 'setup': setup or payoff})
            out.append({'t': b, 'kind': 'beat_end', 'weight': 2.0 if payoff else 0.8, 'what': f'beat {beat["n"]} "{beat["name"]}" ({purpose}) ends',
                        'beat': beat['n'], 'name': beat['name'], 'payoff': payoff})
            for joke in beat['jokes']:
                out.append({'t': a, 'end': b, 'kind': 'joke', 'weight': 2.0, 'what': f'joke "{joke}" (beat {beat["n"]})', 'beat': beat['n'], 'name': joke})
    return out


def envelope(path, rate=4000, step=0.1):
    """Short-term level of a file's audio: [dB] every `step` seconds (RMS over the step), or [] without audio."""
    p = subprocess.run([tools.ffmpeg(), '-v', 'error', '-i', str(path), '-vn', '-ac', '1', '-ar', str(rate), '-f', 's16le', '-'],
                       capture_output=True)
    if p.returncode != 0 or not p.stdout:
        return []
    a = array('h')
    a.frombytes(p.stdout[:len(p.stdout) // 2 * 2])
    n = int(rate * step)
    out = []
    for i in range(0, len(a) - n + 1, n):
        chunk = a[i:i + n]
        ms = sum(v * v for v in chunk) / n
        out.append(10 * math.log10(ms / 32768.0 ** 2 + 1e-12))
    return out


def peak_times(levels, step=0.1, over=8.0, gap=1.0):
    """(t, dB over the median) of local maxima at least `over` dB above the median level of the non-silent steps,
    at least `gap` seconds apart (the louder wins)."""
    voiced = [v for v in levels if v > -60]
    if len(voiced) < 5:
        return []
    med = statistics.median(voiced)
    found = []
    for i in range(1, len(levels) - 1):
        v = levels[i]
        if v - med >= over and v >= levels[i - 1] and v >= levels[i + 1]:
            found.append((i * step, v - med))
    found.sort(key=lambda p: -p[1])
    kept = []
    for t, d in found:
        if all(abs(t - k) >= gap for k, _ in kept):
            kept.append((t, d))
    return sorted(kept)


def peaks(m):
    master = getattr(m, 'master', None)
    if not master or not Path(master).exists():
        return []
    return peak_times(envelope(master))


# ---- Candidates ----

def candidates(evs, cuts, words, total, shortest=SHORTEST, longest=LONGEST, beat=BEAT):
    """Every (start, end) from a setup to a payoff plus a beat, snapped (never mid-word), within the length limits."""
    payoffs = [e for e in evs if e['kind'] in ('key', 'sound', 'peak', 'beat_end') or (e['kind'] == 'mark' and e.get('payoff'))]
    starts = {0.0} | {round(c, 4) for c in cuts if c < total} | {round(e['t'], 4) for e in evs if e['kind'] in ('beat_start', 'line')}
    out = set()
    for p in payoffs:
        end_at = p.get('end', p['t']) if p['kind'] == 'key' else p['t']
        e = timemap.snap_end(min(total, end_at + beat), cuts, words, ceiling=total)
        for s0 in starts:
            s = timemap.snap_start(s0, cuts, words)
            if shortest - 1e-6 <= e - s <= longest + 1e-6:
                out.add((round(s, 4), round(e, 4)))
    return sorted(out)


def score(start, end, evs, cuts, ideal=IDEAL):
    """(score, reasons) of one range: what it holds, how it starts and ends, how busy it is, how long."""
    length = end - start
    inside = [e for e in evs if start - 1e-6 <= e['t'] <= end + 1e-6]
    reasons, total = [], 0.0
    content = sum(e['weight'] for e in inside if e['kind'] not in ('beat_start', 'beat_end', 'line', 'joke'))
    content += sum(0.5 for e in inside if e['kind'] == 'line')
    jokes = [e for e in evs if e['kind'] == 'joke' and start - 0.5 <= e['t'] and e.get('end', e['t']) <= end + 0.5]
    content += sum(e['weight'] for e in jokes)
    total += content / math.sqrt(max(1.0, length / 10))
    if jokes:
        reasons.append('holds ' + ', '.join(e['name'] for e in jokes))
    # The ending: the strongest payoff in the last 1.5 s.
    tail = [e for e in inside if e['t'] >= end - BEAT - 0.7 and e['kind'] in ('key', 'sound', 'peak', 'beat_end', 'mark')]
    if tail:
        best = max(tail, key=lambda e: e['weight'])
        total += 1.5 * best['weight']
        reasons.append(f'ends on {best["what"]} plus a beat')
    else:
        reasons.append('ends without a payoff in its last second')
        total -= 1.0
    head = [e for e in evs if abs(e['t'] - start) < 0.25 and e['kind'] in ('beat_start', 'line')]
    setups = [e for e in head if e['kind'] == 'beat_start' and e.get('setup')]
    if setups:
        total += 1.5
        reasons.append(f'starts on {setups[0]["what"]}')
    elif head:
        total += 0.5
        reasons.append(f'starts on a line: "{head[0]["what"][:40]}"')
    if any(abs(c - start) < 1e-3 for c in cuts):
        total += 0.3
    n_cuts = sum(1 for c in cuts if start + 1e-3 < c < end - 1e-3)
    density = n_cuts / max(1.0, length)
    total += min(1.0, density * 2.0)
    if n_cuts:
        reasons.append(f'{n_cuts} cuts ({density:.2f} a second)')
    keys = [e for e in inside if e['kind'] == 'key']
    sounds = [e for e in inside if e['kind'] == 'sound' and e['weight'] >= 1.0]
    if keys:
        reasons.append(f'{len(keys)} key word(s): ' + ', '.join(sorted({e["what"].split('"')[1] for e in keys}))[:60])
    if sounds:
        reasons.append('sounds: ' + ', '.join(sorted({e['what'] for e in sounds}))[:60])
    if length > ideal[1]:
        total -= (length - ideal[1]) / 15
    elif length < ideal[0]:
        total -= (ideal[0] - length) / 20
    return round(total, 3), reasons


def overlap(a, b):
    lo, hi = max(a[0], b[0]), min(a[1], b[1])
    return max(0.0, hi - lo) / max(1e-6, min(a[1] - a[0], b[1] - b[0]))


def rank(cands, evs, cuts, keep=10, most_overlap=0.5):
    scored = sorted(((score(s, e, evs, cuts), s, e) for s, e in cands), key=lambda x: (-x[0][0], x[1]))
    kept = []
    for (sc, reasons), s, e in scored:
        if all(overlap((s, e), (k['start'], k['end'])) <= most_overlap for k in kept):
            kept.append({'start': s, 'end': e, 'seconds': round(e - s, 3), 'score': sc, 'reasons': reasons})
        if len(kept) >= keep:
            break
    return kept


def title_of(moment, evs):
    """A working title: the joke or beat it holds, else its last key line."""
    inside = [e for e in evs if moment['start'] - 0.5 <= e['t'] <= moment['end'] + 0.5]
    jokes = [e for e in inside if e['kind'] == 'joke' and e.get('end', e['t']) <= moment['end'] + 0.5]
    if jokes:
        return max(jokes, key=lambda e: e['t'])['name']
    beats = [e for e in inside if e['kind'] == 'beat_start']
    if beats:
        return beats[-1]['name']
    lines = [e for e in inside if e['kind'] == 'line']
    keyed = [e for e in lines if any(k['kind'] == 'key' and k['t'] >= e['t'] and k['t'] <= e.get('end', e['t']) for k in inside)]
    pick = (keyed or lines)
    return pick[-1]['what'] if pick else 'Moment'


def cold(moment, evs, cuts, total):
    """Whether a moment starts cold: not at the start of the video and not on a beat that sets something up."""
    if moment['start'] < 0.05:
        return False
    return not any(e['kind'] == 'beat_start' and e.get('setup') and abs(e['t'] - moment['start']) < 0.3 for e in evs)


def hook_of(moment, evs):
    """The hook card text for a cold start: the beat or joke it pays off, short."""
    name = title_of(moment, evs)
    words = re.sub(r'[*"]', '', name).split()
    return ' '.join(words[:6])


def find(it, shortest=SHORTEST, longest=LONGEST, ask=False, model=None, say=print, keep=10):
    m = timemap.load(it)
    m.master = it.cut / 'master.mp4'
    evs = events(m)
    words = timemap.words(m)
    cuts = m.boundaries()
    total = m.seconds
    if total < shortest + 1e-6:
        s = 0.0
        e = timemap.snap_end(total, cuts, words, ceiling=total)
        sc, reasons = score(s, e, evs, cuts)
        found = [{'start': s, 'end': e, 'seconds': round(e - s, 3), 'score': sc, 'reasons': [f'the whole master ({total:.2f} s is under {shortest:g} s)'] + reasons}]
    else:
        found = rank(candidates(evs, cuts, words, total, shortest, longest), evs, cuts, keep=keep)
    for n, mo in enumerate(found, 1):
        mo['n'] = n
        mo['title'] = title_of(mo, evs)
        mo['cold'] = cold(mo, evs, cuts, total)
        mo['hook'] = hook_of(mo, evs) if mo['cold'] else None
        mo['frames'] = list(timemap.frame_range(mo['start'], mo['end'], m.fps))
        mo['shots'] = sorted({(sg.part, sg.shot) for sg, *_ in timemap.sub_timeline(m.segments, *mo['frames']) if sg.shot},
                             key=lambda p: (p[0] or 0, p[1]))
        mo['shots'] = [s for _, s in mo['shots']]
    review = None
    if ask and found:
        review = ask_reviewer(it, found, evs, model, say)
    data = {'run': str(it.path), 'fps': m.fps, 'seconds': total, 'shortest': shortest, 'longest': longest, 'beat': BEAT,
            'signals': {k: sum(1 for e in evs if e['kind'] == k) for k in sorted({e['kind'] for e in evs})},
            'moments': found, 'reviewer': review, 'events': [{k: (round(v, 3) if isinstance(v, float) else v) for k, v in e.items()} for e in evs]}
    out = it.path / 'clips'
    out.mkdir(exist_ok=True)
    (out / 'moments.json').write_text(json.dumps(data, indent=1) + '\n')
    return data


def ask_reviewer(it, found, evs, model, say):
    """One model pass: the contact sheet (when a review packet exists), the outline and the candidates; it re-scores
    each candidate 1-10 and may rename it. Its scores are blended into the ranking (half weight)."""
    from videocraft import agents
    if not agents.backend():
        say('  --ask: no model (claude on PATH or ANTHROPIC_API_KEY); ranked without a reviewer')
        return None
    images = sorted((it.review / 'packet').glob('contact*.png'))[:4] if (it.review / 'packet').exists() else []
    outline = None
    for s in timemap.load(it).segments:
        if s.run:
            o, path = outline_of(s.run)
            if path:
                outline = Path(path).read_text()
                break
    lines = [f'#{m["n"]} {m["start"]:.2f}-{m["end"]:.2f} s: {m["title"]}; ' + '; '.join(m['reasons']) for m in found]
    prompt = ('You pick moments of a finished video to cut as vertical shorts (15-60 s, a setup and its payoff, watched '
              'silent first). You see only stills (if any) and text, not the video; say so if it matters.\n\n'
              + (f'The story outline:\n{outline}\n\n' if outline else '')
              + 'Candidates (seconds in the master):\n' + '\n'.join(lines)
              + '\n\nScore each candidate 1-10 as a short, give a better title (at most 8 words) and a hook line for the '
                'first second (at most 6 words). Answer JSON: {"moments": [{"n", "score", "title", "hook", "why"}]}.')
    schema = {'type': 'object', 'properties': {'moments': {'type': 'array', 'items': {'type': 'object', 'properties': {
        'n': {'type': 'integer'}, 'score': {'type': 'number'}, 'title': {'type': 'string'}, 'hook': {'type': 'string'},
        'why': {'type': 'string'}}, 'required': ['n', 'score']}}}, 'required': ['moments']}
    try:
        text = agents.ask(prompt, images=images, schema=schema, model=model, timeout=900)
        from videocraft.review.reviews import extract_json
        answer = extract_json(text)
    except Exception as e:  # the ranking stands without the reviewer
        say(f'  --ask: the reviewer failed ({type(e).__name__}: {e}); ranked without it')
        return {'error': str(e)}
    by_n = {int(r['n']): r for r in answer.get('moments', []) if 'n' in r}
    for m in found:
        r = by_n.get(m['n'])
        if r:
            m['reviewer'] = r
            m['score'] = round(m['score'] + 0.5 * float(r.get('score', 0)), 3)
            m['reasons'].append(f'reviewer {r.get("score")}/10: {r.get("why", "")[:80]}')
            if r.get('title'):
                m['title'] = r['title']
            if r.get('hook') and m['cold']:
                m['hook'] = r['hook']
    found.sort(key=lambda m: -m['score'])
    for n, m in enumerate(found, 1):
        m['n'] = n
    return {'model': agents.model_name(model), 'images': [str(p) for p in images], 'answer': answer}
