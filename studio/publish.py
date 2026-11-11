"""Copies the baked floors the live building uses into ../baked/, where the page server shows them, with an
index (building.json): which floor serves which part of the building, the kit, and the sun they were baked in.

python3 studio/publish.py
"""
import json
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
DEST = os.path.join(os.path.dirname(HERE), "baked")
SHELLS = {"floor": "studio-shell", "lobby": "lobby-shell"}  # every project floor is the one baked studio floor


def copy_tree(name):
    src = os.path.join(OUT, "viewer", name)
    dst = os.path.join(DEST, name)
    if os.path.exists(dst):
        shutil.rmtree(dst)
    os.makedirs(dst)
    for f in sorted(os.listdir(src)):
        if f.endswith((".bin", ".jpg", ".json")):
            shutil.copy2(os.path.join(src, f), os.path.join(dst, f))


def main():
    os.makedirs(DEST, exist_ok=True)
    shells = {}
    for role, name in SHELLS.items():
        if os.path.exists(os.path.join(OUT, "viewer", name, "floor.json")):
            copy_tree(name)
            shells[role] = name + "/"
        else:
            print("not baked yet:", name)
    copy_tree("kit")
    people = os.path.exists(os.path.join(OUT, "viewer", "people", "people.json"))
    if people:
        copy_tree("people")
    sun = json.load(open(os.path.join(OUT, "sun.json")))["sun_direction_plan"]
    index = {"about": "Arnheim's photo-real floors (studio/), as the live building loads them (src/photo-building.js). "
                      "Each project floor is the same baked floor; the sun is the direction they were baked in, plan axes.",
             "shells": shells, "kit": "kit/", "people": "people/" if people else None, "sun": sun}
    json.dump(index, open(os.path.join(DEST, "building.json"), "w"), indent=1)
    total = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(DEST) for f in fs)
    print("published", shells, f"{total / 1e6:.1f} MB to", DEST)


main()
