"""How long things wait on you: the hook marks the moment an agent that asked you something goes on
(connect/claude_code.py, "answered"), and the page times each wait and fills its meter (src/waiting.js).

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
    {"at": 100, "key": "a", "project": "Shop", "title": "Fix the till", "kind": "working", "what": ""},
    {"at": 200, "key": "a", "project": "Shop", "title": "Fix the till", "kind": "asked", "what": "May I run the tests?"},
    {"at": 260, "key": "a", "project": "Shop", "title": "Fix the till", "kind": "asked", "what": "Again?"},  # still the same wait
    {"at": 500, "key": "a", "project": "Shop", "title": "Fix the till", "kind": "answered", "what": "It went on."},
    {"at": 600, "key": "b", "project": "Lab", "title": "New menu", "kind": "asked", "what": "Which font?"},
    {"at": 700, "key": "c", "project": "Lab", "title": "Old menu", "kind": "asked", "what": "Keep it?"},
    {"at": 900, "key": "c", "project": "Lab", "title": "Old menu", "kind": "finished", "what": "Kept."},
    {"at": 950, "key": "d", "project": "Lab", "title": "Gone quiet", "kind": "asked", "what": "Hello?"},
]

SCRIPT = """
import { pathToFileURL } from 'node:url';
const w = await import(pathToFileURL(process.argv[1] + '/src/waiting.js').href);
const day = JSON.parse(process.argv[2]);
const now = 1600;
const all = w.waits(day, now);
const held = w.waits(day, now, new Set(['b']));
const items = [
  { kind: 'permission', key: 'b', title: 'New menu', project: 'Lab', at: 600 },
  { kind: 'question', key: 'e', title: 'Asks', project: 'Lab', at: 1500 },
  { kind: 'task', title: 'A task', at: 10 },
  { kind: 'turn', key: 'f', title: 'Done', at: 20 },
];
console.log(JSON.stringify({
  all: all.map((x) => [x.key, x.from, x.to, x.seconds]),
  held: held.map((x) => x.key),
  sum: (({ total, count, longest }) => [total, count, longest.key])(w.waitedSum(held)),
  words: [0, 59, 60, 360, 3600, 3900, 7260].map(w.waitFor),
  moods: [60, 300, 899, 900].map(w.waitMood),
  meter: (({ item, seconds, share, mood }) => [item.key, seconds, share, mood])(w.meter(items, now)),
  noMeter: w.meter(items.slice(2), now),
  lines: items.map((i) => w.waitingLine(i, now)),
  said: w.sayWaited(held, items, (p) => p.toUpperCase(), now),
  none: w.sayWaited([], [], (p) => p, now),
  asked: ['How long have the agents waited on me?', 'how long has it been waiting', 'waiting time today', 'what is waiting on me?'].map((q) => w.WAITED_ASKED.test(q)),
}));
"""


@unittest.skipUnless(NODE, "Node.js isn't installed")
class WaitingWordsTest(unittest.TestCase):
    def test_waits_and_the_meter(self):
        done = subprocess.run([NODE, "--input-type=module", "-e", SCRIPT, ROOT, json.dumps(DAY)], capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        out = json.loads(done.stdout)
        self.assertEqual(out["all"], [["a", 200, 500, 300], ["b", 600, None, 1000], ["c", 700, 900, 200], ["d", 950, None, 650]])
        self.assertEqual(out["held"], ["a", "b", "c"])  # "d" went quiet without a word: left out
        self.assertEqual(out["sum"], [1500, 3, "b"])
        self.assertEqual(out["words"], ["under a minute", "under a minute", "1 min", "6 min", "1 h", "1 h 5 min", "2 h 1 min"])
        self.assertEqual(out["moods"], ["working", "needs", "needs", "failed"])
        self.assertEqual(out["meter"], ["b", 1000, 1, "failed"])  # the longest held up, full past fifteen minutes
        self.assertIsNone(out["noMeter"])  # tasks and finished agents hold nobody up
        self.assertEqual(out["lines"], ["Waiting 16 min", "Waiting 1 min", None, None])
        self.assertEqual(out["said"], 'Agents waited on you 25 min today, 3 times. The longest was 16 min: "New menu" on LAB. '
                                      "2 are waiting now, the longest for 16 min.")
        self.assertEqual(out["none"], "No agent has waited on you today.")
        self.assertEqual(out["asked"], [True, True, True, False])


class AnsweredTest(unittest.TestCase):
    """The hook: an agent that asked for your permission and then went on gets an "answered" moment, so its wait ends."""

    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.data = os.path.join(self.base, "data")
        self.shop = os.path.realpath(os.path.join(self.base, "shop"))
        os.makedirs(self.data)
        os.makedirs(self.shop)
        with open(os.path.join(self.data, "company.json"), "w", encoding="utf-8") as handle:
            json.dump({"company": "Example", "floors": [{"id": "shop", "label": "Shop", "folder": self.shop}]}, handle)
        self.env = {**os.environ, "ARNHEIM_DATA": self.data}

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def hook(self, **event):
        event = {"session_id": "abc123def456-7890", "cwd": self.shop, **event}
        done = subprocess.run([sys.executable, HOOK], input=json.dumps(event), capture_output=True, text=True, env=self.env, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_answered_ends_the_wait(self):
        self.hook(hook_event_name="UserPromptSubmit", prompt="Fix the till")
        self.hook(hook_event_name="Notification", notification_type="permission_prompt", message="Claude needs your permission to use Bash")
        self.hook(hook_event_name="PostToolUse", tool_name="Bash", tool_input={"command": "make test"})
        self.hook(hook_event_name="PostToolUse", tool_name="Bash", tool_input={"command": "make"})  # working already: nothing
        with open(os.path.join(self.data, "feeds", "history", budget.local_day() + ".json"), encoding="utf-8") as handle:
            day = json.load(handle)
        self.assertEqual([m["kind"] for m in day["moments"]], ["working", "asked", "answered"])
        self.assertEqual(day["spent"], {"Shop": 0})  # each floor's spend that day, for the weekly report


if __name__ == "__main__":
    unittest.main()
