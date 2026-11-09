"""Control of Claude Code agents from the building: connect/control.py, and the hook's side of it in
connect/claude_code.py. A stand-in for Claude Code's `claude` command answers for real agents.

Each test makes a company of its own in a temporary folder (ARNHEIM_DATA), so your data/ is never
touched. Run from the repository's folder: python3 -m unittest discover tests
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "connect"))

import control  # noqa: E402  (after the path is set)

HOOK = os.path.join(ROOT, "connect", "claude_code.py")
SESSION = "abc123def456-7890"
KEY = "cc-abc123def456"

# Stands in for `claude -p --output-format stream-json`: reads the words on stdin and says them back,
# with the folder it ran in and how it was started. Words starting "wait" keep it busy a while.
FAKE = r'''
import json, os, sys, time
args = sys.argv[1:]
words = sys.stdin.read()
how = "resumed" if "--resume" in args else "started"
sid = args[args.index("--resume" if how == "resumed" else "--session-id") + 1]
print(json.dumps({"type": "system", "subtype": "init", "session_id": sid}), flush=True)
if words.startswith("wait"):
    time.sleep(30)
said = f"{how} {sid} in {os.getcwd()}: {words}"
print(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": said}]}}), flush=True)
print(json.dumps({"type": "result", "result": said, "session_id": sid}), flush=True)
'''


class ControlTest(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.data = os.path.join(self.base, "data")
        self.lantern = os.path.realpath(os.path.join(self.base, "code", "lantern"))
        os.makedirs(self.data)
        os.makedirs(self.lantern)
        company = {
            "company": "Example Studio",
            "rooms": [{"id": "work", "label": "Work"}, {"id": "conversations", "label": "Conversations"}],
            "floors": [{"id": "lantern", "label": "Lantern", "folder": self.lantern}, {"id": "studio", "label": "Studio"}],
            "feeds": ["feeds/claude-code.json"],
        }
        with open(os.path.join(self.data, "company.json"), "w", encoding="utf-8") as handle:
            json.dump(company, handle)
        fake = os.path.join(self.base, "fake_claude.py")
        with open(fake, "w", encoding="utf-8") as handle:
            handle.write(FAKE)
        self.env = dict(os.environ, ARNHEIM_DATA=self.data)
        self.box = control.Box(self.data)
        self.control = control.Control(self.data, claude=[sys.executable, fake])

    def tearDown(self):
        shutil.rmtree(self.base)

    def hook(self, **event):
        """Runs the hook as Claude Code does. What it printed, as JSON, or None."""
        event.setdefault("session_id", SESSION)
        event.setdefault("cwd", self.lantern)
        done = subprocess.run([sys.executable, HOOK], input=json.dumps(event), capture_output=True, text=True, env=self.env, timeout=60)
        self.assertEqual(done.returncode, 0)
        return json.loads(done.stdout) if done.stdout.strip() else None

    def talk(self):
        with open(os.path.join(self.data, "feeds", "claude-code.json"), encoding="utf-8") as handle:
            return next(c for c in json.load(handle)["conversations"] if c["id"] == KEY)

    def call(self, method, name, body=None, token=None):
        code, _, data, _ = self.control.handle(method, name, b"" if body is None else json.dumps(body).encode(), self.control.token if token is None else token)
        return code, json.loads(data)

    def until(self, check, seconds=15):
        end = time.time() + seconds
        while time.time() < end:
            got = check()
            if got:
                return got
            time.sleep(0.1)
        self.fail("it never happened")

    def keep_watching(self):
        """Someone is using the building: its page says `here` every few seconds."""
        stop = threading.Event()

        def watch():
            while not stop.is_set():
                self.box.watch()
                stop.wait(1)
        threading.Thread(target=watch, daemon=True).start()
        self.addCleanup(stop.set)

    # ---------- off, and the page's token ----------

    def test_nothing_happens_while_it_is_off(self):
        self.assertIsNone(self.hook(hook_event_name="UserPromptSubmit", prompt="Fix the bookmark"))
        self.assertIsNone(self.hook(hook_event_name="PostToolUse", tool_name="Read", tool_input={}))
        began = time.time()
        self.assertIsNone(self.hook(hook_event_name="PermissionRequest", tool_name="Bash", tool_input={"command": "npm test"}))
        self.assertLess(time.time() - began, 5)  # with the building closed, Claude Code asks at once
        self.assertFalse(os.path.exists(os.path.join(self.data, "control")))
        self.assertTrue(self.talk()["check"])  # the building still shows it waiting for you

    def test_only_with_the_page_token(self):
        code, given = self.call("GET", "token", token="")
        self.assertEqual((code, given["on"], given["token"]), (200, True, self.control.token))
        self.assertEqual(self.call("GET", "state", token="")[0], 403)
        self.assertEqual(self.call("GET", "state", token="a guess")[0], 403)
        self.assertEqual(self.call("POST", "stop", {"key": KEY}, token="a guess")[0], 403)
        code, state = self.call("GET", "state")
        self.assertEqual((code, state["asks"], state["runs"]), (200, [], []))
        self.assertFalse(self.box.watched())  # a page left open on its own isn't someone to answer
        self.assertEqual(self.call("GET", "here", token="a guess")[0], 403)
        self.assertEqual(self.call("GET", "here")[0], 200)
        self.assertTrue(self.box.watched())
        self.assertEqual(state["projects"], [{"project": "Lantern", "label": "Lantern", "floor": "lantern"}])
        self.assertNotIn(self.lantern, json.dumps(state))  # no folders in what the page is given

    # ---------- messages ----------

    def test_a_message_reaches_claude_at_its_next_step(self):
        self.hook(hook_event_name="UserPromptSubmit", prompt="Fix the bookmark")
        code, sent = self.call("POST", "say", {"key": KEY, "text": "Use the blue button"})
        self.assertEqual((code, sent["sent"]), (200, "queued"))
        out = self.hook(hook_event_name="PostToolUse", tool_name="Read", tool_input={})
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "PostToolUse")
        self.assertIn('"Use the blue button"', out["hookSpecificOutput"]["additionalContext"])
        self.assertIsNone(self.hook(hook_event_name="PostToolUse", tool_name="Read", tool_input={}))  # handed over once
        self.assertEqual(self.talk()["heard"], sent["id"])
        self.assertIsNone(self.hook(hook_event_name="Stop", last_assistant_message="Done: the button is blue now. Anything else?"))
        talk = self.talk()
        self.assertEqual((talk["answered"], talk["says"]["now"]), (sent["id"], "Done: the button is blue now. Anything else?"))
        self.assertNotIn("heard", talk)

    def test_a_message_keeps_it_going_instead_of_stopping(self):
        self.hook(hook_event_name="UserPromptSubmit", prompt="Fix the bookmark")
        code, sent = self.call("POST", "say", {"key": KEY, "text": "Also check the back button"})
        out = self.hook(hook_event_name="Stop", last_assistant_message="Fixed.")
        self.assertEqual(out["decision"], "block")
        self.assertIn('"Also check the back button"', out["reason"])
        self.assertTrue(self.talk()["working"])
        self.assertIsNone(self.hook(hook_event_name="Stop", last_assistant_message="The back button works too."))
        self.assertEqual(self.talk()["answered"], sent["id"])

    def test_messages_only_for_conversations_in_the_building(self):
        for key in ("cc-nobody", "../../etc", "", None, 7):
            self.assertEqual(self.call("POST", "say", {"key": key, "text": "hi"})[0], 400, key)
        self.hook(hook_event_name="UserPromptSubmit", prompt="Fix the bookmark")
        self.assertEqual(self.call("POST", "say", {"key": KEY, "text": "  "})[0], 400)
        self.assertEqual(self.call("POST", "say", {"key": KEY, "text": "x" * 3000})[0], 400)

    # ---------- stopping ----------

    def test_stop_at_its_next_step(self):
        self.hook(hook_event_name="UserPromptSubmit", prompt="Fix the bookmark")
        self.assertEqual(self.call("POST", "stop", {"key": KEY})[0], 200)
        out = self.hook(hook_event_name="PostToolUse", tool_name="Bash", tool_input={"command": "ls"})
        self.assertEqual(out["continue"], False)
        self.assertIn("Stopped", out["stopReason"])
        self.assertFalse(self.talk()["working"])
        self.assertIsNone(self.hook(hook_event_name="PostToolUse", tool_name="Bash", tool_input={}))  # once
        # A new message from you in Claude Code spends a request to stop that came too late.
        self.call("POST", "stop", {"key": KEY})
        self.assertIsNone(self.hook(hook_event_name="UserPromptSubmit", prompt="Carry on"))
        self.assertIsNone(self.hook(hook_event_name="PostToolUse", tool_name="Bash", tool_input={}))

    # ---------- permissions ----------

    def ask_in_the_background(self, **given):
        event = {"hook_event_name": "PermissionRequest", "session_id": SESSION, "cwd": self.lantern, "tool_name": "Bash", "tool_input": {"command": "npm test"}, **given}
        proc = subprocess.Popen([sys.executable, HOOK], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, env=self.env)
        proc.stdin.write(json.dumps(event))
        proc.stdin.close()
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        ask = self.until(lambda: next(iter(self.call("GET", "state")[1]["asks"]), None))
        return proc, ask

    def decision(self, proc):
        out = proc.stdout.read()
        proc.stdout.close()
        self.assertEqual(proc.wait(timeout=20), 0)
        return json.loads(out)["hookSpecificOutput"]["decision"] if out.strip() else None

    def test_allow_answers_the_one_request_shown(self):
        self.hook(hook_event_name="UserPromptSubmit", prompt="Fix the bookmark")
        self.keep_watching()
        proc, ask = self.ask_in_the_background()
        self.assertEqual((ask["key"], ask["what"]), (KEY, "Bash: npm test"))
        self.assertEqual(self.talk()["says"]["needs"], "I'm waiting for your permission: Bash: npm test.")
        self.assertEqual(self.call("POST", "answer", {"id": ask["id"], "behavior": "always"})[0], 400)
        self.assertEqual(self.call("POST", "answer", {"id": "someotherrequest", "behavior": "allow"})[0], 400)
        self.assertEqual(self.call("POST", "answer", {"id": ask["id"], "behavior": "allow"})[0], 200)
        self.assertEqual(self.call("POST", "answer", {"id": ask["id"], "behavior": "deny"})[0], 400)  # one answer
        self.assertEqual(self.decision(proc), {"behavior": "allow"})  # this once: no rule for later
        self.assertEqual(self.call("GET", "state")[1]["asks"], [])

    def test_deny_and_stop(self):
        self.hook(hook_event_name="UserPromptSubmit", prompt="Fix the bookmark")
        self.keep_watching()
        proc, ask = self.ask_in_the_background()
        self.call("POST", "answer", {"id": ask["id"], "behavior": "deny"})
        self.assertEqual(self.decision(proc)["behavior"], "deny")
        proc, ask = self.ask_in_the_background(tool_input={"command": "rm -rf build"})
        self.call("POST", "stop", {"key": KEY})
        decision = self.decision(proc)
        self.assertEqual((decision["behavior"], decision["interrupt"]), ("deny", True))

    def test_no_answer_means_claude_code_asks(self):
        self.hook(hook_event_name="UserPromptSubmit", prompt="Fix the bookmark")
        self.keep_watching()
        self.env["ARNHEIM_CONTROL_WAIT"] = "5"
        began = time.time()
        proc, _ = self.ask_in_the_background()
        self.assertIsNone(self.decision(proc))
        self.assertLess(time.time() - began, 15)
        self.assertEqual(self.call("GET", "state")[1]["asks"], [])

    # ---------- agents started from the building ----------

    def run_of(self, key):
        return next((r for r in self.call("GET", "state")[1]["runs"] if r["key"] == key), None)

    def test_start_then_talk_to_it(self):
        code, started = self.call("POST", "start", {"project": "Lantern", "text": "fix the login page"})
        self.assertEqual(code, 200)
        key = started["key"]
        run = self.until(lambda: (self.run_of(key) or {}).get("state") == "done" and self.run_of(key))
        sid = self.control.runs[key]["sid"]
        self.assertEqual(key, "cc-" + sid.replace("-", "")[:12])  # the key the hook gives the same conversation
        self.assertEqual(run["title"], "Fix the login page")  # as a title; Claude Code is given the words as said
        self.assertEqual(run["said"], f"started {sid} in {self.lantern}: fix the login page")
        code, sent = self.call("POST", "say", {"key": key, "text": "And the logout page"})
        self.assertEqual((code, sent["sent"]), (200, "resumed"))
        run = self.until(lambda: (self.run_of(key) or {}).get("answered") == sent["id"] and self.run_of(key))
        self.assertEqual(run["said"], f"resumed {sid} in {self.lantern}: And the logout page")
        self.assertEqual(self.call("POST", "start", {"project": "Studio", "text": "Hi"})[0], 400)  # no folder
        self.assertEqual(self.call("POST", "start", {"project": "Elsewhere", "text": "Hi"})[0], 400)

    def test_one_started_here_stays_when_its_turn_ends(self):
        code, started = self.call("POST", "start", {"project": "Lantern", "text": "Fix the login page"})
        key = started["key"]
        self.until(lambda: (self.run_of(key) or {}).get("state") == "done")
        sid = self.control.runs[key]["sid"]
        self.hook(hook_event_name="UserPromptSubmit", session_id=sid, prompt="Fix the login page")
        self.hook(hook_event_name="SessionEnd", session_id=sid)
        with open(os.path.join(self.data, "feeds", "claude-code.json"), encoding="utf-8") as handle:
            talk = next(c for c in json.load(handle)["conversations"] if c["id"] == key)
        self.assertFalse(talk["working"])
        self.hook(hook_event_name="UserPromptSubmit", prompt="Fix the bookmark")  # one from a terminal
        self.hook(hook_event_name="SessionEnd")
        with open(os.path.join(self.data, "feeds", "claude-code.json"), encoding="utf-8") as handle:
            self.assertEqual([c["id"] for c in json.load(handle)["conversations"]], [key])

    def test_stop_one_started_here(self):
        code, started = self.call("POST", "start", {"project": "Lantern", "text": "wait a while"})
        key = started["key"]
        self.until(lambda: self.control.alive(self.control.runs[key]))
        self.assertEqual(self.call("POST", "stop", {"key": key})[0], 200)
        self.until(lambda: (self.run_of(key) or {}).get("state") == "stopped", seconds=12)


class WordsTest(unittest.TestCase):
    def test_what_a_permission_is_for(self):
        self.assertEqual(control.describe("Bash", {"command": "npm test"}), "Bash: npm test")
        self.assertEqual(control.describe("Edit", {"file_path": "/x/app.js", "old_string": "a"}), "Edit: /x/app.js")
        self.assertEqual(control.describe("WebFetch", {"url": "https://example.com", "prompt": "read"}), "WebFetch: https://example.com")
        self.assertEqual(control.describe("Odd", {}), "Odd")
        self.assertLessEqual(len(control.describe("Bash", {"command": "x" * 900})), 300)

    def test_what_claude_is_handed(self):
        one = control.message([{"text": "Use the blue button"}])
        self.assertIn('"Use the blue button"', one)
        two = control.message([{"text": "a"}, {"text": "b"}], stopping=True)
        self.assertTrue(two.startswith("Before you stop"))
        self.assertIn('(1) "a" (2) "b"', two)


if __name__ == "__main__":
    unittest.main()
