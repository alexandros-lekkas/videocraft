"""Measurements of a cut, written to measure/metrics.json. Minimal for now: the export's format against the plan.

Workstream (d) adds the rest (docs/DESIGN.md, "Measure"): camera jerk and view speed from frames.csv, text on screen
against the reading-time rule, safe-area and capital-height checks, black or frozen frames, loudness.
"""
import json
import subprocess

from blockreel import tools


def probe(path):
    out = subprocess.run([tools.ffprobe(), '-v', 'error', '-select_streams', 'v:0', '-count_packets', '-show_entries',
                          'stream=width,height,r_frame_rate,nb_read_packets,codec_name,pix_fmt:format=duration,size', '-of', 'json', str(path)],
                         capture_output=True, text=True, check=True)
    data = json.loads(out.stdout)
    s, f = data['streams'][0], data['format']
    num, den = s['r_frame_rate'].split('/')
    return {'width': s['width'], 'height': s['height'], 'fps': int(num) / int(den), 'frames': int(s['nb_read_packets']),
            'codec': s['codec_name'], 'pixfmt': s['pix_fmt'], 'seconds': float(f['duration']), 'bytes': int(f['size'])}


def measure(it):
    plan, result = it.plan(), it.result()
    out = plan['output']
    master = it.cut / 'master.mp4'
    video = probe(master)
    expected = sum(s['frames'] for s in result['shots'])
    for clip in it.edit()['clip']:
        expected -= sum(clip.get('trim') or [0, 0])
    checks = {
        'size': video['width'] == out['width'] and video['height'] == out['height'],
        'fps': abs(video['fps'] - out['fps']) < 1e-6,
        'frames': video['frames'] == expected,
        'shots_complete': all(s['frames'] == round(p['duration'] * out['fps']) for s, p in zip(result['shots'], plan['shots'])),
    }
    metrics = {'master': video, 'expectedFrames': expected, 'checks': checks, 'pass': all(checks.values()),
               'take': {'wallSeconds': result.get('wallSeconds'), 'captureFps': result.get('captureFps')}}
    it.measure.mkdir(exist_ok=True)
    (it.measure / 'metrics.json').write_text(json.dumps(metrics, indent=2) + '\n')
    return metrics
