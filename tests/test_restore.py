"""Restore points: the hook takes one before an agent changes files (connect/claude_code.py and
connect/restore.py), and the building puts the files back to one (connect/control.py). The page's words
for them are JavaScript (src/restore.js), so that test runs under Node.js, and is skipped without it.

Each test makes a company and a git project of its own in a temporary folder (ARNHEIM_DATA), so your
data/ and your projects are never touched. Run from the repository's folder: python3 -m unittest discover tests
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "connect"))

import control  # noqa: E402  (after the path is set)
import restore  # noqa: E402

HOOK = os.path.join(ROOT, "connect", "claude_code.py")
NODE = shutil.which("node")
SESSION = "abc123def456-7890"
KEY = "cc-abc123def456"


def git(folder, *args):
    return subprocess.run(["git", "-C", folder, *args], capture_output=True, text=True, check=True).stdout.strip()


@unittest.skipUnless(shutil.which("git"), "git isn't installed")
class RestoreTest(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.data = os.path.join(self.base, "data")
        self.lantern = os.path.realpath(os.path.join(self.base, "code", "lantern"))
        os.makedirs(self.data)
        os.makedirs(self.lantern)
        company = {"company": "Example Studio", "floors": [{"id": "lantern", "label": "Lantern", "folder": self.lantern}],
                   "feeds": ["feeds/claude-code.json", "feeds/restore.json"]}
        with open(os.path.join(self.data, "company.json"), "w", encoding="utf-8") as handle:
            json.dump(company, handle)
        git(self.lantern, "init", "-q")
        for name, value in (("user.name", "Someone"), ("user.email", "someone@example.com"), ("commit.gpgsign", "false")):
            git(self.lantern, "config", name, value)
        self.write("app.py", "print('one')\n")
        self.write("notes.md", "notes\n")
        self.write(".gitignore", "build/\n")
        git(self.lantern, "add", "-A")
        git(self.lantern, "commit", "-qm", "first")
        self.env = {**os.environ, "ARNHEIM_DATA": self.data}

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def write(self, name, text):
        path = os.path.join(self.lantern, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)

    def read(self, name):
        with open(os.path.join(self.lantern, name), encoding="utf-8") as handle:
            return handle.read()

    def hook(self, **event):
        event = {"session_id": SESSION, "cwd": self.lantern, **event}
        done = subprocess.run([sys.executable, HOOK], input=json.dumps(event), capture_output=True, text=True, env=self.env, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout) if done.stdout.strip() else None

    def points(self):
        return restore.read_points(self.data)

    def feed(self):
        with open(os.path.join(self.data, "feeds", "claude-code.json"), encoding="utf-8") as handle:
            return json.load(handle)

    def test_one_a_turn_before_the_first_change(self):
        self.hook(hook_event_name="UserPromptSubmit", prompt="Tidy the app")
        self.write("app.py", "print('staged')\n")
        git(self.lantern, "add", "app.py")  # staged, and an untracked file: both are in the point, and stay as they were
        self.write("draft.txt", "a draft\n")
        self.assertIsNone(self.hook(hook_event_name="PreToolUse", tool_name="Read", tool_input={"file_path": "app.py"}))
        self.assertEqual(self.points(), [])  # reading changes nothing: no point
        self.assertIsNone(self.hook(hook_event_name="PreToolUse", tool_name="Edit", tool_input={"file_path": "app.py"}))
        points = self.points()
        self.assertEqual(len(points), 1)
        p = points[0]
        self.assertEqual((p["project"], p["key"], p["repo"], p["by"], p["files"]), ("Lantern", KEY, ".", "agent", 2))
        self.assertEqual(p["why"], 'before changing files for "Tidy the app"')
        self.assertNotIn(self.base, json.dumps(points))  # no folder of this computer's in the feed
        self.assertEqual(git(self.lantern, "status", "--short"), "M  app.py\n?? draft.txt")  # untouched
        self.assertEqual(git(self.lantern, "rev-list", "--count", "HEAD"), "1")  # nothing on the branch
        self.assertTrue(git(self.lantern, "for-each-ref", "refs/arnheim/restore/"))
        self.hook(hook_event_name="PreToolUse", tool_name="Write", tool_input={"file_path": "b.py"})
        self.assertEqual(len(self.points()), 1)  # the same turn: once is enough
        self.hook(hook_event_name="PreToolUse", tool_name="Bash", tool_input={"command": "ls -la"})
        self.assertEqual(len(self.points()), 1)  # a harmless command: none
        self.hook(hook_event_name="PreToolUse", tool_name="Bash", tool_input={"command": "cd x && rm -rf build"})
        self.assertEqual(len(self.points()), 2)  # a bulk delete: one every time
        self.assertEqual(self.points()[-1]["why"], "before: cd x && rm -rf build")
        self.hook(hook_event_name="UserPromptSubmit", prompt="And the notes")
        self.hook(hook_event_name="PreToolUse", tool_name="MultiEdit", tool_input={"file_path": "notes.md"})
        self.assertEqual(len(self.points()), 3)  # a new message: a new turn

    def test_go_back_from_the_building(self):
        self.hook(hook_event_name="UserPromptSubmit", prompt="Tidy the app")
        self.write("draft.txt", "a draft\n")
        self.hook(hook_event_name="PreToolUse", tool_name="Edit", tool_input={"file_path": "app.py"})
        point = self.points()[0]
        # The agent's changes: one file changed, one deleted, one made, one draft deleted.
        self.write("app.py", "print('broken')\n")
        os.remove(os.path.join(self.lantern, "notes.md"))
        os.remove(os.path.join(self.lantern, "draft.txt"))
        self.write("new.py", "new\n")
        self.write("build/out.txt", "ignored\n")
        self.hook(hook_event_name="Stop", last_assistant_message="Done.")
        c = control.Control(self.data)
        ask = lambda name, body: c.handle("POST", name, json.dumps(body).encode(), c.token)
        code, _, out, _ = ask("restore", {"id": point["id"]})
        out = json.loads(out)
        self.assertEqual(code, 200, out)
        self.assertEqual(self.read("app.py"), "print('one')\n")
        self.assertEqual(self.read("notes.md"), "notes\n")
        self.assertEqual(self.read("draft.txt"), "a draft\n")
        self.assertEqual(self.read("new.py"), "new\n")  # made since: left, and listed
        self.assertEqual(out["left"], ["new.py"])
        self.assertTrue(os.path.exists(os.path.join(self.lantern, "build", "out.txt")))  # ignored: never touched
        kept = next(p for p in self.points() if p["id"] == out["kept"])
        self.assertEqual((kept["by"], kept["key"]), ("you", ""))
        # Going back can be undone: back to how it was a moment ago.
        code, _, out, _ = ask("restore", {"id": kept["id"]})
        self.assertEqual(code, 200, out)
        self.assertEqual(self.read("app.py"), "print('broken')\n")
        # Refused: not a point, one not kept, or an agent at work on the floor.
        for body, why in (({"id": "rm -rf /"}, "isn't a restore point"), ({"id": "rp-000000000000"}, "isn't kept")):
            code, _, said, _ = ask("restore", body)
            self.assertEqual(code, 400)
            self.assertIn(why, json.loads(said)["error"])
        self.hook(hook_event_name="UserPromptSubmit", prompt="More")
        code, _, said, _ = ask("restore", {"id": point["id"]})
        self.assertEqual(code, 400)
        self.assertIn("at work on Lantern", json.loads(said)["error"])

    def test_not_in_git_or_not_the_company(self):
        plain = os.path.join(self.base, "code", "plain")
        os.makedirs(plain)
        self.assertIsNone(restore.take(plain, "before", project="Lantern", data=self.data))
        elsewhere = os.path.join(self.base, "elsewhere")
        os.makedirs(elsewhere)
        git(elsewhere, "init", "-q")
        self.assertIsNone(restore.take(elsewhere, "before", project="Lantern", data=self.data))  # near no floor
        self.hook(hook_event_name="PreToolUse", tool_name="Edit", tool_input={"file_path": "x"}, cwd=elsewhere)
        self.assertEqual(self.points(), [])

    def test_keeps_the_last_forty(self):
        for i in range(restore.KEEP + 3):
            restore.take(self.lantern, f"point {i}", project="Lantern", data=self.data, now=1000 + i)
            self.write("app.py", f"print({i})\n")
        points = self.points()
        self.assertEqual(len(points), restore.KEEP)
        self.assertEqual(points[0]["why"], "point 3")
        refs = git(self.lantern, "for-each-ref", "--format=%(refname)", "refs/arnheim/restore/").split()
        self.assertEqual(len(refs), restore.KEEP)  # the oldest let go

    def test_risky_commands(self):
        for command in ("rm -rf build", "rm -r x", "git reset --hard HEAD~1", "git clean -fdx", "git checkout -- app.py",
                        "git checkout .", "git restore app.py", "git stash", "find . -name '*.pyc' -delete", "a && rm -fr y",
                        "git switch -f main", "truncate -s 0 log.txt"):
            self.assertTrue(restore.risky(command), command)
        for command in ("ls -la", "rm file.txt", "git status", "git checkout main", "python3 -m unittest", "grep -r x ."):
            self.assertFalse(restore.risky(command), command)


SCRIPT = """
import { pathToFileURL } from 'node:url';
const r = await import(pathToFileURL(process.argv[1] + '/src/restore.js').href);
const points = [
  { id: 'rp-aaaaaaaaaaaa', at: 100, project: 'Lantern', key: 'cc-1', title: 'Fix', why: 'before changing files for "Fix"', by: 'agent', files: 2 },
  { id: 'rp-bbbbbbbbbbbb', at: 300, project: 'Lantern', key: 'cc-2', title: 'Docs', why: 'before: rm -rf build', by: 'agent', files: 0 },
  { id: 'rp-cccccccccccc', at: 200, project: 'Tidepool', key: 'cc-3', why: 'before changing files', by: 'agent' },
  { id: 'nope', at: 400, project: 'Lantern' },
];
const clock = (t) => `t${t}`;
console.log(JSON.stringify({
  floor: r.pointsOf(points, { project: 'Lantern' }).map((p) => p.id),
  talk: r.pointsOf(points, { key: 'cc-3' }).map((p) => p.id),
  line: r.sayPoint(points[0], clock),
  none: r.sayRestore([]),
  some: r.sayRestore(points, (p) => p.toUpperCase(), clock, 2),
  back: r.wentBack({ kept: 'rp-x', left: ['a.py', 'b.py'], more: 1 }),
  backOne: r.wentBack({ kept: null, left: ['a.py'], more: 0 }),
  backNone: r.wentBack({ kept: 'rp-x', left: [] }),
  asked: ['can I undo what the agent did?', 'restore points', 'put the files back', 'roll it back', 'go back to before', 'what is the weather'].map((q) => r.RESTORE_ASKED.test(q)),
}));
"""


@unittest.skipUnless(NODE, "Node.js isn't installed")
class RestoreWordsTest(unittest.TestCase):
    def test_words(self):
        done = subprocess.run([NODE, "--input-type=module", "-e", SCRIPT, ROOT], capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        out = json.loads(done.stdout)
        self.assertEqual(out["floor"], ["rp-bbbbbbbbbbbb", "rp-aaaaaaaaaaaa"])
        self.assertEqual(out["talk"], ["rp-cccccccccccc"])
        self.assertEqual(out["line"], 't100, before changing files for "Fix". 2 files not yet committed then')
        self.assertIn("no restore points yet", out["none"])
        self.assertTrue(out["some"].startswith("3 restore points are kept. The latest: LANTERN at t300, before: rm -rf build; TIDEPOOL at t200"))
        self.assertEqual(out["back"], "The files are back as they were. 3 files made since then were left as they are: a.py, b.py and 1 more. "
                                      "How they were a moment ago is kept as a restore point too.")
        self.assertEqual(out["backOne"], "The files are back as they were. 1 file made since then was left as it is: a.py.")
        self.assertEqual(out["backNone"], "The files are back as they were. How they were a moment ago is kept as a restore point too.")
        self.assertEqual(out["asked"], [True, True, True, True, True, False])


if __name__ == "__main__":
    unittest.main()
