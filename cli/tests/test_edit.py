"""The picture edit's frame arithmetic (no ffmpeg): clip lengths, marks, black gaps, push-in windows, speed, looks."""
import math
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from videocraft.edit import graph, looks, timeline  # noqa: E402
from videocraft.edit.timeline import EditError  # noqa: E402

PLAN = {'output': {'width': 1920, 'height': 1080, 'fps': 60}}
SHOTS = {'a': 180, 'b': 150}
MARKS = {'a': [{'label': 'push', 'frame': 60}], 'b': []}


def resolve(clips, **edit):
    return timeline.resolve(PLAN, {'clip': clips, **edit}, SHOTS, MARKS)


class FramesTest(unittest.TestCase):
    def test_sub_second_clips_are_exact(self):
        t = resolve([{'shot': 'a', 'in': 0, 'length': 0.25}, {'shot': 'a', 'in': 50, 'length': 0.35}, {'shot': 'b', 'in': 100, 'length': 0.5}])
        self.assertEqual([c['out_frames'] for c in t['clips']], [15, 21, 30])
        self.assertEqual([c['out_start'] for c in t['clips']], [0, 15, 36])
        self.assertEqual(t['frames'], 66)

    def test_trim_marks_and_black(self):
        t = resolve([{'shot': 'a', 'trim': [10, 20]}, {'black': 0.8}, {'shot': 'a', 'in': 'push', 'out': {'mark': 'push', 'offset': 30}}])
        a, black, c = t['clips']
        self.assertEqual((a['src_in'], a['src_out'], a['out_frames']), (10, 160, 150))
        self.assertEqual((black['kind'], black['out_frames'], black['out_start']), ('black', 48, 150))
        self.assertEqual((c['src_in'], c['src_out'], c['out_start']), (60, 90, 198))

    def test_integers_are_frames_and_decimals_seconds(self):
        self.assertEqual(timeline.frames_of(12, 60, 'x'), 12)
        self.assertEqual(timeline.frames_of(0.5, 60, 'x'), 30)
        with self.assertRaises(EditError):
            timeline.frames_of('12', 60, 'x')

    def test_errors_name_the_place(self):
        with self.assertRaisesRegex(EditError, r'edit.clip\[0\].in.*no mark "nope"'):
            resolve([{'shot': 'a', 'in': 'nope'}])
        with self.assertRaisesRegex(EditError, r'edit.clip\[0\]: the clip takes frames 170 to 200'):
            resolve([{'shot': 'a', 'in': 170, 'frames': 30}])
        with self.assertRaisesRegex(EditError, r'unknown key\(s\) zoom'):
            timeline.check({'clip': [{'shot': 'a', 'zoom': 2}]}, ['a'])
        with self.assertRaisesRegex(EditError, 'preset is one of'):
            timeline.check({'clip': [], 'export': [{'preset': 'tiktok'}]}, ['a'])

    def test_original_audio_exports(self):
        from videocraft.edit import cut
        timeline.check({'clip': [], 'export': [{'preset': 'x-1080p60', 'audio': 'original'}]}, ['a'])
        with self.assertRaisesRegex(EditError, r'edit.export\[0\]: audio is "game"'):
            timeline.check({'clip': [], 'export': [{'preset': 'x-1080p60', 'audio': 'mojang'}]}, ['a'])
        with self.assertRaisesRegex(EditError, 'for the video presets'):
            timeline.check({'clip': [], 'export': [{'preset': 'gif', 'audio': 'original'}]}, ['a'])
        self.assertTrue(cut.wants_original({'export': [{'preset': 'x-1080p60', 'audio': 'original'}]}))
        self.assertFalse(cut.wants_original({'export': [{'preset': 'x-1080p60', 'audio': 'original'}]}, exports=False))
        self.assertFalse(cut.wants_original({'export': [{'preset': 'x-1080p60'}]}))
        self.assertTrue(cut.wants_original({}, original_audio=True))

    def test_fades_must_fit(self):
        with self.assertRaisesRegex(EditError, 'longer than the clip'):
            resolve([{'shot': 'a', 'in': 0, 'frames': 20, 'fade_in': 12, 'fade_out': 12}])


class PushTest(unittest.TestCase):
    def test_window_is_even_and_inside(self):
        self.assertEqual(timeline.window(1920, 1080, 1.5, 960, 540), (1280, 720, 320, 180))
        cw, ch, left, top = timeline.window(1920, 1080, 1.5, 0, 2000)
        self.assertEqual((left, top), (0, 1080 - ch))
        cw, ch, left, top = timeline.window(1920, 1080, 1.7, 1001, 333)
        self.assertTrue(cw % 2 == ch % 2 == left % 2 == top % 2 == 0)

    def test_push_in_pieces_cover_the_clip(self):
        t = resolve([{'shot': 'a', 'push': [{'at': 'push', 'zoom': 1.5, 'hold': 40}]}])
        pieces = t['clips'][0]['push']
        self.assertEqual([p['kind'] for p in pieces], ['plain', 'ramp', 'hold', 'ramp', 'plain'])
        self.assertEqual([(p['from'], p['to']) for p in pieces], [(0, 60), (60, 67), (67, 107), (107, 116), (116, 180)])
        # The ramp zooms about the point that ends exactly on the held window.
        ramp, hold = pieces[1], pieces[2]
        cw, ch, left, top = hold['window']
        self.assertAlmostEqual(ramp['fx'] * (1 - 1 / 1.5), left, delta=1)
        self.assertAlmostEqual(ramp['fy'] * (1 - 1 / 1.5), top, delta=1)

    def test_slow_push(self):
        t = resolve([{'shot': 'b', 'push': {'from': 1.0, 'to': 1.15, 'x': 960, 'y': 700}}])
        (piece,) = t['clips'][0]['push']
        self.assertEqual((piece['kind'], piece['from'], piece['to'], piece['z1']), ('slow', 0, 150, 1.15))
        self.assertIn('perspective=', graph.piece_chain(piece, 1920, 1080))


class SpeedTest(unittest.TestCase):
    def test_constant_speed(self):
        double = resolve([{'shot': 'a', 'in': 0, 'frames': 60, 'speed': 2.0}])['clips'][0]
        half = resolve([{'shot': 'a', 'in': 0, 'frames': 60, 'speed': 0.5}])['clips'][0]
        self.assertEqual((double['out_frames'], half['out_frames']), (30, 120))
        self.assertEqual(half['src_map'][:6], [0, 0, 1, 1, 2, 2])

    def test_ramp_map_is_monotonic_and_ends_slow(self):
        clip = resolve([{'shot': 'a', 'in': 0, 'out': 90, 'speed': [{'at': 0, 'speed': 1.0}, {'at': 90, 'speed': 0.4}]}])['clips'][0]
        m = clip['src_map']
        self.assertEqual(len(m), clip['out_frames'])
        self.assertTrue(all(b - a in (0, 1) for a, b in zip(m, m[1:])))
        self.assertEqual(m[:5], [0, 1, 2, 3, 4])
        self.assertGreater(m[-10:].count(m[-1]), 1)

    def test_ffmpeg_expression_matches_python(self):
        keys = [(0, 1.0), (30, 0.3), (60, 0.3), (90, 1.0)]
        expr = timeline.time_expr(keys, 10)
        for n in (0, 5, 20, 35, 70, 100):
            py = expr.replace('N', str(n)).replace('if(', '_if(').replace('lte(', '_lte(')
            # ffmpeg's if() evaluates only the branch it takes; Python evaluates both, so the other branch may log a negative.
            safe_log = lambda x: math.log(x) if x > 0 else float('nan')  # noqa: E731
            value = eval(py, {'_if': lambda c, a, b: a if c else b, '_lte': lambda a, b: a <= b, 'log': safe_log})
            self.assertAlmostEqual(value, timeline._time(keys, 10 + n) - timeline._time(keys, 10), places=9)


class LooksTest(unittest.TestCase):
    def test_looks_apply_over_a_run(self):
        t = resolve([{'shot': 'a'}, {'shot': 'b'}, {'black': 0.5}, {'shot': 'a', 'grade': 'cool'}],
                    look=[{'from': 'b', 'to': 3, 'grade': 'sepia', 'frame': {'color': '#e8a23a'}}])
        self.assertNotIn('look', t['clips'][0])
        self.assertEqual(t['clips'][1]['look']['grade'], 'sepia')
        self.assertNotIn('look', t['clips'][2])
        self.assertEqual(t['clips'][3]['look']['grade'], 'cool')  # the clip's own grade wins

    def test_tint_keeps_grey_brightness(self):
        m = looks.tint_matrix(looks.hex_rgb('#b89470'), 1.0)
        rows = [m[0:3], m[4:7], m[8:11]]
        luma = sum(w * sum(r) for w, r in zip((0.2126, 0.7152, 0.0722), rows))
        self.assertAlmostEqual(luma, 1.0, places=6)
        self.assertEqual(looks.grade_filter(None), '')
        self.assertIn('colorchannelmixer', looks.grade_filter('sepia'))

    def test_frame_png(self):
        with tempfile.TemporaryDirectory() as d:
            path = looks.frame_png(Path(d) / 'f.png', 64, 36, '#e8a23a', 4, 3)
            data = path.read_bytes()
            self.assertEqual(data[:8], b'\x89PNG\r\n\x1a\n')
            width, height = struct.unpack('>II', data[16:24])
            self.assertEqual((width, height), (64, 36))
            idat = data[data.index(b'IDAT') + 4:data.index(b'IEND') - 8]
            raw = zlib.decompress(idat)
            row = raw[18 * (1 + 64 * 4):19 * (1 + 64 * 4)]
            self.assertEqual(row[1 + 3], 255)            # the edge is solid
            self.assertEqual(row[1 + 32 * 4 + 3], 0)     # the middle is clear

    def test_graph_has_black_and_concat(self):
        t = resolve([{'shot': 'a', 'in': 0, 'length': 0.25}, {'black': 0.5}])
        inputs, g = graph.build(t, lambda s: f'/x/{s}.mp4', lambda spec: '/x/f.png')
        self.assertEqual(inputs, ['-i', '/x/a.mp4'])
        self.assertIn('trim=start_frame=0:end_frame=15', g[0])
        self.assertTrue(any(x.startswith('color=c=black:s=1920x1080:r=60,trim=end_frame=30') for x in g))
        self.assertTrue(g[-1].endswith('concat=n=2:v=1:a=0,setpts=N/(60*TB)[v]'))


if __name__ == '__main__':
    unittest.main()
