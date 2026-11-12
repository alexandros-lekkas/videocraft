"""Optional command groups (cli.load_groups): videocraft.<name>.commands with register(subparsers)."""
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'cli'))
import videocraft  # noqa: E402
from videocraft import cli  # noqa: E402

GROUPS = {
    'testhello': "def register(sub):\n    sub.add_parser('hello').set_defaults(run=lambda args: 7)\n",
    # Implements a placeholder's command: replaces the not-yet placeholder instead of clashing with it.
    'testlint': "def register(sub):\n    sub.add_parser('lint').set_defaults(run=lambda args: 8)\n",
    'testbroken': "import videocraft_no_such_dependency\n",
}


class GroupTests(unittest.TestCase):
    def test_groups_register_missing_ones_are_skipped_broken_ones_reported(self):
        with tempfile.TemporaryDirectory() as extra:
            for name, source in GROUPS.items():
                (Path(extra) / name).mkdir()
                (Path(extra) / name / '__init__.py').write_text('')
                (Path(extra) / name / 'commands.py').write_text(source)
            stderr = io.StringIO()
            # The temporary folder is a second home for videocraft's subpackages, as cli/videocraft/<name>/ would be.
            with mock.patch.object(videocraft, '__path__', [*videocraft.__path__, extra]), \
                    mock.patch.object(cli, 'GROUPS', (*GROUPS, 'testmissing')), redirect_stderr(stderr):
                parser = cli.build_parser()
            for name in GROUPS:
                sys.modules.pop(f'videocraft.{name}.commands', None)
                sys.modules.pop(f'videocraft.{name}', None)
        args = parser.parse_args(['hello'])
        self.assertEqual(args.run(args), 7)
        args = parser.parse_args(['lint'])
        self.assertEqual(args.run(args), 8)
        self.assertNotIn('testmissing', stderr.getvalue(), 'a missing group is silent')
        self.assertIn('command group testbroken failed to load', stderr.getvalue())
        self.assertIn('videocraft_no_such_dependency', stderr.getvalue())

    def test_the_groups_in_the_checkout_load_cleanly(self):
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            cli.build_parser()
        self.assertEqual(stderr.getvalue(), '')


if __name__ == '__main__':
    unittest.main()
