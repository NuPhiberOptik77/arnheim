// Arnheim's building: a company as a dollhouse at an angle, whose floors glide out into floor
// plans. It takes plain data (the company map, then each room's live data through setLive())
// and knows nothing about the page around it. Its craft (one lit model, cut-away walls,
// fit-to-view rig, render on demand, bloom) comes from House Control by 0xProbability, MIT
// licence: see THIRD_PARTY_NOTICES.md.
import * as THREE from '../vendor/three/three.module.js';
import { EffectComposer } from '../vendor/three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from '../vendor/three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from '../vendor/three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from '../vendor/three/addons/postprocessing/OutputPass.js';
import { at, box, cyl, decal, disposeTree, floorMesh, freeze, lampGlow, mat, newScope, useScope } from './three/kit.js';
import { piece } from './three/furniture.js';
import { D, H, ROOMS, W, paletteFor } from './three/rooms.js';
import { buildPerson } from './three/poe.js';

const rad = THREE.MathUtils.degToRad;
const clamp = THREE.MathUtils.clamp;
const lerp = THREE.MathUtils.lerp;
const smooth = THREE.MathUtils.smoothstep;

const SLAB = 0.26;
const STEP = H + SLAB;
const CURB = 0.14;
const FAR = 1.5;
const INNER = 0.72;
const GLIDE = 6;
const PART = 46;
const LABEL_ROOM = 1.6;
const MAX_PIXEL_RATIO = 1.5;
const PULSE_MS = 4000; // amber only breathes for this long after the last touch, then the model goes idle

const VIEWS = {
  building: { az: 5, el: 19, azSpan: [4, 58], elSpan: [9, 50] }, // nearly straight on
  floor: { az: 32, el: 49, azSpan: [4, 62], elSpan: [26, 72] },
  room: { az: 28, el: 44, azSpan: [2, 62], elSpan: [24, 72] },
  person: { az: 24, el: 17, azSpan: [2, 62], elSpan: [4, 60] }, // close enough to see Poe's face
};

const LAMP = {
  quiet: { color: '#ffc78f', level: 0.3 },
  working: { color: '#ffb066', level: 1 },
  needs: { color: '#ff8a1e', level: 1.05 },
  check: { color: '#8fb4ff', level: 0.75 },
  failed: { color: '#ff5a6e', level: 0.55 },
};

const THEMES = {
  dark: {
    sky: '#a49cf0', ground: '#1a1215', hemi: 0.46, sun: '#b9c0ff', sunI: 0.62, exposure: 1.08, lampK: 13, spotK: 15, bloom: 0.36, glass: '#3d5fae', glassI: 0.55,
    bg: { all: ['#57392a', '#0a0e1a'], needs: ['#663a14', '#0b0d16'], working: ['#5e4522', '#0b0e18'] },
  },
  light: {
    sky: '#ffffff', ground: '#c2b8a8', hemi: 1.75, sun: '#fff0da', sunI: 2.2, exposure: 0.92, lampK: 18, spotK: 20, bloom: 0.14, glass: '#bcd6ff', glassI: 0.7,
    bg: { all: ['#f7ead8', '#dfe5ee'], needs: ['#fbdcb6', '#e8e3dc'], working: ['#fae9c4', '#e6e5df'] },
  },
};

// Where each room sits on a floor plan: back row, then front row. A fifth room (such as the
// Company room) carries the back row on to the right, so nobody else's room gets smaller walls.
const SLOTS = [[0, 0], [1, 0], [0, 1], [1, 1], [2, 0]];
// Tall shelves go at the back of the floor plan, so they hide nothing behind them. Other rooms keep
// the order the company map gives them, unless a room says where it goes with "order".
const KIND_ORDER = { goals: 0, code: 1, conversations: 2, work: 3 };
const PLAN_WALLS = [
  { n: FAR, w: FAR, e: CURB, s: CURB },
  { n: FAR, w: INNER, e: CURB, s: CURB },
  { n: INNER, w: FAR, e: CURB, s: CURB },
  { n: INNER, w: INNER, e: CURB, s: CURB },
  { n: FAR, w: INNER, e: CURB, s: CURB },
];

export function createBuilding(canvas, org, { onPick, onHover, onStatus, onWalk, labels, insets = [64, 44] }) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: false, alpha: false, powerPreference: 'default' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, MAX_PIXEL_RATIO));
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap;
  renderer.shadowMap.autoUpdate = false;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(24, 1, 0.5, 260);
  const raycaster = new THREE.Raycaster();
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const hitMaterial = new THREE.MeshBasicMaterial();
  const blocker = new THREE.MeshBasicMaterial({ colorWrite: false, depthWrite: false });

  const defs = [...org.floors, org.lobby, org.basement].filter(Boolean);
  const X0 = -2 * W;
  // The longest row of rooms. Past four, the extra room is a wing off the end of the top floor.
  const ROW_ROOMS = Math.max(...defs.map((def) => (def.rooms || org.rooms).length + (def.extraRooms?.length || 0)));
  const BOTTOM = -STEP - SLAB - 0.5;
  const ROOF_Y = org.floors.length * STEP + H;
  const SIGN_TOP = ROOF_Y + 3.2;

  let themeName = 'dark';
  let T = THEMES.dark;
  let live = {};
  let liveSig = '';
  let view = {};
  let scenePick = { mode: 'all' };
  let personRoom = null; // the room Poe stands in
  let personWake = -Infinity;
  const storeys = [];
  const rooms = new Map();
  let signGroup = null;
  let groundGroup = null;
  let signHit = null;
  let signMaterial = null;
  let shadowsDirty = true;
  let moonOnly = false;
  let settling = false;
  let resized = false;
  let selected = null;
  const signPart = { value: 0, goal: 0 };
  let walker = null; // a first-person walk, while one is going (walk.js)
  let walkStart = null;
  let version = 0; // goes up whenever what stands in the rooms changes, so a walk looks again

  /* ---------- light and background ---------- */

  const hemi = new THREE.HemisphereLight(0xffffff, 0x000000, 1);
  const moon = new THREE.DirectionalLight(0xffffff, 1);
  moon.castShadow = true;
  moon.shadow.mapSize.set(2048, 2048);
  moon.shadow.autoUpdate = false;
  moon.shadow.bias = -0.0008;
  moon.shadow.normalBias = 0.04;
  moon.shadow.radius = 4;
  moon.shadow.camera.near = 1;
  moon.shadow.camera.far = 90;
  scene.add(hemi, moon, moon.target);

  // Four real lamps with soft shadows, lent to whichever floor is out on the table.
  const spots = Array.from({ length: 4 }, () => {
    const spot = new THREE.SpotLight(0xffffff, 0, 0, 1.22, 0.8, 2);
    spot.castShadow = true;
    spot.shadow.mapSize.set(1024, 1024);
    spot.shadow.autoUpdate = false;
    spot.shadow.camera.near = 0.15;
    spot.shadow.camera.far = 9;
    spot.shadow.bias = -0.0006;
    spot.shadow.normalBias = 0.03;
    spot.shadow.radius = 5;
    scene.add(spot, spot.target);
    return spot;
  });

  const bgCanvas = document.createElement('canvas');
  bgCanvas.width = 4;
  bgCanvas.height = 256;
  const bgTexture = new THREE.CanvasTexture(bgCanvas);
  bgTexture.colorSpace = THREE.SRGBColorSpace;
  scene.background = bgTexture;
  const bg = { top: new THREE.Color('#57392a'), bottom: new THREE.Color('#0a0e1a'), goalTop: new THREE.Color('#57392a'), goalBottom: new THREE.Color('#0a0e1a') };
  function paintBackground() {
    const g = bgCanvas.getContext('2d');
    const fill = g.createLinearGradient(0, 0, 0, 256);
    fill.addColorStop(0, `#${bg.top.getHexString()}`);
    fill.addColorStop(0.72, `#${bg.bottom.getHexString()}`);
    fill.addColorStop(1, `#${bg.bottom.getHexString()}`);
    g.fillStyle = fill;
    g.fillRect(0, 0, 4, 256);
    bgTexture.needsUpdate = true;
  }

  const glassMaterial = new THREE.MeshStandardMaterial({ color: '#9cc0ff', roughness: 0.1, emissive: '#3d5fae', emissiveIntensity: 0.55 });

  /* ---------- the model ---------- */

  function buildRoom(storey, def, i) {
    const kind = storey.kindOf(def);
    const spec = ROOMS[kind];
    const scope = newScope();
    useScope(scope);
    const g = new THREE.Group();
    const room = {
      key: `${storey.id}/${def.id}`, floorId: storey.id, roomId: def.id, label: def.label, kind, i, storey, g, scope, spec,
      walls: {}, objects: [], moreChips: [], info: {}, sig: null, content: null, mood: 'quiet', hot: false, gain: 1,
      level: 0.3, goal: 0.3, color: new THREE.Color(LAMP.quiet.color), goalColor: new THREE.Color(LAMP.quiet.color), upper: [], signs: [],
      rowX: i * W, planX: SLOTS[i][0] * W, planZ: SLOTS[i][1] * D,
      lamp: new THREE.Vector3(...spec.lamps.main), lamp2: new THREE.Vector3(...spec.lamps.side),
      rowWalls: { n: H, w: H, e: CURB, s: CURB }, planWalls: PLAN_WALLS[i],
    };

    const frozen = new THREE.Group();
    g.add(frozen);
    frozen.add(floorMesh({ x: 0, z: 0, w: W, d: D }, kind === 'library' ? 'walnut' : storey.style.floor));
    frozen.add(at(box(W, SLAB, D, mat('#57524a', { rough: 0.9 }), { r: 0 }), W / 2, -SLAB - 0.002, D / 2));

    const body = mat(kind === 'library' ? '#dccab2' : storey.style.wall, { rough: 0.95 });
    const cap = mat('#2b2e38', { rough: 0.8 });
    const faces = [body, body, cap, body, body, body];
    const wall = (w, d, x, z) => {
      const m = at(box(w, 1, d, body, { r: 0 }), x, 0, z);
      m.material = faces;
      m.castShadow = true;
      m.receiveShadow = true;
      m.userData.live = true;
      g.add(m);
      return m;
    };
    const t = 0.09;
    room.walls.n = wall(W + t, t, W / 2, 0);
    room.walls.s = wall(W + t * 0.6, t * 0.7, W / 2, D);
    room.walls.w = wall(t, D + t, 0, D / 2);
    room.walls.e = wall(t * 0.7, D + t * 0.6, W, D / 2);
    const skirt = mat('#f4f1ea', { rough: 0.85 });
    frozen.add(at(box(W, 0.085, 0.02, skirt, { r: 0 }), W / 2, 0, 0.055), at(box(0.02, 0.085, D, skirt, { r: 0 }), 0.055, 0, D / 2));

    // A window on the back wall, seen only while the floor is in the building.
    const pane = new THREE.Group();
    if (storey.role !== 'basement') {
      const wx = i % 2 === 0 ? W * 0.3 : W * 0.68;
      const frame = mat('#2c3142', { rough: 0.6 });
      const glass = at(box(1.3, 1, 0.01, glassMaterial, { r: 0 }), wx, 0.98, 0.05);
      glass.userData.live = true;
      pane.add(glass);
      for (const [fx, fy, fw, fh] of [[0, 0, 1.36, 0.05], [0, 1, 1.36, 0.05], [-0.66, 0, 0.05, 1.04], [0.66, 0, 0.05, 1.04], [0, 0, 0.04, 1.02]]) {
        const bar = at(box(fw, fh, 0.03, frame, { r: 0 }), wx + fx, 0.97 + fy, 0.06);
        bar.userData.live = true;
        pane.add(bar);
      }
    }
    g.add(pane);
    room.pane = pane;

    // The lamps: a pendant over the middle and a floor or bench lamp in a corner.
    room.glow = lampGlow();
    const [lx, ly, lz] = spec.lamps.main;
    frozen.add(
      at(cyl(0.006, 0.006, H - ly - 0.1, mat('#23262e'), 6), lx, ly + 0.1, lz),
      at(cyl(0.05, 0.06, 0.05, mat('#23262e', { rough: 0.4, metal: 0.6 }), 12), lx, ly + 0.12, lz),
      at(new THREE.Mesh(new THREE.SphereGeometry(0.17, 24, 14), room.glow), lx, ly, lz),
    );
    room.glow2 = lampGlow();
    const [sx, sy, sz] = spec.lamps.side;
    if (kind === 'machine') {
      frozen.add(at(cyl(0.06, 0.1, 0.1, room.glow2, 18), sx, sy - 0.05, sz));
    } else if (spec.lamps.deskTop != null) {
      // A desk lamp standing on a counter.
      const top = spec.lamps.deskTop;
      const brass = mat('#c9a06a', { rough: 0.35, metal: 0.6 });
      frozen.add(
        at(cyl(0.06, 0.07, 0.02, brass, 18), sx, top, sz),
        at(cyl(0.008, 0.008, sy - top - 0.12, brass, 6), sx, top + 0.02, sz),
        at(cyl(0.06, 0.1, 0.14, room.glow2, 24), sx, sy - 0.12, sz),
      );
    } else {
      frozen.add(
        decal(0.7, 0.7, sx, sz),
        at(cyl(0.13, 0.15, 0.02, mat('#23262e', { rough: 0.4, metal: 0.5 }), 18), sx, 0, sz),
        at(cyl(0.011, 0.011, sy - 0.2, mat('#23262e', { rough: 0.4, metal: 0.5 }), 6), sx, 0.02, sz),
        at(cyl(0.13, 0.18, 0.28, room.glow2, 24), sx, sy - 0.16, sz),
      );
    }

    const ctx = { signs: room.signs, upper: room.upper };
    spec.decor(frozen, storey.style, ctx, room);
    for (const part of [...room.upper, ...room.signs]) { frozen.remove(part); g.add(part); }
    freeze(frozen);
    if (spec.person) {
      room.person = buildPerson(spec.person);
      g.add(room.person.group);
      personRoom = room;
    }

    const hit = new THREE.Mesh(new THREE.BoxGeometry(W, H + SLAB, D), hitMaterial);
    hit.position.set(W / 2, (H - SLAB) / 2, D / 2);
    hit.visible = false;
    hit.userData = { hit: true, floorId: storey.id, roomId: def.id };
    g.add(hit);
    room.hit = hit;

    // Invisible full-height walls so a real lamp's light stays in its room even with the walls cut.
    const blockers = new THREE.Group();
    const bx = SLOTS[i][0] === 0 ? W : 0;
    const bz = SLOTS[i][1] === 0 ? D : 0;
    const sideX = new THREE.Mesh(new THREE.BoxGeometry(0.04, H, D), blocker);
    sideX.position.set(bx, H / 2, D / 2);
    const sideZ = new THREE.Mesh(new THREE.BoxGeometry(W, H, 0.04), blocker);
    sideZ.position.set(W / 2, H / 2, bz);
    for (const m of [sideX, sideZ]) { m.castShadow = true; m.userData.live = true; blockers.add(m); }
    blockers.visible = false;
    g.add(blockers);
    room.blockers = blockers;

    useScope(null);
    storey.group.add(g);
    rooms.set(room.key, room);
    return room;
  }

  function buildStorey(def, order) {
    const role = def.id === org.basement?.id ? 'basement' : def.id === org.lobby?.id ? 'lobby' : 'floor';
    // A room's kind says what stands in it. Basement rooms are machines, apart from the library.
    const kindOf = (r) => {
      const kind = r.kind || (role === 'basement' ? (r.id === 'library' ? 'library' : 'machine') : r.id);
      return ROOMS[kind] ? kind : 'lounge';
    };
    const index = org.floors.indexOf(def);
    const y = role === 'basement' ? -STEP : role === 'lobby' ? 0 : (org.floors.length - index) * STEP;
    const list = [...(def.rooms || org.rooms), ...(def.extraRooms || [])];
    const cols = list.length > 4 ? 3 : 2;
    const storey = {
      id: def.id, label: def.label, order, role, y, def, style: paletteFor(def, role, index), kindOf, cols, ox: -(cols * W) / 2,
      group: new THREE.Group(), rooms: [], t: 0, goalT: 0, part: 0, goalPart: 0,
    };
    scene.add(storey.group);
    const place = (r, i) => r.order ?? KIND_ORDER[kindOf(r)] ?? 10 + i;
    const ordered = list.map((r, i) => [place(r, i), r]).sort((a, b) => a[0] - b[0]).map(([, r]) => r);
    ordered.forEach((r, i) => storey.rooms.push(buildRoom(storey, r, i)));
    storeys.push(storey);
    placeStorey(storey);
  }

  function buildSign() {
    useScope(null);
    signGroup = new THREE.Group();
    const roof = mat('#3a3631', { rough: 0.9 });
    const trim = mat('#d9d3c7', { rough: 0.8 });
    signGroup.add(
      at(box(4 * W + 0.5, 0.22, D + 0.4, roof, { r: 0.02 }), 0, ROOF_Y, 0),
      at(box(4 * W + 0.5, 0.26, 0.12, trim, { r: 0.01 }), 0, ROOF_Y + 0.22, -D / 2 - 0.14),
      at(box(0.12, 0.26, D + 0.4, trim, { r: 0.01 }), -2 * W - 0.19, ROOF_Y + 0.22, 0),
    );
    if (ROW_ROOMS > 4) {
      const reach = (ROW_ROOMS - 4) * W;
      signGroup.add(
        at(box(reach + 0.25, 0.22, D + 0.4, roof, { r: 0.02 }), 2 * W + reach / 2 + 0.125, ROOF_Y, 0),
        at(box(reach + 0.25, 0.26, 0.12, trim, { r: 0.01 }), 2 * W + reach / 2 + 0.125, ROOF_Y + 0.22, -D / 2 - 0.14),
      );
    }
    const canvasW = 2048;
    const c = document.createElement('canvas');
    c.width = canvasW;
    c.height = 512;
    const g = c.getContext('2d');
    g.fillStyle = '#10131b';
    g.fillRect(0, 0, canvasW, 512);
    g.textAlign = 'center';
    g.textBaseline = 'middle';
    g.fillStyle = '#ffe3bd';
    g.font = '800 228px -apple-system, "Helvetica Neue", Arial, sans-serif';
    g.fillText(org.company, canvasW / 2, 200);
    g.fillStyle = '#f4d7b0';
    g.font = '600 92px -apple-system, "Helvetica Neue", Arial, sans-serif';
    g.fillText(`Mission: ${org.mission || 'Not written yet'}`, canvasW / 2, 400);
    const tex = new THREE.CanvasTexture(c);
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.anisotropy = 8;
    signMaterial = new THREE.MeshStandardMaterial({ map: tex, emissiveMap: tex, emissive: '#ffffff', emissiveIntensity: 1.5, roughness: 0.5 });
    const sign = new THREE.Group();
    const sw = 10.4;
    const sh = 2.6;
    const face = new THREE.Mesh(new THREE.PlaneGeometry(sw, sh), signMaterial);
    face.position.set(0, 1.9, 0.12);
    face.userData.live = true;
    const back = at(box(sw + 0.24, sh + 0.24, 0.2, mat('#2a2622', { rough: 0.7 }), { r: 0.03 }), 0, 1.9 - sh / 2 - 0.12, 0);
    sign.add(back, face);
    for (const sx of [-1, 1]) sign.add(at(box(0.16, 0.7, 0.16, mat('#2a2622', { rough: 0.7 }), { r: 0.01 }), sx * (sw / 2 - 1), 0, 0));
    sign.position.set(-0.3, ROOF_Y + 0.22, -0.35);
    sign.rotation.y = rad(16);
    signGroup.add(sign);
    for (const [x, z, h] of [[-8.6, 1.3, 1.1], [8.6, 1.4, 1.3], [8, -1.2, 0.9]]) {
      signGroup.add(decal(1.1, 1.1, x, z, { y: ROOF_Y + 0.235 }), at(piece('plant', { height: h }), x, ROOF_Y + 0.22, z));
    }
    signHit = new THREE.Mesh(new THREE.BoxGeometry(sw, sh + 0.7, 0.5), hitMaterial);
    signHit.position.set(-0.3, ROOF_Y + 0.22 + 1.6, -0.3);
    signHit.visible = false;
    signHit.userData = { hit: true, company: true };
    signGroup.add(signHit);
    freeze(signGroup);
    scene.add(signGroup);
  }

  function buildGround() {
    useScope(null);
    const root = new THREE.Group();
    const earth = mat('#4a3b2c', { rough: 1 });
    const grass = mat('#4d6b45', { rough: 1 });
    const plinth = mat('#4a443c', { rough: 0.9 });
    const left = X0 - 4.6;
    const depth = STEP + SLAB + 0.4;
    root.add(
      at(box(4 * W + 7.4, 0.42, D + 2.6, plinth, { r: 0.1 }), -1.6, BOTTOM - 0.42, 0),
      at(box(4.6, depth, D + 1.8, earth, { r: 0 }), left + 2.3, -depth, 0),
      at(box(4.6, 0.12, D + 1.8, grass, { r: 0.02 }), left + 2.3, -0.12, 0),
      at(box(4 * W + 0.4, depth + 0.1, 0.5, earth, { r: 0 }), 0, -depth, -D / 2 - 0.32),
    );
    for (const [x, z, h] of [[left + 1.5, 1.2, 1.9], [left + 3.2, -1, 1.5]]) {
      root.add(decal(1.5, 1.5, x, z, { y: 0.012 }), at(piece('plant', { height: h }), x, 0, z));
    }
    // Steel struts under the wing, from the floor below up to the wing's slab.
    if (ROW_ROOMS > 4) {
      const steel = mat('#5f656f', { rough: 0.5, metal: 0.4 });
      const rise = STEP - SLAB;
      const reach = 3.4;
      for (const z of [-D / 2 + 0.3, D / 2 - 0.3]) {
        const strut = at(box(0.13, Math.hypot(rise, reach), 0.13, steel, { r: 0 }), -X0, (org.floors.length - 1) * STEP, z);
        strut.rotation.z = -Math.atan2(reach, rise);
        root.add(strut);
      }
    }
    freeze(root);
    scene.add(root);
    groundGroup = root;
  }

  /* ---------- how a floor moves between the building and the table ---------- */

  function placeStorey(s) {
    const t = s.t;
    const xp = smooth(t, 0.35, 1);
    const zp = smooth(t, 0, 0.6);
    const wp = smooth(t, 0.05, 0.55);
    s.group.position.set(lerp(X0, s.ox, xp), s.y + s.part * PART, -D / 2 + GLIDE * smooth(t, 0, 0.5));
    s.group.visible = Math.abs(s.part) < 0.92;
    for (const r of s.rooms) {
      r.g.position.set(lerp(r.rowX, r.planX, xp), 0, lerp(0, r.planZ, zp));
      for (const side of ['n', 's', 'e', 'w']) r.walls[side].scale.y = lerp(r.rowWalls[side], r.planWalls[side], wp);
      r.pane.visible = t < 0.1;
      for (const part of r.upper) part.visible = t < 0.1;
      r.blockers.visible = t > 0.96;
    }
  }

  function roomWorld(r, out, x = 0, y = 0, z = 0) {
    return out.set(
      r.storey.group.position.x + r.g.position.x + x,
      r.storey.group.position.y + y,
      r.storey.group.position.z + r.g.position.z + z,
    );
  }

  /* ---------- live data ---------- */

  function chooseMood(room) {
    const m = LAMP[room.mood] || LAMP.quiet;
    const lift = room.kind === 'machine' && room.mood === 'quiet' ? 1.5 : 1;
    room.goal = m.level * lift * room.gain + (room.hot ? 0.1 : 0);
    room.goalColor.set(m.color);
  }

  function sceneGain(room) {
    let on = true;
    if (scenePick.mode === 'needs') on = room.mood === 'needs' || room.mood === 'check';
    else if (scenePick.mode === 'working') on = room.mood === 'working' || !!room.info.working;
    else if (scenePick.mode === 'floor') on = room.floorId === scenePick.floor;
    return on ? 1 : 0.06;
  }

  function dimEmissives(room) {
    const k = room.gain < 0.5 ? 0.04 : 1;
    for (const m of room.scope.materials.values()) {
      if (m.userData.baseEmissive) m.emissiveIntensity = m.userData.baseEmissive * k;
    }
  }

  function fillRoom(room) {
    if (room.content) {
      room.g.remove(room.content);
      disposeTree(room.content);
    }
    useScope(room.scope);
    room.objects = [];
    room.moreChips = [];
    const content = new THREE.Group();
    const ctx = {
      object(o) {
        const hit = new THREE.Mesh(new THREE.BoxGeometry(o.w, o.h, o.d), hitMaterial);
        hit.position.set(o.x, o.y + o.h / 2, o.z);
        hit.visible = false;
        hit.userData = { hit: true, floorId: room.floorId, roomId: room.roomId, href: o.href, title: o.title, sub: o.sub };
        content.add(hit);
        room.objects.push({ ...o, hit });
      },
      more(count, x, y, z) { room.moreChips.push({ count, x, y, z }); },
    };
    room.spec.fill(content, room.info, ctx, room.storey.style);
    room.g.add(content);
    freeze(content);
    useScope(null);
    room.content = content;
    dimEmissives(room);
  }

  function setLive(model) {
    const whole = JSON.stringify(model);
    if (whole === liveSig) return; // the panel's data moved on but nothing the model shows did
    liveSig = whole;
    live = model;
    let changed = false;
    for (const room of rooms.values()) {
      const info = model[room.key] || {};
      const sig = JSON.stringify(info);
      if (sig === room.sig) continue;
      room.sig = sig;
      room.info = info;
      room.mood = info.state || 'quiet';
      room.gain = sceneGain(room);
      chooseMood(room);
      fillRoom(room);
      room.live?.set(info);
      changed = true;
    }
    if (changed) { shadowsDirty = true; version += 1; }
    rebuildTargets();
    wake(3);
  }

  function setScene(next) {
    scenePick = next;
    for (const room of rooms.values()) {
      room.gain = sceneGain(room);
      chooseMood(room);
      dimEmissives(room);
    }
    applyPalette();
    wake(3);
  }

  function setTheme(dark) {
    themeName = dark ? 'dark' : 'light';
    T = THEMES[themeName];
    hemi.color.set(T.sky);
    hemi.groundColor.set(T.ground);
    moon.color.set(T.sun);
    renderer.toneMappingExposure = T.exposure;
    bloom.strength = T.bloom;
    glassMaterial.emissive.set(T.glass);
    glassMaterial.emissiveIntensity = T.glassI;
    if (signMaterial) signMaterial.emissiveIntensity = dark ? 1.5 : 1.05;
    applyPalette();
    wake(3);
  }

  function applyPalette() {
    const dim = scenePick.mode === 'all' ? 1 : 0.72;
    hemi.intensity = T.hemi * dim;
    moon.intensity = T.sunI * dim;
    const p = T.bg;
    const picked = scenePick.mode === 'floor' && storeys.find((s) => s.id === scenePick.floor);
    const pair = scenePick.mode === 'floor' ? [picked?.style.sky?.[themeName] || p.all[0], p.all[1]] : p[scenePick.mode] || p.all;
    bg.goalTop.set(pair[0]);
    bg.goalBottom.set(pair[1]);
  }

  function highlight(next) {
    let changed = false;
    for (const room of rooms.values()) {
      const on = !!next && room.floorId === next.floor && (!next.room || room.roomId === next.room);
      if (on !== room.hot) {
        room.hot = on;
        chooseMood(room);
        changed = true;
      }
    }
    if (changed) wake(2);
  }

  /* ---------- camera rig ---------- */

  const rig = {
    az: VIEWS.building.az, el: VIEWS.building.el, dist: 90, target: new THREE.Vector3(0, 9, 0),
    goal: { az: VIEWS.building.az, el: VIEWS.building.el, dist: 90, target: new THREE.Vector3(0, 9, 0) },
    zoom: 1,
  };
  let width = 1;
  let height = 1;
  const [topInset, bottomInset] = insets;
  const fwd = new THREE.Vector3();
  const right = new THREE.Vector3();
  const up = new THREE.Vector3();
  const v = new THREE.Vector3();

  function basis(az, el) {
    const a = rad(az);
    const e = rad(el);
    fwd.set(-Math.sin(a) * Math.cos(e), -Math.sin(e), -Math.cos(a) * Math.cos(e));
    right.set(Math.cos(a), 0, -Math.sin(a));
    up.crossVectors(right, fwd);
  }

  function fitDistance(bounds, az, el, fill) {
    basis(az, el);
    const c = bounds.getCenter(new THREE.Vector3());
    const usable = Math.max(0.3, (height - topInset - bottomInset) / height);
    const tanV = Math.tan(rad(camera.fov / 2)) * fill * usable;
    const tanH = Math.tan(rad(camera.fov / 2)) * camera.aspect * fill;
    let dist = 0;
    for (let i = 0; i < 8; i++) {
      v.set(i & 1 ? bounds.max.x : bounds.min.x, i & 2 ? bounds.max.y : bounds.min.y, i & 4 ? bounds.max.z : bounds.min.z).sub(c);
      const depth = v.dot(fwd);
      dist = Math.max(dist, Math.abs(v.dot(right)) / tanH - depth, Math.abs(v.dot(up)) / tanV - depth);
    }
    return { dist, center: c };
  }

  const focusStorey = () => storeys.find((s) => s.id === view.floor) || null;
  const focusRoom = () => (view.floor && view.room ? rooms.get(`${view.floor}/${view.room}`) : null);
  const viewName = () => (focusRoom() ? (view.close && focusRoom().person ? 'person' : 'room') : view.floor ? 'floor' : 'building');

  function aim() {
    const s = focusStorey();
    const r = focusRoom();
    const bounds = new THREE.Box3();
    let fill = 1;
    if (s) {
      const ox = s.ox;
      const oz = -D / 2 + GLIDE;
      if (r?.person && view.close) {
        // Close enough to see the face of the person at the desk.
        const [px, , pz] = r.spec.person.at;
        bounds.min.set(ox + r.planX + px - 0.7, s.y + 0.95, oz + r.planZ + pz - 0.3);
        bounds.max.set(ox + r.planX + px + 0.7, s.y + 1.9, oz + r.planZ + pz + 0.45);
        fill = 0.92;
      } else if (r) {
        bounds.min.set(ox + r.planX, s.y, oz + r.planZ);
        bounds.max.set(ox + r.planX + W, s.y + 1.5, oz + r.planZ + D);
        fill = 0.88;
      } else {
        bounds.min.set(ox, s.y, oz);
        bounds.max.set(ox + s.cols * W, s.y + 1.2, oz + 2 * D);
        fill = 0.95;
      }
    } else {
      bounds.min.set(X0 - LABEL_ROOM, BOTTOM, -D / 2);
      bounds.max.set(X0 + ROW_ROOMS * W + 0.4, SIGN_TOP, D / 2);
    }
    const { dist, center } = fitDistance(bounds, rig.goal.az, rig.goal.el, fill);
    rig.goal.dist = dist * rig.zoom;
    rig.goal.target.copy(center);
    // In the building view, shift the model right to leave room for the floor names.
    if (!s) rig.goal.target.addScaledVector(right, -Math.min(2.4, Math.max(0, 74 / (width / (2 * dist * Math.tan(rad(camera.fov / 2)) * camera.aspect)) - 0.6)));
    if (reduced.matches) {
      rig.az = rig.goal.az;
      rig.el = rig.goal.el;
      rig.dist = rig.goal.dist;
      rig.target.copy(rig.goal.target);
    }
  }

  function updateRig(dt) {
    const k = reduced.matches ? 1 : 1 - Math.exp(-dt * 4.2);
    const g = rig.goal;
    const gap = Math.abs(g.az - rig.az) + Math.abs(g.el - rig.el) + Math.abs(g.dist - rig.dist) * 0.5 + rig.target.distanceTo(g.target);
    if (gap > 0.003) {
      rig.az += (g.az - rig.az) * k;
      rig.el += (g.el - rig.el) * k;
      rig.dist += (g.dist - rig.dist) * k;
      rig.target.lerp(g.target, k);
    }
    basis(rig.az, rig.el);
    camera.position.copy(rig.target).addScaledVector(fwd, -rig.dist);
    camera.lookAt(rig.target);
    return gap > 0.003;
  }

  function aimLights(near = null, reach = 0) {
    const s = focusStorey();
    const dir = new THREE.Vector3(7, 15, 10).normalize();
    const goal = near || (s ? rig.goal.target : new THREE.Vector3(0, 9, 0));
    moon.target.position.copy(goal);
    moon.position.copy(goal).addScaledVector(dir, 42);
    const span = reach || (s ? 13 : 24);
    const sc = moon.shadow.camera;
    sc.left = sc.bottom = -span;
    sc.right = sc.top = span;
    sc.updateProjectionMatrix();
    moon.updateMatrixWorld();
    moon.target.updateMatrixWorld();
  }

  const ring = new THREE.Mesh(
    new THREE.RingGeometry(0.48, 0.56, 40).rotateX(-Math.PI / 2),
    new THREE.MeshBasicMaterial({ color: '#ffe2bd', transparent: true, opacity: 0.95, depthWrite: false, toneMapped: false }),
  );
  ring.visible = false;
  scene.add(ring);

  function focus(next) {
    // While someone walks the building the floors stay put; the view applies when the walk ends.
    if (walker) { view = { floor: next.floor, room: next.room, item: next.item, close: !!next.close }; return; }
    const moved = next.floor !== view.floor || next.room !== view.room || !!next.close !== !!view.close;
    view = { floor: next.floor, room: next.room, item: next.item, close: !!next.close };
    if (personRoom && next.floor === personRoom.floorId) personWake = performance.now();
    const s = focusStorey();
    if (moved) {
      const name = viewName();
      rig.zoom = 1;
      rig.goal.az = VIEWS[name].az;
      rig.goal.el = VIEWS[name].el;
    }
    for (const st of storeys) {
      st.goalT = s && st === s ? 1 : 0;
      st.goalPart = s && st !== s ? (st.order < s.order ? 1 : -1) : 0;
    }
    signPart.goal = s ? 1 : 0;
    aim();
    aimLights();
    selected = null;
    const r = focusRoom();
    if (r && next.item) selected = r.objects.find((o) => o.href === next.item) || null;
    rebuildTargets();
    moonOnly = true;
    wake(3);
  }

  function zoomBy(factor) {
    rig.zoom = clamp(rig.zoom * factor, 0.55, 1.3);
    aim();
    wake(2);
  }
  function turn(dAz, dEl) {
    const name = viewName();
    rig.goal.az = clamp(rig.goal.az + dAz, ...VIEWS[name].azSpan);
    rig.goal.el = clamp(rig.goal.el + dEl, ...VIEWS[name].elSpan);
    aim();
    wake(2);
  }
  function resetView() {
    const name = viewName();
    rig.zoom = 1;
    rig.goal.az = VIEWS[name].az;
    rig.goal.el = VIEWS[name].el;
    aim();
    wake(2);
  }

  /* ---------- picking ---------- */

  let targets = [];
  function rebuildTargets() {
    targets = [];
    const s = focusStorey();
    if (s) {
      for (const r of s.rooms) {
        targets.push(r.hit);
        for (const o of r.objects) targets.push(o.hit);
      }
    } else {
      for (const st of storeys) for (const r of st.rooms) targets.push(r.hit);
      if (signHit) targets.push(signHit);
    }
  }

  const ndc = new THREE.Vector2();
  function pickAt(event) {
    const box2 = canvas.getBoundingClientRect();
    ndc.set(((event.clientX - box2.left) / box2.width) * 2 - 1, -((event.clientY - box2.top) / box2.height) * 2 + 1);
    raycaster.setFromCamera(ndc, camera);
    const hits = raycaster.intersectObjects(targets, false);
    if (!hits.length) return null;
    return (hits.find((h) => h.object.userData.href) || hits[0]).object.userData;
  }

  function describe(hit) {
    if (hit.company) return { title: org.company, sub: `Mission: ${org.mission || 'Not written yet'}` };
    const room = rooms.get(`${hit.floorId}/${hit.roomId}`);
    if (hit.title) return { title: hit.title, sub: hit.sub };
    if (!view.floor) {
      const lines = live[`floor:${hit.floorId}`]?.lines || [];
      return { title: room?.storey.label, sub: lines.map((l) => l.text).join(', ') };
    }
    const info = room?.info || {};
    return { title: room?.label, sub: info.sub ?? [info.big, info.detail].filter((x) => x != null && x !== '').join(' ') };
  }

  let press = null;
  let lastActive = performance.now();
  const touched = () => { lastActive = performance.now(); };
  canvas.addEventListener('pointerdown', (event) => {
    if (walker) return; // the walk has its own way of looking and tapping
    touched();
    press = { x: event.clientX, y: event.clientY, az: rig.goal.az, el: rig.goal.el, moved: false };
    canvas.setPointerCapture?.(event.pointerId);
  });
  canvas.addEventListener('pointermove', (event) => {
    if (walker) return;
    touched();
    if (press) {
      const dx = event.clientX - press.x;
      const dy = event.clientY - press.y;
      if (!press.moved && Math.hypot(dx, dy) > 5) { press.moved = true; canvas.style.cursor = 'grabbing'; onHover?.(null); }
      if (press.moved) {
        const name = viewName();
        rig.goal.az = clamp(press.az - dx * 0.3, ...VIEWS[name].azSpan);
        rig.goal.el = clamp(press.el + dy * 0.22, ...VIEWS[name].elSpan);
        aim();
        wake(2);
      }
      return;
    }
    const hit = pickAt(event);
    canvas.style.cursor = hit ? 'pointer' : 'grab';
    highlight(hit && !hit.company ? (view.floor ? { floor: hit.floorId, room: hit.roomId } : { floor: hit.floorId }) : null);
    const box2 = canvas.getBoundingClientRect();
    onHover?.(hit ? describe(hit) : null, event.clientX - box2.left, event.clientY - box2.top);
  });
  canvas.addEventListener('pointerup', (event) => {
    if (walker) return;
    const wasTap = press && !press.moved;
    press = null;
    canvas.style.cursor = 'grab';
    if (!wasTap) return;
    const hit = pickAt(event);
    if (hit) { onHover?.(null); onPick?.(hit); }
  });
  canvas.addEventListener('pointercancel', () => { press = null; });
  canvas.addEventListener('pointerleave', () => { if (!walker) { onHover?.(null); highlight(null); } });
  canvas.addEventListener('wheel', (event) => {
    event.preventDefault();
    if (walker) return;
    touched();
    zoomBy(Math.exp(event.deltaY * 0.0014));
  }, { passive: false });
  canvas.style.cursor = 'grab';

  /* ---------- labels: real text over the model, only as many as fit ---------- */

  const labelEls = new Map();
  const shortTitle = (text) => {
    const s = String(text || '');
    if (s.length <= 36) return s;
    return `${s.slice(0, 36).replace(/\s+\S*$/, '')}...`;
  };
  const infoText = (info) => info.sub ?? [info.big, info.detail].filter((x) => x != null && x !== '').join(' ');

  const personLabel = (room) => ({
    key: 'person', title: room.spec.person.name, sub: 'Receptionist', kind: 'quiet', align: 'center', room,
    local: [room.spec.person.at[0], 2.02, room.spec.person.at[2]], rank: 0,
  });

  function wantedLabels() {
    if (walker) return walker.labels();
    const out = [];
    const s = focusStorey();
    const r = focusRoom();
    if (!s) {
      for (const st of storeys) {
        if (st.part !== 0 || st.t > 0.05 || st.rooms.every((room) => room.gain < 0.5)) continue;
        const lines = live[`floor:${st.id}`]?.lines || [];
        out.push({
          key: `f:${st.id}`, title: st.label, sub: lines.map((l) => l.text).join(', '), kind: lines[0]?.kind || 'quiet', align: 'right',
          at: [X0 - 0.2, st.y + H * 0.5, D / 2], rank: lines.some((l) => l.kind === 'needs') ? 0 : 1,
        });
      }
    } else if (!r && s.t > 0.85) {
      for (const room of s.rooms) {
        out.push({ key: `r:${room.key}`, title: room.label, sub: infoText(room.info), kind: room.mood, align: 'center', room, local: [W / 2, room.planWalls.n + 0.3, 0.15], rank: 0 });
        for (const m of room.moreChips) out.push({ key: `m:${room.key}:${m.x}`, title: `+${m.count} more`, kind: 'quiet', align: 'center', room, local: [m.x, m.y + 0.25, m.z], rank: 2 });
      }
      if (personRoom?.storey === s) out.push(personLabel(personRoom));
    } else if (r && s.t > 0.85) {
      out.push({ key: `r:${r.key}`, title: r.label, sub: infoText(r.info), kind: r.mood, align: 'center', room: r, local: [W / 2, r.planWalls.n + 0.5, 0.1], rank: 0 });
      for (const m of r.moreChips) out.push({ key: `m:${r.key}:${m.x}`, title: `+${m.count} more`, kind: 'quiet', align: 'center', room: r, local: [m.x, m.y + 0.25, m.z], rank: 1 });
      if (r === personRoom) out.push(personLabel(r));
      for (const o of r.objects) {
        if (!o.title || o.h < 0.5 || o.person) continue;
        out.push({
          key: `o:${r.key}:${o.href || o.title}`, title: shortTitle(o.title), kind: o.mood || 'quiet', align: 'center', room: r,
          local: [o.x, o.y + o.h + 0.2, o.z], rank: o.mood === 'needs' ? 1 : o.mood === 'working' ? 2 : 3, small: true,
        });
      }
    }
    return out.sort((a, b) => a.rank - b.rank);
  }

  function drawLabels() {
    const placed = [];
    const seen = new Set();
    for (const l of wantedLabels()) {
      let el = labelEls.get(l.key);
      if (!el) {
        el = document.createElement('div');
        el.append(document.createElement('b'), document.createElement('span'));
        labels.append(el);
        labelEls.set(l.key, el);
      }
      const sig = `${l.title}|${l.sub || ''}|${l.kind}|${l.small ? 1 : 0}`;
      if (el.dataset.sig !== sig) {
        el.dataset.sig = sig;
        el.className = `label k-${l.kind || 'quiet'}${l.small ? ' small' : ''}`;
        el.children[0].textContent = l.title;
        el.children[1].textContent = l.sub || '';
        el.children[1].hidden = !l.sub;
        el.hidden = false;
        el.dataset.w = el.offsetWidth;
        el.dataset.h = el.offsetHeight;
      }
      seen.add(l.key);
      if (l.room) roomWorld(l.room, v, ...l.local);
      else v.set(...l.at);
      v.project(camera);
      const lw = Number(el.dataset.w);
      const lh = Number(el.dataset.h);
      let x = (v.x * 0.5 + 0.5) * width;
      let y = (-v.y * 0.5 + 0.5) * height;
      const offscreen = v.z > 1 || Math.abs(v.x) > 1.08 || Math.abs(v.y) > 1.08;
      x -= l.align === 'right' ? lw + 8 : lw / 2;
      y -= lh / 2;
      x = clamp(x, 8, Math.max(8, width - lw - 8));
      y = clamp(y, topInset + 2, Math.max(topInset + 2, height - bottomInset - lh - 2));
      const box2 = { x0: x - 3, y0: y - 3, x1: x + lw + 3, y1: y + lh + 3 };
      const clash = placed.some((p) => box2.x0 < p.x1 && box2.x1 > p.x0 && box2.y0 < p.y1 && box2.y1 > p.y0);
      if (offscreen || clash) { el.hidden = true; continue; }
      placed.push(box2);
      el.hidden = false;
      el.style.transform = `translate(${Math.round(x)}px, ${Math.round(y)}px)`;
    }
    for (const [key, el] of labelEls) if (!seen.has(key)) el.hidden = true;
  }

  /* ---------- the frame loop: draws only when something changed ---------- */

  const target = new THREE.WebGLRenderTarget(4, 4, { type: THREE.HalfFloatType, samples: 4 });
  const composer = new EffectComposer(renderer, target);
  composer.addPass(new RenderPass(scene, camera));
  const bloom = new UnrealBloomPass(new THREE.Vector2(4, 4), 0.36, 0.5, 1);
  composer.addPass(bloom);
  composer.addPass(new OutputPass());

  let raf = 0;
  let timer = 0;
  let awake = 0;
  let last = performance.now();
  let contextLost = false;
  let disposed = false;
  let checkDrawn = 3; // frames left to prove a picture really appears after a start or a comeback
  const stats = { frames: 0, loops: 0, shadowPasses: 0, why: '' };

  function schedule() {
    if (raf || document.hidden || contextLost || disposed) return;
    raf = requestAnimationFrame(frame);
  }
  function wake(frames = 2) {
    awake = Math.max(awake, frames);
    if (timer) { clearTimeout(timer); timer = 0; }
    schedule();
  }

  function updateMotion(dt) {
    let moving = false;
    const k = reduced.matches ? 1 : 1 - Math.exp(-dt * 3.4);
    for (const s of storeys) {
      if (s.t !== s.goalT || s.part !== s.goalPart) {
        s.t += (s.goalT - s.t) * k;
        s.part += (s.goalPart - s.part) * k;
        if (Math.abs(s.goalT - s.t) < 0.002) s.t = s.goalT;
        if (Math.abs(s.goalPart - s.part) < 0.002) s.part = s.goalPart;
        placeStorey(s);
        moving = true;
      }
    }
    if (signPart.value !== signPart.goal) {
      signPart.value += (signPart.goal - signPart.value) * k;
      if (Math.abs(signPart.goal - signPart.value) < 0.002) signPart.value = signPart.goal;
      signGroup.position.y = signPart.value * PART;
      signGroup.visible = signPart.value < 0.92;
      groundGroup.position.y = -signPart.value * PART;
      groundGroup.visible = signPart.value < 0.92;
      moving = true;
    }
    return moving;
  }

  function updateLamps(dt, now) {
    let moving = false;
    const k = reduced.matches ? 1 : 1 - Math.exp(-dt * 4.5);
    const s = focusStorey();
    const pulseOn = !reduced.matches && now - lastActive < PULSE_MS;
    for (const room of rooms.values()) {
      if (!room.storey.group.visible) continue;
      const dl = room.goal - room.level;
      if (Math.abs(dl) > 0.002) { room.level += dl * k; moving = true; } else room.level = room.goal;
      const dc = Math.abs(room.color.r - room.goalColor.r) + Math.abs(room.color.g - room.goalColor.g) + Math.abs(room.color.b - room.goalColor.b);
      if (dc > 0.004) { room.color.lerp(room.goalColor, k); moving = true; } else room.color.copy(room.goalColor);
      const pulse = pulseOn && room.mood === 'needs' && room.gain > 0.5 ? 1 + 0.08 * Math.sin(now / 900) : 1;
      // Only the first four rooms on a floor get a real lamp, so a fifth keeps all of its own light.
      const spotMix = room.storey === s && room.i < spots.length ? smooth(room.storey.t, 0.75, 1) : 0;
      const lamp = room.level * pulse * T.lampK;
      room.scope.uniforms.uLampCol.value.copy(room.color).multiplyScalar(lamp * (1 - 0.72 * spotMix));
      // A desk lamp stays on whatever the room's mood: someone is always at the desk.
      const desk = room.spec.lamps.deskTop != null ? 0.42 * T.lampK * Math.min(1, room.gain) : 0;
      room.scope.uniforms.uLamp2Col.value.copy(room.color).multiplyScalar(Math.max(lamp * 0.34, desk));
      roomWorld(room, room.scope.uniforms.uLampPos.value, room.lamp.x, room.lamp.y, room.lamp.z);
      roomWorld(room, room.scope.uniforms.uLamp2Pos.value, room.lamp2.x, room.lamp2.y, room.lamp2.z);
      const glow = 3.2 * Math.pow(room.level * pulse, 1.25);
      room.glow.emissive.copy(room.color);
      room.glow.emissiveIntensity = glow;
      room.glow.color.set('#8d8f96').lerp(room.color, Math.min(1, room.level * 1.5));
      room.glow2.emissive.copy(room.color);
      room.glow2.emissiveIntensity = Math.max(glow * 0.75, desk ? 0.8 * Math.min(1, room.gain) : 0);
    }
    for (let i = 0; i < spots.length; i++) {
      const room = s?.rooms[i];
      const spot = spots[i];
      if (!room) { spot.intensity = 0; continue; }
      const mix = smooth(s.t, 0.75, 1);
      roomWorld(room, spot.position, room.lamp.x, room.lamp.y - 0.06, room.lamp.z);
      roomWorld(room, spot.target.position, room.lamp.x, 0, room.lamp.z);
      spot.target.updateMatrixWorld();
      spot.color.copy(room.color);
      spot.intensity = room.level * T.spotK * mix;
    }
    return moving;
  }

  function updateBackground(dt) {
    const k = reduced.matches ? 1 : 1 - Math.exp(-dt * 3.5);
    const gap = Math.abs(bg.top.r - bg.goalTop.r) + Math.abs(bg.top.g - bg.goalTop.g) + Math.abs(bg.top.b - bg.goalTop.b)
      + Math.abs(bg.bottom.r - bg.goalBottom.r) + Math.abs(bg.bottom.g - bg.goalBottom.g) + Math.abs(bg.bottom.b - bg.goalBottom.b);
    if (gap < 0.004) return false;
    bg.top.lerp(bg.goalTop, k);
    bg.bottom.lerp(bg.goalBottom, k);
    paintBackground();
    return true;
  }

  function ambient(now, dt) {
    if (reduced.matches) return false;
    let any = false;
    const basement = storeys.find((s) => s.role === 'basement');
    if (basement?.group.visible) {
      for (const room of basement.rooms) {
        if (room.live?.busy && room.gain > 0.5) { room.live.tick(dt); any = true; }
      }
    }
    // Poe breathes and looks around a little, only for a few seconds after a touch or a visit.
    if (personRoom?.storey.group.visible && personRoom.gain > 0.5 && now - Math.max(lastActive, personWake) < PULSE_MS * 2) {
      personRoom.person.tick(now / 1000);
      any = true;
    }
    if (now - lastActive < PULSE_MS) {
      for (const room of rooms.values()) {
        if (room.mood === 'needs' && room.gain > 0.5 && room.storey.group.visible) { any = true; break; }
      }
    }
    return any;
  }

  // Right after a start or a comeback, look at one real pixel: the background is never pure black.
  function confirmDrawn() {
    const gl = renderer.getContext();
    const px = new Uint8Array(4);
    gl.readPixels(gl.drawingBufferWidth >> 1, gl.drawingBufferHeight - 2, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);
    if (px[0] + px[1] + px[2] > 0) {
      checkDrawn = 0;
      labels.hidden = false;
      onStatus?.('drawn');
    } else {
      checkDrawn -= 1;
      if (checkDrawn === 0) onStatus?.('blank');
      else awake = Math.max(awake, 2);
    }
  }

  function frame(now) {
    raf = 0;
    stats.loops += 1;
    if (document.hidden || contextLost || disposed) return;
    try {
      step(now);
    } catch (error) {
      console.error(error);
      onStatus?.('blank');
    }
  }

  function step(now) {
    const dt = Math.min(0.12, Math.max(0.001, (now - last) / 1000));
    last = now;
    const walking = walker ? walker.update(dt, now) : false;
    const camMoving = walker ? false : updateRig(dt);
    const moving = updateMotion(dt);
    const lit = updateLamps(dt, now);
    const painted = updateBackground(dt);
    const anim = ambient(now, dt);
    const active = camMoving || moving || lit || painted || walking;
    if (moving) { moonOnly = true; settling = true; } else if (settling) { settling = false; shadowsDirty = true; awake = Math.max(awake, 2); }
    if (shadowsDirty) {
      renderer.shadowMap.needsUpdate = true;
      moon.shadow.needsUpdate = true;
      for (const spot of spots) spot.shadow.needsUpdate = true;
      shadowsDirty = false;
      moonOnly = false;
      stats.shadowPasses += 1;
    } else if (moonOnly) {
      renderer.shadowMap.needsUpdate = true;
      moon.shadow.needsUpdate = true;
      moonOnly = false;
      stats.shadowPasses += 1;
    }
    if (active || awake > 0 || anim) {
      const r = focusRoom();
      if (selected && r) {
        roomWorld(r, ring.position, selected.x, 0.03, selected.z);
        ring.scale.setScalar(clamp(Math.max(selected.w, selected.d) * 1.05, 0.35, 2));
        ring.visible = true;
      } else ring.visible = false;
      const began = performance.now();
      composer.render(dt);
      stats.renderMs = Math.round(performance.now() - began);
      stats.frames += 1;
      stats.why = camMoving ? 'camera' : walking ? 'walking' : moving ? 'floors' : lit ? 'lamps' : painted ? 'background' : anim ? 'ambient' : 'finishing';
      awake = Math.max(0, awake - 1);
      if (checkDrawn > 0 && resized) confirmDrawn();
      if (disposed) return;
      drawLabels();
    }
    if (active || awake > 0) schedule();
    else if (anim) {
      const idle = now - lastActive > PULSE_MS;
      timer = setTimeout(() => { timer = 0; schedule(); }, idle ? 170 : 40);
    }
  }

  function resize() {
    const box2 = canvas.getBoundingClientRect();
    if (!box2.width || !box2.height) return;
    width = box2.width;
    height = box2.height;
    const pr = Math.min(window.devicePixelRatio || 1, MAX_PIXEL_RATIO);
    renderer.setPixelRatio(pr);
    renderer.setSize(width, height, false);
    composer.setPixelRatio(pr);
    composer.setSize(width, height);
    camera.aspect = width / height;
    if (walker) { camera.clearViewOffset(); camera.fov = walkFov(); } else camera.setViewOffset(width, height, 0, -(topInset - bottomInset) / 2, width, height);
    camera.updateProjectionMatrix();
    aim();
    if (!resized) {
      rig.az = rig.goal.az;
      rig.el = rig.goal.el;
      rig.dist = rig.goal.dist;
      rig.target.copy(rig.goal.target);
      resized = true;
    }
    wake(3);
  }

  const listeners = new AbortController();
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      if (raf) { cancelAnimationFrame(raf); raf = 0; }
      if (timer) { clearTimeout(timer); timer = 0; }
    } else {
      last = performance.now();
      wake(3);
    }
  }, { signal: listeners.signal });

  // The browser can take the graphics away at any time (driver reset, sleep, too many open).
  canvas.addEventListener('webglcontextlost', (event) => {
    event.preventDefault(); // without this the browser never offers them back
    contextLost = true;
    if (raf) { cancelAnimationFrame(raf); raf = 0; }
    if (timer) { clearTimeout(timer); timer = 0; }
    labels.hidden = true;
    onStatus?.('lost');
  });
  canvas.addEventListener('webglcontextrestored', () => {
    contextLost = false;
    checkDrawn = 3;
    shadowsDirty = true;
    wake(3);
  });
  // Hand the graphics back as the page goes, rather than waiting for the browser to collect them.
  window.addEventListener('pagehide', (event) => {
    if (!event.persisted) renderer.forceContextLoss();
  }, { signal: listeners.signal });

  const observer = new ResizeObserver(resize);

  // Lets go of everything, for a fresh start. A canvas that has lost its graphics can't get new
  // ones, so whoever starts the model again must give it a new canvas.
  function dispose() {
    if (disposed) return;
    disposed = true;
    walker?.dispose();
    walker = null;
    listeners.abort();
    observer.disconnect();
    if (raf) cancelAnimationFrame(raf);
    if (timer) clearTimeout(timer);
    scene.traverse((o) => {
      o.geometry?.dispose();
      o.shadow?.dispose?.();
      for (const m of [o.material].flat()) {
        if (!m) continue;
        for (const value of Object.values(m)) if (value?.isTexture) value.dispose();
        m.dispose();
      }
    });
    bgTexture.dispose();
    composer.dispose();
    bloom.dispose();
    const wasLost = renderer.getContext().isContextLost();
    renderer.dispose();
    if (!wasLost) renderer.forceContextLoss();
    labels.replaceChildren();
  }

  // Where a room is on screen now, and how wide it looks in pixels. For tests.
  function where(floorId, roomId) {
    const r = rooms.get(`${floorId}/${roomId}`);
    if (!r) return null;
    const box2 = canvas.getBoundingClientRect();
    const spot = (x, z) => {
      roomWorld(r, v, x, 0.3, z).project(camera);
      return [(v.x * 0.5 + 0.5) * width + box2.left, (-v.y * 0.5 + 0.5) * height + box2.top];
    };
    const [x, y] = spot(W / 2, D / 2);
    const [x0, y0] = spot(0, D / 2);
    const [x1, y1] = spot(W, D / 2);
    return { x: Math.round(x), y: Math.round(y), wide: Math.round(Math.hypot(x1 - x0, y1 - y0)) };
  }

  /* ---------- walking through it in first person (walk.js, loaded the first time) ---------- */

  const walkFov = () => (camera.aspect < 0.9 ? 72 : 60);

  async function walk(on = true) {
    if (!on) { endWalk(); return false; }
    if (walker || disposed) return !!walker;
    walkStart ??= import('./walk.js');
    const { createWalk } = await walkStart;
    if (walker || disposed || contextLost) return !!walker;
    selected = null;
    onHover?.(null);
    highlight(null);
    // Every floor back in the building, rooms in a row, while one at a time is walked.
    for (const s of storeys) { s.t = s.goalT = 0; s.part = s.goalPart = 0; placeStorey(s); }
    signGroup.visible = false;
    groundGroup.visible = false;
    camera.near = 0.05;
    camera.far = 90;
    camera.clearViewOffset();
    camera.fov = walkFov();
    camera.updateProjectionMatrix();
    try {
      walker = createWalk({
        scene, camera, canvas, renderer, storeys, org, reduced, personRoom, start: view.floor,
        onPick, describe, infoText, roomWorld, wake, touched, version: () => version,
        poeAwake() { personWake = performance.now(); },
        shadows(near, reach) { aimLights(near, reach); shadowsDirty = true; wake(2); },
        leave() { endWalk(); onWalk?.(false); },
      });
    } catch (error) {
      console.error(error);
      walker = null;
      restoreView();
      return false;
    }
    wake(3);
    return true;
  }

  function restoreView() {
    camera.near = 0.5;
    camera.far = 260;
    camera.fov = 24;
    for (const s of storeys) placeStorey(s);
    signGroup.visible = signPart.value < 0.92;
    groundGroup.visible = signPart.value < 0.92;
    resize();
    const was = view;
    view = {};
    focus(was);
    shadowsDirty = true;
    wake(3);
  }

  function endWalk() {
    if (!walker) return;
    const ending = walker;
    walker = null;
    ending.dispose();
    restoreView();
  }

  /* ---------- start ---------- */

  labels.hidden = false;
  try {
    buildGround();
    defs.forEach((def, i) => buildStorey(def, i));
    buildSign();
    for (const room of rooms.values()) fillRoom(room);
    rebuildTargets();
    aimLights();
    paintBackground();
    setTheme(true);
    resize();
    observer.observe(canvas);
  } catch (error) {
    dispose(); // a start that fails halfway gives its graphics back
    throw error;
  }

  return {
    setLive, setScene, setTheme, focus, highlight, zoomBy, turn, resetView, wake, where, dispose,
    walk, walking: () => !!walker, walkInfo: () => walker?.info() || null,
    // One picture of the model as it stands now, without waiting for a frame.
    // It does a whole frame's work: a model that has never drawn (a hidden page) has no shadow maps
    // or lamp values yet, and WebGL refuses to draw lit materials without them, leaving only the decals.
    snapshot() {
      renderer.info.autoReset = false; // the composer draws several passes; count them all
      renderer.info.reset();
      awake = Math.max(awake, 1);
      step(performance.now());
      renderer.info.autoReset = true;
      stats.snapshotCalls = renderer.info.render.calls;
      stats.snapshotTriangles = renderer.info.render.triangles;
      stats.snapshotGlError = renderer.getContext().getError();
      return canvas.toDataURL('image/jpeg', 0.9);
    },
    // What the model holds right now, for the Mac app's test mode. Changes nothing.
    inspect() {
      let visibleMeshes = 0;
      scene.traverseVisible((o) => { if (o.isMesh) visibleMeshes += 1; });
      return {
        ...stats, sceneChildren: scene.children.length, visibleMeshes, lastPassCalls: renderer.info.render.calls, lastPassTriangles: renderer.info.render.triangles,
        programs: renderer.info.programs?.length, camera: camera.position.toArray().map((n) => Math.round(n * 10) / 10),
      };
    },
    stats: () => ({ ...stats, calls: renderer.info.render.calls, triangles: renderer.info.render.triangles, geometries: renderer.info.memory.geometries, textures: renderer.info.memory.textures }),
  };
}
