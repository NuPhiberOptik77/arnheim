"""The review line, as the page shows it (src/review.js): in review, passed, sent back, failed or not
reviewed; and in the list of what waits on you (src/queue.js), where only work that came through the line
is listed, marked with how it did.

The rules are JavaScript, so this runs them under Node.js, and is skipped where Node isn't installed.
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
const at = (name) => import(pathToFileURL(process.argv[1] + '/src/' + name).href);
const { reviewOf, reviewMood } = await at('review.js');
const { waitingOnYou, sayWaiting } = await at('queue.js');
const given = JSON.parse(process.argv[2]);
const words = given.cases.map(([c, now]) => { const r = reviewOf(c, now); return r && { ...r, mood: reviewMood(r) }; });
const items = waitingOnYou({ conversations: given.talks, now: given.now });
console.log(JSON.stringify({ words, waiting: items.map((i) => [i.key, i.review?.word || null]), said: sayWaiting(items) }));
"""

CASES = [
    ({}, None),
    ({"review": {"state": "reviewing", "at": NOW - 30, "until": NOW + 300}},
     ("reviewing", "In review", "The review line is checking its work before it reaches you.", None)),
    ({"review": {"state": "reviewing", "at": NOW - 900, "until": NOW - 300}},
     ("error", "Not reviewed", "The review line was cut short, so this work reached you unchecked.", None)),
    ({"review": {"state": "passed", "by": "The reader", "said": "It does what was asked", "times": 0}},
     ("passed", "Passed review", "It passed the review line. It does what was asked.", "ok")),
    ({"review": {"state": "passed", "by": "The tests", "times": 1}},
     ("passed", "Passed review", "It passed the review line, after it was sent back once. The tests passed.", "ok")),
    ({"review": {"state": "sent back", "why": "The tests failed.\nA second line", "times": 1}},
     ("sent back", "Sent back", "The review line sent it back, so it is fixing it: The tests failed.", None)),
    ({"review": {"state": "sent back", "why": "Still red.", "times": 2}},
     ("sent back", "Sent back", "The review line sent it back a second time, so it is fixing it: Still red.", None)),
    ({"review": {"state": "failed", "why": "Still red", "times": 2}},
     ("failed", "Failed review", "It still failed the review line after being sent back twice, so it reached you anyway: Still red.", "failed")),
    ({"review": {"state": "failed", "why": "Still red.", "times": 0}},
     ("failed", "Failed review", "It failed the review line, so it reached you anyway: Still red.", "failed")),
    ({"review": {"state": "error", "said": "The reader gave no verdict (I looked)."}},
     ("error", "Not reviewed", "The review line couldn't finish, so this work reached you unchecked. The reader gave no verdict (I looked).", None)),
]

TALKS = [
    {"id": "a", "project": "Lantern", "title": "The blue button", "check": True, "stopped": NOW - 60, "says": {"now": "I made it blue."},
     "review": {"state": "passed", "by": "The reader", "said": "It does what was asked."}},
    {"id": "b", "project": "Lantern", "title": "The settings page", "working": True, "review": {"state": "sent back", "why": "Still red.", "times": 1}},
    {"id": "c", "project": "Lantern", "title": "The menu", "working": True, "review": {"state": "reviewing", "until": NOW + 300}},
    {"id": "d", "project": "Studio", "title": "The pictures", "check": True, "stopped": NOW - 120, "says": {"now": "Done."},
     "review": {"state": "failed", "why": "One picture is the wrong size.", "times": 2}},
]


@unittest.skipUnless(NODE, "Node.js isn't installed")
class ReviewWordsTest(unittest.TestCase):
    def run_page(self):
        given = {"cases": [[c, NOW] for c, _ in CASES], "talks": TALKS, "now": NOW}
        done = subprocess.run([NODE, "--input-type=module", "-e", SCRIPT, ROOT, json.dumps(given)], capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def test_each_state_in_words(self):
        words = self.run_page()["words"]
        for (c, want), got in zip(CASES, words):
            with self.subTest(c=c):
                self.assertEqual(want, got and (got["state"], got["word"], got["line"], got["mood"]))

    def test_only_what_came_through_waits_on_you(self):
        out = self.run_page()
        self.assertEqual(out["waiting"], [["a", "Passed review"], ["d", "Failed review"]])  # not the one in review, nor the one sent back
        self.assertIn("The blue button on Lantern has finished and waits for your next step. It passed the review line. It does what was asked.", out["said"])
        self.assertIn("It still failed the review line after being sent back twice, so it reached you anyway: One picture is the wrong size.", out["said"])


if __name__ == "__main__":
    unittest.main()
