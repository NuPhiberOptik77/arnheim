"""A weekly report (src/weekly.js): the last seven days floor by floor, from the history files' moments and
what each floor's agents spent each day. The rules are JavaScript, so this test runs under Node.js, and
is skipped where Node isn't installed.
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
const r = await import(pathToFileURL(process.argv[1] + '/src/weekly.js').href);
const days = [
  { day: '2026-11-12', spent: { Shop: 1200000 }, moments: [
    { at: 100, key: 'a', project: 'Shop', title: 'Fix', kind: 'working' },
    { at: 200, key: 'a', project: 'Shop', title: 'Fix', kind: 'changed', what: 'till.py' },
    { at: 210, key: 'a', project: 'Shop', title: 'Fix', kind: 'changed', what: 'till.py' },
    { at: 300, key: 'a', project: 'Shop', title: 'Fix', kind: 'asked', what: 'May I?' },
    { at: 900, key: 'a', project: 'Shop', title: 'Fix', kind: 'answered', what: 'It went on.' },
    { at: 1000, key: 'a', project: 'Shop', title: 'Fix', kind: 'finished', what: 'Done.' },
  ] },
  { day: '2026-11-10', spent: { Lab: 3000, Shop: 'lots' }, moments: [
    { at: 50, key: 'b', project: 'Lab', title: 'Menu', kind: 'working' },
    { at: 60, key: 'b', project: 'Lab', title: 'Menu', kind: 'stopped', what: 'Stopped.' },
    { at: 70, project: 'Lab', kind: 'working' },
  ] },
  { day: '2026-11-11', moments: [] },
];
const report = r.weekReport(days, 2000);
const open = [{ day: '2026-11-12', moments: [{ at: 100, key: 'q', project: 'Lab', title: 'Asks', kind: 'asked', what: '?' }] }];
const dropped = r.weekReport(open, 500000);
const waiting = r.weekReport(open, 500, new Set(['q']));
const empty = r.weekReport([], 2000);
console.log(JSON.stringify({
  from: report.from, to: report.to, busiest: report.busiest,
  floors: report.floors.map((f) => [f.project, f.talks, f.asked, f.files, f.finished, f.stopped, f.waited, f.waits, f.spent]),
  total: [report.total.talks, report.total.files, report.total.spent],
  line: r.floorLine(report.floors[0]),
  said: r.sayWeek(report, (p) => p.toUpperCase()),
  none: r.sayWeek(empty),
  text: r.weekText(report, (p) => p.toUpperCase(), 'Example Studio'),
  dropped: [dropped.total.waits, dropped.total.waited], waiting: [waiting.total.waits, waiting.total.waited],
  asked: ['How was the week?', 'weekly report please', 'sum up the week', 'the week in review', 'what happened yesterday'].map((q) => r.WEEKLY_ASKED.test(q)),
}));
"""


@unittest.skipUnless(NODE, "Node.js isn't installed")
class WeeklyWordsTest(unittest.TestCase):
    def test_the_report(self):
        done = subprocess.run([NODE, "--input-type=module", "-e", SCRIPT, ROOT], capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        out = json.loads(done.stdout)
        self.assertEqual((out["from"], out["to"]), ("2026-11-10", "2026-11-12"))
        self.assertEqual(out["busiest"], {"day": "2026-11-12", "moments": 6})
        self.assertEqual(out["floors"], [["Shop", 1, 1, 1, 1, 0, 600, 1, 1200000], ["Lab", 1, 1, 0, 0, 1, 0, 0, 3000]])
        self.assertEqual(out["total"], [2, 1, 1203000])
        self.assertEqual(out["line"], "1 conversation, 1 instruction, 1 file changed, 1 finished. Waited on you 10 min. 1.2 million tokens.")
        self.assertEqual(out["said"], "This week, 2 conversations on 2 floors: 2 instructions, 1 file changed, 1 finished and 1 stopped. "
                                      "They waited on you 10 min in all. The busiest floor was SHOP. The busiest day was Thursday. 1.2 million tokens.")
        self.assertIn("Nothing happened this week", out["none"])
        self.assertTrue(out["text"].startswith("Example Studio: the week from Tuesday 2026-11-10 to Thursday 2026-11-12\n\nSHOP: 1 conversation"), out["text"])
        self.assertIn("\nLAB: 1 conversation, 1 instruction, 0 files changed, 0 finished, 1 stopped. 3 thousand tokens.\n", out["text"])
        self.assertIn("\n\nIn all: 2 conversations", out["text"])
        self.assertEqual(out["asked"], [True, True, True, True, False])
        self.assertEqual(out["dropped"], [0, 0])  # a wait that never ended, by one not waiting now: left out
        self.assertEqual(out["waiting"], [1, 400])  # one waiting now: counted up to now


if __name__ == "__main__":
    unittest.main()
