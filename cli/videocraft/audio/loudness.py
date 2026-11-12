"""Loudness by EBU R128 (ffmpeg's ebur128 filter) and the master: gain to the target, then a true-peak limiter.

    measure(path or raw) -> {'integrated', 'lra', 'true_peak', 'sample_peak'}
    master(raw_f32, out_wav, target=-14, ceiling=-1) -> measured loudness of out_wav

The limiter runs 4x oversampled (192 kHz) so it catches inter-sample peaks, with its delay compensated so nothing
moves in time (the mix is placed to the sample). Two passes at most: the second corrects what the limiter took off.
"""
import re
import subprocess
from pathlib import Path

from videocraft import tools
from videocraft.audio import dsp

TARGET, CEILING = -14.0, -2.0   # -2 so the AAC master (its encode overshoots the mix by 0.8-0.9 dB) stays under -1 dBTP


def _raw_input(path):
    return ['-f', 'f32le', '-ar', str(dsp.SR), '-ac', '2', '-i', str(path)]


def measure(path, raw=False, start=None, duration=None):
    """EBU R128 integrated loudness (LUFS), loudness range (LU), true peak and sample peak (dBFS) of a file."""
    cmd = [tools.ffmpeg(), '-hide_banner', '-nostats']
    if start is not None:
        cmd += ['-ss', f'{start:.4f}']
    if duration is not None:
        cmd += ['-t', f'{duration:.4f}']
    cmd += (_raw_input(path) if raw else ['-i', str(path)])
    cmd += ['-af', 'ebur128=peak=true+sample:framelog=quiet', '-f', 'null', '-']
    p = subprocess.run(cmd, capture_output=True, text=True)
    text = p.stderr
    summary = text[text.rfind('Summary:'):]

    def grab(label, unit):
        m = re.search(rf'{label}:\s+(-?[\d.]+|-inf)\s+{unit}', summary)
        return None if not m else (-120.0 if m.group(1) == '-inf' else float(m.group(1)))

    out = {'integrated': grab('I', 'LUFS'), 'lra': grab('LRA', 'LU')}
    peaks = re.findall(r'Peak:\s+(-?[\d.]+|-inf)\s+dBFS', summary)
    vals = [(-120.0 if v == '-inf' else float(v)) for v in peaks]
    # ebur128 prints the sample peak block before the true peak block when both are asked for.
    out['sample_peak'] = vals[0] if len(vals) > 1 else None
    out['true_peak'] = vals[-1] if vals else None
    if out['integrated'] is None:
        raise RuntimeError(f'ebur128 gave no loudness for {path}: {text[-400:]}')
    return out


def _render(raw, out_wav, gain_db, ceiling):
    limit = dsp.from_db(ceiling - 0.35)  # a little margin: the 16-bit write and the down-sampler add a hair
    chain = (f'volume={gain_db:.3f}dB,aresample={dsp.SR * 4},'
             f'alimiter=limit={limit:.5f}:attack=2:release=60:level=disabled:latency=1,aresample={dsp.SR}')
    p = subprocess.run([tools.ffmpeg(), '-y', '-hide_banner', '-loglevel', 'error', *_raw_input(raw), '-af', chain,
                        '-c:a', 'pcm_s16le', str(out_wav)], capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f'ffmpeg could not master the mix: {p.stderr[-600:]}')


def master(raw, out_wav, target=TARGET, ceiling=CEILING):
    """Masters the raw float mix to `target` LUFS integrated with true peak at or under `ceiling` dBTP."""
    raw, out_wav = Path(raw), Path(out_wav)
    before = measure(raw, raw=True)
    if before['integrated'] is None or before['integrated'] < -69:
        _render(raw, out_wav, 0.0, ceiling)
        return {**measure(out_wav), 'gain_db': 0.0, 'passes': 1, 'note': 'silent mix: nothing to level'}
    gain = min(40.0, target - before['integrated'])
    after = None
    for passes in (1, 2, 3):
        _render(raw, out_wav, gain, ceiling)
        after = measure(out_wav)
        error = target - after['integrated']
        if abs(error) <= 0.3:
            break
        gain = min(40.0, gain + error)
    return {**after, 'gain_db': round(gain, 2), 'passes': passes, 'before': before['integrated']}
