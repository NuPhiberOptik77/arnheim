"""Replay the day: the hook keeps each day's moments (connect/claude_code.py), and the page rebuilds the
building's conversations at any moment from them (src/replay.js).

The page's rules are JavaScript, so their test runs under Node.js, and is skipped where Node isn't
installed. The hook's test makes a company of its own in a temporary folder (ARNHEIM_DATA).
Run from the repository's folder: python3 -m unittest discover tests
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(ROOT, "connect", "claude_code.py")
NODE = shutil.which("node")
sys.path.insert(0, os.path.join(ROOT, "connect"))
import budget  # noqa: E402  (after the path is set)

DAY = [
    {"at": 100, "key": "a", "project": "Shop", "title": "Fix the till", "kind": "working", "what": 'You asked: "Fix the till"'},
    {"at": 200, "key": "a", "project": "Shop", "title": "Fix the till", "kind": "changed", "what": "till/total.py"},
    {"at": 250, "key": "b", "project": "Lab", "title": "New menu", "kind": "working", "what": ""},
    {"at": 300, "key": "a", "project": "Shop", "title": "Fix the till", "kind": "changed", "what": "till/receipt.py"},
    {"at": 310, "key": "a", "project": "Shop", "title": "Fix the till", "kind": "changed", "what": "till/total.py"},
    {"at": 400, "key": "b", "project": "Lab", "title": "New menu", "kind": "asked", "what": "Which font?"},
    {"at": 500, "key": "a", "project": "Shop", "title": "Fix the till", "kind": "finished", "what": "The till adds up now."},
    {"at": 600, "key": "b", "project": "Lab", "title": "New menu", "kind": "left", "what": "The conversation ended."},
    {"at": 50, "key": "", "kind": "working"},  # no conversation: left out
]

SCRIPT = """
import { pathToFileURL } from 'node:url';
const r = await import(pathToFileURL(process.argv[1] + '/src/replay.js').href);
const day = JSON.parse(process.argv[2]);
const at = (t) => r.conversationsAt(day, t).map((c) => [c.id, c.working, c.check, c.says]);
console.log(JSON.stringify({
  t50: at(50), t220: at(220), t450: at(450), t700: at(700),
  before: r.momentsBefore(day, 450, 3).map((m) => m.at),
  touched: r.touchedBy(day, 'a', 999), touchedEarly: r.touchedBy(day, 'a', 250),
  said: day.slice(0, 8).map(r.sayMoment),
}));
"""


@unittest.skipUnless(NODE, "Node.js isn't installed")
class ReplayRulesTest(unittest.TestCase):
    def test_the_building_at_a_moment(self):
        run = subprocess.run([NODE, "--input-type=module", "-e", SCRIPT, ROOT, json.dumps(DAY)], capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)
        got = json.loads(run.stdout)
        self.assertEqual(got["t50"], [])
        self.assertEqual(got["t220"], [["a", True, False, {"now": "Changing till/total.py."}]])
        self.assertEqual(got["t450"], [["a", True, False, {"now": "Changing till/receipt.py."}][:3] + [{"now": "Changing till/total.py."}],
                                       ["b", False, True, {"needs": "Which font?"}]])
        self.assertEqual(got["t700"], [["a", False, True, {"now": "The till adds up now."}]])  # b had ended
        self.assertEqual(got["before"], [400, 310, 300])
        self.assertEqual((got["touched"], got["touchedEarly"]), (["till/total.py", "till/receipt.py"], ["till/total.py"]))
        self.assertEqual(got["said"], ['Fix the till started work. You asked: "Fix the till"', "Fix the till changed till/total.py.",
                                       "New menu started work.", "Fix the till changed till/receipt.py.", "Fix the till changed till/total.py.",
                                       "New menu asked: Which font?", "Fix the till finished. The till adds up now.", "New menu ended."])


class HistoryTest(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.data = os.path.join(self.base, "data")
        self.lantern = os.path.realpath(os.path.join(self.base, "code", "lantern"))
        os.makedirs(self.data)
        os.makedirs(self.lantern)
        with open(os.path.join(self.data, "company.json"), "w", encoding="utf-8") as handle:
            json.dump({"company": "Example Studio", "floors": [{"id": "lantern", "label": "Lantern", "folder": self.lantern}]}, handle)
        self.env = dict(os.environ, ARNHEIM_DATA=self.data)

    def tearDown(self):
        shutil.rmtree(self.base)

    def hook(self, **event):
        event.setdefault("session_id", "abc123def456-7890")
        event.setdefault("cwd", self.lantern)
        done = subprocess.run([sys.executable, HOOK], input=json.dumps(event), capture_output=True, text=True, env=self.env, timeout=20)
        self.assertEqual(done.returncode, 0, done.stderr)

    def moments(self):
        with open(os.path.join(self.data, "feeds", "history", budget.local_day() + ".json"), encoding="utf-8") as handle:
            return [(m["kind"], m["what"]) for m in json.load(handle)["moments"]]

    def test_a_day_of_moments(self):
        self.hook(hook_event_name="SessionStart", source="startup")
        self.hook(hook_event_name="UserPromptSubmit", prompt="Fix the bookmark")
        self.hook(hook_event_name="PostToolUse", tool_name="Read", tool_input={"file_path": os.path.join(self.lantern, "a.js")})
        self.hook(hook_event_name="PostToolUse", tool_name="Edit", tool_input={"file_path": os.path.join(self.lantern, "reader", "bookmark.js")})
        self.hook(hook_event_name="PostToolUse", tool_name="Edit", tool_input={"file_path": os.path.join(self.lantern, "reader", "bookmark.js")})
        self.hook(hook_event_name="PostToolUse", tool_name="Write", tool_input={"file_path": "/elsewhere/on/this/computer/notes.txt"})
        self.hook(hook_event_name="PermissionRequest", tool_name="Bash", tool_input={"command": "npm test"})
        self.hook(hook_event_name="Stop", last_assistant_message="Fixed the bookmark. It waits for the page to turn.")
        self.hook(hook_event_name="SessionEnd")
        self.assertEqual(self.moments(), [
            ("working", 'You asked: "Fix the bookmark"'),
            ("changed", "reader/bookmark.js"),  # inside the floor's folder, once in five minutes
            ("changed", "notes.txt"),  # outside it: the file's name only, never this computer's folders
            ("asked", "I'm waiting for your permission: Bash: npm test."),
            ("finished", "Fixed the bookmark. It waits for the page to turn."),
            ("left", "The conversation ended."),
        ])

    def test_another_companys_work_is_not_kept(self):
        outside = os.path.join(self.base, "outside")
        os.makedirs(outside)
        self.hook(hook_event_name="UserPromptSubmit", prompt="Hello", cwd=outside)
        self.assertFalse(os.path.exists(os.path.join(self.data, "feeds", "history")))


if __name__ == "__main__":
    unittest.main()
