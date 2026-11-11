#!/usr/bin/env python3
"""Draws the studio floor's plan as an architect would: walls in solid black, windows, door swings,
furniture in thin grey, room names with their areas, dimensions, a scale bar and a north arrow.

The tracer (trace.py) reads only the picture this makes, never these numbers.

python3 draw_plan.py OUT_DIR           ->  OUT_DIR/plan.svg and OUT_DIR/plan.png (the project floor)
python3 draw_plan.py OUT_DIR lobby     ->  OUT_DIR/plan-lobby.svg and .png (the ground floor below it)
"""
import math
import os
import subprocess
import sys

S = 80                      # pixels per metre on the sheet (1:100 at this size)
X0, YTOP = 220, 180         # where the building's outer corner sits on the sheet
WIDTH, DEPTH = 24.0, 16.0   # the building, outside faces, in metres
EXT, INT = 0.30, 0.12       # wall thicknesses
NORTH = 18.0                # true north is this many degrees clockwise from the sheet's up
SHEET = (2560, 1960)
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def X(x):
    return X0 + x * S


def Y(y):
    return YTOP + (DEPTH - y) * S


# One project's floor, one storey up: every room is one the building fills from that project's data
# (Goals, Work, Conversations, Code, and on this floor the Company office), with the lift and stairs that
# join it to the other floors. No room is here that the project can't use.
NB = 10.57 + EXT / 2         # the core and the north face east of it: clear of the partition at y=11
CORE_E = 9.94 + EXT / 2      # the core's east wall, outside on its north part
# Thick walls as rectangles (x0, y0, x1, y1): the outside, an L with the core and the west rooms reaching north,
# and the core's own thick wall along the corridor.
OUTER = [
    (0, 0, WIDTH, EXT), (0, 0, EXT, DEPTH), (0, DEPTH - EXT, CORE_E + EXT / 2, DEPTH),
    (CORE_E - EXT / 2, NB - EXT / 2, CORE_E + EXT / 2, DEPTH), (6.0 - INT / 2, NB - EXT / 2, WIDTH, NB + EXT / 2),
    (WIDTH - EXT, 0, WIDTH, NB + EXT / 2),
]
# Partitions: (axis, at, start, end) along their centre line, metres.
PARTS = [
    ("v", 6.0, 0.15, 15.85), ("h", 6.0, 0.15, 6.0), ("h", 11.0, 0.15, 6.0),
    ("v", 19.5, 0.15, 9.0), ("h", 9.0, 6.0, 23.85),
]
# Openings: (kind, wall, at, from, to, swing) where wall is ("h"|"v", centre line, thickness); swing is the side
# the leaf opens to (+1 = towards larger y or x) and which end is hinged ("a" = from-end, "b" = to-end).
S_, W_, N_, E_, NE_ = ("h", EXT / 2, EXT), ("v", EXT / 2, EXT), ("h", DEPTH - EXT / 2, EXT), ("v", WIDTH - EXT / 2, EXT), ("h", NB, EXT)
OPEN = [
    ("window", S_, 1.2, 5.2, None),
    ("window", W_, 1.0, 5.0, None),
    ("window", W_, 7.0, 10.0, None),
    ("window", W_, 12.0, 15.0, None),
    ("window", N_, 1.5, 4.5, None),
    ("window", N_, 7.3, 8.7, None),                               # the stair's window
    ("window", S_, 7.0, 10.5, None),
    ("window", S_, 11.5, 15.0, None),
    ("window", S_, 16.8, 18.8, None),
    ("window", S_, 20.3, 23.0, None),
    ("window", E_, 1.5, 7.5, None),
    ("window", E_, 9.3, 10.5, None),
    ("open", ("v", 6.0, INT), 2.0, 3.6, None),                    # goals to work
    ("open", ("h", 9.0, INT), 7.0, 9.0, None),                    # work to corridor
    ("door", ("h", 6.0, INT), 2.5, 3.5, (+1, "a")),               # goals to code
    ("door", ("h", 11.0, INT), 3.5, 4.5, (+1, "b")),              # code to conversations
    ("door", ("v", 6.0, INT), 9.4, 10.4, (+1, "a")),              # code to corridor
    ("door", ("h", 9.0, INT), 20.5, 21.5, (-1, "b")),             # corridor to company
    ("door", ("h", NB, EXT), 7.5, 8.4, (+1, "a")),              # corridor to lift and stairs
]
# Room names at their label points, with the net area written below (computed from the inside faces).
ROOMS = [
    ("GOALS", (EXT, EXT, 6 - INT / 2, 6 - INT / 2)), ("CODE", (EXT, 6 + INT / 2, 6 - INT / 2, 11 - INT / 2)),
    ("CONVERSATIONS", (EXT, 11 + INT / 2, 6 - INT / 2, DEPTH - EXT)), ("WORK", (6 + INT / 2, EXT, 19.5 - INT / 2, 9 - INT / 2)),
    ("COMPANY", (19.5 + INT / 2, EXT, WIDTH - EXT, 9 - INT / 2)), ("CORRIDOR", (6 + INT / 2, 9 + INT / 2, WIDTH - EXT, NB - EXT / 2)),
    ("LIFT AND STAIRS", (6 + INT / 2, NB + EXT / 2, CORE_E - EXT / 2, DEPTH - EXT)),
]
FURNITURE = [  # thin grey outlines, metres (x0, y0, x1, y1)
    (1.0, 3.6, 3.4, 4.6), (1.4, 2.1, 2.6, 3.0), (0.6, 10.4, 3.4, 10.8), (1.6, 12.6, 4.4, 14.4),
    (7.2, 2.0, 9.0, 5.6), (10.6, 2.0, 12.4, 5.6), (14.0, 2.0, 15.8, 5.6), (20.6, 3.8, 22.9, 4.9),
    (6.4, 11.3, 7.6, 15.3), (8.0, 11.3, 9.6, 12.9),
] + [(6.4, 11.3 + k * 0.28, 7.6, 11.58 + k * 0.28) for k in range(14)]
TITLE = ("FERNHOLLOW STUDIO FLOOR", "Plan 1:100, first floor. One project floor of a made-up company, drawn for Arnheim.")
YS = [0, 6, 11, 16]

# The lobby, on the ground floor under it: the same outside walls and core. The reception hall faces the street
# (south), its desk where the measured sun reaches the counter, the wall of the company's website screens behind
# it; email, social media and domains each a room of their own (D78: every room is one Arnheim fills from the
# company's front-of-house data); the corridor and the lift and stairs as upstairs.
LOBBY = {
    "parts": [("v", 6.0, 0.15, 15.85), ("h", 8.0, 0.15, 6.0), ("v", 19.5, 0.15, 9.0), ("h", 9.0, 6.0, 23.85)],
    "open": [
        ("window", S_, 1.2, 5.2, None),                             # social media
        ("window", S_, 6.7, 10.6, None),                            # the hall, west bay
        ("door", S_, 11.2, 13.4, (+1, "ab")),                       # the way in from the street, a pair of glazed doors
        ("window", S_, 14.1, 18.4, None),                           # the hall, east bay
        ("window", S_, 20.3, 23.0, None),                           # email
        ("window", W_, 1.5, 6.5, None),
        ("window", W_, 9.5, 14.5, None),
        ("window", N_, 1.5, 4.5, None),
        ("window", N_, 7.3, 8.7, None),                             # the stair's window
        ("window", E_, 1.5, 7.5, None),
        ("window", E_, 9.3, 10.5, None),
        ("door", ("v", 6.0, INT), 5.4, 6.4, (-1, "a")),             # hall to social media
        ("door", ("v", 6.0, INT), 9.4, 10.4, (-1, "b")),            # corridor to domains
        ("open", ("h", 9.0, INT), 7.0, 10.0, None),                 # hall to corridor, by the lift
        ("door", ("h", 9.0, INT), 20.5, 21.5, (-1, "b")),           # corridor to email
        ("door", ("h", NB, EXT), 7.5, 8.4, (+1, "a")),              # corridor to lift and stairs
    ],
    "rooms": [
        ("SOCIAL MEDIA", (EXT, EXT, 6 - INT / 2, 8 - INT / 2)), ("DOMAINS", (EXT, 8 + INT / 2, 6 - INT / 2, DEPTH - EXT)),
        ("RECEPTION", (6 + INT / 2, EXT, 19.5 - INT / 2, 9 - INT / 2)), ("EMAIL", (19.5 + INT / 2, EXT, WIDTH - EXT, 9 - INT / 2)),
        ("CORRIDOR", (6 + INT / 2, 9 + INT / 2, WIDTH - EXT, NB - EXT / 2)),
        ("LIFT AND STAIRS", (6 + INT / 2, NB + EXT / 2, CORE_E - EXT / 2, DEPTH - EXT)),
    ],
    "furniture": [
        (9.75, 4.43, 12.75, 5.28), (8.95, 7.45, 13.55, 7.61), (15.65, 1.6, 17.85, 2.5), (15.78, 3.45, 16.48, 4.15), (17.02, 3.45, 17.72, 4.15),
        (0.7, 1.0, 1.1, 6.8), (0.7, 9.0, 1.1, 15.2), (20.0, 1.0, 20.45, 7.8),
        (6.4, 11.3, 7.6, 15.3), (8.0, 11.3, 9.6, 12.9),
    ] + [(6.4, 11.3 + k * 0.28, 7.6, 11.58 + k * 0.28) for k in range(14)],
    "title": ("FERNHOLLOW LOBBY", "Plan 1:100, ground floor. The lobby of a made-up company's building, drawn for Arnheim."),
    "ys": [0, 8, 16],
    "label_at": {"RECEPTION": (12.75, 3.0)},  # clear of the desk, which stands where the sun lands (sun/place_in_sun.py)
}


def wall_rect(axis, at, a, b, t):
    if axis == "h":
        return (a, at - t / 2, b, at + t / 2)
    return (at - t / 2, a, at + t / 2, b)


def rect_svg(r, **style):
    x0, y0, x1, y1 = r
    attrs = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in style.items())
    return f'<rect x="{X(x0):.2f}" y="{Y(y1):.2f}" width="{(x1 - x0) * S:.2f}" height="{(y1 - y0) * S:.2f}" {attrs}/>'


def line(x0, y0, x1, y1, w=1.2, c="#111", extra=""):
    return f'<line x1="{X(x0):.2f}" y1="{Y(y0):.2f}" x2="{X(x1):.2f}" y2="{Y(y1):.2f}" stroke="{c}" stroke-width="{w}" {extra}/>'


def draw(fl=None):
    fl = fl or {"parts": PARTS, "open": OPEN, "rooms": ROOMS, "furniture": FURNITURE, "title": TITLE, "ys": YS}
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{SHEET[0]}" height="{SHEET[1]}" viewBox="0 0 {SHEET[0]} {SHEET[1]}">',
           '<rect width="100%" height="100%" fill="#fbfaf7"/>',
           '<style>text{font-family:"Helvetica Neue",Arial,sans-serif;fill:#151515}</style>']
    # furniture first, so walls sit on top
    for f in fl["furniture"]:
        out.append(rect_svg(f, fill="none", stroke="#8a8a8a", stroke_width="1"))
    walls = list(OUTER) + [wall_rect(a, at, s, e, INT) for a, at, s, e in fl["parts"]]
    for r in walls:
        out.append(rect_svg(r, fill="#141414"))
    for kind, (axis, at, t), a, b, swing in fl["open"]:
        out.append(rect_svg(wall_rect(axis, at, a, b, t + 0.02), fill="#fbfaf7"))
        lo, hi = at - t / 2, at + t / 2
        if axis == "h":
            seg = lambda p0, p1, **k: line(p0[0], p0[1], p1[0], p1[1], **k)
            P = lambda along, across: (along, across)
        else:
            seg = lambda p0, p1, **k: line(p0[0], p0[1], p1[0], p1[1], **k)
            P = lambda along, across: (across, along)
        out.append(seg(P(a, lo), P(a, hi), w=1.2))
        out.append(seg(P(b, lo), P(b, hi), w=1.2))
        if kind == "window":
            for across in (lo, at - 0.03, at + 0.03, hi):
                out.append(seg(P(a, across), P(b, across), w=1.0))
        elif kind == "open":
            for across in (lo, hi):
                out.append(seg(P(a, across), P(b, across), w=1.0, extra='stroke-dasharray="6 5"'))
        elif kind == "door":
            side, hinge = swing
            face = hi if side > 0 else lo
            leaves = [(a, b - a, +1)] if hinge == "a" else [(b, b - a, -1)] if hinge == "b" else [(a, (b - a) / 2, +1), (b, (b - a) / 2, -1)]
            for h, w, d in leaves:
                tip = P(h, face + side * w)
                out.append(seg(P(h, face), tip, w=2.2))
                start = P(h + d * w, face)
                sx, sy, ex, ey = X(start[0]), Y(start[1]), X(tip[0]), Y(tip[1])
                cx, cy = X(P(h, face)[0]), Y(P(h, face)[1])
                cross = (sx - cx) * (ey - cy) - (sy - cy) * (ex - cx)
                out.append(f'<path d="M{sx:.2f},{sy:.2f} A{w * S:.2f},{w * S:.2f} 0 0 {1 if cross > 0 else 0} {ex:.2f},{ey:.2f}" fill="none" stroke="#333" stroke-width="1"/>')
    for name, (x0, y0, x1, y1) in fl["rooms"]:
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        area = (x1 - x0) * (y1 - y0)
        small = name in ("CORRIDOR", "LIFT AND STAIRS")
        size = 18 if small else 21
        if name == "CORRIDOR":
            cx = 15.0
        cx, cy = fl.get("label_at", {}).get(name, (cx, cy))
        out.append(f'<text x="{X(cx):.1f}" y="{Y(cy) - 2:.1f}" font-size="{size}" font-weight="600" letter-spacing="1.5" text-anchor="middle">{name.replace("&", "&amp;")}</text>')
        if name != "CORRIDOR":
            out.append(f'<text x="{X(cx):.1f}" y="{Y(cy) + size + 4:.1f}" font-size="{size - 3}" text-anchor="middle">{area:.1f} m²</text>')
    # dimensions: grid chains below and to the left
    yd = -1.4
    xs = [0, 6, 19.5, 24]
    out.append(line(0, yd, WIDTH, yd, w=1))
    for x in xs:
        out.append(line(x, yd - 0.15, x, yd + 0.15, w=1))
    for a, b in zip(xs, xs[1:]):
        out.append(f'<text x="{X((a + b) / 2):.1f}" y="{Y(yd) - 8:.1f}" font-size="17" text-anchor="middle">{b - a:.2f}</text>')
    out.append(line(0, yd - 0.9, WIDTH, yd - 0.9, w=1))
    out.append(line(0, yd - 1.05, 0, yd - 0.75, w=1) + line(WIDTH, yd - 1.05, WIDTH, yd - 0.75, w=1))
    out.append(f'<text x="{X(WIDTH / 2):.1f}" y="{Y(yd - 0.9) - 8:.1f}" font-size="17" text-anchor="middle">24.00</text>')
    xd = -1.4
    ys = fl["ys"]
    out.append(line(xd, 0, xd, DEPTH, w=1))
    for y in ys:
        out.append(line(xd - 0.15, y, xd + 0.15, y, w=1))
    for a, b in zip(ys, ys[1:]):
        tx, ty = X(xd) - 10, Y((a + b) / 2)
        out.append(f'<text x="{tx:.1f}" y="{ty:.1f}" font-size="17" text-anchor="middle" transform="rotate(-90 {tx:.1f} {ty:.1f})">{b - a:.2f}</text>')
    # scale bar, title and north arrow, well clear of the building
    sx, sy = X0, SHEET[1] - 150
    out.append(f'<rect x="{sx}" y="{sy}" width="{5 * S}" height="10" fill="#141414"/>')
    out.append(f'<text x="{sx}" y="{sy + 36}" font-size="18">0</text><text x="{sx + 5 * S}" y="{sy + 36}" font-size="18" text-anchor="end">5 m</text>')
    out.append(f'<text x="{X0 + 12 * S}" y="{SHEET[1] - 118}" font-size="26" font-weight="700" letter-spacing="2" text-anchor="middle">{fl["title"][0]}</text>')
    out.append(f'<text x="{X0 + 12 * S}" y="{SHEET[1] - 84}" font-size="18" text-anchor="middle">{fl["title"][1]}</text>')
    nx, ny, r = SHEET[0] - 150, 300, 46
    ang = math.radians(NORTH)
    tip = (nx + math.sin(ang) * r * 1.25, ny - math.cos(ang) * r * 1.25)
    left = (nx + math.sin(ang - 2.6) * r * 0.55, ny - math.cos(ang - 2.6) * r * 0.55)
    right = (nx + math.sin(ang + 2.6) * r * 0.55, ny - math.cos(ang + 2.6) * r * 0.55)
    out.append(f'<circle cx="{nx}" cy="{ny}" r="{r}" fill="none" stroke="#141414" stroke-width="1.5"/>')
    out.append(f'<polygon points="{tip[0]:.1f},{tip[1]:.1f} {left[0]:.1f},{left[1]:.1f} {nx},{ny} {right[0]:.1f},{right[1]:.1f}" fill="#141414"/>')
    lab = (nx + math.sin(ang) * r * 1.75, ny - math.cos(ang) * r * 1.75)
    out.append(f'<text x="{lab[0]:.1f}" y="{lab[1] + 9:.1f}" font-size="26" font-weight="700" text-anchor="middle">N</text>')
    out.append("</svg>")
    return "\n".join(out)


def main():
    out = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "out")
    lobby = len(sys.argv) > 2 and sys.argv[2] == "lobby"
    os.makedirs(out, exist_ok=True)
    svg = os.path.join(out, "plan-lobby.svg" if lobby else "plan.svg")
    with open(svg, "w", encoding="utf-8") as handle:
        handle.write(draw(LOBBY if lobby else None))
    png = svg[:-4] + ".png"
    subprocess.run([CHROME, "--headless=new", "--hide-scrollbars", "--force-device-scale-factor=1", "--no-first-run",
                    f"--window-size={SHEET[0]},{SHEET[1]}", f"--screenshot={png}", "file://" + svg],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("wrote", svg, "and", png)


if __name__ == "__main__":
    main()
