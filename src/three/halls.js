// The halls you walk through: a corridor in front of every floor's rooms, the reception in the
// lobby, a lift at the west end of each floor, and the founder's office on top. They exist only
// while someone walks the building (walk.js). Shapes, light and colour are made in code, so a hall
// is whole on its own; materials marked with userData.photo are dressed in real photographed ones
// once those have loaded (photo.js): 'plaster', 'oak' and 'terrazzo' get pictures; 'stone',
// 'polished', 'metal' and 'glass' only reflections.
import * as THREE from '../../vendor/three/three.module.js';
import { at, box, cyl, decal, freeze, lit, mat, newScope, rng, useScope } from './kit.js';
import { piece } from './furniture.js';
import { buildPerson, lookSpec } from './poe.js';
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

// A run of floor-to-ceiling glass along x or along z, between slim dark mullions. You can see
// through it, but it stops you like a wall.
function glazing(g, still, [x0, z0], [x1, z1], high, glass, metal) {
  const alongX = z0 === z1;
  const len = alongX ? x1 - x0 : z1 - z0;
  const bar = (a, h, c, material, t, y = 0) => (alongX
    ? at(box(a, h, c, material, { r: 0 }), x0 + t, y, z0)
    : at(box(c, h, a, material, { r: 0 }), x0, y, z0 + t));
  const pane = bar(len, high, 0.02, glass, len / 2);
  pane.userData = { live: true, solid: true };
  g.add(pane);
  for (let t = 0; t < len + 0.01; t += 1.55) still.add(bar(0.05, high, 0.08, metal, Math.min(t, len - 0.03)));
  still.add(bar(len, 0.09, 0.12, metal, len / 2), bar(len, 0.08, 0.1, metal, len / 2, high - 0.08));
}

// A curved block: the ring between radii r0 and r1 round (cx, cz), from angle a0 to a1 (0 points
// along x, a quarter turn along -z), h tall from y up, its edges rounded by `round` if given.
function curve(cx, cz, r0, r1, a0, a1, h, material, y = 0, round = 0) {
  const shape = new THREE.Shape();
  shape.absarc(0, 0, r1 - round, a0 + round / r1, a1 - round / r1, false);
  shape.absarc(0, 0, r0 + round, a1 - round / r0, a0 + round / r0, true);
  const geo = new THREE.ExtrudeGeometry(shape, {
    depth: h - 2 * round, curveSegments: 48,
    bevelEnabled: round > 0, bevelThickness: round, bevelSize: round, bevelSegments: 3,
  });
  geo.rotateX(-Math.PI / 2);
  geo.translate(cx, y + round, cz);
  return new THREE.Mesh(geo, material);
}

// The lift at the west end of a floor: its shaft, a warm cab, doors that slide apart, the floor's
// name over them and the button that calls it.
function addLift(g, still, extras, name, metal, glow) {
  const [inL, inR] = LIFT.inner;
  const doorL = LIFT.x - LIFT.half;
  const doorR = LIFT.x + LIFT.half;
  const zf = LIFT.depth;
  const cabD = zf - 0.35;
  const cabZ = 0.15 + cabD / 2;
  const wood = mat('#9a7756', { rough: 0.6 });
  const edge = glow('#ffcf96', 2);
  const cabFloor = mat('#33302d', { rough: 0.35 });
  const brass = mat('#c9a06a', { rough: 0.3, metal: 0.7 });
  wood.userData.photo = 'oak';
  cabFloor.userData.photo = 'stone';
  brass.userData.photo = 'metal';
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
    flat(inL, 0.15, inR - inL, cabD, cabFloor, 0.004),
    // a warm line round the doorway, and the call buttons
    at(box(0.025, LIFT.cab, 0.025, edge, { r: 0 }), doorL - 0.013, 0, zf + 0.013),
    at(box(0.025, LIFT.cab, 0.025, edge, { r: 0 }), doorR + 0.013, 0, zf + 0.013),
    at(box(doorR - doorL + 0.05, 0.025, 0.025, edge, { r: 0 }), LIFT.x, LIFT.cab, zf + 0.013),
    at(box(0.11, 0.24, 0.02, metal, { r: 0.004 }), (doorR + inR) / 2, 0.92, zf + 0.01),
  );
  const rail = at(cyl(0.018, 0.018, inR - inL - 0.3, brass, 10), inR - 0.15, 0.95, 0.24);
  rail.rotation.z = Math.PI / 2;
  still.add(rail);
  for (const y of [0.97, 1.07]) {
    const press = at(cyl(0.022, 0.022, 0.012, glow('#ffd29a', 2.2), 16), (doorR + inR) / 2, y, zf + 0.02);
    press.rotation.x = Math.PI / 2;
    still.add(press);
  }
  const steel = mat('#bab3a7', { rough: 0.32, metal: 0.75 });
  steel.userData.photo = 'metal';
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
  const label = sign(name, '', 1.9, 0.3, 1.5);
  label.position.set(LIFT.x, LIFT.cab + 0.15, zf + 0.012);
  g.add(label);
  extras.push(label.material.map, label.material);
  const call = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.6, 0.3), new THREE.MeshBasicMaterial());
  call.position.set((doorR + inR) / 2, 1.0, zf + 0.12);
  call.visible = false;
  call.userData = { hit: true, lift: true };
  g.add(call);
  extras.push(call.material);
  return { setDoors, call };
}

// A hall's two local lamps, set in world space: the floor stays where it is while you walk.
function setLamps(scope, storey, lamps) {
  const p = storey.group.position;
  const u = scope.uniforms;
  u.uLampPos.value.set(p.x + lamps[0][0], p.y + lamps[0][1], p.z + lamps[0][2]);
  u.uLampCol.value.set(lamps[0][3]).multiplyScalar(lamps[0][4]);
  u.uLamp2Pos.value.set(p.x + lamps[1][0], p.y + lamps[1][1], p.z + lamps[1][2]);
  u.uLamp2Col.value.set(lamps[1][3]).multiplyScalar(lamps[1][4]);
}

// What the walk gets back from a hall: the group, the lift and where it leaves you, and how to let
// it all go. `more` adds the hall's size and anything of its own.
function made(g, scope, extras, lift, more) {
  return {
    group: g, entrance: null, poe: null, picks: [lift.call],
    lift: { x: LIFT.x, z: LIFT.depth, open: 0 },
    setDoors: lift.setDoors,
    // Where you stand when the lift brings you to this floor, facing out of the doors.
    spot: { x: LIFT.x, z: 1.05, yaw: Math.PI },
    inLift: (x, z) => x > -2.3 && x < -0.5 && z > 0.25 && z < 1.98,
    dispose() {
      g.traverse((o) => { if (o.isMesh) o.geometry.dispose(); });
      for (const m of scope.materials.values()) m.dispose();
      for (const x of extras) x.dispose();
    },
    ...more,
  };
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
  wall.userData.photo = 'plaster';
  ceiling.userData.photo = 'plaster';
  metal.userData.photo = 'metal';

  // The floor: terrazzo in the reception, polished concrete everywhere else.
  let floor;
  if (lobby) {
    const tex = terrazzo();
    floor = lit(new THREE.MeshStandardMaterial({ map: tex, roughness: 0.34 }));
    floor.userData.photo = 'terrazzo';
    extras.push(tex, floor);
  } else {
    floor = mat(storey.role === 'basement' ? '#5b5f66' : '#a9a398', { rough: 0.5 });
    floor.userData.photo = 'stone';
  }
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

  // The front is glass from floor to ceiling.
  const glass = mat('#a9c7ec', { rough: 0.06, metal: 0.2, opacity: 0.16 });
  glass.userData.photo = 'metal';
  glazing(g, still, [WEST, front], [east, front], high, glass, metal);
  still.add(
    at(box(0.14, high, depth, wall, { r: 0 }), WEST - 0.07, 0, D + depth / 2),
    at(box(0.14, H, D, wall, { r: 0 }), WEST - 0.07, 0, D / 2),
    at(box(0.14, high, depth, wall, { r: 0 }), east + 0.07, 0, D + depth / 2),
  );

  const lift = addLift(g, still, extras, storey.label, metal, glow);

  /* ---------- the reception, in the lobby ---------- */

  let poe = null;
  let entrance = null;
  if (lobby) {
    const oak = mat('#cfae84', { rough: 0.55 });
    const stone = mat('#2e2c2a', { rough: 0.3, metal: 0.1 });
    const fabric = mat(style.fabric, { rough: 0.9 });
    const panel = mat('#d6c1a3', { rough: 0.85 });
    oak.userData.photo = 'oak';
    panel.userData.photo = 'oak';
    stone.userData.photo = 'stone';
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
    still.add(at(box(fw, 3.5, 0.16, panel, { r: 0 }), mid, 0, fz));
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
    seat.userData.photo = 'oak';
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

  // The hall's two local lamps.
  setLamps(scope, storey, lobby
    ? [[mid, 2.4, D + 2.9, '#ffd2a1', 9], [mid, 2.2, D + 5.2, '#ffe6c8', 5]]
    : [[east * 0.28, 2.3, D + depth / 2, '#ffe3c2', 8], [east * 0.72, 2.3, D + depth / 2, '#ffe3c2', 8]]);
  freeze(still);
  useScope(null);
  return made(g, scope, extras, lift, { west: WEST, east, front, depth, high, entrance, poe });
}

/* ---------- the penthouse: the founder's office ---------- */

const PENTHOUSE = { half: 8.5, front: 11.4, high: 5.2 };

// An abstract picture for the office wall: a dusk in soft bands of colour, a pale sun low in it
// and still water below.
function painting() {
  const c = document.createElement('canvas');
  c.width = 1024;
  c.height = 640;
  const g = c.getContext('2d');
  const sky = g.createLinearGradient(0, 0, 0, c.height);
  sky.addColorStop(0, '#2d2546');
  sky.addColorStop(0.45, '#8c3f3a');
  sky.addColorStop(0.64, '#e0874f');
  sky.addColorStop(1, '#f2c48a');
  g.fillStyle = sky;
  g.fillRect(0, 0, c.width, c.height);
  const sun = g.createRadialGradient(640, 360, 10, 640, 360, 150);
  sun.addColorStop(0, 'rgba(255, 244, 222, 1)');
  sun.addColorStop(0.6, 'rgba(255, 226, 180, 0.95)');
  sun.addColorStop(1, 'rgba(255, 214, 160, 0)');
  g.fillStyle = sun;
  g.fillRect(0, 0, c.width, c.height);
  for (let i = 0; i < 7; i++) {
    g.fillStyle = `rgba(38, 24, 40, ${0.18 + i * 0.07})`;
    g.fillRect(0, 430 + i * 30, c.width, 12 + i * 3);
  }
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  return tex;
}

// The sky outside the penthouse, painted once on the inside of a sphere: a dusk whose glow lies low
// behind the rings (along +z, a quarter of the way round the picture), stars overhead, a sea of
// cloud below.
function duskSky() {
  const c = document.createElement('canvas');
  c.width = 2048;
  c.height = 1024;
  const g = c.getContext('2d');
  const fill = g.createLinearGradient(0, 0, 0, c.height);
  for (const [t, color] of [[0, '#0b1029'], [0.3, '#1d1d3f'], [0.42, '#4a2d4d'], [0.48, '#b5604a'], [0.5, '#f0a35c'], [0.515, '#a8655a'], [0.6, '#3d2a3a'], [1, '#0a0c16']]) fill.addColorStop(t, color);
  g.fillStyle = fill;
  g.fillRect(0, 0, c.width, c.height);
  const glow = g.createRadialGradient(512, 512, 0, 512, 512, 620);
  glow.addColorStop(0, 'rgba(255, 190, 120, 0.85)');
  glow.addColorStop(0.35, 'rgba(240, 140, 90, 0.35)');
  glow.addColorStop(1, 'rgba(200, 100, 90, 0)');
  g.save();
  g.translate(512, 512);
  g.scale(1, 0.3);
  g.fillStyle = glow;
  g.fillRect(-620, -620, 1240, 1240);
  g.restore();
  const rand = rng(5);
  for (let i = 0; i < 700; i++) {
    g.fillStyle = `rgba(255, 246, 230, ${0.25 + rand() * 0.6})`;
    g.fillRect(rand() * c.width, rand() * rand() * 400, 1.6, 1.6);
  }
  for (let i = 0; i < 260; i++) {
    const y = 524 + rand() * rand() * 280;
    g.fillStyle = `rgba(255, 196, 160, ${0.03 + 0.07 * (1 - (y - 524) / 280)})`;
    g.beginPath();
    g.ellipse(rand() * c.width, y, 80 + rand() * 240, 5 + rand() * 12, 0, 0, Math.PI * 2);
    g.fill();
  }
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

// The founder's office: a floor above all the others that only the walk has. One wide room under
// a high ceiling with glass on three sides, centred on the lift so its doors open straight onto
// the desk, a slab of pale oak that seems to float. Behind it, two rings of light round a small
// sun hang in the air before the glass, "as if by miracle", as in Poe's story. A cloud of pearls
// of light hangs over the way in; a library fills the wall to one side, a lounge the other.
export function buildPenthouse(storey, { founder = null, assistant = null } = {}) {
  const { half, front, high } = PENTHOUSE;
  const mid = LIFT.x;
  const west = mid - half;
  const east = mid + half;
  const scope = newScope();
  useScope(scope);
  const extras = [];
  const g = new THREE.Group();
  const still = new THREE.Group();
  g.add(still);
  const glow = (color, k) => mat('#1c1611', { rough: 0.7, emissive: color, emissiveIntensity: k });
  const wall = mat('#d4c9bb', { rough: 0.95 });
  const ceiling = mat('#262220', { rough: 0.95 });
  const floor = mat('#2b2724', { rough: 0.22 });
  const metal = mat('#2d2a27', { rough: 0.45, metal: 0.5 });
  const oak = mat('#cfae84', { rough: 0.55 });
  const leather = mat('#4a2e21', { rough: 0.5 });
  const velvet = mat('#3f5a4f', { rough: 0.9 });
  const stone = mat('#3a3531', { rough: 0.3, metal: 0.1 });
  const glass = mat('#c4d8f0', { rough: 0.05, metal: 0.2, opacity: 0.07 });
  const kinds = [[wall, 'plaster'], [ceiling, 'plaster'], [floor, 'polished'], [metal, 'metal'], [oak, 'oak'], [stone, 'stone'], [glass, 'glass']];
  for (const [m, kind] of kinds) m.userData.photo = kind;

  // The shell: floor and ceiling, a back wall with a line of light along its top, glass on three sides.
  still.add(
    flat(west, 0, east - west, front, floor),
    flat(west, 0, east - west, front, ceiling, high, true),
    at(box(east - west, high, 0.14, wall, { r: 0 }), mid, 0, -0.07),
    at(box(east - west, 0.035, 0.04, glow('#ffd7a6', 2.2), { r: 0 }), mid, high - 0.3, 0.03),
  );
  glazing(g, still, [west, front], [east, front], high, glass, metal);
  glazing(g, still, [west, 0], [west, front], high, glass, metal);
  glazing(g, still, [east, 0], [east, front], high, glass, metal);
  const dusk = duskSky();
  const sky = new THREE.Mesh(new THREE.SphereGeometry(60, 48, 24), new THREE.MeshBasicMaterial({ map: dusk, side: THREE.BackSide, depthWrite: false }));
  sky.position.set(mid, 1.62, front / 2);
  sky.renderOrder = -1; // drawn first, so everything else stands in front of it
  sky.userData = { live: true, noCollide: true, backdrop: true };
  g.add(sky);
  extras.push(dusk, sky.material);

  // The lift stands free against the back wall, its shaft rising to the ceiling as a dark core with
  // the founder's name lit high on it.
  const lift = addLift(g, still, extras, storey.label, metal, glow);
  still.add(at(box(-WEST, high - H, LIFT.depth, metal, { r: 0 }), LIFT.x, H, LIFT.depth / 2));
  const name = founder?.name || '';
  const title = founder?.title || '';
  if (name) {
    const plaque = sign(name, title, 2.5, 0.9, 1.4);
    plaque.position.set(LIFT.x, 3.3, LIFT.depth + 0.012);
    g.add(plaque);
    extras.push(plaque.material.map, plaque.material);
  }

  // The desk: a slab of pale oak on a block of clear glass, so it seems to float, with a line of warm
  // light under its edge. An empty chair behind it faces the lift; two armchairs wait in front.
  const dz = 7.4;
  const clear = mat('#d8e8ff', { rough: 0.05, metal: 0.1, opacity: 0.18 });
  still.add(
    at(box(2.8, 0.06, 1.0, oak, { r: 0.012 }), mid, 0.7, dz),
    at(box(0.5, 0.7, 0.46, clear, { r: 0.01 }), mid, 0, dz),
    at(box(2.5, 0.012, 0.02, glow('#ffcf96', 2.4), { r: 0 }), mid, 0.68, dz - 0.47),
    decal(3.8, 2, mid, dz, { color: '#ffb877', opacity: 0.3, add: true }),
    at(box(0.34, 0.016, 0.24, mat('#9a9ca3', { rough: 0.35, metal: 0.6 }), { r: 0.006 }), mid + 0.55, 0.76, dz + 0.12),
    at(box(0.16, 0.014, 0.22, leather, { r: 0.004 }), mid - 0.7, 0.76, dz + 0.08),
    at(box(0.09, 0.09, 0.09, stone, { r: 0.005 }), mid - 1.12, 0.76, dz - 0.18),
    at(new THREE.Mesh(new THREE.SphereGeometry(0.045, 20, 14), glow('#ffd29a', 2.6)), mid - 1.12, 0.895, dz - 0.18),
  );
  const chair = new THREE.Group();
  const back = at(box(0.54, 0.8, 0.09, leather, { r: 0.04 }), 0, 0.5, -0.27);
  back.rotation.x = -0.12;
  chair.add(
    at(cyl(0.3, 0.32, 0.035, metal, 5), 0, 0, 0),
    at(cyl(0.03, 0.03, 0.4, metal, 10), 0, 0.03, 0),
    at(box(0.56, 0.1, 0.54, leather, { r: 0.04 }), 0, 0.42, 0),
    at(box(0.07, 0.22, 0.4, leather, { r: 0.03 }), -0.29, 0.52, 0.03),
    at(box(0.07, 0.22, 0.4, leather, { r: 0.03 }), 0.29, 0.52, 0.03),
    back,
  );
  chair.position.set(mid, 0, dz + 0.85);
  chair.rotation.y = Math.PI;
  still.add(chair);
  for (const side of [-1, 1]) {
    const seat = at(piece('armchair', { color: '#cbbba6' }), mid + side * 0.95, 0, dz - 1.5);
    seat.rotation.y = -side * 0.2;
    still.add(decal(1.1, 1, mid + side * 0.95, dz - 1.5), seat);
  }

  // The founder's assistant, if the page names one (org.assistant): on the left as you step out of
  // the lift, standing at a slim desk of her own and facing the lift, off the way to the founder's desk.
  let aide = null;
  if (assistant?.name) {
    const ax = 2.5;
    const az = 3.15;
    const tx = ax - 0.5; // the desk, between her and whoever comes to talk
    still.add(
      at(box(0.62, 0.045, 1.5, oak, { r: 0.01 }), tx, 0.98, az),
      at(box(0.5, 0.98, 0.04, metal, { r: 0.006 }), tx, 0, az - 0.68),
      at(box(0.5, 0.98, 0.04, metal, { r: 0.006 }), tx, 0, az + 0.68),
      at(box(0.025, 0.62, 1.36, metal, { r: 0.006 }), tx - 0.27, 0.3, az),
      at(box(0.02, 0.012, 1.3, glow('#ffcf96', 2.2), { r: 0 }), tx - 0.31, 0.96, az),
      at(box(0.2, 0.012, 0.28, glow('#9fb7d6', 0.7), { r: 0.006 }), tx + 0.12, 1.025, az + 0.2),
      at(box(0.15, 0.014, 0.21, leather, { r: 0.004 }), tx + 0.05, 1.025, az - 0.3),
      at(cyl(0.05, 0.06, 0.02, metal, 20), tx + 0.1, 1.025, az - 0.6),
      at(cyl(0.008, 0.008, 0.3, metal, 8), tx + 0.1, 1.04, az - 0.6),
      at(new THREE.Mesh(new THREE.SphereGeometry(0.05, 20, 14), glow('#ffd29a', 2.4)), tx + 0.1, 1.38, az - 0.6),
      decal(1.6, 2.1, ax - 0.25, az, { color: '#ffb877', opacity: 0.22, add: true }),
    );
    const spec = lookSpec(assistant.look || {});
    spec.at = [ax, 0, az];
    spec.turn = -1.5; // towards the lift
    spec.look = -0.12;
    const person = buildPerson(spec);
    g.add(person.group);
    const hit = new THREE.Mesh(new THREE.BoxGeometry(1.1, 1.85, 1.6), new THREE.MeshBasicMaterial());
    hit.position.set(ax - 0.3, 0.92, az);
    hit.visible = false;
    hit.userData = { hit: true, stay: true, title: assistant.name, sub: `${assistant.title || 'Assistant'}. Step into the ring by her desk to talk.` };
    g.add(hit);
    extras.push(hit.material);
    aide = {
      x: ax, z: az, stand: [ax - 1.75, az], hit,
      // stay: she has no page of her own in the list, so her card has no Open button.
      who: { title: assistant.name, sub: assistant.title || 'Assistant', href: assistant.href || '#/assistant', voice: assistant.voice || null, stay: true },
    };
  }

  // The centrepiece, between the desk and the glass: two rings of light round a small sun.
  const rz = 9.6;
  const ry = 2.4;
  const ringA = at(new THREE.Mesh(new THREE.TorusGeometry(2.05, 0.05, 12, 128), glow('#ffd6a0', 2.6)), mid, ry, rz);
  const ringB = at(new THREE.Mesh(new THREE.TorusGeometry(1.72, 0.022, 8, 128), glow('#ffe8c8', 1.9)), mid, ry, rz + 0.1);
  ringB.rotation.y = 0.55;
  const sun = at(new THREE.Mesh(new THREE.SphereGeometry(0.19, 32, 20), glow('#fff0d6', 3.2)), mid, ry, rz);
  still.add(ringA, ringB, sun, decal(5.6, 3.4, mid, rz - 0.4, { color: '#ffc27d', opacity: 0.24, add: true }));

  // Over the way in, a cloud of pearls of light on fine threads, rising and falling like a slow wave,
  // high enough to walk under. One draw for all the pearls and one for all the threads.
  const rand = rng(23);
  const pearls = [];
  for (let x = -4.8; x <= 4.8; x += 0.34) {
    for (let z = -2.3; z <= 2.3; z += 0.34) {
      const px = x + (rand() - 0.5) * 0.26;
      const pz = z + (rand() - 0.5) * 0.26;
      const e = (px / 4.8) ** 2 + (pz / 2.3) ** 2;
      if (e > 1) continue;
      const wave = Math.sin(px * 0.85 + pz * 0.6) * 0.45 + Math.cos(px * 0.4 - pz * 1.1) * 0.3;
      pearls.push([mid + px, 3.5 + wave - (1 - e) * 0.45 + (rand() - 0.5) * 0.12, 4.95 + pz, 0.025 + rand() * 0.03]);
    }
  }
  const bead = new THREE.IcosahedronGeometry(1, 2);
  const beadM = new THREE.MeshBasicMaterial({ color: '#ffffff' });
  const cloud = new THREE.InstancedMesh(bead, beadM, pearls.length);
  const m4 = new THREE.Matrix4();
  const turn = new THREE.Quaternion();
  const where = new THREE.Vector3();
  const size = new THREE.Vector3();
  const tint = new THREE.Color();
  const warm = ['#ffd9a3', '#fff1de', '#ffc27a', '#ffe6c2'];
  const lines = new Float32Array(pearls.length * 6);
  pearls.forEach(([x, y, z, r], i) => {
    cloud.setMatrixAt(i, m4.compose(where.set(x, y, z), turn, size.setScalar(r)));
    cloud.setColorAt(i, tint.set(warm[i % warm.length]).multiplyScalar(1.5 + rand() * 1.3));
    lines.set([x, y + r, z, x, high, z], i * 6);
  });
  cloud.userData = { live: true, noCollide: true };
  const threads = new THREE.BufferGeometry();
  threads.setAttribute('position', new THREE.BufferAttribute(lines, 3));
  const threadM = new THREE.LineBasicMaterial({ color: '#d9c7ae', transparent: true, opacity: 0.2 });
  g.add(cloud, new THREE.LineSegments(threads, threadM));
  still.add(decal(10.5, 5.6, mid, 4.95, { color: '#ffd29e', opacity: 0.1, add: true }));
  extras.push(beadM, threads, threadM, cloud);

  // East of the lift, a lounge: a curved sofa round a stone table on a round rug, open to the glass,
  // and on the back wall a picture of a dusk over a low sideboard.
  const lx = 4.3;
  const lz = 6.6;
  const rug = new THREE.Mesh(new THREE.CircleGeometry(2.75, 64).rotateX(-Math.PI / 2), mat('#5a4a3e', { rough: 0.95 }));
  rug.position.set(lx, 0.006, lz);
  rug.userData.flat = true;
  const a0 = Math.PI / 2 - 1.65;
  const a1 = Math.PI / 2 + 1.65;
  const cushions = 5;
  const span = (a1 - a0) / cushions;
  for (let k = 0; k < cushions; k++) still.add(curve(lx, lz, 1.45, 2.1, a0 + k * span + 0.012, a0 + (k + 1) * span - 0.012, 0.26, velvet, 0.12, 0.05));
  still.add(
    rug,
    curve(lx, lz, 1.6, 2.22, a0 + 0.03, a1 - 0.03, 0.12, metal),
    curve(lx, lz, 2.04, 2.34, a0, a1, 0.68, velvet, 0.08, 0.06),
    decal(5, 5, lx, lz, { opacity: 0.25 }),
    at(cyl(0.42, 0.5, 0.33, oak, 40), lx, 0, lz),
    at(cyl(0.8, 0.8, 0.05, stone, 48), lx, 0.33, lz),
    at(box(0.3, 0.05, 0.22, mat('#c9553f', { rough: 0.9 }), { r: 0.006 }), lx - 0.2, 0.38, lz + 0.1),
    at(cyl(0.11, 0.07, 0.09, mat('#eceae5', { rough: 0.4 }), 24), lx + 0.3, 0.38, lz - 0.15),
  );
  const art = painting();
  const picture = new THREE.Mesh(
    new THREE.PlaneGeometry(3.6, 2.25),
    lit(new THREE.MeshStandardMaterial({ map: art, emissiveMap: art, emissive: '#ffffff', emissiveIntensity: 0.22, roughness: 0.85 })),
  );
  picture.position.set(3.75, 2.45, 0.045);
  still.add(at(box(3.72, 2.37, 0.04, metal, { r: 0 }), 3.75, 1.265, 0.02), picture, at(piece('sideboard', { width: 2.8 }), 3.75, 0, 0.23));
  extras.push(art, picture.material);

  // West of the lift, a library nearly to the ceiling with its ladder, and two armchairs by a small
  // table and a lamp in front of it.
  for (let i = 0; i < 6; i++) still.add(at(piece('bookshelf', { width: 1.05, height: 4.4 }), west + 0.75 + i * 1.07, 0, 0.18));
  const ladder = new THREE.Group();
  const long = Math.hypot(0.68, 4.25);
  for (const sx of [-0.22, 0.22]) ladder.add(at(box(0.045, long, 0.06, oak, { r: 0.01 }), sx, 0, 0));
  for (let y = 0.3; y < long - 0.2; y += 0.32) ladder.add(at(box(0.44, 0.035, 0.035, oak, { r: 0.008 }), 0, y, 0));
  ladder.position.set(-6.1, 0, 1.05);
  ladder.rotation.x = -Math.atan2(0.68, 4.25);
  still.add(ladder);
  const nx = -6.6;
  const nz = 4.6;
  for (const side of [-1, 1]) {
    const seat = at(piece('armchair', { color: side < 0 ? '#8a5f3c' : '#b5603f' }), nx + side * 1.1, 0, nz);
    seat.rotation.y = (-side * Math.PI) / 2;
    still.add(decal(1.1, 1.1, nx + side * 1.1, nz), seat);
  }
  still.add(
    at(cyl(0.05, 0.16, 0.5, metal, 16), nx, 0, nz),
    at(cyl(0.36, 0.36, 0.04, oak, 36), nx, 0.5, nz),
    decal(1, 1, nx, nz),
    at(cyl(0.16, 0.18, 0.025, metal, 24), nx - 1.9, 0, nz - 0.9),
    at(cyl(0.012, 0.012, 1.45, metal, 8), nx - 1.9, 0.02, nz - 0.9),
    at(cyl(0.15, 0.21, 0.3, glow('#ffe1b8', 1.3), 28), nx - 1.9, 1.42, nz - 0.9),
  );

  // By the glass, a telescope on its tripod, looking up; tall plants in three corners.
  const telescope = new THREE.Group();
  for (let k = 0; k < 3; k++) {
    const a = (k / 3) * Math.PI * 2;
    const leg = at(cyl(0.012, 0.015, 1.25, metal, 8), Math.cos(a) * 0.32, 0, Math.sin(a) * 0.32);
    leg.rotation.set(-Math.sin(a) * 0.26, 0, Math.cos(a) * 0.26);
    telescope.add(leg);
  }
  const tube = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.075, 1.0, 24), mat('#e3ddd2', { rough: 0.35, metal: 0.3 }));
  tube.position.set(0, 1.27, 0.08);
  tube.rotation.x = Math.PI / 2 - 0.6;
  telescope.add(tube);
  telescope.position.set(west + 2.2, 0, front - 1.0);
  telescope.rotation.y = 0.3;
  still.add(telescope);
  for (const [x, z, h] of [[west + 0.6, front - 0.6, 2.3], [east - 0.6, front - 0.6, 2.1], [east - 0.6, 0.7, 1.8]]) {
    still.add(decal(1, 1, x, z), at(piece('plant', { height: h }), x, 0, z));
  }

  // Tapping the desk says whose it is.
  const hit = new THREE.Mesh(new THREE.BoxGeometry(3.0, 1.3, 2.2), new THREE.MeshBasicMaterial());
  hit.position.set(mid, 0.65, dz + 0.35);
  hit.visible = false;
  hit.userData = { hit: true, stay: true, title: name || "The founder's desk", sub: title };
  g.add(hit);
  extras.push(hit.material);

  setLamps(scope, storey, [[mid, ry + 0.2, rz - 1.1, '#ffcf96', 11], [mid, 3.4, 4.9, '#ffe2bf', 9]]);
  freeze(still);
  useScope(null);
  return made(g, scope, extras, lift, {
    west, east, front, high, picks: [lift.call, hit, ...(aide ? [aide.hit] : [])],
    desk: { x: mid, z: dz + 0.85, name, title },
    assistant: aide, // where the founder's assistant stands and where to talk to her (walk.js)
    // Where the founder's notes hang (three/notes.js): in the library, a row at eye height in front of
    // the shelves, the newest nearest the lift, parted round the ladder and turned a little towards the
    // reading chairs, each on a thread from the ceiling.
    notes: {
      slots: [-3.25, -3.95, -4.65, -5.35, -6.85, -7.55, -8.25, -8.95].map((x) => ({ x, z: 0.98, turn: Math.atan2(-6.1 - x, 8) })),
      y: 1.52, high, where: 'in the library: step out of the lift and turn right',
    },
  });
}
