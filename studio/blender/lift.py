"""The lift: a real one, where the plan draws a plain door into LIFT AND STAIRS.

From the corridor: a portal of honed dark stone round a doorway lined in brushed steel, an indicator strip over
it with its up and down lamps, and a call button beside it. In the doorway, two brushed steel leaves that part in
the middle. Each leaf is a group of its own ("LIFT DOOR WEST", "LIFT DOOR EAST"), so the live building can slide
them open as you come. Behind them, the car: walnut panels on its sides, pale travertine on its back wall over a
walnut dado, a bronze handrail round three sides, a dark stone floor, a lit ceiling panel in a bronze frame, and
the floor buttons on a steel plate beside the door.

Every floor has its lift in the same place: the core between x 6.06 and 9.94 m, behind the wall at y 10.72 m,
so one lift serves the whole building. Plan metres: x east, y north (into the core), z up.
"""
import bpy  # noqa: F401  (the materials and meshes below need Blender)

import kit
import materials as M

LIFT_ROOM = "LIFT AND STAIRS"
X0, X1 = 7.5, 8.5                  # the doorway, 1.0 m clear between the portal's piers
HEAD = 2.2                         # its head
CAR = (7.2, 8.8, 10.95, 12.45)     # the car's inside: x0, x1, y0 (behind the leaves), y1
CAR_H = 2.35                       # its ceiling
LEAF_Y = (10.868, 10.896)          # the leaves: just behind the wall, which runs to y 10.862
LEAF_W = 0.53                      # each leaf; they overlap the doorway's sides by 3 cm
SLIDE = 0.5                        # how far each slides open (the live building does the same)
DOORS = ("LIFT DOOR WEST", "LIFT DOOR EAST")


@M.material("brushed")
def brushed(g, color="#B4B7BA", streak=0.05, along="Z"):
    """Brushed steel: fine streaks along `along`. Baked as a matte surface of its own colour (bake.py), so the
    streaks are what tell it from paint."""
    m = g.coords("Object", (260, 260, 1.5) if along == "Z" else (1.5, 260, 260))
    n = g.n("ShaderNodeTexNoise", Scale=1.0, Detail=8.0, Roughness=0.75)
    g.link(m, "Vector", n, "Vector")
    col = g.ramp(n, "Fac", [(0.3, M._shade(color, streak)), (0.5, color), (0.7, M._shade(color, -streak))])
    g.link(col, "Color", g.bsdf, "Base Color")
    g.set(**{"Metallic": 1.0, "Roughness": 0.32, "Anisotropic": 0.5})


def adopt(plan, rooms_beside):
    """The plan with the door into the lift room made the lift's doorway. False when the plan has no lift room."""
    for o in plan["openings"]:
        if o["kind"] not in ("door", "double door"):
            continue
        sides = [r["name"] if r else None for r in rooms_beside(plan, o)]
        if LIFT_ROOM in sides and None not in sides:
            y = o["from"][1]
            o.update(kind="lift", width=X1 - X0)
            o["from"], o["to"] = [X0, y], [X1, y]
            return True
    return False


def entrance(o, t, c, col, opened=False, ceiling=3.0):
    """The corridor's side of the lift: the portal, the doorway's steel lining, the indicator, the call button, and
    the two leaves (open in a photo when opened)."""
    face = c - t / 2                     # the corridor's face of the wall
    back = c + t / 2                     # the car's side
    stone = M.stone("#3E3B38", "#2C2A28", 0.42, 2.6)
    steel = brushed()
    dark_glass = M.matte("#0E0E10", 0.08)
    lamp = M.glow("#FFE9C9", 6.0)
    proud = 0.025
    # the portal: two piers and a head of dark stone standing 25 mm proud of the plaster
    kit.box("lift portal west", (X0 - 0.36, face - proud, 0.0), (X0, face, HEAD + 0.32), col, stone, 0.003)
    kit.box("lift portal east", (X1, face - proud, 0.0), (X1 + 0.36, face, HEAD + 0.32), col, stone, 0.003)
    kit.box("lift portal head", (X0, face - proud, HEAD), (X1, face, HEAD + 0.32), col, stone, 0.003)
    # the doorway lined in steel through the wall's thickness
    kit.box("lift lining west", (X0, face - proud, 0.0), (X0 + 0.02, back, HEAD), col, steel, 0.002)
    kit.box("lift lining east", (X1 - 0.02, face - proud, 0.0), (X1, back, HEAD), col, steel, 0.002)
    kit.box("lift lining head", (X0, face - proud, HEAD - 0.02), (X1, back, HEAD), col, steel, 0.002)
    kit.box("lift sill", (X0, face - proud, -0.02), (X1, LEAF_Y[1] + 0.004, 0.004), col, brushed("#A9ACAF", 0.04, "X"))
    # over the doorway: a strip of dark glass with the up and down lamps
    mid = (X0 + X1) / 2
    kit.box("lift indicator", (mid - 0.16, face - proud - 0.006, HEAD + 0.1), (mid + 0.16, face - proud, HEAD + 0.2), col, dark_glass, 0.003)
    for k, dx in enumerate((-0.05, 0.05)):
        kit.box(f"lift indicator lamp {k}", (mid + dx - 0.018, face - proud - 0.008, HEAD + 0.135), (mid + dx + 0.018, face - proud - 0.006, HEAD + 0.165), col, lamp)
    # a downlight in the ceiling in front of the lift, washing the portal
    kit.cylinder("lift downlight trim", (mid, face - 0.6, ceiling - 0.004), 0.085, 0.008, col, steel, 48, axis="Z")
    kit.cylinder("lift downlight", (mid, face - 0.6, ceiling - 0.009), 0.06, 0.004, col, M.glow("#FFF0DA", 260.0), 48, axis="Z")
    # the call button, on a slim steel plate beside the east pier
    px = X1 + 0.5
    kit.box("lift call plate", (px - 0.045, face - 0.008, 0.95), (px + 0.045, face, 1.25), col, steel, 0.003)
    kit.cylinder("lift call ring", (px, face - 0.009, 1.1), 0.024, 0.004, col, lamp, axis="Y")
    kit.cylinder("lift call button", (px, face - 0.013, 1.1), 0.019, 0.008, col, steel, axis="Y")
    # the two leaves, each a group of its own so the live building can slide it
    shut = {"LIFT DOOR WEST": mid - LEAF_W, "LIFT DOOR EAST": mid}
    for name, x in shut.items():
        if opened:
            x += -SLIDE if name.endswith("WEST") else SLIDE
        leaf = kit.box(name.lower(), (x, LEAF_Y[0], 0.008), (x + LEAF_W, LEAF_Y[1], HEAD - 0.004), col, steel, 0.002)
        leaf["group"] = name
        # the leaf's meeting edge: a thin black seal, so the closed doors read as two
        edge = mid - 0.002 if name.endswith("WEST") else mid
        if opened:
            edge += -SLIDE if name.endswith("WEST") else SLIDE
        seal = kit.box(f"{name.lower()} seal", (edge, LEAF_Y[0] - 0.001, 0.008), (edge + 0.002, LEAF_Y[1] + 0.001, HEAD - 0.004), col, M.matte("#121212", 0.6))
        seal["group"] = name


def car(col):
    """The car, behind the leaves, and the shaft round it."""
    x0, x1, y0, y1 = CAR
    H = CAR_H
    walnut = M.oak("#80603F", 18.0, "Z", 0.07)
    travertine = M.stone("#E4D9C6", "#C7B496", 0.38, 2.2)
    bronze = M.matte("#6E5236", 0.32, 0.85)
    reveal = M.matte("#2A2420", 0.5, 0.6)
    steel = brushed()
    floor = M.stone("#57524C", "#3D3935", 0.4, 3.2)
    light = M.glow("#FFF1DE", 6.0)
    # the shaft: concrete round the car, closing off the rest of the core
    shaft = M.concrete("#8E8A84")
    kit.box("lift shaft west", (x0 - 0.3, 10.862, -0.3), (x0 - 0.25, y1 + 0.3, 3.0), col, shaft)
    kit.box("lift shaft east", (x1 + 0.25, 10.862, -0.3), (x1 + 0.3, y1 + 0.3, 3.0), col, shaft)
    kit.box("lift shaft back", (x0 - 0.3, y1 + 0.25, -0.3), (x1 + 0.3, y1 + 0.3, 3.0), col, shaft)
    kit.box("lift shaft top", (x0 - 0.3, 10.862, CAR_H + 0.1), (x1 + 0.3, y1 + 0.3, 3.0), col, shaft)
    # the car's shell: its walls in a dark reveal colour, which shows in the gaps between the panels
    kit.box("lift car west", (x0 - 0.05, y0 - 0.05, 0.0), (x0, y1 + 0.05, H), col, reveal)
    kit.box("lift car east", (x1, y0 - 0.05, 0.0), (x1 + 0.05, y1 + 0.05, H), col, reveal)
    kit.box("lift car back", (x0, y1, 0.0), (x1, y1 + 0.05, H), col, reveal)
    kit.box("lift car ceiling", (x0 - 0.05, y0 - 0.05, H), (x1 + 0.05, y1 + 0.05, H + 0.08), col, reveal)
    kit.box("lift car floor", (x0, y0 - 0.05, -0.03), (x1, y1, 0.004), col, floor)
    # the front: steel returns either side of the door and a header over it, their faces inside the car at y0
    kit.box("lift car return west", (x0, LEAF_Y[1] + 0.004, 0.0), (X0, y0, H), col, steel, 0.002)
    kit.box("lift car return east", (X1, LEAF_Y[1] + 0.004, 0.0), (x1, y0, H), col, steel, 0.002)
    kit.box("lift car header", (X0, LEAF_Y[1] + 0.004, HEAD), (X1, y0, H), col, steel, 0.002)
    # the sides: three walnut panels each, over a steel kick plate, 8 mm shadow gaps between
    kick = 0.14
    gap = 0.008
    for side, x, inward in (("west", x0, 1), ("east", x1, -1)):
        kit.box(f"lift kick {side}", (min(x, x + inward * 0.012), y0, 0.004), (max(x, x + inward * 0.012), y1, kick), col, steel, 0.001)
        n = 3
        for k in range(n):
            ya = y0 + (y1 - y0) * k / n + gap / 2
            yb = y0 + (y1 - y0) * (k + 1) / n - gap / 2
            kit.box(f"lift panel {side} {k}", (min(x, x + inward * 0.014), ya, kick + gap), (max(x, x + inward * 0.014), yb, H - 0.06), col, walnut, 0.002)
    # the back: a walnut dado to the handrail, travertine over it, a steel kick plate
    kit.box("lift kick back", (x0, y1 - 0.012, 0.004), (x1, y1, kick), col, steel, 0.001)
    kit.box("lift dado back", (x0 + gap, y1 - 0.014, kick + gap), (x1 - gap, y1, 0.86), col, walnut, 0.002)
    kit.box("lift stone back", (x0 + gap, y1 - 0.018, 0.86 + gap), (x1 - gap, y1, H - 0.06), col, travertine, 0.002)
    # the ceiling: a lit panel in a bronze frame
    inset = 0.3
    kit.box("lift ceiling light", (x0 + inset, y0 + inset, H - 0.012), (x1 - inset, y1 - inset, H), col, light)
    for k, (a, b) in enumerate((((x0, y0), (x1, y0 + 0.02)), ((x0, y1 - 0.02), (x1, y1)), ((x0, y0), (x0 + 0.02, y1)), ((x1 - 0.02, y0), (x1, y1)))):
        kit.box(f"lift ceiling trim {k}", (a[0], a[1], H - 0.05), (b[0], b[1], H - 0.03), col, bronze)  # a bronze band round the top of the walls
    for k, (a, b) in enumerate((((x0 + inset - 0.03, y0 + inset - 0.03), (x1 - inset + 0.03, y0 + inset)),
                                ((x0 + inset - 0.03, y1 - inset), (x1 - inset + 0.03, y1 - inset + 0.03)),
                                ((x0 + inset - 0.03, y0 + inset), (x0 + inset, y1 - inset)),
                                ((x1 - inset, y0 + inset), (x1 - inset + 0.03, y1 - inset)))):
        kit.box(f"lift ceiling frame {k}", (a[0], a[1], H - 0.02), (b[0], b[1], H), col, bronze, 0.002)
    # the handrail: a bronze tube round three sides at 0.92 m, on standoffs
    r, z, off = 0.019, 0.92, 0.065
    kit.cylinder("lift rail back", ((x0 + x1) / 2, y1 - off, z), r, (x1 - x0) - 2 * off - 0.02, col, bronze, 32, axis="X")
    for side, x in (("west", x0 + off), ("east", x1 - off)):
        ya, yb = y0 + 0.35, y1 - off
        kit.cylinder(f"lift rail {side}", (x, (ya + yb) / 2, z), r, yb - ya, col, bronze, 32, axis="Y")
        for k, yy in enumerate((ya + 0.06, yb - 0.25)):
            kit.cylinder(f"lift rail {side} standoff {k}", ((x + (x0 if side == 'west' else x1)) / 2, yy, z), 0.008, off, col, bronze, 16, axis="X")
    for k, xx in enumerate((x0 + 0.3, (x0 + x1) / 2, x1 - 0.3)):
        kit.cylinder(f"lift rail back standoff {k}", (xx, y1 - off / 2, z), 0.008, off, col, bronze, 16, axis="Y")
    # the floor buttons: on a steel plate on the east return, facing into the car
    plate_x = (X1 + x1) / 2
    face = y0
    kit.box("lift button plate", (plate_x - 0.075, face, 0.8), (plate_x + 0.075, face + 0.006, 1.62), col, steel, 0.003)
    kit.box("lift button display", (plate_x - 0.05, face + 0.006, 1.46), (plate_x + 0.05, face + 0.01, 1.56), col, M.matte("#0E0E10", 0.08))
    kit.box("lift button display text", (plate_x - 0.02, face + 0.0102, 1.495), (plate_x + 0.02, face + 0.0106, 1.525), col, M.glow("#FFD9A0", 4.0))
    ring = M.glow("#FFE9C9", 3.0)
    for k in range(6):
        zz = 0.9 + k * 0.085
        kit.cylinder(f"lift floor ring {k}", (plate_x, face + 0.0065, zz), 0.019, 0.003, col, ring, 32, axis="Y")
        kit.cylinder(f"lift floor button {k}", (plate_x, face + 0.009, zz), 0.015, 0.008, col, steel, 32, axis="Y")
