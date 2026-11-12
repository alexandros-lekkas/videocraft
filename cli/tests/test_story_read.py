"""`story read`: the transcript a cold reader gets, the read with a fake model, the gate in build and make."""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'cli'))
os.environ.setdefault('VIDEOCRAFT_VOICE', 'estimate')

from videocraft import script  # noqa: E402
from videocraft.story import _ask, read, stages  # noqa: E402

FIXTURE = ROOT / 'cli/tests/fixtures/nibs-vs-duke-3shot.toml'
NVD = ROOT / 'examples/nibs-vs-duke.toml'


def answer(score, issues=()):
    return '```json\n' + json.dumps({'score': score, 'understood': 'A goat brags about jumping.', 'issues': list(issues)}) + '\n```'


ISSUE = {'shot': 'horn', 'speaker': 'Nibs', 'line': 'This horn.', 'kind': 'missing_setup', 'severity': 'high',
         'problem': 'Why the horn matters is never set up.', 'fix': 'This horn. Only got the one.'}


class TranscriptTests(unittest.TestCase):
    def test_lines_in_cut_order_with_the_on_screen_names(self):
        raw = script.load(NVD)
        entries = read.transcript(raw, str(NVD))
        shots = [e['shot'] for e in entries if not e.get('black')]
        clip_order = []
        for c in raw['edit']['clip']:
            if 'shot' in c and (not clip_order or clip_order[-1] != c['shot']):
                clip_order.append(c['shot'])
        self.assertEqual(shots, [s for s in clip_order if s in shots])
        self.assertTrue(any(e.get('black') for e in entries))      # the dip to black is in the transcript
        lines = [l for e in entries if not e.get('black') for l in e['lines']]
        said = sum(1 for s in raw['shot'] for c in s.get('cue') or [] if c.get('do') == 'say')
        self.assertEqual(len(lines), said)                          # every say line, once
        first = lines[0]
        self.assertEqual((first['speaker'], first['character']), ('Nibs', 'nibs'))
        self.assertNotIn('*', ' '.join(l['text'] for l in lines))   # key-word marks are not what a viewer sees
        self.assertTrue(any(l.get('cut_on') for l in lines))
        self.assertIn('Duke', {l['speaker'] for l in lines})

    def test_packed_lines_follow_the_line_before_them(self):
        raw = {'name': 'pack', 'shot': [{'name': 'a', 'duration': 3, 'camera': {'rig': 'fixed'}, 'cue': [
            {'at': 0.25, 'do': 'say', 'actor': 'x', 'text': 'Breaking tonight: press reports say'},
            {'do': 'say', 'actor': 'x', 'text': 'he was a target.'},
            {'at': 0.1, 'do': 'sound', 'id': 'minecraft:block.note_block.bell'},
            {'do': 'say', 'actor': 'x', 'text': 'Back to you.'}]}]}
        entry = read.transcript(raw, None)[0]
        self.assertEqual([x['text'] for x in entry['lines']], ['Breaking tonight: press reports say', 'he was a target.', 'Back to you.'])

    def test_the_text_has_the_picture_and_the_lines_but_not_the_premise(self):
        raw = script.load(FIXTURE)
        out = read.text(read.transcript(raw, str(FIXTURE)), read.cast_lines(raw, str(FIXTURE)))
        self.assertIn('[1. strut] camera: lead on nibs', out)
        self.assertIn('action: nibs walk', out)
        self.assertIn("Nibs [nibs]: Hey. It's me. Nibs.", out)
        self.assertIn('[2. horn]', out)
        self.assertNotIn(raw['description'], out)

    def test_on_screen_text_and_sounds_are_listed(self):
        raw = {'name': 'x', 'shot': [{'name': 'a', 'duration': 2, 'note': 'A goat stares at a poster.', 'cue': [
            {'at': 0, 'do': 'card', 'text': 'THREE YEARS LATER'}, {'at': 0.5, 'do': 'sound', 'id': 'minecraft:entity.goat.screaming.ambient'},
            {'at': 1, 'do': 'say', 'actor': 'nibs', 'text': 'Again?', 'style': 'shout'},
            {'at': 1.5, 'do': 'say', 'actor': 'nibs', 'text': 'Next slide. Next slide!', 'cut_on': 3}]}]}
        out = read.text(read.transcript(raw))
        self.assertIn('picture: A goat stares at a poster.', out)
        self.assertIn('on screen: card: THREE YEARS LATER', out)
        self.assertIn('sound: entity.goat.screaming.ambient', out)
        self.assertIn('Nibs [nibs]: Again?  (shout)', out)
        self.assertIn('(cut to the next shot on "slide!")', out)     # cut_on as a word index names the word


class ReadTests(unittest.TestCase):
    def test_a_read_with_a_fake_model(self):
        seen = {}

        def fake(prompt, images=(), schema=None, model=None):
            seen['prompt'], seen['schema'] = prompt, schema
            return 'Here is my read.\n' + answer(6, [ISSUE])

        raw = script.load(FIXTURE)
        result = read.read(raw, str(FIXTURE), ask=fake)
        self.assertEqual(result['score'], 6)
        self.assertFalse(result['pass'])
        self.assertEqual(result['lines'], 4)
        self.assertIn("Nibs [nibs]: Hey. It's me. Nibs.", seen['prompt'])
        self.assertIn('first time', seen['prompt'])
        self.assertEqual(seen['schema'], read.SCHEMA)
        with tempfile.TemporaryDirectory() as tmp:
            md = read.write(result, tmp, 'nibs-vs-duke')
            text = md.read_text()
            self.assertIn('**6/10 makes sense** (FAIL', text)
            self.assertIn('Why the horn matters is never set up.', text)
            self.assertIn('This horn. Only got the one.', text)
            self.assertEqual(json.loads((Path(tmp) / 'story-read.json').read_text())['score'], 6)
        self.assertIn('This horn. Only got the one.', read.note(result))

    def test_parse_takes_bare_json_and_clamps_the_score(self):
        self.assertEqual(read.parse('{"score": 12, "issues": []}')['score'], 10)
        self.assertEqual(read.parse('noise {"score": 8.4, "understood": "x", "issues": [1, {"shot": "a"}]} tail')['issues'], [{'shot': 'a'}])
        with self.assertRaises(read.ReadError):
            read.parse('I could not read it.')


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='videocraft-read-test-'))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def run_cli(self, argv, fake):
        from videocraft import cli
        out = io.StringIO()
        env = {'VIDEOCRAFT_STORIES': str(self.tmp / 'stories'), 'VIDEOCRAFT_STORY_RUNS': str(self.tmp / 'runs/story')}
        with mock.patch.dict(os.environ, env), mock.patch.object(_ask, 'ask', fake), redirect_stdout(out):
            code = cli.main(argv)
        return code, out.getvalue()

    def test_story_read_on_a_script_file(self):
        code, out = self.run_cli(['story', 'read', str(FIXTURE), '--out', str(self.tmp / 'r')], lambda p, **k: answer(9))
        self.assertEqual(code, 0, out)
        self.assertIn('RESULT   PASS 9/10', out)
        self.assertTrue((self.tmp / 'r/story-read.md').exists())
        code, out = self.run_cli(['story', 'read', str(FIXTURE), '--out', str(self.tmp / 'r')], lambda p, **k: answer(5, [ISSUE]))
        self.assertEqual(code, 1, out)
        self.assertIn('FAIL', out)
        self.assertIn('missing_setup horn', out)

    def test_make_stops_before_the_take_when_the_read_fails(self):
        from videocraft.story.store import Store
        nvd = ROOT / 'stories/nibs-vs-duke'
        answers = {'Stage 1 of 5': (nvd / 'premise.md').read_text(), 'Stage 2 of 5': (nvd / 'bible.toml').read_text(),
                   'Stage 3 of 5': (nvd / 'outline.md').read_text(), 'Stage 4 of 5': (nvd / 'script.md').read_text()}
        text = FIXTURE.read_text().replace('name = "nibs-vs-duke"', 'name = "goat-brag"')
        for d in ('6.2', '1.2', '1.7'):
            text = text.replace(f'duration = {d}', 'duration = 7.0')
        answers['Stage 5 of 5'] = text + '\n[[shot]]\nname = "more"\nduration = 7.0\ncamera = { rig = "orbit" }\n'
        reads = []

        def fake(prompt, images=(), schema=None, model=None):
            if 'A cold read' in prompt:
                reads.append(prompt)
                return answer(4, [ISSUE])
            return next(v for k, v in answers.items() if k in prompt)

        with mock.patch.object(stages, 'lint', lambda path, text: []):
            code, out = self.run_cli(['make', 'a goat brags', '--id', 'goat-brag', '--dry-run', '--read-rounds', '0'], fake)
        self.assertEqual(code, 1, out)
        self.assertIn('READ     4/10 makes sense (FAIL', out)
        self.assertIn('RESULT   FAIL the script does not make sense yet', out)
        self.assertEqual(len(reads), 1)
        self.assertTrue((Store(runs=self.tmp / 'runs/story', stories=self.tmp / 'stories').story_dir('goat-brag') / 'story-read.md').exists())


if __name__ == '__main__':
    unittest.main()
