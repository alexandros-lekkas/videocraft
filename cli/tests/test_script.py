"""python3 -m unittest discover -s cli/tests  (run from the repo root; no game needed)."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'cli'))
from videocraft import script  # noqa: E402


class ScriptTests(unittest.TestCase):
    def test_hello_compiles_to_the_checked_plan(self):
        plan, edit = script.compile_script(script.load(ROOT / 'examples/hello.toml'))
        self.assertEqual(plan['version'], script.PLAN_VERSION)
        self.assertEqual(plan['shots'][0]['camera']['rig'], 'orbit')
        self.assertEqual(edit['clip'], [{'shot': 'orbit'}])
        # The Java side parses the same shape (PlanChecks reads cli/tests/plans/*.plan.json).
        (ROOT / 'cli/tests/plans/hello.plan.json').write_text(json.dumps(plan, indent=2) + '\n')

    def test_errors_name_the_place_and_the_fix(self):
        with self.assertRaisesRegex(script.ScriptError, 'shot orbit: duration'):
            script.compile_script({'name': 'x', 'shot': [{'name': 'orbit', 'camera': {'rig': 'orbit'}}]})
        with self.assertRaisesRegex(script.ScriptError, 'unknown key'):
            script.compile_script({'name': 'x', 'shots': []})
        with self.assertRaisesRegex(script.ScriptError, 'outside the shot'):
            script.compile_script({'name': 'x', 'shot': [{'name': 'a', 'duration': 1, 'camera': {'rig': 'orbit'}, 'cue': [{'at': 2, 'do': 'mark'}]}]})


if __name__ == '__main__':
    unittest.main()
