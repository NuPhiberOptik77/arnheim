// Walking the building in first person. The building lends its scene, camera and floors; this
// adds the halls (three/halls.js), the controls on the page, the lift and the burn between floors
// (three/burn.js), and gives everything back when the walk ends. It loads only when someone walks.
import * as THREE from '../vendor/three/three.module.js';
import { ShaderPass } from '../vendor/three/addons/postprocessing/ShaderPass.js';
import { createBurn } from './three/burn.js';
import { buildHall, buildPenthouse } from './three/halls.js';
import { dressHall, loadPhoto, photoWanted } from './three/photo.js';
import { createWalkNotes } from './walk-notes.js';
import { D, H, W } from './three/rooms.js';
import { createVoice } from './voice.js';

const EYE = 1.62;
const WALK = 1.5; // metres a second
const RUN = 3;
const RADIUS = 0.22; // how close you can come to a wall
const CELL = 0.2; // the floor plan that stops you is drawn in squares this size
const STRIDE = 0.74;
const QUIET_MS = 4000; // the hand-held drift fades this long after the last touch
const CURB = 0.14;
const SHUTTER = 1 / 160; // seconds: the motion blur is what a phone's shutter would catch
const MOVES = new Set(['KeyW', 'KeyA', 'KeyS', 'KeyD', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'ShiftLeft', 'ShiftRight']);

// The look of phone footage, drawn last: a little motion blur as the camera turns, softer
// corners, a faint vignette and fine grain that is stronger in the shadows. Kept subtle, and
// off for anyone who asks for reduced motion.
const FOOTAGE = {
  uniforms: {
    tDiffuse: { value: null }, uVel: { value: new THREE.Vector2() }, uRes: { value: new THREE.Vector2(1, 1) },
    uTime: { value: 0 }, uGrain: { value: 1 }, uSoft: { value: 1 },
  },
  vertexShader: /* glsl */ `
varying vec2 vUv;
void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
  fragmentShader: /* glsl */ `
uniform sampler2D tDiffuse;
uniform vec2 uVel;
uniform vec2 uRes;
uniform float uTime;
uniform float uGrain;
uniform float uSoft;
varying vec2 vUv;
float hash(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
void main() {
  vec2 c = vUv - 0.5;
  float edge = dot(c, c) * 2.0;
  vec4 sum = vec4(0.0);
  for (int i = 0; i < 7; i++) {
    float t = float(i) / 6.0 - 0.5;
    sum += texture2D(tDiffuse, vUv + uVel * t + c * (edge * uSoft * 0.012 * t));
  }
  vec4 col = sum / 7.0;
  float n = hash(floor(vUv * uRes) + fract(uTime * 7.31) * 113.0) - 0.5;
  float luma = dot(col.rgb, vec3(0.299, 0.587, 0.114));
  col.rgb += n * uGrain * (0.045 - 0.025 * luma);
  col.rgb *= 1.0 - edge * 0.16;
  gl_FragColor = col;
}`,
};

// The walk's look lives in walk.css, added as a stylesheet link rather than a <style> tag, so a page
// whose content security policy allows only its own files (style-src 'self') takes it too. Resolves
// once it has loaded, or failed (the walk still works, plainly), or after four seconds.
// Starts the real materials loading before the walk shows, so it can open on the finished rooms.
// Returns null when this device keeps the drawn ones (photo.js decides).
export function preparePhoto(renderer) {
  if (!photoWanted(renderer)) return null;
  const job = { value: null, failed: false, k: 0, listen: null };
  job.promise = loadPhoto(renderer, (k) => { job.k = k; job.listen?.(k); }).then(
    (p) => { job.value = p; return p; },
    (error) => { job.failed = true; throw error; },
  );
  job.promise.catch(() => {}); // the walk reports a failure itself
  return job;
}

let styled = null;
export function loadStyle() {
  if (styled) return styled;
  const link = document.createElement('link');
  link.id = 'arnheim-walk-style';
  link.rel = 'stylesheet';
  link.href = new URL('./walk.css', import.meta.url).href;
  styled = new Promise((resolve) => {
    link.addEventListener('load', resolve, { once: true });
    link.addEventListener('error', resolve, { once: true });
    setTimeout(resolve, 4000);
  });
  document.head.append(link);
  return styled;
}

export function createWalk(ctx) {
  const { scene, camera, canvas, renderer, storeys, reduced } = ctx;
  const stage = canvas.parentElement;
  const coarse = window.matchMedia('(pointer: coarse)').matches;
  const still = () => reduced.matches;
  const listeners = new AbortController();
  const { signal } = listeners;
  const burn = createBurn(scene, { count: coarse || stage.clientWidth < 820 ? 20000 : 46000 });
  const footage = new ShaderPass(FOOTAGE);
  footage.enabled = !still();
  ctx.composer.addPass(footage);
  const px = new THREE.Vector2();
  let lastYaw = 0;
  let lastPitch = 0;
  // The real materials (photo.js): they start loading as the walk begins, unless this device
  // should keep it light; until they arrive, and if they never do, the drawn ones stand.
  const job = ctx.photo || null; // started by preparePhoto before the walk showed
  let photo = job?.value || null;
  let photoState = !job ? 'off' : photo ? 'on' : job.failed ? 'failed' : 'loading';
  let loadTimer = 0;
  let gone = false;
  const hitMaterial = new THREE.MeshBasicMaterial();
  const halls = new Map();
  const ray = new THREE.Raycaster();
  const ndc = new THREE.Vector2();
  const v = new THREE.Vector3();
  const ahead = new THREE.Vector3();
  const order = [...storeys].sort((a, b) => b.y - a.y); // top floor first
  // The founder's office (three/halls.js): a floor above the others that only the walk has, at the
  // top of the lift's list. Its height only matters to its own light.
  const founder = ctx.org.founder || null;
  const given = founder?.firstName || founder?.name?.trim().split(/\s+/)[0] || '';
  const penthouse = {
    id: 'penthouse', label: given ? `${given}'s office` : 'Penthouse', role: 'penthouse', rooms: [],
    group: new THREE.Group(), y: order[0].y + H + 0.3,
  };
  penthouse.group.position.set(order[0].group.position.x, penthouse.y, order[0].group.position.z);
  penthouse.group.visible = false;
  scene.add(penthouse.group);
  order.unshift(penthouse);
  const me = {
    x: 0, z: 0, yaw: 0, pitch: -0.05, yawGoal: 0, pitchGoal: -0.05, vx: 0, vz: 0, speed: 0,
    phase: 0, amp: 0, dip: 0, dipV: 0, striding: false, target: null, stuck: 0,
  };
  const keys = new Set();
  const stick = { x: 0, y: 0, id: null };
  let here = null;
  let hall = null;
  let map = null;
  let ride = null;
  let inLift = false;
  let press = null;
  let lastTap = null;
  let lastInput = performance.now();
  let seen = ctx.version();
  let surveyed = 0;
  let cardTimer = 0;

  /* ---------- the controls on the page ---------- */

  loadStyle(); // already loaded when the building started the walk; this only covers other callers
  const el = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  };
  const button = (text, onClick, label) => {
    const b = el('button', 'aw-btn', text);
    b.type = 'button';
    if (label) b.setAttribute('aria-label', label);
    b.addEventListener('click', onClick, { signal });
    return b;
  };
  const hud = el('div', 'aw-hud');
  const floorName = button('', () => (picker.hidden ? openPicker() : closePicker()), 'Choose a floor for the lift');
  floorName.classList.add('aw-name');
  const floorBox = el('div', 'aw-floor');
  floorBox.append(button('▼', () => stepFloor(-1), 'Take the lift down a floor'), floorName, button('▲', () => stepFloor(1), 'Take the lift up a floor'));
  hud.append(button('Leave', () => ctx.leave(), 'Leave the walk'), floorBox);
  const picker = el('div', 'aw-picker');
  picker.hidden = true;
  picker.setAttribute('role', 'dialog');
  picker.setAttribute('aria-label', 'The lift');
  const card = el('div', 'aw-card');
  card.hidden = true;
  card.setAttribute('role', 'status');
  const cardTitle = el('b');
  const cardSub = el('span');
  const cardText = el('div');
  cardText.append(cardTitle, cardSub);
  const openButton = button('Open', () => ctx.leave(), 'Leave the walk and open this in the list');
  card.append(cardText, openButton);
  const help = el('p', 'aw-help', coarse
    ? 'Walk with the stick and drag to look. Tap the floor to go there, or something to open it. Double-tap to burn this floor and rebuild it.'
    : 'WASD or the arrow keys to walk, Shift to hurry, drag to look. Click the floor to go there, or something to open it. Double-click to burn this floor and rebuild it. Esc to leave.');
  const stickEl = el('div', 'aw-stick');
  const knob = el('span');
  stickEl.append(knob);
  stickEl.setAttribute('aria-hidden', 'true');
  const loading = el('div', 'aw-load');
  loading.setAttribute('role', 'status');
  const loadingText = el('span', null, 'Loading real materials');
  const loadingBar = el('b');
  const track = el('i');
  track.append(loadingBar);
  loading.append(loadingText, track);
  loading.hidden = photoState !== 'loading';
  stage.append(hud, picker, card, help, stickEl, loading);
  stage.classList.add('arnheim-walking');
  // Talking with whoever's ring you stand in, by typing or out loud (voice.js).
  const voice = createVoice({ hud, card, ctx, el, button, signal });
  const helpTimer = setTimeout(() => help.classList.add('aw-faded'), 9000);
  // The founder's notes, hung in their office (walk-notes.js): the page gives them and is asked for more.
  const notes = createWalkNotes({
    stage, signal, coarse, notes: ctx.notes?.(), ask: () => ctx.onNotes?.(), wake: ctx.wake,
    hideCard() { clearTimeout(cardTimer); card.hidden = true; },
    remap() { if (here === penthouse && !ride) look(); },
  });

  function openPicker() {
    if (ride) return;
    const list = el('ul');
    for (const s of order) {
      const b = button(s.label, () => rideTo(s), s === here ? `${s.label}, you are here` : `Take the lift to ${s.label}`);
      if (s === here) { b.setAttribute('aria-current', 'true'); b.disabled = true; }
      const item = el('li');
      item.append(b);
      list.append(item);
    }
    picker.replaceChildren(el('p', null, 'Take the lift to'), list);
    picker.hidden = false;
    card.hidden = true;
  }
  function closePicker() { picker.hidden = true; }

  // A card naming what was tapped, for a few seconds; or, while someone stands in a talking ring,
  // naming who they are with, for as long as they stay.
  function showCard(hit, talk = false) {
    const info = ctx.describe(hit) || {};
    cardTitle.textContent = info.title || hit.title || '';
    cardSub.textContent = info.sub || '';
    cardSub.hidden = !cardSub.textContent;
    openButton.hidden = !!hit.stay; // a thing of the walk's own, with nothing to open in the list
    card.classList.toggle('aw-talking', talk);
    card.hidden = false;
    clearTimeout(cardTimer);
    if (!talk) cardTimer = setTimeout(() => { if (talking) showCard(talking.who, true); else card.hidden = true; }, 7000);
  }

  function input() {
    lastInput = performance.now();
    ctx.touched();
    ctx.wake(2);
  }

  /* ---------- floors and halls ---------- */

  function hallFor(s) {
    let entry = halls.get(s.id);
    if (entry) return entry;
    // A building can give its own halls (photo-building.js: the baked floor's corridor, lift and reception).
    entry = (s !== penthouse && ctx.hallFor?.(s)) || (s === penthouse
      ? buildPenthouse(s, { founder, assistant: ctx.org.assistant || null })
      : buildHall(s, { company: ctx.org.company, mission: ctx.org.mission }));
    if (photo) dressHall(entry, photo);
    if (s === penthouse) notes.hang(entry);
    const person = ctx.personRoom;
    if (entry.poe && person?.storey === s) {
      const P = person.spec.person;
      const hit = new THREE.Mesh(new THREE.BoxGeometry(0.8, 1.1, 0.6), hitMaterial);
      hit.position.set(entry.poe.x, 1.05, entry.poe.z);
      hit.visible = false;
      hit.userData = { hit: true, talk: true, floorId: person.floorId, roomId: person.roomId, href: P.href, title: P.name, sub: `${P.title || 'Receptionist'}. Tap to talk.` };
      entry.group.add(hit);
      entry.picks.push(hit);
    }
    halls.set(s.id, entry);
    return entry;
  }

  // The rooms open onto the hall: no front walls, and a full wall at the far end.
  function setWalls(s, on) {
    for (const r of s.rooms) if (r.walls) r.walls.s.visible = !on;
    const last = s.rooms[s.rooms.length - 1];
    if (last?.walls) last.walls.e.scale.y = on ? H : CURB;
  }

  // The receptionist stands behind the hall's reception desk while you walk, and goes back to their room
  // after. Their room's counter is put away meanwhile, so there is only ever one reception desk.
  function placeReceptionist(on) {
    const room = ctx.personRoom;
    if (!room?.person || room.storey !== here || !hall?.poe || hall.baked) return; // a baked hall's receptionist is already at their desk
    const P = room.spec.person;
    const body = room.person.group;
    if (room.counter) room.counter.visible = !on;
    if (on) {
      hall.group.add(body);
      body.position.set(hall.poe.x, 0, hall.poe.z);
      body.rotation.y = hall.poe.turn;
      room.lamp2.set(hall.poe.x - room.g.position.x + 0.5, 1.9, hall.poe.z - room.g.position.z + 0.9);
    } else {
      room.g.add(body);
      body.position.set(...P.at);
      body.rotation.y = P.turn;
      room.lamp2.set(...room.spec.lamps.side);
    }
  }

  function chest(out) {
    const p = here.group.position;
    return out.set(p.x + me.x, p.y + 1.1, p.z + me.z);
  }

  function enter(s, spawn) {
    if (here) leave(here);
    here = s;
    hall = hallFor(s);
    if (!hall.group.parent) s.group.add(hall.group);
    hall.group.visible = true;
    setWalls(s, true);
    placeReceptionist(true);
    s.group.visible = true;
    look();
    const at = spawn === 'entrance' && hall.entrance ? hall.entrance : hall.spot;
    me.x = at.x;
    me.z = at.z;
    me.yaw = me.yawGoal = at.yaw;
    me.pitch = me.pitchGoal = -0.05;
    me.vx = me.vz = me.speed = 0;
    me.target = null;
    free();
    placeSpots();
    hall.lift.open = 0;
    hall.setDoors(0);
    inLift = hall.inLift(me.x, me.z);
    floorName.textContent = s.label;
    const p = s.group.position;
    ctx.shadows(new THREE.Vector3(p.x + (hall.west + hall.east) / 2, p.y + 1, p.z + hall.front / 2), Math.max(hall.east - hall.west, hall.front) / 2 + 2);
  }

  function leave(s) {
    setTalk(null);
    setWalls(s, false);
    placeReceptionist(false);
    const entry = halls.get(s.id);
    if (entry) entry.group.visible = false;
    s.group.visible = false;
  }

  // Reads the floor as it stands: what stops you (anything between knee and chest height, drawn
  // onto a grid) and what a tap can land on.
  function survey(s) {
    s.group.updateMatrixWorld(true);
    const inv = new THREE.Matrix4().copy(s.group.matrixWorld).invert();
    const m = new THREE.Matrix4();
    const a = new THREE.Vector3();
    const b = new THREE.Vector3();
    const c = new THREE.Vector3();
    const x0 = hall.west - 0.4;
    const z0 = (hall.north ?? 0) - 0.4;
    const cols = Math.ceil((hall.east + 0.4 - x0) / CELL);
    const rows = Math.ceil((hall.front + 0.4 - z0) / CELL);
    const cells = new Uint8Array(cols * rows); // what stops you
    const sight = new Uint8Array(cols * rows); // what hides a name behind it: walls and tall things
    const solids = [];
    const mark = (grid, xa, xb, za, zb) => {
      const c0 = Math.max(0, Math.floor((xa - x0) / CELL));
      const c1 = Math.min(cols - 1, Math.floor((xb - x0) / CELL));
      const r0 = Math.max(0, Math.floor((za - z0) / CELL));
      const r1 = Math.min(rows - 1, Math.floor((zb - z0) / CELL));
      for (let r = r0; r <= r1; r++) for (let q = c0; q <= c1; q++) grid[r * cols + q] = 1;
    };
    const visit = (o, top) => {
      if (!top && !o.visible) return;
      if (o.isMesh && !o.userData.hit) {
        const mt = Array.isArray(o.material) ? o.material[0] : o.material;
        if (mt && mt.colorWrite !== false) {
          solids.push(o);
          if (!o.userData.noCollide && (!mt.transparent || o.userData.solid)) {
            m.multiplyMatrices(inv, o.matrixWorld);
            const pos = o.geometry.attributes.position;
            const idx = o.geometry.index;
            const n = idx ? idx.count : pos.count;
            for (let i = 0; i + 2 < n; i += 3) {
              a.fromBufferAttribute(pos, idx ? idx.getX(i) : i).applyMatrix4(m);
              b.fromBufferAttribute(pos, idx ? idx.getX(i + 1) : i + 1).applyMatrix4(m);
              c.fromBufferAttribute(pos, idx ? idx.getX(i + 2) : i + 2).applyMatrix4(m);
              const lo = Math.min(a.y, b.y, c.y);
              const hi = Math.max(a.y, b.y, c.y);
              if (hi < 0.12 || lo > 2.4) continue;
              const xa = Math.min(a.x, b.x, c.x);
              const xb = Math.max(a.x, b.x, c.x);
              const za = Math.min(a.z, b.z, c.z);
              const zb = Math.max(a.z, b.z, c.z);
              if (lo <= 1.5) mark(cells, xa, xb, za, zb);
              if (hi > 1.6) mark(sight, xa, xb, za, zb);
            }
          }
        }
      }
      for (const child of o.children) visit(child, false);
    };
    visit(s.group, true);
    return { x0, z0, cols, rows, cells, sight, solids };
  }

  // Whether the walker can see a spot on this floor, or a wall or something tall is in the way.
  function inView(x1, z1) {
    const len = Math.hypot(x1 - me.x, z1 - me.z);
    const steps = Math.ceil(len / (CELL / 2));
    for (let i = 1; i < steps; i++) {
      const t = i / steps;
      if (len * t < 0.3) continue;
      if (len * (1 - t) < 0.4) break;
      const q = Math.floor((me.x + (x1 - me.x) * t - map.x0) / CELL);
      const r = Math.floor((me.z + (z1 - me.z) * t - map.z0) / CELL);
      if (q >= 0 && r >= 0 && q < map.cols && r < map.rows && map.sight[r * map.cols + q]) return false;
    }
    return true;
  }
  function look() {
    map = survey(here);
    surveyed = performance.now();
    seen = ctx.version();
  }

  /* ---------- talking: a ring on the floor by each agent at work, and by the receptionist ---------- */

  // Stand in a ring and the walk knows who you mean: the ring lights, a card names them, and the
  // page hears of them as if they had been tapped.
  const ringGeo = new THREE.RingGeometry(0.3, 0.4, 48).rotateX(-Math.PI / 2);
  const ringIdle = new THREE.MeshBasicMaterial({ color: '#ffc985', transparent: true, opacity: 0.4, depthWrite: false });
  const ringLit = new THREE.MeshBasicMaterial({ color: '#ffe4bd', transparent: true, opacity: 0.95, depthWrite: false });
  let spots = [];
  let talking = null;
  let heldOff = false; // a re-seat ended a talk: no new one until the walker steps off the ring

  // Every square of this floor's plan the walker can reach from where they stand.
  function reach() {
    const { cols, rows, x0, z0 } = map;
    const open = new Uint8Array(cols * rows);
    const q0 = Math.floor((me.x - x0) / CELL);
    const r0 = Math.floor((me.z - z0) / CELL);
    if (q0 < 0 || r0 < 0 || q0 >= cols || r0 >= rows) return open;
    const queue = [r0 * cols + q0];
    open[queue[0]] = 1;
    while (queue.length) {
      const i = queue.pop();
      const q = i % cols;
      const r = (i - q) / cols;
      for (const [nq, nr] of [[q + 1, r], [q - 1, r], [q, r + 1], [q, r - 1]]) {
        const j = nr * cols + nq;
        if (nq < 0 || nr < 0 || nq >= cols || nr >= rows || open[j]) continue;
        if (blocked(x0 + (nq + 0.5) * CELL, z0 + (nr + 0.5) * CELL)) continue;
        open[j] = 1;
        queue.push(j);
      }
    }
    return open;
  }

  // A ring for each agent at work on this floor, and for the receptionist: at the place the walker can reach
  // that is nearest a good spot to talk from, not too close to them and not on another ring.
  // Placing them again (the page's work changed and people moved seats) never hands you to someone
  // else while you stand still: the talk goes on if the same person's ring is still where you stand,
  // and otherwise ends, with no new one until you step off the ring you are on.
  function placeSpots() {
    const was = talking;
    for (const s of spots) s.ring.removeFromParent();
    spots = [];
    const open = reach();
    const add = (who, ax, az, sx, sz) => {
      let best = null;
      // Near them and apart from the other rings (they touch at 0.8); in a crowded room, a little
      // further off and closer together, so everyone still has one.
      for (const [far, apart] of [[2.2, 0.8], [2.9, 0.62]]) {
        let gap = Infinity;
        for (let i = 0; i < open.length; i++) {
          if (!open[i]) continue;
          const q = i % map.cols;
          const x = map.x0 + (q + 0.5) * CELL;
          const z = map.z0 + ((i - q) / map.cols + 0.5) * CELL;
          const away = Math.hypot(x - ax, z - az);
          if (away < 0.55 || away > far || spots.some((s) => Math.hypot(x - s.x, z - s.z) < apart)) continue;
          const d = Math.hypot(x - sx, z - sz);
          if (d < gap) { gap = d; best = { x, z }; }
        }
        if (best) break;
      }
      if (!best) return;
      const ring = new THREE.Mesh(ringGeo, ringIdle);
      ring.position.set(best.x, 0.025, best.z);
      hall.group.add(ring);
      spots.push({ ...best, ring, who, ax, az });
    };
    for (const room of here.rooms) {
      const { x: rx, z: rz } = room.g?.position || { x: 0, z: 0 }; // a baked floor's rooms are in the floor's own coordinates
      for (const o of room.objects) {
        const f = o.figure;
        if (f) add({ title: o.title, sub: o.sub, href: o.href, floorId: room.floorId, roomId: room.roomId }, rx + f.x, rz + f.z, rx + f.stand[0], rz + f.stand[1]);
      }
    }
    const person = ctx.personRoom;
    if (hall.poe && person?.storey === here) {
      const P = person.spec.person;
      add({ title: P.name, sub: P.title || 'Receptionist', href: P.href, voice: P.voice || null, floorId: person.floorId, roomId: person.roomId }, hall.poe.x, hall.poe.z, hall.poe.x, hall.poe.z + 1.75);
    }
    const A = hall.assistant; // the founder's assistant, in their office
    if (A) add({ ...A.who, floorId: here.id, roomId: 'office' }, A.x, A.z, A.stand[0], A.stand[1]);
    if (!was) return;
    const same = spots.find((s) => (s.who.href || s.who.title) === (was.who.href || was.who.title) && Math.hypot(me.x - s.x, me.z - s.z) < 0.42);
    if (same) {
      talking = same;
      same.ring.material = ringLit;
    } else {
      setTalk(null);
      heldOff = true;
    }
  }

  function setTalk(spot) {
    if (spot === talking) return;
    if (talking) talking.ring.material = ringIdle;
    talking = spot;
    if (spot) {
      // Walking into the ring by a tap: on arrival, turn to face whoever it is for.
      if (me.target && Math.hypot(me.target.x - spot.x, me.target.z - spot.z) < 0.5) me.target.face = [spot.ax, spot.az];
      spot.ring.material = ringLit;
      showCard(spot.who, true);
      ctx.onPick?.({ ...spot.who, walk: true });
    } else if (card.classList.contains('aw-talking')) card.hidden = true;
    voice.talkTo(spot?.who || null);
    ctx.wake(2);
  }

  /* ---------- moving ---------- */

  function blocked(x, z) {
    const c0 = Math.floor((x - RADIUS - map.x0) / CELL);
    const c1 = Math.floor((x + RADIUS - map.x0) / CELL);
    const r0 = Math.floor((z - RADIUS - map.z0) / CELL);
    const r1 = Math.floor((z + RADIUS - map.z0) / CELL);
    for (let r = r0; r <= r1; r++) {
      for (let q = c0; q <= c1; q++) {
        if (q < 0 || r < 0 || q >= map.cols || r >= map.rows) return true;
        if (!map.cells[r * map.cols + q]) continue;
        const nx = Math.max(map.x0 + q * CELL, Math.min(x, map.x0 + (q + 1) * CELL));
        const nz = Math.max(map.z0 + r * CELL, Math.min(z, map.z0 + (r + 1) * CELL));
        if ((nx - x) ** 2 + (nz - z) ** 2 < RADIUS * RADIUS) return true;
      }
    }
    return false;
  }

  // Slides along walls rather than sticking to them. Someone already inside something may walk out.
  function move(dx, dz) {
    const steps = Math.max(1, Math.ceil(Math.hypot(dx, dz) / 0.08));
    const loose = blocked(me.x, me.z);
    for (let i = 0; i < steps; i++) {
      const nx = me.x + dx / steps;
      if (loose || !blocked(nx, me.z)) me.x = nx;
      const nz = me.z + dz / steps;
      if (loose || !blocked(me.x, nz)) me.z = nz;
    }
  }

  function free() {
    if (!blocked(me.x, me.z)) return;
    for (let r = 0.2; r < 2.5; r += 0.2) {
      for (let a = 0; a < Math.PI * 2; a += Math.PI / 8) {
        const x = me.x + Math.cos(a) * r;
        const z = me.z + Math.sin(a) * r;
        if (!blocked(x, z)) { me.x = x; me.z = z; return; }
      }
    }
  }

  /* ---------- the lift and the burn ---------- */

  function stepFloor(dir) {
    const to = order[order.indexOf(here) - dir];
    if (to) rideTo(to);
  }

  // Goes to another floor, or (at a point) burns this floor away and rebuilds it.
  function rideTo(to, at = null) {
    if (ride || !to || (to === here && !at)) return;
    closePicker();
    card.hidden = true;
    me.target = null;
    input();
    if (still()) { if (to !== here) enter(to, 'lift'); return; }
    ride = { to, same: to === here, at, phase: 'close', t: 0 };
    if (ride.same || !hall.inLift(me.x, me.z)) burnOut();
  }

  function burnOut() {
    ride.phase = 'out';
    burn.start({ root: here.group, origin: ride.at || chest(new THREE.Vector3()), inward: false, eye: camera.position });
    here.group.visible = false;
  }

  function advance(dt) {
    ride.t += dt;
    if (ride.phase === 'close') {
      if (hall.lift.open < 0.05 || ride.t > 1.2) burnOut();
    } else if (ride.phase === 'out') {
      if (burn.running) return;
      if (!ride.same) enter(ride.to, 'lift');
      here.group.visible = false; // it gathers out of points first
      ride.phase = 'in';
      const eye = chest(new THREE.Vector3());
      burn.start({ root: here.group, origin: ride.same ? ride.at : eye, inward: true, eye });
    } else if (ride.phase === 'in' && !burn.running) {
      here.group.visible = true;
      ride = null;
    }
  }

  /* ---------- input ---------- */

  const typing = (event) => event.target?.closest?.('input, textarea, select, [contenteditable]');
  window.addEventListener('keydown', (event) => {
    if (typing(event) || event.metaKey || event.ctrlKey || event.altKey) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      if (!picker.hidden) closePicker();
      else ctx.leave();
    } else if (event.key === 'PageUp' || event.key === 'PageDown') {
      event.preventDefault();
      stepFloor(event.key === 'PageUp' ? 1 : -1);
    } else if (MOVES.has(event.code)) {
      event.preventDefault();
      keys.add(event.code);
      me.target = null;
      input();
    }
  }, { signal });
  window.addEventListener('keyup', (event) => { keys.delete(event.code); }, { signal });
  window.addEventListener('blur', () => keys.clear(), { signal });

  // Drag to look, as if taking hold of the world; a quick tap goes somewhere or opens something.
  canvas.addEventListener('pointerdown', (event) => {
    if (press || (event.pointerType === 'mouse' && event.button !== 0)) return;
    press = { id: event.pointerId, x: event.clientX, y: event.clientY, at: performance.now(), yaw: me.yawGoal, pitch: me.pitchGoal, moved: false, touch: event.pointerType !== 'mouse' };
    try { canvas.setPointerCapture(event.pointerId); } catch { /* a pointer the browser no longer tracks */ }
    input();
  }, { signal });
  canvas.addEventListener('pointermove', (event) => {
    if (!press || event.pointerId !== press.id) return;
    const dx = event.clientX - press.x;
    const dy = event.clientY - press.y;
    if (!press.moved && Math.hypot(dx, dy) > 6) press.moved = true;
    if (!press.moved) return;
    const k = press.touch ? 0.0062 : 0.0045;
    me.yawGoal = press.yaw + dx * k;
    me.pitchGoal = THREE.MathUtils.clamp(press.pitch + dy * k * 0.8, -0.75, 0.6);
    input();
  }, { signal });
  const release = (event) => {
    if (!press || event.pointerId !== press.id) return;
    const tap = !press.moved && performance.now() - press.at < 450;
    press = null;
    if (tap && event.type === 'pointerup') tapAt(event.clientX, event.clientY);
  };
  canvas.addEventListener('pointerup', release, { signal });
  canvas.addEventListener('pointercancel', release, { signal });

  // Tap to talk: tapping someone who has a ring (the receptionist, the founder's assistant, an agent at
  // work or waiting for you) walks you onto it,
  // round whatever is in the way, and turns you to face them as you arrive. The talk itself starts
  // as you step in (setTalk), just as if you had walked there.
  const ringOf = (hit) => spots.find((s) => (hit.href ? s.who.href === hit.href : s.who.title === hit.title)) || null;

  function walkToTalk(hit) {
    const spot = ringOf(hit);
    if (!spot) return false;
    if (spot === talking) { showCard(spot.who, true); return true; }
    const way = wayTo(spot.x, spot.z);
    if (!way) return false;
    showCard(hit);
    me.target = { ...way.shift(), next: way, face: [spot.ax, spot.az] };
    ctx.wake(2);
    return true;
  }

  // The way from here to a spot on this floor: the floor plan's squares, searched outward from where
  // you stand, then pulled straight wherever nothing is in the way. Null if it can't be reached.
  function wayTo(tx, tz) {
    const { cols, rows, x0, z0 } = map;
    const square = (x, z) => {
      const q = Math.floor((x - x0) / CELL);
      const r = Math.floor((z - z0) / CELL);
      return q < 0 || r < 0 || q >= cols || r >= rows ? -1 : r * cols + q;
    };
    const start = square(me.x, me.z);
    const goal = square(tx, tz);
    if (start < 0 || goal < 0) return null;
    const from = new Int32Array(cols * rows).fill(-1);
    from[start] = start;
    const queue = [start];
    for (let head = 0; head < queue.length && from[goal] < 0; head++) {
      const i = queue[head];
      const q = i % cols;
      const r = (i - q) / cols;
      for (const [nq, nr] of [[q + 1, r], [q - 1, r], [q, r + 1], [q, r - 1]]) {
        const j = nr * cols + nq;
        if (nq < 0 || nr < 0 || nq >= cols || nr >= rows || from[j] >= 0) continue;
        if (blocked(x0 + (nq + 0.5) * CELL, z0 + (nr + 0.5) * CELL)) continue;
        from[j] = i;
        queue.push(j);
      }
    }
    if (from[goal] < 0) return null;
    const squares = [{ x: tx, z: tz }];
    for (let i = from[goal]; i !== start; i = from[i]) squares.unshift({ x: x0 + ((i % cols) + 0.5) * CELL, z: z0 + (Math.floor(i / cols) + 0.5) * CELL });
    const clear = (a, b) => {
      const steps = Math.ceil(Math.hypot(b.x - a.x, b.z - a.z) / (CELL / 2));
      for (let i = 1; i <= steps; i++) if (blocked(a.x + ((b.x - a.x) * i) / steps, a.z + ((b.z - a.z) * i) / steps)) return false;
      return true;
    };
    const points = [];
    let at = { x: me.x, z: me.z };
    for (let k = 0; k < squares.length; k++) {
      let far = k;
      while (far + 1 < squares.length && clear(at, squares[far + 1])) far += 1;
      at = squares[far];
      points.push(at);
      k = far;
    }
    return points;
  }

  function tapAt(x, y) {
    if (ride) return;
    const now = performance.now();
    const double = !!lastTap && now - lastTap.at < 340 && Math.hypot(x - lastTap.x, y - lastTap.y) < 36;
    lastTap = double ? null : { at: now, x, y };
    const box = canvas.getBoundingClientRect();
    ndc.set(((x - box.left) / box.width) * 2 - 1, -((y - box.top) / box.height) * 2 + 1);
    ray.setFromCamera(ndc, camera);
    const surface = ray.intersectObjects(map.solids, false)[0];
    if (double) {
      if (surface) rideTo(here, surface.point.clone());
      return;
    }
    const picks = [...hall.picks];
    for (const r of here.rooms) for (const o of r.objects) if (!o.person) picks.push(o.hit);
    const thing = ray.intersectObjects(picks, false).find((h) => h.distance < 10);
    if (notes.tap(thing && (!surface || thing.distance <= surface.distance + 0.3) ? thing.object.userData : null)) return;
    if (thing && (!surface || thing.distance <= surface.distance + 0.3)) {
      const hit = thing.object.userData;
      if (hit.lift) { openPicker(); return; }
      if ((hit.talk || ringOf(hit)) && walkToTalk(hit)) return;
      showCard(hit);
      if (!hit.stay) ctx.onPick?.({ ...hit, walk: true });
      return;
    }
    if (!surface) return;
    const spot = here.group.worldToLocal(surface.point.clone());
    if (spot.y > 0.08) spot.copy(here.group.worldToLocal(surface.point.clone().addScaledVector(ray.ray.direction, -0.5)));
    me.target = { x: spot.x, z: spot.z };
  }

  // The stick, for thumbs: up walks ahead, sideways steps aside.
  function moveStick(event) {
    const r = stickEl.getBoundingClientRect();
    const max = r.width / 2 - 8;
    let dx = event.clientX - (r.left + r.width / 2);
    let dy = event.clientY - (r.top + r.height / 2);
    const len = Math.hypot(dx, dy);
    if (len > max) { dx *= max / len; dy *= max / len; }
    stick.x = dx / max;
    stick.y = dy / max;
    knob.style.transform = `translate(${dx}px, ${dy}px)`;
    me.target = null;
    input();
  }
  stickEl.addEventListener('pointerdown', (event) => {
    event.stopPropagation();
    stick.id = event.pointerId;
    try { stickEl.setPointerCapture(event.pointerId); } catch { /* a pointer the browser no longer tracks */ }
    moveStick(event);
  }, { signal });
  stickEl.addEventListener('pointermove', (event) => { if (event.pointerId === stick.id) moveStick(event); }, { signal });
  const dropStick = (event) => {
    if (event.pointerId !== stick.id) return;
    stick.id = null;
    stick.x = 0;
    stick.y = 0;
    knob.style.transform = '';
  };
  stickEl.addEventListener('pointerup', dropStick, { signal });
  stickEl.addEventListener('pointercancel', dropStick, { signal });

  /* ---------- each frame ---------- */

  // Moves the walk on by dt seconds and places the camera; true while anything is still moving.
  function update(dt, now) {
    if (!here) return false;
    let busy = false;
    if (ride) { advance(dt); busy = true; }
    if (!ride && ctx.version() !== seen && now - surveyed > 1500) { look(); placeSpots(); }

    // Turning: smooth, whether by drag, keys or walking somewhere.
    const turn = (keys.has('ArrowLeft') ? 1 : 0) - (keys.has('ArrowRight') ? 1 : 0);
    if (turn && !ride) { me.yawGoal += turn * dt * 1.9; busy = true; }
    const k = still() ? 1 : 1 - Math.exp(-dt * 11);
    const dYaw = me.yawGoal - me.yaw;
    const dPitch = me.pitchGoal - me.pitch;
    if (Math.abs(dYaw) > 1e-4 || Math.abs(dPitch) > 1e-4) {
      me.yaw += dYaw * k;
      me.pitch += dPitch * k;
      busy = true;
    } else {
      me.yaw = me.yawGoal;
      me.pitch = me.pitchGoal;
    }

    // Where the walker wants to go: keys, the stick, or a spot they tapped.
    let f = 0;
    let s = 0;
    if (!ride) {
      if (keys.has('KeyW') || keys.has('ArrowUp')) f += 1;
      if (keys.has('KeyS') || keys.has('ArrowDown')) f -= 1;
      if (keys.has('KeyD')) s += 1;
      if (keys.has('KeyA')) s -= 1;
      if (Math.hypot(stick.x, stick.y) > 0.14) { f -= stick.y; s += stick.x; }
    }
    const manual = Math.hypot(f, s) > 0.05;
    if (manual || ride) me.target = null;
    const sin = Math.sin(me.yaw);
    const cos = Math.cos(me.yaw);
    let wx = 0;
    let wz = 0;
    if (manual) {
      const len = Math.max(1, Math.hypot(f, s));
      const pace = (keys.has('ShiftLeft') || keys.has('ShiftRight') ? RUN : WALK) / len;
      wx = (-sin * f + cos * s) * pace;
      wz = (-cos * f - sin * s) * pace;
    } else if (me.target) {
      // On a way with corners (walkToTalk), each corner is passed on the move, not stopped at.
      if (me.target.next?.length && Math.hypot(me.target.x - me.x, me.target.z - me.z) < 0.3) {
        me.target = { ...me.target.next.shift(), next: me.target.next, face: me.target.face };
      }
      const last = !me.target.next?.length;
      const dx = me.target.x - me.x;
      const dz = me.target.z - me.z;
      const dist = Math.hypot(dx, dz);
      if (last && dist < 0.12) {
        const them = me.target.face;
        me.target = null;
        if (them) {
          const turn = Math.atan2(-(them[0] - me.x), -(them[1] - me.z)) - me.yawGoal;
          me.yawGoal += Math.atan2(Math.sin(turn), Math.cos(turn));
        }
      } else {
        const pace = last ? Math.min(WALK, 0.3 + dist * 1.4) : WALK;
        wx = (dx / dist) * pace;
        wz = (dz / dist) * pace;
        let face = Math.atan2(-dx, -dz) - me.yawGoal;
        face = Math.atan2(Math.sin(face), Math.cos(face));
        if (dist > 0.6 || !last) me.yawGoal += face * Math.min(1, dt * 2.4);
      }
    }
    const want = Math.hypot(wx, wz);
    const ease = still() ? 1 : 1 - Math.exp(-dt * (want > me.speed ? 4.5 : 6.5));
    me.vx += (wx - me.vx) * ease;
    me.vz += (wz - me.vz) * ease;
    me.speed = Math.hypot(me.vx, me.vz);
    if (me.speed < 0.01 && want === 0) { me.vx = 0; me.vz = 0; me.speed = 0; }
    if (me.speed > 0) {
      const ox = me.x;
      const oz = me.z;
      move(me.vx * dt, me.vz * dt);
      const went = Math.hypot(me.x - ox, me.z - oz);
      if (me.target && went < me.speed * dt * 0.3) {
        me.stuck += dt;
        if (me.stuck > 0.4) me.target = null;
      } else me.stuck = 0;
      me.phase += (went / STRIDE) * Math.PI;
      busy = true;
      if (hall.poe && Math.hypot(me.x - hall.poe.x, me.z - hall.poe.z) < 7) ctx.poeAwake();
    }

    // A soft settle as the walker comes to a stop, and the stride fading out.
    if (me.speed > 0.7) me.striding = true;
    else if (me.striding && me.speed < 0.2) { me.striding = false; if (!still()) me.dipV -= 0.2; }
    me.dipV += (-me.dip * 70 - me.dipV * 11) * dt;
    me.dip += me.dipV * dt;
    if (Math.abs(me.dip) > 2e-4 || Math.abs(me.dipV) > 2e-3) busy = true;
    else { me.dip = 0; me.dipV = 0; }
    const ampGoal = still() ? 0 : Math.min(1, me.speed / WALK);
    me.amp += (ampGoal - me.amp) * (1 - Math.exp(-dt * 5));
    if (Math.abs(ampGoal - me.amp) > 0.002) busy = true;
    else me.amp = ampGoal;

    // The lift: its doors open as you come near, and stepping in shows the floors.
    const L = hall.lift;
    const doorGoal = ride ? 0 : Math.hypot(me.x - L.x, me.z - L.z) < 2.4 ? 1 : 0;
    if (Math.abs(doorGoal - L.open) > 0.003) {
      L.open += (doorGoal - L.open) * (still() ? 1 : 1 - Math.exp(-dt * 3.6));
      hall.setDoors(L.open);
      busy = true;
    } else if (L.open !== doorGoal) {
      L.open = doorGoal;
      hall.setDoors(doorGoal);
    }
    if (!ride) {
      const inside = hall.inLift(me.x, me.z);
      if (inside && !inLift) openPicker();
      else if (!inside && inLift) closePicker();
      inLift = inside;
      const ring = spots.find((s) => Math.hypot(me.x - s.x, me.z - s.z) < 0.42) || null;
      if (!ring) heldOff = false;
      if (!heldOff) setTalk(ring);
    }
    if (notes.update(dt, me, here === penthouse && !ride, still())) busy = true;
    if (burn.update(dt, camera, renderer)) busy = true;

    // The camera at eye height: a gentle bob and sway in step, and a little hand-held drift that
    // fades a few seconds after the last touch, so a still picture really is still.
    const hand = still() ? 0 : Math.max(0, 1 - (now - lastInput) / QUIET_MS) * 0.7 + me.amp * 0.3;
    if (hand > 0.003) busy = true;
    const t = now / 1000;
    const sway = Math.sin(me.phase) * 0.016 * me.amp;
    const bob = (Math.cos(me.phase * 2) - 1) * 0.012 * me.amp;
    const p = here.group.position;
    camera.position.set(p.x + me.x + cos * sway, p.y + EYE + bob + me.dip, p.z + me.z - sin * sway);
    camera.rotation.set(
      me.pitch + hand * (Math.sin(t * 0.7 + 0.4) * 0.6 + Math.sin(t * 2.5) * 0.4) * 0.003,
      me.yaw + hand * (Math.sin(t * 0.9) * 0.6 + Math.sin(t * 2.1 + 1.3) * 0.4) * 0.004,
      Math.sin(me.phase) * 0.005 * me.amp,
      'YXZ',
    );
    footage.enabled = !still();
    if (footage.enabled) {
      const vfov = THREE.MathUtils.degToRad(camera.fov);
      const hfov = 2 * Math.atan(Math.tan(vfov / 2) * camera.aspect);
      // The smear a phone's shutter catches at this speed of turn, whatever the frame rate, kept light.
      const smear = (d, span) => THREE.MathUtils.clamp(((d / Math.max(dt, 0.004)) * SHUTTER) / span, -0.008, 0.008);
      footage.uniforms.uVel.value.set(smear(camera.rotation.y - lastYaw, hfov), smear(camera.rotation.x - lastPitch, vfov));
      footage.uniforms.uTime.value = t;
      footage.uniforms.uRes.value.copy(renderer.getDrawingBufferSize(px));
    }
    lastYaw = camera.rotation.y;
    lastPitch = camera.rotation.x;
    return busy;
  }

  // Names over the nearest open rooms, and the receptionist's, for the building's label layer.
  function labels() {
    if (!here || ride) return [];
    const out = [];
    camera.getWorldDirection(ahead);
    for (const room of here.rooms) {
      // over a drawn room's open front; over the middle of a baked one
      const local = room.g ? [W / 2, H - 0.3, D + 0.02] : [room.centre[0], 2.3, room.centre[1]];
      const seenAt = room.g ? [room.g.position.x + W / 2, D + 0.02] : room.centre;
      ctx.roomWorld(room, v, ...local);
      const d = v.distanceTo(camera.position);
      if (d > 16 || v.sub(camera.position).normalize().dot(ahead) < 0.35 || !inView(...seenAt)) continue;
      out.push({ key: `w:${room.key}`, title: room.label, sub: ctx.infoText(room.info), kind: room.mood, align: 'center', room, local, rank: d });
    }
    const person = ctx.personRoom;
    if (hall.poe && person?.storey === here) {
      const p = here.group.position;
      v.set(p.x + hall.poe.x, p.y + 2.05, p.z + hall.poe.z);
      if (v.distanceTo(camera.position) < 12 && inView(hall.poe.x, hall.poe.z)) out.push({ key: 'w:poe', title: person.spec.person.name, sub: person.spec.person.title || 'Receptionist', kind: 'quiet', align: 'center', at: v.toArray(), rank: 0 });
    }
    if (hall.desk?.name) {
      const p = here.group.position;
      v.set(p.x + hall.desk.x, p.y + 1.75, p.z + hall.desk.z);
      if (v.distanceTo(camera.position) < 14 && inView(hall.desk.x, hall.desk.z)) out.push({ key: 'w:founder', title: hall.desk.name, sub: hall.desk.title, kind: 'quiet', align: 'center', at: v.toArray(), rank: 0 });
    }
    if (hall.assistant) {
      const p = here.group.position;
      const A = hall.assistant;
      v.set(p.x + A.x, p.y + 2.1, p.z + A.z);
      if (v.distanceTo(camera.position) < 12 && inView(A.x, A.z)) out.push({ key: 'w:assistant', title: A.who.title, sub: A.who.sub, kind: 'quiet', align: 'center', at: v.toArray(), rank: 0 });
    }
    return out.sort((a, b) => a.rank - b.rank).slice(0, 5);
  }

  // A point on this floor (floor-local metres) on the screen, in page pixels, or null behind you.
  function onScreen(x, y, z) {
    const p = here.group.position;
    const v = new THREE.Vector3(p.x + x, p.y + y, p.z + z).project(camera);
    if (v.z > 1 || Math.abs(v.x) > 1 || Math.abs(v.y) > 1) return null;
    const box = canvas.getBoundingClientRect();
    return [Math.round(box.left + ((v.x + 1) / 2) * box.width), Math.round(box.top + ((1 - v.y) / 2) * box.height)];
  }

  // Where the walker is, for tests, with where the people to talk to and the rooms' openings are
  // on the screen, to tap.
  function info() {
    const r2 = (n) => Math.round(n * 100) / 100;
    return {
      floor: here?.id, x: r2(me.x), z: r2(me.z), yaw: r2(me.yaw), speed: r2(me.speed), riding: ride?.phase || null,
      burning: burn.active, points: burn.count, inLift, doors: r2(hall?.lift.open || 0), picker: !picker.hidden, card: card.hidden ? null : cardTitle.textContent,
      photo: photoState, film: footage.enabled, talk: talking?.who.title || null, rings: spots.map((r) => [r2(r.x), r2(r.z)]),
      voice: voice.info(),
      notes: notes.info(),
      people: here ? spots.map((s) => ({ title: s.who.title, href: s.who.href || null, at: onScreen(s.ax, 0.9, s.az), ring: onScreen(s.x, 0.03, s.z) })) : [],
      openings: here ? here.rooms.map((r) => {
        const [x, z] = r.g ? [r.g.position.x + W / 2, r.g.position.z + D + 0.8] : r.centre;
        return { room: r.roomId, x: r2(x), z: r2(z), at: onScreen(x, 0, z) };
      }) : [],
    };
  }

  function dispose() {
    gone = true;
    listeners.abort();
    clearTimeout(cardTimer);
    clearTimeout(helpTimer);
    clearTimeout(loadTimer);
    voice.dispose();
    if (here) { placeReceptionist(false); setWalls(here, false); }
    for (const entry of halls.values()) {
      entry.group.removeFromParent();
      entry.dispose();
    }
    halls.clear();
    notes.dispose();
    penthouse.group.removeFromParent();
    photo?.dispose(); // after the halls: their materials only borrowed these pictures
    photo = null;
    burn.dispose();
    ctx.composer.removePass(footage);
    footage.dispose();
    hitMaterial.dispose();
    ringGeo.dispose();
    ringIdle.dispose();
    ringLit.dispose();
    for (const node of [hud, picker, card, help, stickEl, loading]) node.remove();
    stage.classList.remove('arnheim-walking');
    here = null;
  }

  /* ---------- start: at the reception's door, or at the lift of the floor in view ---------- */

  const first = storeys.find((s) => s.id === ctx.start) || storeys.find((s) => s.role === 'lobby') || order[0];
  for (const s of storeys) s.group.visible = false; // one floor at a time
  enter(first, first.role === 'lobby' ? 'entrance' : 'lift');
  // No effect on arrival: the walk simply opens on the finished rooms.

  if (photoState === 'loading') {
    const show = (k) => { loadingBar.style.width = `${Math.round(k * 100)}%`; };
    show(job.k);
    job.listen = show;
    job.promise.then((p) => {
      if (gone) { p.dispose(); return; }
      photo = p;
      for (const entry of halls.values()) dressHall(entry, p);
      photoState = 'on';
      loadingText.textContent = 'Real materials on';
      loadTimer = setTimeout(() => {
        loading.classList.add('aw-faded');
        loadTimer = setTimeout(() => { loading.hidden = true; }, 700);
      }, 900);
      ctx.wake(3);
    }, (error) => {
      if (gone) return;
      photoState = 'failed';
      loading.hidden = true;
      console.warn('Arnheim: the real materials did not load, so the drawn ones stay.', error);
    });
  }

  // For tests: whether a spot on this floor stops the walker, and the squares they can reach from where they stand.
  const debug = { blocked: (x, z) => blocked(x, z), reach: () => reach(), map: () => map, me: () => ({ x: me.x, z: me.z }) };
  return { update, labels, info, dispose, setNotes: notes.set, debug };
}
