"""Text on screen against the layout rules of docs/DESIGN.md section 5, from each shot's text.json.

What is read (the text workstream writes it; these spellings and a few obvious variants are accepted):

    {"width": 1920, "height": 1080, "fps": 60,
     "items": [{"kind": "caption", "text": "Hey. It's me. Nibs.", "start": 12, "end": 140,   # frames, end exclusive
                "box": [x, y, w, h],                                                         # pixels of the frame
                "cap_height": 58,                                                            # pixels
                "words": [{"w": "Hey.", "frame": 12}, ...]}]}                                # when each word appears

Frames are the shot's own. Rules, all at the frame's own size (the 1920x1080 numbers scale with the frame):
safe area x 5-95 %, y 5-85 % (96-1824, 54-918); one message at a time; complete on screen (from its last word)
for at least max(1.2 s, 0.5 s + 0.3 s a word); capital height at least 44 px at 1920 wide; at most 2.5 words a
second over the time it is on screen. One-word items under the reading time are listed apart (montage words).
"""
import json
from pathlib import Path

SAFE = (96 / 1920, 54 / 1080, 1824 / 1920, 918 / 1080)
CAP_MIN = 44
WPS_MAX = 2.5


def reading_seconds(words):
    return max(1.2, 0.5 + 0.3 * words)


def _get(d, *names, default=None):
    for n in names:
        if n in d:
            return d[n]
    return default


def normalise(item, fps):
    start = _get(item, 'start', 'from', 'first')
    end = _get(item, 'end', 'to', 'last')
    if 'frames' in item and isinstance(item['frames'], list) and len(item['frames']) == 2:
        start, end = item['frames']
    box = _get(item, 'box', 'rect', default=None)
    if isinstance(box, dict):
        box = [box.get('x', 0), box.get('y', 0), box.get('w', box.get('width', 0)), box.get('h', box.get('height', 0))]
    words = []
    for w in _get(item, 'words', default=[]) or []:
        if isinstance(w, dict):
            frame = _get(w, 'frame', 'start', 'at_frame')
            if frame is None and 'at' in w:
                frame = (start or 0) + round(float(w['at']) * fps)
            words.append((str(_get(w, 'w', 'word', 'text', default='')), int(frame if frame is not None else start or 0)))
        else:
            words.append((str(w), int(start or 0)))
    text = _get(item, 'text', default=' '.join(w for w, _ in words))
    if isinstance(text, list):
        text = ' '.join(text)
    count = len(words) or len(str(text).split())
    complete = max((f for _, f in words), default=start)
    return {'kind': _get(item, 'kind', 'type', default='text'), 'text': str(text), 'start': int(start or 0), 'end': int(end or 0),
            'box': box, 'cap': _get(item, 'cap_height', 'capHeight', 'cap'), 'words': words, 'count': count,
            'complete': int(complete or 0)}


def load(path, fps):
    data = json.loads(Path(path).read_text())
    items = data if isinstance(data, list) else _get(data, 'items', 'text', default=[])
    size = (data.get('width'), data.get('height')) if isinstance(data, dict) else (None, None)
    return [normalise(i, fps) for i in items], size


def check(items, fps, width=1920, height=1080, shot=None):
    """Violations of every rule, and a per-item table. Each violation names the shot, the frame and the text."""
    scale = width / 1920
    safe = (SAFE[0] * width, SAFE[1] * height, SAFE[2] * width, SAFE[3] * height)
    table, problems = [], []

    def problem(rule, item, detail):
        problems.append({'rule': rule, 'shot': shot, 'frame': item['start'], 't': round(item['start'] / fps, 3),
                         'text': item['text'][:60], 'detail': detail})

    for it in items:
        on = (it['end'] - it['start']) / fps
        complete = (it['end'] - it['complete']) / fps
        need = reading_seconds(it['count'])
        wps = it['count'] / on if on > 0 else float('inf')
        row = {'shot': shot, 'kind': it['kind'], 'text': it['text'], 'start': it['start'], 'end': it['end'], 'seconds': round(on, 3),
               'complete_seconds': round(complete, 3), 'reading_seconds': round(need, 3), 'words': it['count'],
               'words_per_second': round(wps, 3), 'cap_height': it['cap'], 'box': it['box']}
        table.append(row)
        if complete + 1e-9 < need:
            problem('reading_one_word' if it['count'] == 1 else 'reading', it,
                    f'complete for {complete:.2f} s, needs {need:.2f} s ({it["count"]} words)')
        if it["count"] > 1 and wps > WPS_MAX + 1e-9:
            problem('words_per_second', it, f'{wps:.2f} words/s over {on:.2f} s (at most {WPS_MAX})')
        if it['cap'] is not None and float(it['cap']) < CAP_MIN * scale - 1e-9:
            problem('cap_height', it, f'capital height {it["cap"]} px, at least {CAP_MIN * scale:.0f} px at this width')
        if it['box']:
            x, y, w, h = it['box']
            if x < safe[0] or y < safe[1] or x + w > safe[2] or y + h > safe[3]:
                problem('safe_area', it, f'box {x},{y} {w}x{h} leaves the safe area x {safe[0]:.0f}-{safe[2]:.0f}, y {safe[1]:.0f}-{safe[3]:.0f}')
    ordered = sorted(items, key=lambda i: i['start'])
    for a, b in zip(ordered, ordered[1:]):
        if b['start'] < a['end']:
            problem('one_message', b, f'on screen with "{a["text"][:40]}" for {(a["end"] - b["start"]) / fps:.2f} s')
    return table, problems
