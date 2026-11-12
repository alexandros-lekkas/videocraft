"""The dialogue resolver (videocraft.voice) with a fake engine: deterministic word timings, no model."""
import os
import sys
import tempfile
import unittest
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'cli'))
# The suite never starts the voice worker: every script with say cues (here and in other groups' tests) compiles on
# estimated timings unless a test passes its own engine. Set at import, so before any test of the discovery runs.
os.environ.setdefault('VIDEOCRAFT_VOICE', 'estimate')

from videocraft import script  # noqa: E402
from videocraft.voice import cast as castmod  # noqa: E402
from videocraft.voice import front, resolve  # noqa: E402


class FakeEngine:
    """Word i starts at 0.1 + 0.4 i and lasts 0.3 s; writes a short silent wav. Counts what it synthesizes."""
    name = 'fake'
    audio = True

    def __init__(self):
        self.calls = []

    def run(self, specs, outs):
        self.calls.append([' '.join(s['tokens']) for s in specs])
        res = []
        for s, out in zip(specs, outs):
            words = [{'word': t, 'start': round(0.1 + 0.4 * i, 3), 'end': round(0.4 + 0.4 * i, 3)} for i, t in enumerate(s['tokens'])]
            with wave.open(str(out), 'wb') as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(48000)
                w.writeframes(b'\0\0' * 4800)
            res.append({'words': words, 'seconds': words[-1]['end'] + 0.1, 'engine': 'fake', 'timing': 'ok'})
        return res


CAST = {'character': [{'id': 'nibs', 'name': 'Nibs', 'color': '#a8c8ff', 'voice': 'ryan', 'bark': 'minecraft:entity.goat.ambient'},
                      {'id': 'duke', 'name': 'Duke', 'voice': 'aiden'}]}


def shot(name, cues, duration=1.0):
    s = {'name': name, 'camera': {'rig': 'fixed', 'eye': [0, 70, 0], 'at': [0, 70, 5]}, 'cue': cues}
    if duration is not None:
        s['duration'] = duration
    return s


def scene(*shots):
    return {'name': 'talk-test', 'cast': CAST, 'shot': list(shots)}


class Resolver(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = Path(self.tmp.name)
        self.engine = FakeEngine()
        self.log = []

    def tearDown(self):
        self.tmp.cleanup()

    def run_resolve(self, raw, engine=None):
        return resolve.resolve(raw, 'test', engine=engine or self.engine, log=self.log.append, cache=self.cache)

    def test_extend_grows_the_shot_to_the_last_word_plus_tail(self):
        out = self.run_resolve(scene(shot('a', [{'do': 'say', 'actor': 'nibs', 'text': 'This is my *horn now.', 'at': 0.5}])))
        a = out['shot'][0]
        # last word ends at 0.5 + 0.4 * 4 + 0.4 = 2.5; + 0.25 tail = 2.75 s
        self.assertAlmostEqual(a['duration'], 2.75)
        cap = next(c for c in a['cue'] if c['do'] == 'caption')
        self.assertEqual(cap['at'], 0.5)
        self.assertEqual([w['w'] for w in cap['words']], ['This', 'is', 'my', '*horn', 'now.'])
        self.assertEqual([w['at'] for w in cap['words']], [0.1, 0.5, 0.9, 1.3, 1.7])
        self.assertEqual(cap['speaker'], {'name': 'Nibs', 'color': '#a8c8ff'})
        self.assertNotIn('say', [c['do'] for c in a['cue']])
        v = out['edit']['voice']
        self.assertEqual(len(v), 1)
        self.assertEqual((v[0]['shot'], v[0]['at'], v[0]['gain']), ('a', 0.5, 0.0))
        self.assertTrue((ROOT / v[0]['file']).exists() or Path(v[0]['file']).exists())
        d = out['edit']['dialogue'][0]
        self.assertEqual((d['character'], d['shot'], d['start_frame']), ('nibs', 'a', 30))

    def test_a_long_shot_is_not_shortened_and_duration_may_be_left_out(self):
        out = self.run_resolve(scene(shot('a', [{'do': 'say', 'actor': 'duke', 'text': 'Hm.'}], duration=5.0),
                                     shot('b', [{'do': 'say', 'actor': 'duke', 'text': 'Thank you.'}], duration=None)))
        self.assertEqual(out['shot'][0]['duration'], 5.0)
        self.assertAlmostEqual(out['shot'][1]['duration'], round((0.8 + 0.25) * 60) / 60)

    def test_bark_on_the_first_word(self):
        out = self.run_resolve(scene(shot('a', [{'do': 'say', 'actor': 'nibs', 'text': 'Hey.', 'at': 1.0}])))
        snd = next(c for c in out['shot'][0]['cue'] if c['do'] == 'sound')
        self.assertEqual((snd['id'], snd['at'], snd.get('relative')), ('minecraft:entity.goat.ambient', 1.1, True))
        out = self.run_resolve(scene(shot('a', [{'do': 'say', 'actor': 'nibs', 'text': 'Hey.', 'bark': False}])))
        self.assertFalse(any(c['do'] == 'sound' for c in out['shot'][0]['cue']))

    def test_cut_on_ends_the_shot_on_the_word_and_carries_the_rest(self):
        out = self.run_resolve(scene(
            shot('a', [{'do': 'say', 'actor': 'nibs', 'text': 'I challenge you to a *jump-off!', 'at': 0.2, 'cut_on': 'jump-off'}], duration=4.0),
            shot('b', [{'do': 'caption', 'at': 2.0, 'text': 'later'}], duration=1.0)))
        a, b = out['shot']
        # "jump-off!" is word 5: onset 0.2 + 0.1 + 2.0 = 2.3 s = frame 138
        self.assertAlmostEqual(a['duration'], 138 / 60)
        cap = next(c for c in a['cue'] if c['do'] == 'caption')
        self.assertEqual([w['w'] for w in cap['words']], ['I', 'challenge', 'you', 'to', 'a'])
        carried = b['cue'][0]
        self.assertEqual((carried['do'], carried['at']), ('caption', 0.0))
        self.assertEqual(carried['words'], [{'w': '*jump-off!', 'at': 0.0}])
        # the voice plays on into b: b lasts to the word's end + tail (0.3 + 0.25 s) or its own 2 s caption
        self.assertGreaterEqual(b['duration'], 1.0)
        d = out['edit']['dialogue'][0]
        self.assertEqual(d['cut_on'], {'word': '*jump-off!', 'index': 5, 'onset': 2.3, 'frame': 138})
        self.assertEqual(d['carried_to'], 'b')
        self.assertEqual(out['edit']['voice'][0]['shot'], 'a')

    def test_cut_on_checks_the_word_and_late_cues(self):
        with self.assertRaisesRegex(script.ScriptError, 'not a word of the line'):
            self.run_resolve(scene(shot('a', [{'do': 'say', 'actor': 'nibs', 'text': 'Hey there.', 'cut_on': 'nope'}]), shot('b', [])))
        with self.assertRaisesRegex(script.ScriptError, 'now ends on'):
            self.run_resolve(scene(shot('a', [{'do': 'say', 'actor': 'nibs', 'text': 'Hey there.', 'cut_on': 'there'},
                                              {'do': 'caption', 'at': 3.0, 'text': 'late'}], duration=4.0), shot('b', [])))

    def test_lines_without_at_follow_each_other(self):
        out = self.run_resolve(scene(shot('a', [{'do': 'say', 'actor': 'nibs', 'text': 'One two.', 'at': 0.5, 'pause_after': 0.3},
                                                {'do': 'say', 'actor': 'duke', 'text': 'Three.'}])))
        caps = [c for c in out['shot'][0]['cue'] if c['do'] == 'caption']
        # the first ends at 0.5 + 0.8 = 1.3; + 0.3 pause
        self.assertAlmostEqual(caps[1]['at'], 1.6)
        self.assertEqual(caps[1]['speaker']['name'], 'Duke')

    def test_cache_makes_a_rerun_free_and_identical(self):
        raw = scene(shot('a', [{'do': 'say', 'actor': 'nibs', 'text': 'Hey.'}, {'do': 'say', 'actor': 'duke', 'text': 'Hm.'}]))
        first = self.run_resolve(raw)
        self.assertEqual(self.engine.calls, [['Hey.', 'Hm.']])
        again = self.run_resolve(raw)
        self.assertEqual(self.engine.calls, [['Hey.', 'Hm.']])
        strip = lambda o: [{k: v for k, v in d.items() if k != 'cached'} for d in o['edit']['dialogue']]  # noqa: E731
        self.assertEqual(strip(first), strip(again))
        self.assertEqual(first['shot'], again['shot'])
        self.assertTrue(all(d['cached'] for d in again['edit']['dialogue']))
        # a different style is a different take; the other line still comes from the cache
        raw['shot'][0]['cue'][0]['style'] = 'shout'
        self.run_resolve(raw)
        self.assertEqual(self.engine.calls[-1], ['Hey.'])

    def test_estimate_fallback_has_captions_but_no_voice(self):
        out = self.run_resolve(scene(shot('a', [{'do': 'say', 'actor': 'nibs', 'text': 'Best jumper in the whole *valley.'}])),
                               engine=front.EstimateEngine())
        self.assertNotIn('voice', out['edit'])
        cap = next(c for c in out['shot'][0]['cue'] if c['do'] == 'caption')
        ats = [w['at'] for w in cap['words']]
        self.assertEqual(ats, sorted(ats))
        self.assertGreater(out['shot'][0]['duration'], 1.5)
        self.assertEqual(out['edit']['dialogue'][0]['engine'], 'estimate')

    def test_engine_for_warns_and_estimates_without_a_voice(self):
        saved = front.installed
        front.installed = lambda: False
        try:
            log = []
            self.assertIsInstance(front.engine_for('auto', log=log.append), front.EstimateEngine)
            self.assertIn('WARNING', log[0])
            with self.assertRaises(front.VoiceError):
                front.engine_for('voice', log=log.append)
        finally:
            front.installed = saved

    def test_unknown_keys_and_characters(self):
        with self.assertRaisesRegex(script.ScriptError, 'unknown key'):
            self.run_resolve(scene(shot('a', [{'do': 'say', 'actor': 'nibs', 'text': 'Hey.', 'volume': 3}])))
        self.run_resolve(scene(shot('a', [{'do': 'say', 'actor': 'stranger-x', 'text': 'Who?'}])))
        self.assertTrue(any('stranger-x' in l and 'generic' in l for l in self.log))

    def test_the_estimate_reads_at_about_two_and_a_half_words_a_second(self):
        words = front.estimate('So today, I challenge Duke to a jump-off!'.split())
        rate = len(words) / words[-1]['end']
        self.assertTrue(2.0 < rate < 3.2, rate)


class Casts(unittest.TestCase):
    def test_the_committed_cast(self):
        chars, _ = castmod.read_file(ROOT / 'cast/nibs-vs-duke.toml')
        self.assertEqual((chars['nibs'].engine, chars['nibs'].voice), ('qwen3', 'ryan'))
        self.assertEqual((chars['duke'].engine, chars['duke'].voice), ('qwen3', 'aiden'))
        spec = chars['duke'].spec(['Hm.'], 'sleepy', 1.0, castmod.STYLES)
        self.assertIn('Sleepy', spec['instruct'])
        draft = chars['duke'].spec(['Hm.'], None, 1.0, castmod.STYLES, draft=True)
        self.assertEqual((draft['engine'], draft['voice'], draft['instruct']), ('kokoro', 'am_onyx', None))

    def test_style_keys_change_the_cache_key(self):
        ch = castmod.Character(id='x', name='X', color='#fff')
        a, b = ch.spec(['Hi.'], None), ch.spec(['Hi.'], 'whisper')
        self.assertNotEqual(front.key_of(a), front.key_of(b))
        self.assertEqual(front.key_of(a), front.key_of(ch.spec(['Hi.'], None)))


class Compile(unittest.TestCase):
    def test_talk_example_compiles_without_a_voice(self):
        saved = os.environ.get('VIDEOCRAFT_VOICE')
        os.environ['VIDEOCRAFT_VOICE'] = 'estimate'
        try:
            plan, edit = script.compile_script(script.load(ROOT / 'examples/talk.toml'), str(ROOT / 'examples/talk.toml'))
        finally:
            if saved is None:
                os.environ.pop('VIDEOCRAFT_VOICE', None)
            else:
                os.environ['VIDEOCRAFT_VOICE'] = saved
        dos = [c['do'] for s in plan['shots'] for c in s['timeline']]
        self.assertNotIn('say', dos)
        self.assertGreaterEqual(dos.count('caption'), 4)
        self.assertEqual(len(edit['dialogue']), 4)
        self.assertTrue(any(d.get('cut_on') for d in edit['dialogue']))

    def test_lint_sees_resolved_lines_and_treats_spoken_captions_as_subtitles(self):
        from videocraft import lint
        problems = lint.lint(script.load(ROOT / 'examples/talk.toml'))
        self.assertFalse([p for p in problems if p['severity'] == 'error'], problems)
        self.assertTrue(any('spoken' in p['message'] for p in problems))
        raw = scene(shot('a', [{'do': 'say', 'actor': 'nibs', 'text': 'Hey you.', 'fit': 'none', 'at': 0.5}], duration=0.8))
        self.assertTrue(any(p['rule'] == 'reading' and p['severity'] == 'error' for p in lint.lint(raw)), 'up under 1 s')

    def test_scripts_without_say_are_untouched(self):
        raw = script.load(ROOT / 'examples/hello.toml')
        self.assertFalse(resolve.has_say(raw))


if __name__ == '__main__':
    unittest.main()
