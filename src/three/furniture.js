// Adapted from House Control by 0xProbability, MIT licence: see THIRD_PARTY_NOTICES.md.
// Procedural furniture library. Every builder returns a Group standing on y = 0,
// centred on its footprint and facing +z; the plan's "rot" turns it from there.
import * as THREE from '../../vendor/three/three.module.js';
import { box, cyl, mat, at, rng } from './kit.js';

const WOOD = '#a98459';
const DARK_WOOD = '#5a4334';
const WHITE = '#eceae5';
const BLACK = '#1b1c21';
const METAL = '#9a9fa8';

const group = (...children) => {
  const g = new THREE.Group();
  g.add(...children.flat().filter(Boolean));
  return g;
};

function darker(hex, k = 0.75) {
  return `#${new THREE.Color(hex).multiplyScalar(k).getHexString()}`;
}

function legs(w, d, h, material, inset = 0.06, r = 0.022) {
  const out = [];
  for (const sx of [-1, 1]) for (const sz of [-1, 1]) {
    out.push(at(cyl(r, r * 0.8, h, material, 10), sx * (w / 2 - inset), 0, sz * (d / 2 - inset)));
  }
  return out;
}

function seating(width, depth, color, cushions) {
  const fabric = mat(color, { rough: 1 });
  const dark = mat(darker(color, 0.82), { rough: 1 });
  const arm = 0.2;
  const inner = width - arm * 2;
  const parts = [
    ...legs(width, depth, 0.1, mat(BLACK, { rough: 0.5 }), 0.08),
    at(box(width, 0.2, depth, dark, { r: 0.05 }), 0, 0.1, 0),
    at(box(inner, 0.52, 0.24, dark, { r: 0.09 }), 0, 0.3, -depth / 2 + 0.12),
  ];
  for (const sx of [-1, 1]) parts.push(at(box(arm, 0.36, depth, dark, { r: 0.08 }), sx * (width / 2 - arm / 2), 0.3, 0));
  const cw = inner / cushions;
  for (let i = 0; i < cushions; i++) {
    const x = -inner / 2 + cw * (i + 0.5);
    parts.push(at(box(cw - 0.02, 0.17, depth - 0.3, fabric, { r: 0.06 }), x, 0.3, 0.1));
    const back = at(box(cw - 0.04, 0.36, 0.16, fabric, { r: 0.07 }), x, 0.46, -depth / 2 + 0.3);
    back.rotation.x = -0.14;
    parts.push(back);
  }
  return group(parts);
}

function chair(color = BLACK) {
  const m = mat(color, { rough: 0.7 });
  const back = at(box(0.42, 0.4, 0.04, m, { r: 0.02 }), 0, 0.47, -0.2);
  back.rotation.x = -0.1;
  return group(...legs(0.42, 0.42, 0.44, m, 0.04, 0.015), at(box(0.44, 0.05, 0.44, m, { r: 0.02 }), 0, 0.42, 0), back);
}

function doorLines(width, height, y, z, count, material) {
  const out = [];
  for (let i = 1; i < count; i++) out.push(at(box(0.008, height, 0.006, material, { r: 0 }), -width / 2 + (width / count) * i, y, z));
  return out;
}

const builders = {
  rug({ size = [2, 1.4], color = '#3b4a66' }) {
    const g = group(
      at(box(size[0], 0.016, size[1], mat(color, { rough: 1 }), { r: 0.006 }), 0, 0, 0),
      at(box(size[0] - 0.24, 0.018, size[1] - 0.24, mat(darker(color, 1.18), { rough: 1 }), { r: 0.006 }), 0, 0, 0),
    );
    g.userData.flat = true;
    return g;
  },

  sofa({ width = 2.2, color = '#8b93a7', pillow = '#d8d7d2' }) {
    const g = seating(width, 0.95, color, width > 2 ? 3 : 2);
    // throw pillow
    const p = at(box(0.36, 0.36, 0.12, mat(pillow, { rough: 1 }), { r: 0.05 }), -width / 2 + 0.42, 0.46, -0.1);
    p.rotation.set(-0.25, 0.3, 0.1);
    g.add(p);
    if (width > 2) {
      const q = at(box(0.36, 0.36, 0.12, mat(darker(color, 0.88), { rough: 1 }), { r: 0.05 }), width / 2 - 0.42, 0.46, -0.1);
      q.rotation.set(-0.25, -0.3, -0.1);
      g.add(q);
    }
    return g;
  },

  armchair({ color = '#c28a5a' }) {
    return seating(0.92, 0.88, color, 1);
  },

  coffeeTable({ width = 1.1 }) {
    const wood = mat(WOOD, { rough: 0.6 });
    return group(
      at(box(width, 0.04, 0.58, wood, { r: 0.015 }), 0, 0.36, 0),
      at(box(width - 0.16, 0.02, 0.44, mat(BLACK, { rough: 0.5 }), { r: 0.008 }), 0, 0.14, 0),
      ...legs(width, 0.58, 0.36, mat(BLACK, { rough: 0.5 }), 0.07, 0.015),
      at(box(0.24, 0.035, 0.17, mat('#c9553f', { rough: 0.9 }), { r: 0.006 }), 0.22, 0.4, 0.05),
      at(cyl(0.05, 0.04, 0.09, mat(WHITE, { rough: 0.4 })), -0.3, 0.4, -0.08),
    );
  },

  tv({ width = 1.7, unit = DARK_WOOD, fronts = BLACK }) {
    const sw = width * 0.84;
    const sh = sw * 0.5625;
    const screen = new THREE.MeshStandardMaterial({
      color: '#05070c', roughness: 0.25, emissive: '#27407a', emissiveIntensity: 0.35,
    });
    const panel = at(box(sw - 0.02, sh - 0.02, 0.01, screen, { r: 0 }), 0, 0.745, -0.129);
    panel.userData.screen = true;
    return group(
      at(box(width, 0.36, 0.4, mat(unit, { rough: 0.6 }), { r: 0.015 }), 0, 0.1, 0),
      ...legs(width, 0.4, 0.1, mat(BLACK), 0.08, 0.015),
      ...doorLines(width, 0.3, 0.13, 0.2, 3, mat(fronts)),
      at(box(sw + 0.03, sh + 0.03, 0.035, mat(BLACK, { rough: 0.4 }), { r: 0.008 }), 0, 0.72, -0.15),
      panel,
      at(box(0.5, 0.07, 0.09, mat('#2a2c33', { rough: 0.7 }), { r: 0.02 }), 0, 0.46, 0.05),
    );
  },

  // A little screen for a camera's feed: a stand, a body and a glowing display.
  monitor({ width = 0.34, height = 0.23 }) {
    const body = mat('#22242a', { rough: 0.55 });
    const screen = new THREE.MeshStandardMaterial({
      color: '#05070c', roughness: 0.25, emissive: '#1d2c4d', emissiveIntensity: 0.25,
    });
    const panel = at(box(width - 0.045, height - 0.045, 0.008, screen, { r: 0 }), 0, 0.075 + height / 2, 0.012);
    panel.userData.screen = true;
    return group(
      at(cyl(0.062, 0.062, 0.012, body, 20), 0, 0.008, 0),
      at(cyl(0.012, 0.014, 0.075, body, 10), 0, 0.045, 0),
      at(box(width, height, 0.026, body, { r: 0.014 }), 0, 0.075 + height / 2, 0),
      panel,
    );
  },

  sideboard({ width = 1.6 }) {
    return group(
      ...legs(width, 0.42, 0.16, mat(BLACK), 0.07, 0.015),
      at(box(width, 0.6, 0.42, mat(WOOD, { rough: 0.6 }), { r: 0.015 }), 0, 0.16, 0),
      ...doorLines(width, 0.54, 0.19, 0.21, 4, mat(DARK_WOOD)),
      at(cyl(0.07, 0.05, 0.26, mat('#3d6b8c', { rough: 0.35 })), -width / 2 + 0.3, 0.76, 0),
      at(box(0.3, 0.05, 0.2, mat('#d8c9a8', { rough: 0.9 }), { r: 0.006 }), width / 2 - 0.35, 0.76, 0),
    );
  },

  diningSet({ width = 1.8, chairs = 6, top = '#b48d63', seat = '#2b2e37' }) {
    const depth = 0.95;
    const wood = mat(top, { rough: 0.55 });
    const g = group(
      at(box(width, 0.05, depth, wood, { r: 0.02 }), 0, 0.71, 0),
      ...legs(width, depth, 0.71, mat(BLACK, { rough: 0.5 }), 0.1, 0.028),
      at(cyl(0.16, 0.1, 0.07, mat(WHITE, { rough: 0.4 })), 0, 0.76, 0),
    );
    const perSide = Math.ceil(chairs / 2);
    for (let i = 0; i < chairs; i++) {
      const side = i < perSide ? 1 : -1;
      const k = i < perSide ? i : i - perSide;
      const n = i < perSide ? perSide : chairs - perSide;
      const c = chair(seat);
      c.position.set(-width / 2 + (width / n) * (k + 0.5), 0, side * (depth / 2 + 0.12));
      c.rotation.y = side > 0 ? Math.PI : 0;
      g.add(c);
    }
    return g;
  },

  island({ width = 2.0, stools = 3, base = '#39424f', top = '#e9e7e2' }) {
    const g = group(
      at(box(width - 0.12, 0.88, 0.62, mat(base, { rough: 0.7 }), { r: 0.015 }), 0, 0, -0.04),
      at(box(width, 0.05, 0.86, mat(top, { rough: 0.3 }), { r: 0.015 }), 0, 0.88, 0),
    );
    for (let i = 0; i < stools; i++) {
      const x = -width / 2 + (width / stools) * (i + 0.5);
      g.add(group(
        at(cyl(0.16, 0.16, 0.012, mat(BLACK, { rough: 0.4 })), x, 0, 0.62),
        at(cyl(0.015, 0.015, 0.64, mat(METAL, { rough: 0.3, metal: 0.8 }), 10), x, 0, 0.62),
        at(cyl(0.17, 0.15, 0.05, mat('#c28a5a', { rough: 0.9 })), x, 0.64, 0.62),
      ));
    }
    return g;
  },

  kitchen({ width = 3, upper = true, front = '#e4e1da', worktop = '#33363d' }) {
    const fronts = mat(front, { rough: 0.6 });
    const seam = mat(darker(front, 0.72));
    const metal = mat('#b9bcc2', { metal: 0.8, rough: 0.35 });
    const n = Math.max(2, Math.round(width / 0.6));
    const g = group(
      at(box(width, 0.1, 0.54, mat('#23262c', { rough: 0.8 }), { r: 0.01 }), 0, 0, -0.02),
      at(box(width, 0.76, 0.6, fronts, { r: 0.008 }), 0, 0.1, 0),
      ...doorLines(width, 0.72, 0.12, 0.3, n, seam),
      at(box(width + 0.02, 0.04, 0.66, mat(worktop, { rough: 0.3 }), { r: 0.008 }), 0, 0.86, 0.01),
      at(box(width, 0.6, 0.02, mat('#d7dadd', { rough: 0.25, metal: 0.05 }), { r: 0 }), 0, 0.9, -0.305),
      at(box(0.46, 0.02, 0.42, metal, { r: 0.01 }), -width / 4, 0.885, 0.02),
      at(box(0.4, 0.016, 0.34, mat('#70757d', { rough: 0.3, metal: 0.6 }), { r: 0.01 }), -width / 4, 0.893, 0.02),
      at(cyl(0.016, 0.016, 0.26, metal, 10), -width / 4, 0.9, -0.24),
      at(box(0.03, 0.028, 0.2, metal, { r: 0.008 }), -width / 4, 1.15, -0.15),
      at(box(0.58, 0.012, 0.5, mat('#0c0d10', { rough: 0.15 }), { r: 0 }), width / 4, 0.9, 0),
      ...[[-0.13, -0.11], [0.13, -0.11], [-0.13, 0.11], [0.13, 0.11]].map(([dx, dz]) =>
        at(cyl(0.075, 0.075, 0.008, mat('#1b1d22', { rough: 0.3 }), 20), width / 4 + dx, 0.908, dz)),
      at(box(0.56, 0.56, 0.02, mat('#101216', { rough: 0.18, metal: 0.6 }), { r: 0.01 }), width / 4, 0.14, 0.302),
      at(box(0.5, 0.022, 0.035, metal, { r: 0.01 }), width / 4, 0.74, 0.32),
    );
    for (let i = 0; i < n; i++) {
      g.add(at(box(0.12, 0.016, 0.02, metal, { r: 0.006 }), -width / 2 + (width / n) * (i + 0.5), 0.76, 0.307));
    }
    if (upper) {
      g.add(
        at(box(width, 0.72, 0.35, fronts, { r: 0.008 }), 0, 1.48, -0.125),
        ...doorLines(width, 0.66, 1.51, 0.05, n, seam),
        ...Array.from({ length: n }, (_, i) =>
          at(box(0.12, 0.016, 0.02, metal, { r: 0.006 }), -width / 2 + (width / n) * (i + 0.5), 1.54, 0.056)),
        at(box(0.6, 0.06, 0.5, metal, { r: 0.012 }), width / 4, 1.42, -0.05),
      );
    }
    return g;
  },

  fridge() {
    const body = mat('#c5c9d0', { rough: 0.35, metal: 0.5 });
    return group(
      at(box(0.7, 1.92, 0.68, body, { r: 0.025 }), 0, 0, 0),
      at(box(0.66, 0.008, 0.005, mat('#7c8088'), { r: 0 }), 0, 1.25, 0.34),
      at(box(0.02, 0.5, 0.03, mat('#70747c', { metal: 0.7, rough: 0.3 }), { r: 0.008 }), -0.26, 1.34, 0.35),
      at(box(0.02, 0.4, 0.03, mat('#70747c', { metal: 0.7, rough: 0.3 }), { r: 0.008 }), -0.26, 0.76, 0.35),
    );
  },

  bed({ width = 1.6, color = '#7f8fb5', frame = DARK_WOOD, headboard = null, blanket = null }) {
    const depth = 2.1;
    const linen = mat('#f1efea', { rough: 1 });
    const g = group(
      ...legs(width, depth - 0.14, 0.12, mat(frame, { rough: 0.7 }), 0.1, 0.03),
      at(box(width + 0.06, 0.18, depth + 0.02, mat(frame, { rough: 0.7 }), { r: 0.02 }), 0, 0.12, 0),
      at(box(width - 0.06, 0.2, depth - 0.08, linen, { r: 0.05 }), 0, 0.3, 0.02),
      at(box(width + 0.14, 1.04, 0.12, mat(headboard || darker(color, 0.62), { rough: 1 }), { r: 0.05 }), 0, 0, -depth / 2 - 0.03),
      at(box(width + 0.02, 0.15, depth * 0.68, mat(color, { rough: 1 }), { r: 0.07 }), 0, 0.5, depth * 0.15),
      at(box(width + 0.04, 0.06, 0.52, mat(darker(color, 0.84), { rough: 1 }), { r: 0.025 }), 0, 0.58, depth * 0.24),
    );
    if (blanket) g.add(at(box(width + 0.08, 0.045, 0.44, mat(blanket, { rough: 1 }), { r: 0.02 }), 0, 0.6, depth * 0.36));
    for (const sx of [-1, 1]) {
      const pillow = at(box(width / 2 - 0.14, 0.14, 0.42, linen, { r: 0.06 }), sx * width / 4, 0.52, -depth / 2 + 0.34);
      pillow.rotation.x = -0.2;
      g.add(pillow);
    }
    for (const sx of [-1, 1]) {
      const cushion = at(box(0.38, 0.11, 0.26, mat(darker(color, 1.16), { rough: 1 }), { r: 0.05 }), sx * width / 4 + 0.02, 0.6, -depth / 2 + 0.66);
      cushion.rotation.x = -0.32;
      g.add(cushion);
    }
    return g;
  },

  nightstand() {
    return group(
      at(box(0.46, 0.44, 0.4, mat(WOOD, { rough: 0.6 }), { r: 0.015 }), 0, 0.06, 0),
      ...legs(0.46, 0.4, 0.06, mat(BLACK), 0.06, 0.014),
      at(box(0.4, 0.006, 0.005, mat(DARK_WOOD), { r: 0 }), 0, 0.28, 0.2),
    );
  },

  dresser({ width = 1.3 }) {
    const g = group(
      ...legs(width, 0.45, 0.1, mat(BLACK), 0.06, 0.015),
      at(box(width, 0.74, 0.45, mat(WHITE, { rough: 0.6 }), { r: 0.015 }), 0, 0.1, 0),
      at(cyl(0.09, 0.07, 0.18, mat('#c9a15e', { rough: 0.4 })), width / 2 - 0.3, 0.84, 0),
    );
    for (let i = 1; i < 3; i++) g.add(at(box(width - 0.06, 0.006, 0.005, mat('#b9b6ae'), { r: 0 }), 0, 0.1 + 0.247 * i, 0.226));
    return g;
  },

  radiator({ width = 1.0, color = '#f2f1ed' }) {
    const body = mat(color, { rough: 0.5, metal: 0.15 });
    const valve = mat('#8d939c', { metal: 0.8, rough: 0.3 });
    const g = group(at(box(width, 0.52, 0.06, body, { r: 0.02 }), 0, 0.18, 0));
    const fins = Math.max(4, Math.round(width / 0.055));
    for (let i = 1; i < fins; i++) {
      g.add(at(box(0.012, 0.5, 0.075, body, { r: 0.004 }), -width / 2 + (width / fins) * i, 0.19, 0));
    }
    g.add(at(cyl(0.02, 0.02, 0.05, valve, 10), -width / 2 - 0.02, 0.66, 0.02));
    g.add(at(cyl(0.02, 0.02, 0.05, valve, 10), width / 2 + 0.02, 0.66, 0.02));
    return g;
  },

  bench({ width = 1.2, color = WOOD }) {
    const wood = mat(color, { rough: 0.62 });
    const dark = mat(darker(color, 0.78), { rough: 0.7 });
    const g = group(at(box(width - 0.1, 0.06, 0.3, dark, { r: 0.01 }), 0, 0.34, 0));
    for (let i = 0; i < 3; i++) {
      g.add(at(box(width, 0.035, 0.1, wood, { r: 0.008 }), 0, 0.4, -0.12 + i * 0.12));
    }
    for (const sx of [-1, 1]) for (const sz of [-1, 1]) {
      g.add(at(box(0.05, 0.34, 0.05, dark, { r: 0.008 }), sx * (width / 2 - 0.05), 0, sz * 0.11));
    }
    return g;
  },

  curtain({ width = 1.6, height = 2.3, color = '#8a8d92' }) {
    const fabric = mat(color, { rough: 1 });
    const g = group(
      at(box(width + 0.16, 0.025, 0.025, mat(METAL, { rough: 0.3, metal: 0.8 }), { r: 0.01 }), 0, height + 0.03, 0),
    );
    const panel = Math.min(0.5, width * 0.32);
    for (const sx of [-1, 1]) {
      const p = at(box(panel, height, 0.06, fabric, { r: 0.02 }), sx * (width / 2 - panel / 2 - 0.02), 0.02, 0);
      p.rotation.y = sx * 0.06;
      g.add(p);
    }
    return g;
  },

  plant({ height = 1.2 }) {
    const rand = rng(Math.round(height * 1000));
    const leaves = [mat('#3f7d52', { rough: 0.9 }), mat('#4f9462', { rough: 0.9 }), mat('#35694a', { rough: 0.9 })];
    const g = group(
      at(cyl(0.17, 0.12, 0.3, mat('#d7d0c4', { rough: 0.8 })), 0, 0, 0),
      at(cyl(0.15, 0.15, 0.02, mat('#3a2c22', { rough: 1 })), 0, 0.285, 0),
      at(cyl(0.015, 0.02, height * 0.55, mat('#6b4a33', { rough: 1 }), 8), 0, 0.3, 0),
    );
    const count = Math.round(6 + height * 5);
    for (let i = 0; i < count; i++) {
      const t = i / (count - 1);
      const y = 0.5 + t * (height - 0.62);
      const spread = 0.28 * Math.sin(Math.PI * (0.25 + t * 0.7));
      const a = rand() * Math.PI * 2;
      const blob = new THREE.Mesh(new THREE.IcosahedronGeometry(0.13 + rand() * 0.1, 1), leaves[i % 3]);
      blob.position.set(Math.cos(a) * spread * rand(), y, Math.sin(a) * spread * rand());
      blob.scale.y = 0.75 + rand() * 0.3;
      g.add(blob);
    }
    return g;
  },

  vanity({ width = 1.0 }) {
    const mirror = new THREE.MeshStandardMaterial({ color: '#b9c7dc', roughness: 0.12, metalness: 0.9 });
    return group(
      at(box(width, 0.62, 0.48, mat(WOOD, { rough: 0.6 }), { r: 0.012 }), 0, 0.2, 0),
      ...doorLines(width, 0.56, 0.23, 0.24, 2, mat(DARK_WOOD)),
      at(box(width + 0.03, 0.04, 0.5, mat(WHITE, { rough: 0.25 }), { r: 0.012 }), 0, 0.82, 0),
      at(cyl(0.19, 0.15, 0.1, mat(WHITE, { rough: 0.2 })), 0, 0.86, 0.02),
      at(cyl(0.012, 0.012, 0.2, mat(METAL, { rough: 0.2, metal: 0.9 }), 10), 0, 0.86, -0.18),
      at(box(width * 0.82, 0.8, 0.025, mirror, { r: 0.01 }), 0, 1.08, -0.225),
    );
  },

  bathtub() {
    return group(
      at(box(1.7, 0.56, 0.78, mat(WHITE, { rough: 0.25 }), { r: 0.1 }), 0, 0, 0),
      at(box(1.5, 0.02, 0.58, mat('#9fd3ec', { rough: 0.1, emissive: '#1d4f6b', emissiveIntensity: 0.25 }), { r: 0.009 }), 0, 0.545, 0),
      at(cyl(0.014, 0.014, 0.2, mat(METAL, { rough: 0.2, metal: 0.9 }), 10), -0.74, 0.56, 0),
    );
  },

  toilet() {
    const c = mat(WHITE, { rough: 0.25 });
    const bowl = at(cyl(0.19, 0.13, 0.4, c), 0, 0, 0.1);
    bowl.scale.z = 1.25;
    const lid = at(cyl(0.2, 0.2, 0.03, c), 0, 0.4, 0.1);
    lid.scale.z = 1.25;
    return group(at(box(0.38, 0.78, 0.17, c, { r: 0.03 }), 0, 0, -0.24), bowl, lid);
  },

  desk({ width = 1.4 }) {
    const c = chair('#2b2e37');
    c.position.z = 0.5;
    c.rotation.y = Math.PI;
    return group(
      at(box(width, 0.04, 0.65, mat(WOOD, { rough: 0.55 }), { r: 0.012 }), 0, 0.72, 0),
      ...legs(width, 0.65, 0.72, mat(BLACK), 0.06, 0.02),
      at(box(0.56, 0.34, 0.025, mat(BLACK, { rough: 0.3 }), { r: 0.008 }), 0, 0.86, -0.18),
      at(box(0.2, 0.1, 0.12, mat(BLACK), { r: 0.008 }), 0, 0.76, -0.18),
      c,
    );
  },

  wardrobe({ width = 1.6, height = 2.1 }) {
    return group(
      at(box(width, height, 0.6, mat(WHITE, { rough: 0.6 }), { r: 0.015 }), 0, 0, 0),
      ...doorLines(width, height - 0.08, 0.04, 0.3, Math.max(2, Math.round(width / 0.55)), mat('#b9b6ae')),
    );
  },

  bookshelf({ width = 1.0, height = 1.8 }) {
    const rand = rng(Math.round(width * 100 + height * 7));
    const wood = mat(WOOD, { rough: 0.6 });
    const g = group(at(box(width, height, 0.04, wood, { r: 0 }), 0, 0, -0.14));
    for (const sx of [-1, 1]) g.add(at(box(0.03, height, 0.32, wood, { r: 0 }), sx * (width / 2 - 0.015), 0, 0));
    const shelves = Math.round(height / 0.38);
    const colors = ['#c9553f', '#3d6b8c', '#d8c9a8', '#4f9462', '#8b93a7', '#d9b98a'];
    for (let i = 0; i <= shelves; i++) {
      const y = (height - 0.03) * (i / shelves);
      g.add(at(box(width, 0.03, 0.32, wood, { r: 0 }), 0, y, 0));
      if (i === shelves) break;
      let x = -width / 2 + 0.06;
      while (x < width / 2 - 0.12) {
        const bw = 0.03 + rand() * 0.04;
        const bh = 0.2 + rand() * 0.1;
        g.add(at(box(bw, bh, 0.2, mat(colors[Math.floor(rand() * colors.length)], { rough: 0.9 }), { r: 0 }), x + bw / 2, y + 0.03, 0));
        x += bw + 0.004;
        if (rand() < 0.12) x += 0.12;
      }
    }
    return g;
  },
};

export const FURNITURE_TYPES = Object.keys(builders);
export const piece = (type, options = {}) => builders[type](options);

// Approximate [width, depth] of each piece, for the 2D plan editor.
export function footprint(item) {
  const w = item.width;
  switch (item.type) {
    case 'rug': return item.size || [2, 1.4];
    case 'sofa': return [w || 2.2, 0.95];
    case 'armchair': return [0.92, 0.88];
    case 'coffeeTable': return [w || 1.1, 0.58];
    case 'tv': return [w || 1.7, 0.4];
    case 'monitor': return [item.width || 0.34, 0.2];
    case 'sideboard': return [w || 1.6, 0.42];
    case 'diningSet': return [w || 1.8, 1.9];
    case 'island': return [w || 2, 1.1];
    case 'kitchen': return [w || 3, 0.62];
    case 'fridge': return [0.7, 0.68];
    case 'bed': return [(w || 1.6) + 0.1, 2.14];
    case 'nightstand': return [0.46, 0.4];
    case 'dresser': return [w || 1.3, 0.45];
    case 'plant': return [0.45, 0.45];
    case 'vanity': return [w || 1, 0.5];
    case 'bathtub': return [1.7, 0.78];
    case 'toilet': return [0.4, 0.66];
    case 'desk': return [w || 1.4, 0.65];
    case 'wardrobe': return [w || 1.6, 0.6];
    case 'bookshelf': return [w || 1, 0.32];
    case 'bench': return [w || 1.2, 0.38];
    case 'curtain': return [w || 1.6, 0.08];
    case 'radiator': return [w || 1.0, 0.12];
    default: return [0.6, 0.6];
  }
}

export function buildFurniture(items) {
  const root = new THREE.Group();
  for (const item of items) {
    const make = builders[item.type];
    if (!make || !Array.isArray(item.pos)) {
      console.warn(`[plan] skipping furniture of unknown type "${item.type}"`);
      continue;
    }
    const g = make(item);
    g.position.set(item.pos[0], item.y || 0, item.pos[1]);
    g.rotation.y = THREE.MathUtils.degToRad(item.rot || 0);
    g.userData.item = item;
    const flat = g.userData.flat;
    g.traverse((o) => {
      if (o.isMesh) { o.castShadow = !flat; o.receiveShadow = true; }
    });
    root.add(g);
  }
  return root;
}
