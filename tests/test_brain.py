"""The receptionist's and the assistant's brain: connect/brain.py, and serve.py's /brain/. A stand-in
for Claude Code's `claude` command answers for Claude, and writes down how it was started and
what it was told, in a temporary folder of its own.

Run from the repository's folder: python3 -m unittest discover tests
"""
import http.client
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "connect"))

import brain  # noqa: E402  (after the path is set)
import serve  # noqa: E402

# Stands in for `claude -p --input-format stream-json --output-format stream-json
# --include-partial-messages`: reads one JSON message a line, and answers each a word at a time,
# with how many it has had ("Turn 2: you said ..."). Words with "slowly" pause after the first
# piece, "hang" never answer, "fail" get Claude Code's error, and "crash" stop it.
FAKE = r'''
import json, os, sys, time
here = os.path.dirname(os.path.abspath(__file__))

def note(**row):
    with open(os.path.join(here, "record.jsonl"), "a", encoding="utf-8") as out:
        out.write(json.dumps({"pid": os.getpid(), **row}) + "\n")

note(args=sys.argv[1:], cwd=os.getcwd(), env={k: v for k, v in os.environ.items() if k.startswith("CLAUDE")})
print(json.dumps({"type": "system", "subtype": "init"}), flush=True)
turn = 0
for raw in sys.stdin:
    text = json.loads(raw)["message"]["content"][0]["text"]
    turn += 1
    note(turn=turn, text=text)
    words = text.rsplit("The person says: ", 1)[-1]
    if "crash" in words:
        print("fake claude: crashed on purpose", file=sys.stderr, flush=True)
        sys.exit(3)
    if "hang" in words:
        time.sleep(60)
    if "fail" in words:
        print(json.dumps({"type": "result", "subtype": "success", "is_error": True, "result": "Not logged in · Please run /login"}), flush=True)
        continue
    answer = "Ready." if text.endswith("Reply with just: Ready.") else f"Turn {turn}: you said {words}"
    for i, piece in enumerate(answer.split(" ")):
        delta = {"type": "text_delta", "text": piece if i == 0 else " " + piece}
        print(json.dumps({"type": "stream_event", "event": {"type": "content_block_delta", "index": 0, "delta": delta}}), flush=True)
        if "slowly" in words and i == 0:
            time.sleep(1.5)
    print(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": answer}]}}), flush=True)
    print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": answer}), flush=True)
'''

FACTS = [
    ["Company", "Example Studio, a company that is made up."],
    ["Floor: Lantern", "Lantern: a reading app. Tasks: \"Fix the login page\" (needs you)."],
    ["Needs you", "1 thing needs you: \"Fix the login page\", on Lantern."],
]


class Fake:
    """A temporary folder with the stand-in claude in it, and what it wrote down."""

    def __init__(self):
        self.base = tempfile.mkdtemp()
        self.path = os.path.join(self.base, "fake_claude.py")
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write(FAKE)

    def rows(self):
        try:
            with open(os.path.join(self.base, "record.jsonl"), encoding="utf-8") as handle:
                return [json.loads(raw) for raw in handle]
        except OSError:
            return []

    def starts(self):
        return [r for r in self.rows() if "args" in r]

    def said(self):
        return [r for r in self.rows() if "turn" in r]

    def remove(self):
        shutil.rmtree(self.base, ignore_errors=True)


def gone(pid, seconds=8):
    """Whether that process has ended (and been reaped) within the time."""
    end = time.time() + seconds
    while time.time() < end:
        try:
            os.kill(pid, 0)
        except OSError:
            return True
        time.sleep(0.05)
    return False


class BrainTest(unittest.TestCase):
    def setUp(self):
        self.fake = Fake()
        self.addCleanup(self.fake.remove)
        self.brain = self.make()

    def make(self, **given):
        made = brain.Brain(claude=given.pop("claude", [sys.executable, self.fake.path]), model=given.pop("model", "haiku"), **{"wait": 20, **given})
        self.addCleanup(made.close)
        return made

    def call(self, method, name, body=None, token=None, to=None):
        to = to or self.brain
        code, kind, data, _ = to.handle(method, name, b"" if body is None else json.dumps(body).encode(), to.token if token is None else token)
        if not isinstance(data, bytes):
            return code, [json.loads(raw) for raw in data]
        return code, json.loads(data)

    def ask(self, text, facts=FACTS, who="receptionist", name="Iris", company="Example Studio", to=None):
        code, lines = self.call("POST", "ask", {"who": who, "name": name, "company": company, "facts": facts, "text": text}, to=to)
        self.assertEqual(code, 200, lines)
        return lines

    def answer(self, lines):
        self.assertEqual(lines[-1], {"done": True}, lines)
        return "".join(x["text"] for x in lines[:-1])

    # ---------- the page's token ----------

    def test_only_with_the_page_token(self):
        code, status = self.call("GET", "status", token="")
        self.assertEqual((code, status["on"], status["model"], status["token"]), (200, True, "haiku", self.brain.token))
        body = {"who": "receptionist", "facts": FACTS, "text": "Hello there"}
        for token in ("", "a guess", None):
            self.assertEqual(self.brain.handle("POST", "ask", json.dumps(body).encode(), token)[0], 403, token)
            self.assertEqual(self.brain.handle("POST", "prime", json.dumps(body).encode(), token)[0], 403, token)
        self.assertEqual(self.call("GET", "ask")[0], 405)
        self.assertEqual(self.call("POST", "status")[0], 405)
        self.assertEqual(self.call("POST", "think", body)[0], 404)
        self.assertEqual(self.fake.starts(), [])  # nothing refused ever started a claude

    def test_requests_that_make_no_sense(self):
        for body in ({"who": "boss", "text": "hi"}, {"who": "receptionist", "text": "  "}, {"who": "receptionist", "text": "x" * 3000},
                     {"who": "receptionist", "text": "hi", "facts": "all of them"}, {"who": "receptionist", "text": "hi", "facts": [["only a name"]]},
                     {"who": "receptionist", "text": "hi", "facts": [["Big", "x" * 200_000]]}):
            self.assertEqual(self.call("POST", "ask", body)[0], 400, body)
        self.assertEqual(self.brain.handle("POST", "ask", b"not json", self.brain.token)[0], 400)
        self.assertEqual(self.fake.starts(), [])

    # ---------- answers ----------

    def test_an_answer_comes_in_pieces(self):
        lines = self.ask("What's the capital of Japan?")
        self.assertGreater(len(lines), 3)
        self.assertTrue(all(set(x) == {"text"} for x in lines[:-1]))
        self.assertEqual(self.answer(lines), "Turn 1: you said What's the capital of Japan?")

    def test_facts_go_whole_once_then_only_what_changed(self):
        self.ask("What needs me?")
        self.ask("And after that?")
        changed = [FACTS[0], ["Floor: Lantern", "Lantern: a reading app. No open tasks."], ["Working now", "The Lantern agent is working."]]
        self.ask("What changed?", facts=changed)
        first, second, third = [r["text"] for r in self.fake.said()]
        self.assertTrue(first.startswith("The building's facts, as they stand now:"))
        for section, text in FACTS:
            self.assertIn(f"## {section}\n{text}", first)
        self.assertTrue(first.endswith("The person says: What needs me?"))
        self.assertEqual(second, "The person says: And after that?")  # nothing new to tell
        self.assertTrue(third.startswith("Changed since you last looked:"))
        self.assertIn("## Floor: Lantern\nLantern: a reading app. No open tasks.", third)
        self.assertIn("## Working now\nThe Lantern agent is working.", third)
        self.assertIn("## Needs you\n(No longer there.)", third)
        self.assertNotIn("## Company", third)  # unchanged, so not sent again

    def test_the_same_claude_answers_a_follow_up(self):
        self.assertEqual(self.answer(self.ask("What needs me?")), "Turn 1: you said What needs me?")
        self.assertEqual(self.answer(self.ask("Which floor is it on?")), "Turn 2: you said Which floor is it on?")
        self.assertEqual(len(self.fake.starts()), 1)
        self.assertEqual({r["pid"] for r in self.fake.said()}, {self.fake.starts()[0]["pid"]})

    def test_a_fresh_claude_after_one_stops(self):
        self.ask("What needs me?")
        pid = self.brain.running()["receptionist"]
        os.kill(pid, signal.SIGKILL)
        end = time.time() + 8
        while "receptionist" in self.brain.running() and time.time() < end:
            time.sleep(0.05)
        self.assertEqual(self.brain.running(), {})
        self.assertEqual(self.answer(self.ask("Are you there?")), "Turn 1: you said Are you there?")
        starts = self.fake.starts()
        self.assertEqual(len(starts), 2)
        self.assertNotEqual(starts[0]["pid"], starts[1]["pid"])
        self.assertTrue(self.fake.said()[-1]["text"].startswith("The building's facts"))  # a new claude is told everything
        # One that stops partway: the page hears why, and the next question starts afresh.
        lines = self.ask("Please crash now")
        self.assertEqual(len(lines), 1)
        self.assertIn("Claude Code stopped: fake claude: crashed on purpose", lines[0]["error"])
        self.assertEqual(self.answer(self.ask("Hello again")), "Turn 1: you said Hello again")
        self.assertEqual(len(self.fake.starts()), 3)

    def test_how_claude_is_started(self):
        with mock.patch.dict(os.environ, {"CLAUDECODE": "1", "CLAUDE_CODE_ENTRYPOINT": "cli", "CLAUDE_CONFIG_DIR": "/a/config/folder"}):
            self.ask("What needs me?")
        start = self.fake.starts()[0]
        args = start["args"]
        for flag, value in (("--model", "haiku"), ("--effort", "low"), ("--input-format", "stream-json"),
                            ("--output-format", "stream-json"), ("--tools", ""), ("--setting-sources", "")):
            self.assertEqual(args[args.index(flag) + 1], value, flag)
        for flag in ("-p", "--verbose", "--include-partial-messages", "--strict-mcp-config", "--no-session-persistence",
                     "--exclude-dynamic-system-prompt-sections"):
            self.assertIn(flag, args)
        persona = args[args.index("--system-prompt") + 1]
        self.assertTrue(persona.startswith("You are Iris, the receptionist of Example Studio, shown as a building in Arnheim"))
        self.assertIn("never invent people, numbers or work", persona)
        self.assertIn("you never merge, publish, deploy, run jobs, sign in, send messages or email, buy or pay", persona)
        # A plain, separate claude: none of Claude Code's own marks, but your settings' folder.
        self.assertEqual(start["env"], {"CLAUDE_CONFIG_DIR": "/a/config/folder"})
        # In an empty folder of its own, which goes when it does.
        folder = start["cwd"]
        self.assertNotEqual(os.path.realpath(folder), os.path.realpath(ROOT))
        self.assertTrue(os.path.basename(folder).startswith("arnheim-brain-"))
        self.assertEqual(os.listdir(folder), [])
        pid = start["pid"]
        self.brain.close()
        self.assertTrue(gone(pid))
        self.assertFalse(os.path.exists(folder))

    def test_each_person_has_their_own(self):
        self.ask("Hello", who="receptionist")
        self.ask("Hello", who="assistant", name="Wren")
        running = self.brain.running()
        self.assertNotEqual(running["receptionist"], running["assistant"])
        personas = [s["args"][s["args"].index("--system-prompt") + 1] for s in self.fake.starts()]
        self.assertTrue(personas[1].startswith("You are Wren, the assistant of Example Studio"))
        # Someone renamed in the company's files is someone new: a claude of their own.
        self.ask("Hello", who="assistant", name="Robin")
        self.assertTrue(gone(running["assistant"]))
        self.assertTrue(self.fake.starts()[-1]["args"][self.fake.starts()[-1]["args"].index("--system-prompt") + 1].startswith("You are Robin"))
        self.assertEqual(self.brain.running()["receptionist"], running["receptionist"])

    # ---------- priming ----------

    def test_priming_reads_the_facts_and_keeps_the_reply_to_itself(self):
        code, primed = self.call("POST", "prime", {"who": "receptionist", "name": "Iris", "company": "Example Studio", "facts": FACTS})
        self.assertEqual((code, primed), (200, {"ok": True, "primed": True}))
        self.assertEqual(self.call("POST", "prime", {"who": "receptionist", "name": "Iris", "company": "Example Studio", "facts": FACTS})[1],
                         {"ok": True, "primed": False})  # it knows them all already
        lines = self.ask("What needs me?")
        self.assertEqual(self.answer(lines), "Turn 2: you said What needs me?")  # "Ready." went to nobody
        first, second = [r["text"] for r in self.fake.said()]
        self.assertTrue(first.startswith("The building's facts") and first.endswith("\n\nReply with just: Ready."))
        self.assertEqual(second, "The person says: What needs me?")

    # ---------- trouble ----------

    def test_no_claude_is_a_clean_error(self):
        with mock.patch.dict(os.environ, {"ARNHEIM_CLAUDE": "/no/such/folder/claude"}):
            missing = brain.Brain()
        self.addCleanup(missing.close)
        lines = self.ask("What needs me?", to=missing)
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0]["error"].startswith("Claude Code didn't start ("), lines)
        self.assertIn("ARNHEIM_CLAUDE can name another", lines[0]["error"])
        code, primed = self.call("POST", "prime", {"who": "assistant", "facts": FACTS}, to=missing)
        self.assertEqual((code, primed["ok"]), (200, False))
        self.assertEqual(missing.running(), {})

    def test_claude_code_errors_and_slow_answers(self):
        lines = self.ask("Why does it fail?")
        self.assertEqual(lines, [{"error": "Claude Code said: Not logged in · Please run /login"}])
        self.assertEqual(self.brain.running(), {})  # a claude that went wrong is stopped
        slow = self.make(wait=2)
        began = time.time()
        lines = self.ask("Please hang on", to=slow)
        self.assertEqual(lines, [{"error": "Claude took too long to answer, so it was stopped."}])
        self.assertLess(time.time() - began, 10)
        self.assertTrue(gone(self.fake.starts()[-1]["pid"]))
        self.assertEqual(self.answer(self.ask("Better now?", to=slow)), "Turn 1: you said Better now?")

    def test_quiet_claudes_are_stopped(self):
        quiet = self.make(idle=1)
        self.ask("Hello", to=quiet)
        start = self.fake.starts()[-1]
        end = time.time() + 10
        while quiet.running() and time.time() < end:
            time.sleep(0.1)
        self.assertEqual(quiet.running(), {})
        self.assertTrue(gone(start["pid"]))
        self.assertFalse(os.path.exists(start["cwd"]))

    def test_the_model_is_yours_to_choose(self):
        with mock.patch.dict(os.environ, {"ARNHEIM_BRAIN_MODEL": "opus"}):
            chosen = brain.Brain(claude=[sys.executable, self.fake.path])
        self.addCleanup(chosen.close)
        self.assertEqual(chosen.model, "opus")
        with mock.patch.dict(os.environ, {"ARNHEIM_BRAIN_MODEL": ""}):
            plain = brain.Brain(claude=[sys.executable, self.fake.path])
        self.addCleanup(plain.close)
        self.assertEqual(plain.model, "sonnet")
        with self.assertRaises(ValueError):
            brain.Brain(model="--dangerously-skip-permissions")


class ServeBrainTest(unittest.TestCase):
    """serve.py's /brain/: off unless asked, and then only its own page on this computer, with the
    page's token."""

    def setUp(self):
        self.server = serve.Server(("127.0.0.1", 0), serve.Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.fake = Fake()
        self.addCleanup(self.fake.remove)
        self.own = f"http://127.0.0.1:{self.port}"

    def switch_on(self):
        self.server.brain = brain.Brain(claude=[sys.executable, self.fake.path], model="haiku", wait=20)
        self.addCleanup(self.server.brain.close)
        return self.server.brain

    def request(self, method, path, headers=None, body=None, host=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=20)
        self.addCleanup(conn.close)
        conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        conn.putheader("Host", host or f"127.0.0.1:{self.port}")
        for name, value in (headers or {}).items():
            conn.putheader(name, value)
        data = b"" if body is None else json.dumps(body).encode()
        conn.putheader("Content-Length", str(len(data)))
        conn.endheaders(data)
        return conn.getresponse()

    def test_off_by_default(self):
        reply = self.request("GET", "/brain/status")
        self.assertEqual((reply.status, json.loads(reply.read())), (200, {"on": False}))
        body = {"who": "receptionist", "text": "Hello"}
        self.assertEqual(self.request("POST", "/brain/ask", {"Origin": self.own}, body).status, 404)
        self.assertEqual(self.request("POST", "/brain/prime", {"Origin": self.own}, body).status, 404)
        self.assertEqual(self.fake.starts(), [])

    def test_only_its_own_page_with_its_token(self):
        on = self.switch_on()
        reply = self.request("GET", "/brain/status")
        status = json.loads(reply.read())
        self.assertEqual((reply.status, status["on"], status["token"]), (200, True, on.token))
        self.assertEqual(self.request("GET", "/brain/status", host=f"example.com:{self.port}").status, 403)
        body = {"who": "receptionist", "name": "Iris", "company": "Example Studio", "facts": FACTS, "text": "Hello"}
        for headers in ({"X-Arnheim-Brain": on.token},  # no Origin: not a page
                        {"X-Arnheim-Brain": on.token, "Origin": "http://example.com"},  # another site's page
                        {"X-Arnheim-Brain": on.token, "Origin": f"http://localhost:{self.port}"},
                        {"Origin": self.own}, {"Origin": self.own, "X-Arnheim-Brain": "a guess"}):
            self.assertEqual(self.request("POST", "/brain/ask", headers, body).status, 403, headers)
            self.assertEqual(self.request("POST", "/brain/prime", headers, body).status, 403, headers)
        self.assertEqual(self.request("POST", "/brain/ask", {"Origin": self.own, "X-Arnheim-Brain": on.token}, body,
                                      host=f"example.com:{self.port}").status, 403)
        self.assertEqual(self.fake.starts(), [])
        reply = self.request("POST", "/brain/ask", {"Origin": self.own, "X-Arnheim-Brain": on.token}, body)
        self.assertEqual((reply.status, reply.getheader("Content-Type")), (200, "application/x-ndjson; charset=utf-8"))
        lines = [json.loads(raw) for raw in reply.read().splitlines()]
        self.assertEqual("".join(x.get("text", "") for x in lines), "Turn 1: you said Hello")

    def test_an_answer_streams_as_it_comes(self):
        on = self.switch_on()
        body = {"who": "receptionist", "facts": FACTS, "text": "Say it slowly"}
        reply = self.request("POST", "/brain/ask", {"Origin": self.own, "X-Arnheim-Brain": on.token}, body)
        first = json.loads(reply.readline())
        first_at = time.time()
        rest = [json.loads(raw) for raw in reply.read().splitlines()]
        self.assertEqual(first, {"text": "Turn"})
        self.assertEqual(rest[-1], {"done": True})
        self.assertGreater(time.time() - first_at, 1.0)  # the first piece came while Claude was still answering
        self.assertEqual("".join(x.get("text", "") for x in [first, *rest]), "Turn 1: you said Say it slowly")

    def test_never_with_lan(self):
        done = subprocess.run([sys.executable, os.path.join(ROOT, "serve.py"), "--brain", "--lan", "8766"], capture_output=True, text=True, timeout=20)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("only on this computer", done.stderr)


if __name__ == "__main__":
    unittest.main()
