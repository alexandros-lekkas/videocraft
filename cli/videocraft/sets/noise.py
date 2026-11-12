"""Seeded, repeatable noise and choice. No `hash()` (salted per process) and no global random state."""
import math


def _h(*ints):
    """A 32-bit integer hash of integers (splitmix-style), stable across runs and machines."""
    v = 0x9E3779B9
    for i in ints:
        v = (v ^ (int(i) & 0xFFFFFFFF)) * 0x85EBCA6B & 0xFFFFFFFF
        v = (v ^ (v >> 13)) * 0xC2B2AE35 & 0xFFFFFFFF
        v ^= v >> 16
    return v


def rand(seed, *coords):
    """A uniform number in [0, 1) for this seed and cell."""
    return _h(seed, *coords) / 4294967296.0


def salt(text):
    v = 2166136261
    for ch in str(text).encode('utf-8'):
        v = ((v ^ ch) * 16777619) & 0xFFFFFFFF
    return v


def value(seed, x, z):
    """Smooth value noise in [0, 1] at a continuous point; features about one unit wide."""
    x0, z0 = math.floor(x), math.floor(z)
    fx, fz = x - x0, z - z0
    sx, sz = fx * fx * (3 - 2 * fx), fz * fz * (3 - 2 * fz)
    a = rand(seed, x0, z0)
    b = rand(seed, x0 + 1, z0)
    c = rand(seed, x0, z0 + 1)
    d = rand(seed, x0 + 1, z0 + 1)
    return (a + (b - a) * sx) * (1 - sz) + (c + (d - c) * sx) * sz


def fbm(seed, x, z, octaves=3):
    total, amp, norm = 0.0, 1.0, 0.0
    for o in range(octaves):
        total += amp * value(seed + o * 101, x * (2 ** o), z * (2 ** o))
        norm += amp
        amp *= 0.5
    return total / norm


class Mix:
    """A weighted choice of blocks. `"cobblestone"`, `{cobblestone = 5, andesite = 2}` or `[["cobblestone", 5], …]`.

    With `grain` 0 every cell draws on its own (salt and pepper). With `grain` > 0 the rarer entries come in patches
    about `grain` blocks across, which reads as worn ground rather than noise; the first entry is the base."""

    def __init__(self, spec, seed=0, grain=0.0):
        if isinstance(spec, Mix):
            self.entries, self.seed, self.grain = spec.entries, seed, grain
        elif isinstance(spec, str):
            self.entries = [(spec, 1.0)]
        elif isinstance(spec, dict):
            self.entries = [(k, float(v)) for k, v in spec.items()]
        elif isinstance(spec, (list, tuple)):
            self.entries = [(e, 1.0) if isinstance(e, str) else (e[0], float(e[1])) for e in spec]
        else:
            raise ValueError(f'a block mix is a block, a table of block = weight, or a list (got {spec!r})')
        if not self.entries or any(w < 0 for _, w in self.entries):
            raise ValueError(f'a block mix needs at least one block and weights >= 0 (got {spec!r})')
        self.seed, self.grain = seed, float(grain or 0)
        total = sum(w for _, w in self.entries) or 1.0
        self.fractions = [w / total for _, w in self.entries]
        self._thresholds = None

    @property
    def single(self):
        return len(self.entries) == 1

    def _calibrate(self):
        # Thresholds per patch field so each rarer entry covers about its share of the area.
        th = []
        for j in range(1, len(self.entries)):
            samples = sorted(self._field(j, i * 0.37 * self.grain, k * 0.41 * self.grain) for i in range(48) for k in range(48))
            share = self.fractions[j] / max(1e-9, 1.0 - sum(self.fractions[1:j]))
            q = min(len(samples) - 1, max(0, int((1 - min(1.0, share)) * len(samples))))
            th.append(samples[q] if share < 1 else -1)
        self._thresholds = th

    def _field(self, j, x, z):
        g = max(0.5, self.grain)
        return 0.75 * fbm(self.seed + 7919 * j, x / g, z / g, 2) + 0.25 * rand(self.seed + 31 * j, int(x), int(z))

    def pick(self, x, z, y=0):
        if len(self.entries) == 1:
            return self.entries[0][0]
        if self.grain <= 0:
            u = rand(self.seed, x, y, z)
            acc = 0.0
            for (name, _), f in zip(self.entries, self.fractions):
                acc += f
                if u < acc:
                    return name
            return self.entries[-1][0]
        if self._thresholds is None:
            self._calibrate()
        for j in range(1, len(self.entries)):
            if self._field(j, x, z) > self._thresholds[j - 1]:
                return self.entries[j][0]
        return self.entries[0][0]
