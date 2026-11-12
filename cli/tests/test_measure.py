"""Measure maths without ffmpeg: projection, kinematics, shot detection and statistics, text rules, loudness parsing."""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from videocraft.measure import camera, loudness, text, video  # noqa: E402


class Projection(unittest.TestCase):
    def test_basis_is_orthonormal_and_minecraft_oriented(self):
        f, r, u = camera.basis(0, 0)
        self.assertAlmostEqual(f[2], 1)          # yaw 0 faces south, +Z
        self.assertAlmostEqual(r[0], -1)         # looking south, west (-X) is on the right
        self.assertAlmostEqual(u[1], 1)
        f, r, u = camera.basis(90, 0)
        self.assertAlmostEqual(f[0], -1)         # yaw 90 faces west
        f, r, u = camera.basis(37, 25)
        dot = lambda a, b: sum(x * y for x, y in zip(a, b))
        for a in (f, r, u):
            self.assertAlmostEqual(dot(a, a), 1)
        self.assertAlmostEqual(dot(f, r), 0)
        self.assertAlmostEqual(dot(f, u), 0)
        self.assertLess(f[1], 0)                 # positive pitch looks down

    def test_point_ahead_is_centred_and_edges_match_the_fov(self):
        cam = (0, 64, 0)
        self.assertEqual(tuple(round(v, 6) for v in camera.project((0, 64, 10), cam, 0, 0, 70)), (0.5, 0.5))
        top = camera.project((0, 64 + 10 * math.tan(math.radians(35)), 10), cam, 0, 0, 70)
        self.assertAlmostEqual(top[1], 0.0)      # half the vertical fov up is the top edge
        right = camera.project((-10 * math.tan(math.radians(35)) * 16 / 9, 64, 10), cam, 0, 0, 70)
        self.assertAlmostEqual(right[0], 1.0)    # west is right when facing south
        self.assertIsNone(camera.project((0, 64, -5), cam, 0, 0, 70))

    def test_looking_down_moves_a_level_point_up_in_frame(self):
        y = camera.project((0, 64, 10), (0, 64, 0), 0, 10, 70)[1]
        self.assertLess(y, 0.5)

    def test_subject_track_and_framing_flags(self):
        frames, actors = [], []
        for n in range(30):
            frames.append({'frame': n, 'cam_x': 0, 'cam_y': 65, 'cam_z': 0, 'cam_yaw': 0, 'cam_pitch': 0, 'fov': 70})
            # walks towards the camera, drifting right then off the middle third
            actors.append({'frame': n, 'actor': 'nibs', 'x': -n * 0.25, 'y': 64, 'z': 10 - n * 0.2})
        track = camera.subject_track(frames, actors, 'nibs', 1.3)
        f = camera.framing(track, 'lead')
        self.assertEqual(f['seen'], 30)
        self.assertGreater(f['outside_middle_third'], 0)
        self.assertGreater(f['size_change'], 0.15)
        self.assertTrue(any('middle third' in x for x in f['flags']))
        self.assertTrue(any('size changes' in x for x in f['flags']))

    def test_subject_from_the_rigs_own_columns(self):
        frames = [{'frame': 0, 'cam_x': 0, 'cam_y': 65, 'cam_z': 0, 'cam_yaw': 0, 'cam_pitch': 0, 'fov': 70, 'lens_fov': 105.0,
                   'subject': 'nibs', 'subject_x': 0.0, 'subject_y': 64.0, 'subject_z': 5.0, 'subject_head_y': 65.3}]
        (n, v), = camera.subject_track(frames, [], 'nibs', 9.9)
        self.assertAlmostEqual(v[0], 0.5)
        expect = (1.3 / 5) / math.tan(math.radians(52.5)) / 2        # head - feet over the 105-degree lens
        self.assertAlmostEqual(v[2], expect, places=6)

    def test_kinematics_of_constant_velocity_has_no_jerk(self):
        rows = [{'cam_x': n * 0.05, 'cam_y': 64, 'cam_z': 0, 'cam_yaw': 350 + n * 2, 'cam_pitch': 0, 'fov': 70} for n in range(40)]
        k = camera.kinematics(rows, 60)
        self.assertAlmostEqual(k['speed']['median'], 3.0, places=3)
        self.assertAlmostEqual(k['jerk']['max'], 0.0, places=3)
        self.assertAlmostEqual(k['turn']['median'], 120.0, places=2)   # unwrapped across 360
        self.assertAlmostEqual(k['yaw_range'], 78.0, places=3)

    def test_rounding_in_frames_csv_is_not_jerk(self):
        # a smooth ease, written with frames.csv's rounding (1e-4 blocks, 1e-3 degrees)
        ease = lambda t: t * t * (3 - 2 * t)
        rows = [{'cam_x': round(10 * ease(n / 179), 4), 'cam_y': 64, 'cam_z': 0, 'cam_yaw': round(70 * ease(n / 179), 3),
                 'cam_pitch': 0, 'fov': 70} for n in range(180)]
        k = camera.kinematics(rows, 60)
        self.assertLess(k['jerk']['max'], 25)          # the true smoothstep jerk: 6 x 10 / 3³ = 2.2 b/s³, plus residual noise
        self.assertLess(k['turn_jerk']['max'], 40)     # per-frame differencing gave multiples of 216


class Shots(unittest.TestCase):
    def synthetic(self):
        """Blurred differences of 300 frames: motion noise around 5, hard cuts at 100 and 160, black 220-240."""
        blur = [5.0 + (i % 3) for i in range(300)]
        blur[0] = 0
        for c in (100, 160):
            blur[c] = 60.0
        peak = [200] * 300
        for i in range(220, 240):
            peak[i] = 3
            blur[i] = 0.0
        return blur, peak

    def test_cuts_black_and_segments(self):
        blur, peak = self.synthetic()
        black = video.black_runs(peak)
        self.assertEqual(black, [(220, 240)])
        cuts = video.cuts(blur, black)
        self.assertEqual(cuts, [100, 160])
        shots, dropped = video.segments(300, cuts, black, 60)
        self.assertEqual(shots, [(0, 100), (100, 160), (160, 220), (240, 300)])
        self.assertEqual(dropped, [])

    def test_duplicate_frames_do_not_hide_a_cut(self):
        # alternating repeated frames (0) and motion (12): a jump of 40 is a cut against the moving level only
        blur = [0.0 if i % 2 else 12.0 for i in range(200)]
        blur[101] = 40.0
        self.assertEqual(video.cuts(blur), [101])

    def test_a_dark_cut_between_still_shots(self):
        # two dark statics (mean grey 8) joined by a hard cut of 13: under CUT_MIN, but 26 times the stillness around it
        blur = [0.3] * 200
        blur[120] = 13.0
        self.assertEqual(video.cuts(blur), [])                        # without brightness: the fixed minimum misses it
        self.assertEqual(video.cuts(blur, luma=[8.0] * 200), [120])
        self.assertEqual(video.cuts(blur, luma=[120.0] * 200), [])     # in daylight 13 is motion, not a cut
        moving = [4.0] * 200                                           # the same jump in a dark, moving shot: not a cut
        moving[120] = 13.0
        self.assertEqual(video.cuts(moving, luma=[8.0] * 200), [])

    def test_repeated_frames_only_count_when_they_straddle_a_moving_shot(self):
        still_then_moving = [0.01] * 50 + [30.0] + [2.0] * 50          # a locked-off shot cut to a moving one
        self.assertIsNone(video._repeat_at_cut(still_then_moving, 50))
        doubled = list(still_then_moving)
        doubled[51] = 0.0                                               # the first frame of the moving shot is repeated
        self.assertEqual(video._repeat_at_cut(doubled, 50), 'after')
        held = [2.0] * 50 + [30.0] + [2.0] * 50
        held[49] = 0.0                                                  # the moving shot's last frame repeats
        self.assertEqual(video._repeat_at_cut(held, 50), 'before')

    def test_slivers_merge_and_flashes_drop(self):
        shots, dropped = video.segments(400, [3, 100, 103], [(200, 230), (240, 260)], 60)
        self.assertEqual(shots[:2], [(0, 103), (103, 200)])
        self.assertEqual(dropped, [{'start': 230, 'end': 240, 'why': 'flash'}])
        self.assertEqual(shots[-1], (260, 400))

    def test_stats(self):
        s = video.stats([7.0, 1.35, 1.9, 0.5, 0.2, 0.55, 0.37, 3.0, 8.0])
        self.assertEqual(s['count'], 9)
        self.assertEqual(s['median'], 1.35)
        self.assertEqual(s['histogram'], {'<1': 4, '1-2': 2, '2-4': 1, '4-6': 0, '6+': 2})
        self.assertEqual(s['over_7_5s'], 1)
        self.assertEqual(s['short_runs'], [{'first': 3, 'shots': 4}])

    def test_frozen_runs_and_cut_comparison(self):
        full = [5.0] * 50
        for i in range(10, 20):
            full[i] = 0.0
        self.assertEqual(video.frozen_runs(full, []), [(9, 20)])
        matched, missed, extra = video.compare_cuts([100, 161, 300], [100, 160, 220])
        self.assertEqual(matched, [(100, 100), (160, 161)])
        self.assertEqual(missed, [220])
        self.assertEqual(extra, [300])


class Text(unittest.TestCase):
    def test_rules(self):
        fps = 60
        items = [text.normalise(i, fps) for i in [
            {'kind': 'caption', 'text': 'Hey. It is me.', 'start': 0, 'end': 150, 'box': [400, 800, 1100, 90], 'cap_height': 58,
             'words': [{'w': 'Hey.', 'frame': 0}, {'w': 'It', 'frame': 10}, {'w': 'is', 'frame': 20}, {'w': 'me.', 'frame': 30}]},
            {'kind': 'caption', 'text': 'Far too many words for the time it is shown', 'start': 140, 'end': 200, 'box': [50, 800, 900, 90],
             'cap_height': 30},
            {'kind': 'caption', 'text': 'SIX', 'start': 300, 'end': 315},
        ]]
        table, problems = text.check(items, fps, shot='s1')
        rules = sorted(p['rule'] for p in problems)
        self.assertEqual(rules, ['cap_height', 'one_message', 'reading', 'reading_one_word', 'safe_area', 'words_per_second'])
        self.assertEqual(table[0]['complete_seconds'], 2.0)
        self.assertEqual(table[0]['reading_seconds'], 1.7)
        self.assertEqual(text.reading_seconds(1), 1.2)

    def test_the_text_layers_own_records(self):
        record = {'kind': 'caption', 'first_frame': 12, 'last_frame': 131, 'shown_frame': 40, 'box': [400, 800, 1500, 900],
                  'cap_height': 56, 'words_count': 3, 'text': 'Hey. Its me.', 'words': [{'w': 'Hey.', 'frame': 12, 'key': False}]}
        it = text.normalise(record, 60)
        self.assertEqual((it['start'], it['end'], it['complete'], it['box'], it['count']), (12, 132, 40, [400, 800, 1100, 100], 3))
        table, problems = text.check([it], 60)
        self.assertEqual(table[0]['complete_seconds'], round(92 / 60, 3))
        self.assertEqual(problems, [])

    def test_variants_are_read(self):
        it = text.normalise({'type': 'title', 'frames': [10, 70], 'rect': {'x': 1, 'y': 2, 'w': 3, 'h': 4}, 'capHeight': 50,
                             'words': [{'word': 'A', 'at': 0.5}]}, 60)
        self.assertEqual((it['kind'], it['start'], it['end'], it['box'], it['cap'], it['words']), ('title', 10, 70, [1, 2, 3, 4], 50, [('A', 40)]))

    def test_vertical_frame_scales_the_safe_area(self):
        items = [text.normalise({'text': 'Hi', 'start': 0, 'end': 120, 'box': [60, 1700, 300, 80], 'cap_height': 30}, 60)]
        _, problems = text.check(items, 60, 1080, 1920)
        self.assertEqual(sorted(p['rule'] for p in problems), ['safe_area'])   # 30 px at 1080 wide is above 44 * 1080 / 1920

    def test_vertical_safe_area_clears_the_app_overlays(self):
        def rules(box):
            items = [text.normalise({'text': 'Hi', 'start': 0, 'end': 120, 'box': box, 'cap_height': 56}, 60)]
            return [p['rule'] for p in text.check(items, 60, 1080, 1920)[1]]
        self.assertEqual(rules([100, 1300, 800, 120]), [])               # ends at y 1420, x 900
        self.assertEqual(rules([100, 1400, 800, 120]), ['safe_area'])    # into the bottom 25 %
        self.assertEqual(rules([200, 1000, 800, 120]), ['safe_area'])    # into the right 12 % (x 1000 > 950)


class Loudness(unittest.TestCase):
    LOG = '\n'.join([
        '[Parsed_ebur128_0 @ 0x1] t: 0.1  TARGET:-23 LUFS    M:-120.7 S:-120.7     I: -70.0 LUFS       LRA:   0.0 LU',
        '[Parsed_ebur128_0 @ 0x1] t: 0.2  TARGET:-23 LUFS    M:-60.0 S:-120.7     I: -70.0 LUFS       LRA:   0.0 LU',
        '[Parsed_ebur128_0 @ 0x1] t: 0.3  TARGET:-23 LUFS    M:-70.0 S:-120.7     I: -70.0 LUFS       LRA:   0.0 LU',
        '[Parsed_ebur128_0 @ 0x1] t: 0.4  TARGET:-23 LUFS    M:-70.0 S:-120.7     I: -70.0 LUFS       LRA:   0.0 LU',
        '[Parsed_ebur128_0 @ 0x1] t: 0.5  TARGET:-23 LUFS    M:-14.0 S:-120.7     I: -70.0 LUFS       LRA:   0.0 LU',
        '[Parsed_ebur128_0 @ 0x1] t: 1.5  TARGET:-23 LUFS    M:-15.0 S:-120.7     I: -70.0 LUFS       LRA:   0.0 LU',
        '[Parsed_ebur128_0 @ 0x1] Summary:', '  Integrated loudness:', '    I:         -14.2 LUFS', '  Loudness range:',
        '    LRA:        6.0 LU', '  True peak:', '    Peak:       -1.5 dBFS'])

    def test_parse(self):
        samples, integrated, peak, lra = loudness.parse(self.LOG)
        self.assertEqual(len(samples), 6)
        self.assertEqual((integrated, peak, lra), (-14.2, -1.5, 6.0))
        self.assertEqual(loudness.silences(samples), [{'start': 0.0, 'end': 0.4, 'seconds': 0.4}])
        self.assertEqual(loudness.per_second(samples, 1.5), [-70.0, -15.0])


if __name__ == '__main__':
    unittest.main()
