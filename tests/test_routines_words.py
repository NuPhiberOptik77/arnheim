"""Routines, as the page says them (src/routines.js): times near now in words, what each routine's last run
came to, the receptionist's answer, and the last and next times from a schedule, as the runner works them
out. And an agent on a walk saying how its own work did on the review line (src/review.js).

The rules are JavaScript, so this runs them under Node.js, on a fixed clock (TZ=UTC), and is skipped where
Node isn't installed. Run from the repository's folder: python3 -m unittest discover tests
"""
import datetime
import json
import os
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")


def at(text):
    return datetime.datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo=datetime.timezone.utc).timestamp()


NOW = at("2026-11-12 10:30")  # a Thursday

SCRIPT = """
import { pathToFileURL } from 'node:url';
const load = (name) => import(pathToFileURL(process.argv[1] + '/src/' + name).href);
const { whenSaid, routineNow, sayRoutines, timesOf, ROUTINES_ASKED } = await load('routines.js');
const { reviewSaid } = await load('review.js');
const g = JSON.parse(process.argv[2]);
console.log(JSON.stringify({
  when: g.when.map((t) => whenSaid(t, g.now)),
  now: g.routines.map((r) => routineNow(r, g.now)),
  said: sayRoutines(g.routines.slice(0, 3), (p) => p, g.now),
  none: sayRoutines([], (p) => p, g.now),
  times: g.schedules.map((r) => timesOf(r, g.now)),
  asked: g.asked.map((q) => ROUTINES_ASKED.test(q)),
  own: g.reviews.map((c) => reviewSaid(c, g.now)),
}));
"""

ROUTINES = [
    {"label": "Outdated packages", "project": "Lantern", "when": "Every Monday at 09:00", "next": at("2026-11-16 09:00"),
     "last": {"state": "all clear", "at": at("2026-11-09 09:00"), "done": at("2026-11-09 09:01")}},
    {"label": "Sensor readings", "project": "Tidepool", "when": "Every day at 07:00", "next": at("2026-11-13 07:00"),
     "last": {"state": "failed", "at": at("2026-11-12 07:00"), "done": at("2026-11-12 07:00"), "tail": "Sensors 1, 2 and 4: fine\nSensor 3 sent nothing."}},
    {"label": "Security scan", "project": "Studio", "when": "Every Friday at 16:00", "next": at("2026-11-13 16:00")},
    {"label": "Scan", "last": {"state": "running", "at": at("2026-11-12 10:29")}},
    {"label": "Scan", "last": {"state": "needs you", "at": at("2026-11-11 18:00"), "done": at("2026-11-11 18:30"), "said": "Rotate the key in config.js"}},
    {"label": "Scan", "last": {"state": "timeout", "at": at("2026-11-12 09:00"), "done": at("2026-11-12 10:00")}},
    {"label": "Scan", "last": {"state": "error", "at": at("2026-11-03 09:00"), "said": "Not logged in."}},
]

SCHEDULES = [
    ({"every": "day", "at": "07:00"}, "2026-11-12 07:00", "2026-11-13 07:00"),
    ({"every": "weekday", "at": "11:00"}, "2026-11-11 11:00", "2026-11-12 11:00"),
    ({"every": "monday"}, "2026-11-09 09:00", "2026-11-16 09:00"),
    ({"every": "week", "on": "saturday", "at": "07:30"}, "2026-11-07 07:30", "2026-11-14 07:30"),
    ({"every": "hour", "at": "00:45"}, "2026-11-12 09:45", "2026-11-12 10:45"),
]


@unittest.skipUnless(NODE, "Node.js isn't installed")
class RoutinesWordsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        given = {"now": NOW, "routines": ROUTINES, "schedules": [s for s, _, _ in SCHEDULES],
                 "when": [at(t) for t in ("2026-11-12 09:02", "2026-11-11 18:30", "2026-11-09 09:00", "2026-11-13 07:30", "2026-11-16 09:00", "2026-11-03 09:00")],
                 "asked": ["What routines are there?", "any scheduled jobs?", "what runs on a schedule", "how is the lantern floor"],
                 "reviews": [{"review": {"state": "passed", "said": "It does what was asked", "times": 1}},
                             {"review": {"state": "sent back", "why": "Still red.", "times": 2}},
                             {"review": {"state": "failed", "why": "Still red.", "times": 2}}, {}]}
        done = subprocess.run([NODE, "--input-type=module", "-e", SCRIPT, ROOT, json.dumps(given)], capture_output=True, text=True,
                              timeout=30, env=dict(os.environ, TZ="UTC"))
        assert done.returncode == 0, done.stderr
        cls.out = json.loads(done.stdout)

    def test_times_in_words(self):
        self.assertEqual(self.out["when"], ["today at 09:02", "yesterday at 18:30", "last Monday at 09:00", "tomorrow at 07:30",
                                            "on Monday at 09:00", "on 3 Nov"])

    def test_what_each_last_run_came_to(self):
        self.assertEqual([(r["state"], r["line"]) for r in self.out["now"]], [
            ("clear", "All clear last Monday at 09:01. Next on Monday at 09:00."),
            ("needs", "It failed today at 07:00: Sensor 3 sent nothing. Next tomorrow at 07:00."),
            ("waiting", "Not run yet. First run tomorrow at 16:00."),
            ("running", "Running now, since 10:29."),
            ("needs", "It needs you, yesterday at 18:30: Rotate the key in config.js."),
            ("needs", "It ran too long today at 10:00 and was stopped."),
            ("needs", "It couldn't run on 3 Nov: Not logged in."),
        ])

    def test_the_receptionist(self):
        self.assertEqual(self.out["said"], "There are 3 routines, and one needs you. Outdated packages on Lantern, every Monday at 09:00. "
                         "All clear last Monday at 09:01. Next on Monday at 09:00. Sensor readings on Tidepool, every day at 07:00. "
                         "It failed today at 07:00: Sensor 3 sent nothing. Next tomorrow at 07:00. Security scan on Studio, every Friday at 16:00. "
                         "Not run yet. First run tomorrow at 16:00.")
        self.assertTrue(self.out["none"].startswith("There are no routines yet."))
        self.assertEqual(self.out["asked"], [True, True, True, False])

    def test_last_and_next_from_a_schedule(self):
        for (r, last, nxt), got in zip(SCHEDULES, self.out["times"]):
            with self.subTest(r=r):
                self.assertEqual((got["last"], got["next"]), (at(last), at(nxt)))

    def test_an_agent_says_how_its_work_did(self):
        self.assertEqual(self.out["own"], [
            "My work passed the review line, after it was sent back once. It does what was asked.",
            "The review line sent my work back a second time, so I'm fixing it: Still red.",
            "My work still failed the review line after being sent back twice, so it reached you anyway: Still red.",
            None,
        ])


if __name__ == "__main__":
    unittest.main()
