"""A budget per floor, as the page shows it (src/budget.js): what a floor spent today against its budget,
in words.

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

SCRIPT = """
import { pathToFileURL } from 'node:url';
const b = await import(pathToFileURL(process.argv[1] + '/src/budget.js').href);
const [org, talks] = JSON.parse(process.argv[2]);
const out = {
  said: [900, 12400, 2000000, 1250000].map(b.tokensSaid),
  day: b.localDay(new Date(2026, 10, 2, 23, 59)),
  floors: org.floors.map((f) => b.floorSpend(org, f, talks, f.id === 'kite' ? 2 : 1, '2026-11-12')),
  ended: b.spentToday(talks, 'Kite', '2026-11-12', [
    { day: '2026-11-12', talks: { 'cc-a': { project: 'Kite', tokens: 600 }, 'cc-b': { project: 'Shop', tokens: 5 } } },
    { day: '2026-11-11', talks: { 'cc-c': { project: 'Kite', tokens: 99999 } } }, { day: '2026-11-12' }, null]),
};
console.log(JSON.stringify(out));
"""

ORG = {"budget": 1000, "floors": [{"id": "shop", "project": "Shop"}, {"id": "lab", "project": "Lab", "budget": 5000},
                                  {"id": "kite", "project": "Kite"}, {"id": "quiet", "project": "Quiet", "budget": -3}]}
TALKS = [
    {"project": "Shop", "spent": {"day": "2026-11-12", "tokens": 700}},
    {"project": "Shop", "spent": {"day": "2026-11-12", "tokens": 400}},
    {"project": "Shop", "spent": {"day": "2026-11-11", "tokens": 99999}},  # yesterday's
    {"project": "Lab", "spent": {"tokens": 2500}},  # no day: the sample's, today
    {"project": "Kite", "spent": {"day": "2026-11-12", "tokens": 1500}},
    {"project": "Kite", "spent": "lots"},
]


@unittest.skipUnless(NODE, "Node.js isn't installed")
class BudgetWordsTest(unittest.TestCase):
    def test_what_each_floor_spent(self):
        run = subprocess.run([NODE, "--input-type=module", "-e", SCRIPT, ROOT, json.dumps([ORG, TALKS])], capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)
        got = json.loads(run.stdout)
        self.assertEqual(got["said"], ["900", "12 thousand", "2 million", "1.3 million"])
        self.assertEqual(got["day"], "2026-11-02")
        shop, lab, kite, quiet = got["floors"]
        self.assertEqual((shop["spent"], shop["limit"], shop["over"], shop["text"]), (1100, 1000, True, "1 thousand of 1 thousand tokens today, over budget"))
        self.assertEqual((lab["spent"], lab["limit"], lab["over"], lab["share"]), (2500, 5000, False, 0.5))
        self.assertEqual((kite["limit"], kite["over"]), (2000, False))  # let go on once: as much again
        self.assertEqual((quiet["limit"], quiet["over"], quiet["text"]), (1000, False, "0 of 1 thousand tokens today"))
        self.assertEqual(got["ended"], 2100)  # the conversations that left today still count; yesterday's don't


if __name__ == "__main__":
    unittest.main()
