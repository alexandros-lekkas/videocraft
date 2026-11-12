"""The mix balance: the duck's shape and depth, effects under the voice, the per-line voice-over-music measurement."""
import math
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from videocraft import lint  # noqa: E402
from videocraft.audio import balance, dsp, mix  # noqa: E402


def db_at(curve, t):
    return dsp.db(curve[int(round(t * dsp.SR / mix.BLOCK))])


def sine(seconds, freq, amp, start=0.0, total=None):
    n = dsp.seconds_to_samples(total or seconds)
    out = dsp.zeros(n)
    a = dsp.seconds_to_samples(start)
    for i in range(dsp.seconds_to_samples(seconds)):
        if a + i < n:
            out[a + i] = amp * math.sin(2 * math.pi * freq * i / dsp.SR)
    return out


class DuckCurveTests(unittest.TestCase):
    def setUp(self):
        self.n = dsp.seconds_to_samples(4)

    def test_the_bed_is_down_before_the_first_word(self):
        c = mix.duck_curve(self.n, [(1.0, 1.5, -18.0)], -6)
        self.assertAlmostEqual(db_at(c, 1.0 - mix.LOOKAHEAD), -18.0, delta=0.1)      # fully down ahead of the onset
        self.assertAlmostEqual(db_at(c, 1.0 - mix.LOOKAHEAD - mix.ATTACK - 0.01), 0.0, delta=0.1)   # untouched before
        mid = db_at(c, 1.0 - mix.LOOKAHEAD - mix.ATTACK / 2)
        self.assertTrue(-12 < mid < -6, mid)    # a linear ramp in dB over the attack

    def test_it_holds_across_a_short_gap_and_then_releases(self):
        c = mix.duck_curve(self.n, [(1.0, 1.5, -18.0), (1.62, 2.0, -18.0)], -6)
        for t in (1.5, 1.55, 1.6):
            self.assertAlmostEqual(db_at(c, t), -18.0, delta=0.1)        # no swell between packed lines
        self.assertAlmostEqual(db_at(c, 2.0 + mix.HOLD - 0.02), -18.0, delta=0.2)
        # one-pole release: back within 3 dB of the bed about RELEASE * ln(6) after the hold
        t3 = 2.0 + mix.HOLD + mix.RELEASE * math.log(6) + 0.05
        self.assertGreater(db_at(c, t3), -3.2)
        self.assertLess(db_at(c, 2.0 + mix.HOLD + 0.1), -10)

    def test_an_interval_depth_wins_over_a_shallower_one(self):
        c = mix.duck_curve(self.n, [(1.0, 2.0, -6.0), (1.2, 1.4, -20.0)], -6)
        self.assertAlmostEqual(db_at(c, 1.3), -20.0, delta=0.1)
        self.assertAlmostEqual(db_at(c, 1.1), -6.0, delta=0.5)


class LineDuckTests(unittest.TestCase):
    def readings(self, level, a=0.0, b=3.0):
        return [(round(a + k * 0.1, 3), level, level) for k in range(int((b - a) / 0.1) + 1)]

    def test_the_duck_goes_as_deep_as_the_line_needs(self):
        spans = [(1.0, 2.0, 'l1', 'nibs')]
        keys = mix.line_ducks(spans, self.readings(-16.0), self.readings(-24.0), -18.0, -6.0)
        # voice -16, bed -24: the bed must be at -16 - 18 - margin = -35, so 11 dB down
        self.assertAlmostEqual(keys[0][2], -16 - 18 - mix.MARGIN + 24, places=3)

    def test_a_quiet_bed_still_dips_by_the_least_and_a_loud_one_stops_at_the_floor(self):
        spans = [(1.0, 2.0, 'l1', 'nibs')]
        quiet = mix.line_ducks(spans, self.readings(-16.0), self.readings(-55.0), -18.0, -6.0)
        self.assertEqual(quiet[0][2], -6.0)
        loud = mix.line_ducks(spans, self.readings(-16.0), self.readings(10.0), -18.0, -6.0)
        self.assertEqual(loud[0][2], mix.DUCK_FLOOR)

    def test_the_loudest_moment_of_the_bed_under_a_line_sets_it(self):
        music = self.readings(-30.0)
        music[15] = (music[15][0], -20.0, -20.0)    # one swell at 1.5 s
        keys = mix.line_ducks([(1.0, 2.0, 'l1', None)], self.readings(-16.0), music, -18.0, -6.0)
        self.assertAlmostEqual(keys[0][2], -16 - 18 - mix.MARGIN + 20, places=3)


class SfxTests(unittest.TestCase):
    def test_effects_are_held_under_the_voice_and_lower_under_a_line(self):
        readings = [(0.5, -10.0, -10.0), (1.5, -17.0, -17.0), (3.0, -25.0, -25.0)]
        spans = [(1.0, 2.0, 'l1', 'nibs')]
        keys = mix.sfx_keys(readings, -16.0, spans, -3.0, -6.0)
        self.assertEqual(len(keys), 2)
        self.assertAlmostEqual(keys[0][2], -9.0)       # -10 against a ceiling of -19
        self.assertAlmostEqual(keys[1][2], -5.0)       # -17 under a line: limit -22


class MeasureTests(unittest.TestCase):
    def test_parse_reads_momentary_and_short_term(self):
        text = ('[Parsed_ebur128_0 @ 0x1] t: 0.4   TARGET:-23 LUFS    M: -21.8 S:-120.7     I: -21.8 LUFS       LRA:   0.0 LU\n'
                '[Parsed_ebur128_0 @ 0x1] t: 0.5   TARGET:-23 LUFS    M: -inf S: -30.0     I: -21.8 LUFS       LRA:   0.0 LU\n'
                '[Parsed_ebur128_0 @ 0x1] Summary:\n\n  Integrated loudness:\n    I:         -21.8 LUFS\n')
        readings, integrated = balance.parse(text)
        self.assertEqual(readings, [(0.4, -21.8, balance.FLOOR), (0.5, balance.FLOOR, -30.0)])
        self.assertEqual(integrated, -21.8)

    def test_inside_takes_the_windows_within_a_line(self):
        r = [(round(k * 0.1, 3), -20.0, -20.0) for k in range(40)]
        got = [x[0] for x in balance.inside(r, 1.0, 2.0)]
        self.assertEqual(got[0], 1.4)
        self.assertEqual(got[-1], 2.0)
        self.assertEqual(len(balance.inside(r, 1.0, 1.2)), 1)    # shorter than the window: the nearest one

    def test_power_mean(self):
        self.assertEqual(balance.power_mean([-20.0, -20.0]), -20.0)
        self.assertAlmostEqual(balance.power_mean([-20.0, -70.0]), -23.0, delta=0.05)
        self.assertEqual(balance.power_mean([]), balance.FLOOR)

    @unittest.skipUnless(shutil.which('ffmpeg'), 'needs ffmpeg')
    def test_the_ratio_of_a_line_is_voice_over_music_in_lu(self):
        total = 4.0
        voice = sine(1.5, 1000, 0.1, start=1.0, total=total)       # a 1 kHz "line" 20 dB over the bed
        bed = sine(total, 1000, 0.01, total=total)
        b = balance.measure(voice, (bed, bed), None, 0.0, [(1.0, 2.5, 'l1', 'nibs')], [(0.0, total)])
        line = b['lines'][0]
        self.assertAlmostEqual(line['ratio'], 20.0, delta=0.6)
        self.assertAlmostEqual(b['music']['between_lines'], line['music'], delta=0.6)
        self.assertEqual(b['ratio']['close'], [])
        self.assertEqual(balance.warnings(b), [])
        loud = sine(total, 1000, 0.05, total=total)          # 6 dB under the voice: a warning
        b2 = balance.measure(voice, (loud, loud), None, 0.0, [(1.0, 2.5, 'l1', 'nibs')], [(0.0, total)])
        self.assertEqual(b2['ratio']['close'], ['l1'])
        self.assertTrue(any('l1' in w for w in balance.warnings(b2)))


class LintTests(unittest.TestCase):
    def test_mix_settings_that_bury_the_voice_are_warned(self):
        self.assertEqual(lint.mix_rules({'edit': {'music': {'mood': 'playful'}}}), [])
        rules = lint.mix_rules({'edit': {'music': {'mood': 'playful'}, 'mix': {'music_under_voice': -8}}})
        self.assertEqual([r['rule'] for r in rules], ['mix_balance'])
        rules = lint.mix_rules({'edit': {'music': {'mood': 'playful', 'gain': 10}}})
        self.assertEqual([r['where'] for r in rules], ['edit.mix.music_level'])


if __name__ == '__main__':
    unittest.main()
