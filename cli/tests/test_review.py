"""Rubrics, review validation, score aggregation, the climb's comparison, and a packet built from a synthetic run."""
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from videocraft import store, tools  # noqa: E402
from videocraft.review import image, packet, prompts, reviews, rubric  # noqa: E402


def good_review(rub, rid):
    return {'reviewer': rid, 'scores': {c['id']: 7 for c in rubric.criteria_of(rub, rid)},
            'gates': {g['id']: 'pass' for g in rub['gate']},
            'notes': [{'shot': 's01', 't': '0:01.20', 'text': 'holds the subject well'}],
            'fixes': [{'fix': f'fix {i}', 'why': 'because', 'shot': 's01', 't': '0:00.50'} for i in range(3)], 'verdict': 'fine'}


class Rubrics(unittest.TestCase):
    def test_both_rubrics_load_and_cover_every_criterion(self):
        general = rubric.load()
        self.assertEqual(general['name'], 'general')
        self.assertEqual(len(general['criterion']), 6)
        bench = rubric.load('pinksheep-style')
        self.assertEqual([c['id'] for c in bench['criterion']],
                         ['pacing', 'camera', 'staging', 'acting', 'comedic_timing', 'text', 'sound', 'technical', 'energy'])
        self.assertEqual([g['id'] for g in bench['gate']], ['originality'])
        self.assertEqual((bench['pass']['average'], bench['pass']['minimum'], bench['pass']['max_shot_seconds']), (7.0, 5, 7.5))

    def test_a_criterion_no_role_scores_is_refused(self):
        r = rubric.load('pinksheep-style')
        r['role'] = [x for x in r['role'] if x['id'] != 'sound']
        with self.assertRaises(rubric.RubricError):
            rubric.check(r)


class Reviews(unittest.TestCase):
    def setUp(self):
        self.rub = rubric.load('pinksheep-style')

    def test_a_good_review_validates(self):
        r = reviews.validate(good_review(self.rub, 'pacing'), self.rub)
        self.assertEqual(r['scores'], {'pacing': 7, 'comedic_timing': 7, 'energy': 7})
        self.assertEqual(r['rubric'], 'pinksheep-style')

    def test_every_problem_is_named(self):
        bad = good_review(self.rub, 'pacing')
        bad['scores']['pacing'] = 11
        del bad['scores']['energy']
        bad['gates'] = {}
        bad['fixes'] = bad['fixes'][:2]
        bad['notes'].append({'text': 'no citation'})
        with self.assertRaises(reviews.ReviewError) as e:
            reviews.validate(bad, self.rub)
        message = str(e.exception)
        for part in ('scores.pacing', 'scores.energy', 'gates.originality', 'three most valuable', 'notes[1]'):
            self.assertIn(part, message)

    def test_extract_json_takes_the_last_block(self):
        text = 'thinking…\n```json\n{"a": 1}\n```\nmore\n```json\n{"b": 2}\n```\n'
        self.assertEqual(reviews.extract_json(text), {'b': 2})
        with self.assertRaises(reviews.ReviewError):
            reviews.extract_json('no json here')

    def test_aggregate_and_pass_rule(self):
        rs = [reviews.validate(good_review(self.rub, r['id']), self.rub) for r in self.rub['role']]
        s = reviews.aggregate(rs, self.rub)
        self.assertTrue(s['pass'])
        self.assertEqual(s['average'], 7.0)
        rs[0]['scores']['staging'] = 3
        s = reviews.aggregate(rs, self.rub)
        self.assertFalse(s['pass'])
        self.assertEqual(s['criteria']['staging'], 5.0)     # (3 + 7) / 2: story and camera both score staging
        rs[0]['scores']['staging'] = 1
        rs[1]['scores']['staging'] = 3
        s = reviews.aggregate(rs, self.rub)
        self.assertIn('staging under 5', '; '.join(s['reasons']))
        rs[2]['gates']['originality'] = 'fail'
        self.assertEqual(reviews.aggregate(rs, self.rub)['gates']['originality'], 'fail')

    def test_better(self):
        self.assertTrue(reviews.better({'average': 6.0, 'minimum': 5, 'gates': {}}, None))
        self.assertTrue(reviews.better({'average': 6.5, 'minimum': 5, 'gates': {}}, {'average': 6.0, 'minimum': 5}))
        self.assertFalse(reviews.better({'average': 6.0, 'minimum': 5, 'gates': {}}, {'average': 6.0, 'minimum': 5}))
        self.assertFalse(reviews.better({'average': 7.0, 'minimum': 3, 'gates': {}}, {'average': 6.0, 'minimum': 5}))
        self.assertFalse(reviews.better({'average': 9.0, 'minimum': 8, 'gates': {'originality': 'fail'}}, {'average': 6.0}))

    def test_schema_matches_the_role(self):
        s = prompts.schema(self.rub, 'sound')
        self.assertEqual(s['properties']['scores']['required'], ['sound'])
        self.assertEqual(s['properties']['fixes']['minItems'], 3)


class Images(unittest.TestCase):
    def test_png_round_trip_and_font(self):
        c = image.Canvas(40, 20, (10, 20, 30))
        w = c.text(1, 1, 'Ab1:', 2, (255, 0, 0))
        self.assertEqual(w, image.text_width('Ab1:'))
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'x.png'
            c.png(path)
            data = path.read_bytes()
        self.assertEqual(data[:8], b'\x89PNG\r\n\x1a\n')
        width, height = struct.unpack('>II', data[16:24])
        self.assertEqual((width, height), (40, 20))
        idat = data[data.index(b'IDAT') + 4:data.index(b'IEND') - 8]
        raw = zlib.decompress(idat)
        self.assertEqual(len(raw), 20 * (1 + 40 * 3))
        self.assertEqual(raw[1:4], bytes((10, 20, 30)))       # background at (0, 0)
        self.assertIn(bytes((255, 0, 0)), raw)               # ink

    def test_select_expression_is_shallow(self):
        self.assertEqual(packet.select_expr([5]), 'eq(n,5)')
        self.assertEqual(packet.select_expr([3, 1, 2, 9]), '(between(n,1,3)+eq(n,9))')
        deep = packet.select_expr(range(0, 4000, 3))
        depth = max_depth = 0
        for ch in deep:
            depth += ch == '('
            max_depth = max(max_depth, depth)
            depth -= ch == ')'
        self.assertLess(max_depth, 16)

    def test_strip_frames(self):
        self.assertEqual(packet.strip_frames(1), [0])
        self.assertEqual(packet.strip_frames(30, tiles=4), [0, 10, 20, 29])
        self.assertEqual(packet.strip_frames(15, every=5), [0, 5, 10, 14])
        self.assertEqual(len(packet.strip_frames(400)), 12)


@unittest.skipUnless(tools.ffmpeg(), 'ffmpeg not installed')
class Packet(unittest.TestCase):
    """A run made of two synthetic shots, cut together, measured and packeted without a game."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        it = store.Iteration(self.tmp / 'synth' / '0001')
        shots = it.take / 'shots'
        for name, src in (('a', 'testsrc2'), ('b', 'smptebars')):
            (shots / name).mkdir(parents=True)
            subprocess.run([tools.ffmpeg(), '-v', 'error', '-f', 'lavfi', '-i', f'{src}=size=320x180:rate=60:duration=1',
                            '-pix_fmt', 'yuv420p', str(shots / name / 'video.mp4')], check=True)
            rows = ['frame,seconds,cam_x,cam_y,cam_z,cam_yaw,cam_pitch,fov,player_x,player_y,player_z,player_yaw,player_pitch,on_ground']
            rows += [f'{n},{n / 60:.4f},0,65,{n * 0.05:.4f},0,0,70,0,64,10,180,0,1' for n in range(60)]
            (shots / name / 'frames.csv').write_text('\n'.join(rows) + '\n')
        (shots / 'a' / 'text.json').write_text(json.dumps({'items': [
            {'kind': 'caption', 'text': 'Hello there', 'start': 0, 'end': 50, 'box': [200, 900, 400, 60], 'cap_height': 50,
             'words': [{'w': 'Hello', 'frame': 0}, {'w': 'there', 'frame': 10}]}]}))
        plan = {'name': 'synth', 'output': {'width': 320, 'height': 180, 'fps': 60},
                'actors': [], 'shots': [{'name': 'a', 'duration': 1.0, 'camera': {'rig': 'chase', 'subject': 'player'}, 'timeline': []},
                                        {'name': 'b', 'duration': 1.0, 'camera': {'rig': 'fixed'}, 'timeline': [{'at': 0.2, 'do': 'caption', 'text': ['Bars!']}]}]}
        (it.path / 'plan.json').write_text(json.dumps(plan))
        (it.path / 'edit.json').write_text(json.dumps({'clip': [{'shot': 'a'}, {'shot': 'b', 'trim': [0, 10]}]}))
        (it.path / 'meta.json').write_text(json.dumps({'iteration': '0001', 'parent': None, 'created': 'now'}))
        (it.path / 'script.toml').write_text('name = "synth"\n')
        (it.take / 'result.json').write_text(json.dumps({'verdict': 'PASS', 'shots': [{'name': 'a', 'frames': 60}, {'name': 'b', 'frames': 60}]}))
        it.cut.mkdir()
        subprocess.run([tools.ffmpeg(), '-v', 'error', '-i', str(shots / 'a/video.mp4'), '-i', str(shots / 'b/video.mp4'), '-filter_complex',
                        '[1:v]trim=end_frame=50,setpts=PTS-STARTPTS[b];[0:v][b]concat=n=2:v=1[v]', '-map', '[v]', '-pix_fmt', 'yuv420p',
                        str(it.cut / 'master.mp4')], check=True)
        self.it = it

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_measure_then_packet(self):
        from videocraft.measure import measure
        m = measure(self.it)
        self.assertTrue(m['pass'], m['checks'])
        self.assertEqual(m['picture']['shot_stats']['count'], 2)
        self.assertEqual(m['cut_check']['expected'], [60])
        self.assertEqual(m['cut_check']['matched'], 1)
        self.assertEqual(m['framing']['a']['subject'], 'player')
        self.assertEqual(m['text']['counts'].get('safe_area'), 1)    # a 1920-wide box on a 320-wide frame
        manifest = packet.build(self.it, 'pinksheep-style', 'pacing,sound', say=lambda *_: None)
        out = self.it.review / 'packet'
        self.assertEqual(manifest['files']['strips'], ['strips/01-a.jpg', 'strips/02-b.jpg'])
        self.assertEqual(manifest['files']['cuts'], ['cuts/cut-01.jpg'])
        self.assertEqual(manifest['joins'], [{'frame': 60, 't': '0:01.00', 'soft': False}])
        for f in manifest['files']['strips'] + manifest['files']['contact'] + manifest['files']['cuts']:
            self.assertEqual((out / f).read_bytes()[:3], b'\xff\xd8\xff')   # JPEG
        captions = (out / 'captions.md').read_text()
        self.assertIn('"Hello there"', captions)
        self.assertIn('"Bars!"', captions)
        pacing = (out / 'prompts/pacing.md').read_text()
        self.assertIn('cannot hear', pacing)
        self.assertIn('cuts/cut-01.jpg', pacing)
        self.assertIn('exactly three', pacing)
        self.assertEqual(sorted(p.name for p in (out / 'prompts').iterdir()), ['pacing.md', 'sound.md'])

    def test_sound_sheet(self):
        it = self.it
        master = it.cut / 'master.mp4'
        silent = it.cut / 'silent.mp4'
        master.rename(silent)
        subprocess.run([tools.ffmpeg(), '-v', 'error', '-i', str(silent), '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1.8333',
                        '-c:v', 'copy', '-c:a', 'aac', '-shortest', str(master)], check=True)
        (it.path / 'voice.json').write_text(json.dumps([{'id': 'a-1', 'character': 'nibs', 'shot': 'a', 'file': 'v1.wav', 'text': 'Hi *there.',
                                                         'seconds': 0.6, 'words': [{'word': 'Hi', 'start': 0.1, 'end': 0.3}, {'word': '*there.', 'start': 0.35, 'end': 0.6}]}]))
        (it.cut / 'audio.json').write_text(json.dumps({
            'mode': 'game', 'seconds': 1.83, 'sample_rate': 48000, 'channels': 2, 'loudness': {'integrated': -14.0, 'true_peak': -1.6},
            'music': {'source': 'synth', 'style': 'upbeat', 'at': 0.0, 'cues': [{'time': 1.0, 'do': 'hit'}]},
            'events': [{'source': 'game', 'event': 'minecraft:entity.goat.step', 'file': 'mob/goat/step1', 'shot': 'b', 'frame': 12,
                        'time': 1.2, 'gain_db': -9.0}],
            'voice': [{'file': 'v1.wav', 'shot': 'a', 'frame': 6, 'time': 0.1}],
            'skipped': [{'shot': 'a', 'frame': -3, 'event': 'minecraft:entity.goat.step', 'reason': 'started before the cut-in and short'}]}))
        plan = it.plan()
        plan['shots'][1]['timeline'].append({'at': 0.2, 'do': 'jump', 'actor': 'nibs'})
        (it.path / 'plan.json').write_text(json.dumps(plan))
        manifest = packet.build(it, 'pinksheep-style', 'sound', say=lambda *_: None)
        out = it.review / 'packet'
        self.assertEqual(manifest['files']['sound'], ['sound/loudness-1.png'])
        self.assertEqual((out / 'sound/loudness-1.png').read_bytes()[:4], b'\x89PNG')
        sheet = (out / 'sound.md').read_text()
        self.assertIn('| 0:01.20 | 72 | b | 12 | game | entity.goat.step | mob/goat/step1 | -9.0 |', sheet)
        self.assertIn('Hi@M12 *there.@M27', sheet)                 # 0.1 s + word start, in master frames
        self.assertIn('| 0:01.00 | 60 | hit |', sheet)
        self.assertIn('jump nibs @72', sheet)                        # shot b's frame 12 is master frame 72
        self.assertIn('entity.goat.step @72', sheet)
        self.assertIn('started before the cut-in and short | 1 |', sheet)
        prompt = (out / 'prompts/sound.md').read_text()
        self.assertIn('sound/loudness-1.png', prompt)
        self.assertIn('Judging sound without hearing it', prompt)
        self.assertIn('strips/01-a.jpg', prompt)
