"""Sounds by meaning (cli/videocraft/audio/catalog, library, resolve): the committed Minecraft catalog and music map
parse and hold together, tags and palettes resolve to real events, music is picked by mood, the original library is
deterministic, and an original-only mix swaps every tagged Minecraft sound for its library stand-in without reading a
single game asset."""
import json
import re
import shutil
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'cli'))
from videocraft import script, tools  # noqa: E402
from videocraft.audio import assets, catalog, dsp, library, mix, resolve, synth  # noqa: E402
from videocraft.audio.catalog import rules, tomlw  # noqa: E402

sys.path.insert(0, str(ROOT / 'cli' / 'tests'))
from test_audio import fake_iteration  # noqa: E402


def shot(cues, duration=4.0):
    return {'name': 't', 'seed': 5, 'shot': [{'name': 'a', 'duration': duration, 'camera': {'rig': 'fixed'}, 'cue': cues}]}


class CatalogTests(unittest.TestCase):
    def test_the_catalog_parses_and_every_event_is_well_formed(self):
        events = catalog.events()
        self.assertGreater(len(events), 1500)
        lib = set(library.names())
        for name, row in events.items():
            self.assertRegex(name, r'^[a-z0-9_.]+$', name)
            self.assertIn(row['category'], {'hostile', 'neutral', 'player', 'block', 'ambient', 'music', 'record', 'master', 'weather'}, name)
            self.assertIsInstance(row['tags'], list, name)
            self.assertEqual(row['tags'], sorted(set(row['tags'])), name)
            if 'original' in row:
                self.assertIn(row['original'], lib, name)
        # Footsteps per surface, mob voices per mood, the comedy words.
        for query, expected in (('footstep wood', 'block.wood.step'), ('footstep-stone', 'block.stone.step'), ('goat hurt', 'entity.goat.hurt'),
                                ('pop', 'entity.item.pickup'), ('plop', 'entity.chicken.egg'), ('ding', 'entity.experience_orb.pickup'),
                                ('boing', 'entity.slime.jump'), ('scream', 'entity.goat.screaming.ambient'), ('villager', 'entity.villager.ambient'),
                                ('crowd', 'entity.villager.celebrate'), ('levelup', 'entity.player.levelup'), ('click', 'ui.button.click')):
            self.assertEqual(catalog.candidates(query)[0], expected, query)
        self.assertEqual(catalog.original_of('minecraft:block.wood.step'), 'footstep-wood')
        self.assertEqual(catalog.original_of('entity.chicken.ambient'), 'cluck')

    def test_the_palette_names_real_events_and_library_sounds(self):
        events, lib = catalog.events(), set(library.names())
        pal = catalog.palette()
        for name in ('boing', 'pop', 'plop', 'ding', 'fail', 'drumroll', 'record-scratch', 'dramatic-sting', 'crowd', 'applause'):
            self.assertIn(name, pal)
        for name, p in pal.items():
            self.assertIn(p['original'], lib, name)
            steps = list(p.get('pick', [])) + list(p.get('sequence', []))
            if 'roll' in p:
                steps += [{'id': p['roll']['id']}] + list(p['roll'].get('end', []))
            for s in steps:
                self.assertIn(s['id'], events, f'palette.{name}')
                pitch = s.get('pitch', 1.0)
                for v in (pitch if isinstance(pitch, list) else [pitch]):
                    self.assertTrue(0.5 <= v <= 2.0, f'palette.{name}: pitch {v}')

    def test_the_music_map_has_measured_tracks_with_moods(self):
        tracks = catalog.tracks()
        self.assertGreater(len(tracks), 60)
        for f, row in tracks.items():
            self.assertTrue(f.startswith(('music/', 'records/')), f)
            self.assertTrue(set(row['mood']) <= set(synth.MOODS), f)
            self.assertGreater(row['seconds'], 20, f)
            self.assertTrue(0 <= row['entry'] < row['seconds'], f)
            self.assertTrue(60 <= row['bpm'] <= 185, f)
            for a, b, score in row['loops']:
                self.assertTrue(0 <= a < b <= row['seconds'], f)
        self.assertIn('music_disc.cat', tracks['records/cat']['events'])
        for mood in synth.MOODS:
            self.assertTrue(any(mood in r['mood'] for r in tracks.values()), mood)

    def test_rules_tag_by_family_material_and_meaning(self):
        self.assertEqual(rules.category_of('entity.zombie.ambient'), 'hostile')
        self.assertEqual(rules.category_of('entity.goat.ambient'), 'neutral')
        t = rules.tags_for('block.cherry_wood.step')
        self.assertTrue({'footstep', 'footstep-wood', 'wood'} <= set(t), t)
        t = rules.tags_for('entity.goat.screaming.hurt')
        self.assertTrue({'goat', 'scream', 'hurt', 'voice'} <= set(t), t)
        self.assertIn('woof', rules.tags_for('entity.wolf_angry.ambient'))

    def test_the_toml_writer_round_trips(self):
        rows = {'a.b': {'n': 3, 'x': 0.25, 'tags': ['p', 'q'], 'ok': True, 's': 'say "hi"'}}
        text = tomlw.inline_rows('events', rows) + tomlw.table('palette.x-y', {'pick': [{'id': 'a.b', 'pitch': [0.9, 1.1]}]})
        data = tomllib.loads(text)
        self.assertEqual(data['events'], rows)
        self.assertEqual(data['palette']['x-y']['pick'][0]['pitch'], [0.9, 1.1])


class ResolveTests(unittest.TestCase):
    def compile(self, cues):
        plan, _ = script.compile_script(shot(cues))
        return plan['shots'][0]['timeline']

    def test_tags_palettes_and_library_compile_to_event_ids(self):
        cues = self.compile([{'at': 0.5, 'do': 'sound', 'tag': 'pop', 'relative': True},
                             {'at': 0.2, 'do': 'sound', 'palette': 'boing', 'relative': True},
                             {'at': 0.3, 'do': 'sound', 'library': 'slide-whistle-up', 'relative': True},
                             {'at': 0.4, 'do': 'sound', 'tag': 'pop', 'source': 'original', 'relative': True},
                             {'at': 0.6, 'do': 'sound', 'palette': 'crickets', 'relative': True},
                             {'at': 0.7, 'do': 'sound', 'id': 'minecraft:entity.goat.ambient'}])
        by_at = {c['at']: c for c in cues}
        self.assertEqual(by_at[0.5]['id'], 'minecraft:entity.item.pickup')
        self.assertEqual(by_at[0.5]['original'], 'pop')
        self.assertEqual(by_at[0.2]['id'], 'minecraft:entity.slime.jump')
        self.assertTrue(1.05 <= by_at[0.2]['pitch'] <= 1.25)
        self.assertEqual(by_at[0.3]['id'], 'videocraft:lib/slide-whistle-up')
        self.assertEqual(by_at[0.4]['id'], 'videocraft:lib/pop')
        self.assertEqual(by_at[0.6]['id'], 'videocraft:lib/crickets')
        self.assertNotIn('original', by_at[0.7])  # a plain id is left alone
        # Deterministic: the same script compiles to the same cues.
        self.assertEqual(cues, self.compile([{'at': 0.5, 'do': 'sound', 'tag': 'pop', 'relative': True},
                                             {'at': 0.2, 'do': 'sound', 'palette': 'boing', 'relative': True},
                                             {'at': 0.3, 'do': 'sound', 'library': 'slide-whistle-up', 'relative': True},
                                             {'at': 0.4, 'do': 'sound', 'tag': 'pop', 'source': 'original', 'relative': True},
                                             {'at': 0.6, 'do': 'sound', 'palette': 'crickets', 'relative': True},
                                             {'at': 0.7, 'do': 'sound', 'id': 'minecraft:entity.goat.ambient'}]))

    def test_a_roll_expands_into_parts_that_swell_and_stop_at_the_shot_end(self):
        cues = self.compile([{'at': 1.0, 'do': 'sound', 'palette': 'drumroll', 'relative': True}])
        self.assertGreater(len(cues), 30)
        self.assertEqual([c.get('part', 0) for c in cues[:3]], [0, 1, 2])
        self.assertTrue(all(c['original'] == 'snare-roll' for c in cues))
        snares = [c for c in cues if c['id'] == 'minecraft:block.note_block.snare']
        self.assertLess(snares[0]['volume'], snares[-2]['volume'])
        short = self.compile([{'at': 3.5, 'do': 'sound', 'palette': 'drumroll', 'relative': True}])
        self.assertTrue(all(c['at'] <= 4.0 for c in short))

    def test_bad_names_fail_the_compile_naming_the_cue(self):
        for cue, words in (({'do': 'sound', 'tag': 'nonexistent-thing'}, 'neither'), ({'do': 'sound', 'palette': 'bogus'}, 'known:'),
                           ({'do': 'sound', 'library': 'bogus'}, 'no original sound'), ({'do': 'sound', 'tag': 'pop', 'source': 'x'}, 'one of'),
                           ({'do': 'sound', 'palette': 'crickets', 'source': 'minecraft'}, 'original only')):
            with self.assertRaises(script.ScriptError) as e:
                self.compile([{'at': 0.1, **cue}])
            self.assertIn('shot a.cue[0]', str(e.exception))
            self.assertIn(words, str(e.exception))

    def test_music_is_picked_by_mood_deterministically(self):
        for mood in synth.MOODS:
            picked = resolve.pick_track(mood, seconds=40, seed=3)
            self.assertIsNotNone(picked, mood)
            f, row, why = picked
            self.assertIn(mood, row['mood'])
            self.assertNotEqual(row.get('bed'), False)
            self.assertFalse(row.get('vocals'))
            self.assertEqual(picked, resolve.pick_track(mood, seconds=40, seed=3))
        # A bpm wish moves the pick toward tracks near it; seeds spread the picks of one mood.
        picks = {resolve.pick_track('playful', seconds=40, seed=s)[0] for s in range(12)}
        self.assertGreater(len(picks), 1)
        fast = resolve.pick_track('upbeat', bpm=110, seed=1)[1]['bpm']
        self.assertLess(min(abs(fast - 110), abs(fast * 2 - 110), abs(fast / 2 - 110)), 20)
        self.assertEqual(synth.style_for('playful'), ('comedy-chase', None))
        self.assertEqual(synth.style_for('sad'), ('lullaby', 'a minor'))


class LibraryTests(unittest.TestCase):
    def test_at_least_forty_sounds_cover_the_comedy_tags_and_are_deterministic(self):
        names = library.names()
        self.assertGreaterEqual(len(names), 40)
        from videocraft.audio.library import recipes
        self.assertEqual(set(names), set(recipes.RECIPES))
        for tag in ('boing', 'pop', 'plop', 'ding', 'whoosh', 'swish', 'thud', 'splat', 'click', 'footstep-wood', 'footstep-stone',
                    'footstep-grass', 'footstep-sand', 'squeak', 'buzz', 'sting', 'drum', 'drumroll', 'cymbal', 'crowd', 'applause',
                    'record-scratch', 'slide-whistle', 'fall', 'honk', 'bubble', 'sparkle', 'alarm', 'typewriter', 'cash', 'error', 'success'):
            self.assertTrue(library.find([tag]), tag)
        with tempfile.TemporaryDirectory() as d, mock.patch.object(library, 'CACHE', Path(d)), mock.patch.object(library, '_memory', {}):
            a = library.render('boing', seed=2)
            library._memory.clear()
            b = library.render('boing', seed=2)  # from the disk cache
            library._memory.clear()
            c = library.render('boing', seed=3)
        self.assertEqual(a.tobytes(), b.tobytes())
        self.assertNotEqual(a.tobytes(), c.tobytes())
        self.assertLessEqual(dsp.peak(a), library.PEAK + 1e-6)
        self.assertGreater(dsp.rms(a), 0.03)


class OriginalSwapTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_an_original_mix_swaps_tagged_sounds_and_reads_no_game_asset(self):
        if not tools.ffmpeg():
            self.skipTest('ffmpeg not installed')
        plan, _ = script.compile_script(shot([{'at': 0.5, 'do': 'sound', 'tag': 'pop', 'relative': True},
                                              {'at': 1.0, 'do': 'sound', 'palette': 'rimshot', 'relative': True}], duration=2.5))
        tl_cues = plan['shots'][0]['timeline']
        rows = []
        for c in tl_cues:  # what the take would log: each cue on the first frame at or after its time
            frame = int(-(-c['at'] * 60 // 1))
            rows.append(f'{frame},{c["id"]},x/y,master,1,{c.get("pitch", 1)},0,0,0,1,16,0')
        rows.append('100,minecraft:block.wood.step,step/wood1,block,0.15,1,0,0,1,0,16,0')
        edit = {'audio': 'original', 'clip': [{'shot': 'a'}], 'music': {'mood': 'playful'},
                'sfx': [{'shot': 'a', 'at': 2.0, 'palette': 'ding'}, {'time': 0.1, 'tag': 'whoosh'}]}
        it = fake_iteration(self.dir, {'a': 150}, edit, {'a': rows})
        (it.path / 'plan.json').write_text(json.dumps({**plan, 'shots': [{**plan['shots'][0], 'name': 'a'}]}))

        def forbidden(*args, **kwargs):
            raise AssertionError('original-only audio read a game asset')

        with mock.patch.object(assets, 'decode', forbidden), mock.patch.object(assets, 'object_path', forbidden), \
                mock.patch.object(assets, 'index_file', forbidden), mock.patch.object(assets, 'available', forbidden):
            out = mix.build(it)
        report = json.loads((it.cut / 'audio.json').read_text())
        self.assertEqual(out.name, 'audio.wav')
        self.assertFalse(report['game_assets_used'])
        stand_ins = [e['stand_in'] for e in report['events']]
        # The tagged pop -> the library pop; the rimshot's four note-block steps -> one library rimshot; the step -> wood.
        self.assertEqual(sorted(stand_ins), sorted(['pop', 'rimshot', 'footstep-wood']))
        self.assertEqual(sum('palette sequence' in s['reason'] for s in report['skipped']), 3)
        self.assertEqual({e['stand_in'] for e in report['edit_sfx']}, {'ding', 'whoosh'})
        self.assertEqual(report['music']['source'], 'synth')
        self.assertEqual(report['music']['style'], 'comedy-chase')
        self.assertLess(abs(report['loudness']['integrated'] + 14), 1.0)

    def test_tag_patterns_duck_and_lift(self):
        self.assertTrue(mix.matches('entity.goat.screaming.hurt', 'minecraft:entity.goat.screaming.hurt', 'tag:scream'))
        self.assertTrue(mix.matches('block.wood.step', 'minecraft:block.wood.step', 'tag:footstep wood'))
        self.assertFalse(mix.matches('block.wood.step', 'minecraft:block.wood.step', 'tag:footstep stone'))
        self.assertTrue(mix.matches('block.wood.step', 'minecraft:block.wood.step', '*.step'))


class ModContractTests(unittest.TestCase):
    def test_the_mod_accepts_library_events(self):
        java = (ROOT / 'src/main/java/io/github/alexandroslekkas/videocraft/sound/Synth.java').read_text()
        self.assertTrue(re.search(r'LIBRARY = "lib/"', java))


if __name__ == '__main__':
    unittest.main()
