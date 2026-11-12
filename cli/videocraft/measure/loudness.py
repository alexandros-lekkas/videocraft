"""Loudness of a video's sound (EBU R128 through ffmpeg's ebur128 filter): integrated, true peak, the momentary curve
per second and the silent stretches. None when the file has no audio stream. Owned by workstream (d)."""
import re
import statistics
import subprocess

from videocraft import tools

SILENCE = -50.0          # LUFS momentary: below this is silence (the benchmark's dips)
SILENCE_MIN = 0.3        # seconds
LINE = re.compile(r'\bt:\s*([\d.]+)\s.*?\bM:\s*(-?[\d.]+|-inf)')


def has_audio(path):
    out = subprocess.run([tools.ffprobe(), '-v', 'error', '-select_streams', 'a', '-show_entries', 'stream=index', '-of', 'csv=p=0', str(path)],
                         capture_output=True, text=True)
    return bool(out.stdout.strip())


def parse(text):
    """(samples [(t, momentary LUFS)], integrated LUFS, true peak dBFS, LRA LU) from ebur128's verbose log."""
    samples = []
    for line in text.splitlines():
        if 'Parsed_ebur128' in line and ' t:' in line:
            m = LINE.search(line)
            if m:
                samples.append((float(m.group(1)), float('-inf') if m.group(2) == '-inf' else float(m.group(2))))
    summary = text[text.rfind('Summary:'):] if 'Summary:' in text else ''
    grab = lambda key: (lambda m: float(m.group(1)) if m else None)(re.search(key + r':\s*(-?[\d.]+|-inf)', summary))
    return samples, grab('I'), grab('Peak'), grab('LRA')


def per_second(samples, seconds):
    """The momentary loudness of each whole second: the median of the 100 ms readings in it (window ends inside)."""
    out = []
    for k in range(int(seconds + 0.999)):
        values = [m for t, m in samples if k < t <= k + 1 + 1e-6]
        out.append(round(statistics.median(values), 1) if values else None)
    return out


def silences(samples, threshold=SILENCE, minimum=SILENCE_MIN):
    out, start, last = [], None, 0.0
    for t, m in samples:
        quiet = m < threshold
        if quiet and start is None:
            start = max(0.0, t - 0.1)
        elif not quiet and start is not None:
            if t - 0.1 - start >= minimum - 1e-9:
                out.append({'start': round(start, 2), 'end': round(t - 0.1, 2), 'seconds': round(t - 0.1 - start, 2)})
            start = None
        last = t
    if start is not None and last - start >= minimum - 1e-9:
        out.append({'start': round(start, 2), 'end': round(last, 2), 'seconds': round(last - start, 2)})
    return out


def measure(path, start=None, end=None):
    if not has_audio(path):
        return None
    cmd = [tools.ffmpeg(), '-hide_banner', '-nostdin', '-v', 'verbose']
    if start:
        cmd += ['-ss', f'{start:.3f}']
    cmd += ['-i', str(path)]
    if end is not None:
        cmd += ['-t', f'{end - (start or 0):.3f}']
    cmd += ['-vn', '-filter_complex', 'ebur128=peak=true:framelog=verbose', '-f', 'null', '-']
    text = subprocess.run(cmd, capture_output=True, text=True).stderr
    samples, integrated, peak, lra = parse(text)
    seconds = samples[-1][0] if samples else 0.0
    return {'integrated': integrated, 'true_peak': peak, 'lra': lra, 'momentary_per_second': per_second(samples, seconds),
            'silences': silences(samples), 'seconds': round(seconds, 2)}
