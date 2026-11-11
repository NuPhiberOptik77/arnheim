#!/usr/bin/env python3
"""Draws a traced plan back over the drawing it came from, and measures how well they agree.

- Walls: the traced walls are filled in pixel by pixel and laid on the drawing's own wall marks:
  overlap (intersection over union), how much of each falls outside the other, and the mean edge offset.
- Openings: for each, where the drawing's gap really starts and ends, against the traced ends.
- Rooms: the traced area against the area written in the room on the drawing.
- Scale: the traced width against the drawing's overall dimension.

Writes overlay.png (the drawing faded, the trace on top, mismatches in colour) and overlap.json.

python3 overlay.py PLAN.png PLAN.json OUT_DIR
"""
import json
import math
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trace import load_gray, opening  # the same reading of "a wall mark": dark, and thicker than a line

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def main():
    png, js, out = sys.argv[1], sys.argv[2], sys.argv[3]
    d = json.load(open(js))
    s = d["scale"]["px_per_m"]
    ox, oy = d["scale"]["origin_px"]
    P = lambda x, y: (ox + x * s, oy - y * s)
    gray = load_gray(png)
    H, W = gray.shape
    w_m, h_m = d["size"]
    bx0, by0, bx1, by1 = ox, int(round(oy - h_m * s)), int(round(ox + w_m * s)), oy
    original = opening(gray < 110, 6)
    region = np.zeros_like(original)
    region[by0:by1, bx0:bx1] = True
    original &= region

    walls = d["walls"]
    def band(w):
        (ax, ay), (bx, by) = w["a"], w["b"]
        t = w["thickness"]
        horiz = abs(ay - by) < 1e-6
        return horiz, t, (min(ax, bx), max(ax, bx)) if horiz else (min(ay, by), max(ay, by)), ay if horiz else ax
    def meets(x, y, me):
        for o in walls:
            if o is me:
                continue
            h, t, (lo, hi), c = band(o)
            if (h and lo - 1e-3 <= x <= hi + 1e-3 and abs(y - c) <= t / 2 + 1e-3) or \
               (not h and lo - 1e-3 <= y <= hi + 1e-3 and abs(x - c) <= t / 2 + 1e-3):
                return True
        return False
    traced = np.zeros_like(original)
    rects = []
    for w in walls:
        h, t, (lo, hi), c = band(w)
        ends = [(lo, c) if h else (c, lo), (hi, c) if h else (c, hi)]
        lo -= t / 2 if meets(*ends[0], w) else 0
        hi += t / 2 if meets(*ends[1], w) else 0
        cuts = sorted((min(o["from"][0 if h else 1], o["to"][0 if h else 1]), max(o["from"][0 if h else 1], o["to"][0 if h else 1]))
                      for o in d["openings"] if o["wall"] == w["id"])
        a = lo
        for c0, c1 in cuts + [(hi, hi)]:
            if c0 > a:
                rects.append((a, c - t / 2, c0, c + t / 2) if h else (c - t / 2, a, c + t / 2, c0))
            a = max(a, c1)
    for x0, y0, x1, y1 in rects:
        (px0, py1), (px1, py0) = P(x0, y0), P(x1, y1)
        traced[int(round(py0)):int(round(py1)), int(round(px0)):int(round(px1))] = True
    inter = (traced & original).sum()
    union = (traced | original).sum()
    edge = original & ~(np.roll(original, 1, 0) & np.roll(original, -1, 0) & np.roll(original, 1, 1) & np.roll(original, -1, 1))
    wall_report = {
        "overlap_iou": round(inter / union, 4),
        "traced_on_drawn": round(inter / traced.sum(), 4),
        "drawn_covered": round(inter / original.sum(), 4),
        "mean_edge_offset_cm": round((traced ^ original).sum() / edge.sum() / s * 100, 2),
        "drawn_px": int(original.sum()), "traced_px": int(traced.sum()),
    }

    # Openings: the drawing's own gap along the wall's centre line, against the traced ends.
    errs = []
    for o in d["openings"]:
        h = abs(o["from"][1] - o["to"][1]) < 1e-6
        mid = ((o["from"][0] + o["to"][0]) / 2, (o["from"][1] + o["to"][1]) / 2)
        px, py = P(*mid)
        px, py = int(round(px)), int(round(py))
        line = original[py, :] if h else original[:, px]
        i = px if h else py
        a = i
        while a > 0 and not line[a - 1]:
            a -= 1
        b = i
        while b < len(line) - 1 and not line[b + 1]:
            b += 1
        b += 1
        if h:
            drawn = sorted(((a - ox) / s, (b - ox) / s))
            traced_ends = sorted((o["from"][0], o["to"][0]))
        else:
            drawn = sorted(((oy - b) / s, (oy - a) / s))
            traced_ends = sorted((o["from"][1], o["to"][1]))
        e = max(abs(drawn[0] - traced_ends[0]), abs(drawn[1] - traced_ends[1])) * 100
        errs.append(e)
        o["_drawn"] = drawn
    open_report = {"count": len(errs), "worst_end_error_cm": round(max(errs), 2), "mean_end_error_cm": round(sum(errs) / len(errs), 2)}

    rooms = []
    for r in d["rooms"]:
        if r["label_area"] is not None:
            rooms.append({"room": r["name"], "traced_m2": r["area"], "written_m2": r["label_area"],
                          "diff_m2": round(r["area"] - r["label_area"], 2)})
    room_report = {"rooms": len(d["rooms"]), "with_written_area": len(rooms),
                   "worst_area_diff_m2": max(abs(r["diff_m2"]) for r in rooms),
                   "worst_area_diff_pct": round(max(abs(r["diff_m2"]) / r["written_m2"] * 100 for r in rooms), 2),
                   "each": rooms}
    report = {"walls": wall_report, "openings": open_report, "rooms": room_report,
              "scale": d["scale"].get("check"), "north_deg": d["north_deg"]}
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "overlap.json"), "w") as handle:
        json.dump(report, handle, indent=1)

    # The picture: the drawing faded; traced walls in red over it; drawn-but-not-traced in blue,
    # traced-but-not-drawn in magenta; openings and rooms drawn from the data, with names.
    rgb = np.repeat((gray.astype(np.float32) * 0.35 + 165)[..., None], 3, axis=2)
    def paint(mask, color, alpha):
        rgb[mask] = rgb[mask] * (1 - alpha) + np.array(color, np.float32) * alpha
    paint(traced & original, (215, 40, 40), 0.75)
    paint(original & ~traced, (30, 90, 255), 1.0)
    paint(traced & ~original, (230, 0, 200), 1.0)
    base = os.path.join(out, "overlay-base.png")
    subprocess.run(["/opt/homebrew/bin/ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                    "-i", "-", base], input=rgb.clip(0, 255).astype(np.uint8).tobytes(), check=True)
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{W}" height="{H}">',
           f'<image href="overlay-base.png" x="0" y="0" width="{W}" height="{H}"/>',
           '<style>text{font-family:"Helvetica Neue",Arial,sans-serif}</style>']
    colors = ["#e6b800", "#00a37a", "#7a5cff", "#ff7a00", "#0098d4", "#d4006a"]
    for i, r in enumerate(d["rooms"]):
        pts = " ".join(f"{P(x, y)[0]:.1f},{P(x, y)[1]:.1f}" for x, y in r["polygon"])
        svg.append(f'<polygon points="{pts}" fill="{colors[i % 6]}" fill-opacity="0.10" stroke="{colors[i % 6]}" stroke-width="2"/>')
        xs = [p[0] for p in r["polygon"]]; ys = [p[1] for p in r["polygon"]]
        cx, cy = P((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
        svg.append(f'<text x="{cx:.0f}" y="{cy + 52:.0f}" font-size="17" font-weight="700" fill="{colors[i % 6]}" text-anchor="middle">{r["id"]} traced {r["area"]} m²</text>')
    for o in d["openings"]:
        (x0, y0), (x1, y1) = P(*o["from"]), P(*o["to"])
        if o["kind"] == "window":
            svg.append(f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" stroke="#00c8ff" stroke-width="5" stroke-opacity="0.8"/>')
        elif o["kind"] == "open":
            svg.append(f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" stroke="#ff8a00" stroke-width="5" stroke-dasharray="10 6"/>')
        else:
            h = abs(o["from"][1] - o["to"][1]) < 1e-6
            wall = next(w for w in walls if w["id"] == o["wall"])
            t = wall["thickness"] / 2
            side = {"up": +1, "down": -1, "right": +1, "left": -1}[o["swing"]]
            leaves = {"a": [(0, 1.0)], "b": [(1, 1.0)], "ab": [(0, 0.5), (1, 0.5)]}[o["hinge"]]
            ends = [o["from"], o["to"]]
            ends.sort(key=lambda p: p[0] if h else p[1])
            width = o["width"]
            for which, frac in leaves:
                hx, hy = ends[which]
                rad = width * frac
                d_along = 1 if which == 0 else -1
                pts = []
                for k in range(25):
                    th = math.pi / 2 * k / 24
                    along, across = rad * math.cos(th) * d_along, side * (t + rad * math.sin(th))
                    pts.append(P(hx + along, hy + across) if h else P(hx + across, hy + along))
                leaf = [P(hx, hy + side * t), P(hx, hy + side * (t + rad))] if h else [P(hx + side * t, hy), P(hx + side * (t + rad), hy)]
                svg.append('<polyline points="' + " ".join(f"{a:.1f},{b:.1f}" for a, b in pts) + '" fill="none" stroke="#18b04a" stroke-width="3"/>')
                svg.append(f'<line x1="{leaf[0][0]:.1f}" y1="{leaf[0][1]:.1f}" x2="{leaf[1][0]:.1f}" y2="{leaf[1][1]:.1f}" stroke="#18b04a" stroke-width="4"/>')
    if d["north_deg"] is not None:
        ang = math.radians(d["north_deg"])
        svg.append(f'<line x1="{W - 150}" y1="300" x2="{W - 150 + math.sin(ang) * 90:.1f}" y2="{300 - math.cos(ang) * 90:.1f}" stroke="#d4006a" stroke-width="3"/>')
    wr, orp, rr = wall_report, open_report, room_report
    lines = [f"Walls: overlap {wr['overlap_iou'] * 100:.2f}%, mean edge offset {wr['mean_edge_offset_cm']} cm",
             f"Openings: {orp['count']}, worst end {orp['worst_end_error_cm']} cm off",
             f"Rooms: {rr['rooms']}, worst area {rr['worst_area_diff_m2']} m² ({rr['worst_area_diff_pct']}%) off the written area",
             f"Scale check: traced width {d['size'][0]} m, drawn {d['scale'].get('check', {}).get('widest_dimension_label')} m. North {d['north_deg']}°"]
    for i, t in enumerate(lines):
        svg.append(f'<text x="1400" y="{1700 + i * 30}" font-size="22" font-weight="600" fill="#111">{t}</text>')
    svg.append(f'<text x="1400" y="{1700 + len(lines) * 30 + 6}" font-size="18" fill="#444">red: traced on drawn wall  blue: drawn, not traced  magenta: traced, not drawn</text>')
    svg.append("</svg>")
    svg_path = os.path.join(out, "overlay.svg")
    with open(svg_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(svg))
    subprocess.run([CHROME, "--headless=new", "--hide-scrollbars", "--force-device-scale-factor=1", "--no-first-run",
                    "--allow-file-access-from-files", f"--window-size={W},{H}", f"--screenshot={os.path.join(out, 'overlay.png')}",
                    "file://" + os.path.abspath(svg_path)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(json.dumps({k: v for k, v in report.items() if k != "rooms"} | {"rooms": {k: v for k, v in room_report.items() if k != "each"}}, indent=1))


if __name__ == "__main__":
    main()
