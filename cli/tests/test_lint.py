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

    def test_examples_lint_and_hello_is_clean(self):
        for path in sorted((ROOT / 'examples').glob('*.toml')):
            problems = lint.lint(script.load(path))          # every example lints without crashing
            self.assertTrue(all(p['severity'] in ('error', 'warn', 'info') for p in problems))
        self.assertEqual(lint.lint(script.load(ROOT / 'examples/hello.toml')), [])

    def test_reading_time(self):
        self.assertEqual(lint.reading_seconds(1), 1.2)
        self.assertAlmostEqual(lint.reading_seconds(4), 1.7)


if __name__ == '__main__':
    unittest.main()


class Registries(unittest.TestCase):
    """lint's built-in actions and rigs are exactly what the mod registers (r.action / r.rig in the Java sources)."""

    @staticmethod
    def registered(kind):
        import re
        pattern = re.compile(r'\br\.' + kind + r'\(\s*"([a-z0-9_]+)"')
        names = set()
        for path in (ROOT / 'src/main/java').rglob('*.java'):
            names |= set(pattern.findall(path.read_text()))
        return names

    def test_actions_match_the_registries(self):
        java = self.registered('action')
        self.assertGreater(len(java), 30)
        self.assertEqual(lint.BUILT_IN - lint.COMPILED, java,
                         f'missing from lint: {sorted(java - lint.BUILT_IN)}; not in the mod: {sorted(lint.BUILT_IN - lint.COMPILED - java)}')

    def test_rigs_match_the_registries(self):
        java = self.registered('rig')
        self.assertIn('lead', java)
        self.assertEqual(lint.BUILT_IN_RIGS, java,
                         f'missing from lint: {sorted(java - lint.BUILT_IN_RIGS)}; not in the mod: {sorted(lint.BUILT_IN_RIGS - java)}')

    def test_unknown_rig(self):
        raw = {'name': 'x', 'shot': [{'name': 'a', 'duration': 1, 'camera': {'rig': 'orbitt'}},
                                     {'name': 'b', 'duration': 1, 'camera': {'rig': 'mymod:spin'}}]}
        rigs = [p for p in lint.lint(raw) if p['rule'] == 'unknown_rig']
        self.assertEqual([(p['severity'], p['where']) for p in rigs], [('warn', 'shot a.camera')])


class VoicedAndFast(unittest.TestCase):
    """The rules that make voiced, brisk dialogue the default: unvoiced_text, slow_line, dead_air."""

    CAST = {'character': [{'id': 'nibs', 'voice': 'ryan'}, {'id': 'duke', 'voice': 'aiden'}]}

    def setUp(self):
        import os
        self.saved = os.environ.get('VIDEOCRAFT_VOICE')
        os.environ['VIDEOCRAFT_VOICE'] = 'estimate'

    def tearDown(self):
        import os
        if self.saved is None:
            os.environ.pop('VIDEOCRAFT_VOICE', None)
        else:
            os.environ['VIDEOCRAFT_VOICE'] = self.saved

    @staticmethod
    def shot(name, cues, duration=None):
        s = {'name': name, 'camera': {'rig': 'fixed', 'eye': [0, 70, 0], 'at': [0, 70, 5]}, 'cue': cues}
        if duration is not None:
            s['duration'] = duration
        return s

    def rules(self, raw, rule):
        return [p for p in lint.lint(raw) if p['rule'] == rule]

    def test_unvoiced_text_in_a_script_with_a_cast(self):
        raw = {'name': 'x', 'cast': self.CAST, 'shot': [self.shot('a', [
            {'do': 'say', 'actor': 'nibs', 'text': 'Hey there, it is me.', 'at': 0.2},
            {'do': 'caption', 'at': 2.5, 'text': 'I am the best jumper'},
            {'do': 'card', 'at': 4.0, 'title': 'a card says what it likes'},
            {'do': 'caption', 'at': 4.5, 'text': 'Snacks.'}], duration=6.0)]}
        hits = self.rules(raw, 'unvoiced_text')
        self.assertEqual([(p['severity'], p['where']) for p in hits], [('warn', 'shot a.cue[1]')])
        self.assertIn('voice it with `say`', hits[0]['message'])
        # a cast with no say lines yet: still warned; no cast: captions are a silent film's business
        raw['shot'][0]['cue'].pop(0)
        self.assertEqual(len(self.rules(raw, 'unvoiced_text')), 1)
        raw.pop('cast')
        self.assertEqual(self.rules(raw, 'unvoiced_text'), [])

    def test_slow_line(self):
        raw = {'name': 'x', 'cast': self.CAST, 'shot': [self.shot('a', [
            {'do': 'say', 'actor': 'nibs', 'text': 'Best jumper in the whole valley.', 'pace': 0, 'speed': 0.6},
            {'do': 'say', 'actor': 'duke', 'text': 'That was a yawn.', 'style': 'deadpan', 'pace': 0, 'speed': 0.6},
            {'do': 'say', 'actor': 'duke', 'text': 'Best jumper in the whole valley.'}])]}
        hits = self.rules(raw, 'slow_line')
        self.assertEqual([(p['severity'], p['where']) for p in hits], [('warn', 'line a-1'), ('info', 'line a-2')])

    def test_dead_air_inside_dialogue_but_not_over_black_beats_or_action(self):
        def raw(**second):
            return {'name': 'x', 'cast': self.CAST, 'shot': [
                self.shot('a', [{'do': 'say', 'actor': 'nibs', 'text': 'Hey there, it is me.', 'at': 0.2}], duration=4.0),
                self.shot('b', [{'do': 'say', 'actor': 'duke', 'text': 'Well, hello to you.', 'at': 0.1, **second}])]}
        hits = self.rules(raw(), 'dead_air')
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]['where'], 'line b-1')
        self.assertEqual(self.rules(raw(beat=True), 'dead_air'), [])
        black = raw()
        black['edit'] = {'clip': [{'shot': 'a'}, {'black': 0.5}, {'shot': 'b'}]}
        self.assertEqual(self.rules(black, 'dead_air'), [])
        action = raw()
        action['shot'].insert(1, self.shot('jump', [{'do': 'jump', 'actor': 'player', 'at': 0.1}], duration=1.0))
        self.assertEqual(self.rules(action, 'dead_air'), [])
        # packed lines in one shot leave no dead air
        packed = {'name': 'x', 'cast': self.CAST, 'shot': [self.shot('a', [
            {'do': 'say', 'actor': 'nibs', 'text': 'Hey there, it is me.', 'at': 0.2},
            {'do': 'say', 'actor': 'duke', 'text': 'Well, hello to you.', 'at': 4.0}])]}
        self.assertEqual(self.rules(packed, 'dead_air'), [])

    def test_the_talk_example_is_voiced_and_fast(self):
        problems = lint.lint(script.load(ROOT / 'examples/talk.toml'))
        self.assertFalse([p for p in problems if p['severity'] in ('error', 'warn')], problems)


class DialogueMeasures(unittest.TestCase):
    def test_summary_share_silences_and_dead_air(self):
        from videocraft.measure import dialogue
        lines = [{'id': 'a', 'start': 0.5, 'end': 2.5, 'words': 7, 'wps': 3.5},
                 {'id': 'b', 'start': 2.7, 'end': 4.0, 'words': 3, 'wps': 2.3},
                 {'id': 'c', 'start': 6.0, 'end': 7.0, 'words': 3, 'wps': 3.0, 'beat': False},
                 {'id': 'd', 'start': 9.0, 'end': 9.5, 'words': 2, 'wps': 4.0}]
        segments = [{'start': 0, 'end': 5, 'kind': 'shot', 'shot': 's1'}, {'start': 5, 'end': 8, 'kind': 'shot', 'shot': 's2'},
                    {'start': 8, 'end': 8.5, 'kind': 'black', 'shot': None}, {'start': 8.5, 'end': 10, 'kind': 'shot', 'shot': 's3'}]
        s = dialogue.summary(lines, segments, {'s1', 's2', 's3'}, 10.0)
        self.assertAlmostEqual(s['voice_seconds'], 4.8)
        self.assertAlmostEqual(s['voice_share'], 0.48)
        self.assertEqual([g['seconds'] for g in s['longest_silences']], [2.0, 2.0, 0.2])
        self.assertEqual([(g['after'], g['before']) for g in s['dead_air']], [('b', 'c')])   # c-d crosses black
        self.assertEqual(s['slow_lines'], [{'id': 'b', 'wps': 2.3, 'slow_style': False}])
