"""Ask the building about its history (src/history.js): which days a question means, a file it names, and
the receptionist's answer from the week's moments. The rules are JavaScript, so this test runs under
Node.js, and is skipped where Node isn't installed.
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
const r = await import(pathToFileURL(process.argv[1] + '/src/history.js').href);
const now = new Date(2026, 10, 12, 18, 0); // a Thursday, at six in the evening
const at = (daysBack, hh, mm) => new Date(2026, 10, 12 - daysBack, hh, mm).getTime() / 1000;
const week = [
  { at: at(0, 9, 0), key: 'a', project: 'Shop', title: 'Fix the till', kind: 'working', what: '' },
  { at: at(0, 9, 30), key: 'a', project: 'Shop', title: 'Fix the till', kind: 'changed', what: 'till/total.py' },
  { at: at(0, 10, 0), key: 'a', project: 'Shop', title: 'Fix the till', kind: 'finished', what: 'Done.' },
  { at: at(1, 14, 0), key: 'b', project: 'Lab', title: 'New menu', kind: 'changed', what: 'menu/fonts.css' },
  { at: at(1, 14, 5), key: 'b', project: 'Lab', title: 'New menu', kind: 'changed', what: 'till/total.py' },
  { at: at(1, 15, 0), key: 'b', project: 'Lab', title: 'New menu', kind: 'stopped', what: 'Stopped.' },
  { at: at(2, 11, 0), key: 'c', project: 'Shop', title: 'Tidy', kind: 'asked', what: 'Which?' },
  { at: at(9, 11, 0), key: 'z', project: 'Shop', title: 'Long ago', kind: 'changed', what: 'till/total.py' },
];
const clock = (t) => { const d = new Date(t * 1000); return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`; };
const say = (q, project = null) => r.sayHistory(week, r.historyAsked(q, now, project), (p) => p.toUpperCase(), clock, now);
console.log(JSON.stringify({
  days: ['what happened today?', 'What happened yesterday?', 'what did they do on Tuesday?', 'What happened this week?', 'what did the agents do on thursday', 'history']
    .map((q) => { const a = r.historyAsked(q, now); return [a.label, a.days.length, a.days[0]]; }),
  files: ['who changed till/total.py?', 'when was notes.md last changed?', 'who touched the README.md.', 'what happened today?', 'who changed v1.2 today'].map(r.fileAsked),
  today: say('what happened today?'),
  yesterday: say('What happened yesterday?'),
  file: say('Who changed till/total.py?'),
  fileOnFloor: say('who changed total.py this week?', 'Shop'),
  none: say('what happened on Monday?'),
  noFile: say('who changed nothing.txt?'),
  week: say('what happened this week?'),
  asked: ['What happened yesterday?', 'what did the agents do on Tuesday?', 'who changed walk.js?', 'when did the till last change?', "what's happening?", 'what is the weather?']
    .map((q) => r.HISTORY_ASKED.test(q)),
}));
"""


@unittest.skipUnless(NODE, "Node.js isn't installed")
class HistoryWordsTest(unittest.TestCase):
    def test_history(self):
        done = subprocess.run([NODE, "--input-type=module", "-e", SCRIPT, ROOT], capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        out = json.loads(done.stdout)
        self.assertEqual(out["days"], [["today", 1, "2026-11-12"], ["yesterday", 1, "2026-11-11"], ["on Tuesday", 1, "2026-11-10"],
                                       ["this week", 7, "2026-11-12"], ["today", 1, "2026-11-12"], ["today", 1, "2026-11-12"]])
        self.assertEqual(out["files"], ["till/total.py", "notes.md", "README.md", None, None])
        self.assertEqual(out["today"], 'Today: On SHOP, 1 conversation worked: "Fix the till" changed 1 file and finished at 10:00.')
        self.assertEqual(out["yesterday"], 'Yesterday: On LAB, 1 conversation worked: "New menu" changed 2 files and stopped at 15:00.')
        self.assertEqual(out["file"], 'till/total.py was changed 2 times this week: last by "Fix the till" on SHOP at 09:30, '
                                      'before that by "New menu" on LAB yesterday at 14:05.')  # a week back at most
        self.assertEqual(out["fileOnFloor"], 'till/total.py was changed 1 time this week: last by "Fix the till" at 09:30.')
        self.assertEqual(out["none"], "Nothing happened on Monday, as far as the building knows. It keeps a week of history.")
        self.assertEqual(out["noFile"], "Nothing changed nothing.txt this week, as far as the building knows. It keeps a week of history.")
        self.assertTrue(out["week"].startswith('This week: On SHOP, 2 conversations worked: "Fix the till" changed 1 file and finished at 10:00; '
                                               '"Tidy" stopped to ask you something on Tuesday at 11:00. On LAB'), out["week"])
        self.assertEqual(out["asked"], [True, True, True, True, False, False])


if __name__ == "__main__":
    unittest.main()
