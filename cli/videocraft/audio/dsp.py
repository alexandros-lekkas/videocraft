"""Sample buffers in plain Python: array('f') at 48 kHz, mixed with C-speed map() calls where it matters.

Everything here is deterministic and dependency-free (standard library only); the heavy work of decoding and the
limiter is ffmpeg's (assets.py, loudness.py).
"""
import math
import operator
import struct
from array import array
from itertools import repeat

SR = 48000


def zeros(n):
    return array('f', bytes(4 * max(0, int(n))))


def seconds_to_samples(t):
    return int(round(t * SR))


def scaled(src, gain):
    if gain == 1.0:
        return src
    return array('f', map(operator.mul, src, repeat(gain, len(src))))


def add_into(out, src, offset, gain=1.0, start=0, stop=None):
    """out[offset + i] += src[start + i] * gain wherever both exist. Returns the number of samples written."""
    stop = len(src) if stop is None else min(stop, len(src))
    if offset < 0:
        start -= offset
        offset = 0
    n = min(stop - start, len(out) - offset)
    if n <= 0 or start < 0:
        return 0
    seg = src[start:start + n]
    if gain != 1.0:
        seg = map(operator.mul, seg, repeat(gain, n))
    out[offset:offset + n] = array('f', map(operator.add, out[offset:offset + n], seg))
    return n


def multiply(buf, env):
    """buf *= env, sample by sample (same length)."""
    buf[:] = array('f', map(operator.mul, buf, env))


def resample(src, rate):
    """Plays src at `rate` times its speed (pitch as playback rate, as the game does), by linear interpolation."""
    if abs(rate - 1.0) < 1e-4 or len(src) < 2:
        return src
    n = int((len(src) - 1) / rate)
    s = src
    return array('f', [s[i] + (s[i + 1] - s[i]) * (p - i) for p in (j * rate for j in range(n)) for i in (int(p),)])


def fade(buf, fade_in=0, fade_out=0):
    """Linear fades over the first and last samples, in place."""
    n = len(buf)
    fade_in, fade_out = min(fade_in, n), min(fade_out, n)
    for i in range(fade_in):
        buf[i] *= i / fade_in
    for i in range(fade_out):
        buf[n - 1 - i] *= i / fade_out


def ramp_envelope(points, n, block=480):
    """A per-sample gain curve from (sample, gain) points (sorted), held flat before the first and after the last."""
    if not points:
        return array('f', repeat(1.0, n))
    out = array('f')
    pts = sorted(points)
    if pts[0][0] > 0:
        pts.insert(0, (0, pts[0][1]))
    if pts[-1][0] < n:
        pts.append((n, pts[-1][1]))
    for (a, ga), (b, gb) in zip(pts, pts[1:]):
        a, b = max(0, min(n, a)), max(0, min(n, b))
        length = b - a
        if length <= 0:
            continue
        if ga == gb:
            out.extend(repeat(ga, length))
        else:
            step = (gb - ga) / length
            out.extend(array('f', [ga + step * k for k in range(length)]))
    if len(out) < n:
        out.extend(repeat(out[-1] if out else 1.0, n - len(out)))
    return out[:n]


def block_curve_to_samples(curve, block, n):
    """Expands one gain per `block` samples to a per-sample curve, linearly interpolated between block centres."""
    points = [(i * block + block // 2, g) for i, g in enumerate(curve)]
    return ramp_envelope(points, n)


def rms(buf, start=0, stop=None):
    stop = len(buf) if stop is None else stop
    n = stop - start
    if n <= 0:
        return 0.0
    seg = buf[start:stop]
    return math.sqrt(sum(map(operator.mul, seg, seg)) / n)


def block_rms(buf, block):
    """RMS of each `block` samples: a cheap level curve for ducking and onset detection."""
    out = []
    for i in range(0, len(buf), block):
        seg = buf[i:i + block]
        out.append(math.sqrt(sum(map(operator.mul, seg, seg)) / max(1, len(seg))))
    return out


def peak(buf):
    return max(max(buf, default=0.0), -min(buf, default=0.0))


def db(x):
    return 20 * math.log10(x) if x > 1e-12 else -240.0


def from_db(d):
    return 10 ** (d / 20)


def pan_gains(pan):
    """Constant-power gains (left, right) for pan -1 (left) .. 1 (right)."""
    theta = (max(-1.0, min(1.0, pan)) + 1) * math.pi / 4
    return math.cos(theta), math.sin(theta)


def interleave(left, right):
    out = array('f', bytes(8 * len(left)))
    out[0::2] = left
    out[1::2] = right
    return out


def write_f32(path, left, right):
    """Raw interleaved float32 little-endian stereo at SR (what ffmpeg reads with -f f32le -ac 2)."""
    data = interleave(left, right)
    if struct.pack('=f', 1.0) != struct.pack('<f', 1.0):
        data.byteswap()
    with open(path, 'wb') as f:
        data.tofile(f)


def read_f32(path, channels=1):
    data = array('f')
    with open(path, 'rb') as f:
        data.frombytes(f.read())
    if struct.pack('=f', 1.0) != struct.pack('<f', 1.0):
        data.byteswap()
    if channels == 1:
        return data
    return data[0::2], data[1::2]


def read_wav16(path):
    """A 16-bit PCM wav (what the master writes) as (left, right) floats."""
    import wave
    with wave.open(str(path), 'rb') as w:
        if w.getsampwidth() != 2:
            raise ValueError(f'{path}: expected 16-bit PCM')
        channels, frames = w.getnchannels(), w.readframes(w.getnframes())
    pcm = array('h')
    pcm.frombytes(frames)
    if struct.pack('=h', 1) != struct.pack('<h', 1):
        pcm.byteswap()
    data = array('f', map(operator.mul, pcm, repeat(1 / 32768, len(pcm))))
    if channels == 1:
        return data, data
    return data[0::2], data[1::2]
