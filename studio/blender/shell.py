"""The building from the traced plan: walls cut round every opening, floors, ceiling, windows and doors.

Doors between two styled rooms stand open the way the drawing swings them; every door into a room
that is not styled is shut ("close the doors on the rest").
"""
import math

import bpy
from mathutils import Vector

import kit
import materials as M


def inside(poly, x, y):
    res = False
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            res = not res
    return res


def wall_frame(w):
    """(horizontal?, thickness, along-lo, along-hi, across-centre) of a traced wall."""
    (ax, ay), (bx, by) = w["a"], w["b"]
    h = abs(ay - by) < 1e-6
    lo, hi = (min(ax, bx), max(ax, bx)) if h else (min(ay, by), max(ay, by))
    return h, w["thickness"], lo, hi, (ay if h else ax)


def rooms_beside(plan, o):
    """The rooms on each side of an opening: (room on the lower side, room on the higher side)."""
    w = next(w for w in plan["walls"] if w["id"] == o["wall"])
    h, t, *_ = wall_frame(w)
    mx, my = (o["from"][0] + o["to"][0]) / 2, (o["from"][1] + o["to"][1]) / 2
    off = t / 2 + 0.25
    sides = [(mx, my - off), (mx, my + off)] if h else [(mx - off, my), (mx + off, my)]
    found = []
    for x, y in sides:
        found.append(next((r for r in plan["rooms"] if inside(r["polygon"], x, y)), None))
    return found


def opening_heights(plan, design, o):
    hts = design["heights"]
    if o["kind"] == "window":
        lo_room, hi_room = rooms_beside(plan, o)
        room = lo_room or hi_room
        small = o["width"] <= design["small_window_max_width"] and (room is None or room["name"] not in design["styled"])
        return (hts["small_window_sill"] if small else hts["window_sill"]), hts["window_head"]
    if o["kind"] == "open":
        return 0.0, 2.5
    return 0.0, hts["door_head"]


def street_drop(design):
    """How far the street is below this floor: whole storeys for an upper floor, one step for the ground floor."""
    fl = design.get("floor", {})
    return fl.get("level", 0) * fl.get("floor_to_floor", 4.0) or 0.15


def build_shell(plan, design, styles):
    col = kit.collection("shell")
    H = design["heights"]["ceiling"]
    fl = design.get("floor", {})
    G = street_drop(design)   # how far the ground is below this floor
    walls = plan["walls"]
    mottle = design.get("finish", {}).get("plaster_mottle", 0.0)
    plaster = M.plaster(mottle=mottle) if mottle else M.plaster()

    def meets(x, y, me):
        for o in walls:
            if o is me:
                continue
            h, t, lo, hi, c = wall_frame(o)
            if (h and lo - 1e-3 <= x <= hi + 1e-3 and abs(y - c) <= t / 2 + 1e-3) or \
               (not h and lo - 1e-3 <= y <= hi + 1e-3 and abs(x - c) <= t / 2 + 1e-3):
                return True
        return False

    for w in walls:
        h, t, lo, hi, c = wall_frame(w)
        if meets(*((lo, c) if h else (c, lo)), w):
            lo -= t / 2
        if meets(*((hi, c) if h else (c, hi)), w):
            hi += t / 2
        cuts = []
        for o in plan["openings"]:
            if o["wall"] != w["id"]:
                continue
            a, b = sorted((o["from"][0], o["to"][0]) if h else (o["from"][1], o["to"][1]))
            sill, head = opening_heights(plan, design, o)
            cuts.append((a, b, sill, head, o))
        cuts.sort(key=lambda c_: c_[0])
        parts = []
        at = lo
        for a, b, sill, head, o in cuts:
            if a > at:
                parts.append((at, a, 0.0, H))
            if sill > 0:
                parts.append((a, b, 0.0, sill))
            parts.append((a, b, head, H))
            at = b
        if hi > at:
            parts.append((at, hi, 0.0, H))
        parts.append((lo, hi, -G, -0.02))  # the storeys below, so the floor stands on a building
        for i, (a, b, z0, z1) in enumerate(parts):
            z1 = z1 + 0.25 if z1 >= H - 1e-6 else z1  # up through the ceiling slab
            if h:
                kit.box(f"{w['id']}.{i}", (a, c - t / 2, z0), (b, c + t / 2, z1), col, plaster)
            else:
                kit.box(f"{w['id']}.{i}", (c - t / 2, a, z0), (c + t / 2, b, z1), col, plaster)
        for a, b, sill, head, o in cuts:
            if o["kind"] == "window":
                window(o, h, t, c, a, b, sill, head, col, plan["size"])
            elif o["kind"] in ("door", "double door"):
                door(plan, design, o, h, t, c, a, b, head, col)

    # Each room: its finished floor, the slab under it and the ceiling over it (the building is an L, so
    # nothing is laid over the open corner).
    W, D = plan["size"]
    for r in plan["rooms"]:
        style = styles.get(r["name"], {})
        floor = style.get("floor", "oak")
        mat = M.terrazzo(style.get("floor_tone", "#DCD6CC")) if floor == "terrazzo" else M.oak_floor(style.get("floor_tone", "#C7B59C"))
        kit.polygon_slab(f"floor {r['name']} {r['id']}", r["polygon"], -0.02, 0.0, col, mat)
        kit.polygon_slab(f"slab {r['id']}", r["polygon"], -0.3, -0.02, col, M.matte("#9C968C", 0.9))
        kit.polygon_slab(f"ceiling {r['id']}", r["polygon"], H, H + 0.25, col, M.plaster("#F5F4F1", mottle=mottle) if mottle else M.plaster("#F5F4F1"))
    # Outside, a storey down: open ground, and paving round the building.
    kit.box("ground", (-400, -400, -G - 0.02), (400, 400, -G), col, M.ground())
    kit.box("paving", (-3, -3, -G), (W + 3, D + 3, -G + 0.02), col, M.stone("#CFC8BC", "#B9B0A2", 0.6, 0.5))


def window(o, h, t, c, a, b, sill, head, col, size):
    """Slim black frames set near the outside face, split into panes no wider than 1.6 m."""
    black = M.matte("#1C1C1C", 0.4)
    glass = M.window_glass()
    # The outside face is the one nearer the building's edge; frames sit 8 cm in from it.
    mid = size[1] / 2 if h else size[0] / 2
    out_face = c - t / 2 if c < mid else c + t / 2
    plane = out_face + (0.08 if out_face < c else -0.08)
    fw, fd = 0.05, 0.07  # frame face width and depth
    n = max(1, math.ceil((b - a) / 1.6))
    xs = [a + (b - a) * k / n for k in range(n + 1)]

    def bar(u0, u1, z0, z1, name):
        if h:
            kit.box(name, (u0, plane - fd / 2, z0), (u1, plane + fd / 2, z1), col, black, bevel=0.004)
        else:
            kit.box(name, (plane - fd / 2, u0, z0), (plane + fd / 2, u1, z1), col, black, bevel=0.004)

    bar(a, b, sill, sill + fw, f"{o['id']} sill")
    bar(a, b, head - fw, head, f"{o['id']} head")
    for k, x in enumerate(xs):
        u0 = x if k == 0 else (x - fw if k == n else x - fw / 2)
        u1 = x + fw if k == 0 else (x if k == n else x + fw / 2)
        bar(u0, u1, sill, head, f"{o['id']} post {k}")
    if h:
        kit.box(f"{o['id']} glass", (a, plane - 0.003, sill), (b, plane + 0.003, head), col, glass)
    else:
        kit.box(f"{o['id']} glass", (plane - 0.003, a, sill), (plane + 0.003, b, head), col, glass)


def door(plan, design, o, h, t, c, a, b, head, col):
    """A flush oak door with a black lever, in a white lined opening; open or shut as the rooms say."""
    lo_room, hi_room = rooms_beside(plan, o)
    styled = design["styled"]
    exterior = lo_room is None or hi_room is None
    is_open = not exterior and (design.get("all_doors_open") or (lo_room["name"] in styled and hi_room["name"] in styled and o["id"] not in design.get("moment", {}).get("shut", [])))
    lining = M.matte("#F2F0EB", 0.35)
    leaf_mat = M.oak("#CBA57A", 30.0, "Z")
    black = M.matte("#1C1C1C", 0.38)
    glass = M.window_glass()
    # the lining of the opening: two jambs and a head across the wall's thickness
    j = 0.02
    if h:
        kit.box(f"{o['id']} jamb a", (a, c - t / 2, 0), (a + j, c + t / 2, head), col, lining)
        kit.box(f"{o['id']} jamb b", (b - j, c - t / 2, 0), (b, c + t / 2, head), col, lining)
        kit.box(f"{o['id']} lining head", (a, c - t / 2, head - j), (b, c + t / 2, head), col, lining)
    else:
        kit.box(f"{o['id']} jamb a", (c - t / 2, a, 0), (c + t / 2, a + j, head), col, lining)
        kit.box(f"{o['id']} jamb b", (c - t / 2, b - j, 0), (c + t / 2, b, head), col, lining)
        kit.box(f"{o['id']} lining head", (c - t / 2, a, head - j), (c + t / 2, b, head), col, lining)
    # casings (architraves) round the opening on both faces: 60 mm wide, standing 15 mm proud of the plaster
    cw, cp = 0.06, 0.015
    for f in (-1, 1):
        face = c + f * t / 2
        y0_, y1_ = (face, face + f * cp) if f > 0 else (face + f * cp, face)
        if h:
            kit.box(f"{o['id']} casing", (a - cw, y0_, 0), (a, y1_, head + cw), col, lining, 0.002)
            kit.box(f"{o['id']} casing", (b, y0_, 0), (b + cw, y1_, head + cw), col, lining, 0.002)
            kit.box(f"{o['id']} casing", (a - cw, y0_, head), (b + cw, y1_, head + cw), col, lining, 0.002)
        else:
            kit.box(f"{o['id']} casing", (y0_, a - cw, 0), (y1_, a, head + cw), col, lining, 0.002)
            kit.box(f"{o['id']} casing", (y0_, b, 0), (y1_, b + cw, head + cw), col, lining, 0.002)
            kit.box(f"{o['id']} casing", (y0_, a - cw, head), (y1_, b + cw, head + cw), col, lining, 0.002)
    leaves = [("a", b - a)] if o.get("hinge") == "a" else [("b", b - a)] if o.get("hinge") == "b" else [("a", (b - a) / 2), ("b", (b - a) / 2)]
    side = {"up": 1, "right": 1, "down": -1, "left": -1}.get(o.get("swing"), 1)
    for which, width in leaves:
        lw = width - j - 0.004
        thick = 0.042
        parts = []
        lcol = col
        if exterior:  # a glazed front door: black frame round glass
            fr = 0.07
            parts += [kit.box("stile a", (0, -thick / 2, 0.01), (fr, thick / 2, head - j - 0.004), lcol, black, 0.003),
                      kit.box("stile b", (lw - fr, -thick / 2, 0.01), (lw, thick / 2, head - j - 0.004), lcol, black, 0.003),
                      kit.box("rail top", (fr, -thick / 2, head - j - 0.004 - fr), (lw - fr, thick / 2, head - j - 0.004), lcol, black, 0.003),
                      kit.box("rail foot", (fr, -thick / 2, 0.01), (lw - fr, thick / 2, 0.01 + fr * 1.6), lcol, black, 0.003),
                      kit.box("pane", (fr, -0.004, 0.01 + fr * 1.6), (lw - fr, 0.004, head - j - 0.004 - fr), lcol, glass)]
        else:
            parts.append(kit.box("leaf", (0, -thick / 2, 0.01), (lw, thick / 2, head - j - 0.004), lcol, leaf_mat, 0.003))
        # lever handles on both faces, 1.0 m up, 6 cm in from the free edge
        for f in (-1, 1):
            parts.append(kit.cylinder("rose", Vector((lw - 0.07, f * (thick / 2 + 0.006), 1.0)), 0.026, 0.012, lcol, black, axis="Y"))
            parts.append(kit.box("lever", (lw - 0.075 - 0.13, f * (thick / 2 + 0.03) - 0.008, 0.99), (lw - 0.065, f * (thick / 2 + 0.03) + 0.008, 1.01), lcol, black, 0.006))
        hinge_u = a + j if which == "a" else b - j
        sign = 1 if which == "a" else -1          # the leaf runs from its hinge towards the other end
        angle = math.radians(86 if is_open else 0) * side * sign
        if h:
            root = kit.place(parts, (hinge_u, c, 0), 0.0, f"{o['id']} door {which}", col)
            root.rotation_euler = (0, 0, (0 if sign > 0 else math.pi) + angle)
        else:
            root = kit.place(parts, (c, hinge_u, 0), 0.0, f"{o['id']} door {which}", col)
            root.rotation_euler = (0, 0, (math.pi / 2 if sign > 0 else -math.pi / 2) - angle)
        root["open"] = is_open
