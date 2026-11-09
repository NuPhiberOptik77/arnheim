// The receptionist: one person standing behind the front desk, in the building's warm, smooth
// style. Plain data in (POE below, which a page renames and dresses with receptionistSpec), a
// figure out, made only from Three.js shapes: no
// textures, no downloads. Three parts can move (the body, the chest and the head), and each is
// merged by material, so the whole person costs about a dozen draw calls. The people at work
// (buildSeated, at the end) are made the same way, seated and plainer.
import * as THREE from '../../vendor/three/three.module.js';
import { freeze, mat } from './kit.js';

export const POE = {
  name: 'Receptionist', // the company map gives them a name (org.receptionist, receptionistSpec)
  title: 'Receptionist',
  href: '#/front-desk',
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

// A sphere bent into shape, optionally keeping only some of its triangles: those whose middle
// passes `keep`, or with `any`, those with any corner that passes (so `place` can pull the rest
// onto a clean edge). The seam sits at the back.
function shaped(segW, segH, place, keep, any = false) {
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
      let x = 0; let y = 0; let z = 0; let hit = false;
      for (let k = 0; k < 3; k++) {
        const j = index[i + k] * 3;
        x += unit[j]; y += unit[j + 1]; z += unit[j + 2];
        if (any && keep(unit[j], unit[j + 1], unit[j + 2])) hit = true;
      }
      if (any ? hit : keep(x / 3, y / 3, z / 3)) kept.push(index[i], index[i + 1], index[i + 2]);
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

// A braid along a curve: two strands of small beads winding round each other, thinning towards
// the end. Gives the beads and the curve, so ties and clips can be put on it.
function braid(points, r, material, turns = 6) {
  const curve = new THREE.CatmullRomCurve3(points);
  const steps = turns * 4;
  const frames = curve.computeFrenetFrames(steps, false);
  const bead = new THREE.SphereGeometry(1, 10, 8);
  const along = new THREE.Vector3(0, 0, 1);
  const beads = [];
  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    const rr = r * (1 - 0.3 * t);
    for (const strand of [0, Math.PI]) {
      const a = t * turns * Math.PI * 2 + strand;
      const m = new THREE.Mesh(bead, material);
      m.position.copy(curve.getPointAt(t))
        .addScaledVector(frames.normals[i], Math.cos(a) * rr * 0.42)
        .addScaledVector(frames.binormals[i], Math.sin(a) * rr * 0.42);
      m.quaternion.setFromUnitVectors(along, frames.tangents[i]);
      m.scale.set(rr * 0.66, rr * 0.66, rr * 1.05);
      beads.push(m);
    }
  }
  return { beads, curve, frames };
}

// A small flower lying on a surface: petals round a centre, facing out along `out`.
function flower(at, out, size, petals, centre, count = 5) {
  const g = new THREE.Group();
  g.position.copy(at);
  g.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), out.clone().normalize());
  for (let k = 0; k < count; k++) {
    const a = (k / count) * Math.PI * 2;
    g.add(ball([Math.cos(a) * size, Math.sin(a) * size, 0], 1, petals, [size * 0.8, size * 0.8, size * 0.42]));
  }
  g.add(ball([0, 0, size * 0.2], 1, centre, [size * 0.5, size * 0.5, size * 0.4]));
  return g;
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
    skin: paint('skin', 0.55), lips: paint('lips', 0.5), eyes: paint('eyes', 0.3), whites: paint('whites', 0.4), hair: paint('hair', P.hairRough ?? 0.45),
    coat: paint('coat', 0.7), lapel: paint('lapel', 0.45), shirt: paint('shirt', 0.8), square: paint('square', 0.6),
    brass: paint('brass', 0.3, { metal: P.collar === 'round' ? 0 : 0.7 }), trousers: paint('trousers', 0.8), shoes: paint('shoes', 0.35),
    gold: mat(c.gold || c.brass, { rough: 0.3, metal: 0.7 }),
  };
  const S = headShape(P);
  const root = new THREE.Group();
  const upper = new THREE.Group();
  const head = new THREE.Group();

  /* ---------- head and hair ---------- */
  head.add(new THREE.Mesh(shaped(40, 28, (x, y, z) => S.unit(x, y, z)), M.skin));
  const line = (x, z) => { const a = Math.atan2(x, z); return table(a >= 0 ? P.hairline.long : P.hairline.short, Math.abs(a)); };
  // How far the hair stands out from the head, once past the hairline: the default sweeps to one side.
  const volume = P.volume || ((x, y) => 0.025 + 0.05 * smooth(-0.3, 0.7, x) + 0.03 * smooth(0.3, 1, y));
  const ramp = P.ramp || 0.28; // how soon past the hairline the hair reaches its full volume
  // Points just below the hairline are pulled up onto it, so its edge is a clean line, not steps.
  const hairAt = (x, y, z) => {
    const edge = line(x, z);
    if (y < edge) {
      const a = Math.atan2(x, z);
      const s = Math.sqrt(1 - edge * edge);
      [x, y, z] = [Math.sin(a) * s, edge, Math.cos(a) * s];
    }
    return S.unit(x, y, z, 1.012 + volume(x, y, z) * smooth(0, ramp, y - edge));
  };
  const [hairW, hairH] = P.hairDetail || [48, 32];
  head.add(new THREE.Mesh(shaped(hairW, hairH, hairAt, (x, y, z) => y > line(x, z), true), M.hair));
  for (const L of P.locks) head.add(new THREE.Mesh(lock(L.path.map(([a, y, g]) => S.point(a, y, g)), ...L.r), M.hair));
  if (P.bun) head.add(ball(S.point(Math.PI, P.bun.y, P.bun.out), 1, M.hair, [P.bun.r, P.bun.r * 0.9, P.bun.r]));
  // A centre parting from the hairline over the crown: a thin line of scalp lying on the hair.
  if (P.part) {
    const lift = (y) => 1.016 + volume(0, y, 1) * smooth(0, ramp, y - line(0, 1));
    const path = [[0, P.hairline.long[0][1] + 0.03], [0, 0.8], [0, 0.97], [Math.PI, 0.9], [Math.PI, 0.72]];
    head.add(new THREE.Mesh(lock(path.map(([a, y]) => S.point(a, y, lift(y))), 0.0016, 0.0016, 2.6), M.skin));
  }
  // Braids, each held by a tie near its root and a clip further down.
  const centre = new THREE.Vector3(0, P.head.y, P.head.z);
  for (const B of P.braids || []) {
    const { beads, curve, frames } = braid(B.path.map(([a, y, g]) => S.point(a, y, g)), B.r, M.hair, B.turns);
    head.add(...beads);
    if (B.tie) {
      const tie = new THREE.Mesh(new THREE.TorusGeometry(B.r * 0.95, B.r * 0.42, 8, 20), mat(B.tie, { rough: 0.55 }));
      tie.position.copy(curve.getPointAt(0.04));
      tie.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), frames.tangents[0]);
      head.add(tie);
    }
    if (B.clip) {
      const p = curve.getPointAt(B.clipAt ?? 0.72);
      const out = p.clone().sub(centre).normalize();
      head.add(flower(p.clone().addScaledVector(out, B.r * 0.7), out, B.r * 0.62, mat(B.clip, { rough: 0.35 }), mat(B.clip, { rough: 0.25 })));
    }
  }
  const eye = P.eyeSize || 1;
  for (const side of [-1, 1]) {
    const a = 0.37 * side;
    head.add(
      ball(S.face(a, 0.1, -0.001), 1, M.whites, [0.0155 * eye, 0.0072 * eye, 0.005], a),
      ball(S.face(a * 0.97, 0.1, 0.0035), 1, M.eyes, [0.0062 * eye, 0.0062 * eye, 0.003], a),
      ball(S.face(a, 0.16, 0.0005), 1, M.eyes, [0.0165, 0.0026, 0.0055], a, 0.05 * side),
      ...limb(S.face(0.15 * side, 0.37, 0.001), S.face(0.42 * side, 0.405, 0.001), 0.0042, 0.0036, M.hair),
      ...limb(S.face(0.42 * side, 0.405, 0.001), S.face(0.62 * side, 0.33, 0.001), 0.0036, 0.0026, M.hair),
    );
  }
  head.add(
    ball(S.face(0, -0.08, -0.002), 1, M.skin, [0.0095, 0.03, 0.012]),
    ball(S.face(0, -0.25, 0.004), 0.011, M.skin, P.noseTip || [1, 0.85, 1]),
    ball(S.face(0, -0.5, -0.002), 1, M.lips, [0.02, 0.0052, 0.008]),
    ball(S.face(0, -0.565, -0.002), 1, M.lips, [0.018, 0.0062, 0.0085]),
  );
  // The ears: the default cut's long side covers one, so only the short side shows unless the spec says both.
  const ears = P.ears === 'both' ? [-1, 1] : [-1];
  for (const side of ears) {
    head.add(ball(S.point((side * Math.PI) / 2, 0, 0.99), 1, M.skin, [0.011, 0.026, 0.017]));
    if (P.earrings === 'studs') {
      head.add(ball(S.point(side * (Math.PI / 2 - 0.08), -0.15, 1.1), 0.0034, M.gold));
    } else if (P.earrings) {
      const hoop = new THREE.Mesh(new THREE.TorusGeometry(0.011, 0.0022, 8, 24), M.gold);
      hoop.position.copy(S.point((side * Math.PI) / 2, -0.28, 1.06));
      hoop.rotation.y = Math.PI / 2; // hanging flat against the side of the head
      head.add(hoop);
    }
  }

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
  upper.add(...limb([0, 1.47, 0], [0, 1.6, 0.008], 0.05, 0.045, M.skin));
  if (P.collar === 'round') {
    // A cardigan buttoned to the neck: a button band down the front and a rounded collar lying
    // flat round the bare neck.
    upper.add(
      strip(front, 0.84, 1.49, () => -0.0065, () => 0.0065, 0.002, M.lapel, 12, 1),
      tube([0, 1.486, 0.002], [0, 1.516, 0.004], 0.058, 0.055, M.coat), // the neckline, a little up the neck
    );
    for (const y of [1.45, 1.35, 1.25, 1.15, 1.05]) upper.add(ball([0, y, front(0, y) + 0.004], 0.0058, M.brass, [1, 1, 0.45]));
    for (const side of [-1, 1]) {
      const flap = ball([0.047 * side, 1.5, 0.05], 1, M.lapel, [0.05, 0.03, 0.006]);
      flap.rotation.set(-1.05, 0.55 * side, 0.32 * side);
      upper.add(flap);
    }
    const band = new THREE.Mesh(new THREE.TorusGeometry(0.058, 0.0075, 8, 32), M.lapel);
    band.position.set(0, 1.512, -0.004);
    band.rotation.x = Math.PI / 2;
    band.scale.set(1, 0.86, 1);
    upper.add(band);
  } else {
    upper.add(
      strip(front, 1.24, 1.505, (y) => -vee(y), vee, 0.0025, M.shirt),
      strip(front, 1.19, 1.5, (y) => -vee(y) - lapel(y), (y) => -vee(y) + 0.002, 0.005, M.lapel),
      strip(front, 1.19, 1.5, (y) => vee(y) - 0.002, (y) => vee(y) + lapel(y), 0.005, M.lapel),
      strip(front, 0.84, 1.18, () => -0.0025, () => 0.0025, 0.002, M.lapel, 6, 1),
      ball([0, 1.185, front(0, 1.185) + 0.006], 0.0085, M.brass, [1, 1, 0.5]),
      ball([0.066, 1.43, front(0.066, 1.43) + 0.009], 0.0065, M.brass),
      tube([0, 1.488, 0.002], [0, 1.545, 0.006], 0.06, 0.056, M.shirt),
    );
  }
  if (P.pocket !== false) upper.add(strip(front, 1.325, 1.348, () => 0.072, () => 0.106, 0.004, M.square, 2, 2));
  // A flower brooch on the right of the chest (on the left as you face them): [petals, centre].
  if (P.brooch) {
    const [petals, middle] = Array.isArray(P.brooch) ? P.brooch : [P.brooch, P.brooch];
    const x = -0.084;
    const y = 1.372;
    const out = new THREE.Vector3((P.depth * x) / Math.sqrt(Math.max(1e-6, radiusAt(y) ** 2 - x * x)), 0.05, 1);
    upper.add(flower(new THREE.Vector3(x, y, front(x, y) + 0.004), out, 0.0105, mat(petals, { rough: 0.95 }), mat(middle, { rough: 0.9 }), 6));
  }
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

/* ---------- someone else in the same style ---------- */

// A neat hairline round the face, over the ears and down to the nape, for hair drawn back: a bun,
// or braids from a centre parting.
const NEAT_LINE = [[0, 0.55], [0.5, 0.5], [0.95, 0.3], [1.35, 0.12], [1.7, -0.14], [2.3, -0.42], [3.15, -0.56]];
const shade = (hex, k) => `#${new THREE.Color(hex).multiplyScalar(k).getHexString()}`;

// A person in the same style from a page's plain description, such as the receptionist's or the
// founder's assistant's look. Colours are hex strings; anything left out is the default's.
//   skin, hair, lips, coat, shirt, trousers
//   style: 'braids' (a centre parting and a braid each side, with `ties` and `clips` colours),
//     'bun', or the default swept cut if left out
//   accent: buttons and pocket square; pocket: false for none
//   collar: 'round' for a cardigan buttoned to the neck with a rounded collar
//   brooch: a flower on the chest, one colour or [petals, centre]
//   earrings: 'studs' or 'hoops', in `gold` (the accent if left out)
//   face: 'round' for a rounder face with larger eyes
export function lookSpec(look = {}, base = POE) {
  const c = base.colors;
  const skin = look.skin || c.skin;
  const hair = look.hair || c.hair;
  const coat = look.coat || c.coat;
  const accent = look.accent || c.square;
  const cardigan = look.collar === 'round';
  const spec = {
    ...base,
    colors: {
      ...c, skin, hair, coat, lapel: shade(coat, cardigan ? 0.94 : 0.72), shirt: look.shirt || c.shirt, square: accent, brass: accent,
      gold: look.gold || accent, trousers: look.trousers || c.trousers,
      whites: `#${new THREE.Color(c.whites).lerp(new THREE.Color(skin), 0.14).getHexString()}`,
      lips: look.lips || `#${new THREE.Color(skin).lerp(new THREE.Color('#8c3b3a'), 0.3).multiplyScalar(0.82).getHexString()}`,
    },
    fill: { ...base.fill, skin: [shade(skin, 0.5), 0.2], hair: [shade(hair, 0.6), 0.14], coat: [shade(coat, 0.5), cardigan ? 0.12 : 0.28] },
    earrings: look.earrings || null,
    collar: look.collar || null,
    brooch: look.brooch || null,
    pocket: look.pocket ?? true,
  };
  if (look.face === 'round') {
    Object.assign(spec, { head: { ...base.head, w: 0.097, h: 0.12, d: 0.102 }, eyeSize: 1.16, noseTip: [1.2, 0.88, 1] });
  }
  if (look.style === 'braids') {
    Object.assign(spec, {
      hairline: { long: NEAT_LINE, short: NEAT_LINE },
      locks: [],
      volume: (_x, y) => 0.03 + 0.02 * smooth(0.4, 1, y),
      hairRough: 0.9,
      hairDetail: [96, 64],
      ears: 'both',
      part: true,
      // From a tie high on each side, up and out, then down the side of the head to the ear.
      braids: [-1, 1].map((s) => ({
        r: 0.0185, turns: 6, tie: look.ties || null, clip: look.clips || null, clipAt: 0.68,
        path: [[s * 0.95, 0.88, 1.08], [s * 1.18, 0.9, 1.34], [s * 1.42, 0.6, 1.36], [s * 1.55, 0.26, 1.28], [s * 1.62, 0.0, 1.17]],
      })),
    });
  } else if (look.style === 'bun') {
    Object.assign(spec, {
      hairline: { long: NEAT_LINE, short: NEAT_LINE },
      locks: [],
      volume: (_x, y) => 0.03 + 0.025 * smooth(0.3, 1, y),
      ears: 'both',
      bun: { y: 0.42, out: 1.3, r: 0.056 },
    });
  }
  return spec;
}

/* ---------- the people at work ---------- */

// Each person at work gets a look picked by a number from their id, so the same agent always
// looks the same: skin, hair and its cut, a top and trousers.
const LOOKS = {
  skin: ['#f0c8a4', '#deaa82', '#c8926e', '#a8714f', '#7f5238', '#5c3a27'],
  hair: ['#1d1613', '#3a261f', '#5a3926', '#8b5a33', '#c8a26b', '#a7a39d'],
  top: ['#b5603f', '#3f6f7a', '#d4a24c', '#2f4a5c', '#6d7f4e', '#e6dac6', '#7a4f6d', '#c86f5c'],
  legs: ['#27303d', '#3b3b42', '#5b5246', '#2f3c34'],
};
const CUTS = [
  [[0, 0.5], [0.55, 0.47], [1.05, 0.25], [1.5, 0.12], [1.8, -0.08], [2.3, -0.48], [3.15, -0.62]], // short
  POE.hairline.long, // to the jaw all round
  [[0, 0.62], [0.7, 0.55], [1.3, 0.3], [1.8, 0.05], [2.4, -0.3], [3.15, -0.42]], // cropped close
];

// The receptionist a page describes (org.receptionist): `name` and `title` for labels and cards,
// `look` as for lookSpec, a Kokoro `voice`, and the `href` a tap opens. Anything left out keeps
// the default receptionist, so a map with no receptionist still has someone at the desk.
export function receptionistSpec(r = {}) {
  const base = r.look ? lookSpec(r.look) : POE;
  return { ...base, name: r.name || POE.name, title: r.title || POE.title, href: r.href || POE.href, voice: r.voice || null };
}

// Someone seated, in the same smooth style but plainer: a sweater, no coat or locks. They face +z
// from the middle of a seat whose top is `seat` metres up; 'desk' puts their hands on a desk in
// front of them, 'chat' rests them on their knees. Plain meshes, so a room merges them with the
// rest of its things. `n` is a number from their id (rooms.js identity()).
export function buildSeated(n, { seat = 0.46, pose = 'chat' } = {}) {
  const pick = (list, shift) => list[(n >>> shift) % list.length];
  const skin = pick(LOOKS.skin, 0);
  const warm = (color, rough, k = 0.1) => mat(color, { rough, emissive: color, emissiveIntensity: k });
  const M = {
    skin: warm(skin, 0.55), hair: warm(pick(LOOKS.hair, 3), 0.5, 0.06), top: warm(pick(LOOKS.top, 6), 0.8, 0.08),
    legs: mat(pick(LOOKS.legs, 9), { rough: 0.8 }), shoes: mat('#1a1b20', { rough: 0.35 }),
    eyes: mat('#241815', { rough: 0.3 }), whites: mat('#efe9e2', { rough: 0.4 }),
    lips: mat(`#${new THREE.Color(skin).multiplyScalar(0.72).getHexString()}`, { rough: 0.5 }),
  };
  const cut = CUTS[(n >>> 11) % CUTS.length];
  const drop = POE.coat[0][1] - seat; // a seated body is this much lower than the receptionist standing
  const S = headShape({ head: { ...POE.head, y: POE.head.y - drop } });
  const g = new THREE.Group();

  // The head, hair, and a face like the receptionist's.
  g.add(new THREE.Mesh(shaped(28, 20, (x, y, z) => S.unit(x, y, z)), M.skin));
  const line = (x, z) => table(cut, Math.abs(Math.atan2(x, z)));
  const hairAt = (x, y, z) => S.unit(x, y, z, 1.012 + (0.03 + 0.03 * smooth(0.3, 1, y)) * smooth(0, 0.28, y - line(x, z)));
  g.add(new THREE.Mesh(shaped(36, 24, hairAt, (x, y, z) => y > line(x, z)), M.hair));
  for (const side of [-1, 1]) {
    const a = 0.37 * side;
    g.add(
      ball(S.face(a, 0.1, -0.001), 1, M.whites, [0.0155, 0.0072, 0.005], a),
      ball(S.face(a * 0.97, 0.1, 0.0035), 1, M.eyes, [0.0062, 0.0062, 0.003], a),
      ...limb(S.face(0.15 * side, 0.37, 0.001), S.face(0.5 * side, 0.38, 0.001), 0.0042, 0.003, M.hair),
    );
    if (cut !== CUTS[1]) g.add(ball(S.point((side * Math.PI) / 2, 0, 0.99), 1, M.skin, [0.011, 0.026, 0.017]));
  }
  g.add(
    ball(S.face(0, -0.08, -0.002), 1, M.skin, [0.0095, 0.03, 0.012]),
    ball(S.face(0, -0.25, 0.004), 0.011, M.skin, [1, 0.85, 1]),
    ball(S.face(0, -0.53, -0.002), 1, M.lips, [0.02, 0.0058, 0.0085]),
    ...limb([0, 1.47 - drop, 0], [0, 1.6 - drop, 0.008], 0.05, 0.045, M.skin),
  );

  // The body, the shape of the receptionist's coat as a sweater, and the arms: at the keyboard or at rest.
  const profile = new THREE.SplineCurve(POE.coat.map(([r, y]) => new THREE.Vector2(r, y - drop))).getPoints(30);
  const body = new THREE.LatheGeometry(profile, 24, Math.PI);
  body.scale(1, 1, POE.depth);
  g.add(new THREE.Mesh(body, M.top));
  const desk = pose === 'desk';
  for (const side of [-1, 1]) {
    const sh = [0.172 * side, 1.425 - drop, -0.01];
    const el = desk ? [0.215 * side, 1.17 - drop, 0.06] : [0.21 * side, 1.16 - drop, 0.05];
    const wr = desk ? [0.15 * side, 0.77, 0.34] : [0.14 * side, seat + 0.16, 0.3];
    g.add(
      ball([0.162 * side, 1.44 - drop, -0.008], 1, M.top, [0.05, 0.03, 0.06]),
      ...limb(sh, el, 0.05, 0.043, M.top),
      ...limb(el, wr, 0.043, 0.036, M.top),
      ball(v3(wr).add(new THREE.Vector3(-0.015 * side, -0.015, 0.06)), 1, M.skin, [0.032, 0.018, 0.05], -0.2 * side),
    );
  }

  // Legs: thighs along the seat, shins down to the floor.
  for (const side of [-1, 1]) {
    const knee = [0.095 * side, seat + 0.065, 0.42];
    g.add(
      ...limb([0.085 * side, seat + 0.07, 0], knee, 0.068, 0.052, M.legs),
      ...limb(knee, [0.095 * side, 0.1, 0.46], 0.05, 0.04, M.legs),
      ball([0.095 * side, 0.04, 0.53], 1, M.shoes, [0.046, 0.038, 0.1]),
    );
  }
  return g;
}
