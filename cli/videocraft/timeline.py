"""Where each shot sits in the master: cut/timeline.json when the edit wrote one, else edit.json's clips and the take's
frame counts (plain hard cuts with trims). Used by measure, review packets and compare. Owned by workstream (d)."""
import json


def clips(it):
    """[{index, kind, shot, src_in, src_out, out_start, out_frames, fade_in, fade_out}] in master frames, in order."""
    timeline = it.cut / 'timeline.json'
    if timeline.exists():
        out = []
        for k, c in enumerate(json.loads(timeline.read_text()).get('clips', [])):
            out.append({'index': c.get('index', k), 'kind': c.get('kind', 'shot'), 'shot': c.get('shot'),
                        'src_in': int(c.get('src_in', 0) or 0), 'src_out': int(c.get('src_out', 0) or 0),
                        'out_start': int(c.get('out_start', 0)), 'out_frames': int(c.get('out_frames', 0)),
                        'fade_in': int(c.get('fade_in', 0) or 0), 'fade_out': int(c.get('fade_out', 0) or 0),
                        'speed': float(c.get('speed') or 1.0)})
        return out
    result = it.result() or {}
    frames = {s['name']: s['frames'] for s in result.get('shots', [])}
    out, at = [], 0
    for k, clip in enumerate(it.edit()['clip']):
        head, tail = clip.get('trim') or [0, 0]
        total = frames.get(clip.get('shot'), 0)
        n = max(0, total - int(head) - int(tail))
        out.append({'index': k, 'kind': 'shot', 'shot': clip.get('shot'), 'src_in': int(head), 'src_out': total - int(tail),
                    'out_start': at, 'out_frames': n, 'fade_in': 0, 'fade_out': 0, 'speed': 1.0})
        at += n
    return out


def boundaries(cl):
    """(hard, soft): master frames where one clip follows another; soft when a fade or black is next to the join."""
    hard, soft = [], []
    for a, b in zip(cl, cl[1:]):
        fade = a['kind'] != 'shot' or b['kind'] != 'shot' or a['fade_out'] or b['fade_in']
        (soft if fade else hard).append(b['out_start'])
    return hard, soft


def timecode(frame, fps):
    seconds = frame / fps
    m, s = divmod(seconds, 60)
    return f'{int(m)}:{s:05.2f}'
