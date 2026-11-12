// Arnheim's building in its photo-real look: the same company, the same live data and the same calls
// as building.js (createBuilding), drawn from floors baked by Cycles (studio/blender, see baked.js).
// Each project floor is the same baked floor, stacked; the lobby has its own. The building stands cut
// open at the front like a dollhouse; a floor slides out with its ceiling lifted off to show its plan.
// What comes from the data (desks, seats, books, screens, people) is placed live in each room.
import * as THREE from '../vendor/three/three.module.js';
import { FILL, loadKit, loadPeople, loadShell } from './three/baked.js';
import { realPerson as madeFrom } from './three/looks.js';
import { buildPerson, buildSeated, receptionistSpec } from './three/poe.js';

const rad = THREE.MathUtils.degToRad;
const clamp = THREE.MathUtils.clamp;
const lerp = THREE.MathUtils.lerp;
const smooth = THREE.MathUtils.smoothstep;

const PART = 40; // how far the other floors move away while one is out
const GLIDE = 3; // how far a floor slides out towards you
const FRONT = -0.33; // the front wall is cut away just inside its inner face
const CUT = 2.1; // and a floor that is out loses everything above this height: ceiling, lamps, the tops of walls
const CUT_LOBBY = 3.05; // the lobby keeps its taller wall, with the company's name and mission at the top
const MAX_PIXEL_RATIO = 1.5;
const PULSE_MS = 4000;
const LABEL_ROOM = 1.6;

const VIEWS = {
  building: { az: 5, el: 19, azSpan: [-30, 58], elSpan: [6, 50] },
  floor: { az: 18, el: 52, azSpan: [-40, 62], elSpan: [26, 80] },
  room: { az: 16, el: 46, azSpan: [-50, 62], elSpan: [20, 80] },
  person: { az: 10, el: 14, azSpan: [-40, 62], elSpan: [4, 60] },
};

// Which baked room a room of the company map is drawn in.
const SHELL_ROOM = {
  goals: 'GOALS', work: 'WORK', conversations: 'CONVERSATIONS', code: 'CODE', company: 'COMPANY',
  websites: 'RECEPTION', email: 'EMAIL', social: 'SOCIAL MEDIA', domains: 'DOMAINS',
};
const MACHINE_ROOMS = ['WEST MACHINE ROOM', 'MIDDLE MACHINE ROOM', 'EAST MACHINE ROOM', 'LIBRARY'];
// The lift (studio/blender/lift.py), the same on every floor, in a floor's own coordinates: the car you walk
// into, the doorway its two steel leaves close, and how far each leaf slides open. Each leaf is a baked group
// of its own, so the walk can slide it.
const LIFT_DOORS = ['LIFT DOOR WEST', 'LIFT DOOR EAST'];
const CAR = { x0: 7.2, x1: 8.8, z0: -12.45, z1: -10.95 };
const DOORWAY = { x0: 7.5, x1: 8.5, z0: -10.95, z1: -10.5 };
const SLIDE = 0.5;
const PASSAGES = new Set(['CORRIDOR', 'LIFT AND STAIRS', ...LIFT_DOORS]);
const SITE_LEVEL = 0.8;
const BASEMENT_DROP = 3.6; // studio/design-basement.json: floor to floor under the lobby
const ROOF_SLAB = 0.35; // studio/blender/street.py: the baked roof's slab under its top

const KIND_ORDER = { goals: 0, code: 1, conversations: 2, work: 3 };

// A room's light, as a colour over its bake.
const MOOD = {
  quiet: { color: '#ffffff', level: 1 },
  working: { color: '#ffeedd', level: 1.04 },
  needs: { color: '#ffd29e', level: 1.08 },
  check: { color: '#e2ebff', level: 1.02 },
  failed: { color: '#ffc9cf', level: 1.0 },
};

const THEMES = {
  dark: {
    level: 0.84, hemi: 0.9, sun: 1.7, exposure: 0.82,
    bg: { all: ['#57392a', '#0a0e1a'], needs: ['#663a14', '#0b0d16'], working: ['#5e4522', '#0b0e18'] },
  },
  light: {
    level: 1, hemi: 1.1, sun: 2.2, exposure: 0.9,
    bg: { all: ['#f7ead8', '#dfe5ee'], needs: ['#fbdcb6', '#e8e3dc'], working: ['#fae9c4', '#e6e5df'] },
  },
};

// people: where a company's own receptionist and assistant were exported to (people_export.py --company), if
// anywhere; the baked set's agents serve every company.
export function createPhotoBuilding(canvas, org, { base, people: ownPeople, onPick, onHover, onStatus, onWalk, onNotes, labels, insets = [64, 44], talk = null } = {}) {
  const root = base || new URL('../baked/', import.meta.url).href;
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, powerPreference: 'default' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, MAX_PIXEL_RATIO));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  // The cut: everything in front of the front wall's inside, and above a floor that is out.
  const front = new THREE.Plane(new THREE.Vector3(0, 0, -1), 1e4);
  const top = new THREE.Plane(new THREE.Vector3(0, -1, 0), 1e4);
  renderer.clippingPlanes = [front, top];

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(24, 1, 0.3, 500);
  const raycaster = new THREE.Raycaster();
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const hitMaterial = new THREE.MeshBasicMaterial();

  const defs = [...org.floors, org.lobby, org.basement].filter(Boolean);
  let themeName = 'dark';
  let T = THEMES.dark;
  let live = {};
  let liveSig = '';
  let view = {};
  let scenePick = { mode: 'all' };
  let ready = false;
  let failed = null;
  let resized = false;
  let selected = null;
  let notes = [];
  let version = 0;
  let personRoom = null;
  let personWake = -Infinity;
  let kit = null;
  let people = null; // the photo-real people, when they have been exported (baked/people/)
  let own = null; // the company's own receptionist and assistant, when it has exported them (options.people)
  let walker = null; // a first-person walk, while one is going (walk.js)
  let walkStart = null;
  const shells = {};
  const siteMeshes = []; // the baked outside's meshes, once the building is built
  let buildingIndex = null; // building.json: which baked floor serves which part of the building
  let officeTick = null; // the assistant's breathing, in the founder's office while you walk there
  const storeys = [];
  const rooms = new Map();
  let signHit = null;
  let outer = null; // the roof, the sign and the ground: everything that isn't a floor
  const box3 = { x0: 0, x1: 24, z0: -16, z1: 0 }; // the baked floors' footprint, set once they load
  let OX = -12;
  let OZ = 8;

  /* ---------- light and background ---------- */

  const hemi = new THREE.HemisphereLight(0xf3efe8, 0xb9ad9c, 1);
  const sun = new THREE.DirectionalLight(0xfff1de, 2);
  scene.add(hemi, sun, sun.target);

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

  /* ---------- the model ---------- */

  const kindOf = (role) => (r) => r.kind || (role === 'basement' ? (r.id === 'library' ? 'library' : 'machine') : r.id);

  function shellHeight(shell) {
    let h = 0;
    for (const m of shell.group.children) {
      m.geometry.computeBoundingBox();
      h = Math.max(h, m.geometry.boundingBox.max.y);
    }
    return h;
  }

  function boundsOf(outline) {
    const xs = outline.map((p) => p[0]);
    const zs = outline.map((p) => p[1]);
    return { x0: Math.min(...xs), x1: Math.max(...xs), z0: Math.min(...zs), z1: Math.max(...zs) };
  }

  function makeRoom(storey, def, kind, outline, meshes, slots) {
    const b = boundsOf(outline);
    const room = {
      key: `${storey.id}/${def.id}`, floorId: storey.id, roomId: def.id, label: def.label, kind, storey, outline, box: b,
      centre: [(b.x0 + b.x1) / 2, (b.z0 + b.z1) / 2], meshes, slots, content: null, objects: [], moreChips: [], info: {}, sig: null,
      mood: 'quiet', hot: false, gain: 1, level: 1, goal: 1, color: new THREE.Color('#ffffff'), goalColor: new THREE.Color('#ffffff'), liveMats: [],
    };
    const hit = new THREE.Mesh(new THREE.BoxGeometry(b.x1 - b.x0, storey.height, b.z1 - b.z0), hitMaterial);
    hit.position.set(room.centre[0], storey.height / 2, room.centre[1]);
    hit.visible = false;
    hit.userData = { hit: true, floorId: storey.id, roomId: def.id };
    storey.group.add(hit);
    room.hit = hit;
    storey.rooms.push(room);
    rooms.set(room.key, room);
    return room;
  }

  function buildStorey(def, order) {
    const role = def.id === org.basement?.id ? 'basement' : def.id === org.lobby?.id ? 'lobby' : 'floor';
    const shell = shells[role] || null;
    const group = new THREE.Group();
    scene.add(group);
    const storey = {
      id: def.id, label: def.label, role, def, order, group, shell, rooms: [], meshes: [], caps: null,
      height: shell ? shell.height : 3.2, y: 0, t: 0, goalT: 0, part: 0, goalPart: 0,
    };
    const kinds = kindOf(role);
    const list = [...(def.rooms || org.rooms), ...(def.extraRooms || [])];
    const ordered = list.map((r, i) => [r.order ?? KIND_ORDER[kinds(r)] ?? 10 + i, r]).sort((a, b) => a[0] - b[0]).map(([, r]) => r);
    if (shell) {
      // this floor's own copy of the bake: the same shapes and pictures, its own colours (moods, dimming)
      const byName = new Map();
      for (const m of shell.group.children) {
        const copy = new THREE.Mesh(m.geometry, m.material.clone());
        copy.name = m.name;
        if (m.material.transparent) copy.userData.solid = true; // the windows: you can't walk through them
        copy.matrixAutoUpdate = false;
        copy.updateMatrix();
        group.add(copy);
        storey.meshes.push(copy);
        byName.set(m.name, copy);
      }
      const used = new Set();
      // the basement's machines take its machine rooms in turn, west to east
      const machineRoom = () => MACHINE_ROOMS.find((n) => n !== 'LIBRARY' && !used.has(n) && shell.rooms.has(n));
      for (const r of ordered) {
        const name = role === 'basement' ? (kinds(r) === 'library' ? 'LIBRARY' : machineRoom()) : SHELL_ROOM[kinds(r)];
        const baked = name && shell.rooms.get(name);
        if (!baked?.outline) { console.warn(`Arnheim: the photo-real ${role} has no room for "${r.label}" yet.`); continue; }
        used.add(name);
        makeRoom(storey, r, kinds(r), baked.outline, baked.meshes.map((m) => byName.get(m.name)).filter(Boolean), shell.slots.filter((s) => s.room === name));
      }
      // a baked room this floor has no use for stands empty and a little dim
      for (const [name, r] of shell.rooms) {
        if (used.has(name) || PASSAGES.has(name)) continue;
        for (const m of r.meshes) byName.get(m.name)?.material.color.setScalar(0.62);
      }
      // the company's quote, in a script hand on the corridor's long wall, where the bake left room for it
      const q = org.quote?.text && shell.slots.find((x) => x.kind === 'quote');
      if (q) {
        const sign = quoteSign(String(org.quote.text), String(org.quote.by || ''), q.w, q.h);
        sign.position.set(q.at[0] + Math.sin(q.rot) * 0.004, q.at[1], q.at[2] + Math.cos(q.rot) * 0.004);
        sign.rotation.y = q.rot;
        sign.name = 'quote';
        group.add(sign);
      }
    } else {
      // A floor not baked yet (the basement): a plain concrete floor, a room each in a row.
      const concrete = new THREE.MeshStandardMaterial({ color: '#8a8780', roughness: 0.95 });
      const wallMat = new THREE.MeshStandardMaterial({ color: '#b9b4aa', roughness: 0.95 });
      const w = box3.x1 - box3.x0;
      const slab = new THREE.Mesh(new THREE.BoxGeometry(w, 0.2, box3.z1 - box3.z0), concrete);
      slab.position.set((box3.x0 + box3.x1) / 2, -0.1, (box3.z0 + box3.z1) / 2);
      const back = new THREE.Mesh(new THREE.BoxGeometry(w, storey.height, 0.2), wallMat);
      back.position.set((box3.x0 + box3.x1) / 2, storey.height / 2, box3.z0 + 0.1);
      group.add(slab, back);
      const n = Math.max(1, ordered.length);
      ordered.forEach((r, i) => {
        const x0 = box3.x0 + (w * i) / n;
        const x1 = box3.x0 + (w * (i + 1)) / n;
        if (i) {
          const wall = new THREE.Mesh(new THREE.BoxGeometry(0.15, storey.height, box3.z1 - box3.z0), wallMat);
          wall.position.set(x0, storey.height / 2, (box3.z0 + box3.z1) / 2);
          group.add(wall);
        }
        makeRoom(storey, r, kinds(r), [[x0 + 0.1, box3.z0 + 0.2], [x1 - 0.1, box3.z0 + 0.2], [x1 - 0.1, box3.z1 - 0.3], [x0 + 0.1, box3.z1 - 0.3]], [], []);
      });
    }
    storeys.push(storey);
    return storey;
  }

  // Stack the floors: the basement under the ground, the lobby on it, the project floors above in the
  // map's order (its first floor at the top).
  function stack() {
    const lobby = storeys.find((s) => s.role === 'lobby');
    const basement = storeys.find((s) => s.role === 'basement');
    let y = lobby ? lobby.height : 0;
    if (lobby) lobby.y = 0;
    // a baked basement stands a storey down (3.6 m), its light wells meeting the baked street; a drawn one under the ground
    if (basement) basement.y = basement.shell ? -BASEMENT_DROP : -basement.height - 0.35;
    for (const s of storeys.filter((x) => x.role === 'floor').reverse()) { s.y = y; y += s.height; }
    return y;
  }

  function buildOuter(roofY) {
    outer = new THREE.Group();
    const cx = (box3.x0 + box3.x1) / 2;
    const cz = (box3.z0 + box3.z1) / 2;
    const w = box3.x1 - box3.x0 + 0.5;
    const d = box3.z1 - box3.z0 + 0.5;
    const roof = new THREE.MeshStandardMaterial({ color: '#4a4540', roughness: 0.9 });
    const trim = new THREE.MeshStandardMaterial({ color: '#d9d3c7', roughness: 0.8 });
    const paving = new THREE.MeshStandardMaterial({ color: '#a39b8f', roughness: 0.95 });
    const earth = new THREE.MeshStandardMaterial({ color: '#4a3b2c', roughness: 1 });
    if (shells.site) {
      // the baked outside: the streets, pavements, light wells and trees round the ground floor, the roof on top
      for (const m of shells.site.group.children) {
        const mesh = new THREE.Mesh(m.geometry, m.material);
        mesh.name = `outside ${m.name}`;
        mesh.position.y = m.name === 'ROOF' ? roofY + ROOF_SLAB : 0; // the outer group already stands where the building does
        outer.add(mesh);
        siteMeshes.push(mesh);
      }
      tintSite();
      // the earth the basement is dug into, round it and its light wells, so the cut-away shows soil
      const b = storeys.find((x) => x.role === 'basement');
      if (b) {
        const soil = new THREE.MeshStandardMaterial({ color: '#4a3b2c', roughness: 1, side: THREE.DoubleSide });
        const top = -0.45;
        const bottom = b.y - 0.6;
        const h = top - bottom;
        const add = (x0, x1, z0, z1) => {
          const block = new THREE.Mesh(new THREE.BoxGeometry(x1 - x0, h, z1 - z0), soil);
          block.position.set((x0 + x1) / 2, bottom + h / 2, (z0 + z1) / 2);
          outer.add(block);
        };
        add(-9, -2.7, -24, 6.4);       // west of the west light well, out to the street
        add(24, 31, -24, 6.4);         // east of the building
        add(-2.7, 24, -24, -16);       // north of it
        add(10.09, 24, -16, -10.72);   // under the notch in its north side
      }
    } else {
      const slab = new THREE.Mesh(new THREE.BoxGeometry(w, 0.3, d), roof);
      slab.position.set(cx, roofY + 0.15, cz);
      const parapet = new THREE.Mesh(new THREE.BoxGeometry(w, 0.4, 0.14), trim);
      parapet.position.set(cx, roofY + 0.5, box3.z1 + 0.18);
      const ground = new THREE.Mesh(new THREE.BoxGeometry(w + 6, 0.35, d + 3), paving);
      ground.position.set(cx, -0.175, cz + 1);
      outer.add(slab, parapet, ground);
    }
    if (!shells.site && storeys.some((s) => s.role === 'basement')) {
      const b = storeys.find((s) => s.role === 'basement');
      const block = new THREE.Mesh(new THREE.BoxGeometry(w + 6, b.height + 0.4, 0.6), earth);
      block.position.set(cx, b.y + b.height / 2 - 0.2, box3.z0 - 0.5);
      outer.add(block);
    }
    // the company's name and mission on a sign on the roof, as the drawn building has it
    const c = document.createElement('canvas');
    c.width = 2048;
    c.height = 512;
    const g = c.getContext('2d');
    g.fillStyle = '#10131b';
    g.fillRect(0, 0, 2048, 512);
    g.textAlign = 'center';
    g.textBaseline = 'middle';
    g.fillStyle = '#ffe3bd';
    g.font = '800 228px -apple-system, "Helvetica Neue", Arial, sans-serif';
    g.fillText(org.company, 1024, 200);
    g.fillStyle = '#f4d7b0';
    g.font = '600 92px -apple-system, "Helvetica Neue", Arial, sans-serif';
    g.fillText(`Mission: ${org.mission || 'Not written yet'}`, 1024, 400);
    const tex = new THREE.CanvasTexture(c);
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.anisotropy = 8;
    const sw = 10.4;
    const sh = 2.6;
    const face = new THREE.Mesh(new THREE.PlaneGeometry(sw, sh), new THREE.MeshBasicMaterial({ map: tex, toneMapped: false }));
    const back = new THREE.Mesh(new THREE.BoxGeometry(sw + 0.24, sh + 0.24, 0.2), new THREE.MeshStandardMaterial({ color: '#2a2622', roughness: 0.7 }));
    back.position.z = -0.11;
    const sign = new THREE.Group();
    sign.add(face, back);
    for (const sx of [-1, 1]) {
      const leg = new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.9, 0.16), back.material);
      leg.position.set(sx * (sw / 2 - 1), -sh / 2 - 0.45, -0.11);
      sign.add(leg);
    }
    sign.position.set(cx, roofY + 0.3 + 0.9 + sh / 2, box3.z1 - 3);
    outer.add(sign);
    signHit = new THREE.Mesh(new THREE.BoxGeometry(sw, sh + 0.9, 0.5), hitMaterial);
    signHit.position.copy(sign.position);
    signHit.visible = false;
    signHit.userData = { hit: true, company: true };
    outer.add(signHit);
    outer.position.set(OX, 0, OZ);
    scene.add(outer);
    return sign.position.y + sh / 2;
  }

  // The cut faces of a floor that is out: its walls' insides drawn dark, so a cut wall reads as solid.
  function capsFor(s) {
    if (s.caps || !s.shell) return s.caps;
    const cap = new THREE.MeshBasicMaterial({ color: '#2b2622', side: THREE.BackSide, toneMapped: false });
    s.caps = new THREE.Group();
    for (const m of s.meshes) {
      const c = new THREE.Mesh(m.geometry, cap);
      c.matrixAutoUpdate = false;
      s.caps.add(c);
    }
    s.caps.visible = false;
    s.group.add(s.caps);
    return s.caps;
  }

  /* ---------- how a floor moves out of the building ---------- */

  function placeStorey(s) {
    s.group.position.set(OX, s.y + s.part * PART, OZ + GLIDE * smooth(s.t, 0, 0.6));
    s.group.visible = Math.abs(s.part) < 0.92;
    if (s.caps) s.caps.visible = s.t > 0.3;
  }

  function placeCuts() {
    const s = focusStorey();
    const glide = s ? GLIDE * smooth(s.t, 0, 0.6) : 0;
    front.constant = OZ + glide + FRONT;
    top.constant = s ? s.group.position.y + lerp(s.height + PART, cutOf(s), smooth(s.t, 0.1, 0.95)) : 1e4;
  }

  const cutOf = (s) => (s.role === 'lobby' ? CUT_LOBBY : CUT);

  function roomWorld(r, out, x = 0, y = 0, z = 0) {
    const p = r.storey.group.position;
    return out.set(p.x + x, p.y + y, p.z + z);
  }

  /* ---------- live data ---------- */

  function sceneGain(room) {
    let on = true;
    if (scenePick.mode === 'needs') on = room.mood === 'needs' || room.mood === 'check';
    else if (scenePick.mode === 'working') on = room.mood === 'working' || !!room.info.working;
    else if (scenePick.mode === 'floor') on = room.floorId === scenePick.floor;
    return on ? 1 : 0.3;
  }

  function chooseMood(room) {
    const m = MOOD[room.mood] || MOOD.quiet;
    room.goal = m.level * room.gain * (room.hot ? 1.1 : 1);
    room.goalColor.set(m.color);
  }

  // Someone at work: one of the photo-real agents, picked by the work's id, or the drawn person if there are none.
  const AGENT_LOOKS = 6;
  const seated = (n, opts) => {
    const p = people?.make(`agent-${n % AGENT_LOOKS}-${opts.pose === 'desk' ? 'desk' : 'chat'}`, { seed: n });
    return p ? p.group : buildSeated(n, opts);
  };

  function fillRoom(room) {
    if (room.content) {
      room.storey.group.remove(room.content);
      room.content.traverse((o) => { if (o.isMesh && !o.userData.keep) { o.geometry?.dispose?.(); for (const m of [o.material].flat()) { m?.map?.isCanvasTexture && m.map.dispose(); } } });
    }
    room.objects = [];
    room.moreChips = [];
    const content = new THREE.Group();
    const ctx = {
      seated,
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
    const fill = FILL[room.kind] || FILL.lounge;
    fill({ g: content, slots: room.slots, info: room.info, ctx, kit, box: room.box, company: { name: org.company, mission: org.mission } });
    if (room.kind === 'websites') placeReceptionist(room, content, ctx);
    room.storey.group.add(content);
    room.content = content;
    room.liveMats = [];
    content.traverse((o) => {
      if (!o.isMesh || !o.visible) return;
      for (const m of [o.material].flat()) {
        if (!m || m.userData.base || m.blending === THREE.AdditiveBlending) continue;
        m.userData.base = { color: m.color.clone(), emissive: m.emissiveIntensity ?? 0 };
        room.liveMats.push(m);
      }
    });
    tintRoom(room);
  }

  // The photo-real receptionist or assistant, from the company's own set or the baked one, but only one made from
  // the very look the company file gives them: anyone else is drawn from their look, never shown as someone else.
  const realPerson = (name, look) => madeFrom([own, people], name, look);

  // The receptionist, as the map names and dresses them, at the desk in the reception hall.
  function placeReceptionist(room, content, ctx) {
    const spec = receptionistSpec(org.receptionist || {});
    const s = room.slots.find((x) => x.kind === 'person') || { at: [12.25, 0, -5.72], rot: rad(-15) };
    // seated at the desk in the photo-real look when they have been exported, standing behind it as drawn otherwise
    const real = realPerson('receptionist', org.receptionist?.look);
    if (!room.person) room.person = real?.make('receptionist', { seed: 7 }) || buildPerson(spec);
    const g = room.person.group;
    g.position.set(s.at[0], 0, s.at[2]);
    g.rotation.y = s.rot;
    g.traverse((o) => { o.userData.keep = true; });
    content.add(g);
    if (real) {
      const chair = kit.make('desk chair');
      chair.position.set(s.at[0] + Math.sin(s.rot) * 0.045, 0, s.at[2] + Math.cos(s.rot) * 0.045);
      chair.rotation.y = s.rot;
      content.add(chair);
    }
    room.spec = { person: { ...spec, at: s.at } };
    personRoom = room;
    ctx.object({ x: s.at[0], y: 0.95, z: s.at[2], w: 0.7, h: 1.0, d: 0.5, title: spec.name, sub: `${spec.title || 'Receptionist'}. Tap to talk.`, href: spec.href, person: true });
  }

  // A room's light: its mood's colour over the bake, dimmed when the scene picks other rooms.
  function tintRoom(room) {
    const k = room.level * (walker ? 1 : T.level); // walking, the rooms are as photographed, whatever the theme
    for (const m of room.meshes) m.material.color.copy(room.color).multiplyScalar(k);
    const dim = room.gain < 0.5 ? 0.45 : 1;
    for (const m of room.liveMats) {
      m.color.copy(m.userData.base.color).multiplyScalar(dim);
      if (m.emissiveIntensity != null) m.emissiveIntensity = m.userData.base.emissive * dim;
    }
  }

  function applyLive() {
    let changed = false;
    for (const room of rooms.values()) {
      const info = live[room.key] || {};
      const sig = JSON.stringify(info);
      if (sig === room.sig) continue;
      room.sig = sig;
      room.info = info;
      room.mood = info.state || 'quiet';
      room.gain = sceneGain(room);
      chooseMood(room);
      fillRoom(room);
      changed = true;
    }
    if (changed) version += 1;
    rebuildTargets();
  }

  function setLive(model) {
    const whole = JSON.stringify(model);
    if (whole === liveSig) return;
    liveSig = whole;
    live = model;
    if (ready) applyLive();
    wake(3);
  }

  function setScene(next) {
    scenePick = next;
    for (const room of rooms.values()) {
      room.gain = sceneGain(room);
      chooseMood(room);
      tintRoom(room);
    }
    applyPalette();
    wake(3);
  }

  function setTheme(dark) {
    themeName = dark ? 'dark' : 'light';
    T = THEMES[themeName];
    renderer.toneMappingExposure = T.exposure;
    applyPalette();
    for (const room of rooms.values()) tintRoom(room);
    tintSite();
    wake(3);
  }

  // the baked outside dims with the theme, as the rooms do
  // the street in full sun was baked for the rooms' exposure, so it is taken down a little to sit with them
  function tintSite() {
    for (const m of siteMeshes) m.material.color.setScalar(T.level * SITE_LEVEL);
  }

  function applyPalette() {
    const dim = scenePick.mode === 'all' ? 1 : 0.8;
    hemi.intensity = T.hemi * dim;
    sun.intensity = T.sun * dim;
    const p = T.bg;
    const pair = p[scenePick.mode] || p.all;
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

  /* ---------- camera rig (as building.js) ---------- */

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
  let bottomY = -1;
  let signTop = 20;

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
  const viewName = () => (focusRoom() ? (view.close && focusRoom() === personRoom ? 'person' : 'room') : view.floor ? 'floor' : 'building');

  function aim() {
    const s = focusStorey();
    const r = focusRoom();
    const bounds = new THREE.Box3();
    let fill = 1;
    if (s) {
      const x = OX;
      const y = s.y;
      const z = OZ + GLIDE;
      if (r === personRoom && r && view.close) {
        const [px, , pz] = r.spec.person.at;
        bounds.min.set(x + px - 0.7, y + 0.95, z + pz - 0.3);
        bounds.max.set(x + px + 0.7, y + 1.9, z + pz + 0.45);
        fill = 0.92;
      } else if (r) {
        bounds.min.set(x + r.box.x0, y, z + r.box.z0);
        bounds.max.set(x + r.box.x1, y + 1.5, z + r.box.z1);
        fill = 0.9;
      } else {
        bounds.min.set(x + box3.x0, y, z + box3.z0);
        bounds.max.set(x + box3.x1, y + 1.2, z + box3.z1);
        fill = 0.97;
      }
    } else {
      bounds.min.set(OX + box3.x0 - LABEL_ROOM, bottomY, OZ + box3.z0);
      bounds.max.set(OX + box3.x1 + 0.4, signTop, OZ + box3.z1);
    }
    const { dist, center } = fitDistance(bounds, rig.goal.az, rig.goal.el, fill);
    rig.goal.dist = dist * rig.zoom;
    rig.goal.target.copy(center);
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
    if (!ready) return;
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
    if (s) capsFor(s);
    aim();
    selected = null;
    const r = focusRoom();
    if (r && next.item) selected = r.objects.find((o) => o.href === next.item) || null;
    rebuildTargets();
    wake(3);
  }

  function zoomBy(factor) {
    rig.zoom = clamp(rig.zoom * factor, 0.45, 1.3);
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
    // only what the cut leaves standing can be tapped
    const hits = raycaster.intersectObjects(targets, false).filter((h) => front.distanceToPoint(h.point) >= -0.01 && top.distanceToPoint(h.point) >= -0.01);
    if (!hits.length) return null;
    return (hits.find((h) => h.object.userData.href) || hits[0]).object.userData;
  }

  const infoText = (info) => info.sub ?? [info.big, info.detail].filter((x) => x != null && x !== '').join(' ');
  function describe(hit) {
    if (hit.company) return { title: org.company, sub: `Mission: ${org.mission || 'Not written yet'}` };
    const room = rooms.get(`${hit.floorId}/${hit.roomId}`);
    if (hit.title) return { title: hit.title, sub: hit.sub };
    if (!view.floor) {
      const lines = live[`floor:${hit.floorId}`]?.lines || [];
      return { title: room?.storey.label, sub: lines.map((l) => l.text).join(', ') };
    }
    return { title: room?.label, sub: infoText(room?.info || {}) };
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
    if (!ready) return;
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
    if (!wasTap || !ready) return;
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
    return s.length <= 36 ? s : `${s.slice(0, 36).replace(/\s+\S*$/, '')}...`;
  };
  const personLabel = (room) => ({
    key: 'person', title: room.spec.person.name, sub: room.spec.person.title || 'Receptionist', kind: 'quiet', align: 'center', room,
    local: [room.spec.person.at[0], 2.0, room.spec.person.at[2]], rank: 0,
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
          at: [OX + box3.x0 - 0.2, st.y + st.height * 0.5, OZ + box3.z1], rank: lines.some((l) => l.kind === 'needs') ? 0 : 1,
        });
      }
    } else if (!r && s.t > 0.85) {
      for (const room of s.rooms) {
        out.push({ key: `r:${room.key}`, title: room.label, sub: infoText(room.info), kind: room.mood, align: 'center', room, local: [room.centre[0], cutOf(s) + 0.3, room.centre[1]], rank: 0 });
        for (const m of room.moreChips) out.push({ key: `m:${room.key}:${m.x}`, title: `+${m.count} more`, kind: 'quiet', align: 'center', room, local: [m.x, m.y + 0.25, m.z], rank: 2 });
      }
      if (personRoom?.storey === s) out.push(personLabel(personRoom));
    } else if (r && s.t > 0.85) {
      out.push({ key: `r:${r.key}`, title: r.label, sub: infoText(r.info), kind: r.mood, align: 'center', room: r, local: [r.centre[0], cutOf(s) + 0.4, r.box.z0 + 0.3], rank: 0 });
      for (const m of r.moreChips) out.push({ key: `m:${r.key}:${m.x}`, title: `+${m.count} more`, kind: 'quiet', align: 'center', room: r, local: [m.x, m.y + 0.25, m.z], rank: 1 });
      if (r === personRoom) out.push(personLabel(r));
      for (const o of r.objects) {
        if (!o.title || o.person) continue;
        out.push({
          key: `o:${r.key}:${o.href || o.title}`, title: shortTitle(o.title), kind: o.mood || 'quiet', align: 'center', room: r,
          local: [o.x, o.y + o.h + 0.2, o.z], rank: o.mood === 'needs' ? 1 : o.mood === 'working' ? 2 : 3, small: true,
        });
      }
    }
    return out.sort((a, b) => a.rank - b.rank);
  }

  function drawLabels() {
    if (!labels) return;
    const placedBoxes = [];
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
      const b = { x0: x - 2, y0: y - 2, x1: x + lw + 2, y1: y + lh + 2 }; // the photo floors stand closer than the drawn ones: labels may sit 4 px apart
      const clash = placedBoxes.some((p) => b.x0 < p.x1 && b.x1 > p.x0 && b.y0 < p.y1 && b.y1 > p.y0);
      if (offscreen || clash) { el.hidden = true; continue; }
      placedBoxes.push(b);
      el.hidden = false;
      el.style.transform = `translate(${Math.round(x)}px, ${Math.round(y)}px)`;
    }
    for (const [key, el] of labelEls) if (!seen.has(key)) el.hidden = true;
  }

  /* ---------- the frame loop: draws only when something changed ---------- */

  let raf = 0;
  let timer = 0;
  let awake = 0;
  let last = performance.now();
  let contextLost = false;
  let disposed = false;
  let checkDrawn = 3;
  const stats = { frames: 0, loops: 0, why: '' };

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
    if (outer) {
      const s = focusStorey();
      outer.visible = !s || s.t < 0.5;
    }
    placeCuts();
    return moving;
  }

  function updateLights(dt, now) {
    let moving = false;
    const k = reduced.matches ? 1 : 1 - Math.exp(-dt * 4.5);
    const pulseOn = !reduced.matches && now - lastActive < PULSE_MS;
    for (const room of rooms.values()) {
      if (!room.storey.group.visible) continue;
      let changed = false;
      const pulse = pulseOn && room.mood === 'needs' && room.gain > 0.5 ? 1 + 0.035 * Math.sin(now / 900) : 1;
      const goal = room.goal * pulse;
      const dl = goal - room.level;
      if (Math.abs(dl) > 0.002) { room.level += dl * k; changed = true; } else if (room.level !== goal) { room.level = goal; changed = true; }
      const dc = Math.abs(room.color.r - room.goalColor.r) + Math.abs(room.color.g - room.goalColor.g) + Math.abs(room.color.b - room.goalColor.b);
      if (dc > 0.004) { room.color.lerp(room.goalColor, k); changed = true; } else if (dc > 0) { room.color.copy(room.goalColor); changed = true; }
      if (changed) { tintRoom(room); moving = moving || Math.abs(dl) > 0.002 || dc > 0.004; }
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

  function ambient(now) {
    if (reduced.matches) return false;
    let any = false;
    if (personRoom?.person && personRoom.storey.group.visible && personRoom.gain > 0.5 && now - Math.max(lastActive, personWake) < PULSE_MS * 2) {
      personRoom.person.tick(now / 1000);
      any = true;
    }
    if (walker && officeTick && walker.info()?.floor === 'penthouse') {
      officeTick(now / 1000);
      any = true;
    }
    if (now - lastActive < PULSE_MS) {
      for (const room of rooms.values()) if (room.mood === 'needs' && room.gain > 0.5 && room.storey.group.visible) { any = true; break; }
    }
    return any;
  }

  function confirmDrawn() {
    const gl = renderer.getContext();
    const px = new Uint8Array(4);
    gl.readPixels(gl.drawingBufferWidth >> 1, gl.drawingBufferHeight - 2, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);
    if (px[0] + px[1] + px[2] > 0) {
      checkDrawn = 0;
      if (labels) labels.hidden = false;
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
    if (!ready) {
      updateBackground(dt);
      renderer.render(scene, camera);
      if (failed) return;
      awake = Math.max(0, awake - 1);
      return;
    }
    const walking = walker ? walker.update(dt, now) : false;
    const camMoving = walker ? false : updateRig(dt);
    const moving = walker ? false : updateMotion(dt);
    const lit = updateLights(dt, now);
    const painted = walker ? false : updateBackground(dt);
    const anim = ambient(now);
    const active = camMoving || moving || lit || painted || walking;
    if (active || awake > 0 || anim) {
      const r = focusRoom();
      if (selected && r) {
        roomWorld(r, ring.position, selected.x, 0.03, selected.z);
        ring.scale.setScalar(clamp(Math.max(selected.w, selected.d) * 1.05, 0.35, 2));
        ring.visible = true;
      } else ring.visible = false;
      const began = performance.now();
      renderer.render(scene, camera);
      stats.renderMs = Math.round(performance.now() - began);
      stats.frames += 1;
      stats.why = walking ? 'walking' : camMoving ? 'camera' : moving ? 'floors' : lit ? 'lights' : painted ? 'background' : anim ? 'ambient' : 'finishing';
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
    camera.aspect = width / height;
    if (walker) { camera.clearViewOffset(); camera.fov = walkFov(); } else camera.setViewOffset(width, height, 0, -(topInset - bottomInset) / 2, width, height);
    camera.updateProjectionMatrix();
    if (!ready) { wake(2); return; }
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
  canvas.addEventListener('webglcontextlost', (event) => {
    event.preventDefault();
    contextLost = true;
    if (raf) { cancelAnimationFrame(raf); raf = 0; }
    if (timer) { clearTimeout(timer); timer = 0; }
    if (labels) labels.hidden = true;
    onStatus?.('lost');
  });
  canvas.addEventListener('webglcontextrestored', () => {
    contextLost = false;
    checkDrawn = 3;
    wake(3);
  });
  window.addEventListener('pagehide', (event) => {
    if (!event.persisted) renderer.forceContextLoss();
  }, { signal: listeners.signal });
  const observer = new ResizeObserver(resize);

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
      for (const m of [o.material].flat()) {
        if (!m) continue;
        for (const value of Object.values(m)) if (value?.isTexture) value.dispose();
        m.dispose();
      }
    });
    bgTexture.dispose();
    const wasLost = renderer.getContext().isContextLost();
    renderer.dispose();
    if (!wasLost) renderer.forceContextLoss();
    labels?.replaceChildren();
  }

  function where(floorId, roomId) {
    const r = rooms.get(`${floorId}/${roomId}`);
    if (!r) return null;
    const box2 = canvas.getBoundingClientRect();
    const spot = (x, z) => {
      roomWorld(r, v, x, 0.3, z).project(camera);
      return [(v.x * 0.5 + 0.5) * width + box2.left, (-v.y * 0.5 + 0.5) * height + box2.top];
    };
    const [x, y] = spot(r.centre[0], r.centre[1]);
    const [x0, y0] = spot(r.box.x0, r.centre[1]);
    const [x1, y1] = spot(r.box.x1, r.centre[1]);
    return { x: Math.round(x), y: Math.round(y), wide: Math.round(Math.hypot(x1 - x0, y1 - y0)) };
  }


  /* ---------- walking through it in first person (walk.js, loaded the first time) ---------- */

  const walkFov = () => (camera.aspect < 0.9 ? 72 : 60);
  const inside = (b, x, z, pad = 0) => x > b.x0 - pad && x < b.x1 + pad && z > b.z0 - pad && z < b.z1 + pad;

  // The walk's hall on a baked floor: the floor's own corridor, lift and reception, with nothing added
  // but somewhere to tap the lift. Floors are in their own coordinates, as the walk wants them. The
  // founder's office (opts.penthouse) is a floor only the walk has: its baked rooms come with the hall,
  // the assistant at their desk, the founder's name over the lift and where the notes hang; with no
  // baked office the walk draws its own.
  function hallFor(s, opts = null) {
    const office = opts?.penthouse ? shells.office : null;
    if (opts?.penthouse && !office) return null;
    const shell = office || s.shell;
    const group = new THREE.Group();
    const extras = [];
    if (office) {
      for (const m of office.group.children) {
        const copy = new THREE.Mesh(m.geometry, m.material.clone());
        copy.name = m.name;
        if (m.material.transparent) copy.userData.solid = true;
        copy.matrixAutoUpdate = false;
        copy.updateMatrix();
        group.add(copy);
        extras.push(copy.material);
      }
    }
    const liftRoom = shell?.rooms.get('LIFT AND STAIRS')?.outline;
    const corridor = shell?.rooms.get('CORRIDOR')?.outline;
    const lb = liftRoom ? boundsOf(liftRoom) : { x0: box3.x0 + 0.6, x1: box3.x0 + 2.0, z0: box3.z1 - 2.2, z1: box3.z1 - 0.8 };
    const cb = corridor ? boundsOf(corridor) : null;
    // A floor baked with the real lift: its leaves, which the walk slides (it stops you at them while they are shut).
    const leaves = LIFT_DOORS.map((n) => (office ? group.children : s.meshes || []).find((m) => m.name === n)).filter(Boolean);
    const car = leaves.length === 2 ? CAR : null;
    for (const m of leaves) m.userData.noCollide = true;
    const lift = car ? { x: (DOORWAY.x0 + DOORWAY.x1) / 2, z: -10.72, open: 0 } : { x: (lb.x0 + lb.x1) / 2, z: (lb.z0 + lb.z1) / 2, open: 0 };
    // out of the lift, facing the rooms across the corridor (in the office, facing the founder's desk)
    // (below ground the rooms have solid walls, so you face down the corridor, toward its far end, instead)
    const along = s.role === 'basement' && cb && cb.x1 - lift.x > lift.x - cb.x0 ? -Math.PI / 2 : s.role === 'basement' && cb ? Math.PI / 2 : null;
    // (with the real lift, you arrive in its car, facing its doors)
    const spot = car ? { x: (car.x0 + car.x1) / 2, z: car.z0 + 0.55, yaw: Math.PI } : cb ? { x: lift.x, z: (cb.z0 + cb.z1) / 2, yaw: along ?? Math.PI } : office ? { x: lift.x, z: lb.z1 + 1.0, yaw: Math.PI } : { x: lift.x + 2, z: lb.z1 - 0.7, yaw: Math.PI / 2 };
    // The baked lift is a room behind a wall the walk can't pass, so its doorstep counts as the lift: the strip of
    // corridor (or office floor) in front of it. A sign over it says where it is (walk.js).
    const front = car ? null : cb && lb.z1 <= cb.z0 + 0.01 ? { x0: lb.x0, x1: lb.x1, z0: cb.z0 - 0.4, z1: cb.z0 + 0.62 }
      : !cb ? { x0: lb.x0, x1: lb.x1, z0: lb.z1 - 0.4, z1: lb.z1 + 1.2 } : null;
    const liftSign = car ? { x: lift.x, z: DOORWAY.z1 + 0.2, y: 2.75 } : { x: lift.x, z: cb ? cb.z0 + 0.3 : lb.z1 + 0.6, y: 2.35 };
    const tap = new THREE.Mesh(new THREE.BoxGeometry(lb.x1 - lb.x0, 2.2, lb.z1 - lb.z0), hitMaterial);
    tap.position.set(lift.x, 1.1, lift.z);
    tap.visible = false;
    tap.userData = { hit: true, lift: true, stay: true, title: 'The lift' };
    group.add(tap);
    const hall = {
      baked: true, group, lift, liftSign, spot, picks: [tap], sky: shell?.sky || null,
      west: box3.x0, east: box3.x1, north: box3.z0, front: box3.z1,
      car,
      setDoors(v) {
        leaves.forEach((m, i) => { m.position.x = (i ? SLIDE : -SLIDE) * v; m.updateMatrix(); });
      },
      inLift: (x, z) => (car ? inside(car, x, z) : inside(lb, x, z) || (!!front && inside(front, x, z))),
      // whether the lift's shut doors stop a walker this wide at x, z
      shut: (x, z, r = 0) => !!car && lift.open < 0.85 && inside(DOORWAY, x, z, r),
      dispose() { tap.geometry.dispose(); for (const m of extras) m.dispose?.(); },
    };
    if (s.role === 'lobby') {
      const door = s.shell?.slots.find((x) => x.kind === 'entrance');
      hall.entrance = door ? { x: door.at[0], z: door.at[2], yaw: 0 } : { x: (box3.x0 + box3.x1) / 2, z: box3.z1 - 1.0, yaw: 0 };
    }
    if (!office && personRoom?.storey === s) {
      const at = personRoom.spec.person.at;
      hall.poe = { x: at[0], z: at[2], turn: 0 };
    }
    if (office) furnishOffice(hall, office, opts, extras);
    return hall;
  }

  // The founder's office's live part: the assistant at their desk (photo-real when exported, drawn
  // otherwise) with the ring to talk to them, the founder's desk and name, and where the notes hang.
  function furnishOffice(hall, office, { founder = null, assistant = null } = {}, extras) {
    const { group } = hall;
    const slot = (kind) => office.slots.find((x) => x.kind === kind);
    const desk = slot('desk');
    if (desk) {
      const name = founder?.name || '';
      const title = founder?.title || '';
      const hit = new THREE.Mesh(new THREE.BoxGeometry(desk.w + 0.4, 1.3, desk.d + 1.2), hitMaterial);
      hit.position.set(desk.at[0], 0.65, desk.at[2]);
      hit.visible = false;
      hit.userData = { hit: true, stay: true, title: name || "The founder's desk", sub: title };
      group.add(hit);
      hall.picks.push(hit);
      hall.desk = { x: desk.at[0], z: desk.at[2] + 0.85, name, title };
      const plate = slot('nameplate');
      if (plate && name) {
        const sign = nameSign(name.toUpperCase(), plate.w, plate.h, plate.color || '#C9A46A');
        sign.position.set(plate.at[0], plate.at[1] + plate.h / 2, plate.at[2] + 0.012);
        sign.rotation.y = plate.rot;
        group.add(sign);
        extras.push(sign.material.map, sign.material, sign.geometry);
      }
    }
    const seat = slot('assistant');
    if (seat && assistant?.name) {
      const real = realPerson('assistant', assistant.look);
      const person = real?.make('assistant', { seed: 11 }) || buildPerson(receptionistSpec(assistant));
      person.group.position.set(seat.at[0], 0, seat.at[2]);
      person.group.rotation.y = seat.rot;
      group.add(person.group);
      if (real) {
        const chair = kit.make('desk chair');
        chair.position.set(seat.at[0] + Math.sin(seat.rot) * 0.045, 0, seat.at[2] + Math.cos(seat.rot) * 0.045);
        chair.rotation.y = seat.rot;
        group.add(chair);
      }
      const hit = new THREE.Mesh(new THREE.BoxGeometry(1.1, 1.85, 1.6), hitMaterial);
      hit.position.set(seat.at[0] - 0.3, 0.92, seat.at[2]);
      hit.visible = false;
      hit.userData = { hit: true, stay: true, talk: true, title: assistant.name, sub: `${assistant.title || 'Assistant'}. Tap to talk.` };
      group.add(hit);
      hall.picks.push(hit);
      const stand = seat.stand ? [seat.stand[0], seat.stand[2] ?? -seat.stand[1]] : [seat.at[0] - 1.75, seat.at[2]];
      hall.assistant = {
        x: seat.at[0], z: seat.at[2], stand, hit,
        who: { title: assistant.name, sub: assistant.title || 'Assistant', href: assistant.href || '#/assistant', voice: assistant.voice || null, stay: true },
      };
      officeTick = person.tick ? (t) => person.tick(t) : null;
    }
    const notes = office.slots.filter((x) => x.kind === 'note');
    if (notes.length) {
      hall.notes = {
        slots: notes.map((n) => ({ x: n.at[0], z: n.at[2], turn: n.rot })),
        y: notes[0].at[1], high: office.height, where: 'in the library: step out of the lift and turn right',
      };
    }
  }

  // The founder's name in raised gold letters over the lift doors.
  // A quote painted on a wall: the words centred in a script hand, as many lines as they need, and who said
  // them centred under it. Painted, so it takes no light of its own.
  function quoteSign(text, by, w, h, color = '#2E2A26') {
    const c = document.createElement('canvas');
    c.width = 2048;
    c.height = Math.round((2048 * h) / w);
    const g = c.getContext('2d');
    const face = (px) => `${px}px "Snell Roundhand", "Apple Chancery", "Savoye LET", "Segoe Script", "URW Chancery L", cursive`;
    const wide = c.width * 0.94;
    const lines = (px, most = wide) => {
      g.font = face(px);
      const out = [];
      let line = '';
      for (const word of text.trim().split(/\s+/)) {
        const next = line ? `${line} ${word}` : word;
        if (line && g.measureText(next).width > most) { out.push(line); line = word; } else line = next;
      }
      return line ? [...out, line] : out;
    };
    let px = Math.round(c.height / 2.6);
    let rows = lines(px);
    while (px > 12 && rows.length * px * 1.2 + (by ? px * 0.95 : 0) > c.height * 0.96) rows = lines(--px);
    // even lines: the narrowest wrap that needs no more lines, so no word is left alone on the last one
    let lo = wide / 2, hi = wide;
    for (let i = 0; i < 12; i++) { const mid = (lo + hi) / 2; if (lines(px, mid).length > rows.length) lo = mid; else hi = mid; }
    rows = lines(px, hi);
    g.fillStyle = color;
    g.textBaseline = 'alphabetic';
    let y = (c.height - (rows.length * px * 1.2 + (by ? px * 0.95 : 0))) / 2 + px * 0.95;
    g.textAlign = 'center';
    g.font = face(px);
    for (const row of rows) { g.fillText(row, c.width / 2, y); y += px * 1.2; }
    if (by) {
      g.font = face(Math.round(px * 0.62));
      g.fillText(by, c.width / 2, y + px * 0.1);
    }
    const tex = new THREE.CanvasTexture(c);
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.anisotropy = 8;
    return new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ map: tex, transparent: true, opacity: 0.9, depthWrite: false, toneMapped: false }));
  }

  function nameSign(text, w, h, color) {
    const c = document.createElement('canvas');
    c.width = 1024;
    c.height = Math.round((1024 * h) / w);
    const g = c.getContext('2d');
    g.clearRect(0, 0, c.width, c.height);
    g.textAlign = 'center';
    g.textBaseline = 'middle';
    g.font = `600 ${Math.round(c.height * 0.62)}px "Helvetica Neue", Arial, sans-serif`;
    g.fillStyle = 'rgba(0,0,0,0.35)';
    g.fillText(text, c.width / 2 + 3, c.height / 2 + 4);
    g.fillStyle = color;
    g.fillText(text, c.width / 2, c.height / 2);
    const tex = new THREE.CanvasTexture(c);
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.anisotropy = 8;
    return new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshStandardMaterial({ map: tex, transparent: true, roughness: 0.35, metalness: 0.6 }));
  }

  async function walk(on = true) {
    if (!on) { endWalk(); return false; }
    if (walker || disposed || !ready) return !!walker;
    walkStart ??= import('./walk.js');
    const { createWalk, loadStyle } = await walkStart;
    await loadStyle();
    // the founder's office is only ever walked: its baked floor loads the first time someone walks
    if (buildingIndex?.shells?.office && !shells.office) {
      try {
        const office = await loadShell(`${root}${buildingIndex.shells.office}`);
        office.height = shellHeight(office);
        shells.office = office;
      } catch (error) {
        console.warn("Arnheim: the founder's office did not load; the walk draws its own.", error);
      }
    }
    if (walker || disposed || contextLost) return !!walker;
    selected = null;
    onHover?.(null);
    highlight(null);
    // every floor back in the building, whole, while one at a time is walked
    for (const s of storeys) { s.t = s.goalT = 0; s.part = s.goalPart = 0; placeStorey(s); }
    if (outer) outer.visible = false;
    // the cuts stay on (switching three.js's clipping off and on again leaves stale planes behind) but
    // stand out of the way while you walk
    front.constant = top.constant = 1e5;
    scene.background = (shells.lobby || shells.floor)?.sky || bgTexture;
    camera.near = 0.05;
    camera.far = 120;
    camera.clearViewOffset();
    camera.fov = walkFov();
    camera.updateProjectionMatrix();
    try {
      walker = createWalk({
        scene, camera, canvas, renderer, composer: { addPass() {}, removePass() {} }, photo: null, storeys, org, reduced, personRoom, start: view.floor,
        onPick, describe, infoText, roomWorld, wake, touched, version: () => version, talk, hallFor,
        // each floor shows its own view out of the windows
        entered(_s, hall) { scene.background = hall?.sky || (shells.lobby || shells.floor)?.sky || bgTexture; },
        notes: () => notes, onNotes,
        poeAwake() { personWake = performance.now(); },
        shadows() {},
        leave() { endWalk(); onWalk?.(false); },
      });
    } catch (error) {
      console.error(error);
      walker = null;
      restoreView();
      return false;
    }
    for (const room of rooms.values()) tintRoom(room);
    wake(3);
    return true;
  }

  function restoreView() {
    camera.near = 0.3;
    camera.far = 500;
    camera.fov = 24;
    scene.background = bgTexture;
    for (const s of storeys) placeStorey(s);
    placeCuts();
    for (const room of rooms.values()) tintRoom(room);
    if (outer) outer.visible = true;
    resize();
    const was = view;
    view = {};
    focus(was);
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

  async function load() {
    const index = await (await fetch(`${root}building.json`, { cache: 'no-cache' })).json();
    buildingIndex = index;
    const roles = new Set(defs.map((d) => (d.id === org.basement?.id ? 'basement' : d.id === org.lobby?.id ? 'lobby' : 'floor')));
    roles.add('site'); // the outside, when it has been baked
    const [k, folk, ...loaded] = await Promise.all([
      loadKit(`${root}${index.kit}`),
      index.people ? loadPeople(`${root}${index.people}`).catch((error) => { console.warn('Arnheim: the photo-real people did not load; the drawn ones stand in.', error); return null; }) : null,
      ownPeople ? loadPeople(ownPeople.endsWith('/') ? ownPeople : `${ownPeople}/`).catch((error) => { console.warn("Arnheim: the company's own people did not load; they are drawn instead.", error); return null; }) : null,
      ...[...roles].filter((r) => index.shells[r]).map(async (r) => [r, await loadShell(`${root}${index.shells[r]}`)]),
    ]);
    if (disposed) return;
    kit = k;
    people = folk;
    own = loaded.shift();
    for (const [role, shell] of loaded) {
      shell.height = shellHeight(shell);
      shells[role] = shell;
    }
    const any = shells.floor || shells.lobby;
    if (any) {
      let x0 = Infinity; let x1 = -Infinity; let z0 = Infinity; let z1 = -Infinity;
      for (const r of any.rooms.values()) {
        if (!r.outline) continue;
        for (const [x, z] of r.outline) { x0 = Math.min(x0, x); x1 = Math.max(x1, x); z0 = Math.min(z0, z); z1 = Math.max(z1, z); }
      }
      Object.assign(box3, { x0: x0 - 0.3, x1: x1 + 0.3, z0: z0 - 0.3, z1: z1 + 0.3 });
      OX = -(box3.x0 + box3.x1) / 2;
      OZ = -(box3.z0 + box3.z1) / 2;
    }
    const d = new THREE.Vector3(index.sun[0], index.sun[2], -index.sun[1]).normalize();
    sun.position.copy(d).multiplyScalar(40);
    defs.forEach((def, i) => buildStorey(def, i));
    const roofY = stack();
    signTop = buildOuter(roofY);
    bottomY = Math.min(-0.35, ...storeys.map((s) => s.y));
    for (const s of storeys) placeStorey(s);
    ready = true;
    applyLive();
    focus(view);
    resized = false;
    resize();
  }

  if (labels) labels.hidden = false;
  paintBackground();
  setTheme(true);
  resize();
  observer.observe(canvas);
  load().catch((error) => {
    failed = error;
    console.error('Arnheim: the photo-real building could not load.', error);
    onStatus?.('blank');
  });

  return {
    setLive, setScene, setTheme, focus, highlight, zoomBy, turn, resetView, wake, where, dispose,
    debug: () => ({ scene, camera, renderer, storeys }), // for tests in the console; changes nothing by itself
    walk, walking: () => !!walker, walkInfo: () => walker?.info() || null, walkDebug: () => walker?.debug || null,
    setNotes(list) { notes = Array.isArray(list) ? list : []; walker?.setNotes(notes); },
    ready: () => ready,
    // What each room shows and where, for tests. Changes nothing.
    rooms: () => [...rooms.values()].map((r) => ({ key: r.key, kind: r.kind, mood: r.mood, objects: r.objects.map((o) => ({ title: o.title, x: o.x, z: o.z, figure: o.figure || null })) })),
    snapshot() {
      renderer.info.autoReset = false;
      renderer.info.reset();
      awake = Math.max(awake, 1);
      step(performance.now());
      renderer.info.autoReset = true;
      stats.snapshotCalls = renderer.info.render.calls;
      stats.snapshotTriangles = renderer.info.render.triangles;
      return canvas.toDataURL('image/jpeg', 0.9);
    },
    inspect() {
      let visibleMeshes = 0;
      scene.traverseVisible((o) => { if (o.isMesh) visibleMeshes += 1; });
      return { ...stats, ready, notes: notes.length, version, sceneChildren: scene.children.length, visibleMeshes, lastPassCalls: renderer.info.render.calls, lastPassTriangles: renderer.info.render.triangles, camera: camera.position.toArray().map((n) => Math.round(n * 10) / 10) };
    },
    stats: () => ({ ...stats, calls: renderer.info.render.calls, triangles: renderer.info.render.triangles, geometries: renderer.info.memory.geometries, textures: renderer.info.memory.textures }),
  };
}
