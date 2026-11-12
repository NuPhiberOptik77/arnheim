"""Hand out work by talking (src/control.js, deskStart): what the receptionist makes of "get someone to fix the
login bug on Lantern" and the like, which floor it means, and asking which when none is named.

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

SCRIPT = """
import { pathToFileURL } from 'node:url';
globalThis.window = { addEventListener() {} };
const { deskStart } = await import(pathToFileURL(process.argv[1] + '/src/control.js').href);
const [projects, turns] = JSON.parse(process.argv[2]);
const begun = [];
const control = { on: true, projects: () => projects, begin: async (project, text) => { begun.push([project, text]); return {}; } };
let pending = null;
const out = [];
for (const said of turns) {
  const r = deskStart(control, said, pending);
  if (!r) { out.push(null); continue; }
  pending = r.pending;
  out.push([await r.reply, pending && [pending.project, pending.text]]);
}
console.log(JSON.stringify({ out, begun }));
"""
FLOORS = [{"project": "Lantern", "label": "Lantern", "check": "The tests"}, {"project": "Tidepool", "label": "Tidepool", "check": None}]


@unittest.skipUnless(NODE, "Node.js isn't installed")
class HandOutTest(unittest.TestCase):
    def talk(self, turns, floors=FLOORS):
        run = subprocess.run([NODE, "--input-type=module", "-e", SCRIPT, ROOT, json.dumps([floors, turns])], capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)
        return json.loads(run.stdout)

    def test_in_everyday_words(self):
        got = self.talk(["Get someone to fix the login bug on the menu on Lantern", "start it"])
        self.assertEqual(got["out"][0], ['Start an agent on Lantern to fix the login bug on the menu? When it says it\'s done, Arnheim runs the tests on its work. Say "start it", or tap Start.',
                                         ["Lantern", "fix the login bug on the menu"]])
        self.assertIn("Started. The new agent is on Lantern, with your brief and the company's memory.", got["out"][1][0])
        self.assertEqual(got["begun"], [["Lantern", "fix the login bug on the menu"]])

    def test_other_ways_of_saying_it(self):
        got = self.talk(["have an agent on Tidepool tidy the rain gauge code", "never mind", "ask Claude to write the release notes for tidepool"])
        self.assertEqual(got["out"][0][1], ["Tidepool", "tidy the rain gauge code"])
        self.assertEqual(got["out"][1], ["All right, I won't start it.", None])
        self.assertEqual(got["out"][2][1], ["Tidepool", "write the release notes"])
        self.assertEqual(got["begun"], [])

    def test_no_floor_named_asks_which(self):
        got = self.talk(["get someone to update the privacy page", "Tidepool", "yes start it"])
        self.assertEqual(got["out"][0], ["On which floor? Lantern, Tidepool.", [None, "update the privacy page"]])
        self.assertEqual(got["out"][1][1], ["Tidepool", "update the privacy page"])
        self.assertEqual(got["begun"], [["Tidepool", "update the privacy page"]])

    def test_one_floor_needs_no_asking(self):
        got = self.talk(["get someone to update the privacy page"], floors=FLOORS[1:])
        self.assertEqual(got["out"][0][1], ["Tidepool", "update the privacy page"])

    def test_not_handing_out_work(self):
        said = ["what needs me?", "get going", "start it", "ask Claude what is waiting on me", "Ask an agent how it is going",
                "ask Claude on Lantern whether the tests pass", "ask someone to look at the tests on Lantern?", "ask Claude do the tests pass",
                "ask an agent have the tests passed", "ask Claude am I blocked", "ask Claude shall we ship", "ask an agent may I ship it",
                "ask Claude isn't the build broken", "ask an agent whats left"]
        got = self.talk(said)
        self.assertEqual(got["out"], [None] * len(said))
        self.assertEqual(self.talk(["ask Claude to do the release notes for Tidepool"])["out"][0][1], ["Tidepool", "do the release notes"])
        self.assertEqual(got["begun"], [])


if __name__ == "__main__":
    unittest.main()
