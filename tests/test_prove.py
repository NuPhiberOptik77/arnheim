"""Done means proven (connect/prove.py): a floor's own check runs on an agent's work after it changes
files, and what came of it is kept beside the conversation for the building to show.

Each test makes a company of its own in a temporary folder (ARNHEIM_DATA), so your data/ is never
touched, and its checks are small Python commands. Run from the repository's folder:
python3 -m unittest discover tests
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

try:
    import fcntl
except ImportError:  # Windows
    fcntl = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(ROOT, "connect", "claude_code.py")
PROVE = os.path.join(ROOT, "connect", "prove.py")
sys.path.insert(0, os.path.join(ROOT, "connect"))
import control  # noqa: E402  (after the path is set)

PASS = [sys.executable, "-c", "print('collected 12 items'); print('\\x1b[32m12 passed\\x1b[0m')"]
FAIL = [sys.executable, "-c", "import sys; [print(f'line {n}') for n in range(30)]; print('1 failed: test_login'); sys.exit(3)"]
SLOW = [sys.executable, "-c", "import time; print('starting', flush=True); time.sleep(30)"]


class ProveTest(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.data = os.path.join(self.base, "data")
        self.lantern = os.path.realpath(os.path.join(self.base, "code", "lantern"))
        os.makedirs(self.data)
        os.makedirs(self.lantern)
        self.env = dict(os.environ, ARNHEIM_DATA=self.data)
        self.company(PASS)

    def tearDown(self):
        shutil.rmtree(self.base)

    def company(self, check, **more):
        floors = [{"id": "lantern", "label": "Lantern", "folder": self.lantern, "check": {"run": check, "label": "The tests", **more} if check else None},
                  {"id": "studio", "label": "Studio"}]
        with open(os.path.join(self.data, "company.json"), "w", encoding="utf-8") as handle:
            json.dump({"company": "Example Studio", "floors": floors, "feeds": ["feeds/claude-code.json"]}, handle)

    def feed(self, talks=None):
        path = os.path.join(self.data, "feeds", "claude-code.json")
        if talks is not None:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"conversations": talks, "tasks": []}, handle)
        with open(path, encoding="utf-8") as handle:
            return {c["id"]: c for c in json.load(handle)["conversations"]}

    def prove(self, *args):
        done = subprocess.run([sys.executable, PROVE, *args], capture_output=True, text=True, env=self.env, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout.strip()

    def hook(self, **event):
        event.setdefault("session_id", "abc123def456-7890")
        event.setdefault("cwd", self.lantern)
        done = subprocess.run([sys.executable, HOOK], input=json.dumps(event), capture_output=True, text=True, env=self.env, timeout=20)
        self.assertEqual((done.returncode, done.stdout), (0, ""))

    def test_the_check_proves_the_changes_it_covers(self):
        now = time.time()
        self.feed([{"id": "cc-a", "project": "Lantern", "changed": now - 5}, {"id": "cc-b", "project": "Lantern"},
                   {"id": "cc-c", "project": "Studio", "changed": now - 5}])
        self.assertEqual(self.prove("Lantern"), "done")
        talks = self.feed()
        proof = talks["cc-a"]["proof"]
        self.assertEqual((proof["state"], proof["code"], proof["check"]), ("passed", 0, "The tests"))
        self.assertEqual(proof["tail"], "collected 12 items\n12 passed")  # the terminal's colours left out
        self.assertGreater(proof["at"], now - 5)
        self.assertNotIn("proof", talks["cc-b"])  # changed nothing
        self.assertNotIn("proof", talks["cc-c"])  # another floor
        self.assertEqual(self.prove("Lantern"), "nothing")  # nothing new to check

    def test_a_failed_check_keeps_its_last_lines(self):
        self.company(FAIL)
        self.feed([{"id": "cc-a", "project": "Lantern", "changed": time.time()}])
        self.prove("Lantern")
        proof = self.feed()["cc-a"]["proof"]
        self.assertEqual((proof["state"], proof["code"]), ("failed", 3))
        lines = proof["tail"].split("\n")
        self.assertEqual((len(lines), lines[-1], lines[0]), (14, "1 failed: test_login", "line 17"))

    def test_a_check_that_runs_too_long_is_stopped(self):
        self.company(SLOW, timeout=1)
        self.feed([{"id": "cc-a", "project": "Lantern", "changed": time.time()}])
        began = time.time()
        self.prove("Lantern")
        proof = self.feed()["cc-a"]["proof"]
        self.assertEqual((proof["state"], proof["code"], proof["tail"]), ("timeout", None, "starting"))
        self.assertLess(time.time() - began, 15)

    def test_a_check_that_cannot_start(self):
        self.company([os.path.join(self.base, "no-such-command")])
        self.feed([{"id": "cc-a", "project": "Lantern", "changed": time.time()}])
        self.prove("Lantern")
        proof = self.feed()["cc-a"]["proof"]
        self.assertEqual(proof["state"], "error")
        self.assertTrue(proof["tail"].startswith("It didn't start:"), proof["tail"])

    def test_no_check_means_nothing_runs(self):
        self.company(None)
        self.feed([{"id": "cc-a", "project": "Lantern", "changed": time.time()}])
        self.assertEqual(self.prove("Lantern"), "no-check")
        self.assertNotIn("proof", self.feed()["cc-a"])

    def test_check_it_again(self):
        self.feed([{"id": "cc-a", "project": "Lantern", "changed": 100, "proof": {"state": "failed", "at": 200}},
                   {"id": "cc-b", "project": "Lantern", "changed": 100, "proof": {"state": "failed", "at": 200}}])
        self.assertEqual(self.prove("Lantern", "--also", "cc-a"), "done")
        talks = self.feed()
        self.assertEqual((talks["cc-a"]["proof"]["state"], talks["cc-b"]["proof"]["state"]), ("passed", "failed"))

    def test_check_it_again_from_the_building(self):
        self.feed([{"id": "cc-a", "project": "Lantern", "changed": 100, "proof": {"state": "failed", "at": 200}},
                   {"id": "cc-s", "project": "Studio", "changed": 100}])
        building = control.Control(self.data, claude=[sys.executable, "-c", "pass"])
        self.assertEqual(building.prove("cc-a"), {"ok": True, "check": "The tests"})
        for _ in range(100):
            if self.feed()["cc-a"]["proof"]["state"] == "passed":
                break
            time.sleep(0.1)
        self.assertEqual(self.feed()["cc-a"]["proof"]["state"], "passed")
        with self.assertRaises(control.Refused):  # Studio has no check
            building.prove("cc-s")
        with self.assertRaises(control.Refused):
            building.prove("cc-nobody")
        self.assertEqual([p["check"] for p in building.state()["projects"]], ["The tests"])

    @unittest.skipUnless(fcntl, "no file locks here")
    def test_one_check_at_a_time_and_the_next_one_waits_its_turn(self):
        self.feed([{"id": "cc-a", "project": "Lantern", "changed": time.time()}])
        folder = os.path.join(self.data, "feeds", "proof")
        os.makedirs(folder, exist_ok=True)
        self.prove("Lantern")  # names the lock
        [lock] = [n for n in os.listdir(folder) if n.endswith(".lock")]
        self.feed([{"id": "cc-a", "project": "Lantern", "changed": time.time() + 1}])
        with open(os.path.join(folder, lock), "a") as held:  # as a run going on would
            fcntl.flock(held, fcntl.LOCK_EX)
            self.assertEqual(self.prove("Lantern", "--also", "cc-a"), "busy")
        self.assertTrue(os.path.exists(os.path.join(folder, lock.replace(".lock", ".again"))))
        self.assertEqual(self.prove("Lantern"), "done")  # the word left is taken up by the next run
        self.assertFalse(os.path.exists(os.path.join(folder, lock.replace(".lock", ".again"))))

    def test_from_an_agents_edit_to_its_proof(self):
        self.hook(hook_event_name="UserPromptSubmit", prompt="Fix the login")
        self.hook(hook_event_name="PostToolUse", tool_name="Read", tool_input={"file_path": "a.py"})
        self.assertNotIn("changed", self.feed()["cc-abc123def456"])  # reading changes nothing
        self.hook(hook_event_name="PostToolUse", tool_name="Edit", tool_input={"file_path": "a.py"})
        self.assertIn("changed", self.feed()["cc-abc123def456"])
        self.hook(hook_event_name="Stop", last_assistant_message="Fixed the login.")
        for _ in range(100):  # it runs in the background: Claude Code doesn't wait for it
            proof = self.feed()["cc-abc123def456"].get("proof") or {}
            if proof.get("state") not in (None, "checking"):
                break
            time.sleep(0.1)
        self.assertEqual(proof.get("state"), "passed")
        self.hook(hook_event_name="UserPromptSubmit", prompt="Thanks")
        self.hook(hook_event_name="Stop", last_assistant_message="You're welcome.")
        time.sleep(0.5)
        self.assertEqual(self.feed()["cc-abc123def456"]["proof"]["at"], proof["at"])  # nothing new to check


class CheckOfTest(unittest.TestCase):
    def test_what_a_floor_may_name(self):
        here = os.path.realpath(tempfile.gettempdir())
        self.assertEqual(control.check_of({"folder": here, "check": ["make", "test"]}),
                         {"run": ["make", "test"], "folder": here, "timeout": 600, "label": "Its check"})
        self.assertEqual(control.check_of({"folders": [here], "check": {"run": ["npm", "test"], "label": "The tests", "timeout": 99999}})["timeout"], 3600)
        for floor in ({"folder": here}, {"folder": here, "check": "make test"}, {"folder": here, "check": []},
                      {"folder": here, "check": ["make", 3]}, {"check": ["make"]}, {"folder": os.path.join(here, "no-such-folder-here"), "check": ["make"]}):
            with self.subTest(floor=floor):
                self.assertIsNone(control.check_of(floor))


if __name__ == "__main__":
    unittest.main()
