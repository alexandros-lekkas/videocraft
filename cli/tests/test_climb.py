"""The climb's loop with the take, the reviewers and the model stubbed: keep if better, budget, rejected proposals."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from videocraft import agents, climb, script, store  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


class Climb(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.runs = self.tmp / 'runs'
        self.patches = [mock.patch.object(store, 'RUNS', self.runs), mock.patch.object(climb, 'RUNS', self.runs)]
        for p in self.patches:
            p.start()
        self.scores = iter([4.0, 5.5, 5.0, 6.5])   # baseline, then one per proposal
        self.asked = []

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp)

    def take(self, path, parent):
        plan, edit = script.compile_script(script.load(path), str(path))
        it = store.new_iteration(path, plan, edit, parent=parent)
        (it.take / 'result.json').write_text(json.dumps({'verdict': 'PASS', 'shots': []}))
        return it, 0

    def review(self, it, rub, roles):
        avg = next(self.scores)
        s = {'rubric': rub['name'], 'average': avg, 'minimum': avg, 'gates': {}, 'criteria': {}, 'fixes': [
            {'reviewer': 'camera', 'fix': 'slow the orbit', 'why': 'too fast'}], 'reviewers': roles or []}
        (it.path / 'score.json').write_text(json.dumps(s))
        return s

    def ask(self, prompt, images=(), schema=None, model=None, **kw):
        self.asked.append(prompt)
        n = len(self.asked)
        if n == 1:
            renamed = (ROOT / 'examples/hello.toml').read_text().replace('name = "hello"', 'name = "renamed"')
            return f'```toml\n{renamed}```'                     # rejected: renames the script
        text = (ROOT / 'examples/hello.toml').read_text().replace('sweep = 70', f'sweep = {70 - n * 5}')
        return f'```toml\n{text}```\n```markdown\n- slowed the orbit to {70 - n * 5} degrees (camera fix)\n```'

    def test_keeps_only_improvements_and_spends_the_budget(self):
        with mock.patch.object(agents, 'ask', self.ask):
            log = climb.climb(ROOT / 'examples/hello.toml', 4, 'general', 'camera', None, self.take, self.review, say=lambda *a: None)
        self.assertEqual(log['spent'], 4)
        steps = [(s['iteration'], s['parent'], s['average'], s['kept']) for s in log['steps']]
        self.assertEqual(steps, [('0001', None, 4.0, True), ('0002', '0001', 5.5, True), ('0003', '0002', 5.0, False), ('0004', '0002', 6.5, True)])
        self.assertEqual(log['best'], '0004')
        self.assertIn('Your last proposal was rejected', self.asked[1])      # the renamed script came back with the error
        self.assertIn('renames the script', self.asked[1])
        index = json.loads((self.runs / 'hello/index.json').read_text())
        chains = {r['iteration']: r['chain'] for r in index['iterations']}
        self.assertEqual(chains['0004'], ['0002', '0001'])
        self.assertTrue((self.runs / 'hello/0002/notes.md').read_text().startswith('# 0002 from 0001'))
        self.assertEqual(sorted(p.name for p in (self.runs / 'hello/proposals').iterdir()), ['0001.toml', '0002.toml', '0003.toml'])


if __name__ == '__main__':
    unittest.main()
