"""Furnishes and styles the rooms of one project's floor, from code. Each room is set out for what it holds in
Arnheim (design.json says which): flags for goals, a desk per task, a seat per conversation, books and crates
for code, a filing cabinet per part of the company. Positions come from each traced room's inside faces, so
the furniture follows the plan if the drawing changes a little.

Every piece faces a compass side of the plan: S is towards y=0 (the sunny front), N towards the back,
E towards x=24, W towards x=0, or an angle (radians) from facing S.
"""
import math
import random

import bmesh
from mathutils import Vector

import json
import os

import kit
import materials as M
import people
import pieces as P
import shell

FACE = {"S": 0.0, "N": math.pi, "E": math.pi / 2, "W": -math.pi / 2}


def everyone(design, room):
    """Who is in this room at the photographed moment (design.json "moment"), each with their look: an agent by
    the id of what they work on, the founder's assistant from the company file, the founder by their name."""
    m = design.get("moment", {}).get(room)
    if not m:
        return []
    org = None
    out = []
    for p in m if isinstance(m, list) else [m]:
        if p.get("assistant") or p.get("founder") or p.get("receptionist"):
            if org is None:
                here = os.path.dirname(os.path.abspath(__file__))
                org = json.load(open(os.path.join(here, "..", "..", design["moment"]["company"])))
        if p.get("receptionist"):  # dressed the way the company file describes them, as the assistant is
            look = people.assistant_look(org["receptionist"].get("look", {}))
            look["trousers"] = "#2B2A2E"
        elif p.get("assistant"):
            look = people.assistant_look(org["assistant"].get("look", {}))
            look["trousers"] = "#3A4456"  # a navy that still reads in the shade under the table
        elif p.get("founder"):
            look = people.agent_look(org["founder"]["name"])
        else:
            look = people.agent_look(p["id"])
        look.update({k: p[k] for k in ("wear", "top", "build", "mouth", "nod", "roll", "collar") if k in p})  # what they wear today, their face (design.json)
        out.append((p, look))
    return out


def who(design, room):
    found = everyone(design, room)
    return found[0] if found else (None, None)


def identity_seed(m):
    return people.identity(m.get("id", "founder" if m.get("founder") else "receptionist" if m.get("receptionist") else "assistant")) % 1000


def toward(dx, dy):
    """The facing that points a piece's front along (dx, dy)."""
    return math.atan2(dx, -dy)


SLOTS = []  # where the live layer puts what comes from the company's data (bake.py writes them to floor.json)


def put(objs, x, y, face="S", name="piece", col=None, z=0.0, turn=0.0, live=None, slot=None):
    """Places a piece. live names what it shows from the company's data (a desk per task, a seat per
    conversation, the company's name): the photographs keep it, a shell bake for the live building leaves it
    out. slot, with live, records where the live building should put its own: kind, place, facing and size."""
    rot = (FACE[face] if isinstance(face, str) else face) + turn
    root = kit.place(objs, (x, y, z), rot, name, col)
    if live:
        root["live"] = live
        if slot is not None:
            SLOTS.append({"kind": live, "at": [round(x, 3), round(y, 3), round(z, 3)], "rot": round(rot, 4), **slot})
    return root


def bounds(room):
    xs = [p[0] for p in room["polygon"]]
    ys = [p[1] for p in room["polygon"]]
    return min(xs), max(xs), min(ys), max(ys)


def fruit_bowl(col, seed=2):
    rnd = random.Random(seed)
    out = [kit.lathe("bowl", [(0.0, 0.0), (0.07, 0.0), (0.15, 0.06), (0.16, 0.08), (0.15, 0.078), (0.0, 0.018)], col, M.ceramic("#2D2D2B", 0.3), 48)]
    for k in range(6):
        a = k / 6 * 2 * math.pi + rnd.uniform(-0.2, 0.2)
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=12, radius=0.037)
        bmesh.ops.translate(bm, vec=(math.cos(a) * 0.07, math.sin(a) * 0.07, 0.06 + (0.03 if k % 2 else 0)), verts=bm.verts)
        out.append(kit.obj_from_bmesh("fruit", bm, col, M.matte(rnd.choice(["#E5892B", "#D97A22", "#C9B23A"]), 0.45, coat=0.2), smooth=True))
    return out


# ---------- what every finished room has: skirting, ceiling fittings, blinds ----------

def edge_gaps(plan, axis, at, kinds):
    """Openings in the wall along a room's edge, as (lo, hi, kind)."""
    out = []
    for o in plan["openings"]:
        w = next(w for w in plan["walls"] if w["id"] == o["wall"])
        h, t, _lo, _hi, c = shell.wall_frame(w)
        if (axis == "h") != h or abs(c - at) > t / 2 + 0.03 or o["kind"] not in kinds:
            continue
        lo, hi = sorted((o["from"][0], o["to"][0]) if h else (o["from"][1], o["to"][1]))
        out.append((lo, hi, o["kind"]))
    return sorted(out)


def finish(col, plan, design, room, style=None):
    x0, x1, y0, y1 = bounds(room)
    lights = (style or {}).get("lights", "downlights")
    H = design["heights"]["ceiling"]
    white = M.matte("#F2F0EB", 0.4)
    edges = [("h", y0, x0, x1, +1), ("h", y1, x0, x1, -1), ("v", x0, y0, y1, +1), ("v", x1, y0, y1, -1)]
    for axis, at, lo, hi, inward in edges:
        gaps = [g for g in edge_gaps(plan, axis, at, ("door", "double door", "open", "window")) if g[1] > lo + 0.01 and g[0] < hi - 0.01]
        at_ = lo
        runs = []
        for g_lo, g_hi, kind in gaps:
            pad = 0.06 if kind in ("door", "double door") else 0.0  # stop at the door casing
            if g_lo - pad > at_:
                runs.append((at_, g_lo - pad))
            at_ = max(at_, g_hi + pad)
        if hi > at_:
            runs.append((at_, hi))
        for a, b in runs:  # skirting, 80 mm tall and 15 mm proud
            if b - a < 0.05:
                continue
            if axis == "h":
                ys = (at, at + 0.015) if inward > 0 else (at - 0.015, at)
                kit.box("skirting", (a, ys[0], 0), (b, ys[1], 0.08), col, white, 0.002)
            else:
                xs = (at, at + 0.015) if inward > 0 else (at - 0.015, at)
                kit.box("skirting", (xs[0], a, 0), (xs[1], b, 0.08), col, white, 0.002)
        for g_lo, g_hi, kind in gaps:  # a roller blind at every window, let down a little
            if kind != "window":
                continue
            face = {"h": {+1: "N", -1: "S"}, "v": {+1: "E", -1: "W"}}[axis][inward]
            mid = (g_lo + g_hi) / 2
            x, y = (mid, at) if axis == "h" else (at, mid)
            put(P.roller_blind(col, g_hi - g_lo + 0.1, 0.06), x, y, face, "blind", col, z=H - 0.02)
    # recessed downlights on a grid about 2.4 m apart, a sprinkler head beside each (style "lights": "downlights on"
    # lights them, as in a room below ground; "battens" hangs LED battens instead, as in a machine room)
    grid = 3.6 if lights == "battens" else 2.4  # battens: fewer, so the room keeps its shadows (four in a machine room)
    nx = max(1, round((x1 - x0) / grid))
    ny = max(1, round((y1 - y0) / grid))
    for i in range(nx):
        for j in range(ny):
            x = x0 + (i + 0.5) * (x1 - x0) / nx
            y = y0 + (j + 0.5) * (y1 - y0) / ny
            if lights == "battens":
                put(P.batten(col, 1.5, 36.0, "#FFD9B0"), x, y, "E" if (y1 - y0) > (x1 - x0) else "S", "batten", col, z=H)  # about 3600 K
            else:
                put(P.downlight(col, lit=lights == "downlights on"), x, y, "S", "downlight", col, z=H)
            put(P.sprinkler(col), x + 0.6, y + 0.3, "S", "sprinkler", col, z=H)


# ---------- the rooms ----------

def goals(col, room, plan, design, style):
    """What the project is working toward: a card and a flag each on the goals board, red while open, gold once
    reached, hung over the sofa on the back wall, with a low table and a chair drawn up to talk them over."""
    x0, x1, y0, y1 = bounds(room)
    bx = x0 + 4.35  # between the door to the code room and the corner
    put(P.goals_board(col, [tuple(g) for g in style.get("goals", [])], 1.3, 1.0), bx, y1, "S", "goals wall", col, z=1.55,
        live="goals", slot={"w": 1.3, "h": 1.0, "on": "wall"})
    sy = y1 - 0.5
    put(P.rug(col, 2.6, 2.0, "#D8CFC0"), bx - 0.1, y1 - 1.35, "S", "rug", col)
    put(P.sofa(col, 1.9, 0.92, "#CFCBC4", legs="black", back_h=0.70, cushions=("#3A3835", "#B5603F"), loops=0.9), bx, sy, "S", "sofa", col)
    tx, ty = bx, sy - 0.46 - 0.38 - 0.4
    put(P.table(col, 0.8, 0.8, 0.36, top="stone", style="plinth", round_=True), tx, ty, "S", "coffee table", col)
    put(P.objet(col, (0, 0, 0), random.Random(12)), tx - 0.15, ty + 0.12, "S", "vase", col, z=0.36)
    put(P.book_stack(col, 3, seed=5), tx + 0.12, ty - 0.1, "S", "books", col, z=0.36, turn=0.4)
    cx_, cy_ = x0 + 2.6, y0 + 3.0
    put(P.lounge_chair(col, "#7A4A2A", "leather"), cx_, cy_, toward(tx - cx_, ty - cy_), "lounge chair", col)
    put(P.floor_lamp(col, 1.5), x1 - 0.17, y1 - 0.2, "S", "floor lamp", col)
    put(P.art(col, 0.7, 0.9, ("#E9E1D3", "#2E3B35", "#B9653E", "#D9CBB5"), 2.3, "bands", "black"), x0 + 1.25, y1, "S", "art", col, z=1.5)
    put(P.plant(col, "fig", 1.9, "#E3DDD3", seed=3), x0 + 0.4, y1 - 0.4, "S", "fig", col)
    put(P.plant(col, "snake", 0.95, "#2E2D2B", seed=8), x0 + 1.95, y1 - 0.3, "S", "snake plant", col)


def code(col, room, plan, design, style):
    """The project's code: open pull requests as books on the shelves, copies with unsaved changes as crates."""
    x0, x1, y0, y1 = bounds(room)
    for k, xx in enumerate((x0 + 0.85, x0 + 2.37)):
        put(P.bookcase(col, 1.5, 2.4, 0.34, 2, 6, seed=71 + k), xx, y1 - 0.34, "S", "shelves of pull requests", col,
            live="shelves", slot={"w": 1.5, "h": 2.4, "d": 0.34, "cols": 2, "rows": 6})
    put(P.crate(col, 0.45, 0.32, 0.28, tone="#9C7550", seed=1), x0 + 2.6, y1 - 0.62, "S", "crate", col, turn=0.07,
        live="crate", slot={"w": 0.45, "d": 0.32, "h": 0.28, "row": [x0 + 2.4, x0 + 3.9]})
    put(P.crate(col, 0.45, 0.32, 0.28, tone="#9C7550", seed=2), x0 + 3.14, y1 - 0.6, "S", "crate", col, turn=-0.09, live="crate")
    tx, ty = x0 + 2.45, y0 + 2.2
    put(P.rug(col, 2.6, 2.0, "#CDBFA9"), tx, ty, "S", "rug", col)
    put(P.table(col, 1.7, 0.85, 0.74, top="oak", legs="oak", style="four", tone="#C9A882"), tx, ty, "S", "reading table", col)
    put(P.shell_chair(col, "#CFC4B3"), tx - 0.42, ty + 0.72, "S", "chair", col, turn=0.12)
    put(P.shell_chair(col, "#CFC4B3"), tx + 0.45, ty + 0.5, "S", "chair", col, turn=math.radians(15))
    put(P.notebook(col, "#8C5A3C", 0.15, 0.22, open_=True), tx - 0.35, ty + 0.12, "S", "open book", col, z=0.74, turn=0.2)
    put(P.notebook(col, "#2F3B36", 0.13, 0.2, open_=True), tx + 0.45, ty - 0.05, "S", "open book", col, z=0.74, turn=-0.35)
    put(P.sheets(col, 3, seed=4), tx + 0.05, ty - 0.2, "S", "sheets", col, z=0.74)
    put(P.mug(col, "#2E2D2B"), tx + 0.62, ty + 0.25, "S", "mug", col, z=0.74)
    put(P.pen(col), tx - 0.05, ty + 0.2, "S", "pen", col, z=0.74, turn=0.6)
    put(P.pendant_cone(col, 0.2, 3.0 - (0.74 + 0.75), color="#E9E4DA"), tx, ty, "S", "light", col)
    ax, ay = x0 + 0.65, y0 + 1.25  # the reading chair, in the window corner, turned to the room
    put(P.lounge_chair(col, "#8E5B32", "leather"), ax, ay, toward(4.6, -0.3), "leather chair", col)
    put(P.table(col, 0.4, 0.4, 0.52, top="black", legs="black", style="pedestal", round_=True), ax, ay + 0.75, "S", "side table", col)
    put(P.book_stack(col, 2, seed=9), ax, ay + 0.75, "S", "books", col, z=0.52, turn=0.3)
    put(P.floor_lamp(col, 1.4), x0 + 0.25, y0 + 0.5, "S", "floor lamp", col)
    put(P.plant(col, "fig", 1.6, "#A8674A", seed=29), x0 + 0.4, y0 + 3.65, "S", "fig", col)
    put(P.art(col, 1.0, 0.7, ("#ECE5D8", "#7E8B74", "#2E3B35", "#C9A57B"), 4.1, "blobs", "oak"), x1, y0 + 1.6, "W", "art", col, z=1.55)
    put(P.plant(col, "fig", 1.8, "#D9D2C6", seed=17), x1 - 0.4, y1 - 0.4, "S", "fig", col)


def conversations(col, room, plan, design, style):
    """Where the work is talked through: a seat each at the table."""
    x0, x1, y0, y1 = bounds(room)
    cx, cy = x0 + 2.55, (y0 + y1) / 2
    put(P.table(col, 2.8, 1.05, 0.74, top="oak", legs="black", style="sled", tone="#C9A882", top_th=0.04), cx, cy, "S", "table", col)
    put(P.rug(col, 3.2, 2.3, "#A39A8F"), cx, cy, "S", "rug", col)
    tuck = 1.05 / 2 - 0.10 + 0.24  # seat fronts 0.10 m under the table's edge
    here = everyone(design, "CONVERSATIONS")
    for i in range(3):
        x = cx - 0.75 + i * 0.75
        r = random.Random(40 + i)
        for row, sgn, pulled in (("S", -1, 0.15 if i == 0 else 0.0), ("N", 1, 0.15 if i == 2 else 0.0)):
            off = tuck + r.uniform(0.0, 0.08) + pulled
            turn = math.radians(r.uniform(-6, 6))
            facing = "N" if sgn < 0 else "S"
            if any(m["seat"] == [i, row] for m, _ in here):
                off = 0.525 + 0.16  # drawn in: the table's edge 16 cm in front of the seat's middle
            for m, look in here:
                if m["seat"] == [i, row]:  # turned towards whoever they are talking to
                    turn = math.radians(m.get("turn", 0))
                    put(people.person(col, look, "chat", seat=0.47, table=0.74, reach=off - 0.525 + 0.15, seed=identity_seed(m),
                                      look_to=math.radians(m.get("look", 0)), hands=m.get("hands", "table"), moving=m.get("moving", 0.0)),
                        x, cy + sgn * off, facing, "person", col, turn=turn)
            put(P.shell_chair(col, "#8C7A66"), x, cy + sgn * off, facing, "seat", col, turn=turn,
                live="seat", slot={"table": [round(cx, 3), round(cy, 3)], "seat": [i, row], "tuck": round(0.525 + 0.16, 3)})
    for k in (-1, 0, 1):
        put(P.pendant_globe(col, 0.15, 3.0 - (0.74 + 0.75 + 0.15), glow=8.0), cx + k * 0.8, cy, "S", "globe", col)
    put(P.carafe(col), cx + 0.15, cy + 0.05, "S", "carafe", col, z=0.74)
    held = [(cx - 0.75 + m["seat"][0] * 0.75, 1 if m["seat"][1] == "N" else -1) for m, _ in here]  # whoever sits holds their own glass
    for dx, dy in ((-0.85, -0.32), (0.85, 0.3)):
        if not any(abs(cx + dx - hx) < 0.4 and dy * side > 0 for hx, side in held):
            put(P.tumbler(col), cx + dx + 0.18, cy + dy, "S", "glass", col, z=0.74)
    for m, _ in here:  # an open laptop beside whoever brought it, turned a little towards the person next to them
        if m.get("laptop"):
            sgn = 1 if m["seat"][1] == "N" else -1
            put(P.laptop(col, True), cx - 0.75 + m["seat"][0] * 0.75 - sgn * 0.3, cy + sgn * (0.525 - 0.2), "N" if sgn > 0 else "S", "laptop", col, z=0.74, turn=0.2, live="prop")
    lap = any(m.get("laptop") for m, _ in here)
    put(P.notebook(col, "#2F3B36"), cx - 0.8, cy - 0.2, "S", "notebook", col, z=0.74, turn=0.15)
    put(P.notebook(col, "#C9B79C"), cx + 0.85, cy + 0.18, "S", "notebook", col, z=0.74, turn=-0.25)
    put(P.pen(col), cx - 0.62 - (0.05 if lap else 0.0), cy - 0.22, "S", "pen", col, z=0.74, turn=1.2)
    if not lap:
        put(P.laptop(col, open_=False), cx - 0.1, cy + 0.2, "N", "laptop", col, z=0.74, turn=0.12)
    put(P.sideboard(col, 1.25, 0.42, 0.72, legs=True), x1 - 0.68, y1 - 0.21, "S", "credenza", col)
    put(P.art(col, 0.7, 0.9, ("#E9E1D3", "#2E3B35", "#B9653E", "#D9CBB5"), 3.1, "bands", "black"), x1 - 0.68, y1, "S", "art", col, z=1.55)
    put(P.slat_wall(col, w=2.8, h=3.0, slat=0.02, gap=0.015, depth=0.025), x0 + 1.6, y0, "N", "slats", col)
    put(P.sideboard(col, 1.8, 0.42, 0.75, legs=True), x0 + 1.6, y0 + 0.25, "N", "sideboard", col)
    rnd = random.Random(23)
    for k in range(3):
        put(P.objet(col, (0, 0, 0), rnd), x0 + 1.05 + k * 0.55, y0 + 0.25, "S", "on sideboard", col, z=0.75)
    put([kit.box("led strip", (-1.4, -0.03, -0.01), (1.4, 0.0, 0.0), col, M.glow("#FFD9A8", 30.0))], x0 + 1.6, y0 + 0.06, "N", "led", col, z=2.99)
    put(P.plant(col, "fig", 2.0, "#E3DDD3", seed=11), x0 + 0.55, y1 - 0.5, "S", "fig", col)


def work(col, room, plan, design, style):
    """The project's tasks: a desk each, in clusters along the sunny front."""
    x0, x1, y0, y1 = bounds(room)
    rnd = random.Random(7)
    extra = random.Random(17)
    m, look = who(design, "WORK")
    for ci, cx in enumerate((x0 + 3.0, x0 + 6.6, x0 + 10.2)):
        for ri, cy in enumerate((y0 + 2.7, y0 + 4.32)):
            for side, face in ((-1, "E"), (1, "W")):
                screen_face = "E" if side > 0 else "W"
                put(P.table(col, 1.6, 0.8, 0.74, top="oak", legs="black", style="four", tone="#C9A882"), cx + side * 0.4, cy, face, "desk", col,
                    live="desk", slot={"w": 1.6, "d": 0.8, "h": 0.74, "cluster": ci, "row": ri, "side": side, "chair": [round(cx + side * 0.9, 3), round(cy, 3)]})
                pick = rnd.random()
                reach = 0.9 if pick < 0.5 else 1.02  # tucked in, or just out from the desk
                seat = "#B5603F" if rnd.random() < 0.18 else rnd.choice(["#3F4743", "#3F4743", "#5A5650"])
                cy_chair, turn = cy + rnd.uniform(-0.08, 0.08), rnd.choice((-1, 1)) * rnd.uniform(0.03, 0.09)
                busy = m is not None and [ci, ri, side] == m["desk"]
                if busy:  # someone at work here: the chair drawn up, square to the desk
                    reach, cy_chair, turn = 0.8, cy + 0.02, 0.1  # close enough that the elbows bend to the keys, a little off square
                    put(people.person(col, look, "desk", seat=0.52, table=0.74, reach=reach - 0.5 + 0.045, seed=identity_seed(m)),
                        cx + side * (reach + 0.045), cy_chair, "W" if side > 0 else "E", "person", col, turn=turn)  # back in the seat, against the backrest
                put(P.task_chair(col, seat), cx + side * reach, cy_chair, "W" if side > 0 else "E", "chair", col, turn=turn, live="desk")
                lit = rnd.random() < 0.0 or (cx > x0 + 5 and cy > y0 + 3.5 and side < 0)  # two left on at the desktop, facing the door
                put(P.monitor(col, 0.61, on="wallpaper" if lit else False), cx + side * 0.14, cy + 0.2, screen_face, "screen", col, z=0.74, live="desk")
                put(P.keyboard(col), cx + side * 0.5, cy + 0.15, screen_face, "keyboard", col, z=0.74, turn=rnd.uniform(-0.06, 0.06), live="desk")
                put(P.mouse(col), cx + side * 0.52, cy - 0.17, screen_face, "mouse", col, z=0.74, live="desk")
                what = rnd.random()
                if what < 0.4:
                    put(P.mug(col, rnd.choice(["#E9E2D6", "#2E2D2B", "#B9653E"])), cx + side * 0.42, cy - 0.5, "S", "mug", col, z=0.74, live="desk")
                elif what < 0.7:
                    put(P.notebook(col, rnd.choice(["#2F3B36", "#C9B79C", "#8C5A3C"])), cx + side * 0.45, cy - 0.45, "S", "notebook", col, z=0.74, turn=rnd.uniform(-0.4, 0.4), live="desk")
                else:
                    put(P.task_lamp(col), cx + side * 0.25, cy - 0.6, "E" if side > 0 else "W", "desk lamp", col, z=0.74, live="desk")
                if what < 0.4:  # a second thing on every desk (its own random numbers, so the chairs keep theirs)
                    put(P.notebook(col, extra.choice(["#2F3B36", "#C9B79C", "#8C5A3C"])), cx + side * 0.62, cy - 0.42, "S", "notebook", col, z=0.74, turn=extra.uniform(-0.4, 0.4), live="desk")
                else:
                    put(P.mug(col, extra.choice(["#E9E2D6", "#2E2D2B", "#B9653E"])), cx + side * 0.66, cy - 0.32, "S", "mug", col, z=0.74, live="desk")
                if rnd.random() < 0.4:
                    put(P.laptop(col, open_=False), cx + side * 0.5, cy + 0.55, screen_face, "laptop", col, z=0.74, turn=rnd.uniform(-0.2, 0.2), live="desk")
        put(P.pendant_linear(col, 2.6, 0.5), cx, y0 + 3.51, "E", "light", col)
        put(P.book_stack(col, 3, seed=int(cx * 7)), cx + 0.55, y0 + 2.08, "S", "books", col, z=0.74, turn=cx, live="desk")
        put(P.laptop(col, open_=False), cx - 0.5, y0 + 5.0, "E", "laptop", col, z=0.74, turn=0.1, live="desk")
        put(P.task_lamp(col), cx - 0.1, y0 + 2.0, "E", "desk lamp", col, z=0.74, live="desk")
        if x0 + 4 < cx < x0 + 8:  # one desk plant, in the middle cluster
            put(P.plant(col, "fig", 0.42 if cx < x0 + 4 else 0.55, "#B5603F", seed=int(cx * 3)), cx + 0.1, y0 + 5.0, "S", "desk plant", col, z=0.74, turn=cx, live="desk")
        put([P.rbox("cable spine", (-0.03, -0.03, 0.0), (0.03, 0.03, 0.72), col, M.matte("#1C1C1C", 0.5), 0.01)], cx, y0 + 3.51, "S", "cable spine", col, live="desk")
    for k, yy in enumerate((y1 - 1.0, y1 - 2.65)):
        put(P.bookcase(col, 1.6, 2.2, 0.34, 2, 5, seed=7 + k), x1 - 0.34, yy, "W", "bookcase", col)
    put(P.sofa(col, 2.2, 0.9, "#B9B2A4", cushions=("#B5603F", "#B5603F", "#3A3835")), x0 + 5.2, y1 - 0.5, "S", "sofa", col)
    put(P.table(col, 0.45, 0.45, 0.52, top="oak", style="pedestal", round_=True), x0 + 6.62, y1 - 0.5, "S", "side table", col)
    put(P.book_stack(col, 2, seed=5), x0 + 6.62, y1 - 0.5, "S", "books", col, z=0.52, turn=0.4)
    put(P.rug(col, 3.8, 3.4, "#C9BFAF"), x0 + 6.6, y0 + 3.51, "E", "rug", col)
    put(P.plant(col, "fig", 1.75, "#D9D2C6", seed=53), x0 + 6.89, y0 + 6.2, "S", "fig", col)
    put(P.art(col, 1.2, 0.9, ("#ECE5D8", "#C46A3C", "#2E3B35", "#D9B98C"), 6.7, "blobs", "oak"), x1, y0 + 3.2, "W", "canvas", col, z=1.5)
    put(P.plant(col, "fig", 1.95, "#E3DDD3", seed=13), x1 - 0.5, y0 + 0.55, "S", "fig", col)
    put(P.plant(col, "snake", 1.3, "#9C968C", seed=37), x0 + 10.2, y0 + 0.55, "S", "snake plant", col)
    put(P.plant(col, "snake", 1.0, "#D9D2C6", seed=19), x0 + 0.45, y0 + 0.5, "S", "snake plant", col)
    put(P.plant(col, "fig", 1.85, "#D9D2C6", seed=23), x0 + 7.9, y1 - 0.5, "S", "fig", col)
    put(P.plant(col, "snake", 0.9, "#2E2D2B", seed=31), x0 + 10.2 - 1.6, y1 - 0.4, "S", "snake plant", col)


def company(col, room, plan, design, style):
    """Money, legal, subscriptions and key dates: a filing cabinet each, round the founder's table."""
    x0, x1, y0, y1 = bounds(room)
    run_y = y0 + 4.4  # four cabinets in a run on the side wall, 20 mm apart: money, legal, subscriptions, key dates
    for k in range(4):
        put(P.filing_cabinet(col, 0.55, 0.45, 1.02, drawers=3, title=("money", "legal", "subscriptions", "key dates")[k]),
            x0 + 0.225, run_y + (k - 1.5) * 0.575, "E", "filing cabinet", col, live="cabinet", slot={"k": k, "w": 0.55, "d": 0.45, "h": 1.02})
    tx, ty = (x0 + x1) / 2 + 0.45, y0 + 4.3
    put(P.rug(col, 3.7, 2.9, "#B9AF9F"), tx, ty, "E", "rug", col)
    put(P.table(col, 2.2, 1.0, 0.74, top="oak", legs="black", style="sled", tone="#C9A882"), tx, ty, "E", "table", col)
    rnd = random.Random(9)
    m, look = who(design, "COMPANY")
    for i in range(3):
        y = ty - 0.75 + i * 0.75
        for side, face in ((-1, "E"), (1, "W")):
            pulled = {(0, -1): 0.16, (2, 1): 0.13}.get((i, side), 0.0)  # two left pushed back from the table
            off, dy = 0.8 + rnd.uniform(0.05, 0.12) + pulled, rnd.uniform(-0.05, 0.05)
            turn = math.radians(rnd.choice((-1, 1)) * rnd.uniform(3, 6))
            if m is not None and m["seat"] == [i, side]:  # turned on the chair towards the window, reading
                off, turn = 0.69, math.radians(m.get("turn", 0))  # back in the chair
                put(people.person(col, look, "read", seat=0.47, table=0.74, reach=off - 0.5 + 0.12, seed=3),
                    tx + side * off, y + dy, face, "person", col, turn=turn)
            put(P.shell_chair(col, "#C9BBA6"), tx + side * off, y + dy, face, "chair", col, turn=turn)
    put(P.pendant_linear(col, 1.6, 3.0 - (0.74 + 0.75), color="#FFC890"), tx, ty, "E", "light", col)
    put(P.notebook(col, "#2F3B36"), tx + 0.15, ty + 0.55, "S", "notebook", col, z=0.74, turn=0.2)
    put(P.laptop(col, open_=False), tx, ty - 0.85, "S", "laptop", col, z=0.74, turn=0.08)
    for k, tone in enumerate(("#2F3B36", "#C9B79C")):  # lever-arch files, lying flat, a label on each spine
        f = [P.rbox("lever arch file", (-0.143, -0.16, 0.0), (0.143, 0.16, 0.072), col, M.matte(tone, 0.7), 0.004),
             kit.box("spine label", (0.1435, -0.06, 0.02), (0.1445, 0.06, 0.052), col, M.matte("#F4F0E8", 0.8))]
        put(f, tx + 0.05, ty - 0.62, "S", "file", col, z=0.74 + k * 0.073, turn=0.1 + k * 0.12)  # beside her, not in front
    put(P.notebook(col, "#8C5A3C"), tx - 0.2, ty + 0.15, "S", "notebook", col, z=0.74, turn=-0.3)
    put(P.pen(col), tx - 0.05, ty + 0.2, "S", "pen", col, z=0.74, turn=0.9)
    put(P.tumbler(col), tx + 0.22, ty + 0.78, "S", "glass", col, z=0.74)
    put(P.plant(col, "fig", 1.6, "#D9D2C6", seed=47), x0 + 0.35, y0 + 2.15, "S", "fig", col)
    put(P.art(col, 0.9, 1.0, ("#ECE5D8", "#7E8B74", "#2E3B35", "#C9A57B"), 5.3, "blobs", "oak"), x0, run_y, "E", "art", col, z=1.65)
    put(P.table_lamp(col), x0 + 0.225, run_y + 0.86, "E", "lamp", col, z=1.02)
    # the reading corner by the door, out of the photographer's corner opposite (style.json's camera stands there)
    if design.get("all_doors_open"):  # the live floor: its door stands open, so the corner moves to the far wall, out of the way in
        put(P.lounge_chair(col, "#8E5B32", "leather"), x1 - 0.85, y1 - 1.15, toward(-1.0, -1.0), "leather chair", col)
        put(P.floor_lamp(col, 1.5), x1 - 0.35, y1 - 0.5, "S", "floor lamp", col)
    else:
        put(P.lounge_chair(col, "#8E5B32", "leather"), x0 + 0.85, y1 - 1.15, toward(1.0, -1.0), "leather chair", col)
        put(P.floor_lamp(col, 1.5), x0 + 0.35, y1 - 0.5, "S", "floor lamp", col)
    put(P.plant(col, "fig", 2.0, "#D9D2C6", seed=43), x1 - 0.5, y0 + 0.65, "S", "fig", col)


def websites(design):
    """The company's websites from its work file ("presence", type website): lit when live, dark when planned."""
    here = os.path.dirname(os.path.abspath(__file__))
    f = design.get("moment", {}).get("work")
    if not f:
        return []
    return [p for p in json.load(open(os.path.join(here, "..", "..", f))).get("presence", []) if p.get("type") == "website"]


def reception(col, room, plan, design, style):
    """The lobby's hall: the receptionist at the desk, in the sun (sun/place_in_sun.py put the desk there); the
    company's name and mission on an oak wall behind them, its websites on a row of screens under the name; and
    somewhere to wait by the east window."""
    x0, x1, y0, y1 = bounds(room)
    dx, dy, dd, low = 11.25, 4.85, 0.85, 1.0  # the counter's middle and depth (design-lobby.json "subjects" follows it)
    put(P.reception_counter(col, 3.0, dd, 1.05, low=low, low_h=0.76, tone="#6A5543"), dx, dy, "S", "reception counter", col)  # walnut-dark oak, against the pale slats
    back = dy + dd / 2  # the worktop's back edge, on the receptionist's side
    m, look = who(design, "RECEPTION")
    px = dx + 1.5 - low / 2  # at the lowered end, where a visitor in a wheelchair is met, and the camera sees them
    turn = math.radians(m.get("turn", 0)) if m else 0.0
    if m is not None:  # seated at the worktop, as at a desk upstairs: hands on the top, eyes on the screen
        put(people.person(col, look, "desk", seat=0.52, table=0.76, reach=0.345, seed=identity_seed(m),
                          look_to=math.radians(m.get("look", 0)), hands=m.get("hands", "table"), moving=m.get("moving", 0.0)),
            px, back + 0.445, "S", "person", col, turn=turn)
    put(P.task_chair(col, "#3F4743"), px, back + 0.4, "S", "chair", col, turn=turn, live="person")  # the live building seats its own
    SLOTS.append({"kind": "person", "at": [round(px, 3), round(back + 0.445, 3), 0.0], "rot": round(FACE["S"] + turn, 4), "seat": 0.52, "table": 0.76})  # where the live receptionist sits
    mx, my = dx + 0.38, dy + 0.12  # the screen on the high part's worktop, to her right hand's other side
    put(P.monitor(col, 0.55, on="wallpaper"), mx, my, "N", "screen", col, z=0.75, turn=-math.atan2(px - mx, back + 0.445 - my))
    put(P.keyboard(col), px - 0.12, back - 0.2, "N", "keyboard", col, z=0.76, turn=-0.45)
    put(P.mouse(col), px + 0.2, back - 0.18, "N", "mouse", col, z=0.76)
    put(P.notebook(col, "#2F3B36"), px + 0.3, dy - 0.15, "S", "notebook", col, z=0.76, turn=0.2)
    put(P.pen(col), px + 0.22, dy - 0.12, "S", "pen", col, z=0.76, turn=1.1)
    put(P.carafe(col), dx - 1.22, dy - 0.27, "S", "carafe", col, z=1.05)  # water for visitors, on the ledge
    put(P.tumbler(col), dx - 1.05, dy - 0.31, "S", "glass", col, z=1.05)
    put(P.tumbler(col), dx - 0.98, dy - 0.24, "S", "glass", col, z=1.05)
    for k in (-1, 1):  # two rings of light over the counter
        put(P.pendant_ring(col, 0.45, 2.55, design["heights"]["ceiling"]), dx + k * 0.8, dy, "S", "ring light", col)

    # the name wall: free-standing, oak slats on a dark band, the path to the lift round its west end
    wy, ww, wh = 7.45, 4.6, design["heights"]["ceiling"]
    put([kit.box("name wall", (-ww / 2, 0.0, 0.0), (ww / 2, 0.16, wh), col, M.plaster())], dx, wy, "S", "name wall", col)
    put(P.slat_wall(col, ww, wh, slat=0.03, gap=0.012, depth=0.03, tone="#B48E66", vary=0.05, grain=0.08), dx, wy, "S", "slats", col)
    bz0, bz1 = 2.42, 2.98
    put([P.rbox("name band", (-1.7, -0.06, bz0), (1.7, -0.034, bz1), col, M.matte("#24211E", 0.7), 0.004)], dx, wy, "S", "name band", col)
    org = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", design["moment"]["company"]))) if design.get("moment", {}).get("company") else {}
    put(P.letters(col, org.get("company", "").upper(), 0.24, "#C9A46A", 0.014), dx, wy - 0.06, "S", "name", col, z=bz0 + 0.24,
        live="sign", slot={"band": [3.4, round(bz1 - bz0, 3)], "band_z": bz0, "name_size": 0.24, "mission_size": 0.135, "color": "#C9A46A"})
    if org.get("mission"):
        put(P.letters(col, org["mission"], 0.135, "#C9A46A", 0.008), dx, wy - 0.06, "S", "mission", col, z=bz0 + 0.06, live="sign")
    sites = websites(design)
    sw, gap = 0.95, 0.11
    for k, site in enumerate(sites):  # a screen for each website, in a row under the name; a planned one is still dark
        sx = dx + (k - (len(sites) - 1) / 2) * (sw + gap)
        live = site.get("status") == "Live"
        put(P.site_screen(col, sw, 0.56, seed=k, on=live), sx, wy - 0.034, "S", "website " + site["id"], col, z=1.62,  # clear of her head
            live="screens", slot={"w": sw, "h": 0.56, "gap": gap, "row_w": 4.3, "middle": [dx, round(wy - 0.034, 3)]} if k == 0 else None)

    # somewhere to wait, along the east wall: a sofa with its back to it, two chairs drawn up across a low table
    wx, wyy = x1 - 0.5, 3.7
    put(P.rug(col, 2.7, 3.1, "#B9AF9F"), wx - 0.95, wyy, "S", "rug", col)
    put(P.sofa(col, 2.2, 0.9, "#CFC8BC", legs="black", cushions=("#3A3835", "#B5603F")), wx, wyy, "W", "sofa", col)
    put(P.table(col, 0.6, 0.6, 0.38, top="stone", style="plinth", round_=True), wx - 1.05, wyy, "S", "coffee table", col)
    put(P.book_stack(col, 3, seed=14), wx - 1.0, wyy + 0.05, "S", "books", col, z=0.38, turn=0.5)
    for k, cyy in enumerate((wyy - 0.62, wyy + 0.62)):
        put(P.lounge_chair(col, "#8E5B32", "leather"), wx - 2.0, cyy, toward(1.0, -0.3 * (k * 2 - 1)), "lounge chair", col)
    put(P.plant(col, "fig", 2.0, "#D9D2C6", seed=67), x1 - 0.45, y1 - 0.55, "S", "fig", col)
    put(P.art(col, 1.4, 1.0, ("#ECE5D8", "#C46A3C", "#2E3B35", "#D9B98C"), 9.1, "bands", "black"), x1, wyy, "W", "art over sofa", col, z=1.55)
    put(P.plant(col, "fig", 1.9, "#E3DDD3", seed=71), x0 + 0.45, y0 + 0.55, "S", "fig", col)
    put(P.plant(col, "snake", 1.0, "#2E2D2B", seed=73), dx - ww / 2 - 0.35, wy + 0.1, "S", "snake plant", col)
    put(P.plant(col, "fig", 2.1, "#D9D2C6", seed=79), dx + ww / 2 + 0.55, wy - 0.1, "S", "fig", col)
    # a mat inside the doors, and art on the west wall by the door to social media
    put([P.rbox("entrance mat", (-1.2, -0.0, -0.006), (1.2, 1.6, 0.006), col, M.fabric("#3A3835", 1.2, 0.3, 0.8), 0.003)], 12.3, y0, "S", "mat", col)
    SLOTS.append({"kind": "entrance", "at": [12.3, round(y0 + 0.8, 3), 0.0], "rot": 0.0})  # where a walk through the front door begins
    put(P.art(col, 1.1, 1.4, ("#ECE5D8", "#7E8B74", "#2E3B35", "#C9A57B"), 8.3, "blobs", "oak"), x0, 7.65, "E", "art", col, z=1.55)  # between the door and the corner, in the photograph
    put(P.plant(col, "fig", 1.9, "#E3DDD3", seed=83), x0 + 0.45, 4.8, "S", "fig", col)  # by the door to social media


# ---------- the basement ----------

def library(col, room, plan, design, style):
    """The Library of third-party code, the length of the west wing: a book on the shelves for each piece of code
    the company uses or has looked at (the live building puts them there), long reading tables under pendants,
    low cabinets under the high windows onto the light well, a reading corner at each end."""
    x0, x1, y0, y1 = bounds(room)
    H = design["heights"]["ceiling"]
    # the shelves along the east wall, south of the door in from the corridor
    for k, yy in enumerate((1.5, 3.05, 4.6, 6.15)):
        put(P.bookcase(col, 1.5, 2.4, 0.34, 2, 6, tone="#A9825A", seed=81 + k), x1 - 0.34, y0 + yy, "W", "shelves of third-party code", col,
            live="shelves", slot={"w": 1.5, "h": 2.4, "d": 0.34, "cols": 2, "rows": 6})
    # low oak cabinets under the west windows, with lamps lit and a few things on them
    for k, yy in enumerate((3.75, 8.5, 13.0)):
        put(P.sideboard(col, 1.8, 0.45, 0.72, tone="#A9825A", legs=False), x0 + 0.225, yy, "E", "low cabinet", col)
        put(P.table_lamp(col, 0.46, "#D9CBB2", lit=True), x0 + 0.24, yy - 0.55, "E", "lamp", col, z=0.72)
        put(P.plant(col, "snake", 0.45 + 0.08 * k, "#E3DDD3" if k % 2 else "#2E2D2B", seed=60 + k, pot_h=0.16), x0 + 0.24, yy + 0.5, "E", "plant", col, z=0.72)
    # two long reading tables down the middle, a pendant over each, chairs either side
    for k, ty in enumerate((y0 + 4.4, y0 + 11.6)):
        tx = (x0 + 0.45 + x1 - 0.34) / 2
        put(P.rug(col, 3.6, 2.6, "#7C5A44"), tx, ty, "E", "rug", col)
        put(P.table(col, 2.6, 1.0, 0.75, top="oak", legs="oak", style="four", tone="#B08A62"), tx, ty, "E", "reading table", col)
        for i in range(3):
            yy = ty - 0.85 + i * 0.85
            put(P.shell_chair(col, "#5D4B3C", tone="#A9825A"), tx - 0.72, yy, "E", "chair", col, turn=0.05 * (i - 1))
            put(P.shell_chair(col, "#5D4B3C", tone="#A9825A"), tx + 0.72, yy, "W", "chair", col, turn=-0.04 * (i - 1))
        put(P.pendant_linear(col, 1.8, 3.0 - (0.75 + 0.85), H, "#FFE2BC"), tx, ty, "E", "pendant", col)
        put(P.notebook(col, "#2F3B36", 0.15, 0.22, open_=True), tx - 0.25, ty - 0.6 + k * 0.4, "E", "open notebook", col, z=0.75, turn=0.2)
        put(P.mug(col, "#E9E2D6"), tx + 0.3, ty + 0.4 - k * 0.7, "E", "mug", col, z=0.75)
        put(P.pen(col), tx - 0.1, ty - 0.3 + k * 0.4, "E", "pen", col, z=0.75, turn=0.5)
    # the south end: two leather chairs and a lamp, turned to each other
    put(P.rug(col, 2.6, 1.8, "#C9B79C"), (x0 + x1) / 2 - 0.2, y0 + 1.25, "S", "rug", col)
    put(P.lounge_chair(col, "#7A4A2A", "leather"), x0 + 1.25, y0 + 1.15, toward(1.0, 0.3), "leather chair", col)
    put(P.lounge_chair(col, "#7A4A2A", "leather"), x0 + 3.55, y0 + 1.15, toward(-1.0, 0.3), "leather chair", col)
    put(P.table(col, 0.45, 0.45, 0.5, top="black", legs="black", style="pedestal", round_=True), x0 + 2.4, y0 + 0.85, "S", "side table", col)
    put(P.floor_lamp(col, 1.5), x0 + 0.45, y0 + 0.45, "S", "floor lamp", col)
    # the north end: a sofa against the north wall, a low table, armchairs, plants
    put(P.rug(col, 3.4, 2.4, "#6B3F34"), (x0 + x1) / 2, y1 - 1.6, "S", "rug", col)
    put(P.sofa(col, 2.4, 0.95, "#D8CDBD", legs="none"), (x0 + x1) / 2, y1 - 0.55, "S", "sofa", col)
    put(P.table(col, 1.1, 0.6, 0.38, top="oak", legs="oak", style="four", tone="#A9825A"), (x0 + x1) / 2, y1 - 1.75, "S", "low table", col)
    put(P.lounge_chair(col, "#8A5F3C", "leather"), x0 + 0.9, y1 - 2.6, toward(1.0, 0.6), "armchair", col)
    put(P.floor_lamp(col, 1.5), x1 - 0.4, y1 - 0.4, "S", "floor lamp", col)
    put(P.plant(col, "fig", 1.9, "#D9D2C6", seed=63), x0 + 0.45, y1 - 0.45, "S", "fig", col)
    put(P.plant(col, "fig", 1.6, "#A8674A", seed=64), x1 - 0.45, y0 + 7.6, "S", "fig", col)
    # art on the east wall north of the door, and on the north wall over the sofa
    put(P.art(col, 1.2, 0.9, ("#ECE5D8", "#7E8B74", "#2E3B35", "#C9A57B"), 6.2, "blobs", "oak"), x1, y1 - 3.6, "W", "art", col, z=1.5)
    put(P.art(col, 1.6, 0.8, ("#E9E1D3", "#C46A3C", "#2E3B35", "#D9B98C"), 2.7, "blobs", "black"), (x0 + x1) / 2, y1, "S", "art", col, z=1.45)


def machine_room(col, room, plan, design, style):
    """One shared machine's room: the machine in a rack against the side wall (the live building puts it there and
    lights it when it's on or busy), a crash cart beside it, a workbench under the high window with a pegboard of
    tools, a tool chest, wire shelving of spares and archive boxes, a cable tray from the rack to the door, an air
    conditioner, painted pipes, and LED battens on the ceiling."""
    x0, x1, y0, y1 = bounds(room)
    H = design["heights"]["ceiling"]
    seed = int(x0 * 10)
    rnd = random.Random(seed)
    rx, ry = x0 + 0.52, y0 + 4.6
    put(P.server_rack(col, lit=True, seed=seed), rx, ry, "E", "the machine", col,
        live="machine", slot={"w": 0.6, "d": 1.0, "h": 2.0})
    put([P.rbox("ups", (-0.22, -0.32, 0), (0.22, 0.32, 0.62), col, M.matte("#25272B", 0.4, 0.3), 0.01)], rx - 0.08, ry + 0.95, "E", "ups", col)
    put(P.crash_cart(col), rx + 1.3, ry - 1.0, toward(-1.0, 0.4), "crash cart", col)
    # the workbench under the window, a pegboard above it, a screen, keyboard, laptop, toolbox
    bx, by = (x0 + x1) / 2 - 0.2, y0 + 0.45
    put(P.workbench(col, 2.2, 0.72, 0.9), bx, by, "N", "workbench", col)
    put(P.monitor(col, 0.55, on=False), bx - 0.45, by + 0.12, "N", "screen", col, z=0.9)
    put(P.keyboard(col), bx - 0.45, by - 0.12, "N", "keyboard", col, z=0.9)
    put(P.laptop(col, open_=False), bx + 0.35, by - 0.02, "N", "laptop", col, z=0.9, turn=0.15)
    put([P.rbox("toolbox", (-0.22, -0.11, 0), (0.22, 0.11, 0.16), col, M.matte("#B0352B", 0.45), 0.01)], bx + 0.8, by + 0.05, "N", "toolbox", col, z=0.18)
    put(P.task_chair(col, "#3F4743"), bx - 0.4, by + 0.85, "N", "chair", col, turn=rnd.uniform(-0.5, 0.5))
    put(P.tool_cabinet(col, 0.7, 0.46, 1.0, rnd.choice(["#B32A22", "#2D4A6B", "#3C4148"])), bx + 1.65, y0 + 0.35, "N", "tool chest", col)
    # a warm lamp low over the bench, so the work there is lit and the room has a pool of light and shadow
    put(P.pendant_cone(col, 0.19, H - 1.85, H, "#2B2E33"), bx - 0.1, by + 0.05, "N", "bench lamp", col)
    # a steel table in the middle for whatever is being tested or mended: an open case, a meter, a coil of cable
    mx, my = (x0 + x1) / 2 + 0.6, y0 + 3.6
    put(P.workbench(col, 1.6, 0.8, 0.86, tone="#9C8466"), mx, my, "E", "test table", col)
    put([P.rbox("open case", (-0.1, -0.24, 0), (0.1, 0.24, 0.44), col, M.matte("#2A2D33", 0.4, 0.4), 0.004),
         kit.box("board", (-0.098, -0.2, 0.05), (-0.09, 0.2, 0.4), col, M.matte("#2F5A44", 0.5))], mx - 0.1, my + 0.35, "E", "open case", col, z=0.86, turn=0.1)
    put([P.rbox("meter", (-0.05, -0.09, 0), (0.05, 0.09, 0.04), col, M.matte("#E0A21B", 0.4), 0.008)], mx + 0.2, my - 0.4, "E", "meter", col, z=0.86, turn=-0.3)
    ring = [(0.12 * math.cos(t * 2 * math.pi / 24), 0.12 * math.sin(t * 2 * math.pi / 24), 0.02) for t in range(25)]
    put([P.tube("cable coil", ring, 0.015, col, M.matte("#1A3A6B", 0.5), 8)], mx + 0.15, my - 0.05, "E", "cable", col, z=0.86)
    put(P.laptop(col, open_=True), mx - 0.05, my - 0.35, toward(0.0, -1.0), "laptop open", col, z=0.86, turn=0.2)
    put(P.stool(col, 0.65, "#A9825A"), mx + 0.7, my + 0.2, "W", "stool", col, turn=rnd.uniform(-0.6, 0.6))
    # steel shelving of labelled parts bins on the west wall, north of the machine
    for k, yy in enumerate((y0 + 6.65, y0 + 7.65)):
        put(P.bin_shelving(col, 0.98, 0.45, 1.9, 5, seed=seed + 7 * k), x0 + 0.23, yy, "E", "bin shelving", col)
    # a pegboard of tools on the west wall, south of the rack
    put(P.pegboard(col, 1.3, 0.8, seed=seed), x0, y0 + 2.2, "E", "pegboard", col, z=1.05)
    # wire shelving along the east wall, archive boxes stacked on the floor beside it
    for k, yy in enumerate((y0 + 1.9, y0 + 3.2, y0 + 4.5)):
        put(P.wire_shelving(col, 1.2, 0.45, 1.8, 5, seed=seed + k), x1 - 0.23, yy, "W", "shelving", col)
    for k in range(3):
        put([P.rbox("archive box", (-0.2, -0.16, 0), (0.2, 0.16, 0.28), col, M.matte(rnd.choice(["#C9B590", "#BFA982", "#D3C4A5"]), 0.8), 0.006)],
            x1 - 0.3, y0 + 5.5 + (k % 2) * 0.05, "W", "box", col, z=0.28 * k, turn=rnd.uniform(-0.08, 0.08))
    put([P.rbox("archive box", (-0.2, -0.16, 0), (0.2, 0.16, 0.28), col, M.matte("#C9B590", 0.8), 0.006)], x1 - 0.75, y0 + 5.6, "W", "box", col, turn=0.2)
    # a cable tray from over the rack to over the door, under the ceiling
    put(P.cable_tray(col, (x1 - 0.6) - (rx + 0.2), 0.3), (rx + 0.2 + x1 - 0.6) / 2, ry, "S", "cable tray", col, z=H - 0.35)
    # the air conditioner high on the east wall, a fire extinguisher by the door, a step ladder against the north wall
    put([P.rbox("air conditioner", (-0.45, -0.12, 0), (0.45, 0.0, 0.3), col, M.matte("#F1EFEA", 0.35), 0.03),
         kit.box("vent", (-0.4, -0.125, 0.03), (0.4, -0.115, 0.06), col, M.matte("#B9B6B0", 0.5))], x1, y0 + 6.6, "W", "air conditioner", col, z=2.35)
    put([kit.cylinder("extinguisher", Vector((0, 0, 0.3)), 0.08, 0.5, col, M.matte("#B32A22", 0.3, coat=0.4), 32, bevel=0.02),
         kit.cylinder("extinguisher head", Vector((0, 0, 0.6)), 0.03, 0.1, col, M.matte("#1C1C1C", 0.4), 16)], x1 - 0.2, y1 - 0.25, "S", "extinguisher", col)
    alu = M.steel("#C4C6C8", 0.35)
    ladder = [P.rbox("ladder rail", (-0.22, -0.02, 0), (-0.19, 0.02, 1.6), col, alu, 0.006), P.rbox("ladder rail", (0.19, -0.02, 0), (0.22, 0.02, 1.6), col, alu, 0.006)]
    ladder += [P.rbox("ladder step", (-0.2, -0.05, z), (0.2, 0.05, z + 0.025), col, alu, 0.004) for z in (0.3, 0.6, 0.9, 1.2)]
    put(ladder, x0 + 0.6, y1 - 0.12, "S", "ladder", col, turn=0.0)
    # a whiteboard on the north wall beside the door, never over it: west of it, past the ladder, where it fits
    door = [g for g in edge_gaps(plan, "h", y1, ("door", "double door", "open")) if g[1] > x0 and g[0] < x1]
    wx = x0 + 2.2
    if door and wx + 0.72 > door[0][0] and wx - 0.72 < door[0][1]:
        lo, hi = x0 + 0.9, door[0][0] - 0.15
        wx = (lo + hi) / 2 if hi - lo >= 1.3 else (door[0][1] + 0.15 + x1 - 0.5) / 2
    put([P.rbox("whiteboard", (-0.6, -0.012, 0), (0.6, 0.0, 0.9), col, M.matte("#F6F6F3", 0.15, coat=0.6), 0.004),
         kit.box("whiteboard frame", (-0.62, -0.006, -0.02), (0.62, 0.004, 0.92), col, M.steel("#B9BCC0", 0.3))], wx, y1, "S", "whiteboard", col, z=1.1)
    # two pipes along the ceiling, painted, end to end
    for k, z in enumerate((H - 0.18, H - 0.32)):
        put([P.tube("pipe", [(0, -(y1 - y0) / 2 + 0.05, 0), (0, (y1 - y0) / 2 - 0.05, 0)], 0.04 - k * 0.01, col, M.matte("#D9D5CC", 0.4), 16)],
            x1 - 0.35 - k * 0.12, (y0 + y1) / 2, "S", "pipe", col, z=z)


# ---------- the founder's office, on the top floor ----------

def office(col, room, plan, design, style):
    """The founder's office: the founder's desk across from the lift doors, the chair behind it facing them and two
    armchairs in front; the assistant at a desk of their own on the left as you step out of the lift (the live
    building seats them); a round table for four under a ring of light; a reading corner with a telescope by the
    glass; the founder's name over the lift doors (the live building writes it)."""
    x0, x1, y0, y1 = bounds(room)
    H = design["heights"]["ceiling"]
    lx = 7.95                                    # the middle of the lift doors
    # the founder's desk and its chairs
    dx, dy = lx, 4.4
    put(P.rug(col, 4.2, 3.6, "#8C7B6A"), dx, dy + 0.6, "S", "rug", col)
    put(P.table(col, 2.6, 1.0, 0.74, top="oak", legs="oak", style="plinth", tone="#C9A882"), dx, dy, "S", "founder's desk", col)
    SLOTS.append({"kind": "desk", "at": [dx, dy, 0.0], "rot": 0.0, "w": 2.6, "d": 1.0, "h": 0.74})
    put(P.task_chair(col, "#4A2E21"), dx, dy - 0.85, "N", "founder's chair", col)
    for k in (-1, 1):
        put(P.lounge_chair(col, "#CBBBA6", "fabric"), dx + k * 0.95, dy + 1.55, toward(-k * 0.25, -1.0), "armchair", col)
    put(P.laptop(col, open_=False), dx + 0.55, dy + 0.05, "S", "laptop", col, z=0.74, turn=0.1)
    put(P.notebook(col, "#4A2E21", 0.16, 0.22), dx - 0.7, dy + 0.05, "S", "notebook", col, z=0.74, turn=-0.15)
    put(P.table_lamp(col, 0.44, "#E8DCC6", lit=True), dx - 1.1, dy - 0.25, "S", "desk lamp", col, z=0.74)
    put(P.pen(col), dx - 0.45, dy + 0.15, "S", "pen", col, z=0.74, turn=0.7)
    # a low cabinet behind the founder, under the glass
    put(P.sideboard(col, 2.4, 0.45, 0.62, tone="#C9A882", legs=False), dx, y0 + 0.5, "N", "credenza", col)
    put(P.plant(col, "snake", 0.55, "#E3DDD3", seed=91, pot_h=0.18), dx - 0.8, y0 + 0.5, "N", "plant", col, z=0.62)
    put(P.book_stack(col, 3, seed=31), dx + 0.7, y0 + 0.5, "N", "books", col, z=0.62, turn=0.3)
    # the assistant's desk: on the left as you step out of the lift, the assistant facing the way out of it
    ax, ay = 11.55, 8.5
    put(P.table(col, 1.5, 0.7, 0.75, top="oak", legs="black", style="four", tone="#C9A882"), ax - 0.55, ay, "E", "assistant's desk", col)
    # the screen to one side and turned in, so whoever comes to talk sees the assistant, not the back of it
    put(P.monitor(col, 0.55, on=False), ax - 0.7, ay + 0.52, toward(0.7, -0.52), "screen", col, z=0.75)
    put(P.keyboard(col), ax - 0.42, ay + 0.3, "E", "keyboard", col, z=0.75, turn=math.pi / 2)
    put(P.notebook(col, "#2F3B36"), ax - 0.45, ay - 0.35, "E", "notebook", col, z=0.75, turn=0.2)
    put(P.table_lamp(col, 0.4, "#E8DCC6", lit=True), ax - 0.75, ay - 0.6, "E", "lamp", col, z=0.75)
    m, look = who(design, "OFFICE")
    if m is not None:
        put(people.person(col, look, "desk", seat=0.52, table=0.75, reach=0.345, seed=identity_seed(m),
                          look_to=math.radians(m.get("look", 0)), hands=m.get("hands", "table"), moving=m.get("moving", 0.0)),
            ax, ay, "W", "person", col, turn=math.radians(m.get("turn", 0)))
    put(P.task_chair(col, "#3F4743"), ax + 0.05, ay, "W", "chair", col, live="assistant")
    SLOTS.append({"kind": "assistant", "at": [ax, ay, 0.0], "rot": round(FACE["W"], 4), "seat": 0.52, "table": 0.75, "stand": [round(ax - 1.75, 3), ay]})
    put(P.plant(col, "fig", 1.9, "#D9D2C6", seed=93), ax + 0.4, y1 - 0.45, "S", "fig", col)
    # a round table for four under a ring of light, between the desk and the lounge
    tx, ty = 13.6, 3.6
    put(P.rug(col, 3.0, 3.0, "#B9AF9F", round_=True), tx, ty, "S", "rug", col)
    put(P.table(col, 1.3, 1.3, 0.74, top="stone", style="pedestal", round_=True), tx, ty, "S", "round table", col)
    for k in range(4):
        a = k * math.pi / 2 + math.pi / 4
        put(P.shell_chair(col, "#8C7A66"), tx + math.cos(a) * 0.85, ty + math.sin(a) * 0.85, toward(-math.cos(a), -math.sin(a)), "chair", col)
    put(P.pendant_ring(col, 0.75, 2.45, H), tx, ty, "S", "ring light", col)
    put(P.carafe(col), tx + 0.2, ty + 0.1, "S", "carafe", col, z=0.74)
    put(P.tumbler(col), tx - 0.15, ty + 0.25, "S", "glass", col, z=0.74)
    # the reading corner in the south-west, by the glass: two chairs, a lamp, a telescope
    rx, ry = 2.6, 2.6
    put(P.rug(col, 2.6, 2.2, "#6B3F34"), rx, ry, "S", "rug", col)
    put(P.lounge_chair(col, "#7A4A2A", "leather"), rx - 0.75, ry + 0.4, toward(0.8, -0.6), "leather chair", col)
    put(P.lounge_chair(col, "#8E5B32", "leather"), rx + 0.85, ry + 0.45, toward(-0.8, -0.6), "leather chair", col)
    put(P.table(col, 0.45, 0.45, 0.5, top="black", legs="black", style="pedestal", round_=True), rx + 0.05, ry - 0.2, "S", "side table", col)
    put(P.floor_lamp(col, 1.5), rx - 1.5, ry + 1.1, "S", "floor lamp", col)
    put(P.telescope(col), x0 + 0.9, y0 + 0.9, toward(-0.5, -1.0), "telescope", col)
    for (px, py, h, seed) in ((x0 + 0.45, 5.4, 2.1, 95), (16.4, y0 + 0.5, 2.0, 97), (6.4, y1 - 0.5, 1.7, 99)):
        put(P.plant(col, "fig", h, "#D9D2C6", seed=seed), px, py, "S", "fig", col)
    # the founder's name over the lift doors: the live building writes it
    org = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", design["moment"]["company"]))) if design.get("moment", {}).get("company") else {}
    put(P.letters(col, (org.get("founder", {}).get("name") or "").upper(), 0.2, "#C9A46A", 0.012), lx, y1, "S", "name over the lift", col, z=2.75,
        live="nameplate", slot={"w": 2.4, "h": 0.5, "z": 2.6, "color": "#C9A46A"})


def office_library(col, room, plan, design, style):
    """The founder's library, in the west wing: shelves nearly to the ceiling along the back wall and beside the lift,
    a ladder on its rail, two armchairs by a lamp. The founder's notes hang in a row in front of the back shelves
    (the live building hangs them there)."""
    x0, x1, y0, y1 = bounds(room)
    H = design["heights"]["ceiling"]
    n = 3
    w = (x1 - x0 - 0.1) / n
    for k in range(n):
        put(P.bookcase(col, w, H - 0.25, 0.36, 3, 8, tone="#A9825A", seed=101 + k), x0 + 0.05 + w * (k + 0.5), y1 - 0.36, "S", "shelves", col)
    for k in range(2):
        put(P.bookcase(col, 1.6, H - 0.25, 0.36, 2, 8, tone="#A9825A", seed=111 + k), x1 - 0.36, 11.6 + k * 1.65, "W", "shelves", col)
    alu = M.oak("#A9825A", 26.0, "Z")
    lh = H - 0.35
    lean = 0.55
    lad = [P.tube("ladder rail", [(sx, 0.0, 0.0), (sx, lean, lh)], 0.02, col, alu, 10) for sx in (-0.22, 0.22)]
    lad += [P.tube("ladder rung", [(-0.22, lean * z / lh, z), (0.22, lean * z / lh, z)], 0.014, col, alu, 8) for z in [0.3 + 0.32 * i for i in range(int((lh - 0.4) / 0.32))]]
    lad.append(P.tube("rail", [(-2.0, lean + 0.04, lh + 0.02), (2.0, lean + 0.04, lh + 0.02)], 0.012, col, M.steel("#B89B62", 0.35), 10))
    put(lad, x0 + 1.5, y1 - 0.36 - lean - 0.05, "S", "ladder", col)
    cx, cy = (x0 + x1) / 2, 11.4
    put(P.rug(col, 3.0, 2.2, "#7C5A44"), cx, cy, "S", "rug", col)
    for k in (-1, 1):
        put(P.lounge_chair(col, "#8A5F3C" if k < 0 else "#B5603F", "leather"), cx + k * 0.95, cy, toward(-k * 1.0, 0.25), "armchair", col)
    put(P.table(col, 0.5, 0.5, 0.52, top="oak", legs="black", style="pedestal", round_=True), cx, cy + 0.1, "S", "side table", col)
    put(P.book_stack(col, 2, seed=41), cx, cy + 0.1, "S", "books", col, z=0.52, turn=0.4)
    put(P.floor_lamp(col, 1.5), cx - 1.75, cy + 0.6, "S", "floor lamp", col)
    # where the notes hang: a row at eye height in front of the back shelves, turned a little to the chairs
    for k in range(8):
        nx = x0 + 0.55 + k * (x1 - x0 - 1.1) / 7
        SLOTS.append({"kind": "note", "at": [round(nx, 3), round(y1 - 1.05, 3), 1.52], "rot": round(math.atan2(cx - nx, 8.0), 4)})


def office_lounge(col, room, plan, design, style):
    """The lounge, east of the office: a curved sofa round a stone table on a round rug, open to the glass; a big
    picture over a sideboard on the back wall."""
    x0, x1, y0, y1 = bounds(room)
    cx, cy = (x0 + x1) / 2 + 0.2, 4.6
    put(P.rug(col, 4.4, 4.4, "#5A4A3E", round_=True), cx, cy, "S", "rug", col)
    put(P.curved_sofa(col, 1.75, 130, 0.95, "#3F5A4F"), cx, cy + 0.15, "S", "curved sofa", col)
    put(P.table(col, 1.3, 1.3, 0.36, top="stone", style="plinth", round_=True), cx, cy - 0.35, "S", "stone table", col)
    put(P.book_stack(col, 3, seed=51), cx - 0.2, cy - 0.3, "S", "books", col, z=0.36, turn=0.4)
    put(P.carafe(col), cx + 0.3, cy - 0.45, "S", "vase", col, z=0.36)
    put(P.sideboard(col, 2.8, 0.48, 0.72, tone="#A9825A"), cx, y1 - 0.26, "S", "sideboard", col)
    put(P.art(col, 2.6, 1.6, ("#E9D9C2", "#D08A52", "#5E6E78", "#2E3B35"), 3.3, "bands", "black"), cx, y1, "S", "picture", col, z=1.15)
    put(P.table_lamp(col, 0.5, "#E8DCC6", lit=True), cx - 1.1, y1 - 0.26, "S", "lamp", col, z=0.72)
    put(P.floor_lamp(col, 1.55), x1 - 0.5, y0 + 0.6, "S", "floor lamp", col)
    for k, (px, py, h) in enumerate(((x1 - 0.5, y1 - 0.5, 2.1), (x0 + 0.5, y0 + 0.5, 1.8))):
        put(P.plant(col, "fig", h, "#D9D2C6", seed=121 + k), px, py, "S", "fig", col)
    put(P.lounge_chair(col, "#CBBBA6", "fabric"), x1 - 1.2, y0 + 1.5, toward(-0.7, 0.7), "chair by the glass", col)


ROOMS = {"GOALS": goals, "CODE": code, "CONVERSATIONS": conversations, "WORK": work, "COMPANY": company, "RECEPTION": reception,
         "LIBRARY": library, "WEST MACHINE ROOM": machine_room, "MIDDLE MACHINE ROOM": machine_room, "EAST MACHINE ROOM": machine_room,
         "OFFICE": office, "OFFICE LIBRARY": office_library, "LOUNGE": office_lounge}


def in_the_sun(design, x, y, h, c, gz):
    """True when a tree's crown (h tall, c across, standing at height gz) would shade the top of what a styled
    room on this floor is for (design.json "subjects"): the light is followed back from each subject's corners
    and middle towards the measured sun, and tested against the crown, an ellipsoid with 0.3 m to spare."""
    here = os.path.dirname(os.path.abspath(__file__))
    d = json.load(open(os.path.join(here, "..", "out", "sun.json")))["sun_direction_plan"]
    n = math.sqrt(sum(v * v for v in d))
    d = [v / n for v in d]
    centre = (x, y, gz + h - 0.8 * c)
    radii = (c + 0.3, c + 0.3, 0.8 * c + 0.3)
    for room in design.get("styled", []):
        for bx0, by0, bx1, by1, bz in design.get("subjects", {}).get(room, []):
            for px, py in ((bx0, by0), (bx1, by0), (bx0, by1), (bx1, by1), ((bx0 + bx1) / 2, (by0 + by1) / 2)):
                q = [(px - centre[0]) / radii[0], (py - centre[1]) / radii[1], (bz - centre[2]) / radii[2]]
                e = [d[i] / radii[i] for i in range(3)]
                a, b, cc = sum(v * v for v in e), 2 * sum(q[i] * e[i] for i in range(3)), sum(v * v for v in q) - 1
                disc = b * b - 4 * a * cc
                if disc >= 0 and (-b + math.sqrt(disc)) / (2 * a) > 0:
                    return True
    return False


def outside(col, design, plan=None):
    """The street a storey below, for the view out: gardens, trees, roads and the neighbours' buildings, well
    back across the streets. Every tree and building is kept under every window's line to the sun (a ray
    rises 0.53 m per metre towards it)."""
    gz = -shell.street_drop(design)
    trees = ((-11, 19, 9, 3.4), (-12, 7, 7.5, 2.8), (9, -12, 9, 3.2), (30, -7, 8, 3.0), (-6, 27, 10, 3.6),
             (33, 6, 9, 3.3), (-8, -10, 8, 3.0), (3, -13, 9.5, 3.4), (16, -12.5, 8.5, 3.0), (24, -13, 7.5, 2.7),
             (36, 14, 8.5, 3.2), (-16, 28, 9, 3.4))
    for k, (x, y, h, c) in enumerate(trees):
        if in_the_sun(design, x, y, h, c, gz):  # on a lower floor a tree can stand in the sun's way: it is left out
            print("TREE LEFT OUT", k, (x, y), flush=True)
            continue
        put(P.tree(col, h, c, seed=k), x, y, "S", "tree", col, z=gz)
    if plan is not None and gz > -1.0:  # on the street: a paved path from the front doors out to the road
        for o in plan["openings"]:
            w = next(w for w in plan["walls"] if w["id"] == o["wall"])
            if o["kind"] == "double door" and w.get("exterior") and abs(o["from"][1] - o["to"][1]) < 1e-6 and o["from"][1] < 1.0:
                a, b = sorted((o["from"][0], o["to"][0]))
                kit.box("paving path", (a - 0.4, -23.0, gz), (b + 0.4, -3.0, gz + 0.02), col, M.stone("#CFC8BC", "#B9B0A2", 0.6, 0.5))
    road = M.asphalt()
    kit.box("west street", (-31, -400, gz), (-21, 400, gz + 0.03), col, road)
    kit.box("south street", (-400, -33, gz), (400, -23, gz + 0.03), col, road)
    walls = ["#D9CFC1", "#C9B8A3", "#B9A089", "#E2DCD2", "#A88E78", "#CBC5BA"]
    blocks = [((-50, -26), (-34, -10), 12), ((-50, -6), (-34, 10), 14), ((-50, 14), (-34, 28), 11), ((-50, 32), (-34, 46), 15),
              ((-24, -52), (-8, -36), 13), ((-4, -52), (10, -36), 11), ((14, -52), (28, -36), 15), ((32, -52), (46, -36), 12),
              ((46, -16), (60, -2), 16), ((46, 2), (60, 18), 14), ((4, 38), (20, 52), 12), ((24, 38), (38, 52), 16)]
    for k, ((ax, ay), (bx, by), hh) in enumerate(blocks):
        P.building(col, (ax, ay), (bx, by), hh, walls[k % len(walls)], 3.0 + 0.4 * (k % 3), 3.2 + 0.2 * (k % 2), gz)
        kit.box(f"neighbour {k} parapet", (ax - 0.1, ay - 0.1, gz + hh), (bx + 0.1, by + 0.1, gz + hh + 0.6), col, M.outdoor(walls[(k + 2) % len(walls)]))
    rnd = random.Random(99)
    far = M.foliage("#526540")
    for k in range(60):  # far off, softened by the haze: a band of tree crowns and roofs all round
        a = 2 * math.pi * k / 60 + rnd.uniform(-0.04, 0.04)
        r = rnd.uniform(110, 200)
        x, y = 12 + math.cos(a) * r, 8 + math.sin(a) * r
        if False:
            bm = bmesh.new()
            rad = rnd.uniform(4, 7)
            bmesh.ops.create_icosphere(bm, subdivisions=3, radius=rad)
            bmesh.ops.translate(bm, vec=(x, y, gz + rad * 0.9), verts=bm.verts)
            kit.obj_from_bmesh("far tree", bm, col, far, smooth=True)
        else:
            w, d, hh = rnd.uniform(12, 30), rnd.uniform(10, 20), rnd.uniform(9, 24)
            kit.box("far block", (x - w / 2, y - d / 2, gz), (x + w / 2, y + d / 2, gz + hh), col, M.facade(rnd.choice(walls), bay=3.2, storey=3.3))


def furnish(plan, design, styles):
    col = kit.collection("furniture")
    for r in plan["rooms"]:
        fn = ROOMS.get(design.get("furnish", {}).get(r["name"], r["name"]))  # a floor can furnish a room its own way
        if fn and r["name"] in design["styled"]:
            fn(col, r, plan, design, styles.get(r["name"], {}))
            finish(col, plan, design, r, styles.get(r["name"], {}))
        elif design.get("lit", {}).get(r["name"]):  # a room left unfurnished still gets its ceiling lights (below ground)
            finish(col, plan, design, r, {"lights": design["lit"][r["name"]]})
    outside(kit.collection("garden"), design, plan)
