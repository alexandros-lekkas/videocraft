"""Where each frame of each shot lands in the cut: cut/timeline.json, written by the picture edit just before the mix.

    {"fps": 60, "frames": N, "clips": [{"index", "kind": "shot" | "black", "shot", "src_in", "src_out", "out_start",
                                        "out_frames", "speed", "fade_in", "fade_out"}]}

Frames throughout; src_* in the shot's own frames (src_out exclusive), out_* in frames of the cut. When the edit has
not written one (an older cut, or the audio commands run on their own) the trivial timeline is built from edit.json:
clips in order with their trims, `black = <seconds>` clips as gaps.
"""
import bisect
import json
from dataclasses import dataclass


@dataclass
class Clip:
    index: int
    kind: str
    shot: str | None
    src_in: int
    src_out: int
    out_start: int
    out_frames: int
    speed: float = 1.0
    fade_in: int = 0
    fade_out: int = 0
    src_map: list | None = None  # speed ramps: the source frame shown on each output frame of the clip (the edit's)

    @property
    def out_end(self):
        return self.out_start + self.out_frames

    def contains(self, frame):
        return self.kind == 'shot' and self.src_in <= frame < self.src_out

    def out_frame(self, frame):
        """The cut frame (fractional, unclamped) at which this shot's `frame` plays: through the edit's src_map when the
        clip's speed ramps (the first output frame that shows it), else at the clip's constant speed."""
        if self.src_map and self.src_in <= frame < self.src_out:
            return self.out_start + bisect.bisect_left(self.src_map, frame)
        return self.out_start + (frame - self.src_in) / self.speed


@dataclass
class Timeline:
    fps: int
    frames: int
    clips: list

    @property
    def seconds(self):
        return self.frames / self.fps

    def shot_clips(self, shot):
        return [c for c in self.clips if c.kind == 'shot' and c.shot == shot]

    def to_json(self):
        return {'fps': self.fps, 'frames': self.frames, 'clips': [{k: v for k, v in c.__dict__.items() if v is not None} for c in self.clips]}


def from_json(data):
    clips = []
    for i, c in enumerate(data['clips']):
        clips.append(Clip(index=int(c.get('index', i)), kind=c.get('kind', 'shot'), shot=c.get('shot'), src_in=int(c.get('src_in') or 0),
                          src_out=int(c.get('src_out') or 0), out_start=int(c['out_start']), out_frames=int(c['out_frames']),
                          speed=float(c.get('speed') or 1.0), fade_in=int(c.get('fade_in') or 0), fade_out=int(c.get('fade_out') or 0),
                          src_map=c.get('src_map') or None))
    frames = int(data.get('frames') or max((c.out_end for c in clips), default=0))
    return Timeline(fps=int(data['fps']), frames=frames, clips=clips)


def trivial(edit, result, fps):
    """The timeline of a plain cut: edit.json clips in order, trims applied, black gaps, speed 1."""
    frames_of = {s['name']: int(s['frames']) for s in (result or {}).get('shots', [])}
    clips, out = [], 0
    for i, c in enumerate(edit.get('clip', [])):
        if c.get('black') is not None and not c.get('shot'):
            n = int(round(float(c['black']) * fps))
            clips.append(Clip(index=i, kind='black', shot=None, src_in=0, src_out=0, out_start=out, out_frames=n))
            out += n
            continue
        shot = c['shot']
        if shot not in frames_of:
            raise SystemExit(f'edit.clip[{i}]: the take has no frames for shot "{shot}" (result.json)')
        head, tail = (c.get('trim') or [0, 0])
        src_in, src_out = int(head), frames_of[shot] - int(tail)
        speed = float(c.get('speed') or 1.0) if not isinstance(c.get('speed'), (list, dict)) else 1.0
        n = int(round((src_out - src_in) / speed))
        clips.append(Clip(index=i, kind='shot', shot=shot, src_in=src_in, src_out=src_out, out_start=out, out_frames=n, speed=speed,
                          fade_in=int(c.get('fade_in') or 0), fade_out=int(c.get('fade_out') or 0)))
        out += n
    return Timeline(fps=fps, frames=out, clips=clips)


def load(it):
    """The iteration's timeline: cut/timeline.json if the edit wrote one, else the trivial one from edit.json."""
    f = it.cut / 'timeline.json'
    if f.exists():
        return from_json(json.loads(f.read_text()))
    return trivial(it.edit(), it.result(), int(it.plan()['output']['fps']))


def out_time(timeline, shot, frame, clip=None):
    """Seconds in the cut where `shot`'s `frame` plays (first clip that shows it), or None if no clip shows it."""
    for c in ([clip] if clip else timeline.shot_clips(shot)):
        if c.contains(frame):
            return c.out_frame(frame) / timeline.fps
    return None
