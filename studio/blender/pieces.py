"""Furniture, plants, lamps and things, each built from code at the origin, facing -Y (its front), on the floor.

Every builder takes a collection and keyword sizes, and returns the list of objects it made.
"""
import math
import random

import bmesh
import bpy
from mathutils import Matrix, Vector

import kit
import materials as M


# ---------- shapes ----------

def rbox(name, lo, hi, col, mat, r=0.01, soft=False):
    """A box with rounded edges; soft=True rounds it right off, like a cushion."""
    ob = kit.box(name, lo, hi, col, mat, bevel=0 if soft else r, segments=3)
    if soft:
        kit.add_bevel(ob, r, 3)
        kit.subsurf(ob, 2)
    return ob


def tube(name, pts, radius, col, mat, sides=12, cap=True):
    """A round tube along a polyline of points."""
    bm = bmesh.new()
    pts = [Vector(p) for p in pts]
    rings = []
    for i, p in enumerate(pts):
        d = (pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]).normalized()
        up = Vector((0, 0, 1)) if abs(d.z) < 0.9 else Vector((1, 0, 0))
        u = d.cross(up).normalized()
        v = d.cross(u).normalized()
        r = radius(i / max(1, len(pts) - 1)) if callable(radius) else radius
        rings.append([bm.verts.new(p + (u * math.cos(a) + v * math.sin(a)) * r) for a in (2 * math.pi * k / sides for k in range(sides))])
    for a, b in zip(rings, rings[1:]):
        for k in range(sides):
            bm.faces.new((a[k], a[(k + 1) % sides], b[(k + 1) % sides], b[k]))
    if cap:
        bm.faces.new(list(reversed(rings[0])))
        bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return kit.obj_from_bmesh(name, bm, col, mat, smooth=True)


def bent_panel(name, width, height, thick, radius, col, mat, z0=0.0, y0=0.0, tilt=0.0, soft=True):
    """A panel curved round a vertical axis behind it (a chair back): width along X, height up Z."""
    bm = bmesh.new()
    nx, nz = 16, 6
    grid = []
    for k in range(2):
        layer = []
        for j in range(nz + 1):
            row = []
            for i in range(nx + 1):
                s = (i / nx - 0.5) * width
                a = s / radius
                rr = radius + (thick if k else 0)
                x = math.sin(a) * rr
                y = radius - math.cos(a) * rr
                z = z0 + j / nz * height
                y += y0 + (z - z0) * math.tan(tilt)
                row.append(bm.verts.new((x, y, z)))
            layer.append(row)
        grid.append(layer)
    for k in range(2):
        L = grid[k]
        for j in range(nz):
            for i in range(nx):
                q = (L[j][i], L[j][i + 1], L[j + 1][i + 1], L[j + 1][i])
                bm.faces.new(q if k else q[::-1])
    A, B = grid
    for j in range(nz):
        bm.faces.new((A[j][0], A[j + 1][0], B[j + 1][0], B[j][0]))
        bm.faces.new((A[j][nx], B[j][nx], B[j + 1][nx], A[j + 1][nx]))
    for i in range(nx):
        bm.faces.new((A[0][i], B[0][i], B[0][i + 1], A[0][i + 1]))
        bm.faces.new((A[nz][i], A[nz][i + 1], B[nz][i + 1], B[nz][i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = kit.obj_from_bmesh(name, bm, col, mat, smooth=True)
    if soft:
        kit.subsurf(ob, 2)
    return ob


def ring_sector(name, r_in, r_out, a0, a1, z0, z1, col, mat, soft=0.03):
    """Part of a thick ring (a curved sofa's seat or back), centred on the origin."""
    bm = bmesh.new()
    n = max(8, int(abs(a1 - a0) / math.radians(6)))
    rows = []
    for i in range(n + 1):
        a = a0 + (a1 - a0) * i / n
        c, s = math.cos(a), math.sin(a)
        rows.append([bm.verts.new((r * c, r * s, z)) for r, z in ((r_in, z0), (r_out, z0), (r_out, z1), (r_in, z1))])
    for a, b in zip(rows, rows[1:]):
        for k in range(4):
            bm.faces.new((a[k], a[(k + 1) % 4], b[(k + 1) % 4], b[k]))
    bm.faces.new(rows[0][::-1])
    bm.faces.new(rows[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = kit.obj_from_bmesh(name, bm, col, mat, smooth=True)
    kit.add_bevel(ob, soft, 3)
    kit.subsurf(ob, 2)
    return ob


# ---------- tables and storage ----------

def table(col, w=1.6, d=0.8, h=0.74, top="oak", legs="black", style="four", top_th=0.03, round_=False, tone="#CDAA80"):
    top_mat = M.oak(tone, 24.0, "X") if top == "oak" else M.stone() if top == "stone" else M.matte("#F0EEE9", 0.3) if top == "white" else M.matte("#222222", 0.3)
    leg_mat = M.matte("#1C1C1C", 0.4) if legs == "black" else M.oak(tone, 30.0, "Z")
    out = []
    if round_:
        out.append(kit.cylinder("top", Vector((0, 0, h - top_th / 2)), w / 2, top_th, col, top_mat, 96, bevel=0.006))
    else:
        out.append(rbox("top", (-w / 2, -d / 2, h - top_th), (w / 2, d / 2, h), col, top_mat, 0.006))
    lt = 0.04 if legs == "black" else 0.05
    if style == "four":
        inset = 0.06
        for sx in (-1, 1):
            for sy in (-1, 1):
                x, y = sx * (w / 2 - inset), sy * (d / 2 - inset)
                if legs == "black":
                    out.append(rbox("leg", (x - lt / 2, y - lt / 2, 0), (x + lt / 2, y + lt / 2, h - top_th), col, leg_mat, 0.004))
                else:
                    out.append(tube("leg", [(x, y, 0), (x, y, h - top_th)], lambda t: 0.022 + 0.008 * t, col, leg_mat, 16))
        if legs == "black":
            out.append(rbox("rail", (-w / 2 + inset, -d / 2 + inset - lt / 2, h - top_th - 0.06), (w / 2 - inset, -d / 2 + inset + lt / 2, h - top_th), col, leg_mat, 0.003))
            out.append(rbox("rail", (-w / 2 + inset, d / 2 - inset - lt / 2, h - top_th - 0.06), (w / 2 - inset, d / 2 - inset + lt / 2, h - top_th), col, leg_mat, 0.003))
    elif style == "sled":  # a closed rectangle of flat steel at each end
        for sx in (-1, 1):
            x = sx * (w / 2 - 0.08)
            out += [rbox("sled", (x - 0.012, -d / 2 + 0.04, 0), (x + 0.012, d / 2 - 0.04, 0.03), col, leg_mat, 0.003),
                    rbox("sled", (x - 0.012, -d / 2 + 0.04, h - top_th - 0.03), (x + 0.012, d / 2 - 0.04, h - top_th), col, leg_mat, 0.003),
                    rbox("sled", (x - 0.012, -d / 2 + 0.04, 0), (x + 0.012, -d / 2 + 0.07, h - top_th), col, leg_mat, 0.003),
                    rbox("sled", (x - 0.012, d / 2 - 0.07, 0), (x + 0.012, d / 2 - 0.04, h - top_th), col, leg_mat, 0.003)]
    elif style == "pedestal":
        out.append(kit.cylinder("stem", Vector((0, 0, (h - top_th) / 2)), min(w, d) * 0.16, h - top_th, col, top_mat if top == "stone" else leg_mat, 64, bevel=0.004))
        out.append(kit.cylinder("foot", Vector((0, 0, 0.01)), min(w, d) * 0.3, 0.02, col, leg_mat, 64, bevel=0.004))
    elif style == "plinth":
        out.append(rbox("plinth", (-w * 0.32, -d * 0.32, 0), (w * 0.32, d * 0.32, h - top_th), col, top_mat, 0.01))
    return out


def sideboard(col, w=1.8, d=0.45, h=0.72, tone="#CDAA80", legs=True):
    wood = M.oak(tone, 26.0, "Z")
    black = M.matte("#1C1C1C", 0.4)
    lift = 0.16 if legs else 0.0
    out = [rbox("carcass", (-w / 2, -d / 2, lift), (w / 2, d / 2, h), col, wood, 0.006)]
    n = max(2, round(w / 0.45))
    for i in range(1, n):  # shadow gaps between the doors
        x = -w / 2 + w * i / n
        out.append(kit.box("gap", (x - 0.002, -d / 2 - 0.001, lift + 0.02), (x + 0.002, -d / 2 + 0.004, h - 0.02), col, black))
    if legs:
        for sx in (-1, 1):
            for sy in (-1, 1):
                out.append(tube("leg", [(sx * (w / 2 - 0.08), sy * (d / 2 - 0.08), 0), (sx * (w / 2 - 0.08), sy * (d / 2 - 0.08), lift)], 0.015, col, black, 12))
    return out


def shelves(col, w=1.6, n=3, depth=0.26, z0=1.0, gap=0.38, tone="#CDAA80"):
    wood = M.oak(tone, 26.0, "X")
    return [rbox(f"shelf{i}", (-w / 2, 0, z0 + i * gap), (w / 2, depth, z0 + i * gap + 0.035), col, wood, 0.004) for i in range(n)]


def bookcase(col, w=1.8, h=2.2, depth=0.34, cols=3, rows=5, tone="#CDAA80", seed=1, filled=True):
    """Oak shelves, filled with books and the odd object unless filled=False (the live building's empty case)."""
    wood = M.oak(tone, 26.0, "Z")
    t = 0.025
    out = [rbox("side", (-w / 2, 0, 0), (-w / 2 + t, depth, h), col, wood, 0.003),
           rbox("side", (w / 2 - t, 0, 0), (w / 2, depth, h), col, wood, 0.003),
           kit.box("back", (-w / 2, depth - 0.01, 0), (w / 2, depth, h), col, M.matte("#E9E3D9", 0.8))]
    for i in range(cols - 1):
        x = -w / 2 + w * (i + 1) / cols
        out.append(rbox("div", (x - t / 2, 0, 0), (x + t / 2, depth, h), col, wood, 0.003))
    for j in range(rows + 1):
        z = j * (h - t) / rows
        out.append(rbox("board", (-w / 2, 0, z), (w / 2, depth, z + t), col, wood, 0.003))
    rnd = random.Random(seed)
    for j in range(rows if filled else 0):
        z = j * (h - t) / rows + t
        for i in range(cols):
            x0 = -w / 2 + w * i / cols + t
            x1 = -w / 2 + w * (i + 1) / cols - t
            what = rnd.random()
            if what < 0.9:
                out += books(col, x0 + 0.01, x0 + (x1 - x0) * rnd.uniform(0.78, 0.97), z, depth * 0.85, rnd)
            elif what < 0.93:
                out += objet(col, ((x0 + x1) / 2 + rnd.uniform(-0.1, 0.1), depth * 0.45, z), rnd)
    return out


BOOK_COLOURS = ["#E8E1D4", "#C9B79C", "#D8CBB5", "#B9A27E", "#9A8F7E", "#E4D9C4"]
BOOK_DEEP = ["#23324A", "#6B2A2A", "#2F4A3A", "#B88A3A", "#1E2328", "#6F4E37", "#22304A", "#6B2B26", "#B08A3E"]


def books(col, x0, x1, z, depth, rnd):
    out = []
    x = x0
    stack = rnd.random() < 0.6 and x1 - x0 > 0.3
    end = x1 - (0.25 if stack else 0.0)
    band_mats = [M.matte("#B8964E", 0.4), M.matte("#151515", 0.6), M.matte("#E8E1D4", 0.7)]
    while x < end - 0.02:
        t = rnd.uniform(0.015, 0.05)
        h = rnd.uniform(0.18, 0.3)
        dd = min(depth - 0.03, rnd.uniform(0.12, 0.24))
        tone = rnd.choice(BOOK_DEEP) if rnd.random() < 0.7 else rnd.choice(BOOK_COLOURS)
        mat = M.matte(tone, rnd.choice([0.6, 0.7, 0.8]))
        parts = [rbox("book", (0, -dd / 2, 0), (t, dd / 2, h), col, mat, 0.002)]
        for k in range(rnd.choice([0, 1, 1, 2])):  # thin bands printed across the spine
            bz = h * rnd.choice([0.12, 0.2, 0.78, 0.85]) + k * 0.012
            parts.append(kit.box("spine band", (0.001, -dd / 2 - 0.0006, bz), (t - 0.001, -dd / 2, bz + 0.006), col, rnd.choice(band_mats)))
        lean = math.radians(rnd.uniform(5, 15)) if rnd.random() < 0.15 and x > x0 + 0.05 else 0.0
        root = kit.place(parts, (x, depth - 0.02 - dd / 2, z), 0.0, "book", col)
        root.rotation_euler = (0, lean, 0)
        out.append(root)
        x += t + 0.001 + (math.sin(lean) * h if lean else 0.0)
    if stack:  # a short stack lying flat
        y = depth / 2
        zz = z
        for k in range(rnd.randint(2, 4)):
            tt = rnd.uniform(0.02, 0.035)
            ww = rnd.uniform(0.15, 0.22)
            cover = M.matte(rnd.choice(BOOK_DEEP + BOOK_COLOURS), 0.7)
            out.append(rbox("book", (x1 - ww - 0.02, y - 0.1, zz), (x1 - 0.02, y + 0.1, zz + 0.003), col, cover, 0.001))
            out.append(rbox("book", (x1 - ww - 0.02, y - 0.1, zz + tt - 0.003), (x1 - 0.02, y + 0.1, zz + tt), col, cover, 0.001))
            out.append(rbox("spine", (x1 - 0.024, y - 0.1, zz), (x1 - 0.02, y + 0.1, zz + tt), col, cover, 0.0015))
            out.append(kit.box("pages", (x1 - ww - 0.017, y - 0.097, zz + 0.003), (x1 - 0.024, y + 0.097, zz + tt - 0.003), col, M.matte("#EDE6D6", 0.85)))
            zz += tt
    return out


def objet(col, at, rnd):
    """A vase, a bowl or a little sculpture."""
    x, y, z = at
    kind = rnd.choice(["vase", "bowl", "vase", "vase"])
    glaze = M.ceramic(rnd.choice(["#E9E2D6", "#B9653E", "#2D2D2B", "#C9BBA4", "#7E8B74"]), rnd.choice([0.2, 0.55]))
    if kind == "vase":
        hgt = rnd.uniform(0.14, 0.3)
        prof = [(0.0, 0), (0.05, 0), (0.07, hgt * 0.35), (0.055, hgt * 0.75), (0.03, hgt * 0.92), (0.032, hgt), (0.0, hgt * 0.99)]
        return [kit.lathe("vase", prof, col, glaze, 48, (x, y, z))]
    if kind == "bowl":
        prof = [(0.0, 0.0), (0.06, 0.0), (0.12, 0.05), (0.13, 0.07), (0.12, 0.068), (0.0, 0.02)]
        return [kit.lathe("bowl", prof, col, glaze, 48, (x, y, z))]
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=0.07)
    bmesh.ops.translate(bm, vec=(x, y, z + 0.07), verts=bm.verts)
    return [kit.obj_from_bmesh("sphere", bm, col, glaze, smooth=True)]


# ---------- seating ----------

def shell_chair(col, fabric="#D8CDBD", tone="#CDAA80", arms=False):
    fab = M.fabric(fabric, 1.6, 0.3, 0.55, weave=320.0)
    wood = M.oak(tone, 30.0, "Z")
    out = [rbox("seat", (-0.23, -0.24, 0.42), (0.23, 0.2, 0.47), col, fab, 0.025, soft=True),
           bent_panel("back", 0.48, 0.36, 0.035, 0.32, col, fab, z0=0.47, y0=0.16, tilt=math.radians(12))]
    for sx in (-1, 1):
        for sy in (-1, 1):
            out.append(tube("leg", [(sx * 0.19, sy * 0.19 - 0.02, 0.42), (sx * 0.23, sy * 0.24 - 0.02, 0.0)], lambda t: 0.016 - 0.005 * t, col, wood, 12))
    return out


def task_chair(col, fabric="#3F4743"):
    fab = M.fabric(fabric, 1.4, 0.4, 0.5, weave=360.0)
    black = M.matte("#1C1C1C", 0.38)
    steel_ = M.steel("#B8BCC0", 0.3)
    out = [rbox("seat", (-0.245, -0.25, 0.43), (0.245, 0.22, 0.52), col, fab, 0.045, soft=True),
           bent_panel("back", 0.46, 0.52, 0.055, 0.38, col, fab, z0=0.6, y0=0.24, tilt=math.radians(10)),
           rbox("spine", (-0.025, 0.27, 0.44), (0.025, 0.31, 0.7), col, black, 0.01),
           kit.cylinder("gas", Vector((0, 0, 0.3)), 0.025, 0.28, col, steel_, 24),
           kit.cylinder("hub", Vector((0, 0, 0.13)), 0.04, 0.06, col, black, 24)]
    for k in range(5):
        a = 2 * math.pi * k / 5 + math.pi / 2
        c, s = math.cos(a), math.sin(a)
        out.append(tube("arm", [(0, 0, 0.12), (c * 0.32, s * 0.32, 0.07)], 0.018, col, black, 10))
        out.append(kit.cylinder("castor", Vector((c * 0.32, s * 0.32, 0.03)), 0.03, 0.025, col, black, 20, axis="X"))
    for sx in (-1, 1):
        out.append(rbox("armrest", (sx * 0.27 - 0.03, -0.12, 0.66), (sx * 0.27 + 0.03, 0.14, 0.69), col, black, 0.012))
        out.append(rbox("armpost", (sx * 0.27 - 0.012, 0.0, 0.47), (sx * 0.27 + 0.012, 0.03, 0.66), col, black, 0.006))
    return out


def stool(col, h=0.65, tone="#CDAA80"):
    wood = M.oak(tone, 30.0, "Z")
    black = M.matte("#1C1C1C", 0.4)
    out = [kit.cylinder("seat", Vector((0, 0, h - 0.02)), 0.18, 0.04, col, wood, 64, bevel=0.01)]
    for k in range(4):
        a = math.pi / 4 + k * math.pi / 2
        out.append(tube("leg", [(math.cos(a) * 0.12, math.sin(a) * 0.12, h - 0.04), (math.cos(a) * 0.19, math.sin(a) * 0.19, 0)], 0.012, col, black, 10))
    out.append(tube("ring", [(math.cos(a) * 0.165, math.sin(a) * 0.165, 0.25) for a in (2 * math.pi * k / 32 for k in range(33))], 0.007, col, black, 8, cap=False))
    return out


def sofa(col, w=2.2, d=0.95, fabric="#ECE6DC", legs="none", seat_h=0.42, back_h=0.78, arms=True, cushions=(), loops=0.7):
    fab = M.fabric(fabric, loops, 0.45, 0.6, weave=420.0)
    out = [rbox("base", (-w / 2, -d / 2, 0.05 if legs != "none" else 0.0), (w / 2, d / 2, 0.3), col, fab, 0.05, soft=True)]
    arm_w = 0.22 if arms else 0.0
    n = 2 if w < 2.0 else 3
    inner = w - 2 * arm_w
    for i in range(n):
        x0 = -inner / 2 + inner * i / n + 0.005
        x1 = -inner / 2 + inner * (i + 1) / n - 0.005
        out.append(rbox("seat", (x0, -d / 2 + 0.02, 0.28), (x1, d / 2 - 0.2, seat_h), col, fab, 0.06, soft=True))
        out.append(rbox("back", (x0, d / 2 - 0.24, 0.3), (x1, d / 2 - 0.02, back_h), col, fab, 0.07, soft=True))
    if arms:
        for sx in (-1, 1):
            out.append(rbox("arm", (sx * w / 2 - (arm_w if sx > 0 else 0), -d / 2, 0.05), (sx * w / 2 + (0 if sx > 0 else arm_w), d / 2, 0.62), col, fab, 0.07, soft=True))
    rnd = random.Random(len(cushions) + int(w * 10))
    for k, ccol in enumerate(cushions):  # throw cushions leaning on the back
        x = (-1 if k % 2 == 0 else 1) * (inner / 2 - 0.3 - 0.12 * (k // 2))
        cu = rbox("cushion", (-0.225, -0.07, -0.225), (0.225, 0.07, 0.225), col, M.fabric(ccol, 1.2, 0.4, 0.5, weave=300.0), 0.07, soft=True)
        root = kit.place([cu], (x, d / 2 - 0.32, seat_h + 0.22), 0.0, "cushion", col)
        root.rotation_euler = (math.radians(-12), rnd.uniform(-0.12, 0.12), (-1 if k % 2 == 0 else 1) * rnd.uniform(0.1, 0.3))
        out.append(root)
    if legs != "none":
        black = M.matte("#1C1C1C", 0.4)
        for sx in (-1, 1):
            for sy in (-1, 1):
                out.append(tube("leg", [(sx * (w / 2 - 0.08), sy * (d / 2 - 0.08), 0), (sx * (w / 2 - 0.08), sy * (d / 2 - 0.08), 0.06)], 0.02, col, black, 12))
    return out


def curved_sofa(col, radius=1.6, span=110, depth=0.95, fabric="#EFEAE2"):
    """A cloud of a sofa on an arc, the seat facing the arc's centre."""
    fab = M.fabric(fabric, 0.8, 0.65)
    a0, a1 = math.radians(90 - span / 2), math.radians(90 + span / 2)
    r0 = radius
    return [ring_sector("seat", r0, r0 + depth, a0, a1, 0.0, 0.42, col, fab, 0.09),
            ring_sector("back", r0 + depth - 0.28, r0 + depth, a0, a1, 0.4, 0.8, col, fab, 0.1)]


def lounge_chair(col, fabric="#8E5B32", kind="leather", tone="#CDAA80"):
    """A low Danish lounge chair: a light oak frame on splayed legs, flat arms, loose seat and back cushions."""
    mat = M.leather(fabric) if kind == "leather" else M.fabric(fabric, 0.8, 0.6)
    wood = M.oak(tone, 30.0, "Z")
    out = []
    for sx in (-1, 1):
        for sy, top_z in ((-1, 0.56), (1, 0.56)):
            fx, fy = sx * 0.33, sy * 0.3
            out.append(tube("leg", [(fx + sx * 0.03, fy + sy * 0.04, 0.0), (fx, fy, top_z)], lambda t: 0.019 - 0.004 * t, col, wood, 12))
        out.append(rbox("arm", (sx * 0.33 - 0.035, -0.37, 0.56), (sx * 0.33 + 0.035, 0.33, 0.59), col, wood, 0.01))
        out.append(rbox("side rail", (sx * 0.33 - 0.014, -0.3, 0.24), (sx * 0.33 + 0.014, 0.3, 0.29), col, wood, 0.006))
    out += [rbox("front rail", (-0.33, -0.31, 0.24), (0.33, -0.28, 0.29), col, wood, 0.006),
            rbox("back rail", (-0.33, 0.27, 0.24), (0.33, 0.3, 0.29), col, wood, 0.006),
            rbox("seat cushion", (-0.29, -0.33, 0.27), (0.29, 0.26, 0.42), col, mat, 0.05, soft=True)]
    back = rbox("back cushion", (-0.29, -0.06, 0.0), (0.29, 0.06, 0.52), col, mat, 0.05, soft=True)
    root = kit.place([back], (0, 0.22, 0.38), 0.0, "back", col)
    root.rotation_euler = (math.radians(-16), 0, 0)
    out.append(root)
    for sx in (-1, 1):  # the back's two posts, raked with the cushion
        out.append(tube("back post", [(sx * 0.33, 0.3, 0.29), (sx * 0.33, 0.44, 0.86)], 0.017, col, wood, 10))
    out.append(rbox("back rail top", (-0.34, 0.41, 0.8), (0.34, 0.45, 0.84), col, wood, 0.008))
    return out


# ---------- soft things ----------

def rug(col, w=2.4, d=1.7, color="#D9CFC0", round_=False):
    """A wool rug 14 mm thick with a pile you can see, its edge bound in a darker tape 35 mm wide."""
    mat = M.fabric(color, 0.45, 0.3, 1.0)
    if round_:
        return [kit.cylinder("rug", Vector((0, 0, 0.0075)), w / 2, 0.015, col, mat, 96, bevel=0.006)]
    tape = M.fabric(M._shade(color, -0.12), 1.4, 0.3, 0.5, weave=300.0)
    e, t = 0.035, 0.002
    lo = -0.009  # set into the floor: 4 mm of pile and 6 mm of tape stand proud, so feet stand on it, not in it
    out = [rbox("rug", (-w / 2, -d / 2, lo), (w / 2, d / 2, 0.004), col, mat, 0.003)]
    out += [rbox("rug edge", (-w / 2 - t, -d / 2 - t, lo), (w / 2 + t, -d / 2 + e, 0.006), col, tape, 0.003),
            rbox("rug edge", (-w / 2 - t, d / 2 - e, lo), (w / 2 + t, d / 2 + t, 0.006), col, tape, 0.003),
            rbox("rug edge", (-w / 2 - t, -d / 2 + e, lo), (-w / 2 + e, d / 2 - e, 0.006), col, tape, 0.003),
            rbox("rug edge", (w / 2 - e, -d / 2 + e, lo), (w / 2 + t, d / 2 - e, 0.006), col, tape, 0.003)]
    return out


def throw(col, sofa_w, color="#B5603F", at_y=-0.05, width=0.42, arm_w=0.22, arm_h=0.62, seat_h=0.42):
    """A linen throw folded over the sofa's left arm (its +x end): over the top, down the outside, onto the seat."""
    cloth = M.fabric(color, 1.3, 0.35, 0.5, weave=260.0)
    xo = sofa_w / 2
    y0, y1 = at_y - width / 2, at_y + width / 2
    return [rbox("throw", (xo - arm_w - 0.015, y0, arm_h - 0.022), (xo + 0.012, y1, arm_h - 0.004), col, cloth, 0.008, soft=True),
            rbox("throw", (xo - 0.004, y0 + 0.01, arm_h - 0.34), (xo + 0.012, y1 - 0.01, arm_h - 0.01), col, cloth, 0.006, soft=True),
            rbox("throw", (xo - arm_w - 0.022, y0 + 0.005, seat_h - 0.01), (xo - arm_w - 0.004, y1 - 0.005, arm_h - 0.01), col, cloth, 0.006, soft=True),
            rbox("throw", (xo - arm_w - 0.3, y0 + 0.02, seat_h - 0.012), (xo - arm_w - 0.01, y1 - 0.02, seat_h + 0.004), col, cloth, 0.006, soft=True)]


def book_stack(col, n=3, seed=1):
    """Hardbacks lying flat, each a cloth cover round a cream page block, turned a little against each other."""
    rnd = random.Random(seed)
    out, z = [], 0.0
    pages = M.matte("#EFE8DA", 0.85)
    for k in range(n):
        w, d, t = rnd.uniform(0.2, 0.26), rnd.uniform(0.15, 0.19), rnd.uniform(0.022, 0.034)
        cover = M.matte(rnd.choice(BOOK_DEEP + BOOK_COLOURS[1:4]), 0.7)
        parts = [rbox("cover", (-w / 2, -d / 2, 0.0), (w / 2, d / 2, 0.003), col, cover, 0.001),
                 rbox("cover", (-w / 2, -d / 2, t - 0.003), (w / 2, d / 2, t), col, cover, 0.001),
                 rbox("spine", (-w / 2, d / 2 - 0.004, 0.0), (w / 2, d / 2, t), col, cover, 0.0015),
                 kit.box("pages", (-w / 2 + 0.003, -d / 2 + 0.003, 0.003), (w / 2 - 0.003, d / 2 - 0.004, t - 0.003), col, pages)]
        root = kit.place(parts, (rnd.uniform(-0.01, 0.01), rnd.uniform(-0.01, 0.01), z), rnd.uniform(-0.12, 0.12), "book", col)
        out.append(root)
        z += t
    return out


def sheer(col, w=1.6, h=2.75, color="#F3F1EC"):
    """A sheer curtain, softly pleated, hung from the ceiling."""
    bm = bmesh.new()
    nx, nz = max(8, int(w / 0.04)), 6
    grid = [[bm.verts.new(((i / nx - 0.5) * w, 0.025 * math.sin(i / nx * w / 0.12 * math.pi), j / nz * h)) for i in range(nx + 1)] for j in range(nz + 1)]
    for j in range(nz):
        for i in range(nx):
            bm.faces.new((grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]))
    ob = kit.obj_from_bmesh("sheer", bm, col, None, smooth=True)
    mat = bpy.data.materials.get("sheer") or bpy.data.materials.new("sheer")
    g = M.G(mat)
    g.set(**{"Base Color": M.hex_rgb(color), "Roughness": 0.9, "Transmission Weight": 0.55, "Thin Wall": True, "Sheen Weight": 0.4})
    ob.data.materials.append(mat)
    return [ob]


# ---------- light ----------

def pendant_linear(col, length=1.6, drop=0.7, ceiling=3.0, color="#FFE6C4"):
    black = M.matte("#1C1C1C", 0.35)
    z = ceiling - drop
    out = [rbox("bar", (-length / 2, -0.025, z), (length / 2, 0.025, z + 0.04), col, black, 0.006),
           kit.box("diffuser", (-length / 2 + 0.01, -0.018, z - 0.002), (length / 2 - 0.01, 0.018, z + 0.001), col, M.glow(color, 90.0))]
    for sx in (-1, 1):
        out.append(tube("cable", [(sx * length * 0.4, 0, z + 0.04), (sx * length * 0.4, 0, ceiling)], 0.0015, col, black, 6))
        out.append(kit.cylinder("canopy", Vector((sx * length * 0.4, 0, ceiling - 0.01)), 0.04, 0.02, col, M.matte("#F2F0EB", 0.4), 32, bevel=0.003))
    return out


def pendant_globe(col, radius=0.16, drop=0.8, ceiling=3.0, glow=20.0):
    """An opal glass globe. glow 20 is lit; a low glow is a globe left on by day, shaded by the window light."""
    z = ceiling - drop
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=24, radius=radius)
    bmesh.ops.translate(bm, vec=(0, 0, z), verts=bm.verts)
    name = "opal" if glow >= 20.0 else f"opal {glow:g}"
    glass = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    g = M.G(glass)
    if glow >= 20.0:
        g.set(**{"Base Color": M.hex_rgb("#F8F3EA"), "Roughness": 0.25, "Emission Color": M.hex_rgb("#FFE3BC"), "Emission Strength": 20.0, "Subsurface Weight": 0.3})
    else:
        g.set(**{"Base Color": M.hex_rgb("#ECEAE4"), "Roughness": 0.35, "Transmission Weight": 0.25, "Emission Color": M.hex_rgb("#FFE3BC"),
                 "Emission Strength": glow, "Subsurface Weight": 0.3, "Coat Weight": 0.4, "Coat Roughness": 0.08})
    return [kit.obj_from_bmesh("globe", bm, col, glass, smooth=True),
            tube("cable", [(0, 0, z + radius), (0, 0, ceiling)], 0.0018, col, M.matte("#1C1C1C", 0.4), 6),
            kit.cylinder("canopy", Vector((0, 0, ceiling - 0.012)), 0.05, 0.025, col, M.matte("#1C1C1C", 0.4), 32)]


def pendant_cone(col, radius=0.2, drop=0.9, ceiling=3.0, color="#1C1C1C"):
    z = ceiling - drop
    shade = kit.lathe("shade", [(radius, z), (radius * 0.98, z + 0.005), (0.035, z + radius * 0.9), (0.03, z + radius), (0.0, z + radius)], col, M.matte(color, 0.4), 64)
    shade.modifiers.new("thick", "SOLIDIFY").thickness = 0.003
    return [shade, kit.box("bulb", (-0.03, -0.03, z + 0.02), (0.03, 0.03, z + 0.06), col, M.glow("#FFDDB0", 120.0)),
            tube("cable", [(0, 0, z + radius), (0, 0, ceiling)], 0.0018, col, M.matte("#1C1C1C", 0.4), 6)]


def floor_lamp(col, h=1.55, shade_color="#EDE5D6"):
    black = M.matte("#1C1C1C", 0.4)
    out = [kit.cylinder("base", Vector((0, 0, 0.01)), 0.14, 0.02, col, black, 48, bevel=0.004),
           tube("pole", [(0, 0, 0.02), (0, 0, h)], 0.009, col, black, 10)]
    shade = kit.lathe("shade", [(0.2, h - 0.1), (0.2, h + 0.18), (0.0, h + 0.18)], col, M.fabric(shade_color, 0.6, 0.2), 64)
    out.append(shade)
    out.append(kit.box("bulb", (-0.03, -0.03, h - 0.02), (0.03, 0.03, h + 0.04), col, M.glow("#FFDDB0", 45.0)))
    return out


def table_lamp(col, h=0.42, color="#E8DCC6", lit=False):
    shade = M.glow("#FFE7C9", 8.0) if lit else M.fabric("#ECE4D6", 0.7, 0.3, 0.15)
    prof = [(0.165, h - 0.17), (0.164, h - 0.13), (0.161, h - 0.085), (0.156, h - 0.04), (0.151, h)]
    return [kit.lathe("lamp base", [(0.0, 0), (0.07, 0), (0.08, 0.04), (0.03, 0.08), (0.025, h - 0.12), (0.0, h - 0.12)], col, M.ceramic(color, 0.35), 64),
            kit.lathe("lamp shade", prof, col, shade, 96),
            kit.lathe("bulb", [(0.0, h - 0.13), (0.028, h - 0.115), (0.03, h - 0.085), (0.0, h - 0.055)], col, M.matte("#F6F3EC", 0.3), 32)]


# ---------- plants ----------

def leaf_geometry(bm, length, width, curl, droop, at, direction, roll, uv=None):
    """Adds one leaf to a bmesh: an oval blade, cupped, drooping, pointing along direction from at."""
    nl, nw = 8, 3
    d = Vector(direction).normalized()
    side = d.cross(Vector((0, 0, 1)))
    if side.length < 1e-3:
        side = Vector((1, 0, 0))
    side.normalize()
    up = side.cross(d).normalized()
    rot = Matrix.Rotation(roll, 3, d)
    side, up = rot @ side, rot @ up
    rows = []
    for i in range(nl + 1):
        t = i / nl
        half = width / 2 * (math.sin(math.pi * min(1.0, t ** 0.85)) ** 0.9) * (1.0 - 0.25 * t) + 0.001
        row = []
        for j in range(-nw, nw + 1):
            s = j / nw
            p = Vector(at) + d * (t * length) + side * (s * half) + up * (curl * s * s * half - droop * t * t * length)
            row.append(bm.verts.new(p))
        rows.append(row)
    faces = []
    for i in range(nl):
        for j in range(2 * nw):
            faces.append(bm.faces.new((rows[i][j], rows[i][j + 1], rows[i + 1][j + 1], rows[i + 1][j])))
    if uv is not None:
        for f in faces:
            for loop in f.loops:
                v = loop.vert
                loop[uv].uv = ((v.co - Vector(at)).dot(d) / length, 0.5 + (v.co - Vector(at)).dot(side) / max(width, 1e-3))
    return faces


def plant(col, kind="fig", h=1.6, pot_color="#E3DDD3", seed=3, pot_h=None):
    rnd = random.Random(seed)
    out = []
    pot_r = 0.22 if h > 1.2 else (0.07 if h < 0.5 else 0.15)
    ph = pot_h or (0.42 if h > 1.2 else 0.24)
    out.append(kit.lathe("pot", [(0.0, 0.0), (pot_r * 0.82, 0.0), (pot_r, ph * 0.12), (pot_r, ph), (pot_r - 0.015, ph), (pot_r - 0.015, ph * 0.9), (0.0, ph * 0.9)], col, M.ceramic(pot_color, 0.6), 64))
    out.append(kit.cylinder("soil", Vector((0, 0, ph * 0.88)), pot_r - 0.02, 0.02, col, M.matte("#3B2E25", 0.95), 48))
    stem_mat = M.matte("#5B4A36", 0.7)
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")
    green = {"fig": "#34502A", "olive": "#6E7B5A", "snake": "#3F5C34", "grass": "#7A8455"}[kind]
    if kind == "fig":
        stems = rnd.randint(3, 4)
        for k in range(stems):
            base = Vector((rnd.uniform(-0.05, 0.05), rnd.uniform(-0.05, 0.05), ph * 0.9))
            top = Vector((rnd.uniform(-0.25, 0.25), rnd.uniform(-0.25, 0.25), h * rnd.uniform(0.75, 1.0)))
            bow = Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), 0)).normalized() * (top - base).length * rnd.uniform(0.05, 0.08)
            pts = [base.lerp(top, t) + bow * math.sin(math.pi * t) for t in (0, 0.33, 0.66, 1)]
            out.append(tube("stem", pts, lambda t: 0.018 - 0.01 * t, col, stem_mat, 8))
            for i in range(rnd.randint(15, 20) if h > 0.8 else rnd.randint(5, 8)):  # a desk plant has a few
                t = rnd.uniform(0.3, 1.0)
                p = base.lerp(top, t) + bow * math.sin(math.pi * t)
                a = rnd.uniform(0, 2 * math.pi)
                dirv = Vector((math.cos(a), math.sin(a), rnd.uniform(0.2, 0.9)))
                s = rnd.uniform(0.75, 1.25) * (0.8 + 0.25 * t)  # younger leaves at the top are smaller
                leaf_geometry(bm, 0.28 * s, 0.17 * s * rnd.uniform(0.9, 1.1), rnd.uniform(0.2, 0.5), rnd.uniform(0.06, 0.2), p, dirv, rnd.uniform(-0.5, 0.5), uv)
    elif kind == "olive":
        trunk_top = Vector((0.03, -0.02, h * 0.55))
        out.append(tube("trunk", [(0, 0, ph * 0.9), (0.02, 0.01, h * 0.3), trunk_top], lambda t: 0.035 - 0.018 * t, col, stem_mat, 10))
        for b in range(5):
            a = rnd.uniform(0, 2 * math.pi)
            end = trunk_top + Vector((math.cos(a) * rnd.uniform(0.2, 0.4), math.sin(a) * rnd.uniform(0.2, 0.4), rnd.uniform(0.25, h * 0.45)))
            out.append(tube("branch", [trunk_top, trunk_top.lerp(end, 0.5) + Vector((0, 0, 0.05)), end], lambda t: 0.015 - 0.009 * t, col, stem_mat, 8))
            for i in range(240):
                c = end + Vector((rnd.gauss(0, 0.16), rnd.gauss(0, 0.16), rnd.gauss(0, 0.12)))
                aa = rnd.uniform(0, 2 * math.pi)
                leaf_geometry(bm, rnd.uniform(0.055, 0.085), 0.016, 0.2, 0.05, c, (math.cos(aa), math.sin(aa), rnd.uniform(-0.5, 0.6)), rnd.uniform(0, 3), uv)
    elif kind == "snake":
        for i in range(rnd.randint(9, 13)):
            a = rnd.uniform(0, 2 * math.pi)
            base = Vector((math.cos(a) * rnd.uniform(0, 0.08), math.sin(a) * rnd.uniform(0, 0.08), ph * 0.9))
            tilt = rnd.uniform(0.0, 0.25)
            leaf_geometry(bm, h * rnd.uniform(0.6, 1.0) - ph, rnd.uniform(0.05, 0.075), 0.25, 0.0, base,
                          (math.cos(a) * tilt, math.sin(a) * tilt, 1.0), rnd.uniform(0, math.pi), uv)
    else:
        for i in range(60):
            a = rnd.uniform(0, 2 * math.pi)
            base = Vector((rnd.uniform(-0.04, 0.04), rnd.uniform(-0.04, 0.04), ph * 0.9))
            tilt = rnd.uniform(0.2, 0.9)
            leaf_geometry(bm, h * rnd.uniform(0.5, 1.0), 0.012, 0.3, 0.25, base, (math.cos(a) * tilt, math.sin(a) * tilt, 1.0), 0, uv)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    leaves = kit.obj_from_bmesh("leaves", bm, col, M.leaf(green), smooth=True)
    sol = leaves.modifiers.new("thick", "SOLIDIFY")
    sol.thickness = 0.0015
    out.append(leaves)
    return out


# ---------- walls and things on them ----------

def art(col, w=0.9, h=1.2, palette=("#E9E1D3", "#C46A3C", "#2E3B35", "#D9B98C"), seed=1.0, kind="blobs", frame="oak", tone="#CDAA80"):
    """A framed abstract painting, its back on y=0, hanging forward towards -Y."""
    fmat = M.oak(tone, 30.0, "Z") if frame == "oak" else M.matte("#1C1C1C", 0.4) if frame == "black" else M.matte("#F2F0EB", 0.4)
    f = 0.025
    out = [rbox("canvas", (-w / 2 + f, -0.03, -h / 2 + f), (w / 2 - f, 0, h / 2 - f), col, M.art(palette, seed, kind), 0.002)]
    out += [rbox("frame", (-w / 2, -0.04, h / 2 - f), (w / 2, 0, h / 2), col, fmat, 0.002),
            rbox("frame", (-w / 2, -0.04, -h / 2), (w / 2, 0, -h / 2 + f), col, fmat, 0.002),
            rbox("frame", (-w / 2, -0.04, -h / 2), (-w / 2 + f, 0, h / 2), col, fmat, 0.002),
            rbox("frame", (w / 2 - f, -0.04, -h / 2), (w / 2, 0, h / 2), col, fmat, 0.002)]
    return out


def slat_wall(col, w=2.4, h=3.0, slat=0.035, gap=0.015, depth=0.03, tone="#C9A57B", vary=0.0, seed=5, grain=0.0):
    """Vertical oak slats on a dark backing, against a wall at y=0, facing -Y. vary > 0: each slat cut from a
    different board, its tone up to that much lighter or darker."""
    kw = {"grain": grain} if grain else {}
    woods = [M.oak(tone, 34.0, "Z", **kw)] if vary <= 0 else [M.oak(M._shade(tone, v), 34.0, "Z", **kw) for v in (-vary, -vary / 2, 0.0, vary / 2, vary)]
    rnd = random.Random(seed)
    out = [kit.box("backing", (-w / 2, -0.004, 0), (w / 2, 0, h), col, M.matte("#2A2622", 0.8))]
    n = int(w / (slat + gap))
    x0 = -w / 2 + (w - (n * slat + (n - 1) * gap)) / 2
    for i in range(n):
        x = x0 + i * (slat + gap)
        out.append(rbox("slat", (x, -0.004 - depth, 0), (x + slat, -0.004, h), col, rnd.choice(woods) if vary > 0 else woods[0], 0.003))
    return out


def letters(col, text="FERNHOLLOW", size=0.16, color="#B08D57", depth=0.012):
    """Raised metal letters, standing on y=0 and facing -Y."""
    cu = bpy.data.curves.new("letters", "FONT")
    cu.body = text
    cu.size = size
    cu.extrude = depth / 2
    cu.align_x = "CENTER"
    cu.space_character = 1.25
    ob = bpy.data.objects.new("letters", cu)
    col.objects.link(ob)
    ob.rotation_euler = (math.pi / 2, 0, 0)
    ob.location = (0, -depth / 2 - 0.004, 0)
    cu.materials.append(M.steel(color, 0.32))
    return [ob]


def reception_desk(col, w=2.2, d=0.7, h=1.05, tone="#C9A57B"):
    out = slat_box(col, w, d, h - 0.03, tone)
    out.append(rbox("top", (-w / 2 - 0.02, -d / 2 - 0.02, h - 0.03), (w / 2 + 0.02, d / 2 + 0.02, h), col, M.stone("#ECE5DA", "#C9BBA6", 0.3, 1.5), 0.004))
    out.append(rbox("worktop", (-w / 2 + 0.05, -d / 2 + 0.1, 0.72), (w / 2 - 0.05, d / 2 - 0.02, 0.75), col, M.matte("#F0EEE9", 0.35), 0.004))
    return out


def reception_counter(col, w=3.0, d=0.85, h=1.05, ledge=0.37, tone="#C9A57B", low=0.0, low_h=0.76):
    """A reception counter facing -Y: a fluted oak front up to a solid oak ledge for visitors, and behind it, for
    the receptionist, an oak worktop at desk height with room for their knees, between oak end panels. The last
    `low` metres at the +x end are a lowered section at low_h, one oak top right through, open beneath for a
    seated visitor's knees."""
    wood = M.oak(tone, 34.0, "Z", grain=0.08)
    dark = M.matte("#2A2622", 0.8)
    y0, y1 = -d / 2, d / 2
    xl = w / 2 - low  # where the high part ends
    s, g = 0.03, 0.006  # flutes: rounded nearly to a half round, the way a fluted panel is milled
    pl = 0.08  # a dark plinth 80 mm high, set 60 mm back, so a shadow line runs along the floor
    lt = 0.04  # the stone ledge's thickness
    out = [kit.box("front core", (-w / 2 + 0.04, y0 + 0.022, pl), (xl, y0 + 0.06, h - lt), col, dark),
           kit.box("plinth", (-w / 2 + 0.04, y0 + 0.06, 0.0), (xl, y0 + 0.12, pl), col, dark)]
    knee = 0.48  # under the lowered end, 0.7 m clear and 0.48 m deep for a visitor's knees, then a modesty panel
    if low > 0:  # the modesty panel fluted like the front, set back behind the knee space
        out.append(kit.box("modesty core", (xl + 0.02, y0 + knee + 0.012, 0.0), (w / 2 - 0.04, y0 + knee + 0.03, low_h - 0.03), col, dark))
        fx = xl + 0.03
        while fx + s <= w / 2 - 0.05:
            out.append(rbox("flute", (fx, y0 + knee, 0.0), (fx + s, y0 + knee + 0.024, low_h - 0.03), col, wood, 0.011))
            fx += s + g
    n = int((w - 0.1) / (s + g))
    x = -(n * s + (n - 1) * g) / 2
    for i in range(n):
        top = h - lt if x + s <= xl - 0.02 else low_h - 0.03
        if xl - 0.02 < x + s:  # the divider panel, then the lowered end's open knee space
            x += s + g
            continue
        out.append(rbox("flute", (x, y0, pl), (x + s, y0 + 0.024, top), col, wood, 0.011))
        x += s + g
    ends = [(-w / 2, -w / 2 + 0.04, h)] + ([(xl - 0.02, xl + 0.02, h)] if low > 0 else []) + [(w / 2 - 0.04, w / 2, h if low <= 0 else low_h)]
    for xa, xb, top in ends:  # end panels: up to the ledge at the front, desk height behind it
        out.append(rbox("end", (xa, y0, 0.0), (xb, y0 + ledge, top - (lt if top > low_h else 0.03)), col, wood, 0.004))
        out.append(rbox("end", (xa, y0 + ledge - 0.01, 0.0), (xb, y1, min(top, 0.75) - (0.03 if top <= low_h else 0.0)), col, wood, 0.004))
    if low > 0:  # the lowered end's outer side fluted too, so it reads as part of the counter
        fy = y0 + 0.01
        while fy + s <= y1 - 0.01:
            out.append(rbox("flute", (w / 2, fy, 0.0), (w / 2 + 0.024, fy + s, low_h - 0.03), col, wood, 0.011))
            fy += s + g
    out.append(rbox("ledge", (-w / 2 - 0.03, y0 - 0.03, h - lt), (xl + 0.015, y0 + ledge, h), col, M.oak(tone, 30.0, "X", grain=0.08), 0.006))  # solid oak, 40 mm thick
    out.append(kit.box("upstand", (-w / 2 + 0.04, y0 + 0.06, 0.75), (xl - 0.02, y0 + ledge, h - lt), col, dark))
    out.append(rbox("worktop", (-w / 2 + 0.04, y0 + 0.06, 0.72), (xl - 0.02, y1, 0.75), col, M.oak(tone, 30.0, "X", grain=0.08), 0.004))
    if low > 0:
        out.append(rbox("low top", (xl + 0.02, y0 - 0.03, low_h - 0.03), (w / 2 + 0.015, y1, low_h), col, M.oak(tone, 30.0, "X", grain=0.08), 0.004))
    return out


def pendant_ring(col, radius=0.8, z=2.6, ceiling=3.5, tube_r=0.022, glow=6.0):
    """A ring of light on three fine cables: a thin bronze hoop with a warm diffuser along its underside."""
    out = []
    pts = [(radius * math.cos(a), radius * math.sin(a), z) for a in [i * 2 * math.pi / 96 for i in range(97)]]
    out.append(tube("ring", pts, tube_r, col, M.steel("#8A6A45", 0.35), 12))
    out.append(tube("diffuser", [(p[0] * 0.985, p[1] * 0.985, z - tube_r * 0.6) for p in pts], tube_r * 0.62, col, M.glow("#FFE2BD", glow), 10))
    for k in range(3):
        a = k * 2 * math.pi / 3 + 0.4
        out.append(tube("cable", [(radius * math.cos(a), radius * math.sin(a), z), (radius * math.cos(a), radius * math.sin(a), ceiling)], 0.0012, col, M.matte("#1C1C1C", 0.4), 6))
    return out


def site_screen(col, w=0.95, h=0.56, seed=0, on=True):
    """A slim screen on the wall showing one of the company's websites, facing -Y from y=0; dark glass when off."""
    black = M.matte("#141414", 0.3)
    glass = M.screen_site(seed) if on else M.matte("#0B0C0D", 0.05, coat=0.8)
    site = rbox("site", (-w / 2, -0.026, 0.0), (w / 2, -0.02, h), col, glass, 0.002)
    uv = site.data.attributes.new("screen_uv", "FLOAT_VECTOR", "POINT")  # 0 to 1 across the page, kept when the room is joined for the viewer
    for i, v in enumerate(site.data.vertices):
        uv.data[i].vector = ((v.co.x + w / 2) / w, 0.0, v.co.z / h)
    return [rbox("bezel", (-w / 2 - 0.008, -0.022, -0.008), (w / 2 + 0.008, 0.0, h + 0.008), col, black, 0.003), site]


def slat_box(col, w, d, h, tone):
    wood = M.oak(tone, 34.0, "Z")
    out = [kit.box("core", (-w / 2 + 0.03, -d / 2 + 0.03, 0), (w / 2 - 0.03, d / 2, h), col, M.matte("#2A2622", 0.8))]
    s, g = 0.035, 0.012
    for face in ("front", "left", "right"):
        span = w if face == "front" else d - 0.03
        n = int(span / (s + g))
        for i in range(n):
            u = -span / 2 + i * (s + g) + g
            if face == "front":
                out.append(rbox("slat", (u, -d / 2, 0), (u + s, -d / 2 + 0.03, h), col, wood, 0.003))
            else:
                sx = -1 if face == "left" else 1
                out.append(rbox("slat", (sx * w / 2 - (0.03 if sx > 0 else 0), u + 0.015, 0), (sx * w / 2 + (0 if sx > 0 else 0.03), u + 0.015 + s, h), col, wood, 0.003))
    return out


def kitchen_run(col, length=3.0, depth=0.62, tone="#C9A57B", top="#262624", tall=0.0, tall_at_start=False):
    """Base cabinets in oak with shadow-gap pulls, a dark stone worktop, a sink and a tap; back against y=0."""
    wood = M.oak(tone, 26.0, "Z")
    black = M.matte("#1C1C1C", 0.4)
    stone_ = M.stone(top, "#3A3A37", 0.28, 3.0)
    out = [kit.box("plinth", (0, -depth + 0.06, 0), (length, -0.02, 0.1), col, black)]
    n = max(2, round(length / 0.6))
    for i in range(n):
        x0 = length * i / n + 0.002
        x1 = length * (i + 1) / n - 0.002
        out.append(rbox("front", (x0, -depth, 0.1), (x1, -0.03, 0.86), col, wood, 0.003))
        out.append(kit.box("pull gap", (x0 + 0.01, -depth - 0.001, 0.82), (x1 - 0.01, -depth + 0.012, 0.86), col, black))
    out.append(rbox("worktop", (-0.005, -depth - 0.02, 0.86), (length + 0.005, 0.0, 0.9), col, stone_, 0.003))
    out.append(rbox("upstand", (-0.005, -0.015, 0.9), (length + 0.005, 0.0, 1.0), col, stone_, 0.002))
    sx = length * 0.62
    steel_ = M.steel("#C9CCCF", 0.25)
    out.append(kit.box("sink", (sx - 0.25, -depth + 0.12, 0.9), (sx + 0.25, -0.12, 0.902), col, steel_))
    out.append(tube("tap", [(sx, -0.07, 0.9), (sx, -0.07, 1.2), (sx, -0.12, 1.26), (sx, -0.22, 1.24), (sx, -0.24, 1.17)], 0.012, col, steel_, 12))
    # a coffee machine and a kettle
    cm = length * 0.2
    out += [rbox("coffee", (cm - 0.16, -0.42, 0.9), (cm + 0.16, -0.06, 1.3), col, M.steel("#B9BCBF", 0.35), 0.02),
            rbox("coffee top", (cm - 0.16, -0.42, 1.3), (cm + 0.16, -0.06, 1.33), col, black, 0.01),
            kit.cylinder("kettle", Vector((length * 0.38, -0.25, 0.99)), 0.08, 0.18, col, M.matte("#E7E2D8", 0.3), 48, bevel=0.02)]
    if tall > 0:
        x0 = -0.62 if tall_at_start else length
        out.append(rbox("tall unit", (x0, -depth, 0), (x0 + 0.62, 0.0, tall), col, wood, 0.003))
        out.append(kit.box("tall gap", (x0 + 0.309, -depth - 0.001, 0.1), (x0 + 0.311, -depth + 0.004, tall - 0.02), col, black))
    return out


def monitor(col, w=0.6, on=False):
    black = M.matte("#1C1C1C", 0.35)
    screen = M.screen_wallpaper() if on == "wallpaper" else M.screen_on() if on else M.matte("#0B0C0D", 0.05, coat=0.8)
    return [rbox("screen", (-w / 2, -0.012, 0.18), (w / 2, 0.012, 0.18 + w * 0.58), col, screen, 0.004),
            rbox("bezel", (-w / 2 - 0.012, 0.0, 0.168), (w / 2 + 0.012, 0.014, 0.192 + w * 0.58), col, black, 0.004),
            rbox("back", (-w / 2 + 0.01, 0.012, 0.2), (w / 2 - 0.01, 0.04, 0.16 + w * 0.56), col, black, 0.012),
            rbox("neck", (-0.025, 0.04, 0.0), (0.025, 0.06, 0.3), col, black, 0.006),
            rbox("foot", (-0.11, -0.08, 0.0), (0.11, 0.12, 0.008), col, black, 0.004)]


def laptop(col, open_=True):
    alu = M.steel("#C4C6C8", 0.3)
    if not open_:
        return [rbox("base", (-0.16, -0.11, 0.0), (0.16, 0.11, 0.009), col, alu, 0.003),
                rbox("lid", (-0.16, -0.11, 0.0095), (0.16, 0.11, 0.016), col, alu, 0.003),
                kit.box("seam", (-0.158, -0.111, 0.009), (0.158, -0.11, 0.0095), col, M.matte("#2A2B2D", 0.5))]
    return [rbox("base", (-0.16, -0.11, 0.0), (0.16, 0.11, 0.012), col, alu, 0.004),
            rbox("lid", (-0.16, 0.1, 0.01), (0.16, 0.112, 0.22), col, alu, 0.004)]


def tree(col, h=8.0, crown=3.0, seed=1):
    """A garden tree for the view out: a trunk, branches, and a crown of leaf clumps with gaps between them."""
    rnd = random.Random(seed)
    bark = M.matte("#4A4036", 0.9)
    top = Vector((0.05, 0.1, h * 0.55))
    out = [tube("trunk", [(0, 0, 0), (0.1, 0.05, h * 0.3), top], lambda t: 0.2 - 0.1 * t, col, bark, 10)]
    cc = Vector((0, 0, h - crown * 0.8))
    for b in range(7):
        a = rnd.uniform(0, 2 * math.pi)
        end = cc + Vector((math.cos(a) * crown * 0.6, math.sin(a) * crown * 0.6, rnd.uniform(-0.2, 0.7) * crown * 0.5))
        out.append(tube("branch", [top, top.lerp(end, 0.5) + Vector((0, 0, 0.3)), end], lambda t: 0.08 - 0.055 * t, col, bark, 8))
    bm = bmesh.new()
    shape = [(0.0, 0.0), (0.35, 0.3), (0.75, 0.32), (1.0, 0.0), (0.75, -0.32), (0.35, -0.3)]  # an oval leaf, tip at 1
    for k in range(int(170 * crown / 3)):
        while True:
            p = Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-1, 1)))
            if p.length <= 1:
                break
        c = cc + Vector((p.x * crown, p.y * crown, p.z * crown * 0.8))
        twig = Vector((rnd.gauss(0, 1), rnd.gauss(0, 1), rnd.gauss(0, 0.6) + 0.2)).normalized()
        for i in range(150):
            q = c + twig * rnd.uniform(-0.3, 0.3) + Vector((rnd.gauss(0, 0.12), rnd.gauss(0, 0.12), rnd.gauss(0, 0.1)))
            d = (twig * 0.4 + Vector((rnd.gauss(0, 1), rnd.gauss(0, 1), rnd.gauss(0, 1) - 0.4))).normalized()
            side = d.cross(Vector((0, 0, 1)))
            side = side.normalized() if side.length > 1e-3 else Vector((1, 0, 0))
            sz = rnd.uniform(0.09, 0.13)
            bm.faces.new([bm.verts.new(q + d * (u * sz) + side * (v * sz)) for u, v in shape])
    leaves = M.foliage(rnd.choice(["#4D6339", "#566B3C", "#45603A"]))
    out.append(kit.obj_from_bmesh("crown", bm, col, leaves))
    core = bmesh.new()  # the crown's shaded heart, so the gaps between clumps show leaves behind, not sky
    bmesh.ops.create_icosphere(core, subdivisions=4, radius=1.0)
    for v in core.verts:
        n = 1.0 + 0.12 * math.sin(v.co.x * 5.1 + seed) * math.sin(v.co.y * 4.3) * math.sin(v.co.z * 3.7 + seed)
        v.co = cc + Vector((v.co.x * crown * 0.72 * n, v.co.y * crown * 0.72 * n, v.co.z * crown * 0.58 * n))
    out.append(kit.obj_from_bmesh("crown core", core, col, leaves, smooth=True))
    return out


# ---------- things the rooms are for ----------

def goals_board(col, goals, w=1.5, h=0.95, tone="#C9A57B"):
    """The goals wall: an oak-framed linen board with a card per goal, its title written on it and a pinned flag,
    red while open and gold once reached. goals = [(title, "open" | "reached")]. Back on y=0, facing -Y, centred on z=0."""
    wood = M.oak(tone, 30.0, "X")
    linen = M.fabric("#E7E0D3", 0.6, 0.2, 0.25)
    card = M.matte("#F7F4EE", 0.75)
    ink = M.matte("#2B2A28", 0.6)
    red, gold = M.matte("#B4432E", 0.5), M.matte("#D4A72C", 0.6)
    pin = M.matte("#1C1C1C", 0.4)
    f = 0.03
    out = [rbox("linen", (-w / 2 + f, -0.02, -h / 2 + f), (w / 2 - f, 0, h / 2 - f), col, linen, 0.002),
           rbox("frame", (-w / 2, -0.035, h / 2 - f), (w / 2, 0, h / 2), col, wood, 0.002),
           rbox("frame", (-w / 2, -0.035, -h / 2), (w / 2, 0, -h / 2 + f), col, wood, 0.002),
           rbox("frame", (-w / 2, -0.035, -h / 2), (-w / 2 + f, 0, h / 2), col, wood, 0.002),
           rbox("frame", (w / 2 - f, -0.035, -h / 2), (w / 2, 0, h / 2), col, wood, 0.002)]
    n = len(goals)
    rnd = random.Random(3)
    for k, (title, state) in enumerate(goals):
        cx = -w / 2 + w * (k + 0.5) / n
        cw, ch = 0.36, 0.44
        cz = -0.08 + rnd.uniform(-0.02, 0.02)
        parts = [rbox("goal card", (-cw / 2, -0.024, -ch / 2), (cw / 2, -0.02, ch / 2), col, card, 0.001)]
        words, lines, line = title.split(), [], ""
        for wd in words:
            if len(line) + len(wd) + 1 > 13 and line:
                lines.append(line)
                line = wd
            else:
                line = (line + " " + wd).strip()
        lines.append(line)
        for body, size, z_top, mat in (("\n".join(lines), 0.04, ch / 2 - 0.075, ink),
                                       ("REACHED" if state == "reached" else "OPEN", 0.05, -ch / 2 + 0.05, red if state == "open" else gold)):
            cu = bpy.data.curves.new("goal title", "FONT")
            cu.body = body
            cu.size = size
            cu.space_line = 1.15
            cu.align_x = "LEFT"
            cu.materials.append(mat)
            txt = bpy.data.objects.new("goal title", cu)
            col.objects.link(txt)
            txt.rotation_euler = (math.pi / 2, 0, 0)
            txt.location = (-cw / 2 + 0.03, -0.0245, z_top)
            parts.append(txt)
        px = cw / 2 - 0.06
        parts += [tube("flag pin", [(px, -0.024, ch / 2 - 0.03), (px, -0.07, ch / 2 - 0.03)], 0.003, col, pin, 8),
                  tube("flag pole", [(px, -0.06, ch / 2 - 0.035), (px, -0.06, ch / 2 + 0.22)], 0.0028, col, pin, 8)]
        bm = bmesh.new()
        a_, b_, c_ = bm.verts.new((px, -0.06, ch / 2 + 0.22)), bm.verts.new((px, -0.06, ch / 2 + 0.1)), bm.verts.new((px + 0.17, -0.06, ch / 2 + 0.16))
        bm.faces.new((a_, b_, c_))
        flagob = kit.obj_from_bmesh("flag", bm, col, red if state == "open" else gold)
        flagob.modifiers.new("thick", "SOLIDIFY").thickness = 0.002
        parts.append(flagob)
        root = kit.place(parts, (cx, 0, cz), 0.0, "goal", col)
        root.rotation_euler = (0, rnd.uniform(-0.025, 0.025), 0)
        out.append(root)
    return out


def filing_cabinet(col, w=0.5, d=0.6, h=1.3, drawers=4, tone="#C6A47A", label="#B89B62", title=""):
    """An oak cabinet of drawers with black pulls and a brass label holder on each."""
    wood = M.oak(tone, 26.0, "Z")
    black = M.matte("#1C1C1C", 0.4)
    brass = M.steel(label, 0.38)
    card = M.matte("#F4F0E8", 0.8)
    out = [rbox("carcass", (-w / 2, -d / 2, 0.06), (w / 2, d / 2, h), col, wood, 0.005),
           kit.box("plinth", (-w / 2 + 0.03, -d / 2 + 0.04, 0), (w / 2 - 0.03, d / 2 - 0.03, 0.06), col, black)]
    dh = (h - 0.06) / drawers
    for i in range(drawers):
        z0 = 0.06 + i * dh
        out.append(rbox("drawer", (-w / 2 + 0.012, -d / 2 - 0.012, z0 + 0.006), (w / 2 - 0.012, -d / 2, z0 + dh - 0.006), col, wood, 0.003))
        out.append(rbox("cup pull", (-0.045, -d / 2 - 0.022, z0 + dh * 0.6), (0.045, -d / 2 - 0.012, z0 + dh * 0.6 + 0.03), col, brass, 0.006))
        out.append(rbox("label", (-0.03, -d / 2 - 0.016, z0 + dh * 0.32), (0.03, -d / 2 - 0.012, z0 + dh * 0.32 + 0.025), col, brass, 0.002))
        out.append(kit.box("label card", (-0.024, -d / 2 - 0.0165, z0 + dh * 0.32 + 0.004), (0.024, -d / 2 - 0.016, z0 + dh * 0.32 + 0.021), col, card))
        if title and i == drawers - 1:  # the top drawer's card says what the cabinet holds
            cu = bpy.data.curves.new("label text", "FONT")
            cu.body = title.upper()
            cu.size = 0.0055 if len(title) > 9 else 0.0075
            cu.align_x = "CENTER"
            cu.align_y = "CENTER"
            cu.materials.append(M.matte("#2B2A28", 0.6))
            txt = bpy.data.objects.new("label text", cu)
            col.objects.link(txt)
            txt.rotation_euler = (math.pi / 2, 0, 0)
            txt.location = (0, -d / 2 - 0.0167, z0 + dh * 0.32 + 0.0125)
            out.append(txt)
    return out


def crate(col, w=0.6, d=0.4, h=0.32, tone="#D4B892", full=True, seed=1):
    """A slatted wooden crate (a copy of the code with unsaved changes), with papers in it."""
    wood = M.oak(tone, 34.0, "X")
    t = 0.018
    out = [rbox("crate floor", (-w / 2, -d / 2, 0), (w / 2, d / 2, t), col, wood, 0.002)]
    for k in range(3):
        z0 = t + k * (h - t) / 3 + 0.008
        z1 = t + (k + 1) * (h - t) / 3 - 0.008
        out += [rbox("slat", (-w / 2, -d / 2, z0), (w / 2, -d / 2 + t, z1), col, wood, 0.002),
                rbox("slat", (-w / 2, d / 2 - t, z0), (w / 2, d / 2, z1), col, wood, 0.002),
                rbox("slat", (-w / 2, -d / 2, z0), (-w / 2 + t, d / 2, z1), col, wood, 0.002),
                rbox("slat", (w / 2 - t, -d / 2, z0), (w / 2, d / 2, z1), col, wood, 0.002)]
    for sx in (-1, 1):
        for sy in (-1, 1):
            out.append(rbox("post", (sx * w / 2 - (t if sx > 0 else 0), sy * d / 2 - (t if sy > 0 else 0), 0), (sx * w / 2 + (0 if sx > 0 else t), sy * d / 2 + (0 if sy > 0 else t), h), col, wood, 0.002))
    if full:
        rnd = random.Random(seed)
        paper = M.matte("#F2EEE6", 0.85)
        x = -w / 2 + 0.04
        while x < w / 2 - 0.06:
            th = rnd.uniform(0.01, 0.03)
            out.append(rbox("folder", (x, -d / 2 + 0.04, t), (x + th, d / 2 - 0.04, h + rnd.uniform(0.03, 0.06)), col, M.matte(rnd.choice(["#F2EEE6", "#D9CBB5", "#C9B79C", "#2F3B36"]), 0.8) if rnd.random() < 0.6 else paper, 0.002))
            x += th + 0.004
    return out



# ---------- small things that make a room look used ----------

def keyboard(col):
    return [rbox("keyboard", (-0.22, -0.065, 0.0), (0.22, 0.065, 0.012), col, M.matte("#E9E7E2", 0.4), 0.004)]


def mouse(col):
    return [rbox("mouse", (-0.03, -0.055, 0.0), (0.03, 0.055, 0.02), col, M.matte("#E9E7E2", 0.35), 0.012, soft=True)]


def mug(col, color="#E9E2D6"):
    return [kit.lathe("mug", [(0.0, 0.0), (0.04, 0.0), (0.042, 0.005), (0.042, 0.095), (0.037, 0.095), (0.036, 0.01), (0.0, 0.01)], col, M.ceramic(color, 0.3), 40)]


def notebook(col, color="#2F3B36", w=0.15, d=0.21, open_=False):
    if not open_:
        return [rbox("notebook", (-w / 2, -d / 2, 0.0), (w / 2, d / 2, 0.012), col, M.matte(color, 0.7), 0.002)]
    page = M.matte("#F4F0E8", 0.85)
    return [rbox("cover", (-w - 0.005, -d / 2 - 0.005, 0.0), (w + 0.005, d / 2 + 0.005, 0.003), col, M.matte(color, 0.7), 0.001),
            rbox("pages", (-w, -d / 2, 0.003), (-0.004, d / 2, 0.014), col, page, 0.004),
            rbox("pages", (0.004, -d / 2, 0.003), (w, d / 2, 0.012), col, page, 0.004)]


def pen(col):
    return [tube("pen", [(-0.07, 0, 0.005), (0.07, 0, 0.005)], 0.005, col, M.matte("#1C1C1C", 0.3), 10)]


def sheets(col, n=3, seed=1):
    rnd = random.Random(seed)
    out = []
    for k in range(n):
        sh = kit.box("sheet", (-0.105, -0.1485, 0.0), (0.105, 0.1485, 0.0008), col, M.matte("#F6F3EE", 0.85))
        root = kit.place([sh], (rnd.uniform(-0.05, 0.05), rnd.uniform(-0.05, 0.05), k * 0.0009), rnd.uniform(-0.4, 0.4), "sheet", col)
        out.append(root)
    return out


def carafe(col):
    return [kit.lathe("carafe", [(0.0, 0.0), (0.06, 0.0), (0.065, 0.01), (0.065, 0.16), (0.03, 0.22), (0.028, 0.26), (0.026, 0.26), (0.026, 0.22), (0.06, 0.16), (0.06, 0.012), (0.0, 0.012)], col, M.glass(), 48)]


def tumbler(col):
    return [kit.lathe("tumbler", [(0.0, 0.0), (0.035, 0.0), (0.038, 0.09), (0.035, 0.09), (0.032, 0.008), (0.0, 0.008)], col, M.glass(), 40)]


def roller_blind(col, w, drop=0.35, color="#E6E0D4"):
    """A roller blind's cassette and the cloth let down a little, against a wall at y=0, facing -Y; top at z=0."""
    cloth = M.matte(color, 0.85)
    return [rbox("blind cassette", (-w / 2, -0.12, -0.12), (w / 2, 0.0, 0.0), col, M.matte("#EDEBE6", 0.5), 0.006),
            kit.box("blind", (-w / 2 + 0.02, -0.07, -0.12 - drop), (w / 2 - 0.02, -0.066, -0.12), col, cloth),
            rbox("blind rail", (-w / 2 + 0.02, -0.076, -0.135 - drop), (w / 2 - 0.02, -0.06, -0.12 - drop), col, M.matte("#D9D8D3", 0.4), 0.003)]


def downlight(col, lit=False):
    """A recessed downlight, 90 mm across, in the ceiling at z=0; lit=True switches it on."""
    face = M.glow("#FFE6C8", 220.0) if lit else M.matte("#F7F5F0", 0.2)
    return [kit.cylinder("downlight rim", Vector((0, 0, -0.002)), 0.045, 0.004, col, M.matte("#F2F1EE", 0.35), 32),
            kit.cylinder("downlight", Vector((0, 0, -0.0045)), 0.034, 0.001, col, face, 32)]


def sprinkler(col):
    return [kit.cylinder("sprinkler", Vector((0, 0, -0.012)), 0.012, 0.024, col, M.steel("#D9D9D6", 0.3), 16),
            kit.cylinder("sprinkler plate", Vector((0, 0, -0.026)), 0.02, 0.003, col, M.steel("#D9D9D6", 0.3), 16)]



def task_lamp(col, color="#1C1C1C"):
    """A desk lamp: a weighted foot, a jointed arm and a small shade, on."""
    m = M.matte(color, 0.35)
    return [kit.cylinder("lamp foot", Vector((0, 0, 0.01)), 0.07, 0.02, col, m, 32, bevel=0.004),
            tube("lamp arm", [(0, 0, 0.02), (0.02, 0.0, 0.3), (0.2, 0.0, 0.42)], 0.007, col, m, 8),
            kit.lathe("lamp shade", [(0.0, 0.47), (0.03, 0.47), (0.06, 0.4), (0.055, 0.395), (0.0, 0.44)], col, m, 32, (0.2, 0.0, -0.02)),
            kit.cylinder("lamp bulb", Vector((0.2, 0.0, 0.385)), 0.025, 0.004, col, M.glow("#FFE2B8", 40.0), 24)]


def building(col, lo, hi, h, wall, bay, storey, gz=0.0):
    """A neighbour's block: the walls, with every window given a deep surround: a sill 50 mm proud, a head and
    jambs standing 0.2 m out, so the facade has depth and shadow. Windows sit where the facade material puts them."""
    out = [kit.box("block", (lo[0], lo[1], gz), (hi[0], hi[1], gz + h), col, M.facade(wall, bay=bay, storey=storey))]
    bm = bmesh.new()
    d = 0.2

    def add(a, b):
        bmesh.ops.create_cube(bm, size=1.0)
        new = bm.verts[-8:]
        size = Vector(b) - Vector(a)
        mid = (Vector(a) + Vector(b)) / 2
        bmesh.ops.transform(bm, matrix=Matrix.Translation(mid) @ Matrix.Diagonal((*size, 1)), verts=new)

    faces = [("y", lo[1], -1, lo[0], hi[0]), ("y", hi[1], 1, lo[0], hi[0]), ("x", lo[0], -1, lo[1], hi[1]), ("x", hi[0], 1, lo[1], hi[1])]
    for axis, at, out_sign, a0, a1 in faces:
        for f in range(math.floor(gz / storey), math.ceil((gz + h) / storey) + 1):
            z0, z1 = (f + 0.3) * storey, (f + 0.86) * storey  # where the facade material draws the windows
            if z0 < gz + 0.5 or z1 > gz + h - 0.2:
                continue
            k0 = math.ceil((a0 + at) / bay)
            k1 = math.floor((a1 + at) / bay)
            for k in range(k0 - 1, k1 + 1):
                u0, u1 = (k + 0.2) * bay - at, (k + 0.8) * bay - at
                if u0 < a0 + 0.3 or u1 > a1 - 0.3:
                    continue
                p0, p1 = (at, at + out_sign * d) if out_sign > 0 else (at + out_sign * d, at)
                s0, s1 = (at, at + out_sign * 0.05) if out_sign > 0 else (at - 0.05, at)
                if axis == "y":
                    add((u0 - 0.06, s0, z0 - 0.05), (u1 + 0.06, s1, z0))
                    add((u0 - 0.06, p0, z1), (u1 + 0.06, p1, z1 + 0.06))
                    add((u0 - 0.06, p0, z0), (u0, p1, z1))
                    add((u1, p0, z0), (u1 + 0.06, p1, z1))
                else:
                    add((s0, u0 - 0.06, z0 - 0.05), (s1, u1 + 0.06, z0))
                    add((p0, u0 - 0.06, z1), (p1, u1 + 0.06, z1 + 0.06))
                    add((p0, u0 - 0.06, z0), (p1, u0, z1))
                    add((p0, u1, z0), (p1, u1 + 0.06, z1))
    out.append(kit.obj_from_bmesh("window surrounds", bm, col, M.outdoor("#E4E2DD", 0.6)))
    return out


# ---------- the basement: machines, benches and stores ----------

def server_rack(col, h=2.0, w=0.6, d=1.0, lit=False, seed=1):
    """A steel rack cabinet with a perforated front door left open, filled the way a working rack is: servers of
    one, two and four units, a patch panel and a switch near the top, blanking plates in the gaps; status lights
    on each server (lit=True: glowing, for the photographs; the live building lights its own), cable bundles at
    the back."""
    rnd = random.Random(seed)
    # dark greys, not black, so the fronts, handles and drive bays still read in a dim room
    frame = M.matte("#34373C", 0.42, 0.35)
    face = M.matte("#4A4E55", 0.35, 0.45)
    mesh = M.matte("#2B2E33", 0.5, 0.3)
    blank = M.matte("#303338", 0.55, 0.2)
    U = 0.0445
    out = [rbox("rack top", (-w / 2, -d / 2, h - 0.04), (w / 2, d / 2, h), col, frame, 0.004),
           rbox("rack plinth", (-w / 2 + 0.02, -d / 2 + 0.02, 0), (w / 2 - 0.02, d / 2 - 0.02, 0.08), col, frame, 0.004),
           kit.box("rack back", (-w / 2, d / 2 - 0.015, 0.08), (w / 2, d / 2, h - 0.04), col, mesh)]
    for sx in (-1, 1):
        out.append(rbox("rack side", (sx * w / 2 - (0.015 if sx > 0 else 0), -d / 2, 0.08), (sx * w / 2 + (0.0 if sx > 0 else 0.015), d / 2, h - 0.04), col, frame, 0.003))
        out.append(kit.box("rail", (sx * (w / 2 - 0.06) - 0.008, -d / 2 + 0.04, 0.1), (sx * (w / 2 - 0.06) + 0.008, -d / 2 + 0.06, h - 0.06), col, M.steel("#9DA2A8", 0.4)))
    z = 0.1
    top_z = h - 0.08
    k = 0
    while z + U < top_z:
        left = (top_z - z) / U
        if left < 5 and k >= 0:
            kind = "patch" if left >= 1 and k % 2 == 0 else "blank"
        else:
            kind = rnd.choices(["server", "blank"], [0.78, 0.22])[0]
        n = 1 if kind in ("patch", "blank") else rnd.choice([1, 1, 2, 2, 2, 4])
        n = min(n, int(left))
        if n < 1:
            break
        top = z + n * U
        if kind == "blank":
            out.append(kit.box("blanking plate", (-w / 2 + 0.045, -d / 2 + 0.03, z + 0.001), (w / 2 - 0.045, -d / 2 + 0.034, top - 0.001), col, blank))
        elif kind == "patch":
            out.append(rbox("patch panel", (-w / 2 + 0.05, -d / 2 + 0.03, z + 0.003), (w / 2 - 0.05, -d / 2 + 0.12, top - 0.003), col, face, 0.002))
            for i in range(12):
                x = -w / 2 + 0.09 + i * (w - 0.18) / 11
                out.append(kit.box("port", (x - 0.007, -d / 2 + 0.026, z + 0.014), (x + 0.007, -d / 2 + 0.031, z + 0.03), col, M.matte("#0B0C0D", 0.5)))
                out.append(tube("patch lead", [(x, -d / 2 + 0.02, z + 0.022), (x, -d / 2 - 0.03, z + 0.01), (w / 2 - 0.03, -d / 2 - 0.04, z - 0.02)], 0.003, col, M.matte(["#1A3A6B", "#B8B03A", "#D9D4C8"][i % 3], 0.5), 6))
        else:
            out.append(rbox("server", (-w / 2 + 0.05, -d / 2 + 0.035, z), (w / 2 - 0.05, d / 2 - 0.1, top - 0.003), col, face, 0.003))
            out.append(kit.box("server face", (-w / 2 + 0.045, -d / 2 + 0.03, z + 0.004), (w / 2 - 0.045, -d / 2 + 0.036, top - 0.006), col, mesh))
            for i in range(3):
                colr = "#7DFFB0" if i < 2 or rnd.random() < 0.5 else "#FFB347"
                mat = M.glow(colr, 6.0) if lit else M.matte("#3A3D42", 0.3)
                x = w / 2 - 0.09 - i * 0.022
                out.append(kit.box("status light", (x - 0.005, -d / 2 + 0.026, z + 0.012), (x + 0.005, -d / 2 + 0.03, z + 0.02), col, mat))
            out.append(rbox("handle", (-w / 2 + 0.065, -d / 2 + 0.015, z + 0.006), (-w / 2 + 0.08, -d / 2 + 0.03, top - 0.01), col, M.steel("#B8BCC1", 0.3), 0.003))
            if n >= 2:  # drive bays across the front
                for i in range(6):
                    x = -w / 2 + 0.12 + i * 0.065
                    out.append(kit.box("drive", (x, -d / 2 + 0.028, z + 0.01), (x + 0.055, -d / 2 + 0.031, top - 0.012), col, M.matte("#30343A", 0.4, 0.4)))
        z = top
        k += 1
    # the front door, open about 100 degrees on its left hinge
    door_w = w - 0.01
    hinge = Vector((-w / 2, -d / 2 - 0.01, 0))
    door = kit.box("rack door", (0, -0.008, 0.09), (door_w, 0.008, h - 0.05), col, mesh)
    door.matrix_world = Matrix.Translation(hinge) @ Matrix.Rotation(-math.radians(100), 4, "Z")  # swung out towards the room
    out.append(door)
    # cable bundles dropping in at the back
    for k in range(3):
        x = -w / 2 + 0.12 + k * 0.17
        out.append(tube("cables", [(x, d / 2 - 0.06, h - 0.1), (x + 0.01, d / 2 - 0.08, h * 0.6), (x - 0.01, d / 2 - 0.07, 0.3)], 0.018, col, M.matte(["#1A3A6B", "#202226", "#B8B03A"][k], 0.5), 10, cap=True))
    return out


def workbench(col, w=1.8, d=0.75, h=0.9, tone="#B48A5E"):
    """A steel-framed bench with a thick beech top, a shelf under it and a pegboard rail behind."""
    steel = M.matte("#3C4148", 0.4, 0.5)
    top = M.oak(tone, 22.0, "X")
    out = [rbox("bench top", (-w / 2, -d / 2, h - 0.04), (w / 2, d / 2, h), col, top, 0.006),
           kit.box("bench shelf", (-w / 2 + 0.05, -d / 2 + 0.05, 0.16), (w / 2 - 0.05, d / 2 - 0.05, 0.18), col, steel)]
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = sx * (w / 2 - 0.04), sy * (d / 2 - 0.04)
            out.append(rbox("bench leg", (x - 0.025, y - 0.025, 0), (x + 0.025, y + 0.025, h - 0.04), col, steel, 0.003))
        out.append(rbox("bench rail", (sx * (w / 2 - 0.04) - 0.02, -d / 2 + 0.04, 0.16), (sx * (w / 2 - 0.04) + 0.02, d / 2 - 0.04, 0.2), col, steel, 0.003))
    return out


def wire_shelving(col, w=1.2, d=0.45, h=1.8, levels=5, seed=3):
    """Chrome wire shelving with archive boxes, spare cables and a few parts on it."""
    rnd = random.Random(seed)
    chrome = M.steel("#C9CCD0", 0.25)
    out = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            out.append(kit.cylinder("post", Vector((sx * (w / 2 - 0.015), sy * (d / 2 - 0.015), h / 2)), 0.012, h, col, chrome, 16))
    for j in range(levels):
        z = 0.12 + j * (h - 0.16) / (levels - 1)
        out.append(kit.box("wire shelf", (-w / 2, -d / 2, z - 0.012), (w / 2, d / 2, z), col, M.matte("#B9BCC0", 0.35, 0.6)))
        x = -w / 2 + 0.04
        while x < w / 2 - 0.2 and j < levels - 1:
            kind = rnd.random()
            if kind < 0.55:
                bw = rnd.uniform(0.3, 0.4)
                bh = min(0.28, (h - 0.16) / (levels - 1) - 0.05)
                out.append(rbox("archive box", (x, -d / 2 + 0.03, z), (x + bw, d / 2 - 0.04, z + bh), col, M.matte(rnd.choice(["#C9B590", "#BFA982", "#D3C4A5", "#3B3F45"]), 0.8), 0.006))
                x += bw + 0.03
            elif kind < 0.8:
                ring = [(x + 0.12 + 0.1 * math.cos(t * 2 * math.pi / 24), 0.1 * math.sin(t * 2 * math.pi / 24), z + 0.02) for t in range(25)]
                out.append(tube("cable coil", ring, 0.018, col, M.matte(rnd.choice(["#1A3A6B", "#202226", "#D9D4C8"]), 0.5), 8))
                x += 0.27
            else:
                out.append(rbox("part", (x, -0.1, z), (x + 0.22, 0.1, z + 0.06), col, M.matte("#2A2D33", 0.4, 0.4), 0.004))
                x += 0.27
    return out


def bin_shelving(col, w=1.0, d=0.45, h=1.9, levels=5, seed=5):
    """Grey steel shelving of stacking parts bins, each with a white label on its lip, a few left out or pulled."""
    rnd = random.Random(seed)
    steel = M.steel("#8F959B", 0.4)
    out = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            out.append(kit.box("upright", (sx * (w / 2) - 0.02 * (sx > 0), sy * (d / 2) - 0.02 * (sy > 0), 0), (sx * (w / 2) + 0.02 * (sx < 0), sy * (d / 2) + 0.02 * (sy < 0), h), col, steel))
    gap = (h - 0.15) / (levels - 1)
    for j in range(levels):
        z = 0.1 + j * gap
        out.append(kit.box("steel shelf", (-w / 2, -d / 2, z - 0.02), (w / 2, d / 2, z), col, steel))
        if j == levels - 1:
            continue
        n = int((w - 0.04) / 0.31)
        for i in range(n):
            if rnd.random() < 0.08:
                continue  # one taken down
            x = -w / 2 + 0.03 + i * (w - 0.06) / n
            bw = (w - 0.06) / n - 0.015
            bh = min(0.2, gap - 0.07)
            pull = 0.06 if rnd.random() < 0.15 else 0.0
            tone = rnd.choices(["#8A8F96", "#3E5C7A", "#B0352B"], [0.75, 0.18, 0.07])[0]
            out.append(rbox("bin", (x, -d / 2 + 0.02 - pull, z), (x + bw, d / 2 - 0.03 - pull, z + bh), col, M.matte(tone, 0.55), 0.008))
            out.append(kit.box("bin label", (x + bw * 0.25, -d / 2 + 0.014 - pull, z + bh * 0.55), (x + bw * 0.75, -d / 2 + 0.02 - pull, z + bh * 0.8), col, M.matte("#F2F0EA", 0.6)))
    return out


def cable_tray(col, length=4.0, w=0.3):
    """A galvanised ladder tray, hung under the ceiling on threaded rods, with cables laid in it (at z=0 its top)."""
    galv = M.steel("#A9AEB3", 0.45)
    out = []
    for sy in (-1, 1):
        out.append(kit.box("tray side", (-length / 2, sy * w / 2 - 0.004, -0.06), (length / 2, sy * w / 2 + 0.004, 0.0), col, galv))
    n = int(length / 0.3)
    for i in range(n + 1):
        x = -length / 2 + i * length / n
        out.append(kit.box("tray rung", (x - 0.012, -w / 2, -0.06), (x + 0.012, w / 2, -0.05), col, galv))
    for k, c in enumerate(["#1A3A6B", "#202226", "#B8B03A", "#202226", "#1A3A6B"]):
        y = -w / 2 + 0.05 + k * (w - 0.1) / 4
        out.append(tube("cable", [(-length / 2, y, -0.04), (length / 2, y, -0.04)], 0.011, col, M.matte(c, 0.5), 8))
    for i in range(int(length / 1.2) + 1):
        x = -length / 2 + 0.15 + i * (length - 0.3) / max(1, int(length / 1.2))
        for sy in (-1, 1):
            out.append(kit.cylinder("rod", Vector((x, sy * (w / 2 + 0.02), 0.2)), 0.005, 0.4, col, galv, 8))
    return out


def batten(col, length=1.5, strength=60.0, color="#FFF1DE"):
    """A surface-mounted LED batten on the ceiling, on (at z=0 the ceiling)."""
    return [rbox("batten body", (-length / 2, -0.035, -0.05), (length / 2, 0.035, 0.0), col, M.matte("#EDEBE6", 0.4), 0.008),
            kit.box("batten diffuser", (-length / 2 + 0.02, -0.03, -0.053), (length / 2 - 0.02, 0.03, -0.049), col, M.glow(color, strength))]


def tool_cabinet(col, w=0.7, d=0.46, h=1.0, color="#B32A22"):
    """A steel tool chest on castors, drawers of graded heights."""
    paint = M.matte(color, 0.35, 0.3, coat=0.3)
    steel = M.steel("#B8BCC1", 0.3)
    out = [rbox("chest", (-w / 2, -d / 2, 0.1), (w / 2, d / 2, h), col, paint, 0.01)]
    z = 0.14
    for i, dh in enumerate((0.26, 0.2, 0.14, 0.1, 0.08, 0.08)):
        if z + dh > h - 0.03:
            break
        out.append(kit.box("drawer line", (-w / 2 + 0.02, -d / 2 - 0.003, z + dh - 0.004), (w / 2 - 0.02, -d / 2 + 0.002, z + dh), col, M.matte("#1C1C1C", 0.5)))
        out.append(rbox("pull", (-w / 2 + 0.06, -d / 2 - 0.02, z + dh - 0.03), (w / 2 - 0.06, -d / 2 - 0.004, z + dh - 0.015), col, steel, 0.004))
        z += dh
    for sx in (-1, 1):
        for sy in (-1, 1):
            out.append(kit.cylinder("castor", Vector((sx * (w / 2 - 0.06), sy * (d / 2 - 0.06), 0.05)), 0.045, 0.035, col, M.matte("#1C1C1C", 0.6), 16, axis="X"))
    return out


def crash_cart(col, h=1.0):
    """A small trolley with a screen and keyboard on it, wheeled up to whichever machine needs looking at."""
    steel = M.matte("#2B2E33", 0.4, 0.5)
    out = [kit.box("cart shelf", (-0.3, -0.22, h - 0.03), (0.3, 0.22, h), col, steel),
           kit.box("cart shelf", (-0.3, -0.22, 0.2), (0.3, 0.22, 0.23), col, steel)]
    for sx in (-1, 1):
        for sy in (-1, 1):
            out.append(kit.cylinder("cart post", Vector((sx * 0.28, sy * 0.2, h / 2 + 0.05)), 0.012, h - 0.1, col, M.steel("#B8BCC1", 0.3), 12))
            out.append(kit.cylinder("castor", Vector((sx * 0.26, sy * 0.18, 0.04)), 0.035, 0.03, col, M.matte("#1C1C1C", 0.6), 16, axis="X"))
    out += kit_offset(monitor(col, 0.48, on=False), 0, 0.05, h)
    out += kit_offset(keyboard(col), 0, -0.12, h)
    return out


def kit_offset(objs, x, y, z):
    for ob in objs:
        if ob.parent is None:
            ob.location = (ob.location.x + x, ob.location.y + y, ob.location.z + z)
    return objs


def pegboard(col, w=1.2, h=0.8, seed=5):
    """A pegboard with a few tools hung on it."""
    rnd = random.Random(seed)
    out = [kit.box("pegboard", (-w / 2, -0.012, 0), (w / 2, 0.0, h), col, M.matte("#C9B38E", 0.8))]
    for i in range(7):
        x = -w / 2 + 0.12 + i * (w - 0.24) / 6
        z = rnd.uniform(0.2, h - 0.15)
        kind = rnd.random()
        if kind < 0.4:
            out.append(rbox("screwdriver", (x - 0.012, -0.03, z - 0.18), (x + 0.012, -0.012, z), col, M.matte(rnd.choice(["#B32A22", "#E0A21B", "#1A3A6B"]), 0.4), 0.006))
        elif kind < 0.7:
            out.append(rbox("pliers", (x - 0.03, -0.03, z - 0.2), (x + 0.03, -0.014, z), col, M.steel("#9DA2A8", 0.35), 0.008))
        else:
            ring = [(x + 0.07 * math.cos(t * 2 * math.pi / 20), -0.03, z - 0.08 + 0.07 * math.sin(t * 2 * math.pi / 20)) for t in range(21)]
            out.append(tube("cable loop", ring, 0.008, col, M.matte(rnd.choice(["#202226", "#1A3A6B"]), 0.5), 6))
    return out


def telescope(col):
    """A brass telescope on a wooden tripod, looking up at the sky through the glass."""
    oak = M.oak("#A9825A", 30.0, "Z")
    brass = M.steel("#B89B62", 0.3)
    out = []
    for k in range(3):
        a = k * 2 * math.pi / 3
        out.append(tube("tripod leg", [(math.cos(a) * 0.36, math.sin(a) * 0.36, 0.0), (math.cos(a) * 0.05, math.sin(a) * 0.05, 1.12)], 0.016, col, oak, 10))
    out.append(kit.cylinder("mount", Vector((0, 0, 1.15)), 0.05, 0.08, col, brass, 24))
    d = Vector((0.0, -math.cos(0.65), math.sin(0.65)))
    base = Vector((0, 0, 1.22)) - d * 0.45
    out.append(tube("tube", [tuple(base), tuple(base + d * 1.05)], lambda t: 0.055 + 0.02 * t, col, M.matte("#E3DDD2", 0.35, 0.3, coat=0.4), 32))
    out.append(tube("eyepiece", [tuple(base - d * 0.12), tuple(base)], 0.02, col, brass, 16))
    return out


def street_tree(col, h=7.0, crown=2.6, seed=1):
    """A street tree seen from across the road: as tree() but with fewer, larger leaves, light enough for the live
    building's outside."""
    rnd = random.Random(seed)
    bark = M.matte("#4A4036", 0.9)
    top = Vector((0.05, 0.1, h * 0.5))
    out = [tube("trunk", [(0, 0, 0), (0.08, 0.04, h * 0.3), top], lambda t: 0.16 - 0.08 * t, col, bark, 10)]
    cc = Vector((0, 0, h - crown * 0.85))
    for b in range(5):
        a = rnd.uniform(0, 2 * math.pi)
        end = cc + Vector((math.cos(a) * crown * 0.55, math.sin(a) * crown * 0.55, rnd.uniform(-0.2, 0.6) * crown * 0.5))
        out.append(tube("branch", [top, top.lerp(end, 0.5) + Vector((0, 0, 0.3)), end], lambda t: 0.07 - 0.05 * t, col, bark, 6))
    bm = bmesh.new()
    shape = [(0.0, 0.0), (0.4, 0.32), (1.0, 0.0), (0.4, -0.32)]
    for k in range(int(60 * crown / 3)):
        while True:
            p = Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-1, 1)))
            if p.length <= 1:
                break
        c = cc + Vector((p.x * crown, p.y * crown, p.z * crown * 0.8))
        for i in range(40):
            q = c + Vector((rnd.gauss(0, 0.25), rnd.gauss(0, 0.25), rnd.gauss(0, 0.2)))
            d = Vector((rnd.gauss(0, 1), rnd.gauss(0, 1), rnd.gauss(0, 1) - 0.3)).normalized()
            side = d.cross(Vector((0, 0, 1)))
            side = side.normalized() if side.length > 1e-3 else Vector((1, 0, 0))
            sz = rnd.uniform(0.16, 0.24)
            bm.faces.new([bm.verts.new(q + d * (u * sz) + side * (v * sz)) for u, v in shape])
    leaves = M.foliage(rnd.choice(["#4D6339", "#566B3C", "#45603A"]))
    out.append(kit.obj_from_bmesh("crown", bm, col, leaves))
    core = bmesh.new()
    bmesh.ops.create_icosphere(core, subdivisions=3, radius=1.0)
    for v in core.verts:
        n = 1.0 + 0.14 * math.sin(v.co.x * 5.1 + seed) * math.sin(v.co.y * 4.3) * math.sin(v.co.z * 3.7 + seed)
        v.co = cc + Vector((v.co.x * crown * 0.8 * n, v.co.y * crown * 0.8 * n, v.co.z * crown * 0.64 * n))
    out.append(kit.obj_from_bmesh("crown core", core, col, leaves, smooth=True))
    return out


SCRIPT_FONTS = ("/System/Library/Fonts/Supplemental/SnellRoundhand.ttc", "/System/Library/Fonts/Supplemental/Apple Chancery.ttf")


def wrap(text, most=44):
    """Words into lines of at most `most` characters."""
    lines, line = [], ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > most:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    return lines + ([line] if line else [])


def quote(col, text, by="", w=4.4, h=0.9, color="#2E2A26"):
    """A quote painted on the wall in a script hand, each line centred, with who said it centred under it, standing on
    y=0 and facing -Y, its middle at z=0. For the photographs only: the live building writes the company's own."""
    font = None
    for path in SCRIPT_FONTS:
        try:
            font = bpy.data.fonts.load(path, check_existing=True)
            break
        except (RuntimeError, OSError):
            continue
    lines = wrap(text, max(24, int(w / 0.075)))
    size = min(0.17, h / (len(lines) + 0.8) / 1.25)
    rows = [(line, size) for line in lines] + ([(by, size * 0.62)] if by else [])
    total = sum(s * 1.25 for _, s in rows)
    paint = M.matte(color, 0.6)
    out = []
    z = total / 2
    for k, (line, s) in enumerate(rows):
        z -= s * 1.25
        cu = bpy.data.curves.new("quote", "FONT")
        cu.body = line
        cu.size = s
        cu.align_x = "CENTER"
        if font:
            cu.font = font
        ob = bpy.data.objects.new("quote", cu)
        col.objects.link(ob)
        ob.rotation_euler = (math.pi / 2, 0, 0)
        ob.location = (0, -0.002, z + s * 0.3)
        cu.materials.append(paint)
        out.append(ob)
    return out


def picture_light(col, w=0.5, glow=60.0):
    """A brass picture light on a short arm, its back on y=0, the lamp reaching out toward -Y and shining down."""
    brass = M.matte("#9A7A4A", 0.3, 0.9)
    return [kit.box("picture light plate", (-0.03, -0.012, -0.05), (0.03, 0, 0.05), col, brass, 0.002),
            kit.cylinder("picture light arm", Vector((0, -0.09, 0.04)), 0.008, 0.18, col, brass, 16, axis="Y"),
            kit.cylinder("picture light hood", Vector((0, -0.18, 0.06)), 0.026, w, col, brass, 32, axis="X"),
            kit.box("picture light lamp", (-w / 2 + 0.02, -0.19, 0.03), (w / 2 - 0.02, -0.17, 0.036), col, M.glow("#FFE4C2", glow))]
