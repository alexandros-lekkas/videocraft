"""The three machine-wide take slots (game.acquire_slot). Uses a temporary lock folder and never touches a real port."""
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'cli'))
from videocraft import game  # noqa: E402

PORTS = (25750, 25751, 25752)


def always_free(port):
    return True


class SlotTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.held = []
        self.addCleanup(lambda: [slot.release() for slot in self.held])

    def acquire(self, **kwargs):
        kwargs.setdefault('is_free', always_free)
        slot = game.acquire_slot(lock_dir=self.dir.name, ports=PORTS, say=lambda line: None, **kwargs)
        self.held.append(slot)
        return slot

    def test_two_takes_get_different_slots_and_ports(self):
        a, b = self.acquire(wait=0), self.acquire(wait=0)
        self.assertNotEqual(a.index, b.index)
        self.assertEqual((a.port, b.port), (PORTS[a.index], PORTS[b.index]))

    def test_the_fourth_take_waits_then_fails(self):
        for _ in range(3):
            self.acquire(wait=0)
        said = []
        started = time.monotonic()
        with self.assertRaisesRegex(SystemExit, 'busy after 0.3 s'):
            game.acquire_slot(lock_dir=self.dir.name, ports=PORTS, is_free=always_free, wait=0.3, poll=0.05, say=said.append)
        self.assertGreaterEqual(time.monotonic() - started, 0.3)
        self.assertEqual(len(said), 1, 'says once that it is waiting')
        self.assertIn('waiting up to 0.3 s', said[0])

    def test_a_released_slot_is_free_again(self):
        slots = [self.acquire(wait=0) for _ in range(3)]
        slots[1].release()
        self.assertEqual(self.acquire(wait=0).index, slots[1].index)

    def test_a_port_something_else_listens_on_is_skipped(self):
        slot = self.acquire(wait=0, is_free=lambda port: port != PORTS[0])
        self.assertEqual(slot.index, 1)

    def test_the_holder_is_recorded(self):
        slot = self.acquire(wait=0)
        self.assertIn(str(ROOT), game.slot_holder(slot.index, lock_dir=self.dir.name))
        slot.release()
        self.assertEqual(game.slot_holder(slot.index, lock_dir=self.dir.name), '')

    def test_ports_of_other_tools_are_refused(self):
        for port in (25590, 25611, 25680, 25685, 25690, 25720):
            with self.assertRaisesRegex(SystemExit, 'another tool'):
                game.check_port(port)
        self.assertEqual(game.check_port(25751), 25751)


class PidFileTests(unittest.TestCase):
    def test_the_pid_file_records_the_port(self):
        with tempfile.TemporaryDirectory() as d:
            pid_file = Path(d) / 'videocraft.pid'
            with mock.patch.object(game, 'PID_FILE', pid_file):
                pid_file.write_text(json.dumps({'pid': game.os.getpid(), 'port': 25752}))
                self.assertEqual(game.running(), (game.os.getpid(), 25752))
                pid_file.write_text(str(game.os.getpid()))  # an older CLI's bare pid
                self.assertEqual(game.running(), (game.os.getpid(), 25750))


if __name__ == '__main__':
    unittest.main()
