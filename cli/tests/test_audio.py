"""The sound track (cli/videocraft/audio): timeline mapping, pan and attenuation, the synth bed, sound placement, and
the original-only mode that must never touch a game asset."""
import json
import math
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'cli'))
from videocraft import store, tools  # noqa: E402
from videocraft.audio import assets, dsp, mix, sfx, synth  # noqa: E402
from videocraft.audio import timeline as tl  # noqa: E402

HEADER = 'frame,event,file,category,volume,pitch,x,y,z,relative,attenuation_distance,looping\n'
FRAMES = 'frame,seconds,cam_x,cam_y,cam_z,cam_yaw,cam_pitch,fov,player_x,player_y,player_z,player_yaw,player_pitch,on_ground\n'


def fake_iteration(base, shots, edit, sounds):
    """A run store iteration with a passed take: shots {name: frames}, sounds {name: [csv rows]}; camera at the origin
    looking south on every frame."""
    it = store.Iteration(Path(base) / 'it')
    it.take.mkdir(parents=True)
    plan = {'name': 'fake', 'seed': 3, 'output': {'width': 1920, 'height': 1080, 'fps': 60}, 'shots': [{'name': s} for s in shots]}
    (it.path / 'plan.json').write_text(json.dumps(plan))
    (it.path / 'edit.json').write_text(json.dumps(edit))
    (it.take / 'result.json').write_text(json.dumps({'verdict': 'PASS', 'shots': [{'name': s, 'frames': n} for s, n in shots.items()]}))
    for s, n in shots.items():
        d = it.take / 'shots' / s
        d.mkdir(parents=True)
        (d / 'frames.csv').write_text(FRAMES + ''.join(f'{i},{i / 60:.4f},0,0,0,0,0,70,0,0,0,0,0,1\n' for i in range(n)))
        (d / 'sounds.csv').write_text(HEADER + ''.join(r + '\n' for r in sounds.get(s, [])))
    return it


class TimelineTests(unittest.TestCase):
    def test_trims_black_gaps_and_speed_map_frames_to_cut_time(self):
        edit = {'clip': [{'shot': 'a', 'trim': [10, 20]}, {'black': 0.5}, {'shot': 'b', 'speed': 2.0}, {'shot': 'a', 'trim': [0, 100]}]}
        result = {'shots': [{'name': 'a', 'frames': 120}, {'name': 'b', 'frames': 60}]}
        t = tl.trivial(edit, result, 60)
        self.assertEqual([c.kind for c in t.clips], ['shot', 'black', 'shot', 'shot'])
        self.assertEqual([(c.out_start, c.out_frames) for c in t.clips], [(0, 90), (90, 30), (120, 30), (150, 20)])
        self.assertEqual(t.frames, 170)
        # Frame 10 of a is the first frame of the cut; frame 99 its last; frame 100 is trimmed away in the first clip.
        self.assertAlmostEqual(tl.out_time(t, 'a', 10), 0.0)
        self.assertAlmostEqual(tl.out_time(t, 'a', 99), 89 / 60)
        self.assertIsNone(tl.out_time(t, 'b', 60))
        # b plays at double speed: its frame 30 is 15 cut frames into its clip.
        self.assertAlmostEqual(tl.out_time(t, 'b', 30), (120 + 15) / 60)
        # The second use of a: frame 5 shows only in it (the first clip starts at 10).
        self.assertAlmostEqual(tl.out_time(t, 'a', 5), (150 + 5) / 60)

    def test_timeline_json_round_trips(self):
        data = {'fps': 60, 'frames': 50, 'clips': [{'index': 0, 'kind': 'shot', 'shot': 'x', 'src_in': 3, 'src_out': 53, 'out_start': 0,
                                                     'out_frames': 50, 'speed': 1, 'fade_in': 0, 'fade_out': 12}]}
        t = tl.from_json(data)
        self.assertEqual(tl.from_json(t.to_json()), t)
        self.assertEqual(t.clips[0].fade_out, 12)


class SpatialTests(unittest.TestCase):
    def test_distance_attenuation_is_linear_to_the_range(self):
        cam = (0, 0, 0, 0.0)
        self.assertAlmostEqual(mix.spatial(cam, (0, 0, 8), 16, False)[0], 0.5)
        self.assertEqual(mix.spatial(cam, (0, 0, 20), 16, False)[0], 0.0)
        self.assertEqual(mix.spatial(cam, (0, 0, 99), 16, True), (1.0, 0.0))

    def test_pan_follows_the_bearing_from_the_camera_yaw(self):
        south = (0, 0, 0, 0.0)  # yaw 0 looks south (+z): east (+x) is on the left
        self.assertLess(mix.spatial(south, (5, 0, 0), 16, False)[1], -0.7)
        self.assertGreater(mix.spatial(south, (-5, 0, 0), 16, False)[1], 0.7)
        self.assertAlmostEqual(mix.spatial(south, (0, 0, 5), 16, False)[1], 0.0, places=6)
        west = (0, 0, 0, 90.0)  # looking west (-x): south (+z) is on the left
        self.assertLess(mix.spatial(west, (0, 0, 5), 16, False)[1], -0.7)
        gl, gr = dsp.pan_gains(0.0)
        self.assertAlmostEqual(gl * gl + gr * gr, 1.0)


class SynthTests(unittest.TestCase):
    def test_the_bed_is_deterministic_per_seed_with_three_stems(self):
        a = synth.render(3.0, 'sneaky', seed=5)
        b = synth.render(3.0, 'sneaky', seed=5)
        c = synth.render(3.0, 'sneaky', seed=6)
        self.assertEqual(set(a.stems), {'melody', 'bass', 'drums'})
        for k in a.stems:
            self.assertEqual(a.stems[k].tobytes(), b.stems[k].tobytes(), k)
            self.assertEqual(len(a.stems[k]), 3 * dsp.SR)
        self.assertNotEqual(a.notes, c.notes)
        self.assertGreater(dsp.rms(a.stems['drums']), 0.01)

    def test_every_style_renders_and_keys_parse(self):
        for style in synth.STYLES:
            bed = synth.render(9.0, style, seed=1)  # past the two intro bars
            self.assertGreater(dsp.rms(bed.stems['melody']), 0.001, style)
        self.assertEqual(synth.parse_key('F# minor'), (6, True))
        self.assertEqual(synth.parse_key('bb'), (10, None))
        with self.assertRaises(ValueError):
            synth.parse_key('h')

    def test_the_mod_and_the_mix_know_the_same_synthesized_events(self):
        java = (ROOT / 'src/main/java/io/github/alexandroslekkas/videocraft/sound/Synth.java').read_text()
        names = re.findall(r'"([a-z]+)"', java[java.index('List.of('):])
        self.assertEqual(tuple(names), sfx.EVENTS)
        for name in sfx.EVENTS:
            self.assertGreater(len(sfx.synth_event(name)), 100, name)


class PlacementTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_sounds_land_on_their_frames_and_are_skipped_for_good_reasons(self):
        rows = {'a': ['30,videocraft:kick,,master,1,1,0,0,4,0,16,0',            # in the clip
                      '-40,videocraft:ding,,master,1,1,0,0,4,0,16,0',            # 1.2 s ding started 0.67 s before the cut-in: joins
                      '-30,videocraft:pop,,master,1,1,0,0,4,0,16,0',             # a short pop before the cut-in: skipped
                      '200,videocraft:kick,,master,1,1,0,0,4,0,16,0',            # in the trimmed tail: skipped
                      '50,minecraft:music.creative,music/game/x,music,1,1,0,0,0,1,16,0',  # the game's own music
                      '60,videocraft:kick,,master,1,1,0,0,40,0,16,0']}            # 40 blocks away, range 16
        it = fake_iteration(self.dir, {'a': 240, 'b': 60}, {'clip': [{'shot': 'b'}, {'black': 1.0}, {'shot': 'a', 'trim': [0, 60]}]}, rows)
        t = tl.load(it)
        placed, skipped = mix.place_sfx(it, t, mix.Sounds('game'))
        by_event = {p.event: p for p in placed}
        self.assertAlmostEqual(by_event['videocraft:kick'].time, (60 + 60 + 30) / 60)
        self.assertAlmostEqual(by_event['videocraft:ding'].time, 2.0)
        self.assertAlmostEqual(by_event['videocraft:ding'].offset, 40 / 60)
        self.assertEqual(len(placed), 2)
        reasons = sorted(s['reason'] for s in skipped)
        self.assertEqual(reasons, ['music the game started', 'out of earshot of the camera', 'started before the cut-in and short',
                                   'trimmed out of the cut'])
        # Rendered: the kick's first sound is exactly on its frame's sample; effects stop at the end of the clip.
        n = dsp.seconds_to_samples(t.seconds)
        left, _ = mix.render_sfx([by_event['videocraft:kick']], mix.Sounds('game'), n)
        first = next(i for i, x in enumerate(left) if x != 0.0)
        self.assertLessEqual(abs(first - dsp.seconds_to_samples(150 / 60)), 1)
        self.assertEqual(len(left), n)

    def test_original_audio_never_reads_a_game_asset(self):
        if not tools.ffmpeg():
            self.skipTest('ffmpeg not installed')
        rows = {'a': ['10,minecraft:block.note_block.harp,note/harp,record,3,1.189,0,0,3,0,48,0',
                      '40,minecraft:entity.goat.step,mob/goat/step1,neutral,0.15,1,0,0,2,0,16,0',
                      '70,minecraft:entity.chicken.egg,mob/chicken/plop,neutral,1,1,0,0,2,0,16,0',
                      '80,minecraft:entity.fox.ambient,mob/fox/idle1,neutral,1,1,0,0,2,0,16,0',
                      '90,videocraft:crash,,master,1,1,0,0,0,1,16,0']}
        edit = {'audio': 'original', 'clip': [{'shot': 'a'}, {'black': 0.5}],
                'music': {'source': 'game', 'track': 'music/game/wet_hands', 'cue': [{'shot': 'a', 'at': 1.0, 'do': 'drop'}]}}
        it = fake_iteration(self.dir, {'a': 150}, edit, rows)

        def forbidden(*args, **kwargs):
            raise AssertionError('original-only audio read a game asset')

        with mock.patch.object(assets, 'decode', forbidden), mock.patch.object(assets, 'object_path', forbidden), \
                mock.patch.object(assets, 'index_file', forbidden):
            out = mix.build(it)
        report = json.loads((it.cut / 'audio.json').read_text())
        self.assertEqual(out, it.cut / 'audio.wav')
        self.assertEqual({e['source'] for e in report['events']}, {'stand-in', 'synth'})
        self.assertEqual([s['event'] for s in report['skipped']], ['minecraft:entity.fox.ambient'])
        self.assertEqual(report['music']['source'], 'synth')
        self.assertFalse(report['game_assets_used'])
        self.assertLess(abs(report['loudness']['integrated'] + 14), 1.0)
        self.assertLessEqual(report['loudness']['true_peak'], -1.0)
        self.assertLess(report['black_gaps'][0]['integrated'], -50)

    def test_game_audio_without_assets_names_the_file_it_looked_for(self):
        it = fake_iteration(self.dir, {'a': 30}, {'clip': [{'shot': 'a'}]}, {})
        with mock.patch.object(assets, 'ASSETS', Path(self.dir) / 'no-assets'), mock.patch.object(assets, '_index', None):
            with self.assertRaises(assets.MissingAssets) as e:
                mix.build(it)
        self.assertIn(str(Path(self.dir) / 'no-assets' / 'indexes'), str(e.exception))


class DspTests(unittest.TestCase):
    def test_resample_plays_faster_and_add_into_clips_at_the_edges(self):
        src = dsp.zeros(1000)
        for i in range(1000):
            src[i] = math.sin(i / 10)
        self.assertEqual(len(dsp.resample(src, 2.0)), 499)
        out = dsp.zeros(10)
        one = dsp.zeros(5)
        for i in range(5):
            one[i] = 1.0
        self.assertEqual(dsp.add_into(out, one, 8), 2)
        self.assertEqual(dsp.add_into(out, one, -3, 0.5), 2)
        self.assertEqual(list(out), [0.5, 0.5, 0, 0, 0, 0, 0, 0, 1, 1])


if __name__ == '__main__':
    unittest.main()
