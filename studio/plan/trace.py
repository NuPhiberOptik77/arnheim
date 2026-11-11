#!/usr/bin/env python3
"""Traces a floor plan drawing into one data file of walls, openings and rooms, from the picture alone.

How it reads the drawing:
- Walls are the thick dark marks. Thin lines (windows, door leaves and swings, furniture, dimensions,
  text) are wiped first by an opening with a square a little wider than the thickest thin line.
- Each wall is a straight run of thick marks; collinear runs of the same thickness with a gap of
  0.5 to 4.5 m between them are one wall with an opening in the gap.
- An opening is a window if lines run the length of the gap inside the wall, a door if a leaf and a
  swing arc are found (single, or a pair for a double door), else a plain opening.
- Rooms are the spaces left once every opening is closed. Their names and written areas are read
  with macOS's text recognition, enlarged where the text is small.
- The scale comes from the scale bar and its "5 m" label; north from the north arrow's point.

Needs numpy (Blender's own Python has it) and ffmpeg. Coordinates are metres, x to the right, y up the
sheet, from the building's outside bottom-left corner.

python3 trace.py PLAN.png OUT.json
"""
import json
import math
import os
import re
import subprocess
import sys

import numpy as np

FFMPEG = "/opt/homebrew/bin/ffmpeg"
FFPROBE = "/opt/homebrew/bin/ffprobe"
HERE = os.path.dirname(os.path.abspath(__file__))


def load_gray(path):
    size = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0", path],
                          capture_output=True, text=True, check=True).stdout.strip().split(",")
    w, h = int(size[0]), int(size[1])
    raw = subprocess.run([FFMPEG, "-v", "error", "-i", path, "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(h, w)


def box_sum(mask, k):
    """Sum of mask over each k by k window, anchored at the window's top-left."""
    c = np.pad(mask.astype(np.int32), ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    return c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]


def opening(mask, k):
    """Erode then dilate with a k by k square: keeps only marks at least k pixels thick."""
    h, w = mask.shape
    full = box_sum(mask, k) == k * k                      # window fully dark: its top-left anchor survives erosion
    er = np.zeros_like(mask)
    er[:h - k + 1, :w - k + 1] = full
    grown = box_sum(np.pad(er, ((k - 1, 0), (k - 1, 0))), k) > 0
    return grown[:h, :w]


def components(mask):
    """Connected parts of a mask (8-connected), labelled by joining runs row to row. Returns labels, count."""
    h, w = mask.shape
    labels = np.zeros((h, w), np.int32)
    parent = [0]

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    prev = []
    for y in range(h):
        row = mask[y]
        if not row.any():
            prev = []
            continue
        d = np.diff(np.concatenate(([0], row.view(np.int8), [0])))
        cur = []
        j = 0
        for s, e in zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)):
            while j < len(prev) and prev[j][1] < s:
                j += 1
            lab = None
            k = j
            while k < len(prev) and prev[k][0] <= e:
                r = find(prev[k][2])
                if lab is None:
                    lab = r
                elif r != lab:
                    lo_, hi_ = min(r, lab), max(r, lab)
                    parent[hi_] = lo_
                    lab = lo_
                k += 1
            if lab is None:
                parent.append(len(parent))
                lab = len(parent) - 1
            cur.append((s, e, lab))
            labels[y, s:e] = lab
        prev = cur
    roots = np.array([find(i) for i in range(len(parent))], np.int32)
    _, compact = np.unique(roots, return_inverse=True)
    out = compact[labels]
    return out, int(compact.max()) + 1


def bbox(mask):
    ys, xs = np.nonzero(mask)
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1


def ocr(png, crop=None):
    args = ["swift", os.path.join(HERE, "ocr.swift"), png]
    if crop:
        args += [str(int(v)) for v in crop[:4]] + [str(crop[4])]
    done = subprocess.run(args, capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


def runs_rectangles(mask, min_len, tol=3):
    """Rectangles made of row runs at least min_len long whose ends stay put from row to row."""
    rects, open_ = [], {}
    h, w = mask.shape
    for y in range(h + 1):
        found = []
        if y < h and mask[y].any():
            d = np.diff(np.concatenate(([0], mask[y].view(np.int8), [0])))
            for s, e in zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)):
                if e - s >= min_len:
                    found.append((s, e))
        nxt = {}
        for s, e in found:
            key = next((k for k in open_ if abs(k[0] - s) <= tol and abs(k[1] - e) <= tol), None)
            if key is not None:
                nxt[key] = (open_.pop(key)[0], y)
            else:
                nxt[(s, e)] = (y, y)
        for (s, e), (y0, y1) in open_.items():
            rects.append((s, y0, e, y1 + 1))
        open_ = nxt
    return rects


def main():
    png, out_json = sys.argv[1], sys.argv[2]
    gray = load_gray(png)
    H, Wd = gray.shape
    dark = gray < 110
    thick = opening(dark, 6)
    lab, n = components(thick)
    ys, xs = np.nonzero(lab)
    ls = lab[ys, xs]
    x0s = np.full(n, 1 << 30); y0s = np.full(n, 1 << 30); x1s = np.zeros(n, int); y1s = np.zeros(n, int)
    np.minimum.at(x0s, ls, xs); np.minimum.at(y0s, ls, ys); np.maximum.at(x1s, ls, xs + 1); np.maximum.at(y1s, ls, ys + 1)
    counts = np.bincount(ls, minlength=n)
    boxes = {i: (int(x0s[i]), int(y0s[i]), int(x1s[i]), int(y1s[i]), int(counts[i])) for i in range(1, n) if counts[i]}
    boxes = {i: b for i, b in boxes.items() if b[4] >= 100}  # specks left of letters are not walls
    words = ocr(png)

    # Scale: the bar whose end carries a length label ("5 m"): its length in pixels over that.
    is_len = lambda w: re.fullmatch(r"\s*\d+(\.\d+)?\s*m\s*", w["text"])
    labels_m = [w for w in words if is_len(w)]
    if not labels_m:  # small print the first read missed: read round each bar again, enlarged
        for i, b in boxes.items():
            if (b[2] - b[0]) > 15 * (b[3] - b[1]):
                crop = (max(0, b[0] - 60), max(0, b[1] - 20), (b[2] - b[0]) + 120, (b[3] - b[1]) + 70, 3)
                labels_m += [w for w in ocr(png, crop) if is_len(w)]
    def gap_to(i, w):
        b = boxes[i]
        return math.hypot(w["box"][0] + w["box"][2] - b[2], w["box"][1] - b[3])
    bar, label = min(((i, w) for i in boxes for w in labels_m
                      if (boxes[i][2] - boxes[i][0]) > 15 * (boxes[i][3] - boxes[i][1])), key=lambda iw: gap_to(*iw))
    bar_len = boxes[bar][2] - boxes[bar][0]
    bar_m = float(re.match(r"\s*(\d+(?:\.\d+)?)", label["text"]).group(1))
    s = bar_len / bar_m

    # The building: the biggest piece of wall and every piece within 2 m of it, step by step (openings
    # break walls into pieces). The scale bar, title and north arrow sit further off.
    seed = max(boxes, key=lambda i: boxes[i][4])
    reach = 2.0 * s
    inside = {seed}
    grew = True
    while grew:
        grew = False
        for i, b in boxes.items():
            if i in inside or i == bar:
                continue
            for j in list(inside):
                c = boxes[j]
                if max(0, c[0] - b[2], b[0] - c[2], c[1] - b[3], b[1] - c[3]) <= reach:
                    inside.add(i)
                    grew = True
                    break
    bx0 = min(boxes[i][0] for i in inside); by0 = min(boxes[i][1] for i in inside)
    bx1 = max(boxes[i][2] for i in inside); by1 = max(boxes[i][3] for i in inside)
    # Then every piece inside that outline: a corner between two windows can stand far from the rest.
    inside = sorted(i for i, b in boxes.items() if i != bar and b[0] >= bx0 - 2 and b[1] >= by0 - 2 and b[2] <= bx1 + 2 and b[3] <= by1 + 2)
    outside = [i for i in boxes if i not in inside]
    to_m = lambda px, py: (round((px - bx0) / s, 3), round((by1 - py) / s, 3))

    walls_px = np.isin(lab, inside) & thick

    # North: the filled arrow outside the building that is not the bar; its point is the pixel
    # farthest from its middle.
    arrows = [i for i in outside if i != bar and 0.25 < (boxes[i][2] - boxes[i][0]) / max(1, boxes[i][3] - boxes[i][1]) < 4]
    north = None
    if arrows:
        a = max(arrows, key=lambda i: boxes[i][4])
        x0, y0, x1, y1, _ = boxes[a]
        pad = 3 * max(x1 - x0, y1 - y0)
        X0, Y0 = max(0, x0 - pad), max(0, y0 - pad)
        win = dark[Y0:y1 + pad, X0:x1 + pad]
        wl, _ = components(win)
        core = wl[(y0 + y1) // 2 - Y0, (x0 + x1) // 2 - X0]
        part = wl == core                      # the arrow with its ring
        ys, xs = np.nonzero(part)
        # The ring is the thin part: away from the filled arrow. A circle fitted to it gives the centre;
        # the arrow's point is the pixel farthest from that centre.
        filled = opening(part, 6)
        near = box_sum(np.pad(filled, 4), 9) > 0
        ry, rx = np.nonzero(part & ~near[:part.shape[0], :part.shape[1]])
        A = np.column_stack([rx, ry, np.ones_like(rx)]).astype(float)
        D, E, F = np.linalg.lstsq(A, -(rx.astype(float) ** 2 + ry.astype(float) ** 2), rcond=None)[0]
        cx, cy = -D / 2, -E / 2
        far = np.argmax((xs - cx) ** 2 + (ys - cy) ** 2)
        north = round(math.degrees(math.atan2(xs[far] - cx, -(ys[far] - cy))) % 360, 1)

    # Walls: horizontal and vertical straight runs of the wall marks.
    min_len = int(0.35 * s)
    pieces = []
    for x0, y0, x1, y1 in runs_rectangles(walls_px, min_len):
        if y1 - y0 >= 4:
            pieces.append(("h", (y0 + y1) / 2, y1 - y0, x0, x1))
    for y0, x0, y1, x1 in runs_rectangles(walls_px.T, min_len):
        if x1 - x0 >= 4:
            pieces.append(("v", (x0 + x1) / 2, x1 - x0, y0, y1))
    # Collinear pieces of the same thickness are one wall where something is drawn in the gap between
    # them (window glass, a door's swing, a dashed head); an empty gap is where two walls simply end,
    # such as a corridor running between them.
    groups = []
    for axis, c, t, a, b in sorted(pieces, key=lambda p: (p[0], p[1], p[3])):
        g = next((g for g in groups if g["axis"] == axis and abs(g["c"] - c) <= 2.5 and abs(g["t"] - t) <= 3), None)
        if g is None:
            groups.append({"axis": axis, "c": c, "t": t, "pieces": [[a, b]]})
        else:
            g["pieces"].append([a, b])
    lines = []
    for g in groups:
        spans = []
        for a, b in sorted(g["pieces"]):
            if spans and a - spans[-1][1] <= 2:
                spans[-1][1] = max(spans[-1][1], b)
            else:
                spans.append([a, b])
        cur = None
        for a, b in spans:
            if cur is not None and a - cur["spans"][-1][1] <= 8 * s:
                found = classify(dark, cur, cur["spans"][-1][1], a, s, None, lambda x, y: (x, y))
                if found["kind"] != "gap":
                    cur["spans"].append([a, b])
                    continue
            cur = {"axis": g["axis"], "c": g["c"], "t": g["t"], "spans": [[a, b]]}
            lines.append(cur)
    # A piece fully inside a thicker wall's band is that wall seen side-on (a junction): drop it.
    def covered(ln):
        for other in lines:
            if other is ln or other["axis"] == ln["axis"] or other["t"] < ln["t"] - 1:
                continue
            a, b = ln["spans"][0][0], ln["spans"][-1][1]
            if other["c"] - other["t"] / 2 - 1 <= a and b <= other["c"] + other["t"] / 2 + 1:
                return True
        return False
    lines = [ln for ln in lines if not covered(ln) and (ln["spans"][-1][1] - ln["spans"][0][0]) >= 0.5 * s]

    # Snap each wall's ends to the centre of the wall it runs into, so walls meet cleanly.
    def snap(ln, end):
        p = ln["spans"][0][0] if end == 0 else ln["spans"][-1][1]
        for other in lines:
            if other["axis"] == ln["axis"]:
                continue
            lo, hi = other["c"] - other["t"] / 2 - 2, other["c"] + other["t"] / 2 + 2
            oa, ob = other["spans"][0][0] - 2, other["spans"][-1][1] + 2
            if lo <= p <= hi and oa <= ln["c"] <= ob:
                return other["c"] if not (other["t"] > ln["t"] + 3 and (p <= bx0 + other["t"] + 2 or p >= (bx1 if ln["axis"] == "h" else by1) - other["t"] - 2)) else other["c"]
        return p

    walls, openings = [], []
    for ln in lines:
        a, b = snap(ln, 0), snap(ln, 1)
        if ln["axis"] == "h":
            pa, pb = to_m(a, ln["c"]), to_m(b, ln["c"])
        else:
            pa, pb = to_m(ln["c"], b), to_m(ln["c"], a)  # vertical walls run upwards: a is the bottom
        wid = f"w{len(walls) + 1}"
        t_m = round(ln["t"] / s, 3)
        ext = (ln["axis"] == "h" and (abs(ln["c"] - by0) < ln["t"] or abs(ln["c"] - by1) < ln["t"])) or \
              (ln["axis"] == "v" and (abs(ln["c"] - bx0) < ln["t"] or abs(ln["c"] - bx1) < ln["t"]))
        walls.append({"id": wid, "a": list(pa), "b": list(pb), "thickness": t_m, "exterior": bool(ext)})
        for (s0, e0), (s1, e1) in zip(ln["spans"], ln["spans"][1:]):
            openings.append(classify(dark, ln, e0, s1, s, wid, to_m))

    # Rooms: what is left inside once the openings are closed.
    closed = walls_px.copy()
    for o in openings:
        closed[o["_px"][1]:o["_px"][3], o["_px"][0]:o["_px"][2]] = True
    free = ~closed[by0:by1, bx0:bx1]
    rl, rn = components(free)
    rooms = []
    min_area = (1.0 * s) ** 2
    small_crops = []
    for i in range(rn):
        m = rl == i
        if not free[m].all() or m.sum() < min_area:
            continue
        ys, xs = np.nonzero(m)
        if xs.min() == 0 or ys.min() == 0 or xs.max() == free.shape[1] - 1 or ys.max() == free.shape[0] - 1:
            continue  # touches the edge: outside the building
        poly = outline(m)
        rooms.append({"_mask": m, "_box": (xs.min() + bx0, ys.min() + by0, xs.max() + 1 + bx0, ys.max() + 1 + by0),
                      "area": round(m.sum() / s / s, 2),
                      "polygon": [list(to_m(px + bx0, py + by0)) for px, py in poly]})

    def words_in(room, ws):
        x0, y0, x1, y1 = room["_box"]
        hits = []
        for w in ws:
            cx, cy = w["box"][0] + w["box"][2] / 2, w["box"][1] + w["box"][3] / 2
            if x0 <= cx < x1 and y0 <= cy < y1 and room["_mask"][int(cy) - by0, int(cx) - bx0]:
                hits.append(w)
        return hits

    for room in rooms:
        ws = words_in(room, words)
        name = [w for w in ws if re.fullmatch(r"[A-Za-z' ]+", w["text"].strip())]
        area = [w for w in ws if re.match(r"\s*\d+(\.\d+)?\s*m", w["text"])]
        if not name or not area:  # small text: read the room again, enlarged
            x0, y0, x1, y1 = room["_box"]
            ws = words_in(room, ocr(png, (x0, y0, x1 - x0, y1 - y0, 2.5)))
            name = name or [w for w in ws if re.fullmatch(r"[A-Za-z' ]+", w["text"].strip())]
            area = area or [w for w in ws if re.match(r"\s*\d+(\.\d+)?\s*m", w["text"])]
        room["name"] = " ".join(w["text"].strip().upper() for w in sorted(name, key=lambda w: w["box"][1])) or None
        room["label_area"] = float(re.match(r"\s*(\d+(?:\.\d+)?)", area[0]["text"]).group(1)) if area else None

    rooms.sort(key=lambda r: (-r["polygon"][0][1], r["polygon"][0][0]))
    data = {
        "about": "Traced from the drawing by studio/plan/trace.py, from its pixels and words alone. Metres; x right, "
                 "y up the sheet, from the building's outside bottom-left corner.",
        "source": os.path.basename(png),
        "scale": {"px_per_m": round(s, 3), "from": f"scale bar {bar_len} px labelled {label['text'].strip()!r}",
                  "origin_px": [int(bx0), int(by1)]},
        "north_deg": north,
        "size": [round((bx1 - bx0) / s, 3), round((by1 - by0) / s, 3)],
        "walls": walls,
        "openings": [{k: v for k, v in o.items() if not k.startswith("_")} for o in openings],
        "rooms": [{"id": f"r{i + 1}", "name": r["name"], "area": r["area"], "label_area": r["label_area"],
                   "polygon": r["polygon"]} for i, r in enumerate(rooms)],
    }
    overall = [w for w in words if re.fullmatch(r"\d+\.\d\d", w["text"].strip())]
    widest = max(overall, key=lambda w: float(w["text"]), default=None)
    if widest:
        data["scale"]["check"] = {"widest_dimension_label": float(widest["text"]), "building_width_measured": data["size"][0]}
    for i, o in enumerate(data["openings"]):
        o["id"] = f"o{i + 1}"
    with open(out_json, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=1)
    print(f"{len(walls)} walls, {len(openings)} openings "
          f"({', '.join(f'{k} {sum(o['kind'] == k for o in openings)}' for k in ('window', 'door', 'double door', 'open'))}), "
          f"{len(rooms)} rooms; scale {s:.2f} px/m; north {north}°")


def classify(dark, ln, a, b, s, wid, to_m):
    """What fills the gap between a and b (pixels along the wall): window, door, double door or open."""
    c, t, axis = ln["c"], ln["t"], ln["axis"]
    lo, hi = int(round(c - t / 2)), int(round(c + t / 2))
    a, b = int(a), int(b)
    view = dark if axis == "h" else dark.T          # rows across the wall, columns along it
    band = view[max(0, lo - 2):hi + 2, a + 2:b - 2]
    full_lines = int((band.mean(axis=1) > 0.9).sum()) if band.size else 0
    dashed = int(((band.mean(axis=1) > 0.3) & (band.mean(axis=1) < 0.8)).sum()) if band.size else 0
    w = b - a

    def score(hinge, radius, side):
        face = hi if side > 0 else lo
        pts = []
        for k in range(24):  # the swing: a quarter circle from the free end round to the open leaf's tip
            th = math.pi / 2 * k / 23
            along = hinge + (radius * math.cos(th) * (1 if hinge == a else -1))
            across = face + side * radius * math.sin(th)
            pts.append((across, along))
        for k in range(12):  # the open leaf, square to the wall
            pts.append((face + side * radius * k / 11, hinge))
        good = 0
        for r_, c_ in pts:
            r0, c0 = int(round(r_)), int(round(c_))
            if 0 <= r0 < view.shape[0] and 0 <= c0 < view.shape[1] and view[max(0, r0 - 3):r0 + 4, max(0, c0 - 3):c0 + 4].any():
                good += 1
        return good / len(pts)

    best = ("open", 0.0, None, None)
    for side in (+1, -1):
        for hinge in (a, b):
            sc = score(hinge, w, side)
            if sc > best[1]:
                best = ("door", sc, "a" if hinge == a else "b", side)
        sc = (score(a, w / 2, side) + score(b, w / 2, side)) / 2
        if sc > best[1] + 0.02:
            best = ("double door", sc, "ab", side)
    if full_lines >= 2:
        kind, hinge, side = "window", None, None
    elif best[1] >= 0.8:
        kind, hinge, side = best[0], best[2], best[3]
    elif dashed >= 1:
        kind, hinge, side = "open", None, None
    else:
        kind, hinge, side = "gap", None, None
    if axis == "h":
        pa, pb = to_m(a, c), to_m(b, c)
        px = (a, lo, b, hi)
        swing = None if side is None else ("up" if side < 0 else "down")       # rows grow downwards on the sheet
    else:
        pa, pb = to_m(c, b), to_m(c, a)
        px = (lo, a, hi, b)
        swing = None if side is None else ("right" if side > 0 else "left")
    # hinge "a"/"b" is the end nearer the wall's start (left for walls across, bottom for walls up the sheet)
    if axis == "v" and hinge in ("a", "b"):
        hinge = "b" if hinge == "a" else "a"
    out = {"wall": wid, "kind": kind, "from": list(pa), "to": list(pb), "width": round(w / s, 3), "_px": px}
    if hinge:
        out.update(hinge=hinge, swing=swing)
    return out


def outline(mask):
    """The outline of a region as corner points, walking its edge (one loop; rooms have no holes here)."""
    h, w = mask.shape
    m = np.pad(mask, 1)
    edges = {}
    ys, xs = np.nonzero(m[1:-1, 1:-1])
    for y, x in zip(ys + 1, xs + 1):
        if not m[y - 1, x]:
            edges[(x, y)] = (x + 1, y)
        if not m[y, x + 1]:
            edges[(x + 1, y)] = (x + 1, y + 1)
        if not m[y + 1, x]:
            edges[(x + 1, y + 1)] = (x, y + 1)
        if not m[y, x - 1]:
            edges[(x, y + 1)] = (x, y)
    start = min(edges)
    pts, p = [start], edges[start]
    while p != start:
        pts.append(p)
        p = edges[p]
    corners = []
    for i, p in enumerate(pts):
        q, r = pts[i - 1], pts[(i + 1) % len(pts)]
        if (p[0] - q[0], p[1] - q[1]) != (r[0] - p[0], r[1] - p[1]):
            corners.append((p[0] - 1, p[1] - 1))
    return corners


if __name__ == "__main__":
    main()
