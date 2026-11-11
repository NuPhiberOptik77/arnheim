"""A portrait test for the people: one seated person in a plain grey room with a soft window light, shot from
the front, three-quarter and profile, so faces can be checked quickly away from the rooms.

Blender -b --factory-startup --python blender/face_test.py -- OUT_PREFIX [ID]
"""
import math
import os
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kit  # noqa: E402
import materials as M  # noqa: E402
import people  # noqa: E402

a = sys.argv[sys.argv.index("--") + 1:]
out, who = a[0], (a[1] if len(a) > 1 else "cs1")
opts = set(a[2:])  # front: one view only; nosss: no light through the skin; raw: no denoiser
for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
sc = bpy.context.scene
col = kit.collection("test")
kit.box("floor", (-3, -3, -0.01), (3, 3, 0.0), col, M.matte("#8E8A84", 0.7))
kit.box("wall", (-3, 1.2, 0), (3, 1.25, 3), col, M.matte("#B9B4AC", 0.8))
look = people.agent_look(who)
if "shirt" in opts:  # the founder's clothes in the meeting room (design.json)
    look.update(wear="shirt", top="#E8E2D5", build=0.93)
for c_ in ("bun", "long", "short", "cropped"):
    if c_ in opts:
        look["cut"] = c_
if "talk" in opts:
    look["mouth"] = 0.005
objs = people.person(col, look, "chat", seat=0.47, table=0.74, reach=0.3, seed=people.identity(who) % 1000,
                     hands="talk" if "talk" in opts else "table")
kit.place(objs, (0, 0, 0), 0.0, "person", col)
if "noflush" in opts:
    for ob in bpy.data.objects:
        if ob.type == "MESH" and "flush" in ob.data.attributes:
            ob.data.attributes["flush"].data.foreach_set("value", [0.0] * len(ob.data.vertices))
if "nosss" in opts:
    for mat in bpy.data.materials:
        b = mat.node_tree and mat.node_tree.nodes.get("Principled BSDF")
        if b:
            b.inputs["Subsurface Weight"].default_value = 0.0
lamp = bpy.data.lights.new("window", "AREA")
lamp.energy, lamp.size = 450.0, 2.0
lo = bpy.data.objects.new("window", lamp)
sc.collection.objects.link(lo)
lo.location = (-1.6, -1.4, 1.6)
lo.rotation_euler = (Vector((1.6, 1.4, -0.4))).to_track_quat("-Z", "Y").to_euler()
world = bpy.data.worlds.new("w")
sc.world = world
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.6
sc.render.engine = "CYCLES"
sc.cycles.samples = 96
sc.cycles.use_denoising = "raw" not in opts
prefs = bpy.context.preferences.addons["cycles"].preferences
prefs.compute_device_type = "METAL"
prefs.get_devices()
for dev in prefs.devices:
    dev.use = dev.type == "METAL"
sc.cycles.device = "GPU"
sc.render.resolution_x = sc.render.resolution_y = 520
sc.view_settings.view_transform = "AgX"
sc.view_settings.look = "AgX - Medium High Contrast"
sc.view_settings.exposure = -0.9  # the rooms' cameras sit near -1
head = Vector((0, -0.07, 1.2))
views = (("front", 0.0), ("three", 0.65), ("profile", 1.5708))[:1 if "front" in opts else 3]
if "back" in opts:  # from behind and behind-left instead
    views = (("front", 2.4), ("three", 3.1416), ("profile", -1.5708))
if "wide" in opts:  # the upper body, to see clothes and arms
    head, views = Vector((0, -0.15, 0.95)), (("front", 0.0), ("three", 0.65), ("profile", 1.5708))
for name, ang in views:
    cd = bpy.data.cameras.new(name)
    cd.lens = 45 if "wide" in opts else 100
    cam = bpy.data.objects.new(name, cd)
    sc.collection.objects.link(cam)
    cam.location = head + Vector((math.sin(ang) * 0.95, -math.cos(ang) * 0.95, 0.02))
    cam.rotation_euler = (head - cam.location).to_track_quat("-Z", "Y").to_euler()
    sc.camera = cam
    sc.render.filepath = f"{out}-{name}.png"
    bpy.ops.render.render(write_still=True)
    print("RENDERED", sc.render.filepath, flush=True)
