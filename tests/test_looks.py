"""In the photo-real look, a receptionist or assistant is shown photo-real only when they were made from the
very look the company file gives them (src/three/looks.js); anyone else is drawn, never shown as someone else.

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

SAMPLE = {"skin": "#a26b48", "hair": "#2b1d18", "coat": "#5b3b5e", "earrings": "studs"}
OWN = {"skin": "#8d5a3b", "style": "braids", "collar": "round", "brooch": ["#22262b", "#e9dcc4"], "nod": 0.1}  # made up

# Each case: the sets of people as [name of set, {person: recorded look, or None for no look}] (a set of None is a
# people.json that didn't load), the person asked for, the company file's look, and which set should stand for them.
CASES = [
    ("the sample's own receptionist", [["sample", {"receptionist": SAMPLE}]], "receptionist", SAMPLE, "sample"),
    ("the same look, keys in another order", [["sample", {"receptionist": SAMPLE}]], "receptionist",
     dict(reversed(list(SAMPLE.items()))), "sample"),
    ("a company with no look is not the sample's person", [["sample", {"receptionist": SAMPLE}]], "receptionist", None, None),
    ("another look is not the sample's person", [["sample", {"receptionist": SAMPLE}]], "receptionist",
     {**SAMPLE, "coat": "#2f4a5c"}, None),
    ("one setting more is another look", [["sample", {"receptionist": SAMPLE}]], "receptionist", {**SAMPLE, "lips": "#9a5b55"}, None),
    ("one setting fewer is another look", [["sample", {"receptionist": SAMPLE}]], "receptionist",
     {k: v for k, v in SAMPLE.items() if k != "earrings"}, None),
    ("a number written as text is another look", [["own", {"assistant": OWN}]], "assistant", {**OWN, "nod": "0.1"}, None),
    ("a brooch's colours in another order are another look", [["own", {"assistant": OWN}]], "assistant",
     {**OWN, "brooch": list(reversed(OWN["brooch"]))}, None),
    ("the company's own person, made from its look", [["own", {"assistant": OWN}], ["sample", {"assistant": SAMPLE}]],
     "assistant", OWN, "own"),
    ("a company's own person comes before the sample's", [["own", {"receptionist": {}}], ["sample", {"receptionist": {}}]],
     "receptionist", None, "own"),
    ("no look in the file matches a person made from no look", [["own", {"receptionist": {}}]], "receptionist", None, "own"),
    ("a person with no recorded look is never used", [["own", {"receptionist": None}], ["sample", {"receptionist": None}]],
     "receptionist", None, None),
    ("someone the set doesn't have", [["sample", {"receptionist": SAMPLE}]], "assistant", SAMPLE, None),
    ("people that didn't load", [["own", None], ["sample", None]], "receptionist", SAMPLE, None),
]

SCRIPT = """
import { pathToFileURL } from 'node:url';
const { realPerson } = await import(pathToFileURL(process.argv[1] + '/src/three/looks.js').href);
const cases = JSON.parse(process.argv[2]);
const out = cases.map(([sets, name, look]) => {
  const made = sets.map(([label, people]) => people && {
    label,
    has: (n) => n in people,
    lookOf: (n) => people[n] ?? undefined,
  });
  return realPerson(made, name, look ?? undefined)?.label ?? null;
});
console.log(JSON.stringify(out));
"""


@unittest.skipUnless(NODE, "Node.js isn't installed")
class LooksTest(unittest.TestCase):
    def test_who_stands_for_whom(self):
        cases = [[sets, name, look] for _, sets, name, look, _ in CASES]
        run = subprocess.run([NODE, "--input-type=module", "-e", SCRIPT, ROOT, json.dumps(cases)],
                             capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)
        got = json.loads(run.stdout)
        for (what, _, _, _, want), answer in zip(CASES, got):
            with self.subTest(what):
                self.assertEqual(answer, want)


if __name__ == "__main__":
    unittest.main()
