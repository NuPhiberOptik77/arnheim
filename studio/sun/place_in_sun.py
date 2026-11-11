#!/usr/bin/env python3
"""Finds where a room's main piece should stand so the photographed moment's sun lands on its top: the sun
stays fixed (out/sun.json, the moment every photograph shows), the piece moves. For each candidate place it
follows the light back from every 5 cm of the top towards the sun, the same test as pick_sun.py: sunlit when
the ray passes a window's opening at both faces of the wall, between its sill and head. Furniture is not
counted.

python3 place_in_sun.py DESIGN.json ROOM WIDTH DEPTH HEIGHT [Y_MIN Y_MAX]
  prints the best places for a WIDTH x DEPTH top at HEIGHT (metres), its long side along x, its middle
  kept between Y_MIN and Y_MAX if given
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


def windows(plan, design, room):
    """The windows on the room's own outside walls, each as the two wall faces and its span."""
    walls = {w["id"]: w for w in plan["walls"]}
    xs, ys = [p[0] for p in room["polygon"]], [p[1] for p in room["polygon"]]
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
    hts = design["heights"]
    out = []
    for o in plan["openings"]:
        if o["kind"] != "window":
            continue
        w = walls[o["wall"]]
        horiz = abs(w["a"][1] - w["b"][1]) < 1e-6
        c = w["a"][1] if horiz else w["a"][0]
        lo, hi = sorted((o["from"][0], o["to"][0])) if horiz else sorted((o["from"][1], o["to"][1]))
        inner = c - w["thickness"] / 2 if (cy if horiz else cx) < c else c + w["thickness"] / 2
        on_room = (min(xs) - 0.3 <= c <= max(xs) + 0.3) if not horiz else (min(ys) - 0.3 <= c <= max(ys) + 0.3)
        overlaps = (lo < max(xs) and hi > min(xs)) if horiz else (lo < max(ys) and hi > min(ys))
        if on_room and overlaps:
            out.append({"horiz": horiz, "inner": inner, "outer": 2 * c - inner, "lo": lo, "hi": hi,
                        "sill": hts["window_sill"], "head": hts["window_head"]})
    return out


def lit(x, y, z, wins, d):
    out = np.zeros(x.shape, bool)
    for w in wins:
        ok = np.ones(x.shape, bool)
        for plane in (w["inner"], w["outer"]):
            k, along_of = (1, lambda lam: x + lam * d[0]) if w["horiz"] else (0, lambda lam: y + lam * d[1])
            if abs(d[k]) < 1e-9:
                ok[:] = False
                break
            lam = (plane - (y if w["horiz"] else x)) / d[k]
            along, zz = along_of(lam), z + lam * d[2]
            ok &= (lam > 0) & (along >= w["lo"]) & (along <= w["hi"]) & (zz >= w["sill"]) & (zz <= w["head"])
        out |= ok
    return out


def main():
    dpath, name = sys.argv[1], sys.argv[2]
    W, D, H = (float(v) for v in sys.argv[3:6])
    y_lim = (float(sys.argv[6]), float(sys.argv[7])) if len(sys.argv) > 7 else None
    design = json.load(open(dpath))
    base = os.path.dirname(os.path.abspath(dpath))
    plan = json.load(open(os.path.join(base, design["plan"])))
    sun = json.load(open(os.path.join(base, "out", "sun.json")))
    d = np.array(sun["sun_direction_plan"])  # towards the sun, plan axes
    room = next(r for r in plan["rooms"] if r["name"] == name)
    wins = windows(plan, design, room)
    xs, ys = [p[0] for p in room["polygon"]], [p[1] for p in room["polygon"]]
    gx, gy = np.meshgrid(np.arange(-W / 2 + 0.025, W / 2, 0.05), np.arange(-D / 2 + 0.025, D / 2, 0.05))
    best = []
    for cx in np.arange(min(xs) + W / 2 + 0.3, max(xs) - W / 2 - 0.3, 0.1):
        for cy in np.arange(min(ys) + D / 2 + 0.3, max(ys) - D / 2 - 0.3, 0.1):
            if y_lim and not (y_lim[0] <= cy <= y_lim[1]):
                continue
            share = lit(cx + gx.ravel(), cy + gy.ravel(), np.full(gx.size, H), wins, d).mean()
            best.append((round(float(share), 3), round(float(cx), 2), round(float(cy), 2)))
    best.sort(reverse=True)
    print(json.dumps({"room": name, "top": [W, D, H], "sun": [sun["date"], sun["solar_time"], sun["sun_azimuth_deg"], sun["sun_elevation_deg"]],
                      "windows": len(wins), "best": best[:8]}, indent=1))


if __name__ == "__main__":
    main()
