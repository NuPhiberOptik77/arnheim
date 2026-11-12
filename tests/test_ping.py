"""Pings on your phone (connect/ping.py): the morning brief at the day's first time, and later only when a
decision has come up; never twice for the same time, never on a quiet morning, and a new setting waits for its
first time. Sent through a command that stands in for a phone, and through a small local server that stands in
for ntfy. Nothing leaves this computer.

Run from the repository's folder: python3 -m unittest discover tests
"""
import datetime
import http.server
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
import ping  # noqa: E402

DAY = datetime.date(2026, 11, 12)


def at(day_offset, hhmm):
    h, m = (int(x) for x in hhmm.split(":"))
    return datetime.datetime.combine(DAY + datetime.timedelta(days=day_offset), datetime.time(h, m)).timestamp()


RECORD = """import sys
with open(sys.argv[1], "a", encoding="utf-8") as handle:
    handle.write(sys.stdin.read() + "=====\\n")
"""


class PingTest(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.data = os.path.join(self.base, "data")
        os.makedirs(os.path.join(self.data, "feeds", "history"))
        self.got = os.path.join(self.base, "got.txt")
        recorder = os.path.join(self.base, "record.py")
        with open(recorder, "w", encoding="utf-8") as handle:
            handle.write(RECORD)
        self.company({"run": [sys.executable, recorder, self.got], "at": ["08:00", "13:00", "17:00"]})

    def tearDown(self):
        shutil.rmtree(self.base)

    def company(self, pings):
        self.write("company.json", {"company": "Example Studio", "feeds": ["feeds/claude-code.json"],
                                    "floors": [{"id": "lantern", "label": "Lantern"}, {"id": "studio", "label": "Studio"}], "pings": pings})

    def write(self, name, body):
        path = os.path.join(self.data, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(body, handle)

    def work(self, more=()):
        self.write("feeds/claude-code.json", {"conversations": [
            {"id": "c1", "project": "Lantern", "title": "Fix the login", "check": True, "proof": {"state": "passed"}},
            {"id": "c2", "project": "Lantern", "title": "Pick a colour", "says": {"needs": "Blue or green?"}},
            {"id": "c3", "project": "Lantern", "title": "Run the tests", "working": True},
            *more]})
        self.write("work.json", {"tasks": [{"id": "t1", "title": "Renew the domain", "project": "Studio", "status": "needs_you"},
                                           {"id": "t2", "title": "Done already", "project": "Studio", "status": "done"}]})
        self.write("control/asks/a1b2c3d4e5f6.json", {"id": "a1b2c3d4e5f6", "key": "c3", "tool": "Bash", "what": "Bash: npm test",
                                                      "at": time.time(), "until": time.time() + 3600})
        self.write(f"feeds/history/{DAY.isoformat()}.json", {"moments": [
            {"at": at(0, "06:00"), "key": "c0", "title": "Before", "kind": "finished"},
            {"at": at(0, "07:20"), "key": "c1", "project": "Lantern", "title": "Fix the login", "kind": "working"},
            {"at": at(0, "07:40"), "key": "c1", "project": "Lantern", "title": "Fix the login", "kind": "finished"}]})

    def sent(self):
        try:
            with open(self.got, encoding="utf-8") as handle:
                return [p.strip() for p in handle.read().split("=====") if p.strip()]
        except OSError:
            return []

    def test_the_brief_then_only_new_decisions(self):
        self.work()
        self.assertIsNone(ping.tick(self.data, at(0, "07:00")))  # a new setting waits for its first time
        self.assertEqual(self.sent(), [])
        row = ping.tick(self.data, at(0, "08:01"))
        self.assertTrue(row["ok"])
        self.assertEqual(self.sent(), ['Arnheim: your morning brief\nSince 07:00: 1 agent was at work. One finished: "Fix the login", proven.\n\n'
                                       '3 things wait on you:\n'
                                       '- "Run the tests" on Lantern wants your permission to run a command\n'
                                       '- "Pick a colour" on Lantern asks: Blue or green?\n'
                                       '- Your task "Renew the domain" on Studio'])
        self.assertIsNone(ping.tick(self.data, at(0, "08:05")))  # the same time: once
        self.assertIsNone(ping.tick(self.data, at(0, "13:01")))  # nothing new to decide
        self.assertEqual(len(self.sent()), 1)
        self.work([{"id": "c4", "project": "Studio", "title": "Name the release", "says": {"needs": "Which name?"}}])
        self.assertIsNone(ping.tick(self.data, at(0, "16:00")))  # it waits for the next time
        row = ping.tick(self.data, at(0, "17:02"))
        self.assertEqual(row["title"], "Arnheim: 4 decisions wait on you")
        self.assertIn('- "Name the release" on Studio asks: Which name?', self.sent()[-1])
        self.assertNotIn("npm test", "".join(self.sent()))  # a permission's command never leaves this computer
        with open(os.path.join(self.data, "feeds", "pings.json"), encoding="utf-8") as handle:
            kept = json.load(handle)
        self.assertEqual([b["title"] for b in kept["bundles"]], ["Arnheim: your morning brief", "Arnheim: 4 decisions wait on you"])

    def test_a_permission_never_leaves_with_its_command(self):
        """With the building closed, as when you're away: the agent's conversation says it waits for your
        permission, with the command, and the ping names only the kind of permission."""
        folder = os.path.realpath(os.path.join(self.base, "lantern"))
        os.makedirs(folder)
        self.write("company.json", {"company": "Example Studio", "feeds": ["feeds/claude-code.json"],
                                    "floors": [{"id": "lantern", "label": "Lantern", "folder": folder}],
                                    "pings": {"run": [sys.executable, os.path.join(self.base, "record.py"), self.got], "at": ["08:00"]}})
        event = {"session_id": "abc123def456-7890", "cwd": folder, "hook_event_name": "PermissionRequest", "tool_name": "Bash",
                 "tool_input": {"command": "curl -H 'Authorization: Bearer sk-made-up-123' https://example.org"}}
        done = subprocess.run([sys.executable, os.path.join(ROOT, "connect", "claude_code.py")], input=json.dumps(event), capture_output=True,
                              text=True, timeout=30, env=dict(os.environ, ARNHEIM_DATA=self.data, ARNHEIM_CONTROL_WAIT="1"))
        self.assertEqual(done.returncode, 0, done.stderr)
        with open(os.path.join(self.data, "feeds", "claude-code.json"), encoding="utf-8") as handle:
            self.assertIn("sk-made-up-123", json.dumps(json.load(handle)))  # on this computer, the building shows it
        ping.tick(self.data, at(0, "07:00"))
        self.assertTrue(ping.tick(self.data, at(0, "08:01"))["ok"])
        sent = "".join(self.sent())
        self.assertIn("wants your permission to run a command", sent)
        self.assertNotIn("sk-made-up", sent)
        self.assertNotIn("curl", sent)

    def test_a_quiet_morning_sends_nothing(self):
        self.assertIsNone(ping.tick(self.data, at(0, "07:00")))
        self.assertIsNone(ping.tick(self.data, at(1, "08:01")))
        self.assertEqual(self.sent(), [])

    def test_a_missed_time_sends_once(self):
        self.work()
        ping.tick(self.data, at(-1, "20:00"))
        self.assertTrue(ping.tick(self.data, at(0, "18:30"))["ok"])  # asleep through 08:00, 13:00 and 17:00: one ping
        self.assertIsNone(ping.tick(self.data, at(0, "18:31")))
        self.assertEqual(len(self.sent()), 1)

    def test_settings_that_cant_be_used(self):
        for given in ({"ntfy": "ftp://example.org/x"}, {"ntfy": "http://ntfy.sh/topic"}, {"run": "notify"},
                      {"ntfy": "https://ntfy.sh/topic", "at": ["25:00"]}, ["08:00"]):
            self.company(given)
            self.assertIsInstance(ping.settings(self.data), str, given)
        self.company({"ntfy": "https://ntfy.sh/a-long-topic", "at": "07:30"})
        self.assertEqual(ping.settings(self.data), {"ntfy": "https://ntfy.sh/a-long-topic", "at": [(7, 30)]})
        self.company({"ntfy": "http://127.0.0.1:8080/a-topic"})  # plain http only to a server on this computer
        self.assertEqual(ping.settings(self.data)["ntfy"], "http://127.0.0.1:8080/a-topic")
        self.assertEqual([ping.permission(t) for t in ("Bash", "Edit", "Read", "WebFetch", "mcp__x__y", "rm -rf /")],
                         ["run a command", "change a file", "read files", "use the web", "use mcp__x__y", "use a tool"])

    def test_a_test_ping(self):
        done = subprocess.run([sys.executable, os.path.join(ROOT, "connect", "ping.py"), "--test"], capture_output=True, text=True,
                              timeout=30, env=dict(os.environ, ARNHEIM_DATA=self.data))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.sent(), ["Arnheim: a test\nArnheim can reach you here. Pings come at 08:00, 13:00, 17:00."])

    def test_through_ntfy(self):
        heard = []

        class Phone(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                heard.append((self.path, self.headers.get("Title"), self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8")))
                self.send_response(200)
                self.end_headers()

            def log_message(self, *_):
                pass
        server = http.server.HTTPServer(("127.0.0.1", 0), Phone)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            ok, why = ping.send({"ntfy": f"http://127.0.0.1:{server.server_port}/a-long-topic"}, "Arnheim: a test", "Café ready.")
            self.assertEqual((ok, why), (True, None))
            self.assertEqual(heard, [("/a-long-topic", "Arnheim: a test", "Café ready.")])
            server.shutdown()
            server.server_close()  # nobody listening now
            ok, why = ping.send({"ntfy": f"http://127.0.0.1:{server.server_port}/a-long-topic"}, "Arnheim: a test", "x")
            self.assertFalse(ok)
            self.assertIn("couldn't be reached", why)
        finally:
            server.server_close()


if __name__ == "__main__":
    unittest.main()
