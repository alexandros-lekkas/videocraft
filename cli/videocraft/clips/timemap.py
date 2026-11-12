"""Time mapping: which source run, shot and frame every frame of a master (or of an assembly) shows, and back.

A *segment* is one clip of the master's timeline: master frames [out_start, out_start + out_frames) show frames
[src_in, src_out) of shot `shot` of the iteration at `run` (for an assembly, the part's own iteration). Everything
that knows something about a shot (text.json words, sounds.csv, marks.json, actors.csv) is mapped into master time
through these, so moments and shorts work on a single run and on an assembly alike.

Words are intervals: a caption word's onset is the frame it pops in; it lasts until the next word of the same line,
and a line's last word lasts LAST_WORD seconds (or to the end of the item). With a voice timing (edit.json `voice`
entries with `words` = [{w, start, end}] in seconds of the shot) the spoken interval is used instead. A cut never
lands strictly inside a word interval (`snap_start`, `snap_end`). Pure functions except the readers at the bottom.
"""
import bisect
import json
from dataclasses import dataclass, field
from pathlib import Path

LAST_WORD = 0.35       # seconds a line's last word is taken to last when nothing says otherwise
SNAP_SHOT = 1.5        # a range end moves to a shot boundary this close (seconds) before it snaps to words


@dataclass
class Segment:
    out_start: int
    out_frames: int
    kind: str                     # shot | black | card
    shot: str | None = None
    src_in: int = 0
    src_out: int = 0
    speed: float = 1.0
    run: str | None = None        # the iteration folder whose take/shots/<shot>/ this clip shows
    part: int | None = None       # assembly part index (None in a plain run)
    clip: int = 0                 # the clip's index in its own run's timeline
    src_map: list | None = None   # speed ramps: source frame shown on each output frame of the clip

    @property
    def out_end(self):
        return self.out_start + self.out_frames

    def out_frame(self, frame):
        """The master frame (fractional) where this clip shows source `frame` first, or None outside the clip."""
        if self.kind != 'shot' or not self.src_in <= frame < self.src_out:
            return None
        if self.src_map:
            return float(self.out_start + bisect.bisect_left(self.src_map, frame))
        return self.out_start + (frame - self.src_in) / (self.speed or 1.0)

    def src_frame(self, out):
        """The source frame shown on master frame `out` (an integer), or None outside the clip or on black."""
        if self.kind != 'shot' or not self.out_start <= out < self.out_end:
            return None
        k = out - self.out_start
        if self.src_map:
            return self.src_map[min(k, len(self.src_map) - 1)]
        return min(self.src_out - 1, self.src_in + int(k * (self.speed or 1.0)))


@dataclass
class Word:
    text: str
    start: float          # seconds in the master
    end: float
    key: bool = False
    line: str = ''        # an id shared by the words of one caption or voice line
    shot: str | None = None
    part: int | None = None
    spoken: bool = False  # from a voice timing (else from the caption)


@dataclass
class Map:
    fps: int
    frames: int
    segments: list
    width: int = 1920
    height: int = 1080
    parts: list = field(default_factory=list)   # assembly parts: {index, kind, title, run, out_start, out_frames}

    @property
    def seconds(self):
        return self.frames / self.fps

    def locate(self, out):
        """(segment, source frame) shown on master frame `out`; (segment, None) on black or a card."""
        for s in self.segments:
            if s.out_start <= out < s.out_end:
                return s, s.src_frame(out)
        return None, None

    def to_master(self, run, shot, frame):
        """Every master time (seconds) where source `frame` of `shot` (of iteration `run`) plays; usually one."""
        out = []
        for s in self.segments:
            if s.shot == shot and (run is None or s.run == run):
                f = s.out_frame(frame)
                if f is not None:
                    out.append(f / self.fps)
        return out

    def boundaries(self):
        """Seconds in the master where a clip starts, plus the end: the places a short may begin or end on a cut."""
        return sorted({s.out_start / self.fps for s in self.segments} | {self.frames / self.fps})


def from_timeline(data, run=None, part=None, offset=0, fps=None):
    """Segments of one cut/timeline.json (a dict), shifted by `offset` master frames and converted to `fps`."""
    src_fps = int(data.get('fps') or 60)
    fps = fps or src_fps
    k = fps / src_fps
    out = []
    for i, c in enumerate(data.get('clips', [])):
        start = offset + int(round(int(c.get('out_start', 0)) * k))
        frames = max(1, int(round(int(c.get('out_frames', 0)) * k)))
        kind = c.get('kind', 'shot')
        src_in, src_out = int(c.get('src_in') or 0), int(c.get('src_out') or 0)
        speed = (src_out - src_in) / frames if kind == 'shot' and frames else 1.0
        out.append(Segment(out_start=start, out_frames=frames, kind=kind, shot=c.get('shot'), src_in=src_in, src_out=src_out,
                           speed=speed, run=c.get('run', run), part=c.get('part', part), clip=int(c.get('index', i)),
                           src_map=(c.get('src_map') if k == 1 else None) or None))
    return out


def load(it):
    """The map of an iteration: an assembly's timeline.json (parts with their own clips) or a run's cut/timeline.json."""
    f = Path(it.cut) / 'timeline.json'
    if f.exists():
        data = json.loads(f.read_text())
    else:
        from videocraft import timeline as tl
        data = {'fps': it.plan()['output']['fps'], 'clips': tl.clips(it)}
        data['frames'] = sum(c['out_frames'] for c in data['clips'])
    fps = int(data.get('fps') or 60)
    if 'parts' in data:     # an assembly: its clips already carry run, part and assembly frames
        segs = from_timeline(data, fps=fps)
        return Map(fps=fps, frames=int(data['frames']), segments=segs, width=int(data.get('width', 1920)),
                   height=int(data.get('height', 1080)), parts=data['parts'])
    segs = from_timeline(data, run=str(Path(it.path).resolve()), fps=fps)
    plan = it.plan()
    frames = int(data.get('frames') or max((s.out_end for s in segs), default=0))
    return Map(fps=fps, frames=frames, segments=segs, width=int(plan['output']['width']), height=int(plan['output']['height']))


# ---- Words and snapping (pure) ----

def caption_words(items, fps, to_master, shot=None, part=None, prefix=''):
    """Words of one shot's text.json items (the text layer's records), as master-time Words. `to_master(frame)` maps a
    source frame to its master times (a list: a shot may play twice in a montage)."""
    out = []
    for n, item in enumerate(items):
        words = item.get('words') or []
        if not words or item.get('first_frame') is None:
            continue
        last = item.get('last_frame')
        end_frame = (last + 1) if last is not None else None
        onsets = [int(w.get('frame', item['first_frame'])) for w in words]
        for j, w in enumerate(words):
            a = onsets[j]
            b = onsets[j + 1] if j + 1 < len(words) else a + int(round(LAST_WORD * fps))
            if end_frame is not None:
                b = min(b, end_frame)
            b = max(b, a + 1)
            text = str(w.get('w', w.get('word', '')))
            for t0 in to_master(a):
                out.append(Word(text=text.lstrip('*'), start=t0, end=t0 + (b - a) / fps, key=bool(w.get('key')) or text.startswith('*'),
                                line=f'{prefix}{shot}:{n}', shot=shot, part=part))
    return out


def inside_word(t, words, eps=1e-6):
    """The word whose interval holds `t` strictly inside it, or None."""
    for w in words:
        if w.start + eps < t < w.end - eps:
            return w
    return None


def line_bounds(word, words):
    same = [w for w in words if w.line == word.line]
    return min(w.start for w in same), max(w.end for w in same)


def snap_start(t, cuts, words, tolerance=SNAP_SHOT, floor=0.0):
    """A start at or before `t`: the latest shot boundary within `tolerance` before it that is not inside a word, else
    the start of the line `t` is inside (never mid-word), else `t` itself."""
    for c in sorted(cuts, reverse=True):
        if t - tolerance - 1e-9 <= c <= t + 1e-9 and c >= floor and not inside_word(c, words):
            return c
    w = inside_word(t, words)
    if w:
        return max(floor, line_bounds(w, words)[0])
    return max(floor, t)


def snap_end(t, cuts, words, tolerance=SNAP_SHOT, ceiling=None):
    """An end at or after `t`: the earliest shot boundary within `tolerance` after it that is not inside a word, else
    the end of the word `t` is inside, else `t` itself. Never past `ceiling` (the master's end)."""
    for c in sorted(cuts):
        if t - 1e-9 <= c <= t + tolerance + 1e-9 and (ceiling is None or c <= ceiling + 1e-9) and not inside_word(c, words):
            return c
    w = inside_word(t, words)
    end = w.end if w else t
    return min(end, ceiling) if ceiling is not None else end


def frame_range(start, end, fps):
    """Seconds to whole master frames [a, b)."""
    return int(round(start * fps)), int(round(end * fps))


def sub_timeline(segments, a, b):
    """The clips that cover master frames [a, b), cut to that range: [(segment, src_in, src_out, out_frames)] in order.
    A constant-speed clip is cut at the source frame that maps to the range edge; a ramped clip through its src_map."""
    out = []
    for s in segments:
        lo, hi = max(a, s.out_start), min(b, s.out_end)
        if hi <= lo:
            continue
        if s.kind != 'shot':
            out.append((s, None, None, hi - lo))
            continue
        if s.src_map:
            src_in = s.src_map[lo - s.out_start]
            src_out = s.src_map[hi - 1 - s.out_start] + 1
        else:
            src_in = s.src_in + int(round((lo - s.out_start) * s.speed))
            src_out = min(s.src_out, s.src_in + int(round((hi - s.out_start) * s.speed)))
        out.append((s, src_in, max(src_in + 1, src_out), hi - lo))
    return out


# ---- Readers ----

def _json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def shot_dir(seg):
    return Path(seg.run) / 'take' / 'shots' / seg.shot


def words(m):
    """Every word of every caption (and voice line, when timed) in the master, in time order."""
    out, seen = [], set()
    for s in m.segments:
        if s.kind != 'shot' or (s.run, s.shot) in seen:
            continue
        seen.add((s.run, s.shot))
        run, shot = s.run, s.shot
        to_master = lambda f, run=run, shot=shot: m.to_master(run, shot, f)
        data = _json(shot_dir(s) / 'text.json')
        if data:
            out += caption_words(data.get('items', []), m.fps, to_master, shot, s.part, prefix=f'{s.part}:' if s.part is not None else '')
    # Voice timings, when the dialogue resolver wrote words into edit.json's voice entries.
    seen_runs = {s.run for s in m.segments if s.run}
    for run in seen_runs:
        edit = _json(Path(run) / 'edit.json') or {}
        for n, line in enumerate(edit.get('voice') or []):
            if not isinstance(line, dict) or not line.get('words') or not line.get('shot'):
                continue
            at = float(line.get('at', 0))
            for w in line['words']:
                if not isinstance(w, dict) or 'start' not in w:
                    continue
                f0 = int(round((at + float(w['start'])) * m.fps))
                f1 = int(round((at + float(w.get('end', w['start'] + LAST_WORD))) * m.fps))
                for t0 in m.to_master(run, line['shot'], f0):
                    text = str(w.get('w', w.get('word', '')))
                    out.append(Word(text=text.lstrip('*'), start=t0, end=t0 + max(1, f1 - f0) / m.fps, key=text.startswith('*') or bool(w.get('key')),
                                    line=f'voice:{run}:{n}', shot=line['shot'], spoken=True))
    return sorted(out, key=lambda w: w.start)
