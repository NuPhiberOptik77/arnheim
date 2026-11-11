// The building in its photo-real look: floors baked by Cycles (studio/blender, `build.py --bake --shell`),
// drawn without lamps, and on them the pieces that come from the company's data, placed live from the
// bake's "slots" and lit by a sun along the same measured direction. A shell carries the walls, floors,
// windows and fixed furniture; the kit (studio/blender/kit_export.py) carries the desks, seats, books,
// crates, boards and screens, with their colours baked so three.js only adds the light.
import * as THREE from '../../vendor/three/three.module.js';

async function fetchBin(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: ${res.status}`);
  return res.arrayBuffer();
}

// A baked floor: one unlit mesh per room group, each room's material its own, so a room can be tinted
// (its mood) or dimmed (the overview's focus) through the material's colour, which multiplies the bake.
export async function loadShell(base, { anisotropy = 4 } = {}) {
  const manifest = await (await fetch(base + 'floor.json', { cache: 'no-cache' })).json();
  const stamp = `?v=${manifest.baked || Date.now()}`;
  const loader = new THREE.TextureLoader();
  const group = new THREE.Group();
  const rooms = new Map();
  for (const g of manifest.groups) {
    const buf = await fetchBin(base + g.bin + stamp);
    const n = g.vertices;
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(buf, 0, n * 3), 3));
    geo.setAttribute('uv', new THREE.BufferAttribute(new Float32Array(buf, n * 12, n * 2), 2));
    geo.setIndex(new THREE.BufferAttribute(new Uint32Array(buf, n * 20, g.indices), 1));
    const map = await loader.loadAsync(base + g.image + stamp);
    map.colorSpace = THREE.SRGBColorSpace;
    map.anisotropy = anisotropy;
    const material = new THREE.MeshBasicMaterial({ map, toneMapped: false }); // the bake went through the photos' view transform already
    const mesh = new THREE.Mesh(geo, material);
    mesh.name = g.name;
    mesh.userData.baked = true;
    group.add(mesh);
    const room = g.name.replace(/ PEOPLE$/, '');
    if (!rooms.has(room)) rooms.set(room, { meshes: [], outline: null });
    rooms.get(room).meshes.push(mesh);
  }
  for (const r of manifest.rooms || []) {
    if (!rooms.has(r.name)) rooms.set(r.name, { meshes: [] });
    rooms.get(r.name).outline = r.polygon; // [x, z] in viewer axes
  }
  if (manifest.glass) {
    const buf = await fetchBin(base + manifest.glass.bin + stamp);
    const n = manifest.glass.vertices;
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(buf, 0, n * 3), 3));
    geo.setIndex(new THREE.BufferAttribute(new Uint32Array(buf, n * 12, manifest.glass.indices), 1));
    group.add(new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: 0xdfe8ec, transparent: true, opacity: 0.07, depthWrite: false, side: THREE.DoubleSide, toneMapped: false })));
  }
  // the view out of the windows, baked from the same sun, shown as the sky
  let sky = null;
  if (manifest.outside) {
    sky = await loader.loadAsync(base + manifest.outside.image + stamp);
    sky.mapping = THREE.EquirectangularReflectionMapping;
    sky.colorSpace = THREE.SRGBColorSpace;
  }
  // a room's light, as a colour over its bake: 1 is as photographed
  function setTint(name, color = 0xffffff, level = 1) {
    const r = rooms.get(name);
    if (!r) return;
    const c = new THREE.Color(color).multiplyScalar(level);
    for (const m of r.meshes) m.material.color.copy(c);
  }
  return { group, rooms, slots: manifest.slots || [], manifest, setTint, sky, ceiling: manifest.floor?.ceiling ?? 3 };
}

// The kit: each piece's parts as meshes sharing one geometry and colour map, cloned per use.
export async function loadKit(base) {
  const kit = await (await fetch(base + 'kit.json', { cache: 'no-cache' })).json();
  const loader = new THREE.TextureLoader();
  const parts = {};
  for (const [name, piece] of Object.entries(kit.pieces)) {
    parts[name] = {};
    for (const [part, p] of Object.entries(piece)) {
      const buf = await fetchBin(base + p.bin);
      const n = p.vertices;
      const inter = new THREE.InterleavedBuffer(new Float32Array(buf, 0, n * 8), 8);
      const geo = new THREE.BufferGeometry();
      geo.setAttribute('position', new THREE.InterleavedBufferAttribute(inter, 3, 0));
      geo.setAttribute('normal', new THREE.InterleavedBufferAttribute(inter, 3, 3));
      geo.setAttribute('uv', new THREE.InterleavedBufferAttribute(inter, 2, 6));
      geo.setIndex(new THREE.BufferAttribute(new Uint32Array(buf, n * 32, p.indices), 1));
      let map = null;
      if (p.image) {
        map = await loader.loadAsync(base + p.image);
        map.colorSpace = THREE.SRGBColorSpace;
      }
      parts[name][part] = { geo, map, box: p.box };
    }
  }
  // one piece, its live parts given their own material (a screen's glow, a page)
  function make(name, { live = {} } = {}) {
    const g = new THREE.Group();
    g.name = name;
    for (const [part, p] of Object.entries(parts[name] || {})) {
      const mat = live[part] || new THREE.MeshStandardMaterial({ map: p.map, roughness: 0.6, metalness: 0 });
      const mesh = new THREE.Mesh(p.geo, mat);
      mesh.castShadow = mesh.receiveShadow = true;
      mesh.name = `${name} ${part}`;
      g.add(mesh);
    }
    return g;
  }
  return { make, parts };
}

// The people (studio/blender/people_export.py): each a body, and a head on a pivot at the top of the neck,
// so they can breathe and look about. Their colours are baked; the live light falls on them like the kit.
async function interleaved(url, p) {
  const buf = await fetchBin(url + p.bin);
  const inter = new THREE.InterleavedBuffer(new Float32Array(buf, 0, p.vertices * 8), 8);
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.InterleavedBufferAttribute(inter, 3, 0));
  geo.setAttribute('normal', new THREE.InterleavedBufferAttribute(inter, 3, 3));
  geo.setAttribute('uv', new THREE.InterleavedBufferAttribute(inter, 2, 6));
  geo.setIndex(new THREE.BufferAttribute(new Uint32Array(buf, p.vertices * 32, p.indices), 1));
  return geo;
}

export async function loadPeople(base) {
  const list = await (await fetch(base + 'people.json', { cache: 'no-cache' })).json();
  const loader = new THREE.TextureLoader();
  const people = {};
  await Promise.all(Object.entries(list.people).map(async ([name, e]) => {
    const part = async (p) => {
      if (!p) return null;
      const [geo, map] = await Promise.all([interleaved(base, p), loader.loadAsync(base + p.image)]);
      map.colorSpace = THREE.SRGBColorSpace;
      map.anisotropy = 4;
      return { geo, material: new THREE.MeshStandardMaterial({ map, roughness: 0.72, metalness: 0 }) };
    };
    const [body, head] = await Promise.all([part(e.body), part(e.head)]);
    people[name] = { body, head, pivot: e.pivot, kind: e.kind };
  }));
  // someone, with tick(t) to breathe and look about a little (as buildPerson's people do)
  function make(name, { seed = 0 } = {}) {
    const e = people[name];
    if (!e) return null;
    const group = new THREE.Group();
    const torso = new THREE.Group();
    group.add(torso);
    torso.add(new THREE.Mesh(e.body.geo, e.body.material));
    const neck = new THREE.Group();
    neck.position.set(...e.pivot);
    torso.add(neck);
    if (e.head) neck.add(new THREE.Mesh(e.head.geo, e.head.material));
    group.traverse((o) => { if (o.isMesh) o.userData.keep = true; }); // shared shapes: never let go of with a room's pieces
    const phase = (seed % 1000) / 159;
    return {
      group, neck, look: 0,
      tick(t) {
        torso.scale.y = 1 + 0.0035 * Math.sin(t * 1.3 + phase);
        neck.rotation.y = this.look + Math.sin(t * 0.37 + phase) * 0.12;
        neck.rotation.x = Math.sin(t * 0.23 + phase * 2) * 0.035;
      },
    };
  }
  return { make, has: (name) => !!people[name], names: Object.keys(people) };
}

// The light the live pieces stand in: the sky from above, the bounce from the floor, and the sun along the
// direction the floors were baked with (plan [x, y, z] -> viewer [x, z, -y]).
export function sunLight(sunPlan, { strength = 2.2, sky = 1.1 } = {}) {
  const g = new THREE.Group();
  g.add(new THREE.HemisphereLight(0xf3efe8, 0xb9ad9c, sky));
  const d = new THREE.Vector3(sunPlan[0], sunPlan[2], -sunPlan[1]).normalize();
  const sun = new THREE.DirectionalLight(0xfff1de, strength);
  sun.position.copy(d.multiplyScalar(40));
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  Object.assign(sun.shadow.camera, { left: -16, right: 16, top: 16, bottom: -16, near: 1, far: 90 });
  sun.shadow.bias = -0.0004;
  g.add(sun, sun.target);
  return g;
}

/* ---------- what comes from the data, room by room ---------- */

const AMBER = new THREE.Color('#ffb347');
const WARM = new THREE.Color('#ffe2bd');
const COOL = new THREE.Color('#8fb4ff');
const FAIL = new THREE.Color('#ff5a6e');
const DARK = '#1f1d1b';

function standard(color, extra = {}) {
  return new THREE.MeshStandardMaterial({ color, roughness: 0.7, metalness: 0, ...extra });
}

function screenMaterial(mood) {
  const lit = mood === 'needs' ? AMBER : mood === 'working' ? WARM : mood === 'failed' ? FAIL : null;
  return standard(lit || 0x0b0c0d, { emissive: lit || 0x000000, emissiveIntensity: lit ? 1.4 : 0, roughness: 0.08 });
}

function canvasPlane(w, h, draw, px = 512) {
  const c = document.createElement('canvas');
  c.width = px;
  c.height = Math.round((px * h) / w);
  draw(c.getContext('2d'), c.width, c.height);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  return new THREE.Mesh(new THREE.PlaneGeometry(w, h), standard(0xffffff, { map: tex }));
}

// a soft shadow or a pool of light on the floor under a piece
let softTexture = null;
function soft() {
  if (softTexture) return softTexture;
  const c = document.createElement('canvas');
  c.width = c.height = 64;
  const g = c.getContext('2d');
  const r = g.createRadialGradient(32, 32, 2, 32, 32, 31);
  r.addColorStop(0, 'rgba(255,255,255,1)');
  r.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = r;
  g.fillRect(0, 0, 64, 64);
  softTexture = new THREE.CanvasTexture(c);
  return softTexture;
}
function pool(w, d, { color = '#000000', opacity = 0.3, add = false, y = 0.006 } = {}) {
  const geo = new THREE.PlaneGeometry(w, d);
  geo.rotateX(-Math.PI / 2);
  const m = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ map: soft(), color, opacity, transparent: true, depthWrite: false, toneMapped: false, blending: add ? THREE.AdditiveBlending : THREE.NormalBlending }));
  m.position.y = y;
  m.renderOrder = 1;
  return m;
}

// the same few numbers for the same thing every time, so a desk keeps its mug and lamp from one visit to the next
function seeded(n) {
  let a = (n * 2654435761) >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
export function identity(id) {
  let n = 2166136261;
  for (const ch of String(id)) n = Math.imul(n ^ ch.charCodeAt(0), 16777619);
  return n >>> 0;
}

function tinted(kit, name, colour) {
  const g = kit.make(name);
  for (const m of g.children) m.material.color.set(colour);
  return g;
}

// the library's books, by where each piece of third-party code stands
const SHELF_COLOURS = { using: '#2F5A44', 'copied from': '#2D4A6B', considered: '#B08A3E', dropped: '#6B2B26', 'not looked at': '#D8CBB5' };

const MUGS = ['#E9E2D6', '#2E2D2B', '#B9653E'];
const NOTEBOOKS = ['#2F3B36', '#C9B79C', '#8C5A3C'];

// what stands on a desk in use, in the desk's own frame (x along the desk, +z towards the sitter)
function deskThings(kit, n) {
  const r = seeded(n);
  const things = [];
  const put = (g, x, z, turn = 0) => { g.position.set(x, 0.74, z); g.rotation.y = turn; things.push(g); };
  const what = r();
  if (what < 0.4) put(tinted(kit, 'mug', MUGS[Math.floor(r() * 3)]), 0.5, 0.02);
  else if (what < 0.7) put(tinted(kit, 'notebook', NOTEBOOKS[Math.floor(r() * 3)]), 0.45, 0.05, (r() - 0.5) * 0.8);
  else put(kit.make('desk lamp'), 0.6, -0.15, Math.PI / 2);
  if (what < 0.4) put(tinted(kit, 'notebook', NOTEBOOKS[Math.floor(r() * 3)]), 0.42, 0.22, (r() - 0.5) * 0.8);
  else put(tinted(kit, 'mug', MUGS[Math.floor(r() * 3)]), 0.32, 0.26);
  if (r() < 0.4) put(kit.make('laptop'), -0.55, 0.1, (r() - 0.5) * 0.4);
  return things;
}

// a point in a slot's own frame (x across it, z out of its face), in the floor's coordinates
function along(slot, dx, dy, dz) {
  const c = Math.cos(slot.rot);
  const s = Math.sin(slot.rot);
  return [slot.at[0] + dx * c + dz * s, slot.at[1] + dy, slot.at[2] - dx * s + dz * c];
}
const put = (m, x, y, z) => { m.position.set(x, y, z); return m; };
const placed = (g, slot, [x, y, z] = slot.at) => { g.position.set(x, y, z); g.rotation.y = slot.rot; return g; };
const shown = (list, cap) => (list.length > cap ? list.slice(0, cap - 1) : list);

// The fillers: each puts a room's live pieces into g from its slots and its live data (info, as
// building.js has always had it), and tells ctx what can be tapped (ctx.object) and how many more there
// are than fit (ctx.more). Everything is in the floor's coordinates. box is the room's outline's bounds.
export const FILL = {
  goals({ g, slots, info, ctx, box }) {
    const list = info.items || [];
    const s = slots.find((x) => x.kind === 'goals') || { at: [(box.x0 + box.x1) / 2, 1.55, box.z0 + 0.03], rot: 0, w: 1.3, h: 1.0, synthetic: true };
    const goals = shown(list, 6);
    goals.forEach((goal, k) => {
      const card = canvasPlane(0.3, 0.38, (c, w, h) => {
        c.fillStyle = '#f7f4ee';
        c.fillRect(0, 0, w, h);
        c.fillStyle = goal.reached ? '#d4a72c' : '#b4432e';
        c.fillRect(w * 0.12, h * 0.1, w * 0.3, h * 0.2);
        c.fillStyle = '#2b2a28';
        c.font = `${Math.round(w * 0.1)}px Georgia, serif`;
        let line = '';
        let y = h * 0.45;
        for (const word of String(goal.title || '').split(/\s+/)) {
          if (c.measureText(`${line} ${word}`).width > w * 0.8 && line) { c.fillText(line, w * 0.1, y); line = word; y += w * 0.13; } else line = `${line} ${word}`.trim();
        }
        c.fillText(line, w * 0.1, y);
      });
      const cols = Math.min(goals.length, 3);
      const dx = -s.w / 2 + (s.w * ((k % 3) + 0.5)) / cols;
      const dy = goals.length > 3 ? (k < 3 ? 0.22 : -0.24) : 0;
      const p = along(s, dx, dy, 0.025);
      placed(card, s, p);
      g.add(card);
      ctx.object({ x: p[0], y: p[1] - 0.2, z: p[2] + 0.1, w: 0.34, h: 0.42, d: 0.2, title: goal.title, sub: goal.sub, href: goal.href });
    });
    if (list.length > goals.length) ctx.more(list.length - goals.length, ...along(s, s.w / 2 - 0.1, -0.5, 0.1));
  },

  work({ g, slots, info, ctx, kit }) {
    const list = info.items || [];
    const middleOut = (c) => [1, 0, 2, 3, 4][c] ?? c; // the middle cluster first, so a few desks don't huddle in a corner
    const desks = slots.filter((x) => x.kind === 'desk').sort((a, b) => middleOut(a.cluster) - middleOut(b.cluster) || a.row - b.row || a.side - b.side);
    const tasks = shown(list, desks.length);
    tasks.forEach((task, i) => {
      const s = desks[i];
      const unit = new THREE.Group();
      const body = kit.make('desk');
      body.rotation.y = Math.PI;
      const screen = kit.make('monitor', { live: { screen: screenMaterial(task.mood) } });
      screen.position.set(0, 0.74, -0.2);
      const chair = kit.make('desk chair');
      chair.position.set(0, 0, 0.5);
      chair.rotation.y = Math.PI;
      unit.add(body, screen, chair, pool(1.9, 1.1, { opacity: 0.22 }), ...deskThings(kit, identity(task.id ?? task.title)));
      if (task.mood === 'needs' || task.mood === 'working') unit.add(pool(1.7, 1.4, { color: task.mood === 'needs' ? AMBER : WARM, opacity: 0.3, add: true, y: 0.008 }));
      let figure = null;
      if (task.mood === 'working' && ctx.seated) {
        const person = ctx.seated(identity(task.id ?? task.title), { seat: 0.5, pose: 'desk' });
        person.position.set(0, 0, 0.48);
        person.rotation.y = Math.PI; // facing the screen
        unit.add(person);
      }
      // the desk's long side runs along the slot; the sitter is on the chair's side
      const [cx, cz] = [s.chair[0], -s.chair[1]];
      unit.position.set(s.at[0], 0, s.at[2]);
      unit.rotation.y = Math.atan2(-(s.at[0] - cx), -(s.at[2] - cz));
      g.add(unit);
      if (task.mood === 'working') { // stand a little out from the chair and to one side, to talk to them
        const len = Math.hypot(cx - s.at[0], cz - s.at[2]) || 1;
        const out = [(cx - s.at[0]) / len, (cz - s.at[2]) / len];
        figure = { x: cx, z: cz, stand: [cx + out[0] * 0.55 - out[1] * 0.75, cz + out[1] * 0.55 + out[0] * 0.75] };
      }
      ctx.object({ x: s.at[0], y: 0, z: s.at[2], w: 1.2, h: 1.15, d: 1.2, title: task.title, sub: task.sub, href: task.href, mood: task.mood, figure });
    });
    if (list.length > tasks.length) {
      const s = desks[desks.length - 1];
      ctx.more(list.length - tasks.length, s.at[0], 1.3, s.at[2]);
    }
  },

  conversations({ g, slots, info, ctx, kit }) {
    const list = info.items || [];
    const seats = slots.filter((x) => x.kind === 'seat');
    // the table's ends first, then along its sides
    const order = [...seats].sort((a, b) => Math.abs(a.seat[0] - 1) - Math.abs(b.seat[0] - 1) || a.seat[0] - b.seat[0]).reverse();
    const talks = shown(list, order.length);
    talks.forEach((c, i) => {
      const s = order[i];
      const seat = placed(kit.make('seat'), { ...s, at: [s.at[0], 0, s.at[2]] });
      g.add(seat);
      const tableZ = -s.table[1];
      if (c.working || c.check) {
        const person = ctx.seated?.(identity(c.id), { seat: 0.46, pose: 'chat' });
        if (person) { person.position.copy(seat.position); person.rotation.y = s.rot; g.add(person); }
      }
      if (c.working) { const p = pool(1.3, 1.3, { color: WARM, opacity: 0.3, add: true }); p.position.x = s.at[0]; p.position.z = s.at[2]; g.add(p); }
      if (c.check) {
        const light = new THREE.Mesh(new THREE.SphereGeometry(0.04, 12, 8), standard(COOL, { emissive: COOL, emissiveIntensity: 2.4 }));
        light.position.set(...along({ ...s, at: [s.at[0], 0, s.at[2]] }, 0, 0.98, -0.24));
        g.add(light);
      }
      const stand = [s.at[0] + (s.table[0] - s.at[0]) * 0.1, s.at[2] + (s.at[2] > tableZ ? 0.55 : -0.55)];
      ctx.object({ x: s.at[0], y: 0, z: s.at[2], w: 0.7, h: 1.05, d: 0.7, title: c.title, sub: c.sub, href: c.href, mood: c.working ? 'working' : c.check ? 'check' : 'quiet',
        figure: c.working || c.check ? { x: s.at[0], z: s.at[2], stand } : null });
    });
    if (list.length > talks.length) ctx.more(list.length - talks.length, seats[0].table[0], 1.0, -seats[0].table[1]);
  },

  code({ g, slots, info, ctx, kit }) {
    const prs = info.prs || [];
    let left = prs.slice();
    const colours = (p) => p.colour || (p.draft ? '#8B93A7' : ['#3E6B4F', '#2F4A3A', '#4F7A5C'][identity(p.id ?? p.title) % 3]);
    for (const s of slots.filter((x) => x.kind === 'shelves')) {
      const unit = placed(kit.make('bookcase'), s);
      g.add(unit);
      const t = 0.025;
      const order = [...Array(s.rows).keys()].sort((a, b) => Math.abs(a - s.rows / 2) - Math.abs(b - s.rows / 2)); // eye level first
      for (const j of order) {
        for (let c = 0; c < s.cols && left.length; c++) {
          let x = -s.w / 2 + (s.w * c) / s.cols + t + 0.01;
          const x1 = -s.w / 2 + (s.w * (c + 1)) / s.cols - t;
          while (x < x1 - 0.04 && left.length) {
            const pr = left.shift();
            const b = tinted(kit, 'book', colours(pr));
            const y = (j * (s.h - t)) / s.rows + t;
            b.position.set(x + 0.015, y, -(s.d / 2) - 0.02);
            b.scale.y = 0.9 + (identity(pr.id ?? pr.title) % 7) * 0.03;
            unit.add(b);
            const p = along(s, x + 0.015, y, -(s.d / 2) + 0.1);
            ctx.object({ x: p[0], y: p[1], z: p[2], w: 0.06, h: 0.26, d: 0.3, title: pr.title, sub: pr.sub, href: pr.href, mood: pr.mood });
            x += 0.036;
          }
        }
      }
    }
    if (left.length) {
      const s = slots.find((x) => x.kind === 'shelves');
      if (s) ctx.more(left.length, ...along(s, 0, 2.0, 0.1));
    }
    const copies = info.copies || [];
    const crateRow = slots.find((x) => x.kind === 'crate' && x.row);
    const kept = shown(copies, 6);
    kept.forEach((c, i) => {
      if (!crateRow) return;
      const crate = kit.make('crate');
      const x = crateRow.row[0] + 0.25 + (i % 3) * 0.52;
      crate.position.set(x, i >= 3 ? 0.29 : 0, crateRow.at[2]);
      crate.rotation.y = crateRow.rot + (i % 2 ? -0.06 : 0.05);
      g.add(crate, put(pool(0.7, 0.55, { opacity: 0.25 }), x, 0.006, crateRow.at[2]));
      ctx.object({ x, y: i >= 3 ? 0.29 : 0, z: crateRow.at[2], w: 0.5, h: 0.32, d: 0.36, title: c.title, sub: c.sub, href: c.href });
    });
    if (crateRow && copies.length > kept.length) ctx.more(copies.length - kept.length, crateRow.row[1], 0.8, crateRow.at[2]);
  },

  websites({ g, slots, info, ctx, kit, company }) {
    for (const s of slots.filter((x) => x.kind === 'sign')) {
      const [bw, bh] = s.band || [3.4, 0.56];
      const sign = canvasPlane(bw - 0.1, bh - 0.06, (c, w, h) => {
        c.fillStyle = '#24211e';
        c.fillRect(0, 0, w, h);
        c.fillStyle = s.color || '#c9a46a';
        c.textAlign = 'center';
        c.font = `${Math.round(h * 0.42)}px "Gill Sans", "Helvetica Neue", sans-serif`;
        c.fillText(String(company.name || '').toUpperCase().split('').join(String.fromCharCode(8202)), w / 2, h * 0.55);
        if (company.mission) {
          c.font = `${Math.round(h * 0.2)}px "Gill Sans", "Helvetica Neue", sans-serif`;
          c.fillText(company.mission, w / 2, h * 0.86);
        }
      }, 1024);
      placed(sign, s, [s.at[0], (s.band_z ?? 2.42) + bh / 2, s.at[2] + 0.002]);
      g.add(sign);
    }
    const list = info.items || [];
    const row = slots.find((x) => x.kind === 'screens');
    const sites = shown(list, 4);
    if (row) {
      sites.forEach((site, k) => {
        const page = canvasPlane(row.w, row.h, (c, w, h) => {
          const on = site.up || site.live;
          c.fillStyle = site.mood === 'failed' ? '#3a1216' : on ? '#f4f1ea' : '#0b0c0d';
          c.fillRect(0, 0, w, h);
          if (!on && site.mood !== 'failed') return;
          c.fillStyle = site.mood === 'failed' ? '#ff8a96' : '#22201e';
          c.fillRect(0, 0, w, h * 0.1);
          c.fillStyle = site.mood === 'failed' ? '#ffd4d9' : '#2a2724';
          c.font = `${Math.round(h * 0.08)}px Georgia, serif`;
          c.fillText(site.title || '', w * 0.06, h * 0.32);
          if (site.mood !== 'failed') { c.fillStyle = '#5b6b5a'; c.fillRect(w * 0.52, h * 0.16, w * 0.44, h * 0.72); }
        });
        const on = site.up || site.live || site.mood === 'failed';
        page.material.emissive = new THREE.Color(on ? 0xffffff : 0x000000);
        page.material.emissiveMap = page.material.map;
        page.material.emissiveIntensity = on ? 0.5 : 0;
        const unit = kit.make('website screen');
        unit.add(page);
        page.position.set(0, row.h / 2, 0.027);
        const [mx, my] = row.middle;
        const x = mx + (k - (sites.length - 1) / 2) * (row.w + row.gap);
        unit.position.set(x, 1.62, -my);
        unit.rotation.y = row.rot;
        g.add(unit);
        ctx.object({ x, y: 1.62, z: -my + 0.1, w: row.w, h: row.h, d: 0.2, title: site.title, sub: site.sub, href: site.href, mood: site.mood });
      });
      if (list.length > sites.length) ctx.more(list.length - sites.length, row.middle[0] + row.row_w / 2, 2.3, -row.middle[1]);
    }
  },

  company({ g, slots, info, ctx, kit, box }) {
    const list = info.sections || [];
    // the bake's run of cabinets on the side wall first, then a row along the back wall
    const run = slots.filter((x) => x.kind === 'cabinet').sort((a, b) => a.k - b.k);
    list.forEach((section, i) => {
      const s = run[i] || { at: [(box.x0 + box.x1) / 2 + (i - run.length - (list.length - run.length - 1) / 2) * 0.7, 0, box.z0 + 0.32], rot: 0 };
      const cab = placed(kit.make('filing cabinet'), { ...s, at: [s.at[0], 0, s.at[2]] });
      g.add(cab, put(pool(0.9, 0.8, { opacity: 0.25 }), s.at[0], 0.006, s.at[2]));
      const folders = ['#d9a441', '#b5603f', '#4c7595'];
      for (let k = 0; k < Math.min(section.count || 0, 6); k++) {
        const f = new THREE.Mesh(new THREE.BoxGeometry(0.34, 0.018, 0.25), standard(folders[k % 3], { roughness: 0.9 }));
        f.position.set(s.at[0], 1.03 + k * 0.02, s.at[2]);
        f.rotation.y = s.rot;
        g.add(f);
      }
      const [x, , z] = along({ ...s, at: [s.at[0], 0, s.at[2]] }, 0, 0, 0.1);
      ctx.object({ x, y: 0, z, w: 0.62, h: 1.1, d: 0.6, title: section.title, sub: section.sub, href: section.href });
    });
  },

  // Rooms the bake has no live pieces for yet: plain pieces, in the same light, along the back wall.
  email({ g, info, ctx, box }) {
    const wood = standard('#6e5238', { roughness: 0.65 });
    const hole = standard('#241c15', { roughness: 1 });
    const cx = (box.x0 + box.x1) / 2;
    const z = box.z0 + 0.2;
    const unit = new THREE.Mesh(new THREE.BoxGeometry(3, 1.7, 0.36), wood);
    unit.position.set(cx, 0.85, z);
    g.add(unit, put(pool(3.6, 1.0, { opacity: 0.25 }), cx, 0.006, z + 0.1));
    for (let r = 0; r < 3; r++) for (let c = 0; c < 5; c++) {
      const m = new THREE.Mesh(new THREE.BoxGeometry(0.48, 0.38, 0.02), hole);
      m.position.set(cx - 1.14 + c * 0.57, 0.39 + r * 0.5, z + 0.18);
      g.add(m);
    }
    const list = info.items || [];
    list.slice(0, 15).forEach((entry, i) => {
      const x = cx - 1.14 + (i % 5) * 0.57;
      const y = 1.39 - Math.floor(i / 5) * 0.5;
      const plate = new THREE.Mesh(new THREE.BoxGeometry(0.26, 0.07, 0.01), standard('#c9a15e', { roughness: 0.35, metalness: 0.7, emissive: WARM, emissiveIntensity: 0.4 }));
      plate.position.set(x, y + 0.17, z + 0.195);
      g.add(plate);
      ctx.object({ x, y: y - 0.2, z: z + 0.25, w: 0.5, h: 0.4, d: 0.15, title: entry.title, sub: entry.sub, href: entry.href });
    });
    if (list.length > 15) ctx.more(list.length - 15, cx, 1.9, z);
  },

  social({ g, info, ctx, box }) {
    const list = info.items || [];
    const signs = shown(list, 6);
    const dark = standard(DARK, { roughness: 0.5 });
    signs.forEach((entry, i) => {
      const x = box.x0 + ((box.x1 - box.x0) * ((i % 3) + 0.5)) / 3;
      const z = box.z0 + (i < 3 ? 1.2 : 2.6);
      const post = new THREE.Group();
      const foot = new THREE.Mesh(new THREE.BoxGeometry(0.42, 0.03, 0.28), dark);
      foot.position.y = 0.015;
      const pole = new THREE.Mesh(new THREE.BoxGeometry(0.04, 1.05, 0.04), dark);
      pole.position.y = 0.55;
      const face = canvasPlane(0.9, 0.36, (c, w, h) => {
        c.fillStyle = entry.live ? '#f3ede2' : '#1c1f26';
        c.fillRect(0, 0, w, h);
        c.fillStyle = entry.live ? '#2a2724' : '#6d717b';
        c.font = `${Math.round(h * 0.3)}px "Gill Sans", "Helvetica Neue", sans-serif`;
        c.textAlign = 'center';
        c.fillText(entry.title || '', w / 2, h * 0.6);
      });
      face.position.set(0, 1.27, 0.022);
      if (entry.live) { face.material.emissive = new THREE.Color(0xffffff); face.material.emissiveMap = face.material.map; face.material.emissiveIntensity = 0.35; }
      const board = new THREE.Mesh(new THREE.BoxGeometry(0.98, 0.42, 0.04), standard('#2b2f3a', { roughness: 0.6 }));
      board.position.y = 1.27;
      post.add(foot, pole, board, face, pool(1.1, 0.6, { opacity: 0.22 }));
      post.position.set(x, 0, z);
      g.add(post);
      ctx.object({ x, y: 0, z, w: 1.05, h: 1.5, d: 0.4, title: entry.title, sub: entry.sub, href: entry.href });
    });
    if (list.length > signs.length) ctx.more(list.length - signs.length, box.x1 - 0.8, 1.6, box.z0 + 2.6);
  },

  domains({ g, info, ctx, box }) {
    const cx = (box.x0 + box.x1) / 2;
    const z = box.z0 + 0.04;
    const panel = new THREE.Mesh(new THREE.BoxGeometry(3, 1.5, 0.05), standard('#7c5a3c', { roughness: 0.6 }));
    panel.position.set(cx, 1.11, z);
    g.add(panel);
    const list = info.items || [];
    const plaques = shown(list, 6);
    plaques.forEach((entry, i) => {
      const x = cx - 0.72 + (i % 2) * 1.44;
      const y = 1.58 - Math.floor(i / 2) * 0.46;
      const plaque = canvasPlane(1.2, 0.32, (c, w, h) => {
        c.fillStyle = entry.live ? '#c9a15e' : '#6f6556';
        c.fillRect(0, 0, w, h);
        c.fillStyle = entry.live ? '#2a1f12' : '#2b2722';
        c.font = `${Math.round(h * 0.34)}px Georgia, serif`;
        c.textAlign = 'center';
        c.fillText(entry.title || '', w / 2, h * 0.62);
      });
      plaque.material.metalness = entry.live ? 0.5 : 0.2;
      plaque.position.set(x, y, z + 0.03);
      g.add(plaque);
      ctx.object({ x, y: y - 0.16, z: z + 0.1, w: 1.25, h: 0.36, d: 0.15, title: entry.title, sub: entry.sub, href: entry.href });
    });
    if (list.length > plaques.length) ctx.more(list.length - plaques.length, cx, 0.6, z + 0.1);
  },

  // A shared machine: on a baked basement, its rack where the bake left room for it, the status lights on each
  // server green while it is on and amber while a job runs; before the basement is baked, a plain rack.
  machine({ g, slots, info, ctx, kit, box }) {
    const s = slots?.find((x) => x.kind === 'machine');
    if (s && kit) {
      const lit = info.running ? AMBER : info.online ? new THREE.Color('#7fd492') : null;
      const lights = standard(lit || '#3a3d44', lit ? { emissive: lit, emissiveIntensity: 2.2, roughness: 0.3 } : { roughness: 0.3 });
      const rack = placed(kit.make('server rack', { live: { lights } }), s);
      g.add(rack);
      if (lit) g.add(put(pool(1.6, 1.6, { color: lit, opacity: 0.18, add: true }), ...along(s, 0, 0.007, -0.9)));
      const p = along(s, 0, 0, 0);
      ctx.object({ x: p[0], y: 0, z: p[2], w: 1.1, h: 2.0, d: 1.1, title: info.title, sub: info.sub, href: info.href, mood: info.state });
      return;
    }
    const cx = (box.x0 + box.x1) / 2;
    const cz = (box.z0 + box.z1) / 2;
    const rack = new THREE.Mesh(new THREE.BoxGeometry(0.7, 1.9, 1.0), standard('#2a2d33', { roughness: 0.5, metalness: 0.3 }));
    rack.position.set(cx, 0.95, cz);
    const lit = info.running ? AMBER : info.online ? new THREE.Color('#7fd492') : null;
    const led = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.04, 0.01), standard(lit || '#3a3d44', lit ? { emissive: lit, emissiveIntensity: 1.6 } : {}));
    led.position.set(cx, 1.6, cz + 0.505);
    g.add(rack, led, put(pool(1.2, 1.5, { opacity: 0.3 }), cx, 0.006, cz));
    ctx.object({ x: cx, y: 0, z: cz, w: 1.2, h: 1.9, d: 1.2, title: info.title, sub: info.sub, href: info.href, mood: info.state });
  },

  // The library: a book for each piece of third-party code, coloured by where it stands (in use, copied from,
  // considered, dropped, not looked at yet), on the baked library's shelves or, before that, on one bookcase.
  library({ g, slots, info, ctx, kit, box }) {
    const list = info.items || [];
    const shelves = slots?.filter((x) => x.kind === 'shelves') || [];
    const cx = (box.x0 + box.x1) / 2;
    const use = shelves.length ? shelves : [{ at: [cx, 0, box.z0 + 0.2], rot: 0, w: 1.5, h: 2.4, d: 0.34, cols: 2, rows: 6, kind: 'shelves' }];
    const colour = (b) => SHELF_COLOURS[String(b.status || '').toLowerCase()] || null;
    FILL.code({ g, slots: use, info: { prs: list.map((b) => ({ ...b, draft: false, colour: colour(b) })) }, ctx, kit });
  },

  lounge() {},
};
