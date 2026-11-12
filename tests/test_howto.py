"""A shelf of how-tos: the page's rules (src/howto.js: which how-tos, which fits a question, and Markdown drawn
as text only), and the hook handing an agent its floor's how-tos as it starts (connect/claude_code.py).

The page's rules are JavaScript, so their test runs under Node.js, and is skipped where Node isn't
installed. The hook's test makes a company of its own in a temporary folder (ARNHEIM_DATA).
Run from the repository's folder: python3 -m unittest discover tests
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(ROOT, "connect", "claude_code.py")
NODE = shutil.which("node")

SCRIPT = """
import { pathToFileURL } from 'node:url';
const r = await import(pathToFileURL(process.argv[1] + '/src/howto.js').href);
const org = { howtos: [
  { id: 'ship-lantern', title: 'Ship a new build of Lantern', file: 'howtos/ship.md', project: 'Lantern' },
  { id: 'sensor-alarm', title: 'Answer a sensor alarm', file: 'howtos/sensor.md', project: 'Tidepool' },
  { id: 'release-notes', title: 'Write release notes', file: 'howtos/notes.md' },
  { id: 'bad', title: 'Outside', file: '../secret.md' },
  { id: 'abs', title: 'Absolute', file: '/etc/passwd.md' },
  { id: 'NOPE', title: 'Bad id', file: 'x.md' },
  { id: 'html', title: 'Not markdown', file: 'x.html' },
] };
const all = r.howtosOf(org);
const md = '# Ship it\\n\\nFirst `npm test`, then **build**.\\nSame paragraph.\\n\\n- one\\n- two\\n  more of two\\n1. first\\n2) second\\n\\n```\\n<script>alert(1)</script>\\n```\\n## End ##';
console.log(JSON.stringify({
  all: all.map((x) => x.id),
  lantern: r.howtosOf(org, 'Lantern').map((x) => x.id),
  fits: ['How do I ship a new build?', 'how do we write the release notes', 'how to answer an alarm from a sensor', 'How do I bake a cake?', 'ship a new build'].map((q) => r.howtoFor(q, all)?.id ?? null),
  list: r.shelfAsked('what how-tos are there?'),
  said: r.sayShelf(all, (p) => p.toUpperCase()),
  none: r.sayShelf([]),
  blocks: r.blocks(md),
  runs: r.runs('Run `npm test` and **then** go'),
}));
"""


@unittest.skipUnless(NODE, "Node.js isn't installed")
class HowtoWordsTest(unittest.TestCase):
    def test_shelf(self):
        done = subprocess.run([NODE, "--input-type=module", "-e", SCRIPT, ROOT], capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        out = json.loads(done.stdout)
        self.assertEqual(out["all"], ["ship-lantern", "sensor-alarm", "release-notes"])  # never outside the company's folder
        self.assertEqual(out["lantern"], ["ship-lantern", "release-notes"])  # its own, and those for every floor
        self.assertEqual(out["fits"], ["ship-lantern", "release-notes", "sensor-alarm", None, None])
        self.assertTrue(out["list"])
        self.assertEqual(out["said"], 'The shelf in the Library holds 3 how-tos: "Ship a new build of Lantern" for LANTERN, '
                                      '"Answer a sensor alarm" for TIDEPOOL, "Write release notes". Every agent is told its floor\'s as it starts.')
        self.assertIn("no how-tos yet", out["none"])
        self.assertEqual(out["blocks"], [
            {"kind": "h", "level": 1, "text": "Ship it"},
            {"kind": "p", "text": "First `npm test`, then **build**. Same paragraph."},
            {"kind": "ul", "items": ["one", "two more of two"]},
            {"kind": "ol", "items": ["first", "second"]},
            {"kind": "code", "text": "<script>alert(1)</script>"},  # text, drawn as text: never HTML
            {"kind": "h", "level": 2, "text": "End"},
        ])
        self.assertEqual(out["runs"], [{"kind": "text", "text": "Run "}, {"kind": "code", "text": "npm test"}, {"kind": "text", "text": " and "},
                                       {"kind": "strong", "text": "then"}, {"kind": "text", "text": " go"}])


class ToldAsItStartsTest(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.data = os.path.join(self.base, "data")
        self.shop = os.path.realpath(os.path.join(self.base, "shop"))
        os.makedirs(os.path.join(self.data, "howtos"))
        os.makedirs(self.shop)
        company = {"company": "Example", "floors": [{"id": "shop", "label": "Shop", "project": "Shop", "folder": self.shop}],
                   "howtos": [{"id": "till", "title": "Count the till", "file": "howtos/till.md", "project": "Shop"},
                              {"id": "notes", "title": "Write release notes", "file": "howtos/notes.md"},
                              {"id": "lab", "title": "Mix the paint", "file": "howtos/lab.md", "project": "Lab"},
                              {"id": "gone", "title": "Not there", "file": "howtos/gone.md"},
                              {"id": "out", "title": "Outside", "file": "../outside.md"}]}
        with open(os.path.join(self.data, "company.json"), "w", encoding="utf-8") as handle:
            json.dump(company, handle)
        for name in ("till.md", "notes.md", "lab.md"):
            with open(os.path.join(self.data, "howtos", name), "w", encoding="utf-8") as handle:
                handle.write("# A how-to\n")
        with open(os.path.join(self.base, "outside.md"), "w", encoding="utf-8") as handle:
            handle.write("# Outside\n")
        self.env = {**os.environ, "ARNHEIM_DATA": self.data}

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def start(self, cwd):
        event = {"session_id": "abc123def456-7890", "cwd": cwd, "hook_event_name": "SessionStart", "source": "startup"}
        done = subprocess.run([sys.executable, HOOK], input=json.dumps(event), capture_output=True, text=True, env=self.env, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)["hookSpecificOutput"]["additionalContext"] if done.stdout.strip() else None

    def test_its_floors_how_tos(self):
        said = self.start(self.shop)
        data = os.path.realpath(self.data)
        self.assertIn(f'"Count the till" ({os.path.join(data, "howtos", "till.md")})', said)
        self.assertIn(f'"Write release notes" ({os.path.join(data, "howtos", "notes.md")})', said)
        for other in ("Mix the paint", "Not there", "Outside"):  # another floor's, a missing file, outside data/
            self.assertNotIn(other, said)
        elsewhere = os.path.join(self.base, "elsewhere")
        os.makedirs(elsewhere)
        self.assertIsNone(self.start(elsewhere))  # not this company's work: nothing


if __name__ == "__main__":
    unittest.main()
