"""Collision warnings: two conversations changing the same file within two hours. The hook tells the one
that just changed it (connect/claude_code.py), and the page shows the pair (src/clashes.js, under Node,
skipped where Node isn't installed). Each hook test makes a company of its own in a temporary folder.
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
NOW = 1_800_000_000

SCRIPT = """
import { pathToFileURL } from 'node:url';
const c = await import(pathToFileURL(process.argv[1] + '/src/clashes.js').href);
const talks = JSON.parse(process.argv[2]);
const found = c.clashesOf(talks, Number(process.argv[3]));
console.log(JSON.stringify({ pairs: found.map((x) => [x.a.id, x.b.id, x.files, x.working]), said: found.map(c.sayClash), wait: found.length ? c.waitWords(found[0], found[0].b) : null }));
"""
TALKS = [
    {"id": "a", "project": "Shop", "title": "Fix the till", "working": True, "files": [{"path": "till.py", "at": NOW - 60}, {"path": "menu.py", "at": NOW - 100}]},
    {"id": "b", "project": "Shop", "title": "New menu", "files": [{"path": "menu.py", "at": NOW - 600}, {"path": "till.py", "at": NOW - 9000}]},  # till.py too long ago
    {"id": "c", "project": "Lab", "title": "Other floor", "files": [{"path": "menu.py", "at": NOW - 5}]},
    {"id": "d", "project": "Shop", "title": "Quiet one"},
    {"id": "e", "project": "Lab", "title": "Sample", "files": [{"path": "menu.py"}]},  # no times: the sample's
]


@unittest.skipUnless(NODE, "Node.js isn't installed")
class ClashRulesTest(unittest.TestCase):
    def test_pairs_on_one_floor(self):
        run = subprocess.run([NODE, "--input-type=module", "-e", SCRIPT, ROOT, json.dumps(TALKS), str(NOW)], capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)
        got = json.loads(run.stdout)
        self.assertEqual(got["pairs"], [["a", "b", ["menu.py"], True], ["c", "e", ["menu.py"], False]])
        self.assertEqual(got["said"][0], '"Fix the till" and "New menu" both changed menu.py.')
        self.assertIn('Another agent, on "Fix the till", is changing the same files as you (menu.py).', got["wait"])


class ClashHookTest(unittest.TestCase):
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

    def edit(self, session, name):
        event = {"hook_event_name": "PostToolUse", "session_id": session, "cwd": self.lantern, "tool_name": "Edit",
                 "tool_input": {"file_path": os.path.join(self.lantern, name)}}
        done = subprocess.run([sys.executable, HOOK], input=json.dumps(event), capture_output=True, text=True, env=self.env, timeout=20)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)["hookSpecificOutput"]["additionalContext"] if done.stdout else None

    def test_the_second_one_is_told(self):
        subprocess.run([sys.executable, HOOK], input=json.dumps({"hook_event_name": "UserPromptSubmit", "session_id": "first1", "cwd": self.lantern,
                                                                 "prompt": "Fix the bookmark"}), env=self.env, timeout=20, capture_output=True, text=True)
        self.assertIsNone(self.edit("first1", "reader/page.js"))
        self.assertIsNone(self.edit("second2", "reader/streak.js"))  # another file: nothing to say
        told = self.edit("second2", "reader/page.js")
        self.assertIn('"Fix the bookmark" also changed reader/page.js in the last two hours', told)
        with open(os.path.join(self.data, "feeds", "claude-code.json"), encoding="utf-8") as handle:
            talks = {c["id"]: c for c in json.load(handle)["conversations"]}
        self.assertEqual([f["path"] for f in talks["cc-second2"]["files"]], ["reader/streak.js", "reader/page.js"])


if __name__ == "__main__":
    unittest.main()
