"""Side-by-side alignment maths without ffmpeg: fitting a shot to another's length, reference and our segments,
pairing when the counts differ, the output plan, and the source clock the labels show."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from videocraft import sidebyside as sb  # noqa: E402

REPO = Path(__file__).resolve().parents[2]


def clip(name, start, frames, kind='shot'):
    return {'kind': kind, 'shot': name if kind == 'shot' else None, 'out_start': start, 'out_frames': frames}


def seg(kind, n, a, b, **kw):
    return {'kind': kind, 'n': n, 'a': a, 'b': b, 'clips': [{'name': f's{n}', 'a': a, 'b': b}], **kw}


class Fit(unittest.TestCase):
    def test_stretch_fills_exactly(self):
        speed, used, hold = sb.fit(3.0, 2.0, 'stretch')
        self.assertAlmostEqual(speed, 1.5)
        self.assertEqual((used, hold), (3.0, 0.0))
        speed, used, hold = sb.fit(0.2, 1.0, 'stretch')
        self.assertAlmostEqual(speed, 0.2)
        self.assertAlmostEqual(used / speed + hold, 1.0)

    def test_hold_plays_at_own_speed(self):
        self.assertEqual(sb.fit(0.65, 2.6, 'hold'), (1.0, 0.65, 2.6 - 0.65))
        self.assertEqual(sb.fit(5.0, 2.0, 'hold'), (1.0, 2.0, 0.0))     # longer: cut short

    def test_auto_stretches_within_limits_then_holds_or_cuts(self):
        speed, used, hold = sb.fit(2.2, 2.0)                            # 1.1x: a plain stretch
        self.assertAlmostEqual(speed, 1.1)
        self.assertAlmostEqual(used, 2.2)
        self.assertEqual(hold, 0.0)
        speed, used, hold = sb.fit(0.65, 2.6)                           # 0.25x wanted: 0.5x, then hold
        self.assertEqual(speed, 0.5)
        self.assertAlmostEqual(used, 0.65)
        self.assertAlmostEqual(hold, 2.6 - 1.3)
        speed, used, hold = sb.fit(5.0, 2.2)                            # 2.27x wanted: 2x, the rest cut
        self.assertEqual(speed, 2.0)
        self.assertAlmostEqual(used, 4.4)
        self.assertEqual(hold, 0.0)

    def test_always_fills_the_lead_length(self):
        for src in (0.1, 0.5, 1.0, 2.0, 3.3, 9.0):
            for out in (0.25, 1.0, 2.6, 6.0):
                for mode in ('auto', 'stretch', 'hold'):
                    speed, used, hold = sb.fit(src, out, mode)
                    self.assertAlmostEqual(used / speed + hold, out, places=9, msg=(src, out, mode))
                    self.assertLessEqual(used, src + 1e-9)

    def test_empty_shots(self):
        self.assertEqual(sb.fit(0.0, 2.0), (1.0, 0.0, 2.0))
        self.assertEqual(sb.fit(1.0, 0.0), (1.0, 0.0, 0.0))


class Segments(unittest.TestCase):
    def test_reference_ends_at_next_start_and_gaps_are_black(self):
        shots = [{'n': 1, 'start': 0.0, 'seconds': 7.04, 'camera': 'lead track'}, {'n': 2, 'start': 7.0, 'seconds': 1.0, 'camera': 'ecu'},
                 {'n': 3, 'start': 9.0, 'seconds': 0.9, 'camera': 'static'}]
        segs = sb.ref_segments(shots, 0.0, 11.5)
        self.assertEqual([(s['kind'], s['n'], s['a'], s['b']) for s in segs],
                         [('shot', 1, 0.0, 7.0), ('shot', 2, 7.0, 8.0), ('black', 2, 8.0, 9.0), ('shot', 3, 9.0, 9.9), ('black', 3, 9.9, 11.5)])
        self.assertEqual(segs[1]['camera'], 'ecu')
        sliver = sb.ref_segments([{'n': 1, 'start': 0.0, 'seconds': 1.8, 'camera': '-'}, {'n': 2, 'start': 2.0, 'seconds': 1.0, 'camera': '-'}], 0.0, 3.0)
        self.assertEqual([(s['kind'], s['a'], s['b']) for s in sliver], [('shot', 0.0, 2.0), ('shot', 2.0, 3.0)])

    def test_reference_section_clips_shots(self):
        shots = [{'n': k, 'start': float(k), 'seconds': 1.0, 'camera': '-'} for k in range(10)]
        segs = sb.ref_segments(shots, 3.0, 6.0)
        self.assertEqual([s['n'] for s in segs], [3, 4, 5])
        self.assertEqual(segs[-1]['b'], 6.0)

    def test_benchmark_shot_list_reads_and_covers_the_section(self):
        listed = sb.load_shot_list(REPO / 'docs/benchmarks/pinksheep-style.shots.toml')
        self.assertEqual((listed['from'], listed['to']), (0.0, 82.2))
        self.assertEqual([s['n'] for s in listed['shots']], list(range(1, 31)))
        segs = sb.ref_segments(listed['shots'], 0.0, 82.2)
        blacks = [s['n'] for s in segs if s['kind'] == 'black']
        self.assertEqual(blacks, [9, 28, 30])                         # the two dips and the tail
        self.assertAlmostEqual(segs[-1]['b'], 82.2)
        for a, b in zip(segs, segs[1:]):
            self.assertAlmostEqual(a['b'], b['a'], places=4)           # covers the section; 8.35 → 8.4 is no black
        self.assertAlmostEqual(sum(s['b'] - s['a'] for s in segs), 82.2, places=4)

    def test_ours_join_split_shots_and_number_black(self):
        clips = [clip('s01-a', 0, 60), clip('s02-b', 60, 30), clip(None, 90, 30, 'black'), clip('s03-c', 120, 60),
                 clip('s03b-d', 180, 30), clip('end', 210, 60)]
        segs = sb.our_segments(clips, 60)
        self.assertEqual([(s['kind'], s['n']) for s in segs], [('shot', 1), ('shot', 2), ('black', 2), ('shot', 3), ('shot', None)])
        joined = segs[3]
        self.assertEqual((joined['a'], joined['b']), (2.0, 3.5))
        self.assertEqual([c['name'] for c in joined['clips']], ['s03-c', 's03b-d'])

    def test_ours_without_numbers_count_in_order(self):
        clips = [clip('intro', 0, 60), clip('walk', 60, 60), clip(None, 120, 30, 'black'), clip('end', 150, 60)]
        segs = sb.our_segments(clips, 60)
        self.assertEqual([(s['kind'], s['n']) for s in segs], [('shot', 1), ('shot', 2), ('black', 2), ('shot', 3)])

    def test_detected_reference_segments(self):
        pic = {'shots': [{'start': 0.0, 'end': 2.0}, {'start': 2.0, 'end': 3.0}, {'start': 4.0, 'end': 5.0}],
               'black': [{'start': 3.0, 'end': 4.0}]}
        segs = sb.detected_segments(pic, 10.0)
        self.assertEqual([(s['kind'], s['n'], s['a']) for s in segs], [('shot', 1, 10.0), ('shot', 2, 12.0), ('black', 2, 13.0), ('shot', 3, 14.0)])


class Pairing(unittest.TestCase):
    def setUp(self):
        self.ref = [seg('shot', 1, 0, 2), seg('shot', 2, 2, 3), seg('black', 2, 3, 4), seg('shot', 3, 4, 6), seg('shot', 4, 6, 7)]
        self.ours = [seg('shot', 1, 0, 1), seg('shot', 2, 1, 3), seg('shot', 3, 3, 4), seg('shot', None, 4, 5)]

    def test_lead_ours_keeps_every_shot_of_ours(self):
        pairs = sb.pair(self.ref, self.ours, 'ours')
        self.assertEqual(len(pairs), len(self.ours))
        self.assertEqual([(r and r['n'], o['n']) for r, o in pairs], [(1, 1), (2, 2), (3, 3), (None, None)])
        # the reference's black and its shot 4 have no partner: left out

    def test_lead_ref_keeps_every_reference_segment(self):
        pairs = sb.pair(self.ref, self.ours, 'ref')
        self.assertEqual([(r['kind'], r['n'], o and o['n']) for r, o in pairs],
                         [('shot', 1, 1), ('shot', 2, 2), ('black', 2, None), ('shot', 3, 3), ('shot', 4, None)])

    def test_follower_never_plays_backwards(self):
        ours = [seg('shot', 2, 0, 1), seg('shot', 1, 1, 2), seg('shot', 3, 2, 3)]
        pairs = sb.pair(self.ref, ours, 'ours')
        self.assertEqual([r and r['n'] for r, _ in pairs], [2, None, 3])

    def test_plan_output_follows_the_lead_clock(self):
        out = sb.plan_output(sb.pair(self.ref, self.ours, 'ours'), 'ours', 'auto')
        self.assertEqual([(o['t0'], o['t1']) for o in out], [(0, 1), (1, 3), (3, 4), (4, 5)])
        first = out[0]['ref']
        self.assertEqual((first['speed'], first['used'], first['hold']), (2.0, 2.0, 0.0))
        second = out[1]['ref']                                         # 1 s of reference over 2 s: 0.5x, no hold
        self.assertEqual((second['speed'], second['hold']), (0.5, 0.0))
        self.assertIsNone(out[3]['ref'])
        self.assertEqual(sb.blanks(out, 'ref'), [(4, 5)])
        self.assertEqual(sb.blanks(out, 'ours'), [])
        ps = sb.pieces(out, 'ref')
        self.assertEqual([(p['a'], p['b'], p['t0']) for p in ps], [(0, 2.0, 0), (2, 3.0, 1), (4, 6.0, 3)])

    def test_plan_output_lead_ref(self):
        out = sb.plan_output(sb.pair(self.ref, self.ours, 'ref'), 'ref', 'stretch')
        self.assertEqual(out[-1]['t1'], 7)
        self.assertEqual(sb.blanks(out, 'ours'), [(3, 4), (6, 7)])
        self.assertAlmostEqual(out[0]['ours']['speed'], 0.5)

    def test_source_clock_holds(self):
        out = sb.plan_output([(seg('shot', 1, 10.0, 10.65), seg('shot', 1, 0.0, 2.6))], 'ours', 'auto')
        chrome = sb.Chrome(out, {'lead': 'ours'})
        o = out[0]
        self.assertAlmostEqual(chrome._source_time(o, 'ref', 0.0), 10.0)
        self.assertAlmostEqual(chrome._source_time(o, 'ref', 0.65), 10.325)   # half speed
        self.assertAlmostEqual(chrome._source_time(o, 'ref', 2.0), 10.65)     # held
        self.assertAlmostEqual(chrome._source_time(o, 'ours', 2.0), 2.0)

    def test_time_alignment_splits_at_both_sides_cuts(self):
        ref = [seg('shot', 1, 5.0, 7.0), seg('shot', 2, 7.0, 8.0)]
        ours = [seg('shot', 1, 0.0, 1.5), seg('shot', 2, 1.5, 4.0)]
        out = sb.plan_time(ref, ours, 5.0, 'ours')
        self.assertEqual([(o['t0'], o['t1']) for o in out], [(0.0, 1.5), (1.5, 2.0), (2.0, 3.0), (3.0, 4.0)])
        self.assertEqual([o['ref'] and o['ref']['seg']['n'] for o in out], [1, 1, 2, None])
        self.assertEqual(out[1]['ref']['a'], 6.5)


class Graph(unittest.TestCase):
    def test_atempo_chain_stays_in_range(self):
        self.assertEqual(sb._atempo(1.0), [])
        product = lambda chain: __import__('math').prod(float(f.split('=')[1]) for f in chain)
        for speed in (0.25, 0.3, 0.5, 1.7, 2.0, 5.0):
            chain = sb._atempo(speed)
            self.assertAlmostEqual(product(chain), speed, places=5)
            self.assertTrue(all(0.5 <= float(f.split('=')[1]) <= 2.0 for f in chain), chain)

    def test_lead_audio_is_one_trim(self):
        out = sb.plan_output([(seg('shot', 1, 3, 4), seg('shot', 1, 0, 2)), (None, seg('shot', 2, 2, 3))], 'ours', 'auto')
        lines = sb.audio_graph(out, 'ours', '0:a', 3.0)
        self.assertEqual(len(lines), 1)
        self.assertIn('atrim=0.000000:3.000000', lines[0])
        lines = sb.audio_graph(out, 'ref', '1:a', 3.0)
        self.assertIn('aevalsrc=0', ' '.join(lines))                   # the blank second shot is silence
        self.assertTrue(lines[-1].endswith('concat=n=2:v=0:a=1[aout]'))

    def test_video_chain_maps_and_blanks(self):
        out = sb.plan_output([(seg('shot', 1, 3, 4), seg('shot', 1, 0, 2)), (None, seg('shot', 2, 2, 3))], 'ours', 'stretch')
        chain = sb.video_chain(sb.pieces(out, 'ref'), sb.blanks(out, 'ref'))
        self.assertIn("select='between(t,3.000000,3.999900)'", chain)
        self.assertIn('(0.000000+(T-3.000000)/0.500000)', chain)
        self.assertIn("enable='between(t,2.0000,2.9999)'", chain)

    def test_camera_family(self):
        self.assertEqual(sb.camera_family('lead track'), 'moving')
        self.assertEqual(sb.camera_family('lead'), 'moving')
        self.assertEqual(sb.camera_family('ecu cut-in'), 'still')
        self.assertEqual(sb.camera_family('fixed'), 'still')
        self.assertIsNone(sb.camera_family('black'))

    def test_table_writes(self):
        out = sb.plan_output(sb.pair([seg('shot', 1, 0, 2, camera='static')], [seg('shot', 1, 0, 1)], 'ours'), 'ours', 'auto')
        info = {'rigs': {'s1': 'fixed'}, 'fov': {'s1': 40}, 'framing': {'s1': {'x': {'median': 0.5}, 'height': {'median': 0.3}, 'from': 'camera'}},
                'align': 'shots', 'lead': 'ours', 'fit': 'auto', 'audio': 'ours', 'ref_name': 'ref.mp4', 'ref_from': 0.0, 'ref_to': 2.0,
                'our_name': 'x/1', 'ref_source': 'test', 'our_span': 1.0}
        table = sb.rows(out, info)
        self.assertEqual(table[0]['delta'], -1.0)
        self.assertTrue(table[0]['camera_match'])
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'side-by-side.md'
            sb.write_table(table, info, path)
            text = path.read_text()
        self.assertIn('| 1 | 0.00 | 2.00 | 1.00 | -1.00 | -50 | static | s1 | fixed | 40 | x 0.50 · h 0.30 | match |', text)


if __name__ == '__main__':
    unittest.main()
