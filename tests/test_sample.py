"""The sample company's files hang together, so the demo always has something whole to show: every
project has a floor, every name in work.json points at something that is there, and every value is
one the page knows. docs/data.md describes the same rules for your own company.

Run from the repository's folder: python3 -m unittest discover tests
"""
import json
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ID = re.compile(r"^[A-Za-z0-9_-]+$")
PALETTES = {"terracotta", "harbour", "sage", "indigo", "plum", "teal", "sand", "slate"}
TASK = {"needs_you", "working", "waiting", "open", "done", "dropped"}
GOAL = {"open", "reached"}
JOB = {"queued", "running", "done"}
PRESENCE = {"website", "email", "social", "domain"}
SECTIONS = {"Money", "Legal", "Subscriptions", "Key dates"}


def read(name):
    with open(os.path.join(ROOT, "sample", name), encoding="utf-8") as handle:
        return json.load(handle)


class SampleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.map, cls.work, cls.notes = read("company.json"), read("work.json"), read("notes.json")
        cls.storeys = [*cls.map["floors"], cls.map["lobby"], cls.map["basement"]]

    def test_it_says_it_is_made_up(self):
        self.assertTrue(self.map["sample"])

    def test_floors_and_rooms(self):
        ids = [s["id"] for s in self.storeys]
        self.assertEqual(len(ids), len(set(ids)))
        for storey in self.storeys:
            self.assertRegex(storey["id"], ID)
            self.assertTrue(storey["label"])
            rooms = [*(storey.get("rooms") or self.map["rooms"]), *storey.get("extraRooms", [])]
            self.assertLessEqual(len(rooms), 5, storey["id"])
            for room in rooms:
                self.assertRegex(room["id"], ID)
                self.assertTrue(room["label"] and room["about"])
        for floor in self.map["floors"]:
            self.assertIn(floor["palette"], PALETTES)

    def test_everything_is_on_a_floor(self):
        projects = {f.get("project") or f["label"] for f in self.map["floors"]}
        for key in ("tasks", "goals", "conversations", "pullRequests", "copies", "presence"):
            for item in self.work[key]:
                self.assertIn(item["project"], projects, f"{key}: {item}")

    def test_values_the_page_knows(self):
        self.assertTrue(all(t["status"] in TASK for t in self.work["tasks"]))
        self.assertTrue(all(g["status"] in GOAL for g in self.work["goals"]))
        self.assertTrue(all(j["state"] in JOB for j in self.work["jobs"]))
        self.assertTrue(all(p["type"] in PRESENCE for p in self.work["presence"]))
        self.assertTrue(all(c["section"] in SECTIONS for c in self.work["company"]))
        machines = {r["id"] for r in self.map["basement"]["rooms"] if r["id"] != "library"}
        self.assertTrue(all(m["id"] in machines for m in self.work["machines"]))
        self.assertTrue(all(j["machine"] in machines for j in self.work["jobs"]))

    def test_the_story_changes_things_that_are_there(self):
        for step in self.work["story"]:
            self.assertTrue(step["line"])
            for name, key, patch in step["change"]:
                self.assertTrue(any(x["id"] == key for x in self.work[name]), f"{name} {key}")
                self.assertIsInstance(patch, dict)

    def test_notes(self):
        self.assertTrue(self.notes["notes"])
        for note in self.notes["notes"]:
            self.assertTrue(note["id"] and (note.get("title") or note.get("text") or note.get("locked")), note["id"])


if __name__ == "__main__":
    unittest.main()
