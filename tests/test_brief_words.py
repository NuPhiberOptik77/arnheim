"""The brief (src/brief.js): what happened since your last visit, and what waits on you now, in the
receptionist's words. Where it starts, what counts as finished or stopped, the routines that ran, and the
questions that ask for it.

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


NOW = at("2026-11-12 08:30")
SEEN = at("2026-11-11 18:05")  # last night

SCRIPT = """
import { pathToFileURL } from 'node:url';
const { sinceOf, briefOf, sayBrief, sinceSaid, BRIEF_ASKED } = await import(pathToFileURL(process.argv[1] + '/src/brief.js').href);
const g = JSON.parse(process.argv[2]);
const b = briefOf({ ...g.work, since: g.since, now: g.now });
const quiet = briefOf({ moments: [], conversations: [], routines: [], waiting: [], since: g.since, now: g.now });
console.log(JSON.stringify({
  since: [sinceOf(g.seen, g.now), sinceOf(null, g.now), sinceOf(g.now - 3 * 86400, g.now), sinceOf(g.now + 60, g.now)],
  saidSince: g.times.map((t) => sinceSaid(t, g.now)),
  brief: b,
  said: sayBrief(b, (p) => p.toUpperCase(), g.now),
  quiet: { quiet: quiet.quiet, said: sayBrief(quiet, (p) => p, g.now) },
  asked: g.asked.map((q) => BRIEF_ASKED.test(q)),
}));
"""

MOMENTS = [
    {"at": at("2026-11-11 17:00"), "key": "c0", "project": "Studio", "title": "Before you left", "kind": "finished", "what": ""},  # before: left out
    {"at": at("2026-11-11 19:00"), "key": "c1", "project": "Lantern", "title": "Why the bookmark jumps", "kind": "working", "what": ""},
    {"at": at("2026-11-11 21:00"), "key": "c1", "project": "Lantern", "title": "Why the bookmark jumps", "kind": "finished", "what": ""},
    {"at": at("2026-11-11 22:00"), "key": "c2", "project": "Lantern", "title": "Pictures for the app store", "kind": "finished", "what": ""},
    {"at": at("2026-11-12 01:00"), "key": "c3", "project": "Studio", "title": "Plan the quarter", "kind": "working", "what": ""},
    {"at": at("2026-11-12 02:00"), "key": "c3", "project": "Studio", "title": "Plan the quarter", "kind": "finished", "what": ""},
    {"at": at("2026-11-12 03:00"), "key": "c4", "project": "Kitefield", "title": "Tail physics", "kind": "stopped", "what": ""},
    {"at": at("2026-11-12 04:00"), "key": "c5", "project": "Kitefield", "title": "Still going", "kind": "changed", "what": "tail.js"},
    {"at": at("2026-11-12 05:00"), "key": "c6", "project": "Studio", "title": "Went away", "kind": "left", "what": ""},
]
CONVERSATIONS = [
    {"id": "c1", "project": "Lantern", "title": "Why the bookmark jumps", "check": True, "changed": at("2026-11-11 20:50"),
     "proof": {"state": "passed", "check": "The tests", "at": at("2026-11-11 20:55")}},
    {"id": "c2", "project": "Lantern", "title": "Pictures for the app store", "check": True, "changed": at("2026-11-11 21:50"),
     "proof": {"state": "failed", "check": "The picture sizes check", "at": at("2026-11-11 21:55")}},
    {"id": "c3", "project": "Studio", "title": "Plan the quarter", "check": True, "review": {"state": "failed", "why": "No dates.", "times": 2}},
]
ROUTINES = [
    {"id": "rt-a", "project": "Lantern", "label": "Outdated packages", "last": {"state": "all clear", "at": at("2026-11-12 07:00")}},
    {"id": "rt-b", "project": "Tidepool", "label": "Sensor readings", "last": {"state": "failed", "at": at("2026-11-12 07:00"), "tail": "Sensor 3 sent nothing."}},
    {"id": "rt-c", "project": "Studio", "label": "Security scan", "last": {"state": "all clear", "at": at("2026-11-10 16:00")}},  # before: not counted
]
WAITING = [{"kind": "permission"}, {"kind": "question"}, {"kind": "question"}, {"kind": "task"}, {"kind": "turn"}]


@unittest.skipUnless(NODE, "Node.js isn't installed")
class BriefWordsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        given = {"now": NOW, "seen": SEEN, "since": SEEN,
                 "work": {"moments": MOMENTS, "conversations": CONVERSATIONS, "routines": ROUTINES, "waiting": WAITING},
                 "times": [at("2026-11-12 04:30"), at("2026-11-11 18:00"), at("2026-11-09 09:00")],
                 "asked": ["Brief me", "what did I miss?", "What happened overnight?", "catch me up", "give me the morning briefing",
                           "what happened while I was away", "what's happening on Lantern?", "brief the agent"]}
        done = subprocess.run([NODE, "--input-type=module", "-e", SCRIPT, ROOT, json.dumps(given)], capture_output=True, text=True,
                              timeout=30, env=dict(os.environ, TZ="UTC"))
        assert done.returncode == 0, done.stderr
        cls.out = json.loads(done.stdout)

    def test_where_it_starts(self):
        self.assertEqual(self.out["since"], [SEEN, NOW - 12 * 3600, NOW - 24 * 3600, NOW - 12 * 3600])
        self.assertEqual(self.out["saidSince"], ["Since 04:30", "Since yesterday at 18:00", "Since Monday at 09:00"])

    def test_what_happened(self):
        b = self.out["brief"]
        self.assertEqual(b["worked"], 5)  # c1 to c5; c0 was before, c6 only left
        self.assertEqual([(f["title"], f["proof"]) for f in b["finished"]],
                         [("Why the bookmark jumps", "proven"), ("Pictures for the app store", "not proven"), ("Plan the quarter", "failed the review line")])
        self.assertEqual([f["title"] for f in b["stopped"]], ["Tail physics"])
        self.assertEqual((b["ran"], b["clear"]), (2, 1))
        self.assertEqual([r["label"] for r in b["needs"]], ["Sensor readings"])
        self.assertEqual(b["waiting"], {"permission": 1, "question": 2, "task": 1})
        self.assertFalse(b["quiet"])

    def test_the_receptionist(self):
        self.assertEqual(self.out["said"],
                         'Since yesterday at 18:05, 5 agents were at work. 3 finished: "Why the bookmark jumps" on LANTERN, proven; '
                         '"Pictures for the app store" on LANTERN, not proven; "Plan the quarter" on STUDIO, failed the review line. '
                         'One was stopped: "Tail physics" on KITEFIELD. 2 routines ran, 1 all clear. A routine needs you: "Sensor readings" on TIDEPOOL. '
                         'Waiting on you now: 1 permission request, 2 questions and 1 of your tasks. Ask me "what\'s waiting on me?" to hear them.')
        self.assertEqual(self.out["quiet"], {"quiet": True, "said": "Since yesterday at 18:05, all was quiet. Nothing is waiting on you."})

    def test_the_questions_that_ask_for_it(self):
        self.assertEqual(self.out["asked"], [True, True, True, True, True, True, False, False])


if __name__ == "__main__":
    unittest.main()
