"""The company's memory (data/memory.json): decisions the building is asked to remember, handed to every
Claude Code agent in the company's folders as it starts, and to one at work with your next message.

Each test makes a company of its own in a temporary folder (ARNHEIM_DATA), so your data/ is never
touched. Run from the repository's folder: python3 -m unittest discover tests
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(ROOT, "connect", "claude_code.py")
sys.path.insert(0, os.path.join(ROOT, "connect"))
import control  # noqa: E402  (after the path is set)


class MemoryTest(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.data = os.path.join(self.base, "data")
        self.lantern = os.path.realpath(os.path.join(self.base, "code", "lantern"))
        self.elsewhere = os.path.realpath(os.path.join(self.base, "code", "not-this-company"))
        os.makedirs(self.data)
        os.makedirs(self.lantern)
        os.makedirs(self.elsewhere)
        with open(os.path.join(self.data, "company.json"), "w", encoding="utf-8") as handle:
            json.dump({"company": "Example Studio", "floors": [{"id": "lantern", "label": "Lantern", "folder": self.lantern}],
                       "feeds": ["feeds/claude-code.json"]}, handle)
        self.env = dict(os.environ, ARNHEIM_DATA=self.data)
        self.building = control.Control(self.data, claude=[sys.executable, "-c", "pass"])

    def tearDown(self):
        shutil.rmtree(self.base)

    def hook(self, **event):
        event.setdefault("session_id", "abc123def456-7890")
        event.setdefault("cwd", self.lantern)
        done = subprocess.run([sys.executable, HOOK], input=json.dumps(event), capture_output=True, text=True, env=self.env, timeout=20)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout) if done.stdout else None

    def said(self, out):
        return out and out["hookSpecificOutput"]["additionalContext"]

    def test_remember_and_forget(self):
        first = self.building.remember("  Never push   on a Friday. ")
        self.assertEqual(first["text"], "Never push on a Friday.")
        self.assertTrue(first["id"].startswith("m-"))
        self.building.remember("Every kit gets a printed safety sheet.")
        self.assertEqual([m["text"] for m in control.memory(self.data)], ["Never push on a Friday.", "Every kit gets a printed safety sheet."])
        for bad in ("", "   ", "x" * 301, "never push on a friday."):
            with self.subTest(bad=bad[:20]), self.assertRaises(control.Refused):
                self.building.remember(bad)
        self.assertEqual(self.building.forget(first["id"]), {"ok": True})
        self.assertEqual([m["text"] for m in control.memory(self.data)], ["Every kit gets a printed safety sheet."])
        with self.assertRaises(control.Refused):
            self.building.forget(first["id"])

    def test_through_the_pages_requests(self):
        def post(name, body):
            code, _, data, _ = self.building.handle("POST", name, json.dumps(body).encode(), self.building.token)
            return code, json.loads(data)
        code, row = post("remember", {"text": "Keep the app free."})
        self.assertEqual(code, 200)
        self.assertEqual(post("remember", {"text": "Keep the app free."})[0], 400)
        self.assertEqual(post("forget", {"id": row["id"]}), (200, {"ok": True}))
        code, _, _, _ = self.building.handle("POST", "remember", b'{"text": "x"}', "not-the-token")
        self.assertEqual(code, 403)

    def test_nothing_to_tell_means_nothing_said(self):
        self.assertIsNone(self.hook(hook_event_name="SessionStart", source="startup"))
        self.assertIsNone(self.hook(hook_event_name="UserPromptSubmit", prompt="Hello"))

    def test_every_agent_starts_knowing_it(self):
        self.building.remember("Never push on a Friday.")
        self.building.remember("Every kit gets a printed safety sheet.")
        told = self.said(self.hook(hook_event_name="SessionStart", source="startup"))
        self.assertIn("Follow them unless they tell you otherwise: (1) Never push on a Friday. (2) Every kit gets a printed safety sheet.", told)
        self.assertIsNone(self.hook(hook_event_name="UserPromptSubmit", prompt="Fix the login"))  # it knows already

        time.sleep(0.01)
        self.building.remember("Ask before adding a new library.")
        told = self.said(self.hook(hook_event_name="UserPromptSubmit", prompt="Carry on"))
        self.assertIn("made new standing decisions since you started", told)
        self.assertIn("(1) Ask before adding a new library.", told)
        self.assertNotIn("Friday", told)
        self.assertIsNone(self.hook(hook_event_name="UserPromptSubmit", prompt="And again"))

        told = self.said(self.hook(hook_event_name="SessionStart", source="compact"))  # its context was cut short: all of it again
        self.assertIn("(3) Ask before adding a new library.", told)

    def test_with_your_message_from_the_building(self):
        self.hook(hook_event_name="SessionStart", source="startup")
        time.sleep(0.01)
        self.building.remember("Never push on a Friday.")
        control.Box(self.data).post("cc-abc123def456", "Use the blue logo")
        told = self.said(self.hook(hook_event_name="UserPromptSubmit", prompt="Next step"))
        self.assertIn('"Use the blue logo"', told)
        self.assertIn("(1) Never push on a Friday.", told)

    def test_only_this_companys_agents(self):
        self.building.remember("Never push on a Friday.")
        self.assertIsNone(self.hook(hook_event_name="SessionStart", source="startup", cwd=self.elsewhere, session_id="zzz999"))
        self.assertIsNone(self.hook(hook_event_name="UserPromptSubmit", prompt="Hi", cwd=self.elsewhere, session_id="zzz999"))

    def test_a_broken_memory_file_never_troubles_claude_code(self):
        with open(os.path.join(self.data, "memory.json"), "w", encoding="utf-8") as handle:
            handle.write("{ not json")
        self.assertIsNone(self.hook(hook_event_name="SessionStart", source="startup"))
        with open(os.path.join(self.data, "memory.json"), "w", encoding="utf-8") as handle:
            json.dump({"memory": ["a string", {"text": ""}, {"text": "Keep it short."}]}, handle)
        self.assertIn("(1) Keep it short.", self.said(self.hook(hook_event_name="SessionStart", source="startup")))


if __name__ == "__main__":
    unittest.main()
