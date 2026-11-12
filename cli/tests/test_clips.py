"""Long form and clipping (cli/videocraft/clips): time mapping through runs and assemblies, snapping to words and shots,
the outline, moments, the re-frame operator, chapters, the vertical re-shoot script and the [shot.vertical] hook."""
import json
import math
import random
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'cli'))
from videocraft import script  # noqa: E402
from videocraft.clips import assemble, chapters, moments, reframe, shorts, timemap  # noqa: E402

FPS = 60


def word(text, a, b, line='l', key=False):
    return timemap.Word(text=text, start=a, end=b, key=key, line=line)


class TimeMap(unittest.TestCase):
    TIMELINE = {'fps': 60, 'frames': 400, 'clips': [
        {'index': 0, 'kind': 'shot', 'shot': 'a', 'src_in': 12, 'src_out': 132, 'out_start': 0, 'out_frames': 120},
        {'index': 1, 'kind': 'black', 'shot': None, 'out_start': 120, 'out_frames': 30},
        {'index': 2, 'kind': 'shot', 'shot': 'b', 'src_in': 0, 'src_out': 200, 'out_start': 150, 'out_frames': 100},  # 2x speed
        {'index': 3, 'kind': 'shot', 'shot': 'a', 'src_in': 40, 'src_out': 190, 'out_start': 250, 'out_frames': 150}]}

    def test_run_mapping(self):
        segs = timemap.from_timeline(self.TIMELINE, run='/r')
        m = timemap.Map(fps=60, frames=400, segments=segs)
        self.assertEqual(m.locate(0)[1], 12)
        self.assertEqual(m.locate(130), (segs[1], None))       # black
        self.assertEqual(m.locate(160)[1], 20)                 # double speed: 10 master frames are 20 source frames
        self.assertEqual(m.to_master('/r', 'a', 72), [1.0, (250 + 32) / 60])   # a shot shown twice maps twice
        self.assertEqual(m.to_master('/r', 'a', 5), [])        # trimmed away
        self.assertEqual(m.boundaries(), [0.0, 2.0, 2.5, 250 / 60, 400 / 60])

    def test_assembly_offsets(self):
        # Two parts after a 150-frame card each: the second part's frame 0 is at 150 + 120 + 150 assembly frames.
        part = {'fps': 60, 'clips': [{'index': 0, 'kind': 'shot', 'shot': 's', 'src_in': 0, 'src_out': 120, 'out_start': 0, 'out_frames': 120}]}
        segs = timemap.from_timeline(part, run='/p1', part=0, offset=150) + timemap.from_timeline(part, run='/p2', part=1, offset=420)
        m = timemap.Map(fps=60, frames=540, segments=segs)
        self.assertEqual(m.to_master('/p2', 's', 0), [7.0])
        self.assertEqual(m.to_master('/p1', 's', 60), [3.5])
        seg, src = m.locate(480)
        self.assertEqual((seg.run, seg.part, src), ('/p2', 1, 60))

    def test_assembly_rate_conversion(self):
        part = {'fps': 30, 'clips': [{'kind': 'shot', 'shot': 's', 'src_in': 0, 'src_out': 90, 'out_start': 0, 'out_frames': 90}]}
        seg = timemap.from_timeline(part, run='/p', offset=60, fps=60)[0]
        self.assertEqual((seg.out_start, seg.out_frames), (60, 180))
        self.assertAlmostEqual(seg.out_frame(45), 150.0)

    def test_sub_timeline(self):
        segs = timemap.from_timeline(self.TIMELINE, run='/r')
        got = [(s.shot, a, b, n) for s, a, b, n in timemap.sub_timeline(segs, 60, 200)]
        self.assertEqual(got, [('a', 72, 132, 60), (None, None, None, 30), ('b', 0, 100, 50)])
        ramp = timemap.Segment(out_start=0, out_frames=6, kind='shot', shot='c', src_in=10, src_out=14, src_map=[10, 10, 11, 12, 12, 13])
        self.assertEqual([(a, b, n) for _, a, b, n in timemap.sub_timeline([ramp], 2, 5)], [(11, 13, 3)])

    def test_caption_words(self):
        item = {'first_frame': 12, 'last_frame': 125, 'words': [{'w': 'Hey.', 'frame': 12}, {'w': 'It\'s', 'frame': 19},
                                                               {'w': '*Nibs.', 'frame': 34, 'key': True}]}
        ws = timemap.caption_words([item], 60, lambda f: [f / 60 + 1.0], shot='pop')
        self.assertEqual([w.text for w in ws], ['Hey.', 'It\'s', 'Nibs.'])
        self.assertAlmostEqual(ws[0].start, 1.2)
        self.assertAlmostEqual(ws[0].end, 1 + 19 / 60)
        self.assertAlmostEqual(ws[2].end, 1 + (34 + 21) / 60)     # the last word lasts LAST_WORD (0.35 s)
        self.assertTrue(ws[2].key)
        self.assertEqual(len({w.line for w in ws}), 1)


class Snapping(unittest.TestCase):
    WORDS = [word('I\'m', 10.0, 10.3, 'a'), word('at', 10.3, 10.5, 'a'), word('least', 10.5, 11.0, 'a'),
             word('SIX', 12.0, 12.4, 'b', True)]

    def test_never_mid_word(self):
        cuts = [0.0, 9.0, 12.2, 20.0]
        s = timemap.snap_start(10.4, [], self.WORDS)
        self.assertEqual(s, 10.3)                                  # the onset of the word it was inside
        self.assertEqual(timemap.snap_start(10.4, [], self.WORDS, whole_line=True), 10.0)   # or of its line
        overlapping = self.WORDS + [word('least', 10.45, 10.9, 'spoken')]
        self.assertEqual(timemap.snap_start(10.6, [], overlapping), 10.3)                    # clear of both
        self.assertIsNone(timemap.inside_word(s, self.WORDS))
        e = timemap.snap_end(12.1, [c for c in cuts if c != 12.2], self.WORDS)
        self.assertEqual(e, 12.4)                                  # the end of the word it was inside
        self.assertIsNone(timemap.inside_word(e, self.WORDS))

    def test_prefers_shot_boundaries(self):
        self.assertEqual(timemap.snap_start(10.4, [0.0, 9.0], self.WORDS), 9.0)
        self.assertEqual(timemap.snap_end(11.5, [12.6, 20.0], self.WORDS), 12.6)
        # A boundary that falls inside a word is not a place to cut.
        self.assertEqual(timemap.snap_end(11.5, [12.2], self.WORDS), 11.5)
        self.assertEqual(timemap.snap_end(19.5, [20.0], self.WORDS, ceiling=19.8), 19.5)


class Outline(unittest.TestCase):
    def test_benchmark_outline(self):
        o = moments.parse_outline((ROOT / 'stories' / 'nibs-vs-duke' / 'outline.md').read_text())
        beats = {b['n']: b for b in o['beats']}
        self.assertEqual(beats[5]['shots'], (19, 28))
        self.assertEqual(beats[5]['purpose'], 'payoff')
        self.assertEqual(beats[2]['shots'], (5, 5))
        self.assertIn('Six times more goat', beats[5]['jokes'])
        self.assertIn('The egg is the applause', beats[4]['jokes'])
        self.assertEqual(len(o['jokes']), 9)

    def test_shot_numbers(self):
        shots = [{'name': 'open'}, {'name': 's19-brag'}, {'name': 'third'}]
        self.assertEqual(moments.shot_for_number(shots, 19), 's19-brag')
        self.assertEqual(moments.shot_for_number(shots, 3), 'third')
        self.assertIsNone(moments.shot_for_number(shots, 7))


class Moments(unittest.TestCase):
    def test_candidates_are_snapped_and_bounded(self):
        random.seed(3)
        words, evs = [], []
        for i in range(30):    # a line every 3 s, 4 words each, the last word a key word every other line
            t = i * 3.0 + 0.4
            for j in range(4):
                words.append(word(f'w{j}', t + j * 0.3, t + j * 0.3 + 0.3, f'l{i}', key=(j == 3 and i % 2 == 0)))
            evs.append({'t': t, 'end': t + 1.2, 'kind': 'line', 'weight': 0.5, 'what': f'line {i}'})
            if i % 2 == 0:
                evs.append({'t': t + 0.9, 'end': t + 1.2, 'kind': 'key', 'weight': 1.0, 'what': f'key word "k{i}"'})
        evs.append({'t': 47.0, 'kind': 'sound', 'weight': 3.0, 'what': 'entity.goat.screaming'})
        cuts = [k * 2.5 for k in range(37)]
        cands = moments.candidates(sorted(evs, key=lambda e: e['t']), cuts, words, 90.0, 15, 60)
        self.assertTrue(cands)
        for s, e in cands:
            self.assertGreaterEqual(e - s, 15 - 1e-6)
            self.assertLessEqual(e - s, 60 + 1e-6)
            self.assertIsNone(timemap.inside_word(s, words), (s, e))
            self.assertIsNone(timemap.inside_word(e, words), (s, e))
        ranked = moments.rank(cands, evs, cuts, keep=5)
        for a in ranked:
            for b in ranked:
                if a is not b:
                    self.assertLessEqual(moments.overlap((a['start'], a['end']), (b['start'], b['end'])), 0.5)
        self.assertTrue(any(m['start'] <= 47.0 <= m['end'] for m in ranked[:2]), 'the scream is in a top moment')

    def test_peaks(self):
        levels = [-30.0] * 100
        levels[40], levels[42], levels[80] = -10.0, -12.0, -18.0
        got = moments.peak_times(levels, over=8)
        self.assertEqual([round(t, 1) for t, _ in got], [4.0, 8.0])

    def test_salience(self):
        self.assertEqual(moments.salience('minecraft:entity.goat.screaming.ambient'), 3.0)
        self.assertEqual(moments.salience('minecraft:block.stone.step'), 0.0)


class Operator(unittest.TestCase):
    CW, W = 608, 1920

    def run_track(self, subj):
        c = reframe.operator(subj, FPS, self.CW, self.W)
        return c, reframe.stats(c, subj, FPS, self.CW)

    def test_bounded_and_centred(self):
        for amp, period in ((400, 4.0), (500, 5.0), (300, 2.5), (650, 6.0)):
            subj = [960 + amp * math.sin(2 * math.pi * i / FPS / period) for i in range(FPS * 8)]
            c, st = self.run_track(subj)
            self.assertLessEqual(st['max_speed'], reframe.VMAX + 1e-6)
            self.assertLessEqual(st['max_acceleration'], reframe.AMAX * 1.01)
            self.assertEqual(st['inside_crop'], 1.0)
            self.assertEqual(st['inside_centre_60'], 1.0, (amp, period))
            self.assertTrue(all(self.CW / 2 <= x <= self.W - self.CW / 2 for x in c))

    def test_holds_when_still(self):
        random.seed(1)
        subj = [1100 + random.uniform(-20, 20) for _ in range(300)]
        c, st = self.run_track(subj)
        self.assertEqual(st['max_speed'], 0.0)
        self.assertEqual(len({round(x, 6) for x in c}), 1)

    def test_starts_framed_and_holds_unseen(self):
        subj = [None] * 20 + [1500] * 100 + [None] * 40
        c, st = self.run_track(subj)
        self.assertAlmostEqual(c[0], 1500, delta=1)                 # a cut lands framed, no settle
        self.assertAlmostEqual(c[-1], 1500, delta=1)
        self.assertEqual(reframe.operator([None] * 5, FPS, self.CW, self.W), [960.0] * 5)

    def test_layout(self):
        self.assertEqual(reframe.layout(None, 0, 608)[0], 'follow')
        self.assertEqual(reframe.layout(700, 0, 608)[0], 'fit')
        self.assertEqual(reframe.layout(None, 760, 608)[0], 'fit')
        self.assertEqual(reframe.crop_size(1920, 1080), (608, 1080))

    def test_push_map(self):
        to_cut = reframe.push_map([{'kind': 'plain', 'from': 0, 'to': 10},
                                   {'kind': 'hold', 'from': 10, 'to': 20, 'window': [960, 540, 480, 270]}], 1920, 1080)
        self.assertEqual(to_cut(5, 700), 700)
        self.assertEqual(to_cut(15, 960), 960)          # the window's centre stays the centre
        self.assertEqual(to_cut(15, 600), 240)          # 120 px left of the window's edge... times 2

    def test_sendcmd(self):
        text = reframe.sendcmd([304, 304, 400, 2000], 608, 1920, 60)
        self.assertEqual(text.splitlines(), ['0.000000 crop x 0;', '0.033333 crop x 96;', '0.050000 crop x 1312;'])


class Chapters(unittest.TestCase):
    CH = [{'title': 'Cold open', 'start': 0.0, 'end': 12.5}, {'title': 'The barn', 'start': 12.5, 'end': 70.0},
          {'title': 'Duke = champ; #3', 'start': 70.0, 'end': 3725.0}]

    def test_youtube(self):
        text = chapters.youtube(self.CH)
        self.assertEqual(text, '0:00 Cold open\n0:12 The barn\n1:10 Duke = champ; #3\n')
        self.assertEqual(chapters.parse_youtube(text), [(0, 'Cold open'), (12, 'The barn'), (70, 'Duke = champ; #3')])
        self.assertEqual(chapters.stamp(3725.9), '1:02:05')
        self.assertEqual(chapters.problems(self.CH, 3725.0), [])

    def test_problems(self):
        short = [{'title': 'A', 'start': 0.0, 'end': 5.0}, {'title': 'B', 'start': 5.0, 'end': 30.0}]
        p = chapters.problems(short, 30.0)
        self.assertTrue(any('at least 3' in x for x in p))
        self.assertTrue(any('"A" is 5.0 s' in x for x in p))
        self.assertTrue(chapters.problems([{'title': 'A', 'start': 2.0, 'end': 30.0}]))

    def test_ffmetadata(self):
        text = chapters.ffmetadata(self.CH, title='Nibs')
        self.assertTrue(text.startswith(';FFMETADATA1\ntitle=Nibs\n'))
        self.assertIn('START=12500\nEND=70000\ntitle=The barn', text)
        self.assertIn('title=Duke \\= champ\\; \\#3', text)
        self.assertEqual(text.count('[CHAPTER]'), 3)


class Vertical(unittest.TestCase):
    RAW = {'name': 'demo', 'world': {'seed': 'x'}, 'shot': [
        {'name': 'a', 'duration': 4.0, 'camera': {'rig': 'orbit', 'radius': 10}, 'cue': [
            {'at': 0.5, 'do': 'caption', 'text': 'Hello *there.'}, {'at': 1.0, 'do': 'keycap', 'key': 'E', 'x': 1500, 'y': 540}]},
        {'name': 'b', 'duration': 2.0, 'camera': {'rig': 'fixed', 'eye': [0, 70, 0], 'at': [1, 70, 0]},
         'vertical': {'camera': {'fov': 50}, 'subject': [1, 70, 0]}},
        {'name': 'c', 'duration': 2.0, 'camera': {'rig': 'orbit'}}]}

    def test_script(self):
        edit = {'clip': [{'shot': 'a', 'trim': [0, 0], 'fade_in': 6, 'push': [{'at': 30, 'zoom': 1.5, 'x': 1440, 'y': 540}]},
                         {'black': 0.5}, {'shot': 'b', 'fade_out': 10}]}
        timeline = {'clips': [{'index': 0, 'src_in': 0, 'src_out': 240}, {'index': 1}, {'index': 2, 'src_in': 0, 'src_out': 120}]}
        segs = [timemap.Segment(0, 240, 'shot', 'a', 0, 240, clip=0), timemap.Segment(240, 30, 'black', clip=1),
                timemap.Segment(270, 120, 'shot', 'b', 0, 120, clip=2)]
        pieces = timemap.sub_timeline(segs, 60, 330)
        plan = {'output': {'width': 1920, 'height': 1080, 'fps': 60}}
        vs = shorts.vertical_script(self.RAW, plan, edit, timeline, pieces, 'demo-vertical', hook='Wait for it', pull=1.5)
        self.assertEqual(vs['output'], {'width': 1080, 'height': 1920, 'fps': 60})
        self.assertEqual([s['name'] for s in vs['shot']], ['a', 'b'])          # only the shots in the range
        a = vs['shot'][0]
        self.assertEqual(a['camera']['radius'], 15.0)                           # pulled back
        self.assertEqual(a['cue'][0]['do'], 'title')                            # the hook, on the range's first frame
        self.assertEqual(a['cue'][0]['at'], 1.0)
        self.assertEqual(a['cue'][1]['size'], shorts.SHORT_CAPTION)
        self.assertEqual((a['cue'][2]['x'], a['cue'][2]['y']), (843.8, 960.0))  # keeps its place in the frame
        clips = vs['edit']['clip']
        self.assertEqual(clips[0]['in'], 60)
        self.assertEqual(clips[0]['out'], 240)
        self.assertNotIn('fade_in', clips[0])                                   # the range starts after the fade
        self.assertEqual(clips[0]['push'][0]['x'], 1080)                        # mapped into the vertical frame (clamped)
        self.assertEqual(clips[1], {'black': 0.5})
        self.assertEqual((clips[2]['in'], clips[2]['out']), (0, 60))
        self.assertNotIn('fade_out', clips[2])
        self.assertEqual(vs['edit']['audio'], 'none')
        plan_v, _ = script.compile_script(vs, 'vertical')                       # it compiles, and the vertical keys apply
        self.assertEqual(plan_v['shots'][1]['camera']['fov'], 50)
        self.assertEqual(shorts.map_point(960, 540, 1920, 1080), (540.0, 960.0))

    def test_vertical_hook_only_when_vertical(self):
        raw = {'name': 'v', 'shot': [{'name': 'a', 'duration': 1.0, 'camera': {'rig': 'orbit', 'radius': 8},
                                       'vertical': {'camera': {'radius': 5}, 'subject': 'nibs'}}]}
        plan, _ = script.compile_script(raw)
        self.assertEqual(plan['shots'][0]['camera'], {'rig': 'orbit', 'radius': 8})
        plan, _ = script.compile_script({**raw, 'output': {'width': 1080, 'height': 1920}})
        self.assertEqual(plan['shots'][0]['camera'], {'rig': 'orbit', 'radius': 5})
        with self.assertRaises(script.ScriptError):
            script.compile_script({'name': 'v', 'shot': [{'name': 'a', 'duration': 1.0, 'camera': {'rig': 'orbit'}, 'vertical': {'zoom': 2}}]})


class Assembly(unittest.TestCase):
    def test_card_script_compiles(self):
        import tomllib
        text = assemble.card_script(['The "strut"', 'Last year'], 1920, 1080, 60)
        plan, edit = script.compile_script(tomllib.loads(text))
        self.assertEqual([s['name'] for s in plan['shots']], ['card-1', 'card-2'])
        self.assertEqual(plan['shots'][0]['timeline'][0]['title'], 'The "strut"')
        self.assertEqual(plan['shots'][1]['timeline'][0]['subtitle'], 'Part 2')
        self.assertEqual(edit['audio'], 'none')

    def test_level_gain(self):
        self.assertEqual(assemble.level_gain(-14.0), 0.0)
        self.assertEqual(assemble.level_gain(-20.0), 6.0)
        self.assertEqual(assemble.level_gain(-40.0), 12.0)        # at most 12 dB up
        self.assertEqual(assemble.level_gain(-70.0), 0.0)         # silence stays silence
        self.assertEqual(assemble.level_gain(None), 0.0)


if __name__ == '__main__':
    unittest.main()
