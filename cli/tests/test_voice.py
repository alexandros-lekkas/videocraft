"""The dialogue resolver (videocraft.voice) with a fake engine: deterministic word timings, no model."""
import array
import math
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
from videocraft.voice import front, pace, resolve  # noqa: E402


def tone_wav(path, spans, seconds, sr=48000):
    """A 16-bit mono wav: a 220 Hz tone inside each (start, end) span, silence elsewhere."""
    a = array.array('h', [0] * int(seconds * sr))
    for s, e in spans:
        for i in range(int(s * sr), min(len(a), int(e * sr))):
            a[i] = int(9000 * math.sin(2 * math.pi * 220 * i / sr))
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(a.tobytes())


class FakeEngine:
    """Word i starts at 0.1 + 0.4 i and lasts 0.3 s (or `step`/`length`); writes a wav with a tone on every word
    and 0.1 s after the last. Counts what it synthesizes."""
    name = 'fake'
    audio = True

    def __init__(self, step=0.4, length=0.3, head=0.1):
        self.calls = []
        self.step, self.length, self.head = step, length, head

    def run(self, specs, outs):
        self.calls.append([' '.join(s['tokens']) for s in specs])
        res = []
        for s, out in zip(specs, outs):
            words = [{'word': t, 'start': round(self.head + self.step * i, 3), 'end': round(self.head + self.step * i + self.length, 3)}
                     for i, t in enumerate(s['tokens'])]
            tone_wav(out, [(w['start'], w['end']) for w in words], words[-1]['end'] + 0.1)
            res.append({'words': words, 'seconds': words[-1]['end'] + 0.1, 'engine': 'fake', 'timing': 'ok'})
        return res


# pace = 0: these tests are about the resolver's arithmetic on the engine's own timings (Pacing tests the rest)
CAST = {'character': [{'id': 'nibs', 'name': 'Nibs', 'color': '#a8c8ff', 'voice': 'ryan', 'bark': 'minecraft:entity.goat.ambient', 'pace': 0},
                      {'id': 'duke', 'name': 'Duke', 'voice': 'aiden', 'pace': 0}]}


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

    def test_fit_none_line_over_the_cut_carries_its_caption_through_short_shots(self):
        # Words at 0.1 + 0.4 i (0.3 s long) from at = 0.5: onsets 0.6, 1.0, 1.4, 1.8, 2.2
        out = self.run_resolve(scene(
            shot('a', [{'do': 'say', 'actor': 'nibs', 'text': 'one two three *four five', 'at': 0.5, 'fit': 'none'}], duration=1.2),
            shot('b', [], duration=0.4),
            shot('c', [], duration=1.0)))
        a, b, c = out['shot']
        self.assertEqual((a['duration'], b['duration'], c['duration']), (1.2, 0.4, 1.0))   # lengths as written
        cap = next(x for x in a['cue'] if x['do'] == 'caption')
        self.assertEqual([w['w'] for w in cap['words']], ['one', 'two'])
        # b: the whole line so far, "one two" settled before the cut, "three" pops at 1.4 - 1.2
        cb = b['cue'][0]
        self.assertEqual([(w['w'], w['at']) for w in cb['words']], [('one', -0.6), ('two', -0.2), ('three', 0.2)])
        cc = c['cue'][0]
        self.assertEqual([(w['w'], w['at']) for w in cc['words']],
                         [('one', -1.0), ('two', -0.6), ('three', -0.2), ('*four', 0.2), ('five', 0.6)])
        d = out['edit']['dialogue'][0]
        self.assertEqual((d['carried_to'], d['carried_through']), ('b', ['b', 'c']))

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
        # the first voice ends at 0.5 + 0.8 = 1.3; + 0.3 pause: the second voice's first word at 1.6
        self.assertAlmostEqual(caps[1]['at'] + caps[1]['words'][0]['at'], 1.6)
        self.assertEqual(caps[1]['speaker']['name'], 'Duke')

    def test_lines_are_packed_with_the_default_gap(self):
        out = self.run_resolve(scene(shot('a', [{'do': 'say', 'actor': 'nibs', 'text': 'One two.', 'at': 0.5},
                                                {'do': 'say', 'actor': 'duke', 'text': 'Three four.', 'at': 3.0},
                                                {'do': 'say', 'actor': 'nibs', 'text': 'Five.', 'gap': 0.3}], duration=None)))
        d = out['edit']['dialogue']
        starts = [x['at'] + x['words'][0]['start'] for x in d]
        ends = [x['at'] + x['words'][-1]['end'] for x in d]
        # the first at its at; the second's written at = 3.0 is packed GAP after the first; the third after its gap
        self.assertAlmostEqual(starts[0], 0.6)
        self.assertAlmostEqual(starts[1] - ends[0], resolve.GAP)
        self.assertAlmostEqual(starts[2] - ends[1], 0.3)
        self.assertTrue(any('packed' in l for l in self.log))
        # the shot ends `tail` after the last word: no dead air at its end
        self.assertAlmostEqual(out['shot'][0]['duration'], math.ceil((ends[2] + resolve.TAIL) * 60 - 1e-6) / 60)

    def test_a_beat_keeps_its_at(self):
        out = self.run_resolve(scene(shot('a', [{'do': 'say', 'actor': 'nibs', 'text': 'One two.', 'at': 0.5},
                                                {'do': 'say', 'actor': 'duke', 'text': 'Three.', 'at': 3.0, 'beat': True}])))
        self.assertEqual(out['edit']['dialogue'][1]['at'], 3.0)
        self.assertTrue(out['edit']['dialogue'][1]['beat'])

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


class Pacing(unittest.TestCase):
    """pace.py on synthetic wavs: silence trimmed, pauses capped, slow lines stretched, word timings exact."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def line(self, words, seconds):
        wav = self.dir / 'raw.wav'
        tone_wav(wav, [(w['start'], w['end']) for w in words], seconds)
        return wav

    @staticmethod
    def onsets(path, thresh=2000):
        samples, sr = pace.read_wav(path)
        on, prev, n = [], False, sr // 200
        for i in range(0, len(samples), n):
            loud = max(abs(x) for x in samples[i:i + n]) > thresh
            if loud and not prev:
                on.append(i / sr)
            prev = loud
        return on, len(samples) / sr

    def test_trims_head_and_tail_and_caps_pauses(self):
        words = [{'word': 'Hey.', 'start': 0.5, 'end': 0.9}, {'word': 'It', 'start': 1.9, 'end': 2.1},
                 {'word': 'is,', 'start': 2.15, 'end': 2.45}, {'word': 'me.', 'start': 3.25, 'end': 3.6}]
        wav = self.line(words, 4.6)
        out = self.dir / 'paced.wav'
        opts = pace.options({'wps': 3.2, 'caps': True, 'stretch': False})
        w, seconds, info = pace.pace_file(wav, words, opts, out)
        self.assertAlmostEqual(w[0]['start'], pace.HEAD, delta=0.011)
        self.assertLessEqual(seconds - w[-1]['end'], pace.TAIL + 0.03 + 0.011)
        gaps = [b['start'] - a['end'] for a, b in zip(w, w[1:])]
        self.assertAlmostEqual(gaps[0], pace.SENTENCE, delta=0.012)   # after "Hey." (was 1.0 s)
        self.assertAlmostEqual(gaps[1], 0.05, delta=0.005)            # a short gap is left alone
        self.assertAlmostEqual(gaps[2], pace.COMMA, delta=0.012)      # after "is," (was 0.8 s)
        self.assertEqual(info['stretch'], 1.0)
        self.assertGreater(info['wps'], info['wps_raw'])
        # the words are where the audio is: every tone onset matches a word start
        on, _ = self.onsets(out)
        self.assertEqual(len(on), 4)
        for o, x in zip(on, w):
            self.assertAlmostEqual(o, x['start'], delta=0.012)

    def test_a_deadpan_or_beat_line_keeps_its_pauses(self):
        words = [{'word': 'That.', 'start': 0.1, 'end': 0.4}, {'word': 'Was.', 'start': 1.4, 'end': 1.7}]
        wav = self.line(words, 1.8)
        opts = pace.options({'wps': 3.2, 'caps': False, 'stretch': False})
        w, _, _ = pace.pace_file(wav, words, opts, self.dir / 'p.wav')
        self.assertAlmostEqual(w[1]['start'] - w[0]['end'], 1.0, delta=0.012)
        ch = castmod.Character(id='x', name='X', color='#fff')
        self.assertFalse(ch.spec(['Hm.'], 'deadpan')['pace']['caps'])
        self.assertFalse(ch.spec(['Hm.'], None, beat=True)['pace']['caps'])
        self.assertTrue(ch.spec(['Hm.'], None)['pace']['caps'])
        self.assertIsNone(ch.spec(['Hm.'], None, pace=0)['pace'])

    def test_a_slow_line_is_stretched_and_its_words_scaled(self):
        # 6 words at 2 a second, no pauses to cap
        words = [{'word': f'w{i}', 'start': round(0.06 + 0.5 * i, 3), 'end': round(0.06 + 0.5 * i + 0.45, 3)} for i in range(6)]
        wav = self.line(words, 3.2)
        out = self.dir / 'p.wav'
        w, seconds, info = pace.pace_file(wav, words, pace.options({'wps': 3.2}), out)
        self.assertEqual(info['stretch'], pace.MAX_STRETCH)
        self.assertAlmostEqual(info['wps'], info['wps_raw'] * pace.MAX_STRETCH, delta=0.05)
        on, length = self.onsets(out)
        self.assertEqual(len(on), 6)
        for o, x in zip(on, w):
            self.assertAlmostEqual(o, x['start'], delta=0.025)   # atempo smears onsets by about 15 ms
        self.assertAlmostEqual(length, seconds, delta=0.002)
        # a fast line, a short line and a slow style are left at their pace
        fast = [{'word': f'w{i}', 'start': 0.3 * i, 'end': 0.3 * i + 0.25} for i in range(6)]
        self.assertEqual(pace.stretch_factor(fast, pace.options({'wps': 3.2})), 1.0)
        self.assertEqual(pace.stretch_factor(words[:2], pace.options({'wps': 3.2})), 1.0)
        ch = castmod.Character(id='x', name='X', color='#fff')
        self.assertFalse(ch.spec(['Hm.'], 'sleepy')['pace']['stretch'])

    def test_quiet_audio_only_is_cut(self):
        # the aligner put "Hey." ending at 0.4, but the tone (its decay) runs to 0.7: the tail keeps it
        words = [{'word': 'Hey', 'start': 0.1, 'end': 0.4}, {'word': 'you.', 'start': 0.45, 'end': 0.6}]
        wav = self.dir / 'raw.wav'
        tone_wav(wav, [(0.1, 0.7)], 1.5)
        w, seconds, _ = pace.pace_file(wav, words, pace.options({'wps': 0, 'stretch': False}), self.dir / 'p.wav')
        self.assertGreaterEqual(seconds, 0.7 - 0.04 + 0.03 - 0.01)
        self.assertLess(seconds, 0.9)

    def test_estimated_timings_are_paced_too(self):
        tokens = 'So today, I challenge Duke to a jump-off!'.split()
        raw = front.estimate(tokens)
        words, info = pace.pace_words(raw, None, pace.options({'wps': 3.2}))
        self.assertAlmostEqual(words[0]['start'], pace.HEAD / info['stretch'], delta=0.002)
        self.assertGreaterEqual(info['wps'], 3.2 * pace.TRIGGER - 0.01)

    def test_the_resolver_paces_and_records_the_rate(self):
        tmp = Path(self.tmp.name) / 'cache'
        cast = {'character': [{'id': 'nibs', 'voice': 'ryan'}]}
        raw = {'name': 't', 'cast': cast, 'shot': [shot('a', [{'do': 'say', 'actor': 'nibs', 'text': 'one two three four five six'}], None)]}
        out = resolve.resolve(raw, 'test', engine=FakeEngine(step=0.5, length=0.45), log=lambda s: None, cache=tmp)
        d = out['edit']['dialogue'][0]
        self.assertEqual(d['pace']['stretch'], pace.MAX_STRETCH)
        self.assertGreater(d['wps'], 2.3)
        self.assertIn('.p', d['file'])   # the paced copy beside the raw line
        self.assertIn(pace.PACE, [d['pace']['target']])


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
