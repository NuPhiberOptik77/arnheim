"""The outside of the live building, baked in the same measured sun as the floors: the pavements and kerbs, the two
streets on the corner, the light wells dug round the basement with their railings, a few street trees at the sides,
the slab between the basement and the lobby, and the roof with its parapet, the lift's overrun and the plant on it.

Blender -b --factory-startup --python blender/build.py -- --floor site --bake   (this file: blender/street.py)

Writes out/viewer/site/: floor.json with the groups (GROUND, TREES, ROOF) as the floors' files are, the ground in
the lobby's frame (its floor at y=0, the street 0.15 m below) and the roof in its own (its top at y=0), which the
live building lifts to the top of its stack.
"""
import json
import math
import os
import time

import bpy
from mathutils import Matrix, Vector

import bake
import kit
import materials as M
import pieces as P
import shell

STOREYS = 4            # project floors the baked shadow assumes over the lobby (the live building may have more)
LOBBY_H, FLOOR_H = 3.75, 3.25
ROOF_AT = (1000.0, 0.0)  # the roof is built off to one side, so the ground's sun doesn't fall on it (and back)


def footprint():
    """The building's outline in plan metres: an L, the core and west wing reaching north."""
    return [(0, 0, 24.0, 10.72), (0, 10.72, 10.09, 16.0)]


def build(design_basement):
    col = kit.collection("site")
    massing = kit.collection("massing")
    street = -0.15
    top = LOBBY_H + STOREYS * FLOOR_H
    for k, (x0, y0, x1, y1) in enumerate(footprint()):  # the building itself, only to throw its shadow
        kit.box(f"massing {k}", (x0, y0, street), (x1, y1, top), massing, M.plaster())
    # the light wells, from the basement's own design, moved up to the lobby's frame (the basement's floor 3.6 m down)
    wells = kit.collection("wells")
    H = design_basement["heights"]["ceiling"]
    drop = -shell.street_drop(design_basement)          # the street above the basement's floor
    shell.light_wells(design_basement, 24.0, 16.0, H, drop, wells, streets=False)
    lift = Matrix.Translation((0, 0, street - drop))
    for ob in list(wells.objects):
        ob.matrix_world = lift @ ob.matrix_world
        col.objects.link(ob)
        wells.objects.unlink(ob)
    lw = design_basement.get("light_wells", {})
    wx = -(lw.get("width", 2.4) + 0.3)                  # the wells' outer edge, with the retaining wall
    pave = M.stone("#CFC8BC", "#B9B0A2", 0.6, 0.5)
    kerb = M.stone("#B7AFA3", "#A39A8D", 0.5, 0.8)
    road = M.asphalt()
    z0, z1 = street - 0.3, street
    R = 34.0  # how far the ground goes: past the view's edges from the building view
    # pavements: south and west beyond the wells to the kerbs, east and north to the edge
    kit.box("pavement south", (-7.0, -7.0, z0), (24.0 + 7.0, wx, z1), col, pave)
    kit.box("pavement west", (-7.0, wx, z0), (wx, 16.0 + 7.0, z1), col, pave)
    kit.box("pavement east", (24.0, wx, z0), (24.0 + 7.0, 16.0 + 7.0, z1), col, pave)
    kit.box("pavement north", (wx, 16.0, z0), (24.0, 16.0 + 7.0, z1), col, pave)
    kit.box("pavement notch", (10.09, 10.72, z0), (24.0, 16.0, z1), col, pave)
    kit.box("under the lobby", (0, 0, street - 0.2), (24.0, 10.72, -0.02), col, M.matte("#9C968C", 0.9))
    kit.box("under the lobby", (0, 10.72, street - 0.2), (10.09, 16.0, -0.02), col, M.matte("#9C968C", 0.9))
    # kerbs and the two streets on the corner, the far pavements beyond them
    kit.box("kerb south", (-R, -7.15, street - 0.3), (R + 24.0, -7.0, street), col, kerb)
    kit.box("kerb west", (-7.15, -7.15, street - 0.3), (-7.0, R + 16.0, street), col, kerb)
    kit.box("road south", (-R, -15.0, street - 0.42), (R + 24.0, -7.15, street - 0.12), col, road)
    kit.box("road west", (-15.0, -15.0, street - 0.42), (-7.15, R + 16.0, street - 0.12), col, road)
    for k in range(int((2 * R + 24.0) / 6)):  # the dashed line down the middle of the south street
        x = -R + 1.0 + k * 6.0
        kit.box("road line", (x, -11.13, street - 0.12), (x + 3.0, -11.02, street - 0.115), col, M.matte("#E9E6DE", 0.6))
    kit.box("far pavement south", (-R, -R, street - 0.3), (R + 24.0, -15.0, street), col, pave)
    kit.box("far pavement west", (-R, -15.0, street - 0.3), (-15.0, R + 16.0, street), col, pave)
    kit.box("ground east", (24.0 + 7.0, -7.0, street - 0.3), (R + 24.0, R + 16.0, street - 0.02), col, M.ground())
    kit.box("ground north", (-7.0, 16.0 + 7.0, street - 0.3), (24.0 + 7.0, R + 16.0, street - 0.02), col, M.ground())
    # a few street trees along the sides (none in front: the building view looks in from there)
    for k, (x, y, h, c) in enumerate(((-5.2, 3.0, 7.5, 2.6), (-5.2, 11.0, 8.0, 2.8), (27.5, 2.0, 7.0, 2.5), (27.5, 12.0, 7.6, 2.7))):
        trees = P.street_tree(col, h, c, seed=200 + k)
        root = kit.place(trees, (x, y, street), 0.3 * k, "street tree", col)
        root["group"] = "TREES"
        kit.box("tree pit", (x - 0.6, y - 0.6, street - 0.01), (x + 0.6, y + 0.6, street + 0.005), col, M.matte("#3B2E25", 0.95))
    # a lamp post at each side and a bench by the west wall
    steel = M.matte("#2B2E33", 0.4, 0.5)
    for k, (x, y) in enumerate(((-6.4, 7.0), (30.4, 7.0))):
        kit.place([P.tube("lamp post", [(0, 0, 0), (0, 0, 5.2), (0.6, 0, 5.5)], 0.06, col, steel, 12),
                   kit.box("lamp head", (0.45, -0.12, 5.38), (0.95, 0.12, 5.5), col, steel)], (x, y, street), 0.0 if k == 0 else math.pi, "lamp", col)
    kit.place(P.table(col, 1.8, 0.45, 0.45, top="oak", legs="black", style="four", tone="#8C6E4E"), (-6.0, 15.0, street), math.pi / 2, "bench", col)
    return col


def roof(col):
    """The roof: a pale membrane inside a parapet, the lift's overrun over the core, two condensers and a duct,
    a roof hatch. Built at ROOF_AT with its top surface at z=0."""
    ox, oy = ROOF_AT
    rc = kit.collection("roof")
    membrane = M.matte("#B9B4AC", 0.85)
    cope = M.stone("#D9D3C7", "#C9C1B4", 0.6, 0.6)
    plaster = M.plaster("#E4DFD6")
    for k, (x0, y0, x1, y1) in enumerate(footprint()):
        kit.box(f"roof slab {k}", (ox + x0, oy + y0, -0.35), (ox + x1, oy + y1, 0.0), rc, membrane)
    t, ph = 0.3, 0.9
    # parapets as plain boxes outside the slab's edge
    def wall(a, b):
        kit.box("parapet", (ox + a[0], oy + a[1], -0.35), (ox + b[0], oy + b[1], ph), rc, plaster)
        kit.box("coping", (ox + a[0] - 0.03, oy + a[1] - 0.03, ph), (ox + b[0] + 0.03, oy + b[1] + 0.03, ph + 0.06), rc, cope)
    wall((-t, -t), (24.0 + t, 0))                 # south
    wall((24.0, 0), (24.0 + t, 10.72 + t))        # east
    wall((10.09, 10.72), (24.0, 10.72 + t))       # the notch's south side
    wall((10.09, 10.72), (10.09 + t, 16.0 + t))   # the notch's west side
    wall((-t, 16.0), (10.09, 16.0 + t))           # north
    wall((-t, 0), (0, 16.0 + t))                  # west
    # the lift's overrun over the core, with a louvred door on its south side
    kit.box("lift overrun", (ox + 6.0, oy + 11.6, 0.0), (ox + 10.09, oy + 16.0, 2.4), rc, plaster)
    kit.box("overrun cap", (ox + 5.95, oy + 11.55, 2.4), (ox + 10.14, oy + 16.05, 2.48), rc, cope)
    kit.box("overrun door", (ox + 7.4, oy + 11.57, 0.05), (ox + 8.4, oy + 11.6, 2.05), rc, M.matte("#5B5F64", 0.4, 0.5))
    # two condensers on a frame, a duct to the overrun, a roof hatch, a walkway of pavers
    steel = M.matte("#C9CCD0", 0.35, 0.5)
    dark = M.matte("#2B2E33", 0.45, 0.4)
    for k, x in enumerate((14.0, 16.2)):
        kit.box("condenser frame", (ox + x - 0.1, oy + 6.4, 0.0), (ox + x + 1.9, oy + 8.4, 0.12), rc, dark)
        kit.box("condenser", (ox + x, oy + 6.5, 0.12), (ox + x + 1.8, oy + 8.3, 1.3), rc, steel)
        for j in range(2):
            kit.cylinder("fan", Vector((ox + x + 0.45 + j * 0.9, oy + 7.4, 1.31)), 0.36, 0.02, rc, dark, 32)
    kit.box("duct", (ox + 10.09, oy + 7.2, 0.4), (ox + 14.0, oy + 7.6, 0.8), rc, steel)
    kit.box("roof hatch", (ox + 3.0, oy + 12.0, 0.0), (ox + 4.2, oy + 13.2, 0.45), rc, dark)
    for k in range(10):
        kit.box("paver", (ox + 8.4, oy + 1.0 + k * 1.0, 0.0), (ox + 9.2, oy + 1.8 + k * 1.0, 0.04), rc, M.stone("#CFC8BC", "#B9B0A2", 0.6, 0.5))
    return rc


def bake_site(size=2048, samples=256):
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out", "viewer", "site")
    os.makedirs(out_dir, exist_ok=True)
    sc = bpy.context.scene
    bpy.context.view_layer.update()
    site = bpy.data.collections["site"]
    roofc = bpy.data.collections["roof"]
    groups = {"GROUND": [], "TREES": [], "ROOF": []}
    for ob in site.all_objects:
        if ob.type != "MESH":
            continue
        p, inside_tree = ob, False
        while p:
            if p.get("group") == "TREES":
                inside_tree = True
            p = p.parent
        groups["TREES" if inside_tree else "GROUND"].append(ob)
    groups["ROOF"] = [ob for ob in roofc.all_objects if ob.type == "MESH"]
    col = bpy.data.collections.new("baked")
    sc.collection.children.link(col)
    manifest = {"about": "Arnheim's outside, light baked with Cycles in the floors' sun. GROUND and TREES in the lobby's frame (its floor "
                         "at y=0); ROOF in its own, its top at y=0. Coordinates: y up, x the plan's x, z minus the plan's y.",
                "floor": {"id": "site", "level": 0, "shell": True, "ceiling": 0.0, "storeys": STOREYS},
                "rooms": [], "slots": [], "exposure_ev": sc.view_settings.exposure, "groups": [], "glass": None, "cameras": [], "outside": None}
    for name, objs in groups.items():
        t0 = time.time()
        ob = bake.flatten(objs, f"baked {name.lower()}", col)
        if name == "ROOF":  # back to the building's frame
            ob.data.transform(Matrix.Translation((-ROOF_AT[0], -ROOF_AT[1], 0)))
            ob.location = (ROOF_AT[0], ROOF_AT[1], 0)
        bake.lightmap_uv(ob)
        px = 2048 if name != "TREES" else 1024
        image = bpy.data.images.new(f"lightmap {name}", px, px, float_buffer=True)
        bake.bake_group(ob, image, samples)
        if name == "ROOF":
            ob.location = (0, 0, 0)
        jpg = f"{name.lower()}.jpg"
        bake.save_jpeg(image, os.path.join(out_dir, jpg))
        pos, uv, idx = bake.triangles(ob)
        bake.write_bin(os.path.join(out_dir, f"{name.lower()}.bin"), pos, uv, idx)
        manifest["groups"].append({"name": name, "image": jpg, "bin": f"{name.lower()}.bin", "exposure_ev": round(sc.view_settings.exposure, 2),
                                   "vertices": int(len(pos)), "indices": int(len(idx)), "texture_px": px, "seconds": round(time.time() - t0, 1)})
        print("BAKED", name, px, "px", len(idx) // 3, "triangles", round(time.time() - t0, 1), "s", flush=True)
    manifest["baked"] = int(time.time())
    path = os.path.join(out_dir, "floor.json")
    json.dump(manifest, open(path, "w"), indent=1)
    print("WROTE", path, flush=True)
