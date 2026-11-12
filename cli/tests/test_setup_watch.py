"""The first-run progress lines while Gradle and Loom set up (game.SetupWatch), on a fake clock."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from videocraft.game import SetupWatch


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class SetupWatchTest(unittest.TestCase):
    def setUp(self):
        self.clock, self.said = Clock(), []
        self.watch = SetupWatch(say=self.said.append, clock=self.clock)

    def run_to(self, seconds):
        while self.clock.t < seconds:
            self.clock.t += 0.5
            self.watch.tick()

    def test_quiet_then_every_thirty_seconds(self):
        self.run_to(14.5)
        self.assertEqual(self.said, [])
        self.run_to(15)
        self.assertEqual(len(self.said), 1)
        self.assertIn('still setting up Gradle and Minecraft (first run downloads ~1 GB), 0m 15s', self.said[0])
        self.run_to(150)
        self.assertEqual(len(self.said), 5)  # 15, 45, 75, 105, 135
        self.assertTrue(self.said[-1].endswith('2m 15s'))

    def test_output_resets_the_quiet_timer(self):
        self.run_to(10)
        self.watch.line('> Task :compileJava\n')
        self.run_to(24.5)
        self.assertEqual(self.said, [])
        self.run_to(25)
        self.assertEqual(len(self.said), 1)

    def test_download_lines_pass_through_before_the_game(self):
        self.watch.line('Downloading https://example.invalid/client.jar\n')
        self.watch.line('> Task :compileJava\n')
        self.assertEqual(self.said, ['  Downloading https://example.invalid/client.jar'])

    def test_silent_once_the_game_logs(self):
        self.watch.line('[23:51:24] [main/INFO] (FabricLoader/GameProvider) Loading Minecraft 26.3 with Fabric Loader 0.19.5\n')
        self.watch.line('[23:51:52] [Server thread/INFO] (Minecraft) Preparing spawn area: 16%\n')
        self.run_to(300)
        self.assertEqual(self.said, [])


if __name__ == '__main__':
    unittest.main()
