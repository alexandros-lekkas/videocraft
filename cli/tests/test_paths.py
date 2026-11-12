"""Where Loom's game assets are read from: GRADLE_USER_HOME when set, else ~/.gradle (paths.loom_assets)."""
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'cli'))
from videocraft import paths  # noqa: E402


class LoomAssetsTest(unittest.TestCase):
    def test_default_is_home_gradle(self):
        self.assertEqual(paths.loom_assets({}), Path.home() / '.gradle/caches/fabric-loom/assets')

    def test_gradle_user_home(self):
        self.assertEqual(paths.loom_assets({'GRADLE_USER_HOME': '/srv/gradle'}), Path('/srv/gradle/caches/fabric-loom/assets'))
        self.assertEqual(paths.gradle_home({'GRADLE_USER_HOME': ''}), Path.home() / '.gradle')

    def test_audio_assets_follow_it(self):
        # audio.assets reads the environment at import, so check it in a fresh interpreter.
        env = dict(os.environ, GRADLE_USER_HOME='/srv/gradle', PYTHONPATH=str(ROOT / 'cli'))
        env.pop('VIDEOCRAFT_ASSETS', None)
        out = subprocess.run([sys.executable, '-c', 'from videocraft.audio import assets; print(assets.ASSETS)'],
                             env=env, capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(out, '/srv/gradle/caches/fabric-loom/assets')

    def test_no_hard_coded_gradle_home_left(self):
        for path in (ROOT / 'cli' / 'videocraft').rglob('*.py'):
            if path.name != 'paths.py':
                self.assertNotIn("'.gradle", path.read_text(), path)


if __name__ == '__main__':
    unittest.main()
