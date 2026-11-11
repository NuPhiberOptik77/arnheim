"""People, built from code like everything else: a body fused from simple shapes, clothes over it, a shaped
face, hands, and real hair, strand by strand. Nothing downloaded.

A person is built sitting, facing -y, with the middle of their seat at the origin, so furnish.py puts them
the way it puts a chair. Their look comes from the same data as the 3D app: the founder's assistant from the
company file (org.assistant.look), and anyone else from their id, picked the way buildSeated in
src/three/poe.js picks, so the photographs and the app show the same person.
"""
import math
import random

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

import materials as M

# The 3D app's lists (src/three/poe.js LOOKS and CUTS): someone's skin, hair, top and trousers come from
# their id, so the same person looks the same everywhere.
LOOKS = {
    "skin": ["#f0c8a4", "#deaa82", "#c8926e", "#a8714f", "#7f5238", "#5c3a27"],
    "hair": ["#1d1613", "#3a261f", "#5a3926", "#8b5a33", "#c8a26b", "#a7a39d"],
    "top": ["#b5603f", "#3f6f7a", "#d4a24c", "#2f4a5c", "#6d7f4e", "#e6dac6", "#7a4f6d", "#c86f5c"],
    "legs": ["#27303d", "#3b3b42", "#5b5246", "#2f3c34"],
}
# Where the hair stops, by angle round the head (0 is the face, pi the back), as a height from -1 (chin)
# to 1 (crown).
CUTS = {
    "short": [[0, 0.5], [0.55, 0.47], [1.05, 0.25], [1.5, 0.1], [1.8, -0.12], [2.3, -0.45], [3.15, -0.58]],
    "long": [[0, 0.5], [0.55, 0.44], [1.1, 0.2], [1.6, 0.02], [2.0, -0.45], [2.3, -0.7], [3.15, -0.8]],
    "cropped": [[0, 0.62], [0.7, 0.55], [1.3, 0.3], [1.8, 0.05], [2.4, -0.3], [3.15, -0.42]],
}
CUT_ORDER = ["short", "long", "cropped"]
HEAD = (0.072, 0.097, 0.112)  # half width, half depth, half height (metres)


def identity(text):
    """rooms.js identity(): FNV-1a over the id, a stable 32-bit number."""
    n = 2166136261
    for ch in str(text):
        n = ((n ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return n


def agent_look(id_):
    """The look the 3D app gives the agent working on this id (buildSeated in src/three/poe.js)."""
    n = identity(id_)
    pick = lambda name, shift: LOOKS[name][(n >> shift) % len(LOOKS[name])]
    return {"skin": pick("skin", 0), "hair": pick("hair", 3), "top": pick("top", 6), "trousers": pick("legs", 9),
            "cut": CUT_ORDER[(n >> 11) % len(CUT_ORDER)], "wear": "sweater", "build": 1.0}


def assistant_look(look):
    """The founder's assistant from the company file: a coat over a shirt, and their hair style."""
    return {"skin": look.get("skin", "#c8926e"), "hair": look.get("hair", "#3a261f"), "top": look.get("coat", "#2f4a5c"),
            "shirt": look.get("shirt", "#efe6d6"), "trousers": look.get("trousers", "#27303d"), "accent": look.get("accent"),
            "cut": {"bun": "bun", "braids": "long"}.get(look.get("style"), "short"), "wear": "coat", "build": 0.93, "torso": 0.93,
            "earrings": bool(look.get("accent"))}


# ---------- small geometry helpers ----------

def _smooth(e0, e1, x):
    t = np.clip((np.asarray(x, dtype=float) - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _table(points, a):
    return np.interp(a, [p[0] for p in points], [p[1] for p in points])


def _frame(t):
    """Two directions square to t, the first as near level as it can be."""
    t = t.normalized()
    ref = Vector((0, 0, 1)) if abs(t.z) < 0.9 else Vector((1, 0, 0))
    n = ref.cross(t).normalized()
    return n, t.cross(n).normalized()


def _ellipsoid(bm, centre, axes, radii, segs=20, rings=14):
    """An ellipsoid with its three half-lengths along three directions."""
    m = Matrix.Identity(4)
    for i in range(3):
        for j in range(3):
            m[j][i] = axes[i][j] * radii[i]
    m.translation = Vector(centre)
    bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=rings, radius=1.0, matrix=m)


def _rings(bm, rings, segs=24):
    """A closed tube through rings of (centre, across, depth, half-across, half-depth)."""
    loops = []
    for c, n, b, rx, ry in rings:
        loops.append([bm.verts.new(c + n * (rx * math.cos(2 * math.pi * k / segs)) + b * (ry * math.sin(2 * math.pi * k / segs)))
                      for k in range(segs)])
    for A, B in zip(loops, loops[1:]):
        for k in range(segs):
            bm.faces.new((A[k], A[(k + 1) % segs], B[(k + 1) % segs], B[k]))
    bm.faces.new(list(reversed(loops[0])))
    bm.faces.new(loops[-1])


def _limb(bm, pts, radii, steps=4, segs=20, folds=0.0):
    """A round tube along a polyline whose radius changes from point to point, with a ball at each bend.
    folds > 0 gathers cloth: the tube swells and pinches by that share every 2.5 cm at each bend and at the end."""
    pts = [Vector(p) for p in pts]
    rings = []
    total = sum((b - a).length for a, b in zip(pts, pts[1:]))
    bends = [sum((pts[j + 1] - pts[j]).length for j in range(i)) for i in range(1, len(pts) - 1)] + [total - 0.02]
    s = 0.0
    if folds:
        steps = max(steps, 14)
    for i, (a, b) in enumerate(zip(pts, pts[1:])):
        n, d = _frame(b - a)
        seg = (b - a).length
        for k in range(steps + (1 if i == len(pts) - 2 else 0)):
            t = k / steps
            r = radii[i] + (radii[i + 1] - radii[i]) * t
            c = a.lerp(b, t)
            if folds:  # uneven folds that push to one side and the other, the way cloth gathers at a bend
                at = s + seg * t
                w = max(math.exp(-((at - x) / 0.06) ** 2) for x in bends)
                r *= 1 + folds * w * (0.6 * math.sin(2 * math.pi * at / 0.037) + 0.4 * math.sin(2 * math.pi * at / 0.023 + 1.3))
                c = c + n * (r * folds * w * 0.9 * math.cos(2 * math.pi * at / 0.041 + 0.7))
            rings.append((c, n, d, r, r))
        s += seg
    _rings(bm, rings, segs)
    for p, r in zip(pts[1:-1], radii[1:-1]):
        _ellipsoid(bm, p, (Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))), (r, r, r), 16, 10)


def _fuse(name, bm, col, mat, voxel, smooth=(0.6, 6), folds=0.0, keep=None):
    """Melts overlapping shapes into one smooth surface: a voxel remesh, then softened. folds > 0 rumples it
    by that many metres, the way cloth gathers. keep(x, y, z) -> False deletes those faces afterwards."""
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    col.objects.link(ob)
    r = ob.modifiers.new("fuse", "REMESH")
    r.mode = "VOXEL"
    r.voxel_size = voxel
    if folds:
        tex = bpy.data.textures.get("cloth folds") or bpy.data.textures.new("cloth folds", "CLOUDS")
        tex.noise_scale = 0.07
        tex.noise_depth = 0
        d = ob.modifiers.new("folds", "DISPLACE")
        d.texture = tex
        d.strength = folds
        d.mid_level = 0.5
    s = ob.modifiers.new("soften", "SMOOTH")
    s.factor, s.iterations = smooth
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    fused = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    ob.modifiers.clear()
    old = ob.data
    ob.data = fused
    bpy.data.meshes.remove(old)
    if keep:
        b2 = bmesh.new()
        b2.from_mesh(fused)
        gone = [f for f in b2.faces if not keep(*f.calc_center_median())]
        bmesh.ops.delete(b2, geom=gone, context="FACES")
        for _ in range(12):  # the cut follows the voxels in steps: smooth its edge into a clean line
            edge = [v for v in b2.verts if v.is_boundary]
            bmesh.ops.smooth_vert(b2, verts=edge, factor=0.5, use_axis_x=True, use_axis_y=True, use_axis_z=True)
        b2.to_mesh(fused)
        b2.free()
    for p in fused.polygons:
        p.use_smooth = True
    fused.materials.append(mat)
    return ob


def _obj(name, bm, col, mat, smooth=True):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = smooth
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    col.objects.link(ob)
    return ob


def _ik(s, w, l1, l2, pole):
    """Where the elbow (or knee) goes, reaching from s towards w with bones l1 and l2, bending towards pole."""
    d = w - s
    dist = min(d.length, (l1 + l2) * 0.995)
    u = d.normalized()
    a = (l1 * l1 - l2 * l2 + dist * dist) / (2 * dist)
    h = math.sqrt(max(l1 * l1 - a * a, 0.0))
    p = pole - u * pole.dot(u)
    p.normalize()
    return s + u * a + p * h, s + u * dist


# ---------- the pose ----------

def pose(kind, seat, table, reach, rnd, build=1.0, torso=1.0, hands="table"):
    """The joints of someone seated, facing -y. kind: 'desk' (typing on a keyboard `reach` in front of the
    seat's middle), 'chat' (forearms on a table), 'read' (elbows on the table, holding something up)."""
    lean = {"desk": 0.15, "chat": 0.17, "read": 0.13}[kind]
    back = {"desk": 0.075, "chat": 0.03, "read": 0.03}[kind]

    def spine(h):  # torso < 1 is a shorter body from seat to shoulders
        return Vector((0.0, back - lean * h * torso, seat + h * torso))

    J = {"lean": lean, "spine": spine, "seat": seat}
    J["neck"] = spine(0.6)
    nod = {"desk": 0.2, "chat": -0.04, "read": 0.5}[kind] + rnd.uniform(-0.02, 0.02)
    J["head"] = spine(0.6) + Vector((0.0, (-0.01 - 0.03 * nod) if kind == "read" else (-0.03 - 0.06 * nod), 0.14))
    if kind == "read":  # reading, the neck bends too and carries the head down with it, so the nape doesn't stretch bare
        bend = 0.4 * nod
        J["head"] = spine(0.6) + Vector((0.0, -0.01 * math.cos(bend) - 0.14 * math.sin(bend), -0.01 * math.sin(bend) + 0.14 * math.cos(bend) - 0.01))
    J["nod"], J["yaw"] = nod, {"desk": rnd.uniform(-0.12, 0.12), "chat": rnd.uniform(-0.03, 0.03), "read": rnd.uniform(-0.05, 0.05)}[kind]
    sw = 0.178 * build
    for side, sx in (("l", 1), ("r", -1)):
        sh = spine(0.55) + Vector((sx * sw, 0.014, 0.0))
        if kind == "desk":
            knuckle = Vector((sx * 0.105, -reach, table + 0.035))
            wrist = knuckle + Vector((sx * 0.012, 0.085, 0.022))
            pole = Vector((sx * 0.7, 0.5, -1.0))
        elif kind == "chat" and hands == "talk" and sx > 0:  # mid-sentence: this hand lifted off the table, open
            knuckle = Vector((0.2, -reach + 0.01, table + 0.05))
            wrist = knuckle + Vector((-0.02, 0.09, -0.02))
            pole = Vector((1.0, 0.3, -0.6))
        elif kind == "chat" and hands == "glass" and sx > 0:  # this hand rests in the lap
            knuckle = Vector((0.1, -0.3, seat + 0.17))
            wrist = knuckle + Vector((0.02, 0.085, 0.01))
            pole = Vector((1.0, 0.4, -0.3))
        elif kind == "chat":  # forearms resting on the table, elbows bent, hands near the edge
            knuckle = Vector((sx * (0.07 if sx > 0 else 0.1), -reach - (0.0 if sx > 0 else 0.03), table + 0.03))
            wrist = knuckle + Vector((sx * 0.06, 0.07, 0.012))
            pole = Vector((sx * 1.0, 0.25, -0.6))
        else:  # forearms on the table, the file held up at the chest
            knuckle = Vector((sx * 0.1, -reach - 0.03, table + 0.01))
            wrist = knuckle + Vector((sx * 0.025, 0.05, -0.06))
            pole = Vector((sx * 0.8, 0.0, -1.0))
        elbow, wrist = _ik(sh, wrist, 0.275 * build ** 0.5, 0.235 * build ** 0.5, pole)
        J["shoulder_" + side], J["elbow_" + side], J["wrist_" + side], J["knuckle_" + side] = sh, elbow, wrist, knuckle
        hip = Vector((sx * 0.085 * build, 0.01, seat + 0.09))
        knee_z = 0.5 if seat > 0.49 else seat + 0.03
        ky = math.sqrt(max(0.43 ** 2 - (hip.z - knee_z) ** 2, 0.04))
        knee = Vector((sx * 0.105, 0.01 - ky, knee_z))
        fwd = (0.07 if kind == "desk" else ((0.04 if sx > 0 else -0.08) if kind == "chat" else (0.0 if sx > 0 else -0.14))) + rnd.uniform(-0.02, 0.02)  # at a desk side by side; else one back
        ankle = Vector((sx * (0.115 + rnd.uniform(0.0, 0.03)), knee.y - fwd, 0.085))
        splay = sx * math.radians(rnd.uniform(6, 14))
        J["hip_" + side], J["knee_" + side], J["ankle_" + side], J["splay_" + side] = hip, knee, ankle, splay
    return J


# ---------- the parts ----------

# The face down its middle, from crown to chin: (height on the unit head, how far forward of the head's centre
# in metres). The nose stands out from it on its own narrower profile.
PROFILE = [(1.0, 0.0), (0.92, 0.04), (0.75, 0.08), (0.5, 0.094), (0.32, 0.1), (0.22, 0.097), (0.1, 0.09), (-0.1, 0.091),
           (-0.3, 0.095), (-0.42, 0.101), (-0.5, 0.099), (-0.545, 0.095), (-0.6, 0.098), (-0.7, 0.09), (-0.82, 0.099),
           (-0.92, 0.088), (-1.0, 0.05)]
NOSE = [(0.24, 0.0), (0.14, 0.096), (0.0, 0.104), (-0.12, 0.112), (-0.22, 0.121), (-0.27, 0.118), (-0.31, 0.109), (-0.35, 0.1), (-0.38, 0.0)]


EYE = (0.031, 0.0699, 0.006)  # each eyeball's centre in the head's frame (across, either side; forward; up): the cornea 1 mm behind the face's shell
EYE_R = 0.0125  # the eyeball's radius


def _smax(a, b, k):
    """A smooth maximum of a and b, rounded over k."""
    h = np.clip(0.5 + 0.5 * (a - b) / k, 0.0, 1.0)
    return b + (a - b) * h + k * h * (1 - h)


def _profile(table, z):
    zs = [-p[0] for p in table]
    return np.interp(-z, zs, [p[1] for p in table])


def _head_shape(v, eyes=True, mouth=0.0):
    """Points on a unit sphere (columns: across, forward, up) to a head, in metres, in the head's own frame."""
    a, b, c = HEAD
    u, f, z = v[:, 0], v[:, 1], v[:, 2]
    low = _smooth(0.05, 1.0, -z)
    width = 1 - (0.16 + 0.19 * _smooth(-0.2, 0.8, f)) * low
    depth = 1 - 0.42 * _smooth(0.3, 1.0, -z) * _smooth(0.1, -0.7, f)
    width = width * (1 - 0.16 * _smooth(0.72, 0.95, -z) * _smooth(-0.4, 0.2, f) * (1 - _smooth(0.5, 0.9, f)))  # in under the jaw
    x, y, h = a * u * width, b * f * depth, c * z
    au = np.abs(u)
    # the face: the profile's reach at this height, rolling off to the sides the way the head does
    ring = np.sqrt(np.clip(1 - z * z, 1e-3, None))
    target = _profile(PROFILE, z) * np.clip(f, 0, None) / ring
    reach_u = np.interp(z, [-1.0, -0.85, -0.5, 0.0, 1.0], [0.12, 0.26, 0.42, 0.6, 0.6])  # the face narrows to the chin
    face = _smooth(0.25, 0.75, f) * np.exp(-(u / reach_u) ** 4) * (1 - _smooth(0.86, 0.97, -z))
    y = y + face * (target - y)
    # the nose on its own profile: how far it stands proud of the face falls off to the sides, about 16 mm across
    # at the bridge and 28 at the tip, with its wings either side
    sigma = np.interp(-z, [-0.24, -0.1, 0.12, 0.3, 0.37], [0.12, 0.13, 0.16, 0.2, 0.2])
    proud = np.clip(_profile(NOSE, z) - y, 0, None) * np.exp(-(au / sigma) ** 2) * _smooth(0.5, 0.85, f)
    wings = 0.006 * np.exp(-((au - 0.2) / 0.06) ** 2 - ((z + 0.3) / 0.05) ** 2)
    y = y + proud + wings * _smooth(0.5, 0.85, f)
    nostrils = -0.003 * np.exp(-((au - 0.1) / 0.04) ** 2 - ((z + 0.345) / 0.03) ** 2)
    # the fold from the nose's wing to past the mouth's corner: the cheek stands a little proud beyond it
    fold_at = 0.27 + np.clip(-z - 0.3, 0, 0.3) * 0.45
    d = au - fold_at
    smile = 0.0022 * _smooth(-0.05, 0.06, d) * np.exp(-np.clip(d, 0, None) / 0.25) * _smooth(0.22, 0.3, -z) * (1 - _smooth(0.58, 0.7, -z))
    corners = -0.002 * np.exp(-((au - 0.33) / 0.05) ** 2 - ((z + 0.545) / 0.035) ** 2)
    y = y + (nostrils + smile + corners) * _smooth(0.5, 0.85, f)
    cheeks = 0.004 * np.exp(-((au - 0.62) / 0.15) ** 2 - ((z + 0.08) / 0.15) ** 2) * _smooth(0.2, 0.8, f)
    p = np.stack([x, y, h], axis=1)
    nrm = p / np.linalg.norm(p, axis=1, keepdims=True)
    p = p + nrm * cheeks[:, None]
    if mouth:  # lips parted, mid-word: the mouth's line opens into a dark gap
        mz = -0.545 * c
        gap = mouth * np.exp(-(p[:, 0] / 0.019) ** 4 - ((p[:, 2] - mz) / (0.35 * mouth + 0.0008)) ** 2) * _smooth(0.5, 0.85, f)
        p[:, 1] -= gap * 1.6
        p[:, 2] -= mouth * 0.5 * _smooth(mz + 0.002, mz - 0.006, p[:, 2]) * _smooth(0.4, 0.8, f) * np.exp(-(p[:, 0] / 0.05) ** 4)  # the jaw drops
    return _eyes(p, f) if eyes else p


def _upper_lid(tt):
    """How high the upper lid's edge sits above the eye's centre, from the inner corner (tt -1) to the outer (1)."""
    return 0.0041 * (1 - tt * tt) ** 0.55 - 0.0007 * tt  # highest a little inward, over the iris's top 2 mm


def _lower_lid(tt):
    return 0.0035 * (1 - tt * tt) ** 0.8


def _eyes(p, f):
    """Each eye: a broad hollow under the brow, the lids draped over the eyeball, and between them an almond
    about 27 mm wide and 10 mm tall where the skin draws back so the eyeball shows."""
    p = p.copy()
    front = _smooth(0.45, 0.75, f)
    for s in (-1.0, 1.0):
        dx, dz = p[:, 0] - s * EYE[0], p[:, 2] - EYE[2]
        r2 = dx * dx + dz * dz
        y0 = p[:, 1]
        hollow = y0 - 0.0085 * np.exp(-(dx / 0.019) ** 2 - ((dz + 0.002) / 0.016) ** 2)
        brow = 0.0042 * np.exp(-(dx / 0.021) ** 2 - ((dz - 0.017) / 0.006) ** 2)
        lid = np.where(r2 < (EYE_R + 0.0016) ** 2, EYE[1] + np.sqrt(np.clip((EYE_R + 0.0016) ** 2 - r2, 0, None)), -1.0)
        y1 = _smax(hollow + brow, lid, 0.003)
        out = s * dx / 0.0135  # -1 at the inner corner, 1 at the outer
        tt = np.clip(out, -1, 1)
        dzt = dz - 0.0011 * out  # the outer corner a little higher
        upper = _upper_lid(tt)
        lower = _lower_lid(tt)
        opening = _smooth(-0.0005, 0.0005, upper - dzt) * _smooth(-0.0005, 0.0005, dzt + lower) * (np.abs(out) < 1)
        ball = EYE[1] + np.sqrt(np.clip(EYE_R ** 2 - r2, 0, None))
        y1 = y1 - opening * np.clip(y1 - (ball - 0.003), 0, None)
        crease = -0.0009 * np.exp(-((dzt - upper - 0.0035) / 0.0013) ** 2) * np.exp(-(dx / 0.015) ** 4)
        p[:, 1] = y0 + (y1 + crease - y0) * front
    return p


class _Head:
    """The head's frame in the world: centre, then across (person's left), forward (face) and up."""

    def __init__(self, centre, yaw, nod, roll=0.0):
        rz = Matrix.Rotation(yaw, 3, "Z")
        self.c = Vector(centre)
        x = Vector((1, 0, 0))
        f = Vector((0, -math.cos(nod), -math.sin(nod)))
        u = Vector((0, -math.sin(nod), math.cos(nod)))
        x, u = x * math.cos(roll) + u * math.sin(roll), u * math.cos(roll) - x * math.sin(roll)  # head tilted to one side
        self.x, self.f, self.u = rz @ x, rz @ f, rz @ u
        self.R = np.array([list(self.x), list(self.f), list(self.u)])  # rows: local axes in world terms

    def world(self, p):
        return np.asarray(p) @ self.R + np.array(self.c)


def _head(col, H, look, cut, neck_base, chest=None):
    out = []
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=360, v_segments=240, radius=1.0)  # about 1.4 mm apart, fine enough for lids and lips
    v = np.array([vt.co[:] for vt in bm.verts])
    # the sphere's poles run along local z; the shape wants columns (across, forward, up)
    w = H.world(_head_shape(v, mouth=look.get("mouth", 0.0)))
    for vt, p in zip(bm.verts, w):
        vt.co = p
    # the neck, into the head from below and a little behind
    # the neck: from the top of the torso up to the head, so it bends where a neck does when the head nods
    top = H.c - H.u * 0.05 - H.f * 0.022
    mid = (neck_base + top) / 2 + Vector((0, 0.006, 0))
    _limb(bm, [neck_base, mid, top], [0.062, 0.058, 0.056], 3, segs=56)
    if chest:  # the top of the chest, where an open collar shows it
        _ellipsoid(bm, chest[0], (Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))), chest[1], 32, 20)
    for sx in (-1, 1):  # ears, standing off the head about 20 degrees, the open side forward
        out_ = (H.x * (sx * math.cos(0.17)) - H.f * math.sin(0.17)).normalized()
        along = (H.f + H.x * (sx * math.sin(0.17))).normalized()
        _ellipsoid(bm, H.c + H.x * (sx * (HEAD[0] * 0.9 + 0.004)) - H.f * 0.014 - H.u * 0.006, (out_, along, H.u), (0.0048, 0.016, 0.027), 14, 10)
    skin = M.skin(look["skin"])
    head_ob = _fuse("head", bm, col, skin, 0.0013, (0.5, 2))
    # where blood shows through: the nose, the cheeks and the ears, a little redder
    me = head_ob.data
    P = np.array([v.co[:] for v in me.vertices])
    loc = (P - np.array(H.c)) @ H.R.T / np.array(HEAD)
    nu = loc / np.maximum(np.linalg.norm(loc, axis=1, keepdims=True), 1e-6)
    u_, f_, z_ = nu[:, 0], nu[:, 1], nu[:, 2]
    flush = (0.25 * np.exp(-(u_ / 0.12) ** 2 - ((z_ + 0.25) / 0.12) ** 2) * (f_ > 0.6)
             + 1.0 * np.exp(-(u_ / 0.26) ** 4 - ((z_ + 0.54) / 0.075) ** 2) * (f_ > 0.7)
             + 0.36 * np.exp(-((np.abs(u_) - 0.55) / 0.18) ** 2 - ((z_ + 0.12) / 0.16) ** 2) * (f_ > 0.2)
             + 0.45 * _smooth(0.97, 1.08, np.abs(loc[:, 0]))  # the ears only, not the side of the head round them
             * np.exp(-((loc[:, 2] * HEAD[2] + 0.006) / 0.026) ** 4 - ((loc[:, 1] * HEAD[1] + 0.014) / 0.02) ** 4))
    a = me.attributes.new("flush", "FLOAT", "POINT")
    a.data.foreach_set("value", np.clip(flush, 0, 1).astype(np.float32))
    # lashes along the upper lid's edge (a dark line, thickest at the outer corner), a fainter one along the lower,
    # a little shadow over the lids, and the line where the lips meet
    q = (P - np.array(H.c)) @ H.R.T  # head frame, metres
    dark = np.zeros(len(q))
    for s in (-1.0, 1.0):
        dx, dz = q[:, 0] - s * EYE[0], q[:, 2] - EYE[2]
        out_ = s * dx / 0.0135
        tt = np.clip(out_, -1, 1)
        dzt = dz - 0.0011 * out_
        inside = np.abs(out_) < 1.08
        above = dzt - _upper_lid(tt)
        below = -_lower_lid(tt) - dzt
        thick = 0.0007 + 0.0006 * _smooth(0.0, 1.0, tt)
        dark = np.maximum(dark, 0.8 * _smooth(-0.0004, 0.0, above) * (1 - _smooth(thick - 0.0002, thick + 0.0002, above)) * inside * (q[:, 1] > EYE[1]))
        dark = np.maximum(dark, 0.45 * _smooth(-0.0004, 0.0, below) * (1 - _smooth(0.0004, 0.0008, below)) * inside * (q[:, 1] > EYE[1]))
        dark = np.maximum(dark, 0.07 * np.exp(-(dx / 0.016) ** 2 - ((dz - 0.004) / 0.008) ** 2) * (q[:, 1] > EYE[1]))
    mz = -0.545 * HEAD[2]
    mo = look.get("mouth", 0.0)
    dark = np.maximum(dark, (0.55 + 0.4 * (mo > 0)) * np.exp(-((q[:, 2] - mz + 0.3 * mo) / (0.0009 + 0.45 * mo)) ** 2 - (q[:, 0] / (0.024 - 0.4 * mo)) ** 6) * (q[:, 1] > 0.07))
    a = me.attributes.new("lash", "FLOAT", "POINT")
    a.data.foreach_set("value", np.clip(dark, 0, 1).astype(np.float32))
    out.append(head_ob)
    a, b, c = HEAD
    for sx in (-1, 1):  # eyes: a wet eyeball under the lids (which are skin, in the head), and a dark iris
        eye = Vector(H.world(np.array([[sx * EYE[0], EYE[1], EYE[2]]]))[0])
        bm = bmesh.new()
        _ellipsoid(bm, eye, (H.x, H.f, H.u), (EYE_R,) * 3, 32, 20)
        out.append(_obj("eyeball", bm, col, M.eye()))
        bm = bmesh.new()
        _ellipsoid(bm, eye + H.f * (EYE_R - 0.0012), (H.x, H.f, H.u), (0.006, 0.002, 0.006), 20, 12)
        out.append(_obj("iris", bm, col, M.eye("#3B2A20")))
        bm = bmesh.new()  # the cornea: a clear dome 2.5 mm proud of the white
        _ellipsoid(bm, eye + H.f * (EYE_R + 0.0025 - 0.0078), (H.x, H.f, H.u), (0.0078,) * 3, 24, 16)
        out.append(_obj("cornea", bm, col, M.cornea()))
    if look.get("earrings"):
        for sx in (-1, 1):
            bm = bmesh.new()
            _ellipsoid(bm, H.c + H.x * (sx * a * 0.95) - H.f * 0.012 - H.u * 0.034, (H.x, H.f, H.u), (0.0035,) * 3, 10, 8)
            out.append(_obj("earring", bm, col, M.steel(look.get("accent") or "#D4A72C", 0.25)))
    out += _hair(col, H, look["hair"], cut)
    return out


BUN_LINE = [[0, 0.53], [0.4, 0.5], [0.7, 0.53], [1.05, 0.25], [1.5, -0.02], [1.8, -0.26], [2.3, -0.66], [3.15, -0.8]]  # over the tops of the ears  # pulled up from a low nape; the temples a little higher


def _hairline(cut):
    return BUN_LINE if cut == "bun" else CUTS[cut]


def _hair(col, H, color, cut, seed=3):
    """Hair as real strands (curves), over a cap of the same colour so it reads as thick from any side."""
    rnd = np.random.default_rng(seed)
    a, b, c = HEAD
    line = _hairline(cut)
    out = []
    # the cap: the head's shape, lifted 2 mm, kept above the hairline
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=64, v_segments=48, radius=1.0)
    v = np.array([vt.co[:] for vt in bm.verts])
    p = _head_shape(v)
    p = p + p / np.linalg.norm(p, axis=1, keepdims=True) * 0.0025
    ang = np.abs(np.arctan2(v[:, 0], v[:, 1]))
    above = v[:, 2] > _table(line, ang) + (0.22 if cut in ("short", "cropped") else 0.12)
    for vt, q in zip(bm.verts, H.world(p)):
        vt.co = q
    bm.verts.ensure_lookup_table()
    gone = [vt for vt, k in zip(bm.verts, above) if not k]
    bmesh.ops.delete(bm, geom=gone, context="VERTS")
    cap = M.hair_cap(M._shade(color, -0.35))
    cap_ob = _obj("hair cap", bm, col, cap)
    cap_ob.visible_camera = False  # it shades and fills from every other ray; the camera sees strands, not its edge
    out.append(cap_ob)

    # the strands: roots on the scalp above the hairline, combed by a flow on the head's surface
    n = {"short": 90000, "cropped": 70000, "long": 80000, "bun": 70000}[cut]
    d = rnd.normal(size=(n * 3, 3))
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    ang = np.abs(np.arctan2(d[:, 0], d[:, 1]))
    edge = d[:, 2] - _table(line, ang)
    fade = _smooth(0.0, 0.45, edge) if cut in ("short", "cropped") else _smooth(0.0, 0.28, edge)  # thinning over 3-4 cm, no hard edge
    floor = 0.25
    if cut == "bun":  # pulled-up hair is thick right to its hairline (the fine hairs below soften the edge), or the nape shows as a bare band
        fade, floor = _smooth(0.0, 0.08, edge), 0.6
    d = d[(edge > 0.01) & (rnd.random(len(d)) < floor + (1 - floor) * fade)][:n]
    m = len(d)
    steps = {"short": 7, "cropped": 5, "long": 14, "bun": 12}[cut]
    length = {"short": (0.045, 0.07), "cropped": (0.012, 0.025), "long": (0.14, 0.21), "bun": (0.2, 0.26)}[cut]
    lift = {"short": 0.023, "cropped": 0.005, "long": 0.014, "bun": 0.005}[cut]
    L = rnd.uniform(*length, size=m)
    top = _smooth(0.1, 0.75, d[:, 2])  # 0 at the sides and back, 1 on top
    if cut in ("short", "cropped"):
        near = _smooth(0.0, 0.3, d[:, 2] - _table(line, np.abs(np.arctan2(d[:, 0], d[:, 1]))))
        L *= (0.22 + 0.78 * top) * (0.35 + 0.65 * near)  # clipped short at the sides and back, shortest at the edge
    lift_by = lift * (0.25 + 0.75 * top) if cut in ("short", "cropped") else np.full(m, lift)
    whorl = np.array([0.0, -0.35, 0.94])
    bun = np.array([0.0, -0.86, 0.42])
    bun /= np.linalg.norm(bun)
    # a smooth random field, so neighbouring strands clump and wave together
    kx = rnd.normal(size=(6, 3)) * 3.0
    ph = rnd.uniform(0, 2 * np.pi, size=6)

    def field(q):
        return np.stack([np.sin(q @ kx[i] + ph[i]) for i in range(6)], axis=1) @ rnd_w

    rnd_w = rnd.normal(size=(6, 3)) * (0.3 if cut in ("short", "cropped") else 0.18)  # short hair is less combed
    g = max(m // 24, 200)  # guides: the clumps
    pts = np.zeros((g, steps + 1, 3))
    pts[:, 0] = d[:g]
    L_all, lift_all = L, lift_by
    L, lift_by = L[:g], lift_by[:g]
    up = np.array([0.0, 0.0, 1.0])
    for k in range(steps):
        q = pts[:, k]
        down = -(up - q * (q @ up)[:, None])
        if cut == "bun":
            flow = (bun - q) - q * ((bun - q) * q).sum(1)[:, None]
        else:
            away = (q - whorl) - q * ((q - whorl) * q).sum(1)[:, None]
            east = np.cross(up, q)
            side = 0.35 * _smooth(0.35, 0.9, q[:, 2])[:, None] * east
            mix = 0.75 if cut == "long" else 0.45
            back = np.array([0.45, -1.0, 0.0])  # on top, combed back and over to one side
            back_t = back - q * (q @ back)[:, None]
            on_top = (_smooth(0.3, 0.8, q[:, 2]) if cut != "long" else 0.0 * q[:, 2])[:, None]
            flow = (1 - on_top) * (mix * _unit(down) + (1 - mix) * _unit(away) + side) + on_top * _unit(back_t)
            if cut in ("short", "cropped"):  # off the forehead: up and back from the hairline, so the hairline shows
                ang_q = np.abs(np.arctan2(q[:, 0], q[:, 1]))
                sweep = ((1 - _smooth(0.7, 1.5, ang_q)) * _smooth(0.15, 0.45, q[:, 2]))[:, None]
                lift_dir = np.array([0.3, -1.0, 0.25])
                lift_t = lift_dir - q * (q @ lift_dir)[:, None]
                flow = (1 - sweep) * _unit(flow) + sweep * _unit(lift_t)
            if cut == "long":  # in front of the ears, swept back over them (tucked behind), then let fall
                ang_q = np.abs(np.arctan2(q[:, 0], q[:, 1]))
                tuck = (1 - _smooth(1.6, 2.1, ang_q))[:, None]
                behind = np.array([0.0, -1.0, -0.45])
                behind_t = behind - q * (q @ behind)[:, None]
                flow = (1 - tuck) * flow + tuck * _unit(behind_t)
        flow = _unit(_unit(flow) + field(q))
        step = (L / steps / 0.1)[:, None]  # metres to angle on a head about 0.1 m round
        pts[:, k + 1] = _unit(q + flow * step)
    # each strand follows a guide from a root a few millimetres off it, drawing in towards the tip
    idx = rnd.integers(0, g, size=m)
    off = rnd.normal(size=(m, 3))
    off -= pts[idx, 0] * (off * pts[idx, 0]).sum(1)[:, None]
    off = _unit(off) * (rnd.uniform(0.0, 0.07, size=(m, 1)))
    tt = np.linspace(0, 1, steps + 1)[None, :, None]
    clump = rnd.uniform(0.6, 0.95, size=(m, 1, 1))  # drawn tight to the clump's guide by the tip: locks with gaps between
    pts = _unit(pts[idx] + off[:, None, :] * (1 - clump * tt))
    L, lift_by = L_all[idx], lift_by[idx] * rnd.uniform(0.85, 1.15, size=m)
    L = L * rnd.uniform(0.85, 1.15, size=g)[idx] * (rnd.uniform(0.8, 1.18, size=m) if cut == "long" else 1.0)  # each lock its own length, uneven ends
    stray = rnd.random(m) < 0.05  # loose strands curving 3-10 mm off the rest
    lift_by = np.where(stray, lift_by + rnd.uniform(0.003, 0.016 if cut == "long" else 0.01, size=m), lift_by)
    ang_end = np.abs(np.arctan2(pts[:, :, 0], pts[:, :, 1]))
    shape = _head_shape(pts.reshape(-1, 3)).reshape(m, steps + 1, 3)
    t = np.linspace(0, 1, steps + 1)[None, :, None]
    rise = lift_by[:, None, None] * _smooth(0.0, 0.35, t)
    edge_k = pts[:, :, 2] - _table(line, ang_end)
    if cut in ("short", "cropped"):  # tapered: the hair lies close to the head as it nears the cut line, no brim
        rise = rise * (0.2 + 0.8 * _smooth(-0.05, 0.3, edge_k))[:, :, None]
    elif cut == "bun":  # drawn back flat from the hairline, no ridge where it starts
        rise = rise * (0.15 + 0.85 * _smooth(0.0, 0.35, edge_k))[:, :, None]
    nrm = shape / np.linalg.norm(shape, axis=2, keepdims=True)
    world = shape + nrm * (rise + 0.0015 * _smooth(0.0, 0.25, t))  # rooted on the scalp, no gap to shadow
    if cut == "long":  # past the widest part of the head the hair hangs: down, and a little out
        drop = (np.clip(-(pts[:, :, 2] - 0.05), 0, None) * _smooth(1.7, 2.2, ang_end))[:, :, None]
        hang = np.zeros_like(world)
        hang[:, :, 2] = -drop[:, :, 0] * 0.11
        world = world + hang + nrm * drop * 0.02
    world = world + rnd.normal(scale=0.0004, size=world.shape) * t + (stray[:, None, None] * rnd.normal(scale=0.0008, size=world.shape) * t)
    if cut == "long":  # each lock waves a little on its own, so the fall breaks into locks, not one sheet
        side = np.cross(np.array([0.0, 0.0, 1.0]), nrm)
        side /= np.maximum(np.linalg.norm(side, axis=2, keepdims=True), 1e-6)
        ph_ = rnd.uniform(0, 2 * np.pi, size=g)[idx][:, None, None]
        amp = rnd.uniform(0.002, 0.005, size=g)[idx][:, None, None]
        world = world + side * amp * np.sin(2 * np.pi * t * L[:, None, None] / 0.05 + ph_) * t
        world = world + nrm * amp * 0.6 * np.cos(2 * np.pi * t * L[:, None, None] / 0.07 + ph_) * t
    if cut in ("short", "cropped"):  # trim at the cut line
        keep = pts[:, -1, 2] > _table(line, ang_end[:, -1]) - 0.12
        world = world[keep]
    world = H.world(world.reshape(-1, 3)).reshape(-1, steps + 1, 3)
    radius = np.broadcast_to(np.linspace(0.00005, 0.000012, steps + 1), world.shape[:2]).copy()
    out.append(_curves("hair", world, radius, col, M.hair(color)))
    if cut == "bun":  # the bun: strands coiled round a ball at the back of the head
        centre = _head_shape(bun[None])[0] * 1.0 + bun * 0.028
        k = 7000
        rot = _random_rotations(rnd, k)
        s = np.linspace(0, 2 * np.pi * rnd.uniform(0.8, 1.3), 16)
        r = rnd.uniform(0.018, 0.028, size=(k, 1))
        ring = np.stack([np.cos(s)[None] * r, np.sin(s)[None] * r, 0.004 * np.sin(3 * s)[None] * np.ones_like(r)], axis=2)
        coil = np.einsum("kij,ksj->ksi", rot, ring) * np.array([1.12, 0.72, 0.76]) + centre  # wider than it is tall, flattened against the head
        coil = H.world(coil.reshape(-1, 3)).reshape(k, 16, 3)
        out.append(_curves("bun", coil, np.full(coil.shape[:2], 0.00008), col, M.hair(color)))
        wisps = []
        for j in range(30):  # loose strands: at the temples, the nape and out of the bun
            a = (1.25 if j % 3 else 2.9) * (1 if j % 2 else -1) + rnd.normal(scale=0.08)
            z0 = (0.12 if j % 3 else -0.55) + rnd.normal(scale=0.05)
            q0 = _unit(np.array([[math.sin(a) * math.sqrt(1 - z0 * z0), math.cos(a) * math.sqrt(1 - z0 * z0), z0]]))[0]
            root = _head_shape(q0[None])[0] + q0 * 0.002
            fall = rnd.uniform(0.03, 0.06)
            seg = np.array([root + np.array([rnd.normal(scale=0.004), rnd.normal(scale=0.004), -fall * s]) + q0 * 0.003 * s for s in np.linspace(0, 1, 6)])
            wisps.append(seg)
        ws = H.world(np.array(wisps).reshape(-1, 3)).reshape(-1, 6, 3)
        out.append(_curves("wisps", ws, np.full(ws.shape[:2], 0.00004), col, M.hair(color)))
    if cut in ("bun", "long"):  # fine short hairs along the hairline, lying flat the way the hair goes, so it has no edge
        k = 3500
        d2 = rnd.normal(size=(k * 8, 3))
        d2 /= np.linalg.norm(d2, axis=1, keepdims=True)
        e2 = d2[:, 2] - _table(line, np.abs(np.arctan2(d2[:, 0], d2[:, 1])))
        d2 = d2[(e2 > -0.035) & (e2 < 0.05) & (rnd.random(len(d2)) < _smooth(-0.035, 0.02, e2))][:k]
        goal = bun if cut == "bun" else _unit(np.array([[0.0, -0.6, -0.8]]))[0]
        tdir = goal - d2
        tdir -= d2 * (tdir * d2).sum(1)[:, None]
        tdir = _unit(tdir + rnd.normal(scale=0.25, size=tdir.shape))
        ls = rnd.uniform(0.005, 0.016, size=(len(d2), 1))
        p2 = np.stack([_unit(d2 + tdir * ls / 0.1 * s) for s in (0.0, 0.5, 1.0)], axis=1)
        s2 = _head_shape(p2.reshape(-1, 3)).reshape(-1, 3, 3)
        s2 = s2 + s2 / np.linalg.norm(s2, axis=2, keepdims=True) * np.array([0.0, 0.0003, 0.0007])[None, :, None]
        w2 = H.world(s2.reshape(-1, 3)).reshape(-1, 3, 3)
        out.append(_curves("hairline", w2, np.full(w2.shape[:2], 0.000018), col, M.hair(color)))
    # brows: short strands lying flat, combed outwards
    brows = []
    for sx in (-1, 1):
        for j in range(600):  # about 10 mm tall at the inner end, thinning to 3 mm at the tail
            tt = rnd.random()
            u0 = sx * (0.2 + 0.42 * tt)
            z0 = 0.205 + 0.03 * math.sin(tt * math.pi) - 0.015 * tt + rnd.uniform(-1, 1) * (0.042 * (1 - tt) + 0.014)
            p0 = np.array([u0, math.sqrt(max(1 - u0 * u0 - z0 * z0, 0.05)), z0])
            p1 = p0 + np.array([sx * 0.1, 0.0, 0.02])  # 7 mm hairs
            seg = np.linspace(p0, p1, 4)
            brows.append(_head_shape(_unit(seg)) + _unit(seg) * 0.0012)
    bw = H.world(np.array(brows).reshape(-1, 3)).reshape(-1, 4, 3)
    out.append(_curves("brows", bw, np.full(bw.shape[:2], 0.0001), col, M.hair(M._shade(color, -0.18))))
    return out


def _mix_hex(a, b, t):
    ca = [int(a.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    cb = [int(b.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    return "#" + "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(ca, cb))


def _unit(x):
    return x / np.maximum(np.linalg.norm(x, axis=-1, keepdims=True), 1e-9)


def _random_rotations(rnd, k):
    q = rnd.normal(size=(k, 4))
    q /= np.linalg.norm(q, axis=1, keepdims=True)
    w, x, y, z = q.T
    return np.stack([
        np.stack([1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)], 1),
        np.stack([2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)], 1),
        np.stack([2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)], 1)], 1)


def _curves(name, pts, radius, col, mat):
    k, s = pts.shape[:2]
    cv = bpy.data.hair_curves.new(name)
    cv.add_curves([s] * k)
    cv.attributes["position"].data.foreach_set("vector", pts.astype(np.float32).ravel())
    r = cv.attributes.new("radius", "FLOAT", "POINT")
    r.data.foreach_set("value", radius.astype(np.float32).ravel())
    cv.materials.append(mat)
    ob = bpy.data.objects.new(name, cv)
    col.objects.link(ob)
    return ob


def _hand(bm, wrist, knuckle, sx, kind):
    """A hand: palm, four fingers and a thumb, resting palm down (on keys, a table or a file), or for a gesture
    turned palm up and in."""
    d = (knuckle - wrist).normalized()
    down = {"read": Vector((0, 1, 0)), "gesture": Vector((-sx * 0.25, -0.1, 0.96))}.get(kind, Vector((0, 0, -1)))
    nrm = (down - d * down.dot(d)).normalized()
    acr = d.cross(nrm).normalized()
    if acr.x * sx < 0:
        acr = -acr
    if kind == "gesture":  # turned over, the thumb comes to the outside
        acr = -acr
    _ellipsoid(bm, wrist + d * 0.05, (d, acr, nrm), (0.053, 0.042, 0.017), 18, 12)
    curl = {"desk": 0.75, "chat": 0.5, "read": 0.9, "gesture": 0.62}[kind]
    for i, off in enumerate((-0.03, -0.0105, 0.0105, 0.029)):  # index (by the thumb) to little finger
        base = wrist + d * 0.097 + acr * off
        ln = (0.047, 0.052, 0.049, 0.039)[i]
        cu = min(curl * (0.75, 0.95, 1.15, 1.35)[i], 1.2)
        mid = base + d * ln * 0.55 + nrm * ln * 0.25 * cu
        tip = mid + (d * (1 - cu * 0.5) + nrm * cu).normalized() * ln * 0.75
        _limb(bm, [base, mid, tip], [0.0084, 0.0076, 0.0064], 2, 12)
    th0 = wrist + d * 0.03 - acr * 0.028
    th1 = th0 + (d * 0.5 - acr * 0.55 + nrm * 0.45).normalized() * 0.043  # turned in towards the palm
    th2 = th1 + (d * 0.85 - acr * 0.05 + nrm * 0.5).normalized() * 0.032
    _limb(bm, [th0, th1, th2], [0.012, 0.0095, 0.008], 2, 12)


def person(col, look, kind="desk", seat=0.52, table=0.74, reach=0.42, seed=1, look_to=0.0, hands="table", moving=0.0):
    """Someone seated, facing -y, the middle of their seat at the origin. Returns their objects.

    moving > 0: their head turns that many degrees while the shutter is open (frames 0.5 to 1.5 of a 0 to 2
    sweep), the way someone talking moves in a quarter-second exposure, so the photograph shows it as blur."""
    rnd = random.Random(seed)
    build = look.get("build", 1.0)
    J = pose(kind, seat, table, reach, rnd, build, look.get("torso", 1.06), hands)  # shoulders about 58 cm above the seat
    sp = J["spine"]
    out = []
    X = Vector((1, 0, 0))

    def torso_rings(rows, grow=1.0, ease=1.0):
        rings = []
        for row in rows:
            h, hw, hd = row[:3]
            c = sp(h) + Vector((0.0, row[3] if len(row) > 3 else 0.0, 0.0))  # a row may sit back, round the neck rather than the spine
            t = (sp(h + 0.01) - sp(h - 0.01)).normalized()
            b = t.cross(X).normalized()
            rings.append((c, X, b, hw * grow * build * ease, hd * grow * ease))
        return rings

    # the top: a sweater, or a coat over a shirt
    rows = [(0.05, 0.166, 0.118), (0.14, 0.152, 0.108), (0.24, 0.139, 0.102), (0.34, 0.148, 0.108), (0.44, 0.163, 0.114),
            (0.51, 0.178, 0.108), (0.55, 0.172, 0.1), (0.585, 0.148, 0.088), (0.605, 0.108, 0.072), (0.625, 0.075, 0.06), (0.64, 0.064, 0.055)]
    coat = look.get("wear") == "coat"
    open_shirt = look.get("wear") == "shirt"  # a shirt on its own: open at the neck, sleeves rolled to mid forearm
    rolled = {}
    layers = [("shirt", look.get("shirt", "#EDE8DF"), 0.92, 0.0)] if coat else []
    if open_shirt:
        layers.append(("shirt", look["top"], 1.0, 0.0))
    else:
        layers.append(("coat" if coat else "sweater", look["top"], 1.0, 0.012 if coat else 0.0))
    for name, color, grow, longer in layers:
        bm = bmesh.new()
        own = rows + ([(0.655, 0.071, 0.064, 0.025), (0.69, 0.069, 0.066, 0.03), (0.715, 0.067, 0.066, 0.03)][:look.get("collar", 3)] if name == "coat" else [])  # a coat's collar round the neck (which rises behind the spine's line), standing 6 cm up at the back; look["collar"] rows of it (fewer: a lower collar, clear of a lifted jaw)
        if open_shirt:
            own = rows[:-1] + [(0.632, 0.082, 0.07)]  # the collar lying open round the neck, no stand
        if name == "sweater":
            own = rows[:-1]  # a crew neck at the base of the neck, not up it
        if name == "sweater" or open_shirt:  # seated, the hem rides up and rests on the thighs at the hip crease
            own = [(0.15, 0.156, 0.11), (0.215, 0.152, 0.116)] + [r_ for r_ in own if r_[0] > 0.23]  # and gathers in a soft roll above it
        r = torso_rings([(r_[0] - (longer if r_[0] < 0.1 else 0.0),) + tuple(r_[1:]) for r_ in own], grow, 1.03 if open_shirt else (1.0 if name == "shirt" else (1.06 if name == "coat" else 1.08)))
        _rings(bm, r, 28)
        for side in ("l", "r"):
            sh, el, wr = J["shoulder_" + side], J["elbow_" + side], J["wrist_" + side]
            cuff = wr + (wr - el).normalized() * (0.012 if coat else 0.0)
            end_r = 0.04
            if open_shirt:
                cuff, end_r = el.lerp(wr, 0.42), 0.045
                rolled[side] = cuff
            _limb(bm, [sh - Vector((math.copysign(0.035, sh.x), 0, 0.03)), sh - Vector((0, 0, 0.03)), el, cuff],
                  [0.06 * grow * build, 0.057 * grow * build, 0.047 * grow * build, end_r * grow * build], 5, 20, folds=0.09)
        keep = None
        if name == "coat":  # open down the front in a V, so the shirt shows
            def keep(x, y, z, sp=sp, seat=seat):
                h = z - seat
                c = sp(h)
                front_v = c.y - y > 0.04 and abs(x) < 0.08 * _smooth(0.3, 0.62, h) and h > 0.3
                return not (front_v or (h > 0.665 and y < c.y + 0.01))  # the collar's stand only at the back and sides
        if open_shirt:  # the top button undone: a narrow V at the throat
            def keep(x, y, z, sp=sp, seat=seat):
                h = z - seat
                c = sp(h)
                return not (c.y - y > 0.03 and abs(x) < 0.07 * _smooth(0.47, 0.66, h) and h > 0.47)
        fab = (M.knit(color) if name == "sweater" else M.fabric(color, 1.1, 0.3, 0.35, weave=520.0)) if name != "shirt" else M.fabric(color, 0.8, 0.2, 0.2, weave=700.0)
        out.append(_fuse(name, bm, col, fab, 0.005, (0.5, 3), folds=0.011 if name != "shirt" else (0.008 if open_shirt else 0.003), keep=keep))
        if open_shirt:  # each sleeve rolled twice into a band
            bm = bmesh.new()
            for side in ("l", "r"):
                d = (J["wrist_" + side] - J["elbow_" + side]).normalized()
                _limb(bm, [rolled[side] - d * 0.035, rolled[side] + d * 0.006], [0.05 * build, 0.049 * build], 3, 28, folds=0.1)
            out.append(_fuse("rolled sleeves", bm, col, fab, 0.004, (0.5, 2), folds=0.003))
            bm = bmesh.new()  # the shirt's hem, a turned band resting on the thighs
            _rings(bm, [(sp(h_), X, (sp(h_ + 0.005) - sp(h_ - 0.005)).normalized().cross(X).normalized(), 0.158 * 1.05 * build, 0.113 * 1.05)
                        for h_ in (0.145, 0.165)], 32)
            out.append(_fuse("shirt hem", bm, col, fab, 0.004, (0.5, 3)))
        if name == "sweater":  # ribbed cuffs and hem
            bm = bmesh.new()
            for side in ("l", "r"):
                el, wr = J["elbow_" + side], J["wrist_" + side]
                d = (wr - el).normalized()
                _limb(bm, [wr - d * 0.045, wr + d * 0.004], [0.041, 0.037], 2, 24)
            # the ribbed neckband
            _rings(bm, [(sp(h_), X, (sp(h_ + 0.005) - sp(h_ - 0.005)).normalized().cross(X).normalized(), w_ * build, d_)
                        for h_, w_, d_ in ((0.608, 0.088, 0.072), (0.632, 0.079, 0.066))], 32)
            c0, c1 = sp(0.145), sp(0.195)
            _rings(bm, [(c0, X, (sp(0.15) - sp(0.14)).normalized().cross(X).normalized(), 0.163 * 1.08 * build, 0.118 * 1.08),
                        (c1, X, (sp(0.2) - sp(0.19)).normalized().cross(X).normalized(), 0.158 * 1.08 * build, 0.113 * 1.08)], 32)
            out.append(_fuse("cuffs and hem", bm, col, M.knit(M._shade(color, -0.07), rib=True), 0.004, (0.4, 2)))

    # trousers: seat, thighs along the chair, shins down to the shoes
    bm = bmesh.new()
    _rings(bm, torso_rings([(0.0, 0.168, 0.125), (0.08, 0.168, 0.122), (0.17, 0.155, 0.11), (0.25, 0.13, 0.095)]), 28)  # up under the top
    for side in ("l", "r"):
        hip, knee, ankle = J["hip_" + side], J["knee_" + side], J["ankle_" + side]
        _limb(bm, [hip, knee, ankle - Vector((0, 0, 0.01))], [0.082, 0.062, 0.053], 6, 22, folds=0.08)
    wool = _mix_hex(look["trousers"], "#4A4A4C", 0.5)  # a wool trouser, nearer charcoal than the top
    out.append(_fuse("trousers", bm, col, M.fabric(wool, 0.9, 0.12, 0.3, weave=640.0), 0.006, (0.5, 4), folds=0.009))

    # shoes
    bm = bmesh.new()
    sole = []
    for side, sx in (("l", 1), ("r", -1)):
        ankle, splay = J["ankle_" + side], J["splay_" + side]
        fwd = Matrix.Rotation(splay, 3, "Z") @ Vector((0, -1, 0))
        acr = Vector((0, 0, 1)).cross(fwd).normalized()
        heel = Vector((ankle.x, ankle.y, 0.0)) - fwd * 0.07
        k_ = 0.95 * build ** 2  # about 27 cm for a man, 23 for a smaller build
        rows = [(s_ * k_, hw * (0.6 + 0.4 * k_), hh) for s_, hw, hh in [(0.0, 0.03, 0.055), (0.05, 0.04, 0.07), (0.12, 0.046, 0.055), (0.19, 0.045, 0.036), (0.25, 0.032, 0.025), (0.27, 0.014, 0.016)]]
        spring = lambda s, k_=k_: 0.016 * _smooth(0.17 * k_, 0.28 * k_, s)
        _rings(bm, [(heel + fwd * s + Vector((0, 0, hh / 2 + 0.022 + spring(s))), acr, Vector((0, 0, 1)), hw, hh / 2) for s, hw, hh in rows], 20)
        sole.append([(heel + fwd * s + Vector((0, 0, 0.0125 + spring(s))), acr, Vector((0, 0, 1)), hw + 0.004, 0.0125) for s, hw, _ in rows])
    out.append(_fuse("shoes", bm, col, M.leather("#1F1C1A", coat=0.0), 0.003, (0.5, 4)))
    bm = bmesh.new()
    for rings in sole:
        _rings(bm, rings, 20)
    out.append(_fuse("soles", bm, col, M.matte("#3A3430", 0.6), 0.003, (0.4, 2)))

    # hands
    bm = bmesh.new()
    for side, sx in (("l", 1), ("r", -1)):
        _hand(bm, J["wrist_" + side], J["knuckle_" + side], sx, "gesture" if (hands == "talk" and kind == "chat" and sx > 0) else kind)
        if side in rolled:  # bare forearms below the rolled sleeves
            d = (J["wrist_" + side] - J["elbow_" + side]).normalized()
            _limb(bm, [rolled[side] - d * 0.02, J["wrist_" + side]], [0.037 * build, 0.029 * build], 5, 28)
    out.append(_fuse("hands", bm, col, M.skin(look["skin"]), 0.0012, (0.3, 1)))  # light smoothing keeps the gaps between fingers

    bm = bmesh.new()  # a watch on the left wrist: a strap and a small round face
    d = (J["knuckle_l"] - J["wrist_l"]).normalized()
    _limb(bm, [J["wrist_l"] - d * 0.012, J["wrist_l"] - d * 0.001], [0.0305 * build, 0.0305 * build], 2, 32)
    out.append(_obj("watch strap", bm, col, M.leather("#2A211C", coat=0.0)))
    up_ = Vector((0, 0, 1)) - d * d.z
    bm = bmesh.new()
    _ellipsoid(bm, J["wrist_l"] - d * 0.0065 + up_.normalized() * 0.03 * build, (d, d.cross(up_).normalized(), up_.normalized()), (0.016, 0.016, 0.004), 24, 8)
    out.append(_obj("watch", bm, col, M.steel("#C9C6C0", 0.2)))
    if hands in ("glass", "talk"):  # a tumbler of water in the hand on the table
        k = J["knuckle_r"]
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=40, radius1=0.032, radius2=0.036, depth=0.095,
                              matrix=Matrix.Translation(Vector((k.x + 0.06, k.y - 0.01, table + 0.0475))))
        out.append(_obj("glass", bm, col, M.glass()))
    if kind == "read":  # an open file held up to read: a card cover and its pages
        kl, kr = J["knuckle_l"], J["knuckle_r"]
        mid = (kl + kr) / 2 + Vector((0, -0.06, 0.05))
        tilt = Matrix.Rotation(math.radians(-25), 4, "X")
        for name, (w, h, th, dz), mat in (("file cover", (0.25, 0.32, 0.003, 0.0), M.matte("#2F3B36", 0.6)),
                                          ("pages", (0.23, 0.3, 0.008, 0.006), M.matte("#F1EDE4", 0.85))):
            bm = bmesh.new()
            bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(mid) @ tilt @ Matrix.Translation((0, 0, dz)) @ Matrix.Diagonal((w, h, th, 1)))
            out.append(_obj(name, bm, col, mat, smooth=False))

    H = _Head(J["head"], J["yaw"] + look_to, J["nod"] + look.get("nod", 0.0), look.get("roll", 0.0))
    heads = _head(col, H, look, look.get("cut", "short"), sp(0.5 if open_shirt else 0.565) + Vector((0, 0.008, 0)),
                  (sp(0.5) + Vector((0, -0.025, 0)), (0.115 * build, 0.08, 0.09)) if open_shirt else None)  # an open collar shows the throat
    for o in heads:  # the live building turns the head on its own (people_export.py): about the top of the neck
        o["part"] = "head"
        o["pivot"] = list(H.c - H.u * 0.07 - H.f * 0.02)
    pivot = H.c - H.u * 0.1  # the head 5% larger than built, about the top of the neck
    grow = Matrix.Translation(pivot) @ Matrix.Scale(1.0, 4) @ Matrix.Translation(-pivot)
    for o in heads:
        o.matrix_basis = grow @ o.matrix_basis
    if moving:
        pivot_at = H.c - H.u * 0.07 - H.f * 0.02  # the top of the neck
        pivot = bpy.data.objects.new("head turning", None)
        col.objects.link(pivot)
        pivot.location = pivot_at
        for o in heads:
            o.parent = pivot
            o.matrix_parent_inverse = Matrix.Translation(-pivot_at)
        a = math.radians(moving)
        for frame, s in ((0, -1.0), (2, 1.0)):
            pivot.rotation_euler = (s * a * 0.25, 0.0, s * a)
            pivot.keyframe_insert("rotation_euler", frame=frame)
        for fc in pivot.animation_data.action.fcurves if hasattr(pivot.animation_data.action, "fcurves") else []:
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"
        out.append(pivot)
    else:
        out += heads
    return out
