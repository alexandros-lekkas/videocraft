"""Different people, different voices: the cast lint (voice/cast.py lint, lint.cast_rules)."""
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'cli'))
os.environ.setdefault('VIDEOCRAFT_VOICE', 'estimate')

from videocraft import lint  # noqa: E402
from videocraft.voice import cast as castmod  # noqa: E402


def cast_of(*chars):
    return castmod.load({'character': list(chars)})


def rules(problems):
    return [(p['severity'], p['where']) for p in problems if p['rule'] == 'cast_voice']


class CastLint(unittest.TestCase):
    def test_distinct_voices_pass(self):
        c = cast_of({'id': 'a', 'voice': 'ryan'}, {'id': 'b', 'voice': 'aiden'}, {'id': 'n', 'engine': 'kokoro', 'voice': 'bm_george'})
        self.assertEqual(castmod.lint(c, ['a', 'b', 'n']), [])

    def test_the_same_voice_twice_is_an_error_with_a_free_preset(self):
        c = cast_of({'id': 'a', 'voice': 'ryan', 'instruct': 'Brash.'}, {'id': 'b', 'voice': 'ryan', 'instruct': 'brash. '})
        problems = castmod.lint(c, ['a', 'b'])
        self.assertEqual(rules(problems), [('error', 'cast b')])
        suggested = castmod.suggest('qwen3', 'ryan', {('qwen3', 'ryan')})
        self.assertEqual(suggested, 'voice = "aiden"')          # the other English-native qwen3 preset
        self.assertIn(suggested, problems[0]['message'])
        both = castmod.suggest('qwen3', 'ryan', {('qwen3', 'ryan'), ('qwen3', 'aiden')})
        self.assertTrue(both.startswith('engine = "kokoro", voice = "am_'), both)   # none left: an English kokoro voice

    def test_one_preset_with_two_instructions_is_a_warning(self):
        c = cast_of({'id': 'a', 'voice': 'ryan', 'instruct': 'Brash.'}, {'id': 'b', 'voice': 'ryan', 'instruct': 'Gruff and slow.'})
        self.assertEqual(rules(castmod.lint(c, ['a', 'b'])), [('warn', 'cast b')])

    def test_a_suggestion_keeps_the_kind_of_voice(self):
        used = {('kokoro', 'am_onyx')}
        voice = lambda hint: hint.split('"')[-2]
        self.assertEqual(castmod.kind_of('kokoro', voice(castmod.suggest('kokoro', 'am_onyx', used))), 'male')
        self.assertEqual(castmod.kind_of('kokoro', voice(castmod.suggest('kokoro', 'af_heart', used))), 'female')

    def test_a_generic_voice_one_name_for_two_and_colliding_drafts_are_warned(self):
        c = cast_of({'id': 'a', 'voice': 'ryan', 'name': 'Board member', 'draft': {'engine': 'kokoro', 'voice': 'am_onyx'}},
                    {'id': 'b', 'engine': 'kokoro', 'voice': 'am_onyx', 'name': 'Board member'})
        got = castmod.lint(c, ['a', 'b', 'stranger'])
        text = ' '.join(p['message'] for p in got)
        self.assertIn('in no cast', text)
        self.assertIn('called "Board member"', text)
        self.assertIn('draft', text)
        self.assertTrue(all(p['severity'] == 'warn' for p in got if 'stranger' not in p['where']))

    def test_lint_checks_the_scripts_speakers(self):
        raw = {'name': 'x', 'cast': {'character': [{'id': 'a', 'voice': 'ryan'}, {'id': 'b', 'voice': 'ryan'}]},
               'shot': [{'name': 's1', 'duration': 3, 'cue': [{'do': 'say', 'at': 0, 'actor': 'a', 'text': 'Hello there.'},
                                                              {'do': 'say', 'actor': 'b', 'text': 'Hi.'}]}]}
        self.assertEqual(rules(lint.cast_rules(raw)), [('error', 'cast b')])
        self.assertIn(('error', 'cast b'), rules(lint.lint(raw)))

    def test_measured_voices_too_close_in_pitch_sound_alike(self):
        c = cast_of({'id': 'a', 'voice': 'ryan'}, {'id': 'b', 'voice': 'aiden'})
        close = castmod.lint(c, ['a', 'b'], pitches={'a': 216.0, 'b': 200.0})
        self.assertEqual(rules(close), [('warn', 'cast b')])
        self.assertIn('sound alike', close[0]['message'])
        self.assertEqual(castmod.lint(c, ['a', 'b'], pitches={'a': 216.0, 'b': 131.0}), [])

    def test_pitch_of_a_tone(self):
        import array
        import math
        import tempfile
        import wave
        from videocraft.voice import pitch
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'line.wav'
            sr = 48000
            a = array.array('h', [int(8000 * math.sin(2 * math.pi * 180 * i / sr)) for i in range(sr)])
            with wave.open(str(path), 'wb') as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(sr)
                w.writeframes(a.tobytes())
            self.assertAlmostEqual(pitch.median_f0(path), 180.0, delta=4.0)
            self.assertTrue((Path(tmp) / 'line.wav.f0.json').exists())       # cached beside the line
            got = pitch.character_pitches([{'character': 'a', 'file': str(path)}])
            self.assertAlmostEqual(got['a'], 180.0, delta=4.0)

    def test_the_committed_cast_has_a_voice_each(self):
        chars, _ = castmod.read_file(ROOT / 'cast/nibs-vs-duke.toml')
        self.assertEqual(castmod.lint(castmod.Cast(chars), list(chars)), [])


if __name__ == '__main__':
    unittest.main()
