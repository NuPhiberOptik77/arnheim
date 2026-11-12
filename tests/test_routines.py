"""Routines (connect/routines.py): jobs on a schedule that report into the building, and tell you only
when something needs you.

Each test makes a company of its own in a temporary folder (ARNHEIM_DATA), with a stand-in for Claude
Code's `claude` command (ARNHEIM_CLAUDE) for routines that start an agent, so no real Claude Code runs
and your data/ is never touched. Run from the repository's folder: python3 -m unittest discover tests
"""
import datetime
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNNER = os.path.join(ROOT, "connect", "routines.py")
sys.path.insert(0, os.path.join(ROOT, "connect"))
import control  # noqa: E402  (after the path is set)
import routines  # noqa: E402

AGENT = r"""
import json, os, sys
here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(here, "asked.jsonl"), "a") as out:
    out.write(json.dumps({"args": sys.argv[1:], "asked": sys.stdin.read(), "nested": os.environ.get("CLAUDECODE")}) + "\n")
with open(os.path.join(here, "answer.json")) as given:
    print(given.read())
"""


def at(text):
    """A time on this computer's clock, as seconds."""
    return datetime.datetime.strptime(text, "%Y-%m-%d %H:%M").timestamp()


class ScheduleTest(unittest.TestCase):
    def r(self, every, on="monday", hour=9, minute=0):
        return {"every": every, "on": on, "at": (hour, minute)}

    def test_last_and_next_times(self):
        thursday = at("2026-11-12 10:30")  # a Thursday
        cases = [
            (self.r("day"), "2026-11-12 09:00", "2026-11-13 09:00"),
            (self.r("day", hour=11), "2026-11-11 11:00", "2026-11-12 11:00"),
            (self.r("weekday"), "2026-11-12 09:00", "2026-11-13 09:00"),
            (self.r("monday"), "2026-11-09 09:00", "2026-11-16 09:00"),
            (self.r("week", on="saturday", hour=7, minute=30), "2026-11-07 07:30", "2026-11-14 07:30"),
            (self.r("hour", minute=15), "2026-11-12 10:15", "2026-11-12 11:15"),
            (self.r("hour", minute=45), "2026-11-12 09:45", "2026-11-12 10:45"),
        ]
        for r, last, nxt in cases:
            with self.subTest(r=r):
                self.assertEqual(routines.last_time(r, thursday), at(last))
                self.assertEqual(routines.next_time(r, thursday), at(nxt))
        friday_night = at("2026-11-13 22:00")
        self.assertEqual(routines.next_time(self.r("weekday"), friday_night), at("2026-11-16 09:00"))  # over the weekend

    def test_in_words(self):
        self.assertEqual([routines.when(r) for r in (self.r("day", hour=7, minute=5), self.r("weekday"), self.r("friday", hour=16),
                                                     self.r("week", on="sunday"), self.r("hour", minute=30))],
                         ["Every day at 07:05", "Every weekday at 09:00", "Every Friday at 16:00", "Every Sunday at 09:00", "Every hour at 30 past"])


class RoutinesTest(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.data = os.path.join(self.base, "data")
        self.folder = os.path.realpath(os.path.join(self.base, "code", "tidepool"))
        self.tools = os.path.join(self.base, "tools")
        for folder in (self.data, self.folder, self.tools):
            os.makedirs(folder)
        with open(os.path.join(self.tools, "agent.py"), "w", encoding="utf-8") as handle:
            handle.write(AGENT)
        self.env = dict(os.environ, ARNHEIM_DATA=self.data, CLAUDECODE="1",
                        ARNHEIM_CLAUDE=f"{shlex.quote(sys.executable)} {shlex.quote(os.path.join(self.tools, 'agent.py'))}")
        self.flag = os.path.join(self.folder, "sensor-ok")

    def tearDown(self):
        shutil.rmtree(self.base)

    def company(self, *listed, **floor):
        with open(os.path.join(self.data, "company.json"), "w", encoding="utf-8") as handle:
            json.dump({"company": "Example Studio", "feeds": ["feeds/routines.json"],
                       "floors": [{"id": "tidepool", "label": "Tidepool", "folder": self.folder, "routines": list(listed), **floor}]}, handle)

    def sensors(self, **more):
        check = "import os, sys; ok = os.path.exists('sensor-ok'); print('Sensor 3: ' + ('fine' if ok else 'no readings for 6 hours')); sys.exit(0 if ok else 1)"
        return {"id": "sensors", "label": "Sensor readings", "every": "day", "at": "07:00", "run": [sys.executable, "-c", check], **more}

    def answer(self, text, error=False):
        with open(os.path.join(self.tools, "answer.json"), "w", encoding="utf-8") as handle:
            json.dump({"type": "result", "result": text, "is_error": error}, handle)

    def runner(self, *args):
        done = subprocess.run([sys.executable, RUNNER, *args], capture_output=True, text=True, env=self.env, timeout=60)
        return done.returncode, done.stdout.strip(), done.stderr.strip()

    def feed(self):
        with open(os.path.join(self.data, "feeds", "routines.json"), encoding="utf-8") as handle:
            return json.load(handle)

    def test_a_command_that_fails_needs_you_until_it_passes(self):
        self.company(self.sensors())
        self.assertEqual(self.runner("--run", "sensors")[:2], (0, "failed"))
        feed = self.feed()
        [row] = feed["routines"]
        self.assertEqual((row["id"], row["label"], row["when"], row["kind"], row["project"]),
                         ("rt-tidepool-sensors", "Sensor readings", "Every day at 07:00", "command", "Tidepool"))
        self.assertEqual((row["last"]["state"], row["last"]["tail"]), ("failed", "Sensor 3: no readings for 6 hours"))
        self.assertGreater(row["next"], time.time())
        [task] = feed["tasks"]
        self.assertEqual((task["status"], task["routine"], task["project"], task["title"], task["note"]),
                         ("needs_you", "rt-tidepool-sensors", "Tidepool", 'The routine "Sensor readings" needs you', "It failed. Sensor 3: no readings for 6 hours"))

        open(self.flag, "w").close()
        self.assertEqual(self.runner("--run", "rt-tidepool-sensors")[:2], (0, "all clear"))
        feed = self.feed()
        self.assertEqual((feed["routines"][0]["last"]["state"], feed["tasks"]), ("all clear", []))  # nothing needs you: quiet again

    def test_due_once_per_time_and_never_on_first_sight(self):
        self.company(self.sensors())
        r = routines.routines_of(self.data)[0]
        first_seen = at("2026-11-12 08:00")
        self.assertEqual(routines.due(first_seen, self.data), [])  # today's 07:00 was before Arnheim knew of it
        self.assertEqual(routines.due(at("2026-11-12 23:00"), self.data), [])
        self.assertEqual(routines.due(at("2026-11-13 07:01"), self.data), ["rt-tidepool-sensors"])
        self.assertEqual(routines.due(at("2026-11-13 07:02"), self.data), [])  # started: not again while it runs
        with open(os.path.join(self.data, "feeds", "routines.json"), encoding="utf-8") as handle:
            self.assertEqual(json.load(handle)["routines"][0]["since"], first_seen)
        self.assertEqual(routines.running({"state": "starting", "at": at("2026-11-13 07:01")}, r, at("2026-11-13 07:20")), False)  # gone too long
        # A computer asleep over several mornings runs it once when it wakes, not once for each.
        self.assertEqual(routines.due(at("2026-11-16 10:00"), self.data), ["rt-tidepool-sensors"])

    def test_tick_starts_what_is_due_in_the_background(self):
        self.company(self.sensors(every="hour", at="00:00"))
        def back_in_time(rows, tasks):
            rows["rt-tidepool-sensors"]["since"] = time.time() - 2 * 3600
        routines.edit(back_in_time, self.data)
        self.assertEqual(self.runner()[0], 0)
        for _ in range(100):  # it runs on its own, so wait a little for it
            last = self.feed()["routines"][0].get("last") or {}
            if last.get("state") in ("failed", "all clear"):
                break
            time.sleep(0.1)
        self.assertEqual(last["state"], "failed")

    def test_an_agent_that_ends_all_clear_stays_quiet(self):
        self.company({"id": "scan", "label": "Security scan", "every": "friday", "at": "16:00", "ask": "look for secrets added this week"},
                     check={"run": ["npm", "test"], "label": "The tests"})
        self.answer("I looked through this week's changes. Nothing secret or unsafe was added. All clear.")
        self.assertEqual(self.runner("--run", "scan")[:2], (0, "all clear"))
        with open(os.path.join(self.tools, "asked.jsonl"), encoding="utf-8") as handle:
            [call] = [json.loads(line) for line in handle]
        self.assertIn("Look for secrets added this week", call["asked"])
        self.assertIn('as the routine "Security scan" (every friday at 16:00), with no one watching, on the Tidepool floor', call["asked"])
        self.assertIn("Arnheim runs the tests (npm test) on your work", call["asked"])
        self.assertIn('end your last message with the words "All clear"', call["asked"])
        self.assertEqual(call["args"][:3], ["-p", "--output-format", "json"])
        self.assertIsNone(call["nested"])
        row = self.feed()["routines"][0]
        self.assertEqual((row["kind"], row["last"]["state"], row["last"]["said"]),
                         ("agent", "all clear", "I looked through this week's changes. Nothing secret or unsafe was added. All clear."))
        self.assertRegex(row["last"]["key"], r"^cc-[0-9a-f]{12}$")
        self.assertEqual(self.feed()["tasks"], [])

    def test_an_agent_that_needs_you_says_why(self):
        self.company({"id": "scan", "label": "Security scan", "every": "friday", "ask": "look for secrets added this week"})
        self.answer("An API key was added to config.js on Tuesday. I didn't remove it, since the app may need it: decide whether to rotate it.")
        self.assertEqual(self.runner("--run", "scan")[:2], (0, "needs you"))
        [task] = self.feed()["tasks"]
        self.assertEqual(task["note"], "An API key was added to config.js on Tuesday. I didn't remove it, since the app may need it: decide whether to rotate it.")
        self.assertEqual(task["session"], self.feed()["routines"][0]["last"]["key"])  # listed once, as its conversation, when that's in the building

        self.answer("Not logged in.", error=True)
        self.assertEqual(self.runner("--run", "scan")[:2], (0, "error"))
        self.assertEqual(self.feed()["tasks"][0]["note"], "It couldn't run. Not logged in.")

    def test_only_routines_that_can_run_here(self):
        self.company(self.sensors(), {"id": "bad id!", "every": "day", "run": ["true"]}, {"id": "noday", "every": "someday", "run": ["true"]},
                     {"id": "late", "every": "day", "at": "25:00", "run": ["true"]}, {"id": "nothing", "every": "day"})
        self.assertEqual([r["id"] for r in routines.routines_of(self.data)], ["sensors"])
        code, _, err = self.runner("--run", "nowhere")
        self.assertEqual(code, 1)
        self.assertIn("No routine called nowhere", err)
        self.assertEqual(self.runner("--list")[1].split(". Next:")[0], "Sensor readings (Tidepool, sensors): Every day at 07:00")

    def test_run_it_now_from_the_building(self):
        self.company(self.sensors())
        routines.edit(lambda rows, tasks: None, self.data)  # the feed, as the runner first writes it
        building = control.Control(self.data, claude=[sys.executable, "-c", "pass"])

        def post(body):
            code, _, data, _ = building.handle("POST", "run_routine", json.dumps(body).encode(), building.token)
            return code, json.loads(data)
        self.assertEqual(post({"key": "rt-tidepool-sensors"}), (200, {"ok": True, "routine": "Sensor readings"}))
        for _ in range(100):
            last = self.feed()["routines"][0].get("last") or {}
            if last.get("state") == "failed":
                break
            time.sleep(0.1)
        self.assertEqual(last["state"], "failed")
        self.assertEqual(post({"key": "rt-nowhere"})[0], 400)
        self.assertEqual(post({"key": "../../etc"})[0], 400)


if __name__ == "__main__":
    unittest.main()
