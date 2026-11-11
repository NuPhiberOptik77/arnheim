"""Exports the live building's kit: every piece the live building places from the company's data (a desk per
task, a seat per conversation, a book per open change...), built by the same code as the photographs
(pieces.py), with its surface colours baked into a texture so three.js can light it live, in the sun's
measured direction. Parts that change with the data (a screen's glow, a flag's colour, a website's page)
are exported on their own, to be coloured live.

Blender -b --factory-startup --python blender/kit_export.py
Writes out/viewer/kit/: kit.json, and per part a .bin (positions, normals, uv as float32, then uint32
indices; three.js axes, metres, the piece standing on y=0 and facing -z) and a .jpg of its colours.
"""
import json
import math
import os
import sys

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bake  # noqa: E402
import kit  # noqa: E402
import materials as M  # noqa: E402
import pieces as P  # noqa: E402

OUT = os.path.join(os.path.dirname(HERE), "out", "viewer", "kit")


def at(objs, x=0.0, y=0.0, z=0.0, rot=0.0, col=None):
    root = kit.place(objs, (x, y, z), rot, "part", col)
    return [root] + list(root.children_recursive)


def meshes(objs):
    return [o for o in objs if o.type in ("MESH", "FONT")]


# Each piece: parts built facing -Y (the plan's south, three.js -z), standing on z=0. "live" parts are coloured
# by the live building (no texture), the rest carry their baked colours.
def desk(col):
    return {"body": P.table(col, 1.6, 0.8, 0.74, top="oak", legs="black", style="four", tone="#C9A882")
            + at(P.keyboard(col), 0.0, 0.12, 0.74, math.pi, col) + at(P.mouse(col), 0.3, 0.12, 0.74, math.pi, col)}


def desk_chair(col):
    return {"body": P.task_chair(col, "#3F4743")}


def monitor(col):
    parts = P.monitor(col, 0.61, on=False)
    return {"body": parts[1:], "screen": parts[:1]}


def site_screen(col):
    parts = P.site_screen(col, 0.95, 0.56, on=False)
    return {"body": parts[:1], "page": parts[1:]}


def book(col):
    return {"body": [P.rbox("book", (-0.015, -0.09, 0.0), (0.015, 0.09, 0.24), col, M.matte("#F2EEE6", 0.7), 0.002)]}


def server_rack(col):
    parts = P.server_rack(col, lit=False, seed=1)
    lights = [o for o in parts if o.name.startswith("status light")]
    return {"body": [o for o in parts if o not in lights], "lights": lights}


PIECES = {
    "desk": desk,
    "desk chair": desk_chair,
    "monitor": monitor,
    "seat": lambda col: {"body": P.shell_chair(col, "#8C7A66")},
    "bookcase": lambda col: {"body": P.bookcase(col, 1.5, 2.4, 0.34, 2, 6, filled=False)},
    "book": book,
    "crate": lambda col: {"body": P.crate(col, 0.45, 0.32, 0.28, tone="#9C7550", seed=1)},
    "goals board": lambda col: {"body": P.goals_board(col, [], 1.3, 1.0)},
    "website screen": site_screen,
    "filing cabinet": lambda col: {"body": P.filing_cabinet(col, 0.55, 0.45, 1.02, drawers=3)},
    # what stands on a desk in use: pale, so the live building can colour each one (a mug, a notebook)
    "mug": lambda col: {"body": P.mug(col, "#F2EEE6")},
    "notebook": lambda col: {"body": P.notebook(col, "#F2EEE6")},
    "desk lamp": lambda col: {"body": P.task_lamp(col)},
    "laptop": lambda col: {"body": P.laptop(col, open_=False)},
    "server rack": server_rack,
}
LIVE_PARTS = {"screen", "page", "lights"}


def mesh_data(ob):
    """Positions, normals and the colour map's coordinates, per corner, merged where all three agree."""
    me = ob.data
    me.calc_loop_triangles()
    n = len(me.loop_triangles)
    loops = np.zeros(n * 3, dtype=np.int64)
    me.loop_triangles.foreach_get("loops", loops)
    vidx = np.zeros(len(me.loops), dtype=np.int64)
    me.loops.foreach_get("vertex_index", vidx)
    co = np.zeros(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    nor = np.zeros(len(me.loops) * 3)
    me.corner_normals.foreach_get("vector", nor)
    uv = np.zeros(len(me.loops) * 2)
    me.uv_layers["lightmap"].data.foreach_get("uv", uv)
    p, nn, t = co.reshape(-1, 3)[vidx[loops]], nor.reshape(-1, 3)[loops], uv.reshape(-1, 2)[loops]
    rows = np.hstack([np.round(p, 4), np.round(nn, 3), np.round(t, 6)])
    uniq, inv = np.unique(rows, axis=0, return_inverse=True)
    pos = np.stack([uniq[:, 0], uniq[:, 2], -uniq[:, 1]], axis=1).astype(np.float32)
    nrm = np.stack([uniq[:, 3], uniq[:, 5], -uniq[:, 4]], axis=1).astype(np.float32)
    return pos, nrm, uniq[:, 6:8].astype(np.float32), inv.reshape(-1).astype(np.uint32)


def bake_colour(ob, px):
    """The surface colours (what the procedural materials paint, without light) into a texture."""
    image = bpy.data.images.new(f"kit {ob.name}", px, px)
    for slot in ob.material_slots:
        if not slot.material:
            continue
        nt = slot.material.node_tree
        node = nt.nodes.new("ShaderNodeTexImage")
        node.image = image
        for nd in nt.nodes:
            nd.select = False
        node.select = True
        nt.nodes.active = node
    bake.only_select(ob)
    sc = bpy.context.scene
    sc.cycles.samples = 4
    with bpy.context.temp_override(active_object=ob, object=ob, selected_objects=[ob], selected_editable_objects=[ob]):
        bpy.ops.object.bake(type="DIFFUSE", pass_filter={"COLOR"}, margin=4, use_clear=True)
    return image


def main():
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.view_settings.view_transform = "Standard"  # colours as painted: no filmic curve on a texture
    os.makedirs(OUT, exist_ok=True)
    manifest = {"about": "The live building's kit (blender/kit_export.py): pieces placed from the company's data. Each part: a .bin of float32 positions, normals and uv (n x 8), then uint32 indices; three.js axes, metres, standing on y=0, facing -z. Parts named in 'live' carry no colours: the live building colours them.",
                "live": sorted(LIVE_PARTS), "pieces": {}}
    for name, make in PIECES.items():
        col = kit.collection(f"kit {name}")
        parts = make(col)
        bpy.context.view_layer.update()
        entry = {}
        for part, objs in parts.items():
            obs = meshes(list(dict.fromkeys(o for ob in objs for o in [ob] + list(ob.children_recursive))))
            ob = bake.flatten(obs, f"{name} {part}", col)
            bake.lightmap_uv(ob)
            slug = f"{name}-{part}".replace(" ", "-")
            img = None
            if part not in LIVE_PARTS:
                image = bake_colour(ob, 512)
                image.filepath_raw = os.path.join(OUT, slug + ".jpg")
                image.file_format = "JPEG"
                image.save()
                img = slug + ".jpg"
            pos, nrm, uv, idx = mesh_data(ob)
            with open(os.path.join(OUT, slug + ".bin"), "wb") as f:
                f.write(np.hstack([pos, nrm, uv]).astype(np.float32).tobytes())
                f.write(idx.tobytes())
            lo, hi = pos.min(axis=0), pos.max(axis=0)
            entry[part] = {"bin": slug + ".bin", "image": img, "vertices": int(len(pos)), "indices": int(len(idx)),
                           "box": [[round(float(v), 3) for v in lo], [round(float(v), 3) for v in hi]]}
            print("KIT", name, part, len(idx) // 3, "triangles", flush=True)
        manifest["pieces"][name] = entry
    json.dump(manifest, open(os.path.join(OUT, "kit.json"), "w"), indent=1)
    print("WROTE", os.path.join(OUT, "kit.json"), flush=True)


if __name__ == "__main__":  # people_export.py borrows the helpers above
    main()
