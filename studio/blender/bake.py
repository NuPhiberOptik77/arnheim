"""Bakes the floor's light into textures with Cycles and writes what the three.js viewer loads.

Run through build.py once the scene is built:
    Blender -b --factory-startup --python blender/build.py -- --bake [--bake-size 2048] [--bake-samples 256]
        [--bake-only GROUP,GROUP]

Every room's objects (with their modifiers applied) are joined into one mesh, given a lightmap layout and
baked: diffuse light, direct and indirect, with colour, emission and light through leaves, but no
reflections, since a texture can't hold what changes as you move. The view out of the windows is baked as one
panorama from the middle of the floor, with the inside hidden.

People get a group of their own in each room, slimmed for a web page (heads about 16,000 triangles), their
strand hair turned into a solid shape, baked at twice the room's texel density with the full-detail originals
hidden so the slimmed copies don't shade themselves. Each group's lightmap is saved at its room's photo exposure
(rooms without a photo take the floor's most common one), so a room in the viewer looks as it does in its photo.

Writes out/viewer/ (another floor than the studio's: out/viewer/<floor>/): floor.json, one .bin of triangles and one .jpg lightmap per room group, glass.bin and
outside.jpg. Coordinates are three.js ones: y up, x as the plan's x, z as minus the plan's y.
"""
import json
import math
import os
import time

import bpy
import numpy as np

import shell


def room_of(plan, x, y):
    for r in plan["rooms"]:
        if shell.inside(r["polygon"], x, y):
            return r
    return None


def nearest_room(plan, x, y):
    best, bd = None, 1e9
    for r in plan["rooms"]:
        xs = [p[0] for p in r["polygon"]]
        ys = [p[1] for p in r["polygon"]]
        dx = max(min(xs) - x, 0, x - max(xs))
        dy = max(min(ys) - y, 0, y - max(ys))
        d = math.hypot(dx, dy)
        if d < bd:
            best, bd = r, d
    return best


def world_box(ob):
    from mathutils import Vector
    pts = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    lo = [min(p[i] for p in pts) for i in range(3)]
    hi = [max(p[i] for p in pts) for i in range(3)]
    return lo, hi


def slug(name):
    return name.lower().replace("'", "").replace(" ", "-")


PEOPLE_TRIS = {"head": 16000, "hands": 5000, "hair hull": 9000}  # triangles each in the viewer; any other part of a person 6000
LEAVE_OUT = ("cornea",)  # clear: a lightmap can't show what is behind it


def person_of(ob):
    p = ob.parent
    while p:
        if p.name.startswith("person"):
            return p
        p = p.parent
    return None


def hair_hull(curves_ob, material, col, voxel=0.0025, radius=0.003):
    """Strand hair as a solid shape for the viewer: every strand's points to a volume, the volume to a surface."""
    ng = bpy.data.node_groups.new("hair hull", "GeometryNodeTree")
    ng.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    N, L = ng.nodes, ng.links
    out = N.new("NodeGroupOutput")
    info = N.new("GeometryNodeObjectInfo")
    info.inputs["Object"].default_value = curves_ob
    info.transform_space = "RELATIVE"
    pts = N.new("GeometryNodeCurveToPoints")
    pts.mode = "EVALUATED"
    vol = N.new("GeometryNodePointsToVolume")
    vol.inputs["Resolution Mode"].default_value = "Size"
    vol.inputs["Voxel Size"].default_value = voxel
    vol.inputs["Radius"].default_value = radius
    mesh = N.new("GeometryNodeVolumeToMesh")
    mat = N.new("GeometryNodeSetMaterial")
    mat.inputs["Material"].default_value = material
    L.new(info.outputs["Geometry"], pts.inputs[0])
    L.new(pts.outputs["Points"], vol.inputs["Points"])
    L.new(vol.outputs[0], mesh.inputs[0])
    L.new(mesh.outputs[0], mat.inputs["Geometry"])
    L.new(mat.outputs[0], out.inputs[0])
    ob = bpy.data.objects.new("hair hull", bpy.data.meshes.new("hair hull"))
    col.objects.link(ob)
    ob.matrix_world = curves_ob.matrix_world.copy()
    ob.modifiers.new("hull", "NODES").node_group = ng
    return ob


def slim(ob):
    """A decimate on the viewer's copy of a person's part, down to its share of triangles."""
    dg = bpy.context.evaluated_depsgraph_get()
    me = ob.evaluated_get(dg).to_mesh()
    me.calc_loop_triangles()
    n = len(me.loop_triangles)
    ob.evaluated_get(dg).to_mesh_clear()
    want = PEOPLE_TRIS.get(ob.name.split(".")[0], 6000)
    if n > want:
        d = ob.modifiers.new("slim", "DECIMATE")
        d.ratio = want / n


def live_of(ob):
    """The live kind of the piece ob belongs to (furnish.put(live=...)), or None."""
    p = ob
    while p:
        if "live" in p.keys():
            return p["live"]
        p = p.parent
    return None


def group_of(ob):
    """The group a piece asks to be baked in, if any (lift.py's doors, which the live building moves)."""
    p = ob
    while p:
        if "group" in p.keys():
            return p["group"]
        p = p.parent
    return None


def gather(plan, shell=False):
    """Every mesh that can be seen from inside the floor, sorted into a group per room, plus the glass. People go
    in a group of their own per room ("WORK PEOPLE"), with their strand hair as solid hulls; returns the people's
    full-detail originals too, to hide while the slimmed copies bake."""
    bpy.context.view_layer.update()  # pieces are parented to placed empties: bring every world matrix up to date first
    groups, glass, originals = {}, [], []
    hulls = bpy.data.collections.new("viewer hair")
    bpy.context.scene.collection.children.link(hulls)
    for col_name in ("shell", "furniture"):
        col = bpy.data.collections.get(col_name)
        if not col:
            continue
        for ob in list(col.all_objects):
            who = person_of(ob)
            if shell and (who is not None or live_of(ob)):  # the live building draws these itself, from the company's data
                ob.hide_render = True
                continue
            if who is not None:
                originals.append(ob)
                if ob.name.startswith(LEAVE_OUT):
                    continue
                if ob.type == "CURVES" and ob.name.split(".")[0] in ("hair", "bun"):
                    cap = next((o for o in who.children_recursive if o.name.startswith("hair cap")), None)
                    ob = hair_hull(ob, cap.material_slots[0].material if cap else None, hulls)
                elif ob.type != "MESH":
                    continue
                slim(ob)
                r = room_of(plan, who.location.x, who.location.y) or nearest_room(plan, who.location.x, who.location.y)
                groups.setdefault(r["name"] + " PEOPLE", []).append(ob)
                continue
            if ob.type not in ("MESH", "FONT"):
                continue
            lo, hi = world_box(ob)
            if hi[2] < 0.0 or ob.name.startswith(("ground", "paving", "slab")):
                continue  # under the floor or outside: not seen from in here
            mats = [s.material.name for s in ob.material_slots if s.material]
            if any(m.startswith("window_glass") for m in mats):
                glass.append(ob)
                continue
            if group_of(ob):
                groups.setdefault(group_of(ob), []).append(ob)
                continue
            cx, cy = (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2
            r = room_of(plan, cx, cy) or nearest_room(plan, cx, cy)
            groups.setdefault(r["name"], []).append(ob)
    return groups, glass, originals


def flatten(objs, name, col):
    """One mesh object made of the evaluated (modifiers applied) copies of objs, in world space."""
    dg = bpy.context.evaluated_depsgraph_get()
    parts = []
    for ob in objs:
        ev = ob.evaluated_get(dg)
        me = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=dg)
        me.transform(ob.matrix_world)
        if len(me.polygons) == 0:
            bpy.data.meshes.remove(me)
            continue
        part = bpy.data.objects.new(f"{name}.{len(parts)}", me)
        col.objects.link(part)
        parts.append(part)
    with bpy.context.temp_override(active_object=parts[0], object=parts[0], selected_objects=parts, selected_editable_objects=parts):
        bpy.ops.object.join()
    joined = parts[0]
    joined.name = name
    return joined


def lightmap_uv(ob):
    me = ob.data
    uv = me.uv_layers.new(name="lightmap")
    keep = me.uv_layers[0].name if me.uv_layers[0].name != "lightmap" else None
    me.uv_layers.active = uv
    if keep:
        me.uv_layers[keep].active_render = True
    only_select(ob)
    bpy.ops.object.mode_set(mode="EDIT")
    with bpy.context.temp_override(edit_object=ob, active_object=ob, object=ob):
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.0008, area_weight=0.0, correct_aspect=True, scale_to_bounds=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    return uv


def only_select(ob):
    vl = bpy.context.view_layer
    for o in vl.objects:
        o.select_set(False)
    ob.select_set(True)
    vl.objects.active = ob


def bake_group(ob, image, samples):
    sc = bpy.context.scene
    for slot in ob.material_slots:
        m = slot.material
        if not m:
            continue
        nt = m.node_tree
        node = nt.nodes.get("lightmap target") or nt.nodes.new("ShaderNodeTexImage")
        node.name = "lightmap target"
        node.image = image
        for n in nt.nodes:
            n.select = False
        node.select = True
        nt.nodes.active = node
    # metal has no diffuse colour, so a diffuse bake would leave brass letters and rings black: bake them as a
    # matte surface of their own colour, then put the metal back
    metals = []
    for slot in ob.material_slots:
        for n in (slot.material.node_tree.nodes if slot.material else []):
            met = n.inputs.get("Metallic") if n.type == "BSDF_PRINCIPLED" else None
            if met is not None and not met.is_linked and met.default_value > 0.5:
                metals.append((met, met.default_value))
                met.default_value = 0.0
    sc.cycles.samples = samples
    sc.render.bake.use_pass_direct = True
    sc.render.bake.use_pass_indirect = True
    sc.render.bake.margin = 4
    only_select(ob)
    with bpy.context.temp_override(active_object=ob, object=ob, selected_objects=[ob], selected_editable_objects=[ob]):
        bpy.ops.object.bake(type="COMBINED", pass_filter={"EMIT", "DIRECT", "INDIRECT", "DIFFUSE", "TRANSMISSION"},
                            margin=4, use_clear=True)
    for met, v in metals:
        met.default_value = v


def save_jpeg(image, path):
    sc = bpy.context.scene
    sc.render.image_settings.file_format = "JPEG"
    sc.render.image_settings.quality = 92
    image.save_render(filepath=path, scene=sc)  # through the same view transform and exposure as the photos


def triangles(ob, uv_name="lightmap"):
    """Indexed triangles: positions in three.js axes and lightmap coordinates."""
    me = ob.data
    me.calc_loop_triangles()
    n = len(me.loop_triangles)
    loops = np.zeros(n * 3, dtype=np.int64)
    me.loop_triangles.foreach_get("loops", loops)
    vidx = np.zeros(len(me.loops), dtype=np.int64)
    me.loops.foreach_get("vertex_index", vidx)
    co = np.zeros(len(me.vertices) * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    uv = np.zeros(len(me.loops) * 2, dtype=np.float64)
    me.uv_layers[uv_name].data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    p = co[vidx[loops]]
    t = uv[loops]
    rows = np.hstack([np.round(p, 4), np.round(t, 6)])
    uniq, inv = np.unique(rows, axis=0, return_inverse=True)
    pos = np.stack([uniq[:, 0], uniq[:, 2], -uniq[:, 1]], axis=1).astype(np.float32)
    return pos, uniq[:, 3:5].astype(np.float32), inv.reshape(-1).astype(np.uint32)


def write_bin(path, pos, uv=None, idx=None):
    with open(path, "wb") as f:
        f.write(pos.tobytes())
        if uv is not None:
            f.write(uv.tobytes())
        if idx is not None:
            f.write(idx.tobytes())


def panorama(out_dir, design, plan, samples=96, width=4096):
    """The view out: an equirectangular render from the middle of the floor at eye height, inside hidden."""
    sc = bpy.context.scene
    hidden = []
    for name in ("shell", "furniture", "baked", "viewer hair"):  # everything inside, the baked copies too, but not the ground and paving below
        col = bpy.data.collections.get(name)
        if not col:
            continue
        for o in list(col.all_objects):  # a copy: changing a flag rebuilds all_objects and would end the loop early
            if not o.hide_render and not o.name.startswith(("ground", "paving")):
                o.hide_render = True
                hidden.append(o)
    cam = bpy.data.cameras.new("panorama")
    cam.type = "PANO"
    cam.panorama_type = "EQUIRECTANGULAR"
    ob = bpy.data.objects.new("panorama", cam)
    sc.collection.objects.link(ob)
    W, D = plan["size"]
    ob.location = (W / 2, D / 2 - 2.0, 1.6)
    ob.rotation_euler = (math.radians(90), 0, math.radians(-90))  # looking along +X, up +Z
    sc.camera = ob
    sc.render.resolution_x, sc.render.resolution_y = width, width // 2
    sc.cycles.samples = samples
    sc.render.image_settings.file_format = "JPEG"
    sc.render.image_settings.quality = 90
    sc.render.filepath = os.path.join(out_dir, "outside.jpg")
    bpy.ops.render.render(write_still=True)
    for o in hidden:
        o.hide_render = False
    return {"image": "outside.jpg", "at": [ob.location.x, ob.location.z, -ob.location.y], "looks_along": "+x"}


def bake_all(plan, design, styles, size=2048, samples=256, only=None, floor="studio", shell=False):
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out", "viewer")
    if floor != "studio":  # every other floor in a folder of its own beside the studio floor's files
        out_dir = os.path.join(out_dir, floor)
    os.makedirs(out_dir, exist_ok=True)
    sc = bpy.context.scene
    groups, glass, originals = gather(plan, shell)
    col = bpy.data.collections.new("baked")
    sc.collection.children.link(col)
    manifest = {"about": f"Arnheim, the {floor} floor, light baked with Cycles. Coordinates: y up, x the plan's x, z minus the plan's y. "
                         "Each group's lightmap went through its room's photo exposure (exposure_ev on the group).",
                "floor": {"id": floor, "level": design.get("floor", {}).get("level", 0), "shell": shell,
                          "ceiling": design["heights"]["ceiling"]},
                "rooms": [{"name": r["name"], "polygon": [[round(x, 3), round(-y, 3)] for x, y in r["polygon"]]} for r in plan["rooms"]],
                "slots": [],
                "exposure_ev": None, "groups": [], "glass": None, "cameras": [], "outside": None}
    # each room's photo settings; a room with no photo takes the floor's most common exposure
    shots = {r: st["cameras"][0] for r, st in styles.items() if isinstance(st, dict) and st.get("cameras")}
    evs = [c.get("exposure", 0.0) for c in shots.values()]
    common = max(set(evs), key=evs.count) if evs else 0.0
    # rooms first, with the people's originals in the scene so they shade the rooms; then the people's slimmed copies
    for name, objs in sorted(groups.items(), key=lambda kv: (kv[0].endswith(" PEOPLE"), kv[0])):
        if only and name not in only:
            continue
        people = name.endswith(" PEOPLE")
        room = name[:-len(" PEOPLE")] if people else name
        for o in originals:
            o.hide_render = people
        shot = shots.get(room, {})
        sc.view_settings.exposure = shot.get("exposure", common)
        sc.view_settings.look = shot.get("grade", "AgX - Medium High Contrast")
        sc.view_settings.white_balance_temperature = shot.get("wb", 5100)
        t0 = time.time()
        ob = flatten(objs, f"baked {slug(name)}", col)
        lightmap_uv(ob)
        area = sum(p.area for p in ob.data.polygons)
        # about 200 texels a metre (5 mm) once islands fill ~55% of the square (people 400, 2.5 mm), in powers of two up to the cap
        need = math.sqrt(area * (400.0 if people else 200.0) ** 2 / 0.55)
        px = 1024
        while px < need and px < size:
            px *= 2
        image = bpy.data.images.new(f"lightmap {slug(name)}", px, px, float_buffer=True)
        bake_group(ob, image, samples)
        jpg = f"{slug(name)}.jpg"
        save_jpeg(image, os.path.join(out_dir, jpg))
        pos, uv, idx = triangles(ob)
        write_bin(os.path.join(out_dir, f"{slug(name)}.bin"), pos, uv, idx)
        manifest["groups"].append({"name": name, "image": jpg, "bin": f"{slug(name)}.bin", "exposure_ev": round(sc.view_settings.exposure, 2), "vertices": int(len(pos)),
                                   "indices": int(len(idx)), "texture_px": px, "area_m2": round(area, 1),
                                   "seconds": round(time.time() - t0, 1)})
        print("BAKED", name, px, "px", len(idx) // 3, "triangles", round(time.time() - t0, 1), "s", flush=True)
    if glass:
        g = flatten(glass, "baked glass", col)
        g.data.uv_layers.new(name="lightmap")
        pos, _, idx = triangles(g)
        write_bin(os.path.join(out_dir, "glass.bin"), pos, None, idx)
        manifest["glass"] = {"bin": "glass.bin", "vertices": int(len(pos)), "indices": int(len(idx))}
    for r in plan["rooms"]:
        for k, c in enumerate(styles.get(r["name"], {}).get("cameras", [])):
            h = c.get("height", 1.3)
            manifest["cameras"].append({"room": r["name"], "at": [c["at"][0], h, -c["at"][1]], "look": [c["look"][0], h, -c["look"][1]], "lens_mm": c.get("lens", 16)})
    for o in originals:
        o.hide_render = False
    manifest["exposure_ev"] = common
    sc.view_settings.exposure = common
    if not only:
        manifest["outside"] = panorama(out_dir, design, plan)
    path = os.path.join(out_dir, "floor.json")
    if only and os.path.exists(path):
        old = json.load(open(path))
        keep = [g for g in old.get("groups", []) if g["name"] not in only]
        manifest["groups"] = keep + manifest["groups"]
        manifest["outside"] = old.get("outside")
    if shell:  # where the live building puts what comes from the data, in the viewer's coordinates, by room
        import furnish
        for sl in furnish.SLOTS:
            x, y, z = sl["at"]
            r = room_of(plan, x, y) or nearest_room(plan, x, y)
            manifest["slots"].append({**sl, "room": r["name"], "at": [x, z, -y]})
    manifest["baked"] = int(time.time())  # the viewer asks for every file by this, so a cached older file never mixes in
    json.dump(manifest, open(path, "w"), indent=1)
    print("WROTE", path, flush=True)
