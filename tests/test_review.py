"""The review line (connect/review.py and the hook): on a floor that asks for one, a turn that changed
files is held while the floor's check and a reader look at it; work that isn't ready goes back to the
agent with the reason, and after the times allowed it reaches you anyway, marked as failed.

Each test makes a company of its own in a temporary folder (ARNHEIM_DATA), with a git folder for its
floor, and a stand-in for Claude Code's `claude` command (ARNHEIM_CLAUDE) that answers as told and
notes what it was asked, so no real Claude Code runs and your data/ is never touched.
Run from the repository's folder: python3 -m unittest discover tests
"""
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(ROOT, "connect", "claude_code.py")
sys.path.insert(0, os.path.join(ROOT, "connect"))
import budget  # noqa: E402  (after the path is set)
import review  # noqa: E402

GIT = shutil.which("git")

# Stands in for `claude -p`: notes its arguments, a little of its environment and what it was asked, then
# prints the answer in answer.json beside it (Claude Code's --output-format json), or exits as told.
READER = r"""
import json, os, sys
here = os.path.dirname(os.path.abspath(__file__))
asked = sys.stdin.read()
with open(os.path.join(here, "asked.jsonl"), "a") as out:
    out.write(json.dumps({"args": sys.argv[1:], "asked": asked, "cwd": os.getcwd(),
                          "reviewer": os.environ.get("ARNHEIM_REVIEWER"), "nested": os.environ.get("CLAUDECODE")}) + "\n")
with open(os.path.join(here, "answer.json")) as given:
    answer = json.load(given)
print(json.dumps(answer.get("print", answer)))
sys.exit(answer.get("exit", 0))
"""

PASS = {"result": "It does what was asked, and the change is small and clear.\nVERDICT: PASS",
        "usage": {"input_tokens": 100, "cache_creation_input_tokens": 50, "cache_read_input_tokens": 9000, "output_tokens": 25}}
BACK = {"result": "The settings page still shows the old colour.\n\n**VERDICT: SEND BACK: The settings page still uses the old red.**",
        "usage": {"input_tokens": 10, "output_tokens": 5}}


@unittest.skipUnless(GIT, "git isn't installed")
class ReviewLineTest(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.data = os.path.join(self.base, "data")
        self.lantern = os.path.realpath(os.path.join(self.base, "code", "lantern"))
        self.tools = os.path.join(self.base, "tools")
        for folder in (self.data, self.lantern, self.tools):
            os.makedirs(folder)
        git = lambda *args: subprocess.run([GIT, "-C", self.lantern, *args], check=True, capture_output=True)
        git("init", "-q")
        self.write("app.js", "const colour = 'red';\n")
        git("add", "app.js")
        git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-q", "-m", "First")
        self.company(review=True)
        with open(os.path.join(self.tools, "reader.py"), "w", encoding="utf-8") as handle:
            handle.write(READER)
        self.answer(PASS)
        self.env = dict(os.environ, ARNHEIM_DATA=self.data, CLAUDECODE="1",
                        ARNHEIM_CLAUDE=f"{shlex.quote(sys.executable)} {shlex.quote(os.path.join(self.tools, 'reader.py'))}")
        self.env.pop("ARNHEIM_REVIEWER", None)

    def tearDown(self):
        shutil.rmtree(self.base)

    def company(self, **floor):
        with open(os.path.join(self.data, "company.json"), "w", encoding="utf-8") as handle:
            json.dump({"company": "Example Studio", "feeds": ["feeds/claude-code.json"],
                       "floors": [{"id": "lantern", "label": "Lantern", "folder": self.lantern, **floor}]}, handle)

    def answer(self, answer):
        with open(os.path.join(self.tools, "answer.json"), "w", encoding="utf-8") as handle:
            json.dump(answer, handle)

    def write(self, name, text):
        with open(os.path.join(self.lantern, name), "w", encoding="utf-8") as handle:
            handle.write(text)

    def asked(self):
        try:
            with open(os.path.join(self.tools, "asked.jsonl"), encoding="utf-8") as handle:
                return [json.loads(row) for row in handle]
        except OSError:
            return []

    def hook(self, env=None, **event):
        event.setdefault("session_id", "abc123def456-7890")
        event.setdefault("cwd", self.lantern)
        done = subprocess.run([sys.executable, HOOK], input=json.dumps(event), capture_output=True, text=True, env=env or self.env, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout) if done.stdout else None

    def change(self, name, text):
        self.write(name, text)
        self.assertIsNone(self.hook(hook_event_name="PostToolUse", tool_name="Edit", tool_input={"file_path": os.path.join(self.lantern, name)}))

    def finish(self, said="I made it blue."):
        return self.hook(hook_event_name="Stop", last_assistant_message=said)

    def talk(self):
        with open(os.path.join(self.data, "feeds", "claude-code.json"), encoding="utf-8") as handle:
            return json.load(handle)["conversations"][0]

    def test_work_that_passes_reaches_you(self):
        self.hook(hook_event_name="UserPromptSubmit", prompt="Make the button blue")
        self.change("app.js", "const colour = 'blue';\n")
        self.write("notes.md", "Unrelated, and not changed by the agent.\n")
        self.change("button.css", ".button { color: blue; }\n")
        self.assertIsNone(self.finish())
        talk = self.talk()
        self.assertEqual((talk["working"], talk["check"], talk["says"]["now"]), (False, True, "I made it blue."))
        self.assertEqual({k: talk["review"][k] for k in ("state", "by", "said", "times", "most")},
                         {"state": "passed", "by": "The reader", "said": "It does what was asked, and the change is small and clear.", "times": 0, "most": 2})
        self.assertEqual(talk["spent"], {"day": budget.local_day(), "tokens": 175})  # the reader's new tokens count towards the floor

        [call] = self.asked()
        self.assertEqual(call["cwd"], self.lantern)
        self.assertEqual((call["reviewer"], call["nested"]), ("1", None))  # left alone by the hook, and not a Claude Code inside this one
        args = call["args"]
        self.assertEqual(args[args.index("--tools") + 1], "Read,Grep,Glob")
        self.assertEqual(args[args.index("--permission-mode") + 1], "dontAsk")
        self.assertIn("--no-session-persistence", args)
        self.assertIn("--strict-mcp-config", args)
        self.assertIn('They asked it: "Make the button blue".', call["asked"])
        self.assertIn('It says it did this: "I made it blue."', call["asked"])
        self.assertIn("-const colour = 'red';\n+const colour = 'blue';", call["asked"])
        self.assertIn("A new file, button.css:\n.button { color: blue; }", call["asked"])
        self.assertNotIn("Unrelated", call["asked"])  # only what the agent changed

        self.assertIsNone(self.finish("Anything else?"))  # nothing changed since: not reviewed again
        self.assertEqual(len(self.asked()), 1)

    def test_sent_back_with_the_reason_then_reaches_you_anyway(self):
        self.answer(BACK)
        self.hook(hook_event_name="UserPromptSubmit", prompt="Make the button blue")
        self.change("app.js", "const colour = 'blue';\n")
        out = self.finish()
        self.assertEqual(out["decision"], "block")
        self.assertIn("sent your work back (time 1 of 2", out["reason"])
        self.assertIn("The settings page still uses the old red.", out["reason"])
        talk = self.talk()
        self.assertEqual((talk["working"], talk["check"], talk["review"]["state"], talk["review"]["times"]), (True, False, "sent back", 1))
        self.assertEqual(talk["says"]["now"], "The review line sent my work back, so I'm fixing it: The settings page still uses the old red.")

        self.change("settings.js", "const colour = 'blue';\n")
        out = self.finish()
        self.assertIn("time 2 of 2", out["reason"])
        self.assertIn("It was sent back 1 time already", self.asked()[-1]["asked"])

        self.change("settings.js", "const colour = 'navy';\n")
        self.assertIsNone(self.finish("Done now."))  # sent back as often as allowed: it reaches you, marked
        talk = self.talk()
        self.assertEqual((talk["working"], talk["check"], talk["says"]["now"]), (False, True, "Done now."))
        self.assertEqual((talk["review"]["state"], talk["review"]["times"]), ("failed", 2))
        with open(os.path.join(self.data, "feeds", "history", budget.local_day() + ".json"), encoding="utf-8") as handle:
            said = [m["what"] for m in json.load(handle)["moments"]]
        self.assertIn("The review line sent it back: The settings page still uses the old red.", said)
        self.assertIn("It reached you after failing the review line: The settings page still uses the old red.", said)

        self.hook(hook_event_name="UserPromptSubmit", prompt="Try once more")  # a new piece of work starts afresh
        self.assertNotIn("review", self.talk())

    def test_the_check_goes_first(self):
        self.company(review={"times": 1}, check=[sys.executable, "-c", "print('2 tests failed'); raise SystemExit(1)"])
        self.change("app.js", "const colour = 'blue';\n")
        out = self.finish()
        self.assertIn("Its check failed. Its last lines:\n2 tests failed", out["reason"])
        self.assertEqual(self.asked(), [])  # the reader isn't asked about work that fails its check
        talk = self.talk()
        self.assertEqual((talk["proof"]["state"], talk["review"]["by"]), ("failed", "Its check"))

        self.company(review={"times": 1}, check={"run": [sys.executable, "-c", "print('all passed')"], "label": "The tests"})
        self.change("app.js", "const colour = 'navy';\n")
        self.assertIsNone(self.finish())
        talk = self.talk()
        self.assertEqual((talk["proof"]["state"], talk["proof"]["check"], talk["review"]["state"], talk["review"]["times"]), ("passed", "The tests", "passed", 1))
        self.assertEqual(len(self.asked()), 1)

    def test_check_only(self):
        self.company(review={"read": False}, check={"run": [sys.executable, "-c", "pass"], "label": "The tests"})
        self.change("app.js", "const colour = 'blue';\n")
        self.assertIsNone(self.finish())
        self.assertEqual((self.talk()["review"]["state"], self.talk()["review"]["by"]), ("passed", "The tests"))
        self.assertEqual(self.asked(), [])

    def test_no_line_holds_nothing(self):
        self.company()
        self.change("app.js", "const colour = 'blue';\n")
        self.assertIsNone(self.finish())
        self.assertNotIn("review", self.talk())
        self.assertEqual(self.asked(), [])

    def test_a_reader_in_trouble_lets_the_work_through(self):
        for answer in ({"result": "I looked at it."}, {"print": "Not logged in", "exit": 1}):
            self.answer(answer)
            self.change("app.js", f"const colour = '{len(self.asked())}';\n")
            self.assertIsNone(self.finish())
            talk = self.talk()
            self.assertEqual((talk["review"]["state"], talk["working"], talk["check"]), ("error", False, True))
            self.assertIn("The reader gave no verdict", talk["review"]["said"])

    def test_outside_git(self):
        shutil.rmtree(os.path.join(self.lantern, ".git"))
        self.change("app.js", "const colour = 'blue';\n")
        self.assertIsNone(self.finish())
        self.assertIn("This folder isn't kept in git, so read the changed files themselves: app.js.", self.asked()[0]["asked"])

    def test_the_reader_is_left_alone(self):
        env = dict(self.env, ARNHEIM_REVIEWER="1")
        self.assertIsNone(self.hook(env=env, hook_event_name="UserPromptSubmit", prompt="Review this"))
        self.assertFalse(os.path.exists(os.path.join(self.data, "feeds", "claude-code.json")))


class WordsTest(unittest.TestCase):
    def test_a_floor_says_what_it_wants(self):
        self.assertIsNone(review.review_of({}))
        self.assertIsNone(review.review_of({"review": False}))
        self.assertEqual(review.review_of({"review": True}), {"read": True, "times": 2, "timeout": 300})
        self.assertEqual(review.review_of({"review": {"read": False, "times": 9, "timeout": "x"}}), {"read": False, "times": 5, "timeout": 300})

    def test_the_verdict(self):
        found = lambda text: review.VERDICT.findall(text)
        self.assertEqual(found("Fine.\nVERDICT: PASS"), [("PASS", "")])
        self.assertEqual(found("No.\n**Verdict: send back:** the tests are missing."), [("send back", "the tests are missing.")])
        self.assertEqual(found("I'd say VERDICT: PASS in the end"), [])  # only a line of its own counts


if __name__ == "__main__":
    unittest.main()
