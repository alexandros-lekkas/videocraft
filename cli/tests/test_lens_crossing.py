"""The barrel lens of the edit, the zebra crossing set op, mob textures in the compiler, and edit sfx lengths."""
import sys
import tempfile
import unittest
from array import array
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'cli'))
from videocraft import script  # noqa: E402
from videocraft.audio import dsp, mix  # noqa: E402
from videocraft.edit import looks, timeline  # noqa: E402
from videocraft.sets import build  # noqa: E402


class LensTests(unittest.TestCase):
    def test_zoom_keeps_the_corners_inside_the_source(self):
        for k1 in (0.1, 0.3, 0.42, 0.8):
            z = looks.lens_zoom(k1)
            self.assertGreater(z, 1.0)
            self.assertAlmostEqual((1 + k1 / z ** 2) / z, 1.0, places=6)   # the corner samples the source's corner

    def test_filter_is_even_centred_and_empty_without_a_bow(self):
        f = looks.lens_filter({'barrel': 0.4}, 1920, 1080)
        self.assertIn('lenscorrection=k1=0.4000', f)
        crop = f.split('crop=')[1].split(',')[0].split(':')
        cw, ch, x, y = map(int, crop)
        self.assertEqual((cw % 2, ch % 2), (0, 0))
        self.assertEqual((x, y), ((1920 - cw) // 2, (1080 - ch) // 2))
        self.assertEqual(looks.lens_filter({'barrel': 0}, 1920, 1080), '')
        self.assertEqual(looks.lens_filter(None, 1920, 1080), '')

    def test_timeline_checks_and_carries_the_lens(self):
        with self.assertRaises(timeline.EditError):
            timeline._check_look({'lens': {'barrel': 2}}, 'edit.clip[0]')
        with self.assertRaises(timeline.EditError):
            timeline._check_look({'lens': {'bow': 0.3}}, 'edit.clip[0]')
        timeline._check_look({'lens': {'barrel': 0.3, 'k2': 0.05}}, 'edit.clip[0]')


class CrossingTests(unittest.TestCase):
    def test_stripes_run_along_the_lane_across_its_width(self):
        raw = {'name': 'x', 'build': [
            {'do': 'ground', 'from': [-20, -10], 'to': [20, 10], 'mix': 'grass_block'},
            {'do': 'lane', 'points': [[-18, 0], [18, 0]], 'width': 9, 'mix': 'black_concrete', 'mark': 'road', 'smooth': False},
            {'do': 'crossing', 'along': 'road', 'd': 18, 'width': 9, 'depth': 3, 'stripe': 1, 'gap': 1}]}
        g = build(raw).grid
        white = {(x, z) for x in range(-20, 21) for z in range(-10, 11)
                 if (s := g.get(x, -1, z)) is not None and s.id.endswith('white_concrete')}
        self.assertTrue(white)
        xs = {x for x, _ in white}
        zs = sorted({z for _, z in white})
        self.assertLessEqual(max(xs) - min(xs), 3)            # depth along the lane (east)
        self.assertTrue(all(-5 <= z <= 4 for z in zs))        # within the road (cells -5 to 4)
        self.assertTrue(any(b - a > 1 for a, b in zip(zs, zs[1:])))   # gaps between stripes


class TextureTests(unittest.TestCase):
    def test_a_mob_texture_is_made_absolute_against_the_script(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / 's.toml'
            src.write_text('name = "t"\n[[actor]]\nid = "hero"\nkind = "mob"\nentity = "sheep"\nat = [0, 0, 0]\n'
                           'texture = "a/hero.png"\n[[shot]]\nname = "a"\nduration = 1.0\n'
                           'camera = { rig = "fixed", eye = [0, 2, 4], at = [0, 0, 0] }\n')
            plan = script.compile_script(script.load(src), str(src))
            plan = plan[0] if isinstance(plan, tuple) else plan
            actor = next(a for a in plan['actors'] if a['id'] == 'hero')
            self.assertEqual(actor['texture'], str((Path(d) / 'a/hero.png').resolve()))


class EditSfxTests(unittest.TestCase):
    def test_length_cuts_a_long_sound_and_fades_it(self):
        n = dsp.seconds_to_samples(4.0)
        buf = array('f', [1.0]) * dsp.seconds_to_samples(3.0)
        p = mix.Placed(source='game', event='e', file='', shot='', frame=-1, clip=-1, time=0.5, offset=1.0, stop=1.5)
        p.fade = 0.1
        left, _ = mix.render_edit_sfx([p], [buf], n)
        on = [i for i, v in enumerate(left) if abs(v) > 1e-6]
        self.assertAlmostEqual(on[0] / dsp.SR, 0.5, places=2)
        self.assertAlmostEqual(on[-1] / dsp.SR, 1.5, places=2)
        self.assertLess(abs(left[on[-1]]), abs(left[on[0] + 100]))   # faded out


if __name__ == '__main__':
    unittest.main()
