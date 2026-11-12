"""Builds the studio floor in Blender from the traced plan, lights it with the measured sun, and renders.

Blender -b --factory-startup --python blender/build.py -- [--floor studio|lobby] [--render ROOM,ROOM|all] [--samples N]
        [--res WxH] [--ss 2] [--out DIR] [--tag NAME] [--save] [--extra CAMS.json] [--bake [--shell] [--bake-size PX] [--bake-samples N] [--bake-only ROOM,ROOM]]

--ss 2 renders each photo at twice the size and scales it down, the way a sharper sensor would, then gives it a
camera's finish: a 0.3 EV vignette, half a percent of grain and a trace of lateral colour fringing.

Everything comes from code: the plan (out/plan.json, traced), the choices the plan leaves open
(design.json), the sun (out/sun.json, measured) and each room's styling (style.json). --floor lobby builds the
ground floor instead, from design-lobby.json and style-lobby.json (its plan is out/plan-lobby.json).
"""
import json
import math
import os
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import kit  # noqa: E402
import materials as M  # noqa: E402
import shell  # noqa: E402


def args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    opts = {"floor": "studio", "render": "", "samples": 384, "res": "1800x1200", "out": os.path.join(STUDIO, "out", "renders"), "tag": "", "save": False, "ss": 1,
            "bake": False, "shell": False, "bake-size": 2048, "bake-samples": 256, "bake-only": "", "extra": "", "lift-open": False}
    i = 0
    while i < len(a):
        k = a[i].lstrip("-")
        if k in ("save", "bake", "shell", "lift-open"):
            opts[k] = True
            i += 1
            continue
        opts[k] = a[i + 1]
        i += 2
    return opts


def clear():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for col in list(bpy.data.collections):
        bpy.data.collections.remove(col)


def light(design, sun, calib):
    """Sun as a lamp along the measured direction; the sky's glow around it from the physical sky model."""
    sc = bpy.context.scene
    d = Vector(sun["sun_direction_plan"]).normalized()
    lamp = bpy.data.lights.new("sun", "SUN")
    lamp.angle = math.radians(0.545)
    lamp.energy = calib["sun_strength"]
    lamp.color = calib.get("sun_color", (1.0, 0.95, 0.88))
    ob = bpy.data.objects.new("sun", lamp)
    sc.collection.objects.link(ob)
    ob.rotation_euler = d.to_track_quat("Z", "Y").to_euler()  # the lamp shines along its -Z: away from the sun
    world = bpy.data.worlds.new("sky")
    sc.world = world
    nt = world.node_tree
    nt.nodes.clear()
    sky = nt.nodes.new("ShaderNodeTexSky")
    sky.sky_type = "MULTIPLE_SCATTERING"
    sky.sun_disc = False
    sky.sun_elevation = math.radians(sun["sun_elevation_deg"])
    # the sky's sun rotation measured against the lamp in calibration (see calib.json)
    plan_az = math.atan2(d.x, d.y)
    sky.sun_rotation = calib["rotation_offset"] + calib["rotation_sign"] * plan_az
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = calib.get("sky_strength", 1.0)
    out = nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(sky.outputs[0], bg.inputs[0])
    M.exposed(nt, bg.outputs[0], out.inputs[0], copies=2)


def render_settings(samples, res):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "METAL"
    prefs.get_devices()
    for dev in prefs.devices:
        dev.use = dev.type == "METAL"
    c = sc.cycles
    c.device = "GPU"
    c.samples = int(samples)
    c.adaptive_threshold = 0.012
    c.use_denoising = True
    c.denoiser = "OPENIMAGEDENOISE"
    try:
        c.denoising_use_gpu = True
    except AttributeError:
        pass
    c.max_bounces, c.diffuse_bounces, c.glossy_bounces, c.transmission_bounces, c.transparent_max_bounces = 16, 8, 6, 12, 16
    c.caustics_reflective = c.caustics_refractive = False
    # a quarter-second exposure: anyone moving (people.py, moving > 0) blurs; everything else is still
    sc.render.use_motion_blur = True
    sc.render.motion_blur_shutter = 1.0
    sc.frame_set(1)
    c.sample_clamp_indirect = 8.0
    c.blur_glossy = 0.6
    c.use_light_tree = True
    w, h = (int(v) for v in res.split("x"))
    sc.render.resolution_x, sc.render.resolution_y = w, h
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = False
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_depth = "8"
    try:
        sc.view_settings.view_transform = "AgX"
        sc.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    # the photographer's white balance: a little cooler than the warm afternoon light, so white walls read white
    sc.view_settings.use_white_balance = True
    sc.view_settings.white_balance_temperature = 5100


def camera(name, spec, room):
    """A photographer's camera: level (verticals stay straight), wide, at chest height, shifted not tilted."""
    cam = bpy.data.cameras.new(name)
    cam.lens = spec.get("lens", 18)
    cam.sensor_width = 36
    cam.shift_y = spec.get("shift_y", -0.06)
    cam.shift_x = spec.get("shift_x", 0.0)
    cam.clip_start = 0.05
    ob = bpy.data.objects.new(name, cam)
    bpy.context.scene.collection.objects.link(ob)
    x, y = spec["at"]
    tx, ty = spec["look"]
    if spec.get("fstop"):  # a photographer's depth of field, focused on what the room is for
        cam.dof.use_dof = True
        cam.dof.aperture_fstop = spec["fstop"]
        cam.dof.focus_distance = spec.get("focus", math.hypot(tx - x, ty - y))
    ob.location = (x, y, spec.get("height", 1.3))
    yaw = math.atan2(ty - y, tx - x)
    ob.rotation_euler = (math.radians(90), 0, yaw - math.pi / 2)
    f = spec.get("fill")
    if f:  # the photographer's soft box, standing out of the frame beside the camera, aimed at the person
        lamp = bpy.data.lights.new(name + " fill", "AREA")
        lamp.shape = "RECTANGLE"
        lamp.size, lamp.size_y = f.get("size", (1.0, 0.7))
        lamp.energy = f["watts"]
        lamp.color = f.get("color", (1.0, 0.87, 0.75))  # about 4500 K
        fo = bpy.data.objects.new(name + " fill", lamp)
        bpy.context.scene.collection.objects.link(fo)
        fo.location = f["at"]
        fo.rotation_euler = (Vector(f["at"]) - Vector(f["aim"])).to_track_quat("Z", "Y").to_euler()  # an area lamp shines along its -Z
        fo.visible_camera = False
    return ob


def post(src, dst, ss=2, vignette_ev=0.3, grain=0.005, fringe_px=0.3, seed=1):
    """Scales a render down by ss in linear light, then adds the lens and film finish, and writes dst (8-bit PNG)."""
    import numpy as np
    im = bpy.data.images.load(src)
    im.colorspace_settings.name = "Non-Color"
    w, h = im.size
    a = np.array(im.pixels[:], dtype=np.float32).reshape(h, w, 4)[:, :, :3]
    bpy.data.images.remove(im)
    lin = np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)
    if ss > 1:
        h, w = h // ss, w // ss
        lin = lin[:h * ss, :w * ss].reshape(h, ss, w, ss, 3).mean(axis=(1, 3))
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy, half_diag = (w - 1) / 2, (h - 1) / 2, math.hypot(w, h) / 2
    r = np.hypot(xx - cx, yy - cy) / half_diag
    lin *= (2.0 ** (-vignette_ev * r ** 2))[..., None]

    def radial(ch, px):  # resample one channel scaled about the centre, px pixels further out at the corners
        s = 1.0 + px / half_diag
        sx = np.clip((xx - cx) / s + cx, 0, w - 1.001)
        sy = np.clip((yy - cy) / s + cy, 0, h - 1.001)
        x0, y0 = sx.astype(int), sy.astype(int)
        fx, fy = sx - x0, sy - y0
        c = lin[..., ch]
        return (c[y0, x0] * (1 - fx) * (1 - fy) + c[y0, x0 + 1] * fx * (1 - fy) +
                c[y0 + 1, x0] * (1 - fx) * fy + c[y0 + 1, x0 + 1] * fx * fy)
    lin = np.stack([radial(0, fringe_px), lin[..., 1], radial(2, -fringe_px)], axis=-1)
    lin = np.clip(lin, 0.0, 1.0)
    disp = np.where(lin <= 0.0031308, lin * 12.92, 1.055 * lin ** (1 / 2.4) - 0.055)
    rng = np.random.default_rng(seed)
    disp += rng.normal(0.0, grain, (h, w, 1)).astype(np.float32)  # luminance grain
    disp = np.clip(disp, 0.0, 1.0)
    out = bpy.data.images.new("post", w, h, alpha=False)
    rgba = np.concatenate([disp, np.ones((h, w, 1), np.float32)], axis=-1)
    out.pixels.foreach_set(rgba.astype(np.float32).ravel())
    out.filepath_raw = dst
    out.file_format = "PNG"
    out.save()
    bpy.data.images.remove(out)


def main():
    o = args()
    sfx = "" if o["floor"] == "studio" else "-" + o["floor"]
    design = json.load(open(os.path.join(STUDIO, f"design{sfx}.json")))
    plan = json.load(open(os.path.join(STUDIO, design["plan"])))
    sun = json.load(open(os.path.join(STUDIO, "out", "sun.json")))
    calib = json.load(open(os.path.join(STUDIO, "out", "calib.json")))
    styles = json.load(open(os.path.join(STUDIO, f"style{sfx}.json")))
    if o["extra"]:  # test cameras: a room's cameras swapped for the ones in this file, {"ROOM": [spec, ...]}
        for room, specs in json.load(open(o["extra"])).items():
            styles.setdefault(room, {})["cameras"] = specs
    clear()
    if o["floor"] == "site":  # the outside: the streets, the light wells and the roof (street.py)
        import street as outside_site
        basement = json.load(open(os.path.join(STUDIO, "design-basement.json")))
        outside_site.build(basement)
        outside_site.roof(None)
        light(design, sun, calib)
        render_settings(o["samples"], o["res"])
        sc = bpy.context.scene
        sc.view_settings.exposure = design.get("exposure", -1.6)
        outside_site.bake_site(int(o["bake-size"]), int(o["bake-samples"]))
        return
    if o["lift-open"]:  # a photo with the lift's doors open (lift.py)
        design = {**design, "lift_open": True}
    if o["shell"]:  # the live building's floor: every inside door open, so a walk reaches every room
        design = {**design, "all_doors_open": True}
    shell.build_shell(plan, design, styles)
    if os.path.exists(os.path.join(HERE, "furnish.py")):
        import furnish
        furnish.furnish(plan, design, styles)
    light(design, sun, calib)
    ss = int(o["ss"])
    rw, rh = (int(v) for v in o["res"].split("x"))
    render_settings(o["samples"], f"{rw * ss}x{rh * ss}")
    sc = bpy.context.scene
    wanted = [r["name"] for r in plan["rooms"] if r["name"] in design["styled"]] if o["render"] == "all" else [n for n in o["render"].split(",") if n]
    cams = {}
    for r in plan["rooms"]:
        st = styles.get(r["name"], {})
        for k, spec in enumerate(st.get("cameras", []) if isinstance(st, dict) else []):
            cams[(r["name"], k)] = camera(f"cam {r['name']} {k}", spec, r)
    if o["save"]:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(STUDIO, "out", f"studio{sfx}.blend"))
    if o["bake"]:
        import bake
        first = next((c for st in styles.values() if isinstance(st, dict) for c in st.get("cameras", [])), {})
        sc.view_settings.exposure = first.get("exposure", 0.0)
        only = [n for n in o["bake-only"].split(",") if n] or None
        for ob in [x for x in bpy.data.objects if x.name.endswith(" fill")]:  # a photographer's soft box lights the photo, not the room
            bpy.data.objects.remove(ob, do_unlink=True)
        bake.bake_all(plan, design, styles, int(o["bake-size"]), int(o["bake-samples"]), only, o["floor"] + ("-shell" if o["shell"] else ""), o["shell"])
        return
    os.makedirs(o["out"], exist_ok=True)
    for (name, k), cam in cams.items():
        if name not in wanted:
            continue
        st = styles[name]["cameras"][k]
        sc.camera = cam
        sc.view_settings.exposure = st.get("exposure", 0.0)
        sc.view_settings.look = st.get("grade", "AgX - Medium High Contrast")
        sc.view_settings.white_balance_temperature = st.get("wb", 5100)
        slug = name.lower().replace("'", "").replace(" ", "-")
        if o["floor"] != "studio":  # two floors may have a room of the same name (the basement's and the office's LIBRARY)
            slug = f"{o['floor']}-{slug}"
        final = os.path.join(o["out"], f"{slug}-{k}{('-' + o['tag']) if o['tag'] else ''}.png")
        sc.render.filepath = final if ss == 1 else final[:-4] + f"@{ss}x.png"
        if ss > 1:
            sc.render.image_settings.color_depth = "16"
        bpy.ops.render.render(write_still=True)
        if ss > 1:
            post(sc.render.filepath, final, ss, seed=k + len(slug))
            os.remove(sc.render.filepath)
        print("RENDERED", final, flush=True)


main()
