"""The connectors in connect/: what Claude Code's hooks and git turn into, in data/feeds/.

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
HOOK = os.path.join(ROOT, "connect", "claude_code.py")
PROJECTS = os.path.join(ROOT, "connect", "projects.py")


class ConnectTest(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.data = os.path.join(self.base, "data")
        self.lantern = os.path.join(self.base, "code", "lantern")
        os.makedirs(self.data)
        os.makedirs(os.path.join(self.lantern, "app"))
        company = {
            "company": "Example Studio",
            "rooms": [{"id": "work", "label": "Work"}, {"id": "conversations", "label": "Conversations"}],
            "floors": [{"id": "lantern", "label": "Lantern", "folder": self.lantern}, {"id": "studio", "label": "Studio"}],
            "feeds": ["feeds/claude-code.json", "feeds/projects.json"],
        }
        with open(os.path.join(self.data, "company.json"), "w", encoding="utf-8") as handle:
            json.dump(company, handle)
        self.env = dict(os.environ, ARNHEIM_DATA=self.data)

    def tearDown(self):
        shutil.rmtree(self.base)

    def feed(self, name="claude-code.json"):
        try:
            with open(os.path.join(self.data, "feeds", name), encoding="utf-8") as handle:
                return json.load(handle)
        except FileNotFoundError:
            return None

    def hook(self, raw=None, **event):
        event.setdefault("session_id", "abc123def456-7890")
        event.setdefault("cwd", self.lantern)
        done = subprocess.run([sys.executable, HOOK], input=json.dumps(event) if raw is None else raw,
                              capture_output=True, text=True, env=self.env, timeout=20)
        self.assertEqual(done.returncode, 0)
        self.assertEqual(done.stdout, "")  # what a hook prints can reach Claude, so it prints nothing
        return self.feed()

    def test_a_conversation_from_start_to_end(self):
        feed = self.hook(hook_event_name="SessionStart", source="startup")
        [talk] = feed["conversations"]
        self.assertEqual((talk["project"], talk["working"], talk["check"]), ("Lantern", False, False))

        feed = self.hook(hook_event_name="UserPromptSubmit", prompt="Fix the bookmark that jumps\nback a page", cwd=os.path.join(self.lantern, "app"))
        [talk] = feed["conversations"]
        self.assertEqual(talk["title"], "Fix the bookmark that jumps back a page")
        self.assertTrue(talk["working"])
        self.assertIn("Fix the bookmark", talk["says"]["now"])

        feed = self.hook(hook_event_name="Notification", notification_type="permission_prompt", message="Claude needs your permission to use Bash")
        [ask] = [t for t in feed["tasks"] if t["status"] == "needs_you"]
        self.assertEqual(ask["project"], "Lantern")
        self.assertIn("permission", ask["title"])
        self.assertFalse(feed["conversations"][0]["working"])

        feed = self.hook(hook_event_name="PostToolUse", tool_name="Bash", tool_input={"command": "ls"})
        self.assertEqual([t for t in feed["tasks"] if t["status"] == "needs_you"], [])  # answered
        self.assertTrue(feed["conversations"][0]["working"])

        feed = self.hook(hook_event_name="TaskCreated", task_id="1", task_subject="Write a test for the bookmark")
        self.assertEqual([(t["title"], t["status"]) for t in feed["tasks"]], [("Write a test for the bookmark", "open")])
        feed = self.hook(hook_event_name="PostToolUse", tool_name="TaskUpdate", tool_input={"taskId": "1", "status": "in_progress"})
        self.assertEqual(feed["tasks"][0]["status"], "working")
        feed = self.hook(hook_event_name="TaskCompleted", task_id="1", task_subject="Write a test for the bookmark")
        self.assertEqual(feed["tasks"], [])

        said = "The bookmark now waits until the page has turned. I tried it on a long book and it held. " + "More detail. " * 40
        feed = self.hook(hook_event_name="Stop", last_assistant_message=said, stop_hook_active=False, background_tasks=[])
        [talk] = feed["conversations"]
        self.assertEqual((talk["working"], talk["check"]), (False, True))
        self.assertTrue(talk["says"]["now"].startswith("The bookmark now waits until the page has turned."))
        self.assertLessEqual(len(talk["says"]["now"]), 301)

        feed = self.hook(hook_event_name="SessionEnd", reason="prompt_input_exit")
        self.assertEqual((feed["conversations"], feed["tasks"]), ([], []))

    def test_a_conversation_that_moves_out_keeps_its_seat(self):
        self.hook(hook_event_name="UserPromptSubmit", prompt="Tidy up")
        feed = self.hook(hook_event_name="Stop", last_assistant_message="Done.", cwd=self.base)
        [talk] = feed["conversations"]
        self.assertEqual((talk["project"], talk["check"]), ("Lantern", True))

    def test_two_conversations_at_once(self):
        self.hook(hook_event_name="UserPromptSubmit", prompt="First", session_id="one")
        feed = self.hook(hook_event_name="UserPromptSubmit", prompt="Second", session_id="two")
        self.assertEqual(sorted(t["title"] for t in feed["conversations"]), ["First", "Second"])

    def test_the_older_todo_list(self):
        todos = [{"content": "Plan it", "status": "completed"}, {"content": "Build it", "status": "in_progress"}, {"content": "Ship it", "status": "pending"}]
        feed = self.hook(hook_event_name="PostToolUse", tool_name="TodoWrite", tool_input={"todos": todos})
        self.assertEqual([(t["title"], t["status"]) for t in feed["tasks"]], [("Build it", "working"), ("Ship it", "open")])

    def test_only_this_companys_folders(self):
        self.assertIsNone(self.hook(hook_event_name="SessionStart", cwd=self.base))  # no floor holds it
        self.assertIsNone(self.hook(hook_event_name="SessionStart", cwd=self.lantern + "-old"))

    def test_never_troubles_claude_code(self):
        for raw in ("", "not json", "[1, 2]", json.dumps({"hook_event_name": "Stop"})):
            self.assertIsNone(self.hook(raw=raw))
        with open(os.path.join(self.data, "company.json"), "w", encoding="utf-8") as handle:
            handle.write("{ broken")
        self.assertIsNone(self.hook(hook_event_name="SessionStart"))

    @unittest.skipUnless(shutil.which("git"), "git is not installed")
    def test_unsaved_changes_from_git(self):
        subprocess.run(["git", "init", "-q", self.lantern], check=True)
        with open(os.path.join(self.lantern, "app", "page.txt"), "w", encoding="utf-8") as handle:
            handle.write("a change")
        done = subprocess.run([sys.executable, PROJECTS, "--no-github"], capture_output=True, text=True, env=self.env, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        [copy] = self.feed("projects.json")["copies"]
        self.assertEqual((copy["project"], copy["changes"]), ("Lantern", 1))
        self.assertEqual(self.feed("projects.json")["pullRequests"], [])


if __name__ == "__main__":
    unittest.main()
