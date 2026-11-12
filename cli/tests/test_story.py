"""The story pipeline (docs/STORY.md): the store, stage chaining with --from-file, the repair loop, series, make.
No model is called: every model answer here comes from a fake `ask`."""
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
from videocraft.series import series  # noqa: E402
from videocraft.story import _ask, stages  # noqa: E402
from videocraft.story.store import Store, StoryError  # noqa: E402

NVD = ROOT / 'stories/nibs-vs-duke'
FIXTURE = ROOT / 'cli/tests/fixtures/nibs-vs-duke-3shot.toml'


def quiet(*_):
    pass


def model_length_fixture(name='nibs-vs-duke'):
    """The 3-shot fixture stretched to 30 s: a model draft is held to the format's length (a short is 30-90 s)."""
    text = FIXTURE.read_text().replace('name = "nibs-vs-duke"', f'name = "{name}"')
    for d in ('6.2', '1.2', '1.7'):
        text = text.replace(f'duration = {d}', 'duration = 7.0')
    return text + '\n[[shot]]\nname = "more"\nduration = 7.0\ncamera = { rig = "orbit" }\n'


class StoryCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='videocraft-story-test-'))
        self.store = Store(runs=self.tmp / 'runs/story', stories=self.tmp / 'stories')
        # Another workstream's lint is not under test here (stages.lint is tested on its own).
        patcher = mock.patch.object(stages, 'lint', lambda path, text: [])
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def nvd(self, through='script'):
        """nibs-vs-duke's hand-written stages, locked in with --from-file."""
        self.store.create('nibs-vs-duke', fmt='short')
        for stage in ('premise', 'bible', 'outline', 'script')[:('premise', 'bible', 'outline', 'script').index(through) + 1]:
            o = stages.run_stage(self.store, 'nibs-vs-duke', stage, from_file=NVD / f'{stage}.{"toml" if stage == "bible" else "md"}', say=quiet)
            self.assertTrue(o.ok and o.locked, (stage, o.problems))


class StoreTests(StoryCase):
    def test_revisions_parents_and_locking(self):
        s = self.store
        s.create('demo')
        r1 = s.add('demo', 'premise', '# A\n## Logline\nx\n## Format\nshort\n', source='file')
        r2 = s.add('demo', 'premise', '# B\n', parent=r1, note='shorter', source='model')
        self.assertEqual((r1, r2), (1, 2))
        self.assertEqual(s.revision('demo', 'premise', 2)['parent'], 1)
        self.assertEqual(s.revision('demo', 'premise', 2)['note'], 'shorter')
        self.assertTrue((self.tmp / 'runs/story/demo/premise/0002.md').exists())
        self.assertEqual(s.current('demo', 'premise'), 2, 'nothing locked: the newest is current')
        s.lock('demo', 'premise', 1)
        self.assertEqual(s.current('demo', 'premise'), 1)
        self.assertEqual((self.tmp / 'stories/demo/premise.md').read_text(), s.text('demo', 'premise', 1))
        meta = json.loads((self.tmp / 'stories/demo/story.json').read_text())
        self.assertEqual(meta['stages']['premise']['rev'], 1)
        with self.assertRaisesRegex(StoryError, 'no revision 9'):
            s.lock('demo', 'premise', 9)
        with self.assertRaisesRegex(StoryError, 'exists'):
            s.create('demo')

    def test_a_fresh_clone_imports_the_locked_files(self):
        self.nvd('bible')
        shutil.rmtree(self.tmp / 'runs')  # stories/ is committed, runs/ is not
        fresh = Store(runs=self.tmp / 'runs/story', stories=self.tmp / 'stories')
        self.assertEqual(fresh.locked('nibs-vs-duke', 'bible'), 1)
        self.assertEqual(fresh.text('nibs-vs-duke', 'bible'), (NVD / 'bible.toml').read_text())
        self.assertEqual(fresh.stale('nibs-vs-duke', 'bible'), [])
        rev = fresh.add('nibs-vs-duke', 'bible', 'title = "x"\n', parent=1)
        self.assertEqual(rev, 2, 'history continues after the imported revision')

    def test_a_changed_upstream_stage_makes_the_next_one_stale(self):
        self.nvd('outline')
        self.assertEqual(self.store.stale('nibs-vs-duke', 'outline'), [])
        text = (NVD / 'premise.md').read_text().replace('Nibs, a one-horned goat', 'Nibs, a goat')
        rev = self.store.add('nibs-vs-duke', 'premise', text, parent=1)
        self.store.lock('nibs-vs-duke', 'premise', rev)
        self.assertEqual(self.store.stale('nibs-vs-duke', 'outline'), ['premise'])
        self.assertEqual(self.store.stale('nibs-vs-duke', 'bible'), ['premise'])


class ChainTests(StoryCase):
    def test_nibs_vs_duke_from_file_through_a_compiled_plan(self):
        self.nvd('script')
        o = stages.run_stage(self.store, 'nibs-vs-duke', 'shots', from_file=FIXTURE, say=quiet)
        self.assertTrue(o.ok, o.problems)
        self.assertTrue(o.locked)
        plan = json.loads(self.store.revision_path('nibs-vs-duke', 'shots', o.rev).with_suffix('.plan.json').read_text())
        self.assertEqual(plan['plan']['name'], 'nibs-vs-duke')
        self.assertEqual([s['name'] for s in plan['plan']['shots']], ['strut', 'horn', 'bridge'])
        self.assertTrue((self.tmp / 'stories/nibs-vs-duke/shots.toml').exists())
        inputs = self.store.revision('nibs-vs-duke', 'shots', o.rev)['inputs']
        self.assertEqual(sorted(inputs), ['bible', 'outline', 'premise', 'script'])

    def test_a_stage_needs_the_stages_before_it(self):
        self.store.create('lonely')
        with self.assertRaisesRegex(StoryError, 'write premise first'):
            stages.run_stage(self.store, 'lonely', 'outline', ask=lambda p: '', say=quiet)

    def test_a_hand_written_draft_that_fails_is_kept_but_not_locked(self):
        self.nvd('script')
        bad = self.tmp / 'bad.toml'
        bad.write_text(FIXTURE.read_text().replace('rig = "face"', 'rig = "drone"'))
        o = stages.run_stage(self.store, 'nibs-vs-duke', 'shots', from_file=bad, say=quiet)
        self.assertFalse(o.ok)
        self.assertFalse(o.locked)
        self.assertIn('rig "drone" is not a videocraft rig', o.problems[0])
        self.assertIsNone(self.store.locked('nibs-vs-duke', 'shots'))

    def test_the_script_dialogue_of_the_benchmark_is_all_there(self):
        lines = stages.dialogue((NVD / 'script.md').read_text())
        self.assertEqual(len(lines), 24)
        self.assertEqual(lines[0], ('NIBS', "Hey. It's me. *Nibs."))
        self.assertIn(('DUKE', 'A *standing ovation.'), lines)
        self.assertEqual([l for _, l in lines[15:21]], ['*SIX', '*TIMES', '*MORE', '*GOAT', '*THAN', '*HIM'])


class RepairTests(StoryCase):
    def test_the_model_repairs_a_shot_script_that_does_not_compile(self):
        self.nvd('script')
        good = model_length_fixture()
        replies = iter([
            '<<<FILE\nname = "nibs-vs-duke"\n[[shot]]\nname = "a"\n<<<broken toml\nFILE>>>\n',     # not TOML
            '<<<FILE\n' + good.replace('do = "walk"', 'do = "moonwalk"', 1) + 'FILE>>>\n',        # invented action
            'Here you go:\n<<<FILE\n' + good + 'FILE>>>\nHope it helps.',
        ])
        prompts = []

        def fake(prompt, images=(), schema=None, model=None):
            prompts.append(prompt)
            return next(replies)

        o = stages.run_stage(self.store, 'nibs-vs-duke', 'shots', ask=fake, say=quiet)
        self.assertTrue(o.ok, o.problems)
        self.assertEqual((o.rev, o.attempts), (3, 3))
        self.assertEqual(self.store.locked('nibs-vs-duke', 'shots'), 3)
        self.assertIn('Stage 5 of 5', prompts[0])
        self.assertIn('not valid TOML', prompts[1])
        self.assertIn('do = "moonwalk" is not a videocraft action', prompts[2])
        revs = self.store.revisions('nibs-vs-duke', 'shots')
        self.assertEqual([r['source'] for r in revs], ['model', 'repair', 'repair'])
        self.assertEqual([r['parent'] for r in revs], [None, 1, 2])
        # The model is taught the recorder's vocabulary verbatim from docs/SCRIPT.md.
        self.assertIn((ROOT / 'docs/SCRIPT.md').read_text().splitlines()[0], prompts[0])
        self.assertIn('Never a shot over 7.5 s', prompts[0])

    def test_three_failed_repairs_stop_with_the_problems_and_lock_nothing(self):
        self.nvd('script')
        calls = []
        o = stages.run_stage(self.store, 'nibs-vs-duke', 'shots', ask=lambda p, **k: calls.append(p) or 'name = 3',
                             say=quiet)
        self.assertFalse(o.ok)
        self.assertEqual(len(calls), 4, 'one draft and three repairs')
        self.assertEqual(len(self.store.revisions('nibs-vs-duke', 'shots')), 4, 'every attempt is kept')
        self.assertIsNone(self.store.locked('nibs-vs-duke', 'shots'))

    def test_a_too_long_shot_in_a_model_draft_is_sent_back(self):
        self.nvd('script')
        long = model_length_fixture().replace('duration = 7.0', 'duration = 9.0', 1)
        o = stages.run_stage(self.store, 'nibs-vs-duke', 'shots', ask=lambda p, **k: long, repairs=0, say=quiet)
        self.assertTrue(any('never holds a shot over 7.5 s' in p for p in o.problems), o.problems)

    def test_revise_applies_a_note_to_the_current_revision(self):
        self.nvd('outline')
        seen = []
        text = (NVD / 'outline.md').read_text().replace('Snacks', 'Snacks, again')
        o = stages.run_stage(self.store, 'nibs-vs-duke', 'outline', note='retitle beat 2', revise=True,
                             ask=lambda p, **k: seen.append(p) or text, say=quiet)
        self.assertTrue(o.ok, o.problems)
        self.assertIn('retitle beat 2', seen[0])
        self.assertIn('## 2. Snacks (escalation', seen[0], 'the current revision is in the prompt')
        self.assertEqual(self.store.revision('nibs-vs-duke', 'outline', 2)['parent'], 1)

    def test_extract(self):
        self.assertEqual(stages.extract('blah\n<<<FILE\na = 1\nFILE>>>\nmore'), 'a = 1\n')
        self.assertEqual(stages.extract('```toml\na = 1\n```\n'), 'a = 1\n')
        self.assertEqual(stages.extract('a = 1'), 'a = 1\n')


class SeriesTests(StoryCase):
    SPLIT = [
        {'title': 'The Poster', 'logline': 'Nibs finds out Duke won again.', 'previously': '', 'cold_open': 'Nibs struts.',
         'payoff': 'Duke. Again.', 'button': 'Nibs walks into the notice board.', 'gags': ['one horn'],
         'beats': ['setup', 'escalation', 'turn', 'payoff', 'button']},
        {'title': 'The Challenge', 'logline': 'Nibs challenges Duke.', 'previously': 'Duke won again.',
         'cold_open': 'The egg.', 'payoff': 'The scream.', 'button': 'Duke sleeps.', 'gags': ['the yawn']},
    ]

    def test_a_series_shares_the_bible_and_lists_its_episodes(self):
        self.nvd('outline')
        split = self.tmp / 'split.json'
        split.write_text(json.dumps(self.SPLIT))
        ids = series.new(self.store, 'nibs-vs-duke', 2, from_file=split, say=quiet)
        self.assertEqual(ids, ['nibs-vs-duke-e01', 'nibs-vs-duke-e02'])
        e2 = self.store.meta('nibs-vs-duke-e02')
        self.assertEqual((e2['series'], e2['episode'], e2['bible_from']), ('nibs-vs-duke', 2, 'nibs-vs-duke'))
        self.assertEqual(self.store.text('nibs-vs-duke-e02', 'bible'), (NVD / 'bible.toml').read_text())
        premise = self.store.text('nibs-vs-duke-e02', 'premise')
        self.assertIn('## Previously\nDuke won again.', premise)
        self.assertEqual(stages.check('premise', premise, e2), [])
        with self.assertRaisesRegex(StoryError, 'reads its bible from the series story'):
            stages.run_stage(self.store, 'nibs-vs-duke-e01', 'bible', ask=lambda p, **k: '', say=quiet)
        record, rows = series.status(self.store, 'nibs-vs-duke')
        self.assertEqual([r[1] for r in rows], ids)
        self.assertEqual(rows[0][3]['premise'], 'r1')
        self.assertEqual(rows[0][3]['bible'], 'series')
        self.assertEqual(rows[0][3]['outline'], '-')
        # An episode's outline is drafted from its own premise and the series bible.
        seen = []
        stages.run_stage(self.store, 'nibs-vs-duke-e01', 'outline', say=quiet,
                         ask=lambda p, **k: seen.append(p) or (NVD / 'outline.md').read_text())
        self.assertIn('Episode 1 of 2', seen[0])
        self.assertIn('id = "duke"', seen[0])

    def test_a_split_must_continue_the_last_episode(self):
        data, problems = series.parse_split(json.dumps([self.SPLIT[0], {**self.SPLIT[1], 'previously': ''}]), 2)
        self.assertIn('"previously"', problems[0])
        data, problems = series.parse_split(json.dumps(self.SPLIT), 3)
        self.assertIn('3 were asked for', problems[0])


class MakeTests(StoryCase):
    def test_make_dry_run_goes_from_a_prompt_to_a_compiling_shot_script(self):
        answers = {'Stage 1 of 5': (NVD / 'premise.md').read_text(), 'Stage 2 of 5': (NVD / 'bible.toml').read_text(),
                   'Stage 3 of 5': (NVD / 'outline.md').read_text(), 'Stage 4 of 5': (NVD / 'script.md').read_text()}
        answers['Stage 5 of 5'] = model_length_fixture('goat-brag')

        def fake(prompt, images=(), schema=None, model=None):
            return next(v for k, v in answers.items() if k in prompt)

        from videocraft.story import commands
        env = {'VIDEOCRAFT_STORIES': str(self.tmp / 'stories'), 'VIDEOCRAFT_STORY_RUNS': str(self.tmp / 'runs/story')}
        out = io.StringIO()
        with mock.patch.dict(os.environ, env), mock.patch.object(_ask, 'ask', fake), redirect_stdout(out):
            from videocraft import cli
            code = cli.main(['make', 'a goat brags', '--id', 'goat-brag', '--dry-run'])
        self.assertEqual(code, 0, out.getvalue())
        self.assertIn('RESULT   PASS shots.toml compiles', out.getvalue())
        self.assertTrue((self.tmp / 'stories/goat-brag/shots.toml').exists())
        self.assertTrue(commands)


class LockCommandTests(StoryCase):
    def test_lock_checks_the_revision_first(self):
        self.nvd('script')
        bad = self.tmp / 'bad.toml'
        bad.write_text(FIXTURE.read_text().replace('rig = "face"', 'rig = "drone"'))
        stages.run_stage(self.store, 'nibs-vs-duke', 'shots', from_file=bad, say=quiet)
        stages.run_stage(self.store, 'nibs-vs-duke', 'shots', from_file=FIXTURE, lock=False, say=quiet)
        env = {'VIDEOCRAFT_STORIES': str(self.tmp / 'stories'), 'VIDEOCRAFT_STORY_RUNS': str(self.tmp / 'runs/story')}
        from videocraft import cli
        out = io.StringIO()
        with mock.patch.dict(os.environ, env), redirect_stdout(out):
            refused = cli.main(['story', 'lock', 'nibs-vs-duke', 'shots', '1'])
            locked = cli.main(['story', 'lock', 'nibs-vs-duke', 'shots', '2'])
        self.assertEqual((refused, locked), (2, 0), out.getvalue())
        self.assertIn('rig "drone"', out.getvalue())
        self.assertEqual(self.store.locked('nibs-vs-duke', 'shots'), 2)
        self.assertTrue(self.store.revision_path('nibs-vs-duke', 'shots', 2).with_suffix('.plan.json').exists())


class LintHookTests(unittest.TestCase):
    def test_lint_is_skipped_while_it_is_a_placeholder_and_reported_when_it_fails(self):
        # The placeholder takes no file argument, so argparse refuses the call first: skipped, not sent to the model.
        done = mock.Mock(returncode=2, stdout='', stderr='usage: videocraft [-h] [--version]\nvideocraft: error: unrecognized arguments: x.toml')
        with mock.patch.object(stages.subprocess, 'run', return_value=done):
            self.assertEqual(stages.lint(None, 'name = "x"'), [])
        done = mock.Mock(returncode=2, stdout='`videocraft lint` is not implemented yet (workstream d)', stderr='')
        with mock.patch.object(stages.subprocess, 'run', return_value=done):
            self.assertEqual(stages.lint(None, 'name = "x"'), [])
        done = mock.Mock(returncode=1, stdout='shot a: caption needs 2.1 s, has 0.8 s\n', stderr='')
        with mock.patch.object(stages.subprocess, 'run', return_value=done):
            self.assertEqual(stages.lint(None, 'name = "x"'), ['videocraft lint: shot a: caption needs 2.1 s, has 0.8 s'])


if __name__ == '__main__':
    unittest.main()
