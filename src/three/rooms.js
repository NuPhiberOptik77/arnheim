// What stands in each kind of room. Plain data goes in (lists of goals, tasks, seats, entries),
// a model comes out. Nothing here knows about the panel or the server, so this scene can be
// driven from anywhere later on. Modelling helpers and furniture come from House Control (MIT).
import * as THREE from '../../vendor/three/three.module.js';
import { at, box, cyl, decal, mat } from './kit.js';
import { piece } from './furniture.js';
import { POE, buildSeated } from './poe.js';

export const W = 5;
export const D = 4.4;
export const H = 2.6;

const DARK = '#23262e';
const WOOD = '#b48d63';
const AMBER = '#ff8a1e';
const WARM = '#ffb066';
const COOL = '#8fb4ff';
const FAIL = '#ff5a6e';

// Each floor's colours: its floorboards, walls, fabric and rugs, and the sky behind the building
// when that floor is picked. A floor names one with "palette"; otherwise floors take them in turn,
// the lobby takes sand and the basement slate.
export const PALETTES = {
  terracotta: { floor: 'walnut', wall: '#eadfce', fabric: '#b5603f', rug: '#6b3f34', sky: { dark: '#5a3528', light: '#f3dccf' } },
  harbour: { floor: 'oak', wall: '#e7e3db', fabric: '#4c7595', rug: '#2f4660', sky: { dark: '#26425c', light: '#d5e4f1' } },
  sage: { floor: 'oak', wall: '#dde3d2', fabric: '#5a8a5f', rug: '#36533c', sky: { dark: '#2c4a32', light: '#d9ebd6' } },
  indigo: { floor: 'greywood', wall: '#d9dbe6', fabric: '#6a6fb0', rug: '#3b3e6b', sky: { dark: '#2f2f5c', light: '#dcdcf3' } },
  plum: { floor: 'walnut', wall: '#e6d8dc', fabric: '#9b5b79', rug: '#5a3450', sky: { dark: '#4c2a48', light: '#efdcea' } },
  teal: { floor: 'greywood', wall: '#d8e6e3', fabric: '#3f8a85', rug: '#285250', sky: { dark: '#1f4744', light: '#d3eae6' } },
  sand: { floor: 'stone', wall: '#efe7da', fabric: '#c28a5a', rug: '#7a4b2f', sky: { dark: '#4e3b28', light: '#f2e4cd' } },
  slate: { floor: 'slate', wall: '#a8acb2', fabric: '#555b66', rug: '#3a3f49', sky: { dark: '#2d3440', light: '#d8dce2' } },
};
const IN_TURN = ['terracotta', 'harbour', 'sage', 'indigo', 'plum', 'teal'];

export function paletteFor(def, role, index) {
  if (PALETTES[def.palette]) return PALETTES[def.palette];
  if (role === 'lobby') return PALETTES.sand;
  if (role === 'basement') return PALETTES.slate;
  return PALETTES[IN_TURN[Math.max(0, index) % IN_TURN.length]];
}

// A short stable number from an id, so a conversation's figure looks the same every time.
export function identity(id) {
  let n = 2166136261;
  for (const ch of String(id)) n = Math.imul(n ^ ch.charCodeAt(0), 16777619);
  return n >>> 0;
}

function label(text, w, h, { bg = '#1c2230', ink = '#f7efe2', glow = 1.1 } = {}) {
  const canvas = document.createElement('canvas');
  canvas.width = Math.ceil(w * 220);
  canvas.height = Math.ceil(h * 220);
  const g = canvas.getContext('2d');
  g.fillStyle = bg;
  g.fillRect(0, 0, canvas.width, canvas.height);
  g.fillStyle = ink;
  g.textAlign = 'center';
  g.textBaseline = 'middle';
  let px = canvas.height * 0.62;
  g.font = `700 ${px}px -apple-system, "Helvetica Neue", Arial, sans-serif`;
  while (g.measureText(text).width > canvas.width * 0.9 && px > 8) {
    px -= 2;
    g.font = `700 ${px}px -apple-system, "Helvetica Neue", Arial, sans-serif`;
  }
  g.fillText(text, canvas.width / 2, canvas.height * 0.54);
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8;
  const m = new THREE.MeshStandardMaterial({ map: tex, emissiveMap: tex, emissive: '#ffffff', emissiveIntensity: glow, roughness: 0.6 });
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(w, h), m);
  mesh.userData.live = true; // keeps its own material, never merged
  return mesh;
}

function desk(g, x, z, screen, { seat = '#2b2e37', width = 1.08 } = {}) {
  const top = mat(WOOD, { rough: 0.55 });
  const dark = mat(DARK, { rough: 0.6 });
  g.add(
    decal(width + 0.5, 1.5, x, z + 0.18),
    at(box(width, 0.035, 0.54, top, { r: 0.012 }), x, 0.7, z),
    at(box(0.035, 0.7, 0.46, dark, { r: 0 }), x - width / 2 + 0.05, 0, z),
    at(box(0.035, 0.7, 0.46, dark, { r: 0 }), x + width / 2 - 0.05, 0, z),
    at(box(0.05, 0.13, 0.05, dark, { r: 0 }), x, 0.735, z - 0.16),
    at(box(0.5, 0.3, 0.025, dark, { r: 0.008 }), x, 0.84, z - 0.17),
    at(box(0.46, 0.26, 0.004, screen, { r: 0 }), x, 0.86, z - 0.155),
    at(box(0.2, 0.03, 0.14, mat('#e7ddc9', { rough: 0.9 }), { r: 0 }), x - 0.3, 0.735, z + 0.08),
    at(box(0.4, 0.05, 0.4, mat(seat, { rough: 0.8 }), { r: 0.02 }), x, 0.42, z + 0.48),
    at(box(0.4, 0.38, 0.04, mat(seat, { rough: 0.8 }), { r: 0.015 }), x, 0.46, z + 0.69),
    at(cyl(0.022, 0.03, 0.42, dark, 8), x, 0, z + 0.48),
    at(cyl(0.2, 0.2, 0.02, dark, 12), x, 0, z + 0.48),
  );
}

// A bookcase against the back wall. rows() gives each row's height for standing things on.
function bookcase(g, x, z, width, height, rows) {
  const wood = mat('#8a6a4a', { rough: 0.65 });
  g.add(decal(width + 0.5, 0.9, x, z + 0.12));
  g.add(at(box(width, height, 0.04, mat('#6e5238', { rough: 0.8 }), { r: 0 }), x, 0, z - 0.15));
  for (const side of [-1, 1]) g.add(at(box(0.04, height, 0.34, wood, { r: 0 }), x + side * (width / 2 - 0.02), 0, z));
  const levels = [];
  for (let i = 0; i <= rows; i++) {
    const y = 0.08 + (height - 0.12) * (i / rows);
    g.add(at(box(width, 0.03, 0.34, wood, { r: 0 }), x, y, z));
    if (i < rows) levels.push(y + 0.03);
  }
  return levels;
}

function bookPile(g, x, z, width, levels, list, ctx, colorOf, { limit, room = 'Show the list', thick = 0.1 } = {}) {
  const perRow = Math.max(1, Math.floor((width - 0.14) / (thick + 0.012)));
  const room_ = perRow * levels.length;
  const cap = Math.min(limit || room_, room_);
  const shown = list.length > cap ? list.slice(0, cap - 1) : list;
  shown.forEach((item, i) => {
    const row = levels.length - 1 - Math.floor(i / perRow);
    const col = i % perRow;
    const bx = x - width / 2 + 0.08 + (col + 0.5) * (thick + 0.012);
    const tall = 0.26 + (identity(item.id) % 7) * 0.012;
    const color = colorOf(item);
    g.add(at(box(thick, tall, 0.22, mat(color, { rough: 0.8 }), { r: 0 }), bx, levels[row], z + 0.01));
    ctx.object({ x: bx, y: levels[row], z: z + 0.08, w: thick + 0.03, h: tall, d: 0.3, title: item.title, sub: item.sub, href: item.href, mood: item.mood });
  });
  if (list.length > shown.length) {
    ctx.more(list.length - shown.length, x + width / 2 - 0.2, levels[0] + 0.3, z + 0.15, room);
  }
}

// A four-drawer steel filing cabinet with a folder on top for each thing filed, up to six.
function filingCabinet(g, x, z, filed) {
  const height = 1.32;
  const step = (height - 0.07) / 4;
  g.add(decal(1, 0.85, x, z + 0.06), at(box(0.62, height, 0.5, mat('#7d828b', { rough: 0.55, metal: 0.35 }), { r: 0.012 }), x, 0, z));
  for (let i = 0; i < 4; i++) {
    const y = 0.05 + i * step;
    g.add(
      at(box(0.56, step - 0.025, 0.012, mat('#959aa3', { rough: 0.5, metal: 0.35 }), { r: 0 }), x, y, z + 0.256),
      at(box(0.16, 0.022, 0.024, mat(DARK, { rough: 0.4, metal: 0.6 }), { r: 0 }), x, y + step * 0.42, z + 0.27),
      at(box(0.14, 0.05, 0.004, mat('#efe7d6', { rough: 0.9 }), { r: 0 }), x, y + step * 0.62, z + 0.264),
    );
  }
  const folders = ['#d9a441', '#b5603f', '#4c7595'];
  for (let i = 0; i < Math.min(filed, 6); i++) g.add(at(box(0.36, 0.02, 0.27, mat(folders[i % 3], { rough: 0.9 }), { r: 0 }), x, height + i * 0.022, z));
}

function signPost(g, x, z, text, lit) {
  const m = mat(DARK, { rough: 0.5 });
  g.add(decal(1.2, 0.6, x, z), at(box(0.42, 0.03, 0.28, m, { r: 0 }), x, 0, z), at(box(0.04, 1.05, 0.04, m, { r: 0 }), x, 0.02, z));
  g.add(at(box(0.98, 0.42, 0.04, mat('#2b2f3a', { rough: 0.6 }), { r: 0.01 }), x, 1.04, z));
  g.add(at(box(0.9, 0.34, 0.006, mat('#10131a', { rough: 0.4, ...(lit ? { emissive: WARM, emissiveIntensity: 1.7 } : {}) }), { r: 0 }), x, 1.08, z + 0.022));
  return text;
}

/* ---------- each kind of room: lamp places, what stands there always, what comes from data ---------- */

export const ROOMS = {
  goals: {
    lamps: { main: [W / 2, 1.9, 1.7], side: [0.42, 1.42, 0.5] },
    decor(g, s) {
      g.add(at(piece('rug', { size: [3, 1.7], color: s.rug }), W / 2, 0, 2.5));
      const sofa = at(piece('sofa', { width: 1.9, color: s.fabric }), W / 2, 0, 3.65);
      sofa.rotation.y = Math.PI;
      g.add(decal(2.5, 1.5, W / 2, 3.65), sofa, decal(0.9, 0.9, W - 0.45, 0.45), at(piece('plant', { height: 1.25 }), W - 0.45, 0, 0.45));
      const frame = mat('#5a4334', { rough: 0.7 });
      const cork = mat('#c29a68', { rough: 1 });
      g.add(decal(3.4, 0.9, W / 2, 0.55), at(box(3, 1.3, 0.06, frame, { r: 0.02 }), W / 2, 0.55, 0.42), at(box(2.86, 1.16, 0.02, cork, { r: 0 }), W / 2, 0.62, 0.45));
      for (const side of [-1, 1]) g.add(at(box(0.07, 0.6, 0.3, frame, { r: 0 }), W / 2 + side * 1.3, 0, 0.42));
    },
    // A board with a flag per goal: gold once reached.
    fill(g, info, ctx) {
      const list = info.items || [];
      const cap = 8;
      const shown = list.length > cap ? list.slice(0, cap - 1) : list;
      shown.forEach((goal, i) => {
        const col = i % 4;
        const row = Math.floor(i / 4);
        const x = W / 2 - 1.05 + col * 0.7;
        const y = row === 0 ? 1.18 : 0.68;
        const color = goal.reached ? '#f2c14e' : '#e2574c';
        const pole = at(cyl(0.01, 0.01, 0.44, mat(DARK), 6), x, y, 0.5);
        const flag = new THREE.Mesh(new THREE.CylinderGeometry(0.17, 0.17, 0.012, 3), mat(color, { rough: 0.8, ...(goal.reached ? { emissive: color, emissiveIntensity: 0.5 } : {}) }));
        flag.rotation.set(Math.PI / 2, Math.PI / 2, 0);
        flag.position.set(x + 0.13, y + 0.34, 0.5);
        g.add(pole, flag);
        ctx.object({ x: x + 0.1, y, z: 0.5, w: 0.5, h: 0.5, d: 0.2, title: goal.title, sub: goal.sub, href: goal.href });
      });
      if (list.length > shown.length) ctx.more(list.length - shown.length, W / 2 + 1.05, 0.9, 0.5);
    },
  },

  work: {
    lamps: { main: [W / 2, 2, 2.4], side: [0.42, 1.42, 0.5] },
    decor(g) {
      g.add(decal(2, 0.7, W / 2, 0.3), at(piece('sideboard', { width: 1.8 }), W / 2, 0, 0.28));
      g.add(decal(0.9, 0.9, W - 0.45, 0.45), at(piece('plant', { height: 1.1 }), W - 0.45, 0, 0.45));
    },
    // A desk per open task, front row first, the most pressing first, with someone at it while the
    // task is being worked on now. Past the limit, a stack and "+N".
    fill(g, info, ctx) {
      const list = info.items || [];
      const cap = 9;
      const shown = list.length > cap ? list.slice(0, cap - 1) : list;
      const xs = [W * 0.2, W * 0.5, W * 0.8];
      const zs = [3.45, 2.3, 1.15];
      shown.forEach((task, i) => {
        const x = xs[[1, 0, 2][i % 3]];
        const z = zs[Math.floor(i / 3)];
        const needs = task.mood === 'needs';
        const working = task.mood === 'working';
        const screen = needs
          ? mat('#14100b', { rough: 0.3, emissive: AMBER, emissiveIntensity: 2.6 })
          : working
            ? mat('#14100b', { rough: 0.3, emissive: WARM, emissiveIntensity: 1.9 })
            : mat('#0c0f14', { rough: 0.3, emissive: '#3a4a6b', emissiveIntensity: 0.25 });
        desk(g, x, z, screen);
        if (needs) g.add(decal(1.5, 1.2, x, z + 0.2, { color: AMBER, opacity: 0.3, add: true, y: 0.018 }));
        if (working) {
          g.add(decal(1.4, 1.1, x, z + 0.2, { color: WARM, opacity: 0.22, add: true, y: 0.018 }));
          const person = at(buildSeated(identity(task.id ?? task.title), { seat: 0.47, pose: 'desk' }), x, 0, z + 0.48);
          person.rotation.y = Math.PI; // facing the screen
          g.add(person);
        }
        // figure: where someone sits, and a good place to stand and talk to them (walk.js).
        const figure = working ? { x, z: z + 0.48, stand: [x + 0.75, z + 0.65] } : null;
        ctx.object({ x, y: 0, z: z + 0.15, w: 1.2, h: 1.15, d: 1.2, title: task.title, sub: task.sub, href: task.href, mood: task.mood, figure });
      });
      if (list.length > shown.length) {
        const x = xs[2];
        const z = zs[2];
        const paper = mat('#e7ddc9', { rough: 0.95 });
        g.add(decal(1.2, 1, x, z), at(box(0.8, 0.5, 0.56, mat('#a58355', { rough: 0.9 }), { r: 0.01 }), x, 0, z), at(box(0.72, 0.28, 0.5, paper, { r: 0.01 }), x, 0.5, z));
        ctx.more(list.length - shown.length, x, 1.05, z);
      }
    },
  },

  conversations: {
    lamps: { main: [W / 2, 2.05, D / 2 + 0.1], side: [0.42, 1.42, 0.5] },
    decor(g, s) {
      const rug = at(cyl(1.95, 1.95, 0.016, mat(s.rug, { rough: 1 }), 40), W / 2, 0, D / 2 + 0.15);
      rug.userData.flat = true;
      g.add(rug, decal(1.1, 1.1, W / 2, D / 2 + 0.15), at(cyl(0.42, 0.42, 0.04, mat(WOOD, { rough: 0.5 }), 24), W / 2, 0.38, D / 2 + 0.15), at(cyl(0.05, 0.07, 0.38, mat(DARK), 10), W / 2, 0, D / 2 + 0.15));
      g.add(decal(0.9, 0.9, W - 0.42, 0.42), at(piece('plant', { height: 1.3 }), W - 0.42, 0, 0.42));
    },
    // A seat per conversation, with someone in it while the conversation is working now.
    fill(g, info, ctx, s) {
      const list = info.items || [];
      const cap = 8;
      const shown = list.length > cap ? list.slice(0, cap - 1) : list;
      const n = Math.max(shown.length, 3);
      const cx = W / 2;
      const cz = D / 2 + 0.15;
      const fabric = mat(s.fabric, { rough: 1 });
      const dark = mat(DARK, { rough: 0.8 });
      shown.forEach((c, i) => {
        const a = (i / n) * Math.PI * 2 + 0.45;
        const seat = new THREE.Group();
        seat.position.set(cx + Math.sin(a) * 1.42, 0, cz + Math.cos(a) * 1.42);
        seat.rotation.y = a + Math.PI;
        seat.add(
          at(box(0.56, 0.36, 0.52, dark, { r: 0.04 }), 0, 0.04, 0),
          at(box(0.48, 0.1, 0.44, fabric, { r: 0.04 }), 0, 0.36, 0.02),
          at(box(0.56, 0.42, 0.1, fabric, { r: 0.04 }), 0, 0.42, -0.24),
        );
        g.add(decal(1, 1, seat.position.x, seat.position.z), seat);
        if (c.working) {
          seat.add(buildSeated(identity(c.id), { seat: 0.46, pose: 'chat' })); // the same person for the same id
          g.add(decal(1.5, 1.5, seat.position.x, seat.position.z, { color: WARM, opacity: 0.3, add: true, y: 0.02 }));
        }
        if (c.check) seat.add(at(new THREE.Mesh(new THREE.SphereGeometry(0.05, 12, 8), mat(COOL, { emissive: COOL, emissiveIntensity: 2.4 })), 0, 0.98, -0.24));
        ctx.object({ x: seat.position.x, y: 0, z: seat.position.z, w: 0.8, h: 1.05, d: 0.8, title: c.title, sub: c.sub, href: c.href, mood: c.working ? 'working' : c.check ? 'check' : 'quiet',
          figure: c.working ? { x: seat.position.x, z: seat.position.z, stand: [seat.position.x + (cx - seat.position.x) * 0.55, seat.position.z + (cz - seat.position.z) * 0.55] } : null });
      });
      if (list.length > shown.length) ctx.more(list.length - shown.length, cx, 0.72, cz);
    },
  },

  code: {
    lamps: { main: [W / 2, 2.05, 1.9], side: [W - 0.42, 1.42, D - 0.55] },
    decor(g, s) {
      g.add(at(piece('rug', { size: [2.4, 1.5], color: s.rug }), W / 2, 0, 3.2));
      desk(g, W / 2, 3, mat('#0c0f14', { rough: 0.3, emissive: '#3a4a6b', emissiveIntensity: 0.25 }), { width: 1.3 });
      g.add(decal(0.9, 0.9, 0.42, D - 0.5), at(piece('plant', { height: 1 }), 0.42, 0, D - 0.5));
    },
    // Shelves: a book per pull request, a crate per copy with unsaved code.
    fill(g, info, ctx) {
      const prLevels = bookcase(g, 1.55, 0.3, 2.5, 1.75, 3);
      const copyLevels = bookcase(g, 3.95, 0.3, 1.7, 1.75, 3);
      const prs = info.prs || [];
      bookPile(g, 1.55, 0.3, 2.5, prLevels, prs, ctx, (p) => (p.draft ? '#8b93a7' : '#4f9462'), { limit: 45, thick: 0.13 });
      const copies = info.copies || [];
      const cap = 6;
      const shown = copies.length > cap ? copies.slice(0, cap - 1) : copies;
      const crate = mat('#c9a06a', { rough: 0.9 });
      shown.forEach((c, i) => {
        const row = copyLevels.length - 1 - Math.floor(i / 2);
        const x = 3.95 - 0.38 + (i % 2) * 0.76;
        g.add(at(box(0.66, 0.3, 0.26, crate, { r: 0.01 }), x, copyLevels[row], 0.32));
        ctx.object({ x, y: copyLevels[row], z: 0.38, w: 0.7, h: 0.34, d: 0.34, title: c.title, sub: c.sub, href: c.href });
      });
      if (copies.length > shown.length) ctx.more(copies.length - shown.length, 3.95, 1.2, 0.4);
    },
  },

  /* ---------- Front of house: a lobby ---------- */

  websites: {
    // The side lamp is a desk lamp on the counter, so Poe behind it is lit warmly.
    lamps: { main: [W / 2, 2.05, 2.4], side: [W / 2 + 0.72, 1.5, 3.14], deskTop: 1.03 },
    person: POE, // Poe, the receptionist, stands behind the desk (three/poe.js)
    decor(g, s, ctx) {
      const front = mat('#8a5f3c', { rough: 0.55 });
      const top = mat('#e9e4d8', { rough: 0.3 });
      g.add(decal(4.2, 1.8, W / 2, 3.25), at(box(3.3, 0.98, 0.5, front, { r: 0.03 }), W / 2, 0, 3.3), at(box(3.5, 0.05, 0.72, top, { r: 0.02 }), W / 2, 0.98, 3.25));
      const sign = label('Reception', 2.2, 0.36);
      sign.position.set(W / 2, 0.62, 3.56);
      g.add(sign);
      ctx.signs.push(sign);
      g.add(at(cyl(0.05, 0.04, 0.1, mat('#d7d0c4')), W / 2 + 1.25, 1.03, 3.2));
      g.add(decal(0.9, 0.9, W - 0.42, 0.42), at(piece('plant', { height: 1.2 }), W - 0.42, 0, 0.42));
    },
    // A screen per website on a wall of screens: warm when it answered the last check.
    fill(g, info, ctx) {
      const list = info.items || [];
      const cap = 6;
      const shown = list.length > cap ? list.slice(0, cap - 1) : list;
      const frame = mat(DARK, { rough: 0.5 });
      g.add(decal(3.4, 0.8, W / 2, 0.5), at(box(3.1, 1.5, 0.08, mat('#3a3f49', { rough: 0.8 }), { r: 0.01 }), W / 2, 0.4, 0.34));
      shown.forEach((site, i) => {
        const x = W / 2 - 1 + (i % 3);
        const y = i < 3 ? 1.22 : 0.56;
        const screen = site.mood === 'failed'
          ? mat('#14090b', { rough: 0.3, emissive: FAIL, emissiveIntensity: 1.6 })
          : site.up
            ? mat('#14100b', { rough: 0.3, emissive: WARM, emissiveIntensity: 1.5 })
            : mat('#0c0f14', { rough: 0.3, emissive: '#3a4a6b', emissiveIntensity: 0.25 });
        g.add(at(box(0.86, 0.56, 0.04, frame, { r: 0.012 }), x, y, 0.38), at(box(0.78, 0.48, 0.006, screen, { r: 0 }), x, y + 0.04, 0.405));
        ctx.object({ x, y, z: 0.42, w: 0.9, h: 0.6, d: 0.2, title: site.title, sub: site.sub, href: site.href, mood: site.mood });
      });
      if (list.length > shown.length) ctx.more(list.length - shown.length, W / 2 + 1, 0.9, 0.45);
      const [px, , pz] = POE.at;
      ctx.object({ x: px, y: 0.95, z: pz, w: 0.7, h: 1.0, d: 0.5, title: POE.name, sub: 'The receptionist. Tap to talk.', href: POE.href, person: true });
    },
  },

  email: {
    lamps: { main: [W / 2, 2.05, 2.1], side: [W - 0.42, 1.42, 0.5] },
    decor(g, s) {
      g.add(at(piece('rug', { size: [2.6, 1.5], color: s.rug }), W / 2, 0, 3));
      g.add(decal(1.9, 1.3, W / 2, 3.5), at(piece('bench', { width: 1.5, color: '#8a5f3c' }), W / 2, 0, 3.5));
      g.add(decal(0.9, 0.9, 0.42, 0.42), at(piece('plant', { height: 1 }), 0.42, 0, 0.42));
    },
    // Pigeonholes: one lit brass plate per address. Empty stays empty until someone adds them.
    fill(g, info, ctx) {
      const wood = mat('#6e5238', { rough: 0.7 });
      const hole = mat('#241c15', { rough: 1 });
      g.add(decal(3.4, 0.9, W / 2, 0.4), at(box(3, 1.7, 0.36, wood, { r: 0.015 }), W / 2, 0, 0.26));
      const list = info.items || [];
      for (let r = 0; r < 3; r++) {
        for (let c = 0; c < 5; c++) {
          g.add(at(box(0.48, 0.38, 0.02, hole, { r: 0 }), W / 2 - 1.14 + c * 0.57, 0.2 + r * 0.5, 0.44));
        }
      }
      list.slice(0, 15).forEach((entry, i) => {
        const x = W / 2 - 1.14 + (i % 5) * 0.57;
        const y = 1.2 - Math.floor(i / 5) * 0.5;
        g.add(at(box(0.26, 0.09, 0.012, mat('#c9a15e', { rough: 0.35, metal: 0.7, emissive: WARM, emissiveIntensity: 0.9 }), { r: 0 }), x, y + 0.26, 0.46));
        ctx.object({ x, y, z: 0.5, w: 0.5, h: 0.4, d: 0.15, title: entry.title, sub: entry.sub, href: entry.href });
      });
      if (list.length > 15) ctx.more(list.length - 15, W / 2, 1.8, 0.45);
    },
  },

  social: {
    lamps: { main: [W / 2, 2.05, 2], side: [0.42, 1.42, 0.5] },
    decor(g, s) {
      g.add(at(piece('rug', { size: [3.4, 1.5], color: s.rug }), W / 2, 0, 3.25));
      g.add(decal(0.9, 0.9, W - 0.42, 0.42), at(piece('plant', { height: 1.3 }), W - 0.42, 0, 0.42));
      g.add(decal(1.1, 1, 0.75, D - 0.65), at(piece('armchair', { color: s.fabric }), 0.75, 0, D - 0.65));
    },
    // A signboard per account: lit when it is live, dark when it doesn't exist yet.
    fill(g, info, ctx) {
      const list = info.items || [];
      const cap = 6;
      const shown = list.length > cap ? list.slice(0, cap - 1) : list;
      shown.forEach((entry, i) => {
        const x = W / 2 - 1.5 + (i % 3) * 1.5;
        const z = i < 3 ? 0.95 : 2.2;
        signPost(g, x, z, entry.title, entry.live);
        ctx.object({ x, y: 0, z, w: 1.05, h: 1.5, d: 0.4, title: entry.title, sub: entry.sub, href: entry.href });
      });
      if (list.length > shown.length) ctx.more(list.length - shown.length, W / 2 + 1.5, 1.6, 2.2);
    },
  },

  domains: {
    lamps: { main: [W / 2, 2.05, 1.8], side: [W - 0.42, 1.42, D - 0.55] },
    decor(g, s) {
      g.add(at(piece('rug', { size: [2.2, 1.5], color: s.rug }), W / 2, 0, 3.1));
      g.add(decal(1.6, 0.9, W / 2, 3.2), at(piece('coffeeTable', { width: 1.1 }), W / 2, 0, 3.2));
      g.add(decal(0.9, 0.9, 0.42, 0.42), at(piece('plant', { height: 1.2 }), 0.42, 0, 0.42));
    },
    // A brass plaque per web address, on a wooden wall panel.
    fill(g, info, ctx) {
      g.add(decal(3.3, 0.7, W / 2, 0.35), at(box(3, 1.5, 0.05, mat('#7c5a3c', { rough: 0.6 }), { r: 0.012 }), W / 2, 0.36, 0.22));
      const list = info.items || [];
      const cap = 6;
      const shown = list.length > cap ? list.slice(0, cap - 1) : list;
      shown.forEach((entry, i) => {
        const x = W / 2 - 0.72 + (i % 2) * 1.44;
        const y = 1.42 - Math.floor(i / 2) * 0.46;
        const plaque = entry.live
          ? mat('#c9a15e', { rough: 0.35, metal: 0.7, emissive: WARM, emissiveIntensity: 0.8 })
          : mat('#6f6556', { rough: 0.6, metal: 0.3 });
        g.add(at(box(1.2, 0.32, 0.02, plaque, { r: 0.006 }), x, y, 0.26));
        ctx.object({ x, y, z: 0.3, w: 1.25, h: 0.36, d: 0.15, title: entry.title, sub: entry.sub, href: entry.href });
      });
      if (list.length > shown.length) ctx.more(list.length - shown.length, W / 2, 0.6, 0.3);
    },
  },

  /* ---------- the Company room: money, legal, subscriptions and key dates ---------- */

  company: {
    lamps: { main: [W / 2, 1.95, 2.85], side: [0.42, 1.42, 0.5] },
    decor(g, s) {
      g.add(at(piece('rug', { size: [3.5, 2.5], color: s.rug }), W / 2, 0, 2.85));
      g.add(decal(3, 2.2, W / 2, 2.85), at(piece('diningSet', { width: 2.3, chairs: 6 }), W / 2, 0, 2.85));
      g.add(decal(0.9, 0.9, W - 0.42, 0.42), at(piece('plant', { height: 1.2 }), W - 0.42, 0, 0.42));
    },
    // A filing cabinet per section along the back wall. Tapping one opens the Company room.
    fill(g, info, ctx) {
      const list = info.sections || [];
      list.forEach((section, i) => {
        const x = W / 2 + (i - (list.length - 1) / 2) * 0.9;
        filingCabinet(g, x, 0.42, section.count);
        ctx.object({ x, y: 0, z: 0.42, w: 0.72, h: 1.42, d: 0.62, title: section.title, sub: section.sub, href: section.href });
      });
    },
  },

  /* ---------- Basement: machines and the library ---------- */

  machine: {
    lamps: { main: [W / 2, 2.1, 2], side: [0.75, 1.14, 1.05] },
    decor(g, s, ctx, room) {
      const steel = mat('#5f656f', { rough: 0.5, metal: 0.4 });
      const top = mat('#8a6a4a', { rough: 0.7 });
      const dark = mat('#20232a', { rough: 0.55 });
      g.add(decal(3.6, 1.5, W / 2, 1.1), at(box(3.1, 0.05, 0.86, top, { r: 0.01 }), W / 2, 0.78, 1), at(box(2.9, 0.03, 0.7, steel, { r: 0 }), W / 2, 0.25, 1));
      for (const sx of [-1, 1]) for (const sz of [-1, 1]) g.add(at(box(0.05, 0.78, 0.05, steel, { r: 0 }), W / 2 + sx * 1.48, 0, 1 + sz * 0.36));
      for (const y of [2.05, 1.8]) {
        const pipe = at(cyl(0.035, 0.035, W - 0.3, mat('#7d8691', { rough: 0.35, metal: 0.7 }), 10), 0.15, y, 0.12);
        pipe.rotation.z = -Math.PI / 2;
        pipe.userData.upper = true;
        ctx.upper.push(pipe);
        pipe.userData.live = true;
        g.add(pipe);
      }
      // Bench light, the room's second lamp.
      g.add(at(cyl(0.05, 0.07, 0.02, dark, 12), 0.75, 0.83, 1.05), at(cyl(0.01, 0.01, 0.26, dark, 6), 0.75, 0.85, 1.05));

      // The laptop.
      const screen = new THREE.MeshStandardMaterial({ color: '#0c0f14', roughness: 0.3, emissive: '#000000' });
      g.add(at(box(0.6, 0.02, 0.4, steel, { r: 0.008 }), W / 2 - 0.65, 0.83, 1.08));
      const lid = at(box(0.6, 0.38, 0.016, dark, { r: 0.008 }), W / 2 - 0.65, 0.85, 0.88);
      lid.rotation.x = -0.18;
      const glass = at(box(0.56, 0.34, 0.004, screen, { r: 0 }), W / 2 - 0.65, 0.87, 0.895);
      glass.rotation.x = -0.18;
      glass.userData.live = true;
      g.add(lid, glass);

      // The cooler the running machine blows through: a turning fan, blinking lights, moving air.
      const cx = W / 2 + 0.72;
      const cz = 1.1;
      g.add(at(box(0.9, 0.86, 0.5, dark, { r: 0.02 }), cx, 0.83, cz - 0.05));
      const ring = new THREE.Mesh(new THREE.TorusGeometry(0.3, 0.025, 8, 28), steel);
      ring.position.set(cx - 0.06, 1.26, cz + 0.215);
      g.add(ring);
      const fan = new THREE.Group();
      fan.position.copy(ring.position);
      const blade = new THREE.MeshStandardMaterial({ color: '#c6ccd4', roughness: 0.4, metalness: 0.3 });
      for (let i = 0; i < 5; i++) {
        const b = new THREE.Mesh(new THREE.BoxGeometry(0.09, 0.27, 0.012), blade);
        const pivot = new THREE.Group();
        b.position.y = 0.145;
        b.rotation.y = 0.5;
        b.userData.live = true;
        pivot.rotation.z = (i / 5) * Math.PI * 2;
        pivot.add(b);
        fan.add(pivot);
      }
      g.add(fan);
      const leds = [];
      for (let i = 0; i < 3; i++) {
        const led = new THREE.MeshStandardMaterial({ color: '#20232a', emissive: '#7dffb0', emissiveIntensity: 0 });
        const m = at(box(0.05, 0.05, 0.012, led, { r: 0 }), cx + 0.34, 1.02 + i * 0.14, cz + 0.205);
        m.userData.live = true;
        g.add(m);
        leds.push(led);
      }
      const COUNT = 42;
      const air = new THREE.InstancedMesh(
        new THREE.BoxGeometry(0.014, 0.014, 0.3),
        new THREE.MeshBasicMaterial({ color: '#ffffff', transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false }),
        COUNT,
      );
      air.frustumCulled = false;
      air.visible = false;
      air.userData.live = true;
      air.setColorAt(0, new THREE.Color('#000'));
      g.add(air);
      const seeds = Array.from({ length: COUNT }, (_, i) => ({ phase: (i * 0.618034) % 1, u: ((i * 0.381966) % 1) * 2 - 1, v: ((i * 0.7548) % 1) * 2 - 1, speed: 0.8 + ((i * 0.569) % 1) * 0.5 }));
      const dummy = new THREE.Object3D();
      const tint = new THREE.Color();
      room.live = {
        busy: false, online: false, clock: 0,
        set(info) {
          this.busy = !!info.running;
          this.online = !!info.online;
          air.visible = this.busy;
          screen.emissive.set(this.busy ? WARM : this.online ? '#3a4a6b' : '#000000');
          screen.emissiveIntensity = this.busy ? 1.8 : 0.4;
          leds.forEach((led) => { led.emissiveIntensity = this.online || this.busy ? 0.8 : 0; });
          if (!this.busy) fan.rotation.z = 0.3;
        },
        tick(dt) {
          this.clock += dt;
          fan.rotation.z -= dt * 9;
          leds.forEach((led, i) => { led.emissiveIntensity = Math.sin(this.clock * (5 + i * 2.3) + i) > 0 ? 3 : 0.25; });
          seeds.forEach((seed, i) => {
            const t = (seed.phase + this.clock * 0.42 * seed.speed) % 1;
            const reach = 2.9 * t;
            dummy.position.set(ring.position.x + seed.u * (0.2 + 0.5 * t), ring.position.y + seed.v * (0.2 + 0.32 * t) - 0.5 * t * t, ring.position.z + 0.15 + reach);
            dummy.updateMatrix();
            air.setMatrixAt(i, dummy.matrix);
            const fade = Math.pow(Math.sin(Math.PI * t), 0.7) * 0.75;
            air.setColorAt(i, tint.setRGB(fade, fade * 0.85, fade * 0.66));
          });
          air.instanceMatrix.needsUpdate = true;
          if (air.instanceColor) air.instanceColor.needsUpdate = true;
        },
      };
    },
    fill(g, info, ctx) {
      ctx.object({ x: W / 2, y: 0, z: 1, w: 3.2, h: 1.7, d: 1, title: info.title, sub: info.sub, href: info.href, mood: info.state });
    },
  },

  library: {
    lamps: { main: [W / 2, 2.05, 2.3], side: [W - 0.75, 1.42, D - 0.7] },
    decor(g, s) {
      g.add(at(piece('rug', { size: [2.6, 1.7], color: '#6b3f34' }), W / 2, 0, 3.05));
      g.add(decal(1.1, 1, W - 1.5, 3.4), at(piece('armchair', { color: '#b5603f' }), W - 1.5, 0, 3.4));
      g.add(decal(1.1, 1, 1.5, 3.4), at(piece('armchair', { color: '#8a5f3c' }), 1.5, 0, 3.4));
      g.add(decal(1.4, 0.9, W / 2, 3.3), at(piece('coffeeTable', { width: 0.9 }), W / 2, 0, 3.3));
    },
    // Shelves of books, one per piece of third-party code. Nothing here fetches or runs any of them.
    fill(g, info, ctx) {
      const list = info.items || [];
      const colors = { Using: '#4f9462', 'Copied from': '#c9553f', Installed: '#3d6b8c', Considered: '#8b93a7', Dropped: '#4a4d55', 'Not looked at': '#d9b98a' };
      const left = bookcase(g, 1.32, 0.3, 2.3, 2.05, 4);
      const right = bookcase(g, 3.68, 0.3, 2.3, 2.05, 4);
      const half = 40;
      const first = list.slice(0, half);
      bookPile(g, 1.32, 0.3, 2.3, left, first, ctx, (b) => colors[b.status] || '#d9b98a', { thick: 0.09 });
      const second = list.slice(half);
      bookPile(g, 3.68, 0.3, 2.3, right, second, ctx, (b) => colors[b.status] || '#d9b98a', { thick: 0.09 });
    },
  },

  /* ---------- any other kind of room: a quiet lounge with nothing filed in it ---------- */

  lounge: {
    lamps: { main: [W / 2, 2.05, 2.2], side: [0.42, 1.42, 0.5] },
    decor(g, s) {
      g.add(at(piece('rug', { size: [2.8, 1.7], color: s.rug }), W / 2, 0, 2.6));
      const sofa = at(piece('sofa', { width: 1.9, color: s.fabric }), W / 2, 0, 3.65);
      sofa.rotation.y = Math.PI;
      g.add(decal(2.5, 1.5, W / 2, 3.65), sofa, decal(1.6, 0.9, W / 2, 2.4), at(piece('coffeeTable', { width: 1.1 }), W / 2, 0, 2.4));
      g.add(decal(0.9, 0.9, W - 0.45, 0.45), at(piece('plant', { height: 1.25 }), W - 0.45, 0, 0.45));
    },
    fill() {},
  },
};
