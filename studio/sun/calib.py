"""Measures the sun lamp's strength and colour against Blender's physical sky, at the picked sun's elevation.

A flat white (diffuse, albedo 1) plane is rendered from straight above with the sky alone, once with the sky's
sun disc and once without. The difference is the sun's share: its radiance L off the plane gives the sun's
irradiance on level ground, pi * L, and the lamp (which Blender sets as irradiance square on to the light) gets
pi * L / sin(elevation). The colour is that difference's RGB, scaled so the largest channel is 1.

Blender -b --factory-startup --python sun/calib.py -- out/sun.json out/calib.json [ELEVATION_DEG]

The sky's sun rotation (rotation_offset, rotation_sign) is kept from the existing calib.json: it was measured
once against the lamp and doesn't depend on the elevation.
"""
import json
import math
import os
import sys

import bpy
import numpy as np


def measure(elevation_deg, disc):
    sc = bpy.context.scene
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    bpy.ops.mesh.primitive_plane_add(size=20.0)
    plane = bpy.context.active_object
    mat = bpy.data.materials.new("white")
    nt = mat.node_tree
    nt.nodes.clear()
    diff = nt.nodes.new("ShaderNodeBsdfDiffuse")
    diff.inputs["Color"].default_value = (1, 1, 1, 1)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(diff.outputs[0], out.inputs[0])
    plane.data.materials.append(mat)
    cam_data = bpy.data.cameras.new("cam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = 2.0
    cam = bpy.data.objects.new("cam", cam_data)
    sc.collection.objects.link(cam)
    cam.location = (0, 0, 5)
    sc.camera = cam
    world = bpy.data.worlds.new("sky")
    sc.world = world
    wt = world.node_tree
    wt.nodes.clear()
    sky = wt.nodes.new("ShaderNodeTexSky")
    sky.sky_type = "MULTIPLE_SCATTERING"
    sky.sun_disc = disc
    sky.sun_elevation = math.radians(elevation_deg)
    bg = wt.nodes.new("ShaderNodeBackground")
    wo = wt.nodes.new("ShaderNodeOutputWorld")
    wt.links.new(sky.outputs[0], bg.inputs[0])
    wt.links.new(bg.outputs[0], wo.inputs[0])
    sc.render.engine = "CYCLES"
    sc.cycles.samples = 512
    sc.cycles.use_denoising = False
    sc.render.resolution_x = sc.render.resolution_y = 32
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.view_settings.exposure = 0.0
    sc.render.image_settings.file_format = "OPEN_EXR"
    path = os.path.join(bpy.app.tempdir, f"calib-{int(disc)}.exr")
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    im = bpy.data.images.load(path)
    px = np.array(im.pixels[:], dtype=np.float64).reshape(-1, 4)[:, :3]
    return px.mean(axis=0)


def main():
    a = sys.argv[sys.argv.index("--") + 1:]
    sun = json.load(open(a[0]))
    out_path = a[1]
    el = float(a[2]) if len(a) > 2 else sun["sun_elevation_deg"]
    with_disc = measure(el, True)
    sky_only = measure(el, False)
    sun_rgb = with_disc - sky_only
    lum = lambda c: float(0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2])
    L_sun, L_sky = lum(sun_rgb), lum(sky_only)
    old = json.load(open(out_path)) if os.path.exists(out_path) else {}
    result = {
        "about": (f"Measured in Blender (sun/calib.py) on a white diffuse plane: the physical sky's sun gives {L_sun:.2f} "
                  f"on the plane against {L_sky:.2f} from the sky alone at {el:.1f} degrees up ({L_sun / L_sky:.1f} to 1). "
                  f"The lamp is set to that: {L_sun:.2f} x pi / sin({el:.1f} deg). The sky's sun rotation turns clockwise "
                  "from +Y (0 deg: sun on +Y; 90 deg: sun on +X)."),
        "elevation_deg": round(el, 2),
        "sun_strength": round(L_sun * math.pi / math.sin(math.radians(el)), 1),
        "sun_color": [round(float(c / max(sun_rgb)), 3) for c in sun_rgb],
        "sky_strength": old.get("sky_strength", 1.0),
        "rotation_offset": old.get("rotation_offset", 0.0),
        "rotation_sign": old.get("rotation_sign", 1.0),
    }
    if len(a) > 3 and a[3] == "--dry":
        print("CALIB", json.dumps(result))
        return
    json.dump(result, open(out_path, "w"), indent=1)
    print("CALIB", json.dumps(result))


main()
