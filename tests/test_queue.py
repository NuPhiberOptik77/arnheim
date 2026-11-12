"""One list of everything waiting on you, from every agent and the work (src/queue.js): what is in it, in
what order, how the receptionist says it, and when "allow all the reads" allows them.

The rule is JavaScript, so this runs it under Node.js, and is skipped where Node isn't installed.
Run from the repository's folder: python3 -m unittest discover tests
"""
import json
import os
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")
NOW = 1_800_000_000  # seconds

SCRIPT = """
import { pathToFileURL } from 'node:url';
const q = await import(pathToFileURL(process.argv[1] + '/src/queue.js').href);
const out = JSON.parse(process.argv[2]).map(([fn, given, extra]) => {
  const items = q.waitingOnYou(given);
  if (fn === 'list') return items.map((i) => [i.kind, i.key ?? null, i.title, i.what, !!i.read]);
  if (fn === 'together') return q.together(items);
  if (fn === 'say') return q.sayWaiting(items, (p) => `the ${p} floor`, extra ?? 4);
  if (fn === 'allow') return q.allowReadsAsked(extra, items);
  throw new Error(fn);
});
console.log(JSON.stringify(out));
"""


def ask(aid, key, tool, what, at=NOW - 30, until=NOW + 150):
    return {"id": aid, "key": key, "tool": tool, "what": what, "at": at, "until": until}


def talk(cid, title, project="Shop", **more):
    return {"id": cid, "title": title, "project": project, "at": NOW - 600, **more}


def task(tid, title, status="needs_you", project="Shop", **more):
    return {"id": tid, "title": title, "status": status, "project": project, "at": NOW - 7200, **more}


BUSY = {
    "now": NOW,
    "asks": [ask("a1", "c1", "Bash", "npm test", until=NOW + 170), ask("a2", "c2", "Read", "notes.md", until=NOW + 40),
             ask("a3", "r9", "Grep", "TODO")],
    "runs": [{"key": "r9", "project": "Site", "title": "Tidy the site"}],
    "conversations": [
        talk("c1", "Fix the till", working=True), talk("c2", "Price list"),
        talk("c3", "New menu", says={"needs": "Which font?"}),
        talk("c4", "Stock count", check=True, stopped=NOW - 300, says={"now": "Counted 40 lines."}),
        talk("c5", "Old report", check=True, stopped=NOW - 3 * 3600),  # finished too long ago
        talk("c6", "Logo", check=True, stopped=(NOW - 60) * 1000),  # a time in milliseconds
        talk("c7", "Busy one", working=True, says={"needs": "Ignore me, still working"}),
    ],
    "tasks": [task("t1", "Sign the lease", note="By Friday"), task("t2", "Pick a font", session="c3"),
              task("t3", "Order chairs", status="claude"), task("t4", "Call the bank", at=NOW - 99999)],
}


@unittest.skipUnless(NODE, "Node.js isn't installed")
class QueueTest(unittest.TestCase):
    def run_js(self, cases):
        run = subprocess.run([NODE, "--input-type=module", "-e", SCRIPT, ROOT, json.dumps(cases)],
                             capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)
        return json.loads(run.stdout)

    def test_the_list(self):
        (got,) = self.run_js([["list", BUSY]])
        self.assertEqual(got, [
            # permissions first, the one whose wait runs out first at the top
            ["permission", "c2", "Price list", "to read notes.md", True],
            ["permission", "r9", "Tidy the site", "to search for TODO", True],  # named from the run the page started
            ["permission", "c1", "Fix the till", "to run npm test", False],
            # then questions (an agent at work isn't waiting on you), then your tasks, longest waiting first
            ["question", "c3", "New menu", "Which font?", False],
            ["task", None, "Call the bank", "", False],
            ["task", None, "Sign the lease", "By Friday", False],
            # then agents that finished lately, newest first
            ["turn", "c6", "Logo", "It has finished for now.", False],
            ["turn", "c4", "Stock count", "Counted 40 lines.", False],
        ])

    def test_reads_together(self):
        one_read = {**BUSY, "asks": BUSY["asks"][:2]}
        got = self.run_js([["together", BUSY], ["together", one_read], ["together", {"now": NOW}]])
        self.assertEqual(got[0], {"label": "Allow all 2 reads", "ids": ["a2", "a3"]})
        self.assertIsNone(got[1])
        self.assertIsNone(got[2])

    def test_said_aloud(self):
        got = self.run_js([["say", {"now": NOW}], ["say", {"now": NOW, "conversations": [talk("c3", "New menu", says={"needs": "Which font?"})]}],
                           ["say", BUSY, 2], ["say", {"now": NOW, "tasks": [task("t1", "Sign the lease")]}]])
        self.assertEqual(got[0], "Nothing is waiting on you right now.")
        self.assertEqual(got[1], "One thing is waiting on you. New menu on the Shop floor is asking: Which font?")
        self.assertEqual(got[3], 'One thing is waiting on you. Your task "Sign the lease" on the Shop floor.')
        self.assertEqual(got[2], "8 things are waiting on you. Price list on the Shop floor wants your permission to read notes.md. "
                                 "Tidy the site on the Site floor wants your permission to search for TODO. And 6 more in the panel. "
                                 'Say "allow all the reads" to let the 2 that only read go ahead.')

    def test_what_it_wants(self):
        asks = [ask("a1", "c1", "Bash", "npm test"), ask("a2", "c1", "Frobnicate", "the widget"), ask("a3", "c1", None, None),
                ask("a4", "c1", "WebFetch", None)]
        (got,) = self.run_js([["list", {"now": NOW, "asks": asks}]])
        self.assertEqual([i[3] for i in got], ["to run npm test", "to use Frobnicate on the widget", "to use a tool", "to use WebFetch"])

    def test_allow_all_the_reads(self):
        said = ["allow all the reads", "Please approve every read request.", "Allow all of the reads please!",
                "allow all", "don't allow all the reads", "allow all the reads and the tests", "allow everything"]
        got = self.run_js([["allow", BUSY, text] for text in said] + [["allow", {"now": NOW}, "allow all the reads"]])
        self.assertEqual(got, [["a2", "a3"], ["a2", "a3"], ["a2", "a3"], None, None, None, None, []])


if __name__ == "__main__":
    unittest.main()
