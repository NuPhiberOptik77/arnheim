"""Done means proven, as the page shows it (src/proof.js): proven, not proven, checking or claimed, from a
conversation's last change and its floor's check.

The rule is JavaScript, so this runs it under Node.js, and is skipped where Node isn't installed.
Run from the repository's folder: python3 -m unittest discover tests
"""
import json
import os
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")
NOW = 1_800_000_000

SCRIPT = """
import { pathToFileURL } from 'node:url';
const { proofOf, proofMood } = await import(pathToFileURL(process.argv[1] + '/src/proof.js').href);
const out = JSON.parse(process.argv[2]).map(([c, now]) => { const p = proofOf(c, now); return p && { ...p, mood: proofMood(p) }; });
console.log(JSON.stringify(out));
"""

TESTS = {"check": "The tests"}
CASES = [
    ("changed nothing", {}, None),
    ("changed, never checked", {"changed": NOW - 60}, ("claimed", "Claimed", "It changed files, and nothing has checked them yet.")),
    ("passed after its last change", {"changed": NOW - 60, "proof": {**TESTS, "state": "passed", "at": NOW - 30}},
     ("proven", "Proven", "The tests passed after its last change.")),
    ("changed again after it passed", {"changed": NOW - 10, "proof": {**TESTS, "state": "passed", "at": NOW - 30}},
     ("claimed", "Claimed", "It changed files after the tests last ran on them.")),
    ("running now", {"changed": NOW - 60, "proof": {**TESTS, "state": "checking", "at": NOW - 30, "until": NOW + 570}},
     ("checking", "Checking", "Running the tests on its work now.")),
    ("changed again while it ran", {"changed": NOW - 10, "proof": {**TESTS, "state": "checking", "at": NOW - 30, "until": NOW + 570}},
     ("claimed", "Claimed", "It changed files again while the tests ran, so they wait for the next run.")),
    ("a run that was cut short", {"changed": NOW - 4000, "proof": {**TESTS, "state": "checking", "at": NOW - 3000, "until": NOW - 2400}},
     ("claimed", "Claimed", "It changed files, and nothing has checked them yet.")),
    ("failed", {"changed": NOW - 60, "proof": {**TESTS, "state": "failed", "at": NOW - 30, "tail": "1 failed"}},
     ("failed", "Not proven", "The tests failed.")),
    ("ran too long", {"changed": NOW - 60, "proof": {"check": "CI", "state": "timeout", "at": NOW - 30}},
     ("failed", "Not proven", "CI ran too long and was stopped.")),
    ("couldn't start", {"changed": NOW - 60, "proof": {"state": "error", "at": NOW - 30, "tail": "It didn't start."}},
     ("failed", "Not proven", "Its check couldn't run.")),
    ("the sample's, with no times", {"proof": {"check": "The spending check", "state": "passed"}},
     ("proven", "Proven", "The spending check passed after its last change.")),
    ("a proof that isn't one", {"changed": NOW - 60, "proof": "passed"}, ("claimed", "Claimed", "It changed files, and nothing has checked them yet.")),
]
MOODS = {"proven": "ok", "failed": "failed", "claimed": None, "checking": None}


@unittest.skipUnless(NODE, "Node.js isn't installed")
class ProofTest(unittest.TestCase):
    def test_what_the_page_shows(self):
        run = subprocess.run([NODE, "--input-type=module", "-e", SCRIPT, ROOT, json.dumps([[c, NOW] for _, c, _ in CASES])],
                             capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)
        for (what, c, want), got in zip(CASES, json.loads(run.stdout)):
            with self.subTest(what):
                if want is None:
                    self.assertIsNone(got)
                    continue
                self.assertEqual((got["state"], got["word"], got["line"]), want)
                self.assertEqual(got["mood"], MOODS[want[0]])
                if want[0] == "failed" and c["proof"].get("tail"):
                    self.assertEqual(got["tail"], c["proof"]["tail"])


if __name__ == "__main__":
    unittest.main()
