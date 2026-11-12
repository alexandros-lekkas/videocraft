"""`videocraft compare --side-by-side`: a reference video and one of our iterations in one 1920x1080 film.

    videocraft compare --video ref.mp4 --from 0 --to 82.2 --run x/12 --side-by-side -o out/x-vs-ref.mp4 \\
        [--align shots|time] [--shots list.toml] [--lead ours|ref] [--fit auto|stretch|hold] [--audio ours|ref|none]

Each side is a 960x540 pane (left/right, or top/bottom with --layout tb) with a label bar drawn with the built-in
bitmap font (ffmpeg here has no drawtext): side, shot number, camera type, length, play speed; above them a shared
timecode, the shot pair's length delta, and both films' shot lanes with a cursor each.

--align shots pairs shot N of the reference with shot N of ours, and black with black (the dip after shot N with
ours after shot N). The reference's shots come from a shot-list file (--shots; e.g.
docs/benchmarks/pinksheep-style.shots.toml) or, without one, from `measure`'s cut detection. Our shots come from the
iteration's cut/timeline.json; a shot named `s07-…` is shot 7 (`s16b-…` joins shot 16), so a script that splits one
reference shot in two still pairs; without numbers, shots pair in order. The lead side (--lead, default ours) plays at
its own speed; each follower shot is fitted to the lead shot's length: `stretch` changes its speed to fill it exactly,
`hold` plays it at its own speed and holds its last frame (or cuts it short), `auto` (default) stretches within
0.5x-2x and holds or cuts past that. A shot with no partner shows a black pane. --align time plays both from the start
at their own speed, the shorter one holding its last frame.

Next to the video it writes side-by-side.md and .json (per pair: both lengths, camera types, our rig, lens and
measured framing) and side-by-side-sheet.jpg (one row per pair, the middle frame of each).
Nothing of the reference is written anywhere but the output folder the caller chose.
"""
import json
import re
import subprocess
import tomllib
from pathlib import Path

from videocraft import tools
from videocraft.review.image import Canvas, text_width
from videocraft.review.packet import grab

PANE = (960, 540)
FPS = 60
MIN_GAP = 0.25          # a gap between a reference shot's end and the next start longer than this is black (the
                        # benchmark's cut times are good to ±0.1 s; its dips are 0.9 s and more)
MAX_SPEED = 2.0         # --fit auto: stretch within 1/MAX_SPEED to MAX_SPEED, hold or cut past that
BG, INK, DIM, MARK, REF_C, OUR_C = (16, 16, 20), (255, 255, 255), (150, 150, 162), (255, 210, 60), (120, 200, 255), (255, 170, 90)
GOOD, WARN, BAD = (110, 220, 120), (255, 210, 60), (255, 100, 90)
TOP, BOTTOM = 196, 344  # chrome above and below the panes in the left/right layout (196 + 540 + 344 = 1080)


# --- shot lists ------------------------------------------------------------------------------------------------------

def load_shot_list(path):
    """{'from', 'to', 'shots': [{'n', 'start', 'seconds', 'camera'}]} from a shot-list TOML ([section], [[shot]])."""
    data = tomllib.loads(Path(path).read_text())
    sec = data.get('section') or {}
    shots = [{'n': int(s['n']), 'start': float(s['start']), 'seconds': float(s['seconds']), 'camera': s.get('camera', '-')}
             for s in data.get('shot', [])]
    return {'from': sec.get('from'), 'to': sec.get('to'), 'shots': sorted(shots, key=lambda s: s['start'])}


def ref_segments(shots, start, end):
    """The reference section as segments [{'kind': 'shot'|'black', 'n', 'a', 'b', 'camera'}] in source seconds.
    A shot ends at its start plus length or the next start, whichever is first, and at the next start when the gap to
    it is MIN_GAP or less (the listed numbers are rounded); a longer gap is black, numbered after the shot before it,
    and so is the stretch from the last shot's end to `end`."""
    shots = [s for s in shots if start - 1e-6 <= s['start'] < end]
    out = []
    for k, s in enumerate(shots):
        nxt = shots[k + 1]['start'] if k + 1 < len(shots) else end
        b = min(s['start'] + s['seconds'], nxt, end)
        if nxt - b <= MIN_GAP:          # a rounding sliver: the next start is the cut
            b = min(nxt, end)
        out.append({'kind': 'shot', 'n': s['n'], 'a': s['start'], 'b': round(b, 4), 'camera': s.get('camera', '-')})
        if nxt - b > MIN_GAP:
            out.append({'kind': 'black', 'n': s['n'], 'a': round(b, 4), 'b': nxt, 'camera': 'black'})
    if out and out[0]['a'] - start > MIN_GAP:
        out.insert(0, {'kind': 'black', 'n': 0, 'a': start, 'b': out[0]['a'], 'camera': 'black'})
    return out


def detected_segments(picture, start):
    """Reference segments from measure's picture analysis (shots and black, seconds from `start`), numbered in order."""
    items = [('shot', s['start'], s['end']) for s in picture.get('shots', [])] + [('black', b['start'], b['end']) for b in picture.get('black', [])]
    out, n = [], 0
    for kind, a, b in sorted(items, key=lambda x: x[1]):
        n += kind == 'shot'
        out.append({'kind': kind, 'n': n, 'a': round(start + a, 4), 'b': round(start + b, 4), 'camera': '-' if kind == 'shot' else 'black'})
    return out


SHOT_NUMBER = re.compile(r'^s?(\d+)')


def shot_number(name):
    m = SHOT_NUMBER.match(name or '')
    return int(m.group(1)) if m else None


def our_segments(clips, fps, numbered=None):
    """Our clips (timeline.clips) as segments [{'kind', 'n', 'a', 'b', 'clips': [{name, a, b}]}] in master seconds.
    Consecutive clips with the same shot number are one segment; black after shot N is ('black', N). Numbers come from
    the names (`s07-…`) when most shots have one (or numbered=True), else from the order."""
    shots = [c for c in clips if c['kind'] == 'shot']
    if numbered is None:
        numbered = sum(shot_number(c['shot']) is not None for c in shots) * 2 > len(shots)
    out, last, order = [], 0, 0
    for c in clips:
        a, b = c['out_start'] / fps, (c['out_start'] + c['out_frames']) / fps
        if c['kind'] == 'shot':
            if numbered:
                n = shot_number(c['shot'])
            else:
                order += 1
                n = order
            kind = 'shot'
            if n is not None:
                last = n
        else:
            kind, n = 'black', last
        prev = out[-1] if out else None
        if prev and prev['kind'] == kind and prev['n'] == n and n is not None and abs(prev['b'] - a) < 1e-6:
            prev['b'] = b
            prev['clips'].append({'name': c['shot'], 'a': a, 'b': b})
        else:
            out.append({'kind': kind, 'n': n, 'a': a, 'b': b, 'clips': [{'name': c['shot'] or kind, 'a': a, 'b': b}]})
    return out


def pair(ref, ours, lead='ours'):
    """[(ref segment or None, our segment or None)] in the lead side's order. Segments pair on (kind, n); a follower
    segment that would play out of order (its start before the last paired one's) stays unpaired, so the follower
    only ever plays forward. Unpaired follower segments are left out; unpaired lead segments keep a blank partner."""
    leader, follower = (ours, ref) if lead == 'ours' else (ref, ours)
    index = {}
    for seg in follower:
        if seg['n'] is not None:
            index.setdefault((seg['kind'], seg['n']), seg)
    out, last = [], float('-inf')
    for seg in leader:
        partner = index.get((seg['kind'], seg['n'])) if seg['n'] is not None else None
        if partner is not None and partner['a'] < last:
            partner = None
        if partner is not None:
            last = partner['a']
        out.append((partner, seg) if lead == 'ours' else (seg, partner))
    return out


def fit(src, out, mode='auto', max_speed=MAX_SPEED):
    """How a follower shot of `src` seconds fills `out` seconds: (speed, used, hold). `used` seconds of the source play
    at `speed` (source seconds per output second) for used/speed seconds, then its last frame holds for `hold`."""
    if out <= 0 or src <= 0:
        return 1.0, 0.0, max(0.0, out)
    if mode == 'stretch':
        return src / out, src, 0.0
    if mode == 'hold':
        used = min(src, out)
        return 1.0, used, out - used
    speed = min(max(src / out, 1 / max_speed), max_speed)
    used = min(src, out * speed)
    return speed, used, max(0.0, out - used / speed)


def plan_output(pairs, lead='ours', mode='auto'):
    """Output segments [{t0, t1, ref, ours}] where each side is None (blank) or {'seg', 'a', 'speed', 'used', 'hold'}:
    the lead side plays its segment at speed 1, the follower is fitted to it."""
    out, t = [], 0.0
    for r, o in pairs:
        lead_seg = o if lead == 'ours' else r
        length = lead_seg['b'] - lead_seg['a']
        sides = {}
        for name, seg in (('ref', r), ('ours', o)):
            if seg is None:
                sides[name] = None
            elif seg is lead_seg:
                sides[name] = {'seg': seg, 'a': seg['a'], 'speed': 1.0, 'used': length, 'hold': 0.0}
            else:
                speed, used, hold = fit(seg['b'] - seg['a'], length, mode)
                sides[name] = {'seg': seg, 'a': seg['a'], 'speed': speed, 'used': used, 'hold': hold}
        out.append({'t0': round(t, 6), 't1': round(t + length, 6), **sides})
        t += length
    return out


def plan_time(ref, ours, ref_from, lead='ours'):
    """--align time: both sides from their start at their own speed; output segments at every boundary of either."""
    total = (ours[-1]['b'] if lead == 'ours' else ref[-1]['b'] - ref_from) if (ours if lead == 'ours' else ref) else 0.0
    edges = [s[k] for s in ours for k in ('a', 'b')] + [s[k] - ref_from for s in ref for k in ('a', 'b')]
    bounds = sorted({0.0, total, *(round(e, 6) for e in edges if 0 < e < total)})
    at = lambda segs, t, off: next((s for s in segs if s['a'] - off <= t + 1e-9 < s['b'] - off), None)
    out = []
    for t0, t1 in zip(bounds, bounds[1:]):
        if t1 - t0 < 1e-6:
            continue
        sides = {}
        for name, segs, off in (('ref', ref, -ref_from), ('ours', ours, 0.0)):
            seg = at(segs, t0, -off)
            sides[name] = None if seg is None else {'seg': seg, 'a': t0 - off, 'speed': 1.0, 'used': t1 - t0, 'hold': 0.0}
        out.append({'t0': t0, 't1': t1, **sides})
    return out


# --- the ffmpeg graph ------------------------------------------------------------------------------------------------

def _tree(pieces, key):
    """A balanced if() tree choosing the piece whose source start is the last one at or before T."""
    if len(pieces) == 1:
        return key(pieces[0])
    mid = len(pieces) // 2
    return f"if(lt(T,{pieces[mid]['a']:.6f}),{_tree(pieces[:mid], key)},{_tree(pieces[mid:], key)})"


def _sum(terms):
    """a+b+c… as a balanced tree: ffmpeg's parser nests a flat chain and refuses a long one."""
    if len(terms) == 1:
        return terms[0]
    mid = len(terms) // 2
    return f'({_sum(terms[:mid])}+{_sum(terms[mid:])})'


def pieces(out, side):
    """The source pieces one side plays: [{'a', 'b', 't0', 'speed'}], source seconds [a, b) to output from t0."""
    got = []
    for o in out:
        s = o[side]
        if s and s['used'] > 0:
            got.append({'a': s['a'], 'b': s['a'] + s['used'], 't0': o['t0'], 'speed': s['speed']})
    return got


def blanks(out, side):
    """Output stretches [t0, t1) where a side has nothing to show."""
    got = []
    for o in out:
        if o[side] is None:
            if got and abs(got[-1][1] - o['t0']) < 1e-6:
                got[-1] = (got[-1][0], o['t1'])
            else:
                got.append((o['t0'], o['t1']))
    return got


def video_chain(ps, blank, fps=FPS, size=PANE):
    """Filters that turn one source into its pane: keep the frames the pieces use, move them to output time, fill
    holds with repeats (fps), scale, black over the blanks."""
    w, h = size
    if not ps:
        return f'trim=end=0.001,scale={w}:{h},setsar=1,fps={fps}:start_time=0,drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill'
    keep = _sum([f"between(t,{p['a']:.6f},{p['b'] - 1e-4:.6f})" for p in ps])
    expr = _tree(ps, lambda p: f"({p['t0']:.6f}+(T-{p['a']:.6f})/{p['speed']:.6f})")
    f = [f"select='{keep}'", f"setpts='({expr})/TB'", f'fps={fps}:start_time=0', f'scale={w}:{h}:flags=bicubic', 'setsar=1']
    f += [f"drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill:enable='between(t,{a:.4f},{b - 1e-4:.4f})'" for a, b in blank]
    return ','.join(f)


def _atempo(speed):
    chain = []
    while speed > 2.0:
        chain.append('atempo=2.0')
        speed /= 2.0
    while speed < 0.5:
        chain.append('atempo=0.5')
        speed /= 0.5
    if abs(speed - 1.0) > 1e-4:
        chain.append(f'atempo={speed:.6f}')
    return chain


def audio_graph(out, side, label, total):
    """Filter-graph lines that build the chosen side's sound on the output clock into [aout]; None when it has none."""
    ps = [(o, o[side]) for o in out]
    if all(s is None or (s['speed'] == 1.0 and s['hold'] == 0.0) for _, s in ps):
        runs = pieces(out, side)
        contiguous = all(abs((p['a'] - p['t0']) - (runs[0]['a'] - runs[0]['t0'])) < 1e-6 for p in runs) if runs else False
        if contiguous and runs and abs(runs[0]['t0']) < 1e-6 and not blanks(out, side):
            a = runs[0]['a']
            return [f'[{label}]atrim={a:.6f}:{a + total:.6f},asetpts=PTS-STARTPTS,aresample=48000,apad=whole_dur={total:.6f},atrim=0:{total:.6f}[aout]']
    lines, names = [], []
    used = [(k, o, s) for k, (o, s) in enumerate(ps) if s is not None and s['used'] > 0]
    if used:
        lines.append(f'[{label}]aresample=48000,asplit={len(used)}' + ''.join(f'[as{k}]' for k, _, _ in used))
    for k, (o, s) in enumerate(ps):
        d = o['t1'] - o['t0']
        if s is None or s['used'] <= 0:
            lines.append(f'aevalsrc=0:c=stereo:s=48000:d={d:.6f}[ap{k}]')
        else:
            chain = [f"atrim={s['a']:.6f}:{s['a'] + s['used']:.6f}", 'asetpts=PTS-STARTPTS'] + _atempo(s['speed'])
            chain += [f'apad=whole_dur={d:.6f}', f'atrim=0:{d:.6f}', 'aformat=channel_layouts=stereo']
            lines.append(f'[as{k}]' + ','.join(chain) + f'[ap{k}]')
        names.append(f'[ap{k}]')
    lines.append(''.join(names) + f'concat=n={len(names)}:v=0:a=1[aout]')
    return lines


# --- labels (the chrome) ---------------------------------------------------------------------------------------------

def _text(c, x, y, s, scale=2, color=INK):
    return c.text(x, y, str(s).upper(), scale, color)


def _framing_ok(fr):
    """Measured framing worth showing: a subject centre inside the frame and a visible size."""
    x, h = (fr.get('x') or {}).get('median'), (fr.get('height') or {}).get('median')
    return x is not None and h is not None and 0 <= x <= 1 and h >= 0.02


def _clock(t):
    m, s = divmod(max(0.0, t), 60)
    return f'{int(m)}:{s:05.2f}'


def _delta_colour(ref_len, our_len):
    if not ref_len or our_len is None:
        return DIM
    pct = abs(our_len - ref_len) / ref_len
    return GOOD if pct <= 0.15 else WARN if pct <= 0.4 else BAD


class Chrome:
    """Draws the labels around the panes for every output frame, into one RGB strip: in the left/right layout the
    196 rows above the panes and the 344 below, stacked (1920x540); in top/bottom, the 960x1080 column beside them."""

    def __init__(self, out, info, layout='lr', fps=FPS):
        self.out, self.info, self.layout, self.fps = out, info, layout, fps
        self.w, self.h = (1920, TOP + BOTTOM) if layout == 'lr' else (960, 1080)
        self.total = out[-1]['t1'] if out else 0.0
        self.cache = {}

    def _side_lines(self, o, side, clip):
        s, info = o[side], self.info
        name = 'REFERENCE' if side == 'ref' else 'VIDEOCRAFT'
        if s is None:
            return f'{name} · NO MATCHING SHOT', ['(black)'], DIM
        seg = s['seg']
        length = seg['b'] - seg['a']
        if seg['kind'] == 'black':
            head = f'{name} · BLACK' + (f' AFTER SHOT {seg["n"]}' if seg['n'] else '')
        elif side == 'ref':
            head = f'{name} · SHOT {seg["n"]} · {seg.get("camera", "-")}'
        else:
            head = f'{name} · ' + (f'SHOT {seg["n"]}' if seg['n'] is not None else (clip or '-')) + f' · {info["rigs"].get(clip, "-")}'
        if info.get('align') == 'time':     # pieces of shots play at their own speed: no fit to report
            lines = [f'LENGTH {length:.2f} S']
        else:
            lines = [f'LENGTH {length:.2f} S' + ('' if abs(s['speed'] - 1) < 1e-3 else f'  PLAYED AT {s["speed"]:.2f}x')
                     + (f'  HOLD {s["hold"]:.2f} S' if s['hold'] > 0.01 else '')
                     + (f'  CUT {length - s["used"]:.2f} S' if length - s['used'] > 0.01 else '')]
        if side == 'ours' and seg['kind'] == 'shot':
            lines.append(clip + (f'  ({len(seg["clips"])} CLIPS)' if len(seg['clips']) > 1 else ''))
            fr, fov = info['framing'].get(clip) or {}, info['fov'].get(clip)
            bits = []
            if fov:
                bits.append(f'FOV {fov}')
            if _framing_ok(fr):
                bits.append(f'SUBJECT X {fr["x"]["median"]:.2f} H {fr["height"]["median"]:.2f}')
            if bits:
                lines.append('  '.join(bits))
        return head, lines, REF_C if side == 'ref' else OUR_C

    def _clip(self, o, t):
        """The name of our clip on screen at output time t (a segment can join several clips)."""
        s = o['ours']
        if s is None:
            return None
        src = self._source_time(o, 'ours', t)
        clips = s['seg']['clips']
        return next((c['name'] for c in clips if c['a'] - 1e-9 <= src < c['b']), clips[-1]['name'])

    def _background(self, k, clip_key):
        key = (k, clip_key)
        if key in self.cache:
            return self.cache[key]
        o = self.out[k]
        c = Canvas(self.w, self.h, BG)
        info = self.info
        ref_seg = (o['ref'] or {}).get('seg')
        our_seg = (o['ours'] or {}).get('seg')
        ref_len = ref_seg['b'] - ref_seg['a'] if ref_seg and info.get('align') != 'time' else None
        our_len = our_seg['b'] - our_seg['a'] if our_seg else None
        n_total = info['shots']
        lead_seg = our_seg if info['lead'] == 'ours' else ref_seg
        if self.layout == 'lr':
            _text(c, 24, 16, info['title'], 3, INK)
            _text(c, 24, 50, info['subtitle'], 2, DIM)
            if lead_seg and lead_seg['kind'] == 'shot' and lead_seg['n'] is not None:
                _text(c, 24, 86, f'SHOT {lead_seg["n"]} / {n_total}', 6, INK)
            elif lead_seg:
                _text(c, 24, 86, 'BLACK' if lead_seg['kind'] == 'black' else lead_seg['clips'][0]['name'] if 'clips' in lead_seg else '-', 6, DIM)
            if ref_len is not None and our_len is not None:
                d = our_len - ref_len
                s = f'DELTA {d:+.2f} S ({d / ref_len * 100:+.0f}%)' if ref_len else f'DELTA {d:+.2f} S'
                _text(c, 1920 - 24 - text_width(s, 4), 92, s, 4, _delta_colour(ref_len, our_len))
            for side, x0 in (('ref', 0), ('ours', 960)):
                head, lines, col = self._side_lines(o, side, clip_key)
                y = TOP + 12
                c.fill(x0, TOP, 960, 4, col)
                _text(c, x0 + 20, y + 8, head, 3, col)
                for j, line in enumerate(lines):
                    _text(c, x0 + 20, y + 52 + j * 30, line, 2, INK if j == 0 else DIM)
            self._lanes(c, 24, 150, 1920 - 48)
        else:
            _text(c, 24, 16, info['title'], 3, INK)
            _text(c, 24, 50, info['subtitle'], 2, DIM)
            for side, y0 in (('ref', 120), ('ours', 620)):
                head, lines, col = self._side_lines(o, side, clip_key)
                c.fill(0, y0 - 8, 6, 300, col)
                _text(c, 24, y0, head, 3, col)
                for j, line in enumerate(lines):
                    _text(c, 24, y0 + 44 + j * 30, line, 2, INK if j == 0 else DIM)
            if lead_seg and lead_seg['kind'] == 'shot' and lead_seg['n'] is not None:
                _text(c, 24, 420, f'SHOT {lead_seg["n"]} / {n_total}', 5, INK)
            if ref_len is not None and our_len is not None:
                d = our_len - ref_len
                _text(c, 24, 470, f'DELTA {d:+.2f} S' + (f' ({d / ref_len * 100:+.0f}%)' if ref_len else ''), 3, _delta_colour(ref_len, our_len))
            self._lanes(c, 24, 1000, 960 - 48)
        self.cache[key] = bytes(c.px)
        return self.cache[key]

    def _lanes(self, c, x, y, w):
        """Two lanes of shot boundaries at each film's own pace (reference above, ours below)."""
        for row, (segs, total, col) in enumerate(((self.info['ref_segs'], self.info['ref_span'], REF_C), (self.info['our_segs'], self.info['our_span'], OUR_C))):
            yy = y + row * 18
            if not total:
                continue
            a0 = segs[0]['a'] if segs else 0
            for s in segs:
                x0 = x + int((s['a'] - a0) / total * w)
                x1 = x + int((s['b'] - a0) / total * w)
                c.fill(x0, yy, max(1, x1 - x0 - 1), 12, (40, 40, 46) if s['kind'] == 'black' else tuple(v // 2 for v in col))
                c.fill(x0, yy, 1, 12, col)

    def frame(self, i):
        t = i / self.fps
        k = self._segment(t)
        o = self.out[k]
        px = bytearray(self._background(k, self._clip(o, t)))
        c = Canvas.__new__(Canvas)
        c.w, c.h, c.px = self.w, self.h, px
        clock = _clock(t)
        if self.layout == 'lr':
            _text(c, (1920 - text_width(clock, 7)) // 2, 82, clock, 7, MARK)
            for side, x0 in (('ref', 0), ('ours', 960)):
                src = self._source_time(o, side, t)
                if src is not None:
                    s = f'SOURCE {_clock(src)}'
                    _text(c, x0 + 940 - text_width(s, 2), TOP + 20, s, 2, DIM)
            self._cursors(c, o, t, 24, 150, 1920 - 48)
        else:
            _text(c, 24, 330, clock, 7, MARK)
            for side, y0 in (('ref', 120), ('ours', 620)):
                src = self._source_time(o, side, t)
                if src is not None:
                    _text(c, 24, y0 + 150, f'SOURCE {_clock(src)}', 2, DIM)
            self._cursors(c, o, t, 24, 1000, 960 - 48)
        return px

    def _cursors(self, c, o, t, x, y, w):
        for row, (side, total, segs) in enumerate((('ref', self.info['ref_span'], self.info['ref_segs']), ('ours', self.info['our_span'], self.info['our_segs']))):
            src = self._source_time(o, side, t)
            if src is None or not total or not segs:
                continue
            cx = x + int((src - segs[0]['a']) / total * w)
            c.fill(cx - 1, y + row * 18 - 3, 3, 18, MARK)

    def _source_time(self, o, side, t):
        s = o[side]
        if s is None:
            return None
        dt = t - o['t0']
        played = s['used'] / s['speed'] if s['speed'] else 0
        return s['a'] + min(dt, played) * s['speed']

    def _segment(self, t):
        lo, hi = 0, len(self.out) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.out[mid]['t0'] <= t + 1e-9:
                lo = mid
            else:
                hi = mid - 1
        return lo


# --- the run ---------------------------------------------------------------------------------------------------------

def camera_family(camera):
    """'moving' for the reference's lead tracks and our lead/follow rigs, 'still' for statics, inserts, cut-ins and
    graphic cards and our fixed rigs; used for the table's camera-match column."""
    c = (camera or '').lower()
    if c in ('-', '', 'black'):
        return None
    return 'moving' if any(k in c for k in ('lead', 'track', 'follow', 'orbit', 'dolly', 'swing')) else 'still'


def _our_info(it):
    plan = it.plan()
    metrics = {}
    try:
        metrics = json.loads((it.measure / 'metrics.json').read_text())
    except (OSError, json.JSONDecodeError):
        pass
    rigs = {s['name']: ((s.get('camera') or {}).get('rig') or '-') for s in plan.get('shots', [])}
    fov = {}
    for s in plan.get('shots', []):
        f = (s.get('camera') or {}).get('fov')
        fov[s['name']] = '-'.join(str(round(v)) for v in f) if isinstance(f, list) else (round(f) if isinstance(f, (int, float)) else None)
    return plan, rigs, fov, metrics.get('framing') or {}


def rows(out, info):
    """One row per output segment that has a shot on either side: the table of side-by-side.md/.json."""
    got = []
    for o in out:
        r, u = (o['ref'] or {}).get('seg'), (o['ours'] or {}).get('seg')
        if (r or u) and (r or u)['kind'] == 'black' and not ((r and r['kind'] == 'shot') or (u and u['kind'] == 'shot')):
            kind = 'black'
        else:
            kind = 'shot'
        row = {'kind': kind, 'n': (r or u)['n'], 't0': o['t0'], 't1': o['t1'],
               'ref': None if r is None else {'start': round(r['a'], 3), 'seconds': round(r['b'] - r['a'], 3), 'camera': r.get('camera'),
                                              'speed': round(o['ref']['speed'], 3), 'hold': round(o['ref']['hold'], 3)},
               'ours': None}
        if u is not None:
            clips = []
            for c in u['clips']:
                fr = info['framing'].get(c['name']) or {}
                clips.append({'name': c['name'], 'seconds': round(c['b'] - c['a'], 3), 'rig': info['rigs'].get(c['name'], '-'),
                              'fov': info['fov'].get(c['name']), 'subject': fr.get('subject'), 'from': fr.get('from'),
                              'x': (fr.get('x') or {}).get('median'), 'y': (fr.get('y') or {}).get('median'),
                              'height': (fr.get('height') or {}).get('median'), 'size_change': fr.get('size_change')})
            row['ours'] = {'start': round(u['a'], 3), 'seconds': round(u['b'] - u['a'], 3), 'clips': clips,
                           'speed': round(o['ours']['speed'], 3), 'hold': round(o['ours']['hold'], 3)}
        if row['ref'] and row['ours']:
            d = row['ours']['seconds'] - row['ref']['seconds']
            row['delta'] = round(d, 3)
            row['delta_pct'] = round(d / row['ref']['seconds'] * 100, 1) if row['ref']['seconds'] else None
            fam = camera_family(row['ref']['camera'])
            ours_fam = {camera_family(c['rig']) for c in row['ours']['clips']}
            row['camera_match'] = None if fam is None or kind == 'black' else fam in ours_fam
        got.append(row)
    return got


def _framing_text(c):
    if not _framing_ok({'x': {'median': c.get('x')}, 'height': {'median': c.get('height')}}):
        return '-'
    s = f"x {c['x']:.2f} · h {c['height']:.2f}"
    if c.get('size_change'):
        s += f" · size ±{c['size_change'] * 100:.0f}%"
    return s + ('' if c.get('from') == 'camera' else f" ({c.get('subject') or '?'}, {c.get('from') or '?'})")


def write_table(table, info, path):
    L = [f"# Side by side: {info['ref_name']} {info['ref_from']:g}-{info['ref_to']:g} s against {info['our_name']}", '',
         f"Align {info['align']}, lead {info['lead']}, fit {info['fit']}, audio {info['audio']}; reference shots from {info['ref_source']}.", '',
         'Lengths in seconds. Framing is our measured subject centre (x, 0-1 across the frame) and height (share of the frame '
         'height), medians over the shot, with its size change; "camera" means the camera rig placed it, else the biggest '
         'actor in view. The reference has no measured framing: compare it with the video and the sheet.', '',
         '| # | ref start | ref s | ours s | Δ s | Δ % | reference camera | our shot | rig | fov | our framing | camera |',
         '|--:|--:|--:|--:|--:|--:|:--|:--|:--|--:|:--|:--|']
    for r in table:
        ref, ours = r['ref'], r['ours']
        label = (f"after {r['n']}" if r['n'] else 'black') if r['kind'] == 'black' else str(r['n']) if r['n'] is not None else '-'
        clips = ours['clips'] if ours else [None]
        for j, c in enumerate(clips):
            first = j == 0
            cells = [label if first else '', f"{ref['start']:.2f}" if ref and first else '', f"{ref['seconds']:.2f}" if ref and first else ('-' if first else ''),
                     ((f"{ours['seconds']:.2f}" if first else '') + (f" ({c['seconds']:.2f})" if len(clips) > 1 else '')) if ours else '-',
                     f"{r['delta']:+.2f}" if first and 'delta' in r else '', f"{r['delta_pct']:+.0f}" if first and r.get('delta_pct') is not None else '',
                     (ref['camera'] if ref else '(none)') if first else '', c['name'] if c else '(none)', c['rig'] if c else '',
                     str(c['fov']) if c and c['fov'] is not None else '', _framing_text(c) if c else '',
                     ('' if r.get('camera_match') is None else 'match' if r['camera_match'] else '**differs**') if first else '']
            L.append('| ' + ' | '.join(cells) + ' |')
    shots = [r for r in table if r['kind'] == 'shot' and r['ref'] and r['ours']]
    if shots:
        within = sum(1 for r in shots if r.get('delta_pct') is not None and abs(r['delta_pct']) <= 15)
        mism = [str(r['n']) for r in shots if r.get('camera_match') is False]
        L += ['', f"{len(shots)} paired shots; {within} within ±15 % of the reference's length; camera family differs on: {', '.join(mism) or 'none'}.",
              f"Reference total {info['ref_to'] - info['ref_from']:.2f} s, ours {info['our_span']:.2f} s."]
    path.write_text('\n'.join(L) + '\n')


def contact_sheet(table, ref_video, our_video, ref_fps, our_fps, path, tile=(480, 270)):
    """One row per shot pair: the middle frame of the reference's shot and of ours, with lengths and cameras."""
    shots = [r for r in table if r['kind'] == 'shot']
    mid = lambda side: [None if r[side] is None else r[side]['start'] + r[side]['seconds'] / 2 for r in shots]
    ref_mid = [None if t is None else int(round(t * ref_fps)) for t in mid('ref')]
    our_mid = [None if t is None else int(round(t * our_fps)) for t in mid('ours')]
    fr = grab(ref_video, [f for f in ref_mid if f is not None], tile)
    fo = grab(our_video, [f for f in our_mid if f is not None], tile)
    w, h = tile
    left, gap, head, label = 300, 8, 56, 28
    c = Canvas(left + 2 * (w + gap) + gap, head + len(shots) * (h + label + gap) + gap, BG)
    _text(c, gap, 14, 'REFERENCE (LEFT) · VIDEOCRAFT (RIGHT) · MIDDLE FRAME OF EACH SHOT', 2, INK)
    for k, r in enumerate(shots):
        y = head + k * (h + label + gap)
        _text(c, gap, y + 4, f"SHOT {r['n']}", 4, INK)
        if r['ref']:
            _text(c, gap, y + 48, f"REF {r['ref']['seconds']:.2f} S", 2, REF_C)
            _text(c, gap, y + 70, r['ref']['camera'] or '-', 2, REF_C)
        if r['ours']:
            _text(c, gap, y + 100, f"OURS {r['ours']['seconds']:.2f} S", 2, OUR_C)
            _text(c, gap, y + 122, ', '.join(sorted({x['rig'] for x in r['ours']['clips']})), 2, OUR_C)
            fov = r['ours']['clips'][0]['fov']
            if fov is not None:
                _text(c, gap, y + 144, f'FOV {fov}', 2, OUR_C)
            x0 = r['ours']['clips'][0]
            if x0.get('height') is not None and x0.get('from') == 'camera':
                _text(c, gap, y + 166, f"SUBJECT H {x0['height']:.2f}", 2, OUR_C)
        if 'delta' in r:
            _text(c, gap, y + 196, f"DELTA {r['delta']:+.2f} S", 2, _delta_colour(r['ref']['seconds'], r['ours']['seconds']))
        if r.get('camera_match') is False:
            _text(c, gap, y + 222, 'CAMERA DIFFERS', 2, BAD)
        for j, (frames, f, name) in enumerate(((fr, ref_mid[k], 'REFERENCE'), (fo, our_mid[k], 'VIDEOCRAFT'))):
            x = left + gap + j * (w + gap)
            c.fill(x - 1, y - 1, w + 2, h + 2, (60, 60, 70))
            if f is not None and frames.get(f):
                c.paste(frames[f], w, h, x, y)
            else:
                _text(c, x + 20, y + h // 2, '(NO MATCHING SHOT)', 2, DIM)
            sub = r['ours']['clips'][0]['name'] if j == 1 and r['ours'] else f"{name} SHOT {r['n']}"
            _text(c, x + 4, y + h + 7, sub, 2, DIM)
    return c.save(path)


def side_by_side(ref_video, start, end, it, out_path, align='shots', shots=None, lead='ours', mode='auto', audio='ours',
                 layout='lr', our_video=None, say=print):
    """Writes the side-by-side film and, beside it, side-by-side.md/.json and side-by-side-sheet.jpg. Returns the table."""
    from videocraft import measure, timeline
    ref_video, out_path = Path(ref_video), Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ref_probe, our_video = measure.probe(ref_video), Path(our_video or it.cut / 'master.mp4')
    our_probe = measure.probe(our_video)
    listed = load_shot_list(shots) if shots else None
    start = start if start is not None else (listed or {}).get('from') or 0.0
    end = end if end is not None else (listed or {}).get('to') or ref_probe['frames'] / ref_probe['fps']
    if listed:
        ref = ref_segments(listed['shots'], start, end)
        ref_source = str(shots)
    else:
        say(f'Finding the reference\'s cuts with measure ({start:g}-{end:g} s)…')
        ref = detected_segments(measure.measure_video(ref_video, start, end)['picture'], start)
        ref_source = 'measure\'s cut detection'
    fps = int(round(our_probe['fps'])) or FPS
    ours = our_segments(timeline.clips(it), fps)
    plan, rigs, fov, framing = _our_info(it)
    if align == 'time':
        out = plan_time(ref, ours, start, lead)
    else:
        out = plan_output(pair(ref, ours, lead), lead, mode)
    total = out[-1]['t1']
    frames = int(round(total * FPS))
    info = {'rigs': rigs, 'fov': fov, 'framing': framing, 'lead': lead, 'align': align, 'fit': mode, 'audio': audio,
            'shots': sum(1 for s in (ours if lead == 'ours' else ref) if s['kind'] == 'shot' and s['n'] is not None),
            'ref_segs': ref, 'our_segs': ours, 'ref_span': (ref[-1]['b'] - ref[0]['a']) if ref else 0,
            'our_span': (ours[-1]['b'] - ours[0]['a']) if ours else 0, 'ref_name': ref_video.name, 'ref_from': start, 'ref_to': end,
            'our_name': f'{it.path.parent.name}/{it.name}', 'ref_source': ref_source,
            'title': f'REFERENCE  VS  VIDEOCRAFT {plan.get("name", "")}'.strip(),
            'subtitle': f'ALIGN {align} · LEAD {lead} · FIT {mode} · AUDIO {audio} · REFERENCE {start:g}-{end:g} S'}
    paired = out if align == 'shots' else plan_output(pair(ref, ours, lead), lead, mode)
    table = rows(paired, info)          # the table and sheet are per shot pair whatever the film's alignment
    (out_path.parent / 'side-by-side.json').write_text(json.dumps({'reference': str(ref_video), 'from': start, 'to': end, 'run': str(it.path),
                                                                   'video': str(out_path), 'align': align, 'lead': lead, 'fit': mode,
                                                                   'audio': audio, 'rows': table}, indent=2) + '\n')
    write_table(table, info, out_path.parent / 'side-by-side.md')
    sheet = contact_sheet(table, ref_video, our_video, ref_probe['fps'], our_probe['fps'], out_path.parent / 'side-by-side-sheet.jpg')
    say(f'SHEET    {sheet}')
    chrome = Chrome(out, info, layout)
    graph = [f"[1:v]{video_chain(pieces(out, 'ref'), blanks(out, 'ref'))}[r]",
             f"[0:v]{video_chain(pieces(out, 'ours'), blanks(out, 'ours'))}[o]"]
    if layout == 'lr':
        graph += [f'[2:v]split=2[c1][c2]', f'[c1]crop=1920:{TOP}:0:0[top]', f'[c2]crop=1920:{BOTTOM}:0:{TOP}[bot]',
                  '[r][o]hstack=inputs=2[mid]', '[top][mid][bot]vstack=inputs=3,format=yuv420p[v]']
    else:
        graph += ['[r][o]vstack=inputs=2[col]', '[col][2:v]hstack=inputs=2,format=yuv420p[v]']
    maps = ['-map', '[v]']
    side = {'ours': ('ours', '0:a'), 'ref': ('ref', '1:a')}.get(audio)
    if side and (our_probe['audio'] if audio == 'ours' else ref_probe['audio']):
        graph += audio_graph(out, side[0], side[1], total)
        maps += ['-map', '[aout]', '-c:a', 'aac', '-b:a', '192k']
    log = out_path.with_suffix('.ffmpeg.log')
    cmd = [tools.ffmpeg(), '-v', 'error', '-y', '-t', f'{(our_probe["frames"] / our_probe["fps"]) + 1:.3f}', '-i', str(our_video),
           '-t', f'{end + 1:.3f}', '-i', str(ref_video),
           '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{chrome.w}x{chrome.h}', '-r', str(FPS), '-i', '-',
           '-filter_complex', ';'.join(graph), *maps, '-c:v', 'libx264', '-preset', 'medium', '-crf', '20', '-r', str(FPS),
           '-frames:v', str(frames), '-t', f'{total:.6f}', '-movflags', '+faststart', str(out_path)]
    say(f'Rendering {frames} frames ({total:.2f} s, {len(out)} segments) → {out_path}')
    with open(log, 'w') as err:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=err)
        try:
            for i in range(frames):
                proc.stdin.write(chrome.frame(i))
            proc.stdin.close()
        except BrokenPipeError:
            pass
        code = proc.wait()
    if code != 0:
        raise SystemExit(f'ffmpeg failed ({code}); see {log}\n' + log.read_text()[-2000:])
    log.unlink(missing_ok=True)
    return out_path, table
