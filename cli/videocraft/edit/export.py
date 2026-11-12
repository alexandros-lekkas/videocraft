"""Exports from the master, each into cut/ (docs/SCRIPT.md, "Edit"):

    x-1080p60      H.264 1080p (short side) at up to 60 fps, under 25 MB (X / Twitter), audio AAC 192k
    readme-720p30  H.264 720p (short side) at 30 fps, under 10 MB (a GitHub README upload), audio AAC 128k
    gif            a short, small silent loop: `from` and `seconds` (default the first 5 s), 640 px on the long side,
                   stepping down in size and colours until it is under `max_mb` (default 6)
    poster         one PNG frame, at `at` seconds (default half a second before the end)

They work for landscape and vertical masters alike: sizes are set on the short side. Quality steps down only when a
file comes out over its limit.
"""
import subprocess
from pathlib import Path

from videocraft import tools

PRESETS = ('x-1080p60', 'readme-720p30', 'gif', 'poster')
VIDEO = ['-pix_fmt', 'yuv420p', '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-movflags', '+faststart']
MB = 1_000_000


def _scale_short(width, height, short):
    """The size with the short side `short` (never upscaled), both even."""
    s = min(1.0, short / min(width, height))
    return int(round(width * s / 2)) * 2, int(round(height * s / 2)) * 2


def _ladder(make, out, limit, crfs):
    for crf in crfs:
        make(crf)
        if out.stat().st_size <= limit:
            return crf
    return crfs[-1]


def export(spec, master, cut_dir, width, height, fps, seconds, has_audio, audio_file=None, suffix=''):
    """Writes one export; returns its path. `audio_file` (a wav) replaces the master's sound in a video export, whose
    file name then ends in `suffix` (the cut's `-original-audio` copies)."""
    ffmpeg = tools.ffmpeg()
    preset = spec['preset']
    run = lambda args: subprocess.run([ffmpeg, '-y', '-loglevel', 'error', *args], check=True)
    if preset in ('x-1080p60', 'readme-720p30'):
        short, rate, limit, abr, crfs = ((1080, min(fps, 60), 24.5 * MB, '192k', (20, 22, 24, 26, 28, 30)) if preset == 'x-1080p60'
                                         else (720, min(fps, 30), 9.5 * MB, '128k', (24, 26, 28, 30, 32, 34)))
        w, h = _scale_short(width, height, short)
        out = Path(cut_dir) / f'{spec.get("name", preset)}{suffix}.mp4'
        vf = []
        if rate != fps:
            vf.append(f'fps={rate}')
        if (w, h) != (width, height):
            vf.append(f'scale={w}:{h}:flags=lanczos:in_color_matrix=bt709:out_color_matrix=bt709')
        inputs = ['-i', str(master)]
        if audio_file:
            inputs += ['-i', str(audio_file), '-map', '0:v', '-map', '1:a', '-af', 'apad', '-t', f'{seconds:.6f}']
        audio = ['-c:a', 'aac', '-b:a', abr] if has_audio or audio_file else ['-an']
        _ladder(lambda crf: run([*inputs, *(['-vf', ','.join(vf)] if vf else []), '-c:v', 'libx264', '-preset', 'slow',
                                 '-crf', str(crf), '-profile:v', 'high', *VIDEO, *audio, str(out)]), out, limit, crfs)
        return out
    if preset == 'gif':
        start = float(spec.get('from', 0.0))
        length = float(spec.get('seconds', min(5.0, max(0.1, seconds - start))))
        out = Path(cut_dir) / f'{spec.get("name", "preview")}.gif'
        limit = float(spec.get('max_mb', 6)) * MB
        for long_side, rate, colors in ((640, 15, 128), (640, 12, 96), (540, 12, 64), (480, 10, 48), (400, 10, 32)):
            w, h = (long_side, -2) if width >= height else (-2, long_side)
            run(['-ss', f'{start:.3f}', '-t', f'{length:.3f}', '-i', str(master), '-filter_complex',
                 f'fps={rate},scale={w}:{h}:flags=lanczos,split[a][b];[a]palettegen=max_colors={colors}:stats_mode=diff[p];'
                 f'[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle', '-loop', '0', str(out)])
            if out.stat().st_size <= limit:
                break
        return out
    if preset == 'poster':
        out = Path(cut_dir) / f'{spec.get("name", "poster")}.png'
        at = spec.get('at')
        args = ['-sseof', '-0.5', '-i', str(master)] if at is None else ['-ss', f'{float(at):.3f}', '-i', str(master)]
        run([*args, '-frames:v', '1', str(out)])
        return out
    raise ValueError(f'unknown export preset {preset!r}; presets: {", ".join(PRESETS)}')
