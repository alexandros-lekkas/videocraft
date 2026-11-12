"""The cut: edit.json + the take → cut/timeline.json → cut/master.mp4 (+ audio from the audio workstream) → exports.

Entry point (kept stable for cli.py and others):
    cut(iteration, silent=None, exports=True) -> Path of the master

Frame-exact: every clip's frames are resolved in timeline.py before anything is encoded, cut/timeline.json is written
first (the audio mix and measure read it), and the filter graph only ever trims, crops, zooms, retimes to whole
frames, grades, frames and fades. See docs/SCRIPT.md ("Edit") for the grammar.
"""
import json
import os
import subprocess
import threading
import time
from pathlib import Path

from videocraft import tools
from videocraft.edit import export as exports_
from videocraft.edit import graph as graph_
from videocraft.edit import looks
from videocraft.edit.timeline import EditError, resolve

VIDEO = exports_.VIDEO


def _marks(take, shots):
    out = {}
    for name in shots:
        path = take / 'shots' / name / 'marks.json'
        try:
            out[name] = json.loads(path.read_text())
        except (OSError, ValueError):
            out[name] = []
    return out


def timeline_of(it):
    """Resolves the iteration's edit against its take (does not encode). Raises SystemExit with the edit's problem."""
    plan, edit, result = it.plan(), it.edit(), it.result()
    if not result or result.get('verdict') != 'PASS':
        raise SystemExit(f'Nothing to cut: the take in {it.take} did not pass')
    shots = {s['name']: s['frames'] for s in result['shots']}
    try:
        return resolve(plan, edit, shots, _marks(it.take, shots))
    except EditError as e:
        raise SystemExit(f'EDIT ERROR {e}') from e


def is_silent(edit, silent=None):
    if silent is not None:
        return silent
    if os.environ.get('VIDEOCRAFT_SILENT', '').strip() not in ('', '0'):
        return True
    return str(edit.get('audio', '')).lower() in ('none', 'silent', 'off')


VIDEO_PRESETS = ('x-1080p60', 'readme-720p30')


def wants_original(edit, original_audio=None, exports=True):
    """Whether the cut also mixes cut/audio-original.wav: `--original-audio`, or an export with audio = "original"."""
    return bool(original_audio) or (exports and any(str(e.get('audio', '')).lower() == 'original' for e in edit.get('export') or []))


def cut(it, silent=None, exports=True, original_audio=None) -> Path:
    """original_audio: also write master-original-audio.mp4 and an `-original-audio` copy of every video export, with
    the sound track that holds no game audio (cut/audio-original.wav); cut/audio.wav stays the game mix."""
    ffmpeg = tools.ffmpeg()
    plan, edit = it.plan(), it.edit()
    started = time.time()
    timeline = timeline_of(it)
    it.cut.mkdir(exist_ok=True)
    (it.cut / 'timeline.json').write_text(json.dumps(timeline, indent=1) + '\n')
    width, height, fps = timeline['width'], timeline['height'], timeline['fps']

    # The audio mix runs while the picture encodes; it reads timeline.json, written above.
    audio = {'path': None, 'error': None, 'original': None}
    worker = None
    second = wants_original(edit, original_audio, exports)
    if not is_silent(edit, silent):
        try:
            from videocraft.audio import mix
        except ImportError:
            mix = None
        if mix is not None:
            def build():
                try:
                    audio['path'] = mix.build(it)
                    if second and audio['path']:
                        # The game mix keeps cut/audio.wav; the original one never overwrites it.
                        audio['original'] = (audio['path'] if mix._mode(edit, None) == 'original'
                                             else mix.build(it, original=True, name='audio-original'))
                except SystemExit as e:
                    audio['error'] = str(e.code)
                except Exception as e:  # the picture still gets cut; the report names the audio problem
                    audio['error'] = f'{type(e).__name__}: {e}'
            worker = threading.Thread(target=build, daemon=True)
            worker.start()

    pngs = {}

    def frame_png(spec):
        key = json.dumps(spec, sort_keys=True)
        if key not in pngs:
            looks_dir = it.cut / 'looks'
            looks_dir.mkdir(exist_ok=True)
            scale = min(width, height) / 1080
            pngs[key] = looks.frame_png(looks_dir / f'frame-{len(pngs)}.png', width, height, spec.get('color', '#e8a23a'),
                                        float(spec.get('width', 28)), float(spec.get('glow', 12)), float(spec.get('opacity', 1.0)), scale)
        return pngs[key]

    def video_of(shot):
        path = it.take / 'shots' / shot / 'video.mp4'
        if not path.exists():
            raise SystemExit(f'Missing {path}; re-take the shot')
        return path

    inputs, graph = graph_.build(timeline, video_of, frame_png)
    (it.cut / 'graph.txt').write_text(';\n'.join(graph) + '\n')
    picture = it.cut / 'picture.mp4'
    subprocess.run([ffmpeg, '-y', '-loglevel', 'error', *inputs, '-filter_complex', ';'.join(graph), '-map', '[v]', '-r', str(fps),
                    '-c:v', 'libx264', '-preset', 'slow', '-crf', '18', '-profile:v', 'high', *VIDEO, '-an', str(picture)], check=True)
    if worker:
        worker.join()
    out = it.cut / 'master.mp4'
    wav = audio['path']
    seconds = timeline['frames'] / fps
    if wav:
        # The mix is mastered already: AAC 192k, cut or padded to the picture's exact length.
        subprocess.run([ffmpeg, '-y', '-loglevel', 'error', '-i', str(picture), '-i', str(wav), '-map', '0:v', '-map', '1:a',
                        '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-af', 'apad', '-t', f'{seconds:.6f}', '-movflags', '+faststart', str(out)],
                       check=True)
        picture.unlink()
    else:
        picture.replace(out)
    written = {'master': out.name}
    orig = audio['original']
    if orig:
        alt = it.cut / 'master-original-audio.mp4'
        subprocess.run([ffmpeg, '-y', '-loglevel', 'error', '-i', str(out), '-i', str(orig), '-map', '0:v', '-map', '1:a',
                        '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-af', 'apad', '-t', f'{seconds:.6f}', '-movflags', '+faststart', str(alt)],
                       check=True)
        written['master-original-audio'] = alt.name
    poster = exports_.export({'preset': 'poster'}, out, it.cut, width, height, fps, seconds, bool(wav))
    written['poster'] = poster.name
    if exports:
        for spec in edit.get('export') or []:
            path = exports_.export(spec, out, it.cut, width, height, fps, seconds, bool(wav))
            name = spec.get('name', spec['preset'])
            written[name] = path.name
            if orig and spec['preset'] in VIDEO_PRESETS and (original_audio or str(spec.get('audio', '')).lower() == 'original'):
                path = exports_.export(spec, out, it.cut, width, height, fps, seconds, True, audio_file=orig, suffix='-original-audio')
                written[f'{name}-original-audio'] = path.name
    record = {'master': out.name, 'poster': poster.name, 'frames': timeline['frames'], 'seconds': seconds,
              'audio': str(wav) if wav else None, 'audio_error': audio['error'], 'audio_original': str(orig) if orig else None,
              'silent': is_silent(edit, silent), 'exports': written, 'clips': edit['clip'], 'cut_seconds': round(time.time() - started, 1)}
    (it.cut / 'cut.json').write_text(json.dumps(record, indent=2) + '\n')
    if audio['error']:
        print(f'videocraft cut: no sound track ({audio["error"]}); the master is silent', flush=True)
    return out
