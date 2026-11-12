"""A budget per floor, with a brake (connect/budget.py and the hook): what each conversation spends
each day, counted once per reply from its transcript; a floor's agents stopped once when they pass its
budget, and asked about; and every agent paused from the building until it resumes them.

Each test makes a company of its own in a temporary folder (ARNHEIM_DATA), and transcripts of its own,
so your data/ and Claude Code's files are never touched. Run from the repository's folder:
python3 -m unittest discover tests
"""
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(ROOT, "connect", "claude_code.py")
sys.path.insert(0, os.path.join(ROOT, "connect"))
import budget  # noqa: E402  (after the path is set)
import control  # noqa: E402

NOW = datetime.datetime.now(datetime.timezone.utc)
TODAY = budget.local_day()


def reply(mid, n_in, n_cache, n_out, read=5000, when=NOW, parts=2):
    """A reply as Claude Code logs it: one line per part, each with the whole reply's usage."""
    usage = {"input_tokens": n_in, "cache_creation_input_tokens": n_cache, "cache_read_input_tokens": read, "output_tokens": n_out}
    stamp = when.isoformat().replace("+00:00", "Z")
    return "".join(json.dumps({"type": "assistant", "timestamp": stamp, "message": {"id": mid, "usage": usage, "content": [{"type": "text"}]}}) + "\n"
                   for _ in range(parts))


class CountTest(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.path = os.path.join(self.base, "talk.jsonl")

    def tearDown(self):
        shutil.rmtree(self.base)

    def write(self, text, mode="a"):
        with open(self.path, mode, encoding="utf-8") as handle:
            handle.write(text)

    def test_each_reply_once_by_its_day(self):
        yesterday = NOW - datetime.timedelta(days=1, hours=1)
        self.write(json.dumps({"type": "user", "message": {"content": "hi"}}) + "\n" + reply("a", 10, 100, 50, parts=3)
                   + reply("b", 1, 2, 3, when=yesterday) + "not json\n" + '{"type": "assistant", "message": {"usage": "odd"}}\n')
        spent, read = budget.new_tokens(self.path, {})
        self.assertEqual(spent, {TODAY: 160, budget.local_day(yesterday.isoformat()): 6})  # cache reads left out
        self.assertEqual(read["at"], os.path.getsize(self.path))

        self.write(reply("c", 0, 0, 7, parts=1)[:-30])  # a line still being written
        spent, again = budget.new_tokens(self.path, read)
        self.assertEqual((spent, again["at"]), ({}, read["at"]))
        self.write(reply("c", 0, 0, 7), mode="w")  # (the file as it ends up, from the start)
        spent, _ = budget.new_tokens(self.path, {"path": self.path, "at": 0})
        self.assertEqual(spent, {TODAY: 7})

    def test_a_missing_or_new_file(self):
        self.assertEqual(budget.new_tokens(os.path.join(self.base, "none.jsonl"), {}), ({}, {}))
        self.write(reply("a", 1, 1, 1))
        spent, read = budget.new_tokens(self.path, {"path": self.path, "at": 10**9})  # shorter than before: read afresh
        self.assertEqual(spent, {TODAY: 3})

    def test_in_words(self):
        self.assertEqual([budget.tokens(n) for n in (900, 12_400, 2_000_000, 1_250_000)], ["900", "12 thousand", "2 million", "1.2 million"])


class BrakeTest(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.data = os.path.join(self.base, "data")
        self.lantern = os.path.realpath(os.path.join(self.base, "code", "lantern"))
        self.outside = os.path.realpath(os.path.join(self.base, "code", "outside"))
        for folder in (self.data, self.lantern, self.outside):
            os.makedirs(folder)
        with open(os.path.join(self.data, "company.json"), "w", encoding="utf-8") as handle:
            json.dump({"company": "Example Studio", "feeds": ["feeds/claude-code.json"],
                       "floors": [{"id": "lantern", "label": "Lantern", "folder": self.lantern, "budget": 1000}]}, handle)
        self.env = dict(os.environ, ARNHEIM_DATA=self.data)
        self.transcript = os.path.join(self.base, "transcript.jsonl")
        open(self.transcript, "w").close()
        self.box = control.Box(self.data)

    def tearDown(self):
        shutil.rmtree(self.base)

    def spend(self, mid, n):
        with open(self.transcript, "a", encoding="utf-8") as handle:
            handle.write(reply(mid, 0, 0, n))

    def hook(self, **event):
        event.setdefault("session_id", "abc123def456-7890")
        event.setdefault("cwd", self.lantern)
        event.setdefault("transcript_path", self.transcript)
        event.setdefault("hook_event_name", "PostToolUse")
        event.setdefault("tool_name", "Bash")
        done = subprocess.run([sys.executable, HOOK], input=json.dumps(event), capture_output=True, text=True, env=self.env, timeout=20)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout) if done.stdout else None

    def feed(self):
        with open(os.path.join(self.data, "feeds", "claude-code.json"), encoding="utf-8") as handle:
            return json.load(handle)

    def test_the_brake_once_then_let_them_go_on(self):
        self.spend("a", 600)
        self.assertIsNone(self.hook())
        self.assertEqual(self.feed()["conversations"][0]["spent"], {"day": TODAY, "tokens": 600})

        self.spend("b", 500)  # 1,100 of 1,000
        out = self.hook()
        self.assertEqual(out["continue"], False)
        self.assertIn("Lantern's agents have used today's budget of 1 thousand new tokens", out["stopReason"])
        feed = self.feed()
        [ask] = [t for t in feed["tasks"] if t["id"] == "budget-lantern"]
        self.assertEqual((ask["status"], ask["budget"], ask["note"]), ("needs_you", "Lantern", "1 thousand new tokens of 1 thousand. Let them go on, or leave them until tomorrow."))
        self.assertEqual(feed["conversations"][0]["check"], True)

        self.assertIsNone(self.hook())  # asked once: if you carry on in Claude Code yourself, it lets you
        building = control.Control(self.data, claude=[sys.executable, "-c", "pass"])
        self.assertEqual(building.allow_more("Lantern"), {"ok": True, "project": "Lantern", "times": 2})
        self.assertEqual(building.state()["allowed"], {"Lantern": 1})
        self.spend("c", 100)
        self.assertIsNone(self.hook())  # 1,200 of 2,000
        self.assertEqual([t for t in self.feed()["tasks"] if t["id"] == "budget-lantern"], [])
        self.spend("d", 900)
        self.assertEqual(self.hook()["continue"], False)  # 2,100 of 2,000: asked again
        with self.assertRaises(control.Refused):
            building.allow_more("Studio")

    def test_ended_conversations_still_count(self):
        self.spend("a", 900)
        self.assertIsNone(self.hook())
        self.assertIsNone(self.hook(hook_event_name="SessionEnd"))  # it ends, and leaves the feed
        self.assertEqual(self.feed()["conversations"], [])
        self.assertEqual(self.feed()["ended"]["talks"]["cc-abc123def456"]["tokens"], 900)
        other = os.path.join(self.base, "other.jsonl")
        with open(other, "w", encoding="utf-8") as handle:
            handle.write(reply("b", 0, 0, 900))
        out = self.hook(session_id="fff999eee888-1", transcript_path=other)  # 1,800 of 1,000 today
        self.assertEqual(out["continue"], False)
        [ask] = [t for t in self.feed()["tasks"] if t["id"] == "budget-lantern"]
        self.assertTrue(ask["note"].startswith("2 thousand new tokens of 1 thousand"))

        self.spend("c", 50)  # the first comes back: its 900 go on from where they were, never counted twice
        self.hook(hook_event_name="SessionStart", source="resume", tool_name=None)
        self.hook()
        feed = self.feed()
        mine = next(c for c in feed["conversations"] if c["id"] == "cc-abc123def456")
        self.assertEqual(mine["spent"], {"day": TODAY, "tokens": 950})
        self.assertNotIn("cc-abc123def456", feed["ended"]["talks"])
        self.assertEqual(budget.spent_today(feed["conversations"], "Lantern", TODAY, feed["ended"]), 1850)

    def test_never_instead_of_your_message(self):
        self.spend("a", 5000)
        self.box.post("cc-abc123def456", "Wrap up now")
        out = self.hook()
        self.assertIn("Wrap up now", out["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(self.hook()["continue"], False)  # the step after

    def test_pause_everyone_and_resume(self):
        self.box.pause()
        out = self.hook()
        self.assertEqual(out["continue"], False)
        self.assertIn("every agent is paused", out["stopReason"])
        self.assertIsNone(self.hook())  # stopped once
        out = self.hook(hook_event_name="UserPromptSubmit", prompt="Go on")
        self.assertEqual(out["decision"], "block")
        self.assertFalse(self.feed()["conversations"][0]["working"])
        self.assertIsNone(self.hook(hook_event_name="UserPromptSubmit", prompt="Hi", cwd=self.outside, session_id="other1"))  # not this company's
        self.box.resume()
        self.assertIsNone(self.hook(hook_event_name="UserPromptSubmit", prompt="Go on"))
        self.assertTrue(self.feed()["conversations"][0]["working"])

    def test_no_budget_no_brake(self):
        with open(os.path.join(self.data, "company.json"), "w", encoding="utf-8") as handle:
            json.dump({"company": "Example Studio", "floors": [{"id": "lantern", "label": "Lantern", "folder": self.lantern}]}, handle)
        self.spend("a", 10**7)
        self.assertIsNone(self.hook())
        self.assertEqual(self.feed()["conversations"][0]["spent"]["tokens"], 10**7)

    def test_the_page_asks_through_control(self):
        building = control.Control(self.data, claude=[sys.executable, "-c", "pass"])

        def post(name, body=None):
            code, _, data, _ = building.handle("POST", name, json.dumps(body or {}).encode(), building.token)
            return code, json.loads(data)
        self.assertEqual(post("pause"), (200, {"ok": True, "paused": True}))
        self.assertIsInstance(building.state()["paused"], float)
        self.assertEqual(post("resume"), (200, {"ok": True, "paused": False}))
        self.assertIsNone(building.state()["paused"])
        self.assertEqual(post("allow_more", {"project": "Nowhere"})[0], 400)


if __name__ == "__main__":
    unittest.main()
