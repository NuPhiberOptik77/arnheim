#!/usr/bin/env python3
"""Picks the sun by measurement: the date and time that puts the most direct sun on the least sunny styled
room's subject... in practice: the most styled rooms with at least 10% of their subject (main table or sofa
top, design.json "subjects") in direct sun, then the most subject sun on average, while every styled room keeps
at least design.json sun.min_floor_share of its floor in sun. One sun can't reach a table lit from the east and
one lit from the west, so "every subject" isn't on offer.

For each candidate sun position it follows the light back from every 10 cm of floor towards the sun:
a point is sunlit when that ray passes through a window's opening at both faces of the wall (so deep
reveals cut the patch, as they do in life) and below the window head. Furniture is not counted here.

python3 pick_sun.py DESIGN.json OUT.json
"""
import json
import math
import os
import sys

import numpy as np


def sun_position(lat, day, hour):
    """Sun azimuth (degrees clockwise from true north) and elevation at a latitude, day of year, solar hour."""
    decl = math.radians(23.44) * math.sin(math.radians(360 / 365 * (284 + day)))
    ha = math.radians(15 * (hour - 12))
    phi = math.radians(lat)
    el = math.asin(math.sin(phi) * math.sin(decl) + math.cos(phi) * math.cos(decl) * math.cos(ha))
    az = math.atan2(-math.sin(ha), math.tan(decl) * math.cos(phi) - math.sin(phi) * math.cos(ha))
    return math.degrees(az) % 360, math.degrees(el)


def inside(poly, xs, ys):
    """Even-odd test of points against a polygon."""
    res = np.zeros(xs.shape, bool)
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        cross = (y0 > ys) != (y1 > ys)
        with np.errstate(divide="ignore", invalid="ignore"):
            xint = x0 + (ys - y0) * (x1 - x0) / (y1 - y0)
        res ^= cross & (xs < xint)
    return res


def main():
    design = json.load(open(sys.argv[1]))
    base = os.path.dirname(os.path.abspath(sys.argv[1]))
    plan = json.load(open(os.path.join(base, design["plan"])))
    hts = design["heights"]
    north = plan["north_deg"]
    walls = {w["id"]: w for w in plan["walls"]}
    rooms = [r for r in plan["rooms"] if r["name"] in design["styled"]]
    lat = design["site"]["latitude"]

    # Floor points and the windows that light each room (windows on its own outside walls).
    setups = []
    for r in rooms:
        xs_, ys_ = [p[0] for p in r["polygon"]], [p[1] for p in r["polygon"]]
        gx, gy = np.meshgrid(np.arange(min(xs_) + 0.05, max(xs_), 0.1), np.arange(min(ys_) + 0.05, max(ys_), 0.1))
        keep = inside(r["polygon"], gx, gy)
        px, py = gx[keep], gy[keep]
        cx, cy = px.mean(), py.mean()
        wins = []
        for o in plan["openings"]:
            if o["kind"] != "window":
                continue
            w = walls[o["wall"]]
            horiz = abs(w["a"][1] - w["b"][1]) < 1e-6
            c = w["a"][1] if horiz else w["a"][0]
            lo, hi = sorted((o["from"][0], o["to"][0])) if horiz else sorted((o["from"][1], o["to"][1]))
            # this room's window if the room's floor reaches that wall's inner face along the window
            inner = c - w["thickness"] / 2 if (cy if horiz else cx) < c else c + w["thickness"] / 2
            outer = 2 * c - inner
            near = (np.abs(py - inner) < 0.2) if horiz else (np.abs(px - inner) < 0.2)
            span = ((px >= lo) & (px <= hi)) if horiz else ((py >= lo) & (py <= hi))
            if not (near & span).any():
                continue
            sill = hts["small_window_sill"] if o["width"] <= design["small_window_max_width"] and r["name"] not in design["styled"] else hts["window_sill"]
            wins.append({"horiz": horiz, "inner": inner, "outer": outer, "lo": lo, "hi": hi, "sill": sill, "head": hts["window_head"], "id": o["id"]})
        subj = design.get("subjects", {}).get(r["name"], [])
        sx, sy, sz = [], [], []
        for x0, y0, x1, y1, h in subj:  # every 5 cm of the subject's top
            gx2, gy2 = np.meshgrid(np.arange(x0 + 0.025, x1, 0.05), np.arange(y0 + 0.025, y1, 0.05))
            sx.append(gx2.ravel()); sy.append(gy2.ravel()); sz.append(np.full(gx2.size, h))
        setups.append({"room": r["name"], "x": px, "y": py, "z": np.zeros(px.shape), "windows": wins, "area": r["area"],
                       "subject": {"x": np.concatenate(sx), "y": np.concatenate(sy), "z": np.concatenate(sz)} if subj else None})

    def lit(setup, az, el):
        a = math.radians(az - north)
        d = np.array([math.cos(math.radians(el)) * math.sin(a), math.cos(math.radians(el)) * math.cos(a), math.sin(math.radians(el))])
        out = np.zeros(setup["x"].shape, bool)
        for w in setup["windows"]:
            ok = np.ones(setup["x"].shape, bool)
            for plane in (w["inner"], w["outer"]):
                if w["horiz"]:
                    if abs(d[1]) < 1e-9:
                        ok[:] = False; break
                    lam = (plane - setup["y"]) / d[1]
                    along = setup["x"] + lam * d[0]
                else:
                    if abs(d[0]) < 1e-9:
                        ok[:] = False; break
                    lam = (plane - setup["x"]) / d[0]
                    along = setup["y"] + lam * d[1]
                z = setup["z"] + lam * d[2]
                ok &= (lam > 0) & (along >= w["lo"]) & (along <= w["hi"]) & (z >= w["sill"]) & (z <= w["head"])
            out |= ok
        return out

    def score(az, el):
        fr = [lit(s, az, el).mean() for s in setups]
        sub = []
        for s in setups:
            if s["subject"] is None:
                sub.append(1.0)
                continue
            t = dict(s, **s["subject"])
            sub.append(lit(t, az, el).mean())
        ok = min(fr) >= design["sun"].get("min_floor_share", 0.0)
        # one sun can't reach every subject (a room lit from the east and one from the west), so: as many rooms as
        # possible with at least 10% of the subject in sun, then the most subject sun on average
        n = sum(1 for v in sub if v >= 0.1)
        return (n + sum(sub) / len(sub) if ok else -1.0), fr, sub

    best, table = None, []
    for day in range(1, 366, 7):
        for k in range(4 * 6, 4 * 21):
            hour = k / 4
            az, el = sun_position(lat, day, hour)
            if el < design["sun"]["min_elevation_deg"]:
                continue
            m, fr, sub = score(az, el)
            table.append((m, day, hour, az, el))
            if best is None or m > best[0]:
                best = (m, day, hour, az, el, fr, sub)
    _, day0, hour0, *_ = best
    for day in range(max(1, day0 - 7), min(365, day0 + 7) + 1):
        for k in range(-15, 16):
            hour = hour0 + k * 2 / 60
            az, el = sun_position(lat, day, hour)
            if el < design["sun"]["min_elevation_deg"]:
                continue
            m, fr, sub = score(az, el)
            if m > best[0]:
                best = (m, day, hour, az, el, fr, sub)
    m, day, hour, az, el, fr, sub = best
    date = (np.datetime64("2026-01-01") + np.timedelta64(day - 1, "D")).astype(object)
    table.sort(reverse=True)
    result = {
        "picked_by": "the most styled rooms with at least 10% of their subject (main table or sofa top) in direct sun, then the most subject sun on average, with every room keeping at least min_floor_share of its floor in sun (D80)",
        "site_latitude": lat, "north_deg": north,
        "date": date.strftime("%d %B"), "day_of_year": day, "solar_time": f"{int(hour):02d}:{round(hour % 1 * 60):02d}",
        "sun_azimuth_deg": round(az, 2), "sun_elevation_deg": round(el, 2),
        "sun_direction_plan": [round(math.cos(math.radians(el)) * math.sin(math.radians(az - north)), 5),
                               round(math.cos(math.radians(el)) * math.cos(math.radians(az - north)), 5),
                               round(math.sin(math.radians(el)), 5)],
        "sunlit_floor_share": {s["room"]: round(f, 3) for s, f in zip(setups, fr)},
        "sunlit_floor_m2": {s["room"]: round(f * s["area"], 1) for s, f in zip(setups, fr)},
        "sunlit_subject_share": {s["room"]: round(f, 3) for s, f in zip(setups, sub)},
        "least_sunny_subject_share": round(min(sub), 3),
        "least_sunny_floor_share": round(min(fr), 3),
        "windows_counted": {s["room"]: [w["id"] for w in s["windows"]] for s in setups},
        "next_best": [{"score": round(t[0], 3), "day": t[1], "solar_hour": t[2], "az": round(t[3], 1), "el": round(t[4], 1)} for t in table[:5]],
        "candidates_tried": len(table),
    }
    with open(sys.argv[2], "w") as handle:
        json.dump(result, handle, indent=1)
    print(json.dumps({k: result[k] for k in ("date", "solar_time", "sun_azimuth_deg", "sun_elevation_deg", "sunlit_subject_share", "sunlit_floor_share", "candidates_tried")}, indent=1))


if __name__ == "__main__":
    main()
