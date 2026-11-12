"""The cut, minimal for now: the clips of edit.json in order, trimmed, joined and encoded once to cut/master.mp4.

Workstream (c) grows this into the full edit (push-ins with an exact nearest-neighbour crop for UI, speed ramps,
music from the local game assets, sound effects, the export presets), keeping these entry points:
    cut(iteration) -> Path of the master export
"""
import json
import subprocess
from pathlib import Path

from blockreel import tools

VIDEO = ['-pix_fmt', 'yuv420p', '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-movflags', '+faststart']


def cut(it) -> Path:
    ffmpeg = tools.ffmpeg()
    plan, edit, result = it.plan(), it.edit(), it.result()
    if not result or result.get('verdict') != 'PASS':
        raise SystemExit(f'Nothing to cut: the take in {it.take} did not pass')
    fps = plan['output']['fps']
    it.cut.mkdir(exist_ok=True)
    inputs, graph, labels = [], [], []
    for i, clip in enumerate(edit['clip']):
        video = it.take / 'shots' / clip['shot'] / 'video.mp4'
        if not video.exists():
            raise SystemExit(f'Missing {video}; re-take the shot')
        head, tail = (clip.get('trim') or [0, 0])
        frames = next(s['frames'] for s in result['shots'] if s['name'] == clip['shot'])
        inputs += ['-i', str(video)]
        graph.append(f'[{i}:v]trim=start_frame={int(head)}:end_frame={frames - int(tail)},setpts=PTS-STARTPTS,setsar=1[v{i}]')
        labels.append(f'[v{i}]')
    graph.append(''.join(labels) + f'concat=n={len(labels)}:v=1:a=0[v]')
    (it.cut / 'graph.txt').write_text(';\n'.join(graph) + '\n')
    out = it.cut / 'master.mp4'
    subprocess.run([ffmpeg, '-y', '-loglevel', 'error', *inputs, '-filter_complex', ';'.join(graph), '-map', '[v]', '-r', str(fps),
                    '-c:v', 'libx264', '-preset', 'slow', '-crf', '18', '-profile:v', 'high', *VIDEO, '-an', str(out)], check=True)
    poster = it.cut / 'poster.png'
    subprocess.run([ffmpeg, '-y', '-loglevel', 'error', '-sseof', '-0.5', '-i', str(out), '-frames:v', '1', str(poster)], check=True)
    (it.cut / 'cut.json').write_text(json.dumps({'master': out.name, 'poster': poster.name, 'clips': edit['clip']}, indent=2) + '\n')
    return out
