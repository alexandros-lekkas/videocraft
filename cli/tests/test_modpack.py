"""The .mrpack layout from modpack/pack.toml, with Modrinth's API stubbed."""
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from videocraft import modpack  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def fake_fetch(url):
    slug = url.split('/project/')[1].split('/')[0]
    return [{'version_number': 'old', 'files': []},
            {'version_number': VERSIONS[slug], 'files': [
                {'primary': True, 'filename': f'{slug}.jar', 'size': 1234, 'url': f'https://cdn.modrinth.com/data/x/{slug}.jar',
                 'hashes': {'sha1': 'a' * 40, 'sha512': 'b' * 128}}]}]


VERSIONS = {}


class Modpack(unittest.TestCase):
    def test_mrpack(self):
        import tomllib
        pack = tomllib.loads((ROOT / 'modpack/pack.toml').read_text())
        VERSIONS.update({m['slug']: m['version'] for m in pack['mod']})
        with tempfile.TemporaryDirectory() as d:
            jar = Path(d) / 'videocraft-0.1.0.jar'
            jar.write_bytes(b'PK fake jar')
            target, data = modpack.build(jar=jar, out_dir=d, fetch=fake_fetch)
            with zipfile.ZipFile(target) as z:
                names = z.namelist()
                index = json.loads(z.read('modrinth.index.json'))
        self.assertEqual(sorted(names), ['modrinth.index.json', 'overrides/mods/videocraft-0.1.0.jar'])
        self.assertEqual(index['formatVersion'], 1)
        self.assertEqual(index['game'], 'minecraft')
        self.assertEqual(index['dependencies'], {'minecraft': pack['pack']['minecraft'], 'fabric-loader': pack['pack']['fabric_loader']})
        self.assertEqual(len(index['files']), len(pack['mod']))
        f = index['files'][0]
        self.assertEqual(sorted(f), ['downloads', 'env', 'fileSize', 'hashes', 'path'])
        self.assertTrue(f['path'].startswith('mods/'))

    def test_a_missing_version_is_named(self):
        with self.assertRaises(modpack.PackError) as e:
            modpack.resolve('lithium', 'nope', '26.3', fetch=lambda url: [{'version_number': 'mc26.3-0.26.3-fabric', 'files': []}])
        self.assertIn('lithium nope', str(e.exception))
