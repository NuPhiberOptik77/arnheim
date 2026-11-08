// The halls you walk through: a corridor in front of every floor's rooms, the reception in the
// lobby, and a lift at the west end of each floor. They exist only while someone walks the
// building (walk.js). Shapes, light and colour made in code: no images, textures or models to
// download.
import * as THREE from '../../vendor/three/three.module.js';
import { at, box, cyl, decal, freeze, lit, mat, newScope, rng, useScope } from './kit.js';
import { piece } from './furniture.js';
import { D, H, W } from './rooms.js';

export const WEST = -2.8; // the lift's far wall; the rooms start at 0
const CORRIDOR = 3.2;
const RECEPTION = 7.2;
const TALL = 4.4; // the reception's ceiling, higher than the rooms'
const LIFT = { x: -1.4, half: 0.6, depth: 2.25, cab: 2.3, inner: [-2.4, -0.4] };

// A level rectangle, as a floor (facing up) or a ceiling (facing down), textured in metres.
function flat(x, z, w, d, material, y = 0, down = false) {
  const geo = new THREE.PlaneGeometry(w, d);
  geo.rotateX(down ? Math.PI / 2 : -Math.PI / 2);
  geo.translate(x + w / 2, y, z + d / 2);
  const pos = geo.attributes.position;
  const uv = geo.attributes.uv;
  for (let i = 0; i < pos.count; i++) uv.setXY(i, pos.getX(i) / 2.4, pos.getZ(i) / 2.4);
  const mesh = new THREE.Mesh(geo, material);
  mesh.receiveShadow = !down;
  if (down) mesh.userData.flat = true; // a ceiling neither casts nor takes shadows
  return mesh;
}

// Lit lettering on a clear background: a name, and a smaller line under it.
function sign(title, sub, w, h, glow = 1.5) {
  const c = document.createElement('canvas');
  c.width = 1024;
  c.height = Math.max(64, Math.round((1024 * h) / w));
  const g = c.getContext('2d');
  g.textAlign = 'center';
  g.textBaseline = 'middle';
  g.fillStyle = '#ffeedd';
  const fit = (text, px, weight, y) => {
    let size = px;
    do {
      g.font = `${weight} ${size}px -apple-system, "Helvetica Neue", Arial, sans-serif`;
      size -= 2;
    } while (g.measureText(text).width > c.width * 0.92 && size > 10);
    g.fillText(text, c.width / 2, y);
  };
  if (sub) {
    fit(title, c.height * 0.46, 700, c.height * 0.36);
    fit(sub, c.height * 0.17, 500, c.height * 0.78);
  } else fit(title, c.height * 0.62, 650, c.height * 0.54);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  const m = new THREE.MeshStandardMaterial({ map: tex, emissiveMap: tex, emissive: '#ffffff', emissiveIntensity: glow, transparent: true, depthWrite: false, roughness: 0.6 });
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(w, h), m);
  mesh.userData.live = true;
  return mesh;
}

// A pale terrazzo: stone chips scattered on warm white, drawn once on a small canvas.
function terrazzo() {
  const c = document.createElement('canvas');
  c.width = c.height = 512;
  const g = c.getContext('2d');
  g.fillStyle = '#e4ddd1';
  g.fillRect(0, 0, 512, 512);
  const rand = rng(7);
  const chips = ['#b9a58b', '#8f8a82', '#c9774f', '#6f7d84', '#f6f2ea', '#a39a8c'];
  for (let i = 0; i < 2600; i++) {
    const r = 0.8 + rand() * rand() * 4.5;
    g.fillStyle = chips[Math.floor(rand() * chips.length)];
    g.beginPath();
    g.ellipse(rand() * 512, rand() * 512, r, r * (0.55 + rand() * 0.45), rand() * Math.PI, 0, Math.PI * 2);
    g.fill();
  }
  const tex = new THREE.CanvasTexture(c);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8;
  return tex;
}

// The hall for one floor, in that floor's own frame: rooms run along x from 0, their backs at
// z = 0 and their open fronts at z = D; the hall lies in front of them, the lift at the west end.
export function buildHall(storey, { company = '', mission = '' } = {}) {
  const lobby = storey.role === 'lobby';
  const east = storey.rooms.length * W;
  const depth = lobby ? RECEPTION : CORRIDOR;
  const front = D + depth;
  const high = lobby ? TALL : H;
  const mid = (WEST + east) / 2;
  const style = storey.style;
  const scope = newScope();
  useScope(scope);
  const extras = [];
  const g = new THREE.Group();
  const still = new THREE.Group();
  g.add(still);
  const wall = mat(style.wall, { rough: 0.95 });
  const ceiling = mat(lobby ? '#ddd5c8' : '#e7e4dd', { rough: 0.95 });
  const metal = mat('#2d2a27', { rough: 0.45, metal: 0.5 });
  const glow = (color, k) => mat('#1c1611', { rough: 0.7, emissive: color, emissiveIntensity: k });

  // The floor: terrazzo in the reception, polished concrete everywhere else.
  let floor;
  if (lobby) {
    const tex = terrazzo();
    floor = lit(new THREE.MeshStandardMaterial({ map: tex, roughness: 0.34 }));
    extras.push(tex, floor);
  } else floor = mat(storey.role === 'basement' ? '#5b5f66' : '#a9a398', { rough: 0.5 });
  still.add(flat(WEST, D, east - WEST, depth, floor), flat(WEST, LIFT.depth, -WEST, D - LIFT.depth, floor));

  // Ceilings: one over the rooms and the lift, and the hall's own, which in the reception is high.
  still.add(flat(WEST, 0, east - WEST, D, ceiling, H, true), flat(WEST, D, east - WEST, depth, ceiling, high, true));
  if (lobby) {
    still.add(
      at(box(east - WEST, high - H, 0.14, wall, { r: 0 }), mid, H, D - 0.07),
      at(box(east - WEST, 0.035, 0.04, glow('#ffd7a6', 2.4), { r: 0 }), mid, H + 0.03, D + 0.03),
    );
  } else {
    for (let x = 1.4; x < east - 0.6; x += 3) still.add(at(box(1.4, 0.03, 0.16, glow('#fff1dc', 1.6), { r: 0 }), x, H - 0.035, D + depth / 2));
  }

  // The front is glass from floor to ceiling between slim dark mullions. You can see through it,
  // but it stops you like a wall.
  const pane = at(box(east - WEST, high, 0.02, mat('#a9c7ec', { rough: 0.06, metal: 0.2, opacity: 0.16 }), { r: 0 }), mid, 0, front);
  pane.userData = { live: true, solid: true };
  g.add(pane);
  for (let x = WEST; x < east + 0.01; x += 1.55) still.add(at(box(0.05, high, 0.08, metal, { r: 0 }), Math.min(x, east - 0.03), 0, front));
  still.add(
    at(box(east - WEST, 0.09, 0.12, metal, { r: 0 }), mid, 0, front),
    at(box(east - WEST, 0.08, 0.1, metal, { r: 0 }), mid, high - 0.08, front),
    at(box(0.14, high, depth, wall, { r: 0 }), WEST - 0.07, 0, D + depth / 2),
    at(box(0.14, H, D, wall, { r: 0 }), WEST - 0.07, 0, D / 2),
    at(box(0.14, high, depth, wall, { r: 0 }), east + 0.07, 0, D + depth / 2),
  );

  /* ---------- the lift ---------- */

  const [inL, inR] = LIFT.inner;
  const doorL = LIFT.x - LIFT.half;
  const doorR = LIFT.x + LIFT.half;
  const zf = LIFT.depth;
  const cabD = zf - 0.35;
  const cabZ = 0.15 + cabD / 2;
  const wood = mat('#9a7756', { rough: 0.6 });
  const edge = glow('#ffcf96', 2);
  still.add(
    at(box(inL - WEST, H, zf, metal, { r: 0 }), (WEST + inL) / 2, 0, zf / 2),
    at(box(-inR, H, zf, metal, { r: 0 }), inR / 2, 0, zf / 2),
    at(box(inR - inL, H, 0.15, metal, { r: 0 }), LIFT.x, 0, 0.075),
    at(box(doorL - inL, LIFT.cab, 0.2, metal, { r: 0 }), (inL + doorL) / 2, 0, zf - 0.1),
    at(box(inR - doorR, LIFT.cab, 0.2, metal, { r: 0 }), (doorR + inR) / 2, 0, zf - 0.1),
    at(box(inR - inL, H - LIFT.cab, 0.2, metal, { r: 0 }), LIFT.x, LIFT.cab, zf - 0.1),
    // inside: warm wood, a lit ceiling and a dark stone floor
    at(box(0.03, LIFT.cab - 0.1, cabD, wood, { r: 0 }), inL + 0.015, 0.05, cabZ),
    at(box(0.03, LIFT.cab - 0.1, cabD, wood, { r: 0 }), inR - 0.015, 0.05, cabZ),
    at(box(inR - inL - 0.06, LIFT.cab - 0.1, 0.03, wood, { r: 0 }), LIFT.x, 0.05, 0.165),
    at(box(inR - inL - 0.3, 0.02, cabD - 0.3, glow('#fff3e0', 1.5), { r: 0 }), LIFT.x, LIFT.cab - 0.03, cabZ),
    flat(inL, 0.15, inR - inL, cabD, mat('#33302d', { rough: 0.35 }), 0.004),
    // a warm line round the doorway, and the call buttons
    at(box(0.025, LIFT.cab, 0.025, edge, { r: 0 }), doorL - 0.013, 0, zf + 0.013),
    at(box(0.025, LIFT.cab, 0.025, edge, { r: 0 }), doorR + 0.013, 0, zf + 0.013),
    at(box(doorR - doorL + 0.05, 0.025, 0.025, edge, { r: 0 }), LIFT.x, LIFT.cab, zf + 0.013),
    at(box(0.11, 0.24, 0.02, metal, { r: 0.004 }), (doorR + inR) / 2, 0.92, zf + 0.01),
  );
  const rail = at(cyl(0.018, 0.018, inR - inL - 0.3, mat('#c9a06a', { rough: 0.3, metal: 0.7 }), 10), inR - 0.15, 0.95, 0.24);
  rail.rotation.z = Math.PI / 2;
  still.add(rail);
  for (const y of [0.97, 1.07]) {
    const press = at(cyl(0.022, 0.022, 0.012, glow('#ffd29a', 2.2), 16), (doorR + inR) / 2, y, zf + 0.02);
    press.rotation.x = Math.PI / 2;
    still.add(press);
  }
  const steel = mat('#bab3a7', { rough: 0.32, metal: 0.75 });
  const doors = [0, 1].map(() => {
    const d = box(LIFT.half + 0.02, LIFT.cab - 0.02, 0.04, steel, { r: 0.005 });
    d.position.set(0, 0.01, zf - 0.12);
    d.userData = { live: true, noCollide: true };
    g.add(d);
    return d;
  });
  const setDoors = (open) => {
    doors[0].position.x = LIFT.x - LIFT.half / 2 - open * LIFT.half;
    doors[1].position.x = LIFT.x + LIFT.half / 2 + open * LIFT.half;
  };
  setDoors(0);
  const label = sign(storey.label, '', 1.9, 0.3, 1.5);
  label.position.set(LIFT.x, LIFT.cab + 0.15, zf + 0.012);
  g.add(label);
  extras.push(label.material.map, label.material);
  const call = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.6, 0.3), new THREE.MeshBasicMaterial());
  call.position.set((doorR + inR) / 2, 1.0, zf + 0.12);
  call.visible = false;
  call.userData = { hit: true, lift: true };
  g.add(call);
  extras.push(call.material);

  /* ---------- the reception, in the lobby ---------- */

  let poe = null;
  let entrance = null;
  if (lobby) {
    const oak = mat('#cfae84', { rough: 0.55 });
    const stone = mat('#2e2c2a', { rough: 0.3, metal: 0.1 });
    const fabric = mat(style.fabric, { rough: 0.9 });
    // Poe's desk: a fluted arc of pale oak under a dark stone top, bowing out towards the door.
    const R = 3.2;
    const inner = 2.72;
    const spread = 0.52;
    const cz = D + 2.75 - R;
    const sector = (r0, r1, h, material, y) => {
      const shape = new THREE.Shape();
      shape.absarc(0, 0, r1, -Math.PI / 2 - spread, -Math.PI / 2 + spread, false);
      shape.absarc(0, 0, r0, -Math.PI / 2 + spread, -Math.PI / 2 - spread, true);
      const geo = new THREE.ExtrudeGeometry(shape, { depth: h, bevelEnabled: false, curveSegments: 48 });
      geo.rotateX(-Math.PI / 2);
      geo.translate(mid, y, cz);
      return new THREE.Mesh(geo, material);
    };
    still.add(sector(inner, R, 1.0, oak, 0), sector(inner - 0.06, R + 0.07, 0.05, stone, 1.0));
    for (let i = 0; i <= 36; i++) {
      const a = -spread + (2 * spread * i) / 36;
      still.add(at(cyl(0.036, 0.036, 0.92, oak, 10), mid + Math.sin(a) * (R + 0.005), 0.04, cz + Math.cos(a) * (R + 0.005)));
    }
    const base = new THREE.TorusGeometry(R + 0.03, 0.014, 6, 64, 2 * spread);
    base.rotateZ(Math.PI / 2 - spread);
    base.rotateX(Math.PI / 2);
    still.add(at(new THREE.Mesh(base, glow('#ffcf96', 2.6)), mid, 0.03, cz));
    poe = { x: mid, z: cz + inner - 0.42, turn: 0 };

    // Behind Poe, a wall of oak slats with the company's name lit on a dark band.
    const fw = 4.6;
    const fz = D + 0.75;
    still.add(at(box(fw, 3.5, 0.16, mat('#d6c1a3', { rough: 0.85 }), { r: 0 }), mid, 0, fz));
    for (let x = -fw / 2 + 0.1; x < fw / 2 - 0.05; x += 0.13) still.add(at(box(0.05, 3.3, 0.05, oak, { r: 0 }), mid + x, 0.1, fz + 0.1));
    still.add(at(box(fw - 0.2, 0.03, 0.05, glow('#ffd9a8', 2.2), { r: 0 }), mid, 0.05, fz + 0.14));
    if (company) {
      still.add(at(box(3.9, 1.1, 0.02, stone, { r: 0 }), mid, 2.3, fz + 0.14));
      const words = sign(company, mission ? `Mission: ${mission}` : '', 3.8, 1.0, 1.5);
      words.position.set(mid, 2.85, fz + 0.165);
      g.add(words);
      extras.push(words.material.map, words.material);
    }

    // Two rings of light over the desk, hung on fine cables, and the warm pool they throw.
    const ringM = glow('#ffe2bd', 1.7);
    for (const [r, y, dx, dz] of [[1.75, 3.75, 0, 2.6], [1.05, 3.35, 0.95, 2.15]]) {
      const ring = new THREE.Mesh(new THREE.TorusGeometry(r, 0.04, 8, 72), ringM);
      ring.rotation.x = Math.PI / 2;
      ring.position.set(mid + dx, y, D + dz);
      still.add(ring);
      for (let k = 0; k < 3; k++) {
        const a = (k / 3) * Math.PI * 2 + 0.5;
        still.add(at(cyl(0.004, 0.004, high - y, metal, 4), mid + dx + Math.cos(a) * r, y, D + dz + Math.sin(a) * r));
      }
    }
    still.add(decal(5, 5, mid, D + 2.8, { color: '#ffcf96', opacity: 0.2, add: true, y: 0.012 }));

    // West of the desk: a low sofa, a round stone table and two stools on a rug by the window.
    const sx = WEST + 3.4;
    const rug = new THREE.Mesh(new THREE.CircleGeometry(2, 48).rotateX(-Math.PI / 2), mat(style.rug, { rough: 0.95 }));
    rug.position.set(sx, 0.006, front - 2.0);
    rug.userData.flat = true;
    const sofa = new THREE.Group();
    sofa.add(
      at(box(2.4, 0.42, 0.9, fabric, { r: 0.08 }), 0, 0, 0),
      at(box(2.4, 0.4, 0.22, fabric, { r: 0.08 }), 0, 0.4, -0.34),
      at(box(0.22, 0.62, 0.9, fabric, { r: 0.08 }), -1.09, 0, 0),
      at(box(0.22, 0.62, 0.9, fabric, { r: 0.08 }), 1.09, 0, 0),
    );
    sofa.position.set(sx, 0, front - 0.85);
    sofa.rotation.y = Math.PI;
    still.add(rug, sofa, at(cyl(0.5, 0.5, 0.36, stone, 40), sx, 0, front - 2.15), decal(1.4, 1.4, sx, front - 2.15));
    for (const dx of [-1.25, 1.25]) still.add(at(cyl(0.3, 0.33, 0.42, mat('#d9c7ad', { rough: 0.9 }), 32), sx + dx, 0, front - 2.6));

    // East of the desk: round seats around a tall plant, and two discs of colour on the end wall.
    const ex = east - 3.6;
    still.add(at(cyl(0.55, 0.6, 0.45, mat('#5a5048', { rough: 0.8 }), 36), ex, 0, D + 4.3), at(piece('plant', { height: 2.1 }), ex, 0.45, D + 4.3));
    for (let k = 0; k < 3; k++) {
      const a = (k / 3) * Math.PI * 2 + 0.3;
      still.add(at(cyl(0.34, 0.36, 0.42, fabric, 32), ex + Math.cos(a) * 1.35, 0, D + 4.3 + Math.sin(a) * 1.35));
    }
    const art = new THREE.Mesh(new THREE.CircleGeometry(1.25, 56), mat(style.fabric, { rough: 0.8 }));
    art.rotation.y = -Math.PI / 2;
    art.position.set(east - 0.006, 2.1, D + depth * 0.55);
    const sun = new THREE.Mesh(new THREE.CircleGeometry(0.55, 40), glow('#ffd59e', 2));
    sun.rotation.y = -Math.PI / 2;
    sun.position.set(east - 0.012, 2.6, D + depth * 0.55 + 0.6);
    still.add(art, sun);
    for (const [x, z, h] of [[WEST + 0.6, front - 0.6, 1.7], [east - 0.6, front - 0.6, 1.8], [mid - fw / 2 - 0.5, fz + 0.2, 1.5], [mid + fw / 2 + 0.5, fz + 0.2, 1.5]]) {
      still.add(decal(1, 1, x, z), at(piece('plant', { height: h }), x, 0, z));
    }
    still.add(flat(mid - 1, front - 1.15, 2, 1.05, mat('#3a3530', { rough: 0.95 }), 0.005)); // the mat inside the door
    entrance = { x: mid, z: front - 1.3, yaw: 0 };
  } else {
    // A bench and a plant every few metres along the glass.
    const seat = mat('#b48d63', { rough: 0.55 });
    for (let x = 3.2; x < east - 1.5; x += 7) {
      still.add(
        at(box(1.6, 0.07, 0.42, seat, { r: 0.02 }), x, 0.4, front - 0.42),
        at(box(0.06, 0.4, 0.36, metal, { r: 0 }), x - 0.65, 0, front - 0.42),
        at(box(0.06, 0.4, 0.36, metal, { r: 0 }), x + 0.65, 0, front - 0.42),
        decal(0.9, 0.9, x + 1.6, front - 0.5),
        at(piece('plant', { height: 1.3 }), x + 1.6, 0, front - 0.5),
      );
    }
  }

  // The hall's two local lamps, in world space: the floor stays where it is while you walk.
  const p = storey.group.position;
  const lamps = lobby
    ? [[mid, 2.4, D + 2.9, '#ffd2a1', 9], [mid, 2.2, D + 5.2, '#ffe6c8', 5]]
    : [[east * 0.28, 2.3, D + depth / 2, '#ffe3c2', 8], [east * 0.72, 2.3, D + depth / 2, '#ffe3c2', 8]];
  const u = scope.uniforms;
  u.uLampPos.value.set(p.x + lamps[0][0], p.y + lamps[0][1], p.z + lamps[0][2]);
  u.uLampCol.value.set(lamps[0][3]).multiplyScalar(lamps[0][4]);
  u.uLamp2Pos.value.set(p.x + lamps[1][0], p.y + lamps[1][1], p.z + lamps[1][2]);
  u.uLamp2Col.value.set(lamps[1][3]).multiplyScalar(lamps[1][4]);

  freeze(still);
  useScope(null);
  return {
    group: g, west: WEST, east, front, depth, high, entrance, poe, picks: [call],
    lift: { x: LIFT.x, z: zf, open: 0 },
    setDoors,
    // Where you stand when the lift brings you to this floor, facing out of the doors.
    spot: { x: LIFT.x, z: 1.05, yaw: Math.PI },
    inLift: (x, z) => x > -2.3 && x < -0.5 && z > 0.25 && z < 1.98,
    dispose() {
      g.traverse((o) => { if (o.isMesh) o.geometry.dispose(); });
      for (const m of scope.materials.values()) m.dispose();
      for (const x of extras) x.dispose();
    },
  };
}
