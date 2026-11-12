"""lint catches each rule on a fixture script, and passes the examples."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from videocraft import lint, script  # noqa: E402
from videocraft.review import rubric  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


class Lint(unittest.TestCase):
    def test_every_rule_on_the_fixture(self):
        problems = lint.lint(script.load(ROOT / 'cli/tests/fixtures/lint-every-rule.toml'), rubric.load('pinksheep-style'))
        found = {(p['severity'], p['rule']) for p in problems}
        for expected in [('error', 'unknown_key'), ('error', 'cue_outside'), ('warn', 'unknown_action'), ('error', 'unknown_actor'),
                         ('error', 'reading'), ('warn', 'words_per_second'), ('error', 'two_messages'), ('warn', 'long_shot'),
                         ('error', 'anchor'), ('info', 'anchor'), ('warn', 'mark'), ('info', 'reading')]:
            self.assertIn(expected, found, f'{expected} not found in {sorted(found)}')
        unknown = {p['message'].split('`')[1] for p in problems if p['rule'] == 'unknown_key'}
        self.assertTrue({'colour', 'sunset'} <= unknown)        # world.set and until join the allow-lists as others land
        self.assertEqual(sum(1 for p in problems if p['rule'] == 'mark'), 2)            # until and edit.clip.in
        anchors = [p for p in problems if p['rule'] == 'anchor' and p['severity'] == 'error']
        self.assertEqual(len(anchors), 1)                                              # market-lane is placed; barn is not
        self.assertIn('barn', anchors[0]['message'])

    def test_no_rubric_no_long_shot(self):
        problems = lint.lint(script.load(ROOT / 'cli/tests/fixtures/lint-every-rule.toml'))
        self.assertNotIn('long_shot', {p['rule'] for p in problems})

    def test_examples_are_clean(self):
        for path in sorted((ROOT / 'examples').glob('*.toml')):
            errors = [p for p in lint.lint(script.load(path)) if p['severity'] == 'error']
            self.assertEqual(errors, [], f'{path.name}: {errors}')

    def test_reading_time(self):
        self.assertEqual(lint.reading_seconds(1), 1.2)
        self.assertAlmostEqual(lint.reading_seconds(4), 1.7)


if __name__ == '__main__':
    unittest.main()
