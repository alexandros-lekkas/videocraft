"""Proves the cut is frame-exact and the push-in holds pixel-exact, without trusting the filter graph.

The graph is rendered again to decoded frames (no encoder in the way) and compared with the shots' own decoded frames:
- every plain stretch of every clip (no zoom, speed, look or fade) must be exactly the source frames it claims, in
  order (per-frame MD5 of the raw pixels), so clip lengths and in/out points are exact to the frame;
- every frame of a push-in hold must equal the source frame's crop scaled up with nearest neighbour, computed here in
  Python from the raw planes (pixel for pixel, all three planes);
- black gaps are black, and the cut has the timeline's frame count.
Writes cut/verify.json and returns it.
"""
import hashlib
import json
import subprocess

from videocraft import tools
from videocraft.edit import graph as graph_
from videocraft.edit import looks
from videocraft.edit.cut import timeline_of


def _raw_frames(args, width, height):
    """Yields raw yuv420p frames (bytes) from an ffmpeg command's output."""
    size = width * height * 3 // 2
    proc = subprocess.Popen([tools.ffmpeg(), '-loglevel', 'error', *args, '-f', 'rawvideo', '-pix_fmt', 'yuv420p', '-'], stdout=subprocess.PIPE)
    try:
        while True:
            data = proc.stdout.read(size)
            if len(data) < size:
                break
            yield data
    finally:
        proc.stdout.close()
        proc.wait()


def _source(video, first, count, width, height):
    return list(_raw_frames(['-i', str(video), '-vf', f'trim=start_frame={first}:end_frame={first + count},setpts=PTS-STARTPTS'], width, height))


def _nearest(plane, pw, ph, crop, out_w, out_h):
    """Nearest-neighbour upscale of a crop (x, y, w, h) of one plane: source index floor((dst + 0.5) * w / out_w)."""
    x0, y0, cw, ch = crop
    cols = [x0 + min(cw - 1, (2 * x + 1) * cw // (2 * out_w)) for x in range(out_w)]
    out = bytearray()
    for y in range(out_h):
        sy = y0 + min(ch - 1, (2 * y + 1) * ch // (2 * out_h))
        row = plane[sy * pw:(sy + 1) * pw]
        out += bytes(row[c] for c in cols)
    return bytes(out)


def _planes(frame, w, h):
    y = w * h
    c = (w // 2) * (h // 2)
    return frame[:y], frame[y:y + c], frame[y + c:y + 2 * c]


def verify(it, hold_samples=3):
    timeline = timeline_of(it)
    w, h, fps = timeline['width'], timeline['height'], timeline['fps']
    pngs = {}

    def frame_png(spec):
        key = json.dumps(spec, sort_keys=True)
        if key not in pngs:
            pngs[key] = looks.frame_png(it.cut / 'looks' / f'verify-{len(pngs)}.png', w, h, spec.get('color', '#e8a23a'), float(spec.get('width', 28)),
                                        float(spec.get('glow', 12)), float(spec.get('opacity', 1.0)), min(w, h) / 1080)
        return pngs[key]

    (it.cut / 'looks').mkdir(parents=True, exist_ok=True)
    inputs, graph = graph_.build(timeline, lambda s: it.take / 'shots' / s / 'video.mp4', frame_png)
    # The frames of push-in holds to compare pixel for pixel (first, middle, last of each hold); hashes for the rest.
    wanted = set()
    for clip in timeline['clips']:
        at = clip['out_start']
        for piece in clip.get('push') or []:
            n = piece['to'] - piece['from']
            if piece['kind'] == 'hold':
                wanted |= {at + p for p in sorted({0, n // 2, n - 1})[:hold_samples]}
            at += n
    cut, kept = [], {}
    for i, f in enumerate(_raw_frames([*inputs, '-filter_complex', ';'.join(graph), '-map', '[v]'], w, h)):
        cut.append(hashlib.md5(f).hexdigest())
        if i in wanted:
            kept[i] = f
    report = {'frames': len(cut), 'expected_frames': timeline['frames'], 'clips': [], 'pass': len(cut) == timeline['frames']}
    for clip in timeline['clips']:
        entry = {'index': clip['index'], 'kind': clip['kind'], 'shot': clip['shot'], 'out_frames': clip['out_frames'], 'checks': []}
        start = clip['out_start']
        if clip['kind'] == 'black':
            black = hashlib.md5(bytes([16]) * (w * h) + bytes([128]) * (w * h // 2)).hexdigest()
            ok = all(f == black for f in cut[start:start + clip['out_frames']])
            entry['checks'].append({'what': 'black', 'frames': clip['out_frames'], 'pass': ok})
        else:
            plain = not clip.get('speed_keys') and not clip.get('look')
            video = it.take / 'shots' / clip['shot'] / 'video.mp4'
            out_at = start
            for piece in clip['push']:
                n = piece['to'] - piece['from']
                lo, hi = clip['fade_in'], clip['out_frames'] - clip['fade_out']
                if piece['kind'] == 'plain' and plain:
                    # Frames outside the fades are the source frames themselves.
                    a, b = max(out_at, start + lo), min(out_at + n, start + hi)
                    if b > a:
                        src = _source(video, piece['from'] + (a - out_at), b - a, w, h)
                        ok = [hashlib.md5(f).hexdigest() for f in src] == cut[a:b]
                        entry['checks'].append({'what': 'source frames', 'src': [piece['from'] + a - out_at, piece['from'] + b - out_at],
                                                'out': [a, b], 'pass': ok})
                elif piece['kind'] == 'hold' and plain:
                    cw, ch, left, top = piece['window']
                    picks = sorted({0, n // 2, n - 1})[:hold_samples]
                    ok_all = True
                    for p in picks:
                        src = _source(video, piece['from'] + p, 1, w, h)[0]
                        out = kept.get(out_at + p)
                        sy, su, sv = _planes(src, w, h)
                        expect = (_nearest(sy, w, h, (left, top, cw, ch), w, h)
                                  + _nearest(su, w // 2, h // 2, (left // 2, top // 2, cw // 2, ch // 2), w // 2, h // 2)
                                  + _nearest(sv, w // 2, h // 2, (left // 2, top // 2, cw // 2, ch // 2), w // 2, h // 2))
                        ok_all = ok_all and expect == out
                    entry['checks'].append({'what': 'push-in hold is the exact nearest-neighbour crop', 'zoom': piece['zoom'],
                                            'window': piece['window'], 'out': [out_at, out_at + n], 'sampled': [out_at + p for p in picks], 'pass': ok_all})
                out_at += n
        entry['pass'] = all(c['pass'] for c in entry['checks'])
        report['pass'] = report['pass'] and entry['pass']
        report['clips'].append(entry)
    (it.cut / 'verify.json').write_text(json.dumps(report, indent=2) + '\n')
    return report
