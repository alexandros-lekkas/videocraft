"""Dialogue pace on a timeline: words a second per line, how much of the runtime has a voice, and dead air.

Shared by lint (on the script's own timeline, before a take) and measure (on the cut: cut/audio.json places each
line, cut/timeline.json gives clips and black). Standard library only.

    lines     [{id, character, shot, start, end, words, wps, beat, style}]: start/end are the first word's onset and
              the last word's end on the timeline (seconds)
    segments  [{start, end, kind ('shot' | 'black'), shot}]: the timeline's pieces in order
    dialogue  the shots that have a line in them (a line's own shot and the shot a cut-on line carries into)

Dead air is a silence longer than DEAD_AIR between two lines when everything under it is a dialogue shot: not over a
black gap, not across a shot without lines (an action beat), and not before a line marked `beat = true`.
"""
SLOW_WPS = 2.6        # a voiced line slower than this is slow (lint warns; the default pace is 3.2)
DEAD_AIR = 0.8        # seconds without a voice inside a run of dialogue
MIN_WORDS = 3         # shorter lines have no meaningful rate
SLOW_STYLES = ('deadpan', 'sleepy', 'sad')


def wps(words):
    if not words:
        return None
    span = words[-1]['end'] - words[0]['start']
    return round(len(words) / span, 3) if span > 0 else None


def union(intervals):
    out = []
    for s, e in sorted(intervals):
        if out and s <= out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return out


def silences(lines, segments, dialogue):
    """Every gap between voices from the first line to the last: {start, end, seconds, after, before, excused}."""
    if not lines:
        return []
    order = sorted(lines, key=lambda l: l['start'])
    out, end, prev = [], order[0]['end'], order[0]
    for l in order[1:]:
        if l['start'] > end + 1e-6:
            gap = {'start': round(end, 3), 'end': round(l['start'], 3), 'seconds': round(l['start'] - end, 3),
                   'after': prev['id'], 'before': l['id'], 'excused': None}
            under = [s for s in segments if s['start'] < l['start'] - 1e-6 and s['end'] > end + 1e-6]
            if l.get('beat'):
                gap['excused'] = 'beat'
            elif any(s['kind'] == 'black' for s in under):
                gap['excused'] = 'black'
            elif any(s['kind'] == 'shot' and s.get('shot') not in dialogue for s in under):
                gap['excused'] = 'not dialogue'
            out.append(gap)
        if l['end'] > end:
            end, prev = l['end'], l
    return out


def dead_air(lines, segments, dialogue, limit=DEAD_AIR):
    return [g for g in silences(lines, segments, dialogue) if g['seconds'] > limit and not g['excused']]


def slow(lines, limit=SLOW_WPS):
    """Lines of MIN_WORDS or more under `limit` words a second; a slow style is listed with slow_style = True."""
    out = []
    for l in lines:
        if l.get('words', 0) >= MIN_WORDS and l.get('wps') is not None and l['wps'] < limit:
            out.append({**l, 'slow_style': l.get('style') in SLOW_STYLES})
    return out


def summary(lines, segments, dialogue, total):
    """For metrics.json: per-line rate, voice share of the runtime, the longest silences, dead air."""
    voiced = sum(e - s for s, e in union([(l['start'], l['end']) for l in lines]))
    gaps = silences(lines, segments, dialogue)
    rates = [l['wps'] for l in lines if l.get('wps') is not None and l.get('words', 0) >= MIN_WORDS]
    return {'lines': [{k: l.get(k) for k in ('id', 'character', 'shot', 'start', 'end', 'words', 'wps', 'beat', 'style')} for l in lines],
            'voice_seconds': round(voiced, 3), 'runtime': round(total, 3),
            'voice_share': round(voiced / total, 3) if total else None,
            'median_wps': round(sorted(rates)[len(rates) // 2], 3) if rates else None,
            'lead_in': round(min(l['start'] for l in lines), 3) if lines else None,
            'longest_silences': sorted(gaps, key=lambda g: -g['seconds'])[:5],
            'dead_air': [g for g in gaps if g['seconds'] > DEAD_AIR and not g['excused']],
            'slow_lines': [{'id': l['id'], 'wps': l['wps'], 'slow_style': l['slow_style']} for l in slow(lines)]}


# --- the script's own timeline (lint) ------------------------------------------------------------------------------

def script_timeline(resolved, fps=60):
    """(segments, shot_start) for a resolved script: its [[edit.clip]] in order (black clips as black; trims in frames
    taken off, other in/out keys ignored) or every shot in script order. shot_start[name] = (timeline start of the
    shot's first clip, its head trim in seconds)."""
    shots = {s.get('name'): s for s in resolved.get('shot') or []}
    clips = (resolved.get('edit') or {}).get('clip') or [{'shot': n} for n in shots]
    segments, starts, t = [], {}, 0.0
    for c in clips:
        if 'black' in c and 'shot' not in c:
            d = float(c.get('black') or 0)
            segments.append({'start': t, 'end': t + d, 'kind': 'black', 'shot': None})
            t += d
            continue
        s = shots.get(c.get('shot'))
        if s is None:
            continue
        dur = float(s.get('duration') or 0)
        head, tail = 0.0, 0.0
        trim = c.get('trim')
        if isinstance(trim, list) and len(trim) == 2:
            head, tail = (float(x) / fps if isinstance(x, int) else float(x) for x in trim)
        length = max(0.0, dur - head - tail)
        segments.append({'start': t, 'end': t + length, 'kind': 'shot', 'shot': s.get('name')})
        starts.setdefault(s.get('name'), (t, head))
        t += length
    return segments, starts, t


def script_lines(resolved, fps=60):
    """(lines, segments, dialogue shots, runtime) from a resolved script's edit.dialogue."""
    segments, starts, total = script_timeline(resolved, fps)
    lines, dialogue = [], set()
    for d in (resolved.get('edit') or {}).get('dialogue') or []:
        if d.get('shot') not in starts or not d.get('words'):
            continue
        t0, head = starts[d['shot']]
        base = t0 + float(d['at']) - head
        dialogue.add(d['shot'])
        if d.get('carried_to'):
            dialogue.add(d['carried_to'])
        lines.append({'id': d['id'], 'character': d.get('character'), 'shot': d['shot'],
                      'start': round(base + d['words'][0]['start'], 3), 'end': round(base + d['words'][-1]['end'], 3),
                      'words': len(d['words']), 'wps': d.get('wps') if d.get('wps') is not None else wps(d['words']),
                      'beat': bool(d.get('beat')), 'style': d.get('style')})
    return lines, segments, dialogue, total
