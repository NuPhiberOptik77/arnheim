"""Exports people for the live building, built by people.py (the same code as the photographs), seated the way
the live building seats them, slimmed like the viewer's people (bake.slim, hair as solid hulls), with their colours
baked into textures. Each person is two parts: the body, and the head about a pivot at the top of the neck, so the
live building can let them breathe and turn their heads.

Blender -b --factory-startup --python blender/people_export.py -- [--company COMPANY.json | --looks LOOKS.json] [--out DIR]
Without either: the sample company's receptionist and assistant and a set of agents, into out/viewer/people/.
--company: only that company file's receptionist and assistant (the agents come from the sample set). A private
company's people go to a folder of their own with --out, never into this repository.
LOOKS.json: {"people": [{"name": "...", "look": {company-file look} or "agent": "an id", "kind": "desk" | "chat",
"seat": 0.5, "table": 0.74, "reach": 0.4, "hands": "table"}]}. A company-file look is dressed the way furnish.py
dresses the assistant and receptionist.
people.json keeps, for each person made from a company file, the look they were made from, so the live building
uses them only for a company that gives the same look (src/photo-building.js), and draws anyone else.
"""
import json
import os
import sys

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bake  # noqa: E402
import kit  # noqa: E402
import kit_export as KE  # noqa: E402
import people  # noqa: E402

STUDIO = os.path.dirname(HERE)
AGENTS = 6  # agents' looks; the live building picks one by the work's id


def options():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    o = {"looks": "", "company": "", "out": os.path.join(STUDIO, "out", "viewer", "people")}
    for i, a in enumerate(argv):
        if a.startswith("--") and a[2:] in o and i + 1 < len(argv):
            o[a[2:]] = argv[i + 1]
    return o


def company_people(path=os.path.join(os.path.dirname(STUDIO), "sample", "company.json"), agents=True):
    org = json.load(open(path))
    out = []
    r = org.get("receptionist")
    if r:
        out.append({"name": "receptionist", "look": r.get("look", {}), "dress": "receptionist", "kind": "desk", "seat": 0.52, "table": 0.76, "reach": 0.345})
    a = org.get("assistant")
    if a:  # the founder's assistant, at their desk in the founder's office
        out.append({"name": "assistant", "look": a.get("look", {}), "dress": "assistant", "kind": "desk", "seat": 0.52, "table": 0.75, "reach": 0.345})
    for i in range(AGENTS if agents else 0):  # as furnish.py seats them: at a desk on a task chair, and on a chair at the meeting table
        for kind, seat, reach in (("desk", 0.52, 0.345), ("chat", 0.47, 0.31)):
            out.append({"name": f"agent-{i}-{kind}", "agent": f"agent {i}", "kind": kind, "seat": seat, "table": 0.74, "reach": reach})
    return out


def look_of(p):
    if "agent" in p:
        return people.agent_look(p["agent"])
    look = people.assistant_look(p.get("look", {}))
    if p.get("dress") == "receptionist":
        look = {**look, "trousers": "#2B2A2E"}
    elif p.get("dress") == "assistant":
        look = {**look, "trousers": "#3A4456"}  # as furnish.everyone dresses the assistant
    extra = {k: p["look"][k] for k in ("collar", "nod") if k in p.get("look", {})}
    if not isinstance(extra.get("collar", 0), int):  # a company file's "round" collar is a cardigan's: one low row, no stand
        extra["collar"] = 1
    return {**look, **extra}


def web_ready(objs, hulls):
    """The people's parts as the viewer slims them: strand hair as a hull, clear parts left out, meshes decimated."""
    out = []
    for ob in objs:
        if ob.name.startswith(bake.LEAVE_OUT):
            continue
        if ob.type == "CURVES" and ob.name.split(".")[0] in ("hair", "bun"):
            cap = next((o for o in objs if o.name.startswith("hair cap")), None)
            hull = bake.hair_hull(ob, cap.material_slots[0].material if cap else None, hulls)
            for k in ("part", "pivot"):
                if k in ob.keys():
                    hull[k] = ob[k]
            ob = hull
        elif ob.type != "MESH":
            continue
        slim(ob)
        out.append(ob)
    return out


LIVE_TRIS = {"head": 9000, "hands": 3000, "hair hull": 6000}  # lighter than the viewer's: a floor may seat a dozen


def slim(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    me = ob.evaluated_get(dg).to_mesh()
    me.calc_loop_triangles()
    n = len(me.loop_triangles)
    ob.evaluated_get(dg).to_mesh_clear()
    want = LIVE_TRIS.get(ob.name.split(".")[0], 3000)
    if n > want:
        ob.modifiers.new("slim", "DECIMATE").ratio = want / n


def write_part(ob, out_dir, slug, origin):
    ob.data.transform(__import__("mathutils").Matrix.Translation(-__import__("mathutils").Vector(origin)))
    bake.lightmap_uv(ob)
    image = KE.bake_colour(ob, 1024)
    image.filepath_raw = os.path.join(out_dir, slug + ".jpg")
    image.file_format = "JPEG"
    image.save()
    pos, nrm, uv, idx = KE.mesh_data(ob)
    with open(os.path.join(out_dir, slug + ".bin"), "wb") as f:
        f.write(np.hstack([pos, nrm, uv]).astype(np.float32).tobytes())
        f.write(idx.tobytes())
    lo, hi = pos.min(axis=0), pos.max(axis=0)
    print("PERSON PART", slug, len(idx) // 3, "triangles", flush=True)
    return {"bin": slug + ".bin", "image": slug + ".jpg", "vertices": int(len(pos)), "indices": int(len(idx)),
            "box": [[round(float(v), 3) for v in lo], [round(float(v), 3) for v in hi]]}


def main():
    o = options()
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.view_settings.view_transform = "Standard"
    os.makedirs(o["out"], exist_ok=True)
    wanted = (json.load(open(o["looks"]))["people"] if o["looks"]
              else company_people(o["company"], agents=False) if o["company"] else company_people())
    hulls = kit.collection("people hulls")
    manifest = {"about": "People for the live building (blender/people_export.py): each a body and a head, float32 positions, normals and uv "
                         "(n x 8) then uint32 indices, three.js axes, metres, the middle of their seat at the origin, facing +z. "
                         "The head's points are about its pivot (the top of the neck), given in the body's frame.",
                "people": {}}
    for p in wanted:
        col = kit.collection(f"person {p['name']}")
        root = bpy.data.objects.new(f"person {p['name']}", None)  # bake.person_of looks for a parent named "person"
        col.objects.link(root)
        objs = people.person(col, look_of(p), p.get("kind", "desk"), p.get("seat", 0.5), p.get("table", 0.74), p.get("reach", 0.42),
                             seed=people.identity(p["name"]) % 1000, hands=p.get("hands", "table"))
        for ob in objs:
            ob.parent = root
        bpy.context.view_layer.update()
        parts = web_ready([ob for ob in objs], hulls)
        head = [ob for ob in parts if ob.get("part") == "head"]
        body = [ob for ob in parts if ob.get("part") != "head"]
        pivot = list(head[0]["pivot"]) if head else [0.0, 0.0, 1.1]
        entry = {"kind": p.get("kind", "desk"), "seat": p.get("seat", 0.5), "pivot": [round(pivot[0], 4), round(pivot[2], 4), round(-pivot[1], 4)]}
        if "agent" not in p:
            entry["look"] = p.get("look", {})  # the company file's look, as given: the live building matches on it
        entry["body"] = write_part(bake.flatten(body, f"{p['name']} body", col), o["out"], f"{p['name']}-body", (0, 0, 0))
        if head:
            entry["head"] = write_part(bake.flatten(head, f"{p['name']} head", col), o["out"], f"{p['name']}-head", pivot)
        manifest["people"][p["name"]] = entry
    json.dump(manifest, open(os.path.join(o["out"], "people.json"), "w"), indent=1)
    print("WROTE", os.path.join(o["out"], "people.json"), flush=True)


main()
