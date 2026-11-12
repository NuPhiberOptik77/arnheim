"""The company's memory, as the page hears and says it (src/memory.js): what counts as asking the
receptionist to remember something, how the memory is read out, and which decisions answer an agent's
question.

The rules are JavaScript, so this runs them under Node.js, and is skipped where Node isn't installed.
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
const m = await import(pathToFileURL(process.argv[1] + '/src/memory.js').href);
const out = JSON.parse(process.argv[2]).map(([fn, a, b, c]) => {
  if (fn === 'remember') return m.rememberAsked(a);
  if (fn === 'asked') return m.MEMORY_ASKED.test(a);
  if (fn === 'say') return m.sayMemory(a, b);
  if (fn === 'decided') return m.decidedFor(a, b).map((r) => r.id);
  throw new Error(fn);
});
console.log(JSON.stringify(out));
"""

REMEMBER = [
    ("remember that we never push on a Friday", "We never push on a Friday."),
    ("Remember: every kit gets a safety sheet!", "Every kit gets a safety sheet."),
    ("please remember the logo is blue", "The logo is blue."),
    ("Note that the tests take ten minutes.", "The tests take ten minutes."),
    ("From now on, ask before adding a library", "From now on, ask before adding a library."),
    ("going forward we write tests first", "Going forward we write tests first."),
    ("remember me", None),
    ("remember to call the bank", None),
    ("remember when we launched?", None),
    ("Do you remember the logo?", None),
    ("what do you remember", None),
    ("from now on", None),
    ("remind me to call the bank", None),
]
ASKED = [("What have we decided?", True), ("what do the agents know", True), ("Show me the company memory", True),
         ("What do you remember?", True), ("what's the weather", False), ("remember that the sky is blue", False)]
ROWS = [{"id": "push", "text": "We never push on a Friday."}, {"id": "sheet", "text": "Every kit goes out with a printed safety sheet."},
        {"id": "free", "text": "The apps stay free. The kits pay for them."}]


@unittest.skipUnless(NODE, "Node.js isn't installed")
class MemoryWordsTest(unittest.TestCase):
    def run_js(self, cases):
        run = subprocess.run([NODE, "--input-type=module", "-e", SCRIPT, ROOT, json.dumps(cases)], capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)
        return json.loads(run.stdout)

    def test_asked_to_remember(self):
        got = self.run_js([["remember", said] for said, _ in REMEMBER])
        for (said, want), answer in zip(REMEMBER, got):
            with self.subTest(said):
                self.assertEqual(answer, want)

    def test_asked_what_is_remembered(self):
        got = self.run_js([["asked", said] for said, _ in ASKED])
        self.assertEqual(got, [want for _, want in ASKED])

    def test_said_aloud(self):
        many = [{"id": str(n), "text": f"Rule {n}."} for n in range(1, 8)]
        got = self.run_js([["say", []], ["say", ROWS[:1]], ["say", many, 3]])
        self.assertEqual(got[0], 'Nothing is remembered yet. Say "remember that ..." and every agent will be told it as it starts.')
        self.assertEqual(got[1], "One thing every agent is told as it starts: We never push on a Friday.")
        self.assertEqual(got[2], "7 things every agent is told as it starts, the latest 3: Rule 5. Rule 6. Rule 7.")

    def test_a_question_already_answered(self):
        got = self.run_js([
            ["decided", "Should I push the release today? It's Friday.", ROWS],
            ["decided", "Do the kits need a printed sheet about safety?", ROWS],
            ["decided", "Which font should the menu use?", ROWS],
            ["decided", "Friday?", ROWS],  # one word in common is too little to go on
            ["decided", "", ROWS],
        ])
        self.assertEqual(got, [["push"], ["sheet"], [], [], []])


if __name__ == "__main__":
    unittest.main()
