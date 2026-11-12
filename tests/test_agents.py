"""Any agent in the building (connect/agents.py), and OpenAI's Codex CLI through its notify setting
(connect/codex.py): conversations at work, asking, finished and ended, on the floor whose folder they
work in, in their own feed, with their moments in the day's history.

Each test makes a company of its own in a temporary folder (ARNHEIM_DATA), so your data/ is never
touched. Run from the repository's folder: python3 -m unittest discover tests
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENTS = os.path.join(ROOT, "connect", "agents.py")
CODEX = os.path.join(ROOT, "connect", "codex.py")
sys.path.insert(0, os.path.join(ROOT, "connect"))
import budget  # noqa: E402  (after the path is set)


class AgentsTest(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.data = os.path.join(self.base, "data")
        self.lantern = os.path.realpath(os.path.join(self.base, "code", "lantern"))
        self.outside = os.path.realpath(os.path.join(self.base, "code", "outside"))
        for folder in (self.data, self.lantern, self.outside):
            os.makedirs(folder)
        with open(os.path.join(self.data, "company.json"), "w", encoding="utf-8") as handle:
            json.dump({"company": "Example Studio", "floors": [{"id": "lantern", "label": "Lantern", "folder": self.lantern}]}, handle)
        self.env = dict(os.environ, ARNHEIM_DATA=self.data)

    def tearDown(self):
        shutil.rmtree(self.base)

    def run_agent(self, state, says="", cwd=None, **more):
        args = [sys.executable, AGENTS, "--agent", "Codex", "--session", "th-42", "--cwd", cwd or self.lantern, "--state", state, "--says", says]
        for name, value in more.items():
            args += [f"--{name}", value]
        return subprocess.run(args, capture_output=True, text=True, env=self.env, timeout=20)

    def feed(self):
        try:
            with open(os.path.join(self.data, "feeds", "agents.json"), encoding="utf-8") as handle:
                return json.load(handle)
        except FileNotFoundError:
            return None

    def test_from_work_to_the_end(self):
        self.assertEqual(self.run_agent("working", "Fixing the login page.", title="Fix the login").returncode, 0)
        [talk] = self.feed()["conversations"]
        self.assertEqual((talk["id"], talk["agent"], talk["project"], talk["title"], talk["working"]), ("ag-codex-th42", "Codex", "Lantern", "Fix the login", True))
        self.run_agent("asking", "Should the button be blue?")
        feed = self.feed()
        [ask] = feed["tasks"]
        self.assertEqual((ask["status"], ask["session"], feed["conversations"][0]["says"]["needs"]), ("needs_you", "ag-codex-th42", "Should the button be blue?"))
        self.run_agent("finished", "Fixed the login. The button is blue now.")
        feed = self.feed()
        self.assertEqual((feed["tasks"], feed["conversations"][0]["check"], feed["conversations"][0]["working"]), ([], True, False))
        self.run_agent("ended")
        self.assertEqual(self.feed()["conversations"], [])
        with open(os.path.join(self.data, "feeds", "history", budget.local_day() + ".json"), encoding="utf-8") as handle:
            kinds = [m["kind"] for m in json.load(handle)["moments"]]
        self.assertEqual(kinds, ["working", "asked", "finished", "left"])

    def test_only_this_companys_folders(self):
        done = self.run_agent("working", "Hello", cwd=self.outside)
        self.assertEqual(done.returncode, 0)
        self.assertIn("isn't one of the building's floors", done.stderr)
        self.assertIsNone(self.feed())

    def test_codex_when_a_turn_ends(self):
        given = {"type": "agent-turn-complete", "thread-id": "0199a-b2", "turn-id": "t-7", "cwd": self.lantern,
                 "input-messages": ["Rename the settings screen"], "last-assistant-message": "Renamed it to Preferences. The tests pass."}
        done = subprocess.run([sys.executable, CODEX, json.dumps(given)], capture_output=True, text=True, env=self.env, timeout=20)
        self.assertEqual((done.returncode, done.stdout, done.stderr), (0, "", ""))
        [talk] = self.feed()["conversations"]
        self.assertEqual((talk["agent"], talk["title"], talk["check"], talk["says"]["now"]),
                         ("Codex", "Rename the settings screen", True, "Renamed it to Preferences. The tests pass."))
        for odd in ("not json", json.dumps({"type": "something-else"}), json.dumps([1, 2])):
            done = subprocess.run([sys.executable, CODEX, odd], capture_output=True, text=True, env=self.env, timeout=20)
            self.assertEqual((done.returncode, done.stdout), (0, ""))
        self.assertEqual(len(self.feed()["conversations"]), 1)


if __name__ == "__main__":
    unittest.main()
