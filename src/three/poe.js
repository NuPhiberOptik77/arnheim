// Poe, the receptionist: one person standing behind the front desk, in the building's warm,
// smooth style. Plain data in (POE below), a figure out, made only from Three.js shapes: no
// textures, no downloads. Three parts can move (the body, the chest and the head), and each is
// merged by material, so the whole person costs about a dozen draw calls.
import * as THREE from '../../vendor/three/three.module.js';
import { freeze, mat } from './kit.js';

export const POE = {
  name: 'Poe',
  href: '#/poe',
  // Where they stand in their room, behind the desk, and which way they face (towards the camera).
  at: [2.5, 0, 2.72],
  turn: 0.26,
  look: 0.16, // the head turns a little further than the body
  colors: {
    skin: '#c8926e', lips: '#a65f57', eyes: '#241815', whites: '#f1ece6', hair: '#3a261f',
    coat: '#2f4a5c', lapel: '#223646', shirt: '#efe6d6', square: '#e0a85a', brass: '#d2a35c',
    trousers: '#27303d', shoes: '#1a1b20',
  },
  // A faint warm fill, [colour, strength], so they still read in a dim room.
  fill: { skin: ['#6b3a22', 0.22], hair: ['#2a1810', 0.16], coat: ['#18303f', 0.28], shirt: ['#4d4436', 0.22] },
  // The tailored coat from hem to collar, as [radius, height]; the body is this made oval.
  coat: [[0.148, 0.835], [0.156, 0.9], [0.14, 1.0], [0.12, 1.1], [0.128, 1.2], [0.148, 1.3], [0.162, 1.38], [0.163, 1.43], [0.135, 1.47], [0.085, 1.5], [0.06, 1.515]],
  depth: 0.64,
  waist: 1.1,
  neck: 1.585,
  head: { y: 1.69, z: 0.006, w: 0.093, h: 0.122, d: 0.1 },
  // Where the hair stops, by angle around the head (0 is the face): short and cropped on their
  // right, longer on their left. Heights run from -1 (chin) to 1 (crown).
  hairline: {
    long: [[0, 0.5], [0.55, 0.44], [1.1, 0.05], [1.6, -0.35], [2.3, -0.7], [3.15, -0.8]],
    short: [[0, 0.5], [0.55, 0.47], [1.05, 0.22], [1.45, 0.12], [1.75, -0.08], [2.3, -0.5], [3.15, -0.66]],
  },
  // Locks on the long side and a swept fringe: points are [angle, height, distance from the head].
  locks: [
    { r: [0.03, 0.012], path: [[0.15, 0.93, 1.1], [0.6, 0.78, 1.13], [1.0, 0.45, 1.15], [1.15, 0.05, 1.17], [1.2, -0.4, 1.2], [1.2, -0.92, 1.22]] },
    { r: [0.034, 0.014], path: [[0, 0.98, 1.08], [0.9, 0.75, 1.13], [1.45, 0.35, 1.15], [1.6, -0.1, 1.18], [1.6, -0.55, 1.2], [1.55, -0.95, 1.2]] },
    { r: [0.032, 0.012], path: [[-0.2, 0.95, 1.08], [1.4, 0.8, 1.12], [2.0, 0.4, 1.14], [2.1, -0.1, 1.16], [2.05, -0.55, 1.16], [2.0, -0.85, 1.14]] },
    { r: [0.03, 0.012], path: [[3.1, 0.9, 1.06], [2.6, 0.5, 1.1], [2.55, 0, 1.12], [2.5, -0.5, 1.1]] },
    { r: [0.018, 0.011], path: [[-0.45, 0.82, 1.06], [-0.1, 0.8, 1.09], [0.35, 0.68, 1.12], [0.7, 0.5, 1.13], [0.95, 0.25, 1.13]] },
    { r: [0.02, 0.012], path: [[-0.1, 0.9, 1.05], [-0.6, 0.8, 1.05], [-1.0, 0.55, 1.04]] },
  ],
};

const bump = (x, c, w) => Math.exp(-(((x - c) / w) ** 2));
const smooth = (a, b, x) => { const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); };
const table = (rows, a) => {
  for (let i = 1; i < rows.length; i++) {
    if (a <= rows[i][0]) { const [a0, v0] = rows[i - 1]; const [a1, v1] = rows[i]; return v0 + ((v1 - v0) * (a - a0)) / (a1 - a0); }
  }
  return rows[rows.length - 1][1];
};

// The head: a taller sphere with soft cheekbones, a defined jaw and a chin brought forward a touch.
function headShape(P) {
  const { w, h, d, y: cy, z: cz } = P.head;
  const width = (y) => 1 + 0.08 * bump(y, -0.58, 0.2) + 0.04 * bump(y, -0.05, 0.22) - 0.06 * smooth(0.45, 1, y);
  const unit = (x, y, z, grow = 1) => new THREE.Vector3(
    x * w * width(y) * grow, cy + y * h * grow, cz + z * d * (z > 0 ? 1 + 0.06 * bump(y, -0.82, 0.14) : 1.04) * grow);
  const point = (a, y, grow = 1) => { const s = Math.sqrt(Math.max(0, 1 - y * y)); return unit(Math.sin(a) * s, y, Math.cos(a) * s, grow); };
  const face = (a, y, out = 0) => point(a, y).add(new THREE.Vector3(Math.sin(a) * out, 0, Math.cos(a) * out));
  return { unit, point, face };
}

// A sphere bent into shape, optionally keeping only some of its triangles. The seam sits at the back.
function shaped(segW, segH, place, keep) {
  const geo = new THREE.SphereGeometry(1, segW, segH, -Math.PI / 2);
  const pos = geo.attributes.position;
  const unit = pos.array.slice();
  for (let i = 0; i < pos.count; i++) {
    const p = place(unit[i * 3], unit[i * 3 + 1], unit[i * 3 + 2]);
    pos.setXYZ(i, p.x, p.y, p.z);
  }
  if (keep) {
    const index = geo.index.array;
    const kept = [];
    for (let i = 0; i < index.length; i += 3) {
      let x = 0; let y = 0; let z = 0;
      for (let k = 0; k < 3; k++) { const j = index[i + k] * 3; x += unit[j]; y += unit[j + 1]; z += unit[j + 2]; }
      if (keep(x / 3, y / 3, z / 3)) kept.push(index[i], index[i + 1], index[i + 2]);
    }
    geo.setIndex(kept);
  }
  geo.computeVertexNormals();
  return geo;
}

// A soft, slightly flat lock of hair along a curve, thick at the root and fine at the tip.
function lock(points, r0, r1, flat = 0.7) {
  const curve = new THREE.CatmullRomCurve3(points);
  const seg = 20;
  const rad = 8;
  const geo = new THREE.TubeGeometry(curve, seg, 1, rad, false);
  const pos = geo.attributes.position;
  for (let i = 0; i <= seg; i++) {
    const t = i / seg;
    const c = curve.getPointAt(t);
    const n = geo.normals[i];
    const b = geo.binormals[i];
    const r = (r0 + (r1 - r0) * t) * (1 + 0.2 * Math.sin(Math.PI * t));
    for (let j = 0; j <= rad; j++) {
      const v = (j / rad) * Math.PI * 2;
      const s = Math.sin(v) * flat;
      const k = -Math.cos(v);
      pos.setXYZ(i * (rad + 1) + j, c.x + r * (k * n.x + s * b.x), c.y + r * (k * n.y + s * b.y), c.z + r * (k * n.z + s * b.z));
    }
  }
  geo.computeVertexNormals();
  return geo;
}

const v3 = (p) => (p.isVector3 ? p.clone() : new THREE.Vector3(...p));

function ball(p, r, material, scale = [1, 1, 1], turn = 0, tilt = 0) {
  const m = new THREE.Mesh(new THREE.SphereGeometry(r, 16, 12), material);
  m.position.copy(v3(p));
  m.scale.set(...scale);
  m.rotation.set(0, turn, tilt);
  return m;
}

// A tapered tube from a to b; limb() adds round ends.
function tube(a, b, ra, rb, material) {
  const A = v3(a);
  const B = v3(b);
  const m = new THREE.Mesh(new THREE.CylinderGeometry(rb, ra, A.distanceTo(B), 14, 1, true), material);
  m.position.copy(A).add(B).multiplyScalar(0.5);
  m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), B.clone().sub(A).normalize());
  return m;
}
const limb = (a, b, ra, rb, material) => [tube(a, b, ra, rb, material), ball(a, ra, material), ball(b, rb, material)];

// A panel lying on the coat's front (lapels, the shirt, a pocket square), between two edges.
function strip(surface, y0, y1, left, right, lift, material, rows = 10, cols = 4) {
  const pos = [];
  const uv = [];
  const idx = [];
  for (let i = 0; i <= rows; i++) {
    const y = y0 + ((y1 - y0) * i) / rows;
    const xl = left(y);
    const xr = right(y);
    for (let j = 0; j <= cols; j++) {
      const x = xl + ((xr - xl) * j) / cols;
      pos.push(x, y, surface(x, y) + lift);
      uv.push(j / cols, i / rows);
    }
  }
  for (let i = 0; i < rows; i++) {
    for (let j = 0; j < cols; j++) {
      const a = i * (cols + 1) + j;
      idx.push(a, a + 1, a + cols + 2, a, a + cols + 2, a + cols + 1);
    }
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  geo.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
  geo.setIndex(idx);
  geo.computeVertexNormals();
  return new THREE.Mesh(geo, material);
}

// Merge a part by material, then let it turn about its own pivot.
function settle(group, pivot) {
  freeze(group);
  for (const m of group.children) {
    if (!m.isMesh || m.userData.live) continue;
    m.geometry.translate(-pivot[0], -pivot[1], -pivot[2]);
    m.userData.live = true;
  }
  group.position.set(...pivot);
}

export function buildPerson(P = POE) {
  const c = P.colors;
  const paint = (key, rough, extra = {}) => {
    const f = P.fill[key];
    return mat(c[key], { rough, ...(f ? { emissive: f[0], emissiveIntensity: f[1] } : {}), ...extra });
  };
  const M = {
    skin: paint('skin', 0.55), lips: paint('lips', 0.5), eyes: paint('eyes', 0.3), whites: paint('whites', 0.4), hair: paint('hair', 0.45),
    coat: paint('coat', 0.7), lapel: paint('lapel', 0.45), shirt: paint('shirt', 0.8), square: paint('square', 0.6),
    brass: paint('brass', 0.3, { metal: 0.7 }), trousers: paint('trousers', 0.8), shoes: paint('shoes', 0.35),
  };
  const S = headShape(P);
  const root = new THREE.Group();
  const upper = new THREE.Group();
  const head = new THREE.Group();

  /* ---------- head and hair ---------- */
  head.add(new THREE.Mesh(shaped(40, 28, (x, y, z) => S.unit(x, y, z)), M.skin));
  const line = (x, z) => { const a = Math.atan2(x, z); return table(a >= 0 ? P.hairline.long : P.hairline.short, Math.abs(a)); };
  const hairAt = (x, y, z) => {
    const over = smooth(0, 0.28, y - line(x, z));
    return S.unit(x, y, z, 1.012 + (0.025 + 0.05 * smooth(-0.3, 0.7, x) + 0.03 * smooth(0.3, 1, y)) * over);
  };
  head.add(new THREE.Mesh(shaped(48, 32, hairAt, (x, y, z) => y > line(x, z)), M.hair));
  for (const L of P.locks) head.add(new THREE.Mesh(lock(L.path.map(([a, y, g]) => S.point(a, y, g)), ...L.r), M.hair));
  for (const side of [-1, 1]) {
    const a = 0.37 * side;
    head.add(
      ball(S.face(a, 0.1, -0.001), 1, M.whites, [0.0155, 0.0072, 0.005], a),
      ball(S.face(a * 0.97, 0.1, 0.0035), 1, M.eyes, [0.0062, 0.0062, 0.003], a),
      ball(S.face(a, 0.16, 0.0005), 1, M.eyes, [0.0165, 0.0026, 0.0055], a, 0.05 * side),
      ...limb(S.face(0.15 * side, 0.37, 0.001), S.face(0.42 * side, 0.405, 0.001), 0.0042, 0.0036, M.hair),
      ...limb(S.face(0.42 * side, 0.405, 0.001), S.face(0.62 * side, 0.33, 0.001), 0.0036, 0.0026, M.hair),
    );
  }
  head.add(
    ball(S.face(0, -0.08, -0.002), 1, M.skin, [0.0095, 0.03, 0.012]),
    ball(S.face(0, -0.25, 0.004), 0.011, M.skin, [1, 0.85, 1]),
    ball(S.face(0, -0.5, -0.002), 1, M.lips, [0.02, 0.0052, 0.008]),
    ball(S.face(0, -0.565, -0.002), 1, M.lips, [0.018, 0.0062, 0.0085]),
    ball(S.point(-Math.PI / 2, 0, 0.99), 1, M.skin, [0.011, 0.026, 0.017]), // the ear on the short side
  );

  /* ---------- the tailored coat, shirt and arms ---------- */
  const profile = new THREE.SplineCurve(P.coat.map(([r, y]) => new THREE.Vector2(r, y))).getPoints(40);
  const radiusAt = (y) => {
    for (let i = 1; i < profile.length; i++) {
      if (y <= profile[i].y) { const a = profile[i - 1]; const b = profile[i]; return a.x + ((b.x - a.x) * (y - a.y)) / ((b.y - a.y) || 1); }
    }
    return profile[profile.length - 1].x;
  };
  const front = (x, y) => P.depth * Math.sqrt(Math.max(0, radiusAt(y) ** 2 - x * x));
  const body = new THREE.LatheGeometry(profile, 32, Math.PI);
  body.scale(1, 1, P.depth);
  upper.add(new THREE.Mesh(body, M.coat));
  const vee = (y) => 0.052 * Math.max(0, (y - 1.24) / 0.265) ** 0.9;
  const lapel = (y) => (y > 1.39 ? 0.022 + (0.032 * (1.5 - y)) / 0.11 : 0.054 * Math.max(0, (y - 1.19) / 0.2));
  upper.add(
    strip(front, 1.24, 1.505, (y) => -vee(y), vee, 0.0025, M.shirt),
    strip(front, 1.19, 1.5, (y) => -vee(y) - lapel(y), (y) => -vee(y) + 0.002, 0.005, M.lapel),
    strip(front, 1.19, 1.5, (y) => vee(y) - 0.002, (y) => vee(y) + lapel(y), 0.005, M.lapel),
    strip(front, 0.84, 1.18, () => -0.0025, () => 0.0025, 0.002, M.lapel, 6, 1),
    strip(front, 1.325, 1.348, () => 0.072, () => 0.106, 0.004, M.square, 2, 2),
    ball([0, 1.185, front(0, 1.185) + 0.006], 0.0085, M.brass, [1, 1, 0.5]),
    ball([0.066, 1.43, front(0.066, 1.43) + 0.009], 0.0065, M.brass),
    ...limb([0, 1.47, 0], [0, 1.6, 0.008], 0.05, 0.045, M.skin),
    tube([0, 1.488, 0.002], [0, 1.545, 0.006], 0.06, 0.056, M.shirt),
  );
  for (const side of [-1, 1]) {
    const sh = [0.172 * side, 1.425, -0.01];
    const el = [0.212 * side, 1.17, 0.035];
    const wr = [0.135 * side, 1.08, 0.255];
    const hand = new THREE.Vector3(0.112 * side, 1.052, 0.305);
    upper.add(
      ball([0.162 * side, 1.44, -0.008], 1, M.coat, [0.05, 0.03, 0.06]),
      ...limb(sh, el, 0.05, 0.043, M.coat),
      ...limb(el, wr, 0.043, 0.037, M.coat),
      tube(wr, v3(wr).lerp(hand, 0.3), 0.036, 0.034, M.shirt),
      ball(hand, 1, M.skin, [0.03, 0.017, 0.052], -0.35 * side),
      ball(hand.clone().add(new THREE.Vector3(-0.026 * side, 0.006, -0.012)), 1, M.skin, [0.01, 0.009, 0.022], -0.5 * side),
    );
  }

  /* ---------- legs, mostly hidden by the desk ---------- */
  for (const side of [-1, 1]) {
    root.add(
      ...limb([0.072 * side, 0.9, 0], [0.074 * side, 0.48, 0.012], 0.062, 0.05, M.trousers),
      ...limb([0.074 * side, 0.48, 0.012], [0.074 * side, 0.085, -0.005], 0.05, 0.042, M.trousers),
      ball([0.074 * side, 0.036, 0.04], 1, M.shoes, [0.046, 0.036, 0.105]),
    );
  }

  settle(head, [0, P.neck, P.head.z]);
  settle(upper, [0, P.waist, 0]);
  head.position.y -= P.waist;
  upper.add(head);
  settle(root, [0, 0, 0]);
  root.add(upper);
  root.position.set(...P.at);
  root.rotation.y = P.turn;
  head.rotation.y = P.look;

  return {
    group: root,
    // Gentle breathing and a slow look around. Only called while the page is awake.
    tick(t) {
      const b = Math.sin(t * 1.5);
      upper.scale.set(1 + 0.004 * b, 1 + 0.005 * b, 1 + 0.012 * b);
      head.rotation.y = P.look + 0.12 * Math.sin(t * 0.33);
      head.rotation.x = 0.02 * Math.sin(t * 0.21);
    },
  };
}
