// Walking the building in first person. The building lends its scene, camera and floors; this
// adds the halls (three/halls.js), the controls on the page, the lift and the burn between floors
// (three/burn.js), and gives everything back when the walk ends. It loads only when someone walks.
import * as THREE from '../vendor/three/three.module.js';
import { createBurn } from './three/burn.js';
import { buildHall } from './three/halls.js';
import { D, H, W } from './three/rooms.js';

const EYE = 1.62;
const WALK = 1.5; // metres a second
const RUN = 3;
const RADIUS = 0.22; // how close you can come to a wall
const CELL = 0.2; // the floor plan that stops you is drawn in squares this size
const STRIDE = 0.74;
const QUIET_MS = 4000; // the hand-held drift fades this long after the last touch
const CURB = 0.14;
const MOVES = new Set(['KeyW', 'KeyA', 'KeyS', 'KeyD', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'ShiftLeft', 'ShiftRight']);

const CSS = `
.arnheim-walking canvas { touch-action: none; }
.aw-hud { position: absolute; z-index: 5; top: 10px; left: 10px; right: 10px; display: flex; align-items: center; justify-content: space-between; gap: 8px; pointer-events: none; }
.aw-hud > *, .aw-picker, .aw-card { pointer-events: auto; }
.aw-btn { display: inline-flex; align-items: center; justify-content: center; gap: 6px; min-width: 40px; min-height: 40px; padding: 0 14px; border-radius: 12px; border: 1px solid rgba(255, 255, 255, .22); background: rgba(14, 16, 24, .68); color: #f7f2ea; font: 600 14px/1.1 -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, sans-serif; cursor: pointer; -webkit-backdrop-filter: blur(8px); backdrop-filter: blur(8px); }
.aw-btn:hover { background: rgba(14, 16, 24, .86); }
.aw-btn:disabled { cursor: default; }
.aw-btn:focus-visible { outline: 2px solid #ffcf8f; outline-offset: 2px; }
.aw-floor { display: inline-flex; align-items: center; gap: 4px; min-width: 0; }
.aw-name { display: inline-block; min-width: 0; max-width: 42vw; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; line-height: 40px; }
.aw-picker { position: absolute; z-index: 6; top: 60px; left: 50%; transform: translateX(-50%); width: min(290px, calc(100% - 24px)); padding: 12px; border-radius: 16px; background: rgba(14, 16, 24, .86); border: 1px solid rgba(255, 214, 170, .32); color: #f7f2ea; box-shadow: 0 12px 34px rgba(0, 0, 0, .45); -webkit-backdrop-filter: blur(10px); backdrop-filter: blur(10px); }
.aw-picker p { margin: 0 0 8px; font: 600 13px/1.3 -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, sans-serif; color: #e6d9c8; }
.aw-picker ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; }
.aw-picker .aw-btn { width: 100%; justify-content: flex-start; }
.aw-picker .aw-btn[aria-current] { border-color: #ffcf8f; color: #ffd9a8; }
.aw-card { position: absolute; z-index: 5; top: 60px; left: 50%; transform: translateX(-50%); width: min(380px, calc(100% - 24px)); display: flex; align-items: center; gap: 10px; padding: 10px 10px 10px 14px; border-radius: 14px; background: rgba(14, 16, 24, .84); border: 1px solid rgba(255, 255, 255, .2); color: #f7f2ea; box-shadow: 0 10px 30px rgba(0, 0, 0, .4); -webkit-backdrop-filter: blur(10px); backdrop-filter: blur(10px); font: 14px/1.35 -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, sans-serif; }
.aw-card > div { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.aw-card span { font-size: 13px; color: #d6dbe6; overflow-wrap: anywhere; }
.aw-picker[hidden], .aw-card[hidden], .aw-card span[hidden] { display: none; }
.aw-help { position: absolute; z-index: 4; right: 12px; bottom: 12px; max-width: min(420px, calc(100% - 24px)); margin: 0; font: 13px/1.4 -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, sans-serif; color: #f6f0e8; text-shadow: 0 1px 3px rgba(0, 0, 0, .85); pointer-events: none; transition: opacity 1s; }
.aw-help.aw-faded { opacity: 0; }
.aw-stick { position: absolute; z-index: 5; left: 20px; bottom: 24px; width: 120px; height: 120px; border-radius: 50%; background: rgba(14, 16, 24, .36); border: 1px solid rgba(255, 255, 255, .3); touch-action: none; display: none; }
.aw-stick span { position: absolute; left: 50%; top: 50%; width: 52px; height: 52px; margin: -26px 0 0 -26px; border-radius: 50%; background: rgba(255, 238, 220, .85); box-shadow: 0 2px 10px rgba(0, 0, 0, .35); pointer-events: none; }
@media (pointer: coarse) { .aw-stick { display: block; } .aw-help { left: 156px; bottom: 28px; } }
@media (max-width: 820px) { .arnheim-walking { position: fixed !important; inset: 0 !important; width: auto !important; height: auto !important; min-height: 0 !important; z-index: 50; } }
@media (prefers-reduced-motion: reduce) { .aw-help { transition: none; } }
`;

export function createWalk(ctx) {
  const { scene, camera, canvas, renderer, storeys, reduced } = ctx;
  const stage = canvas.parentElement;
  const coarse = window.matchMedia('(pointer: coarse)').matches;
  const still = () => reduced.matches;
  const listeners = new AbortController();
  const { signal } = listeners;
  const burn = createBurn(scene, { count: coarse || stage.clientWidth < 820 ? 20000 : 46000 });
  const hitMaterial = new THREE.MeshBasicMaterial();
  const halls = new Map();
  const ray = new THREE.Raycaster();
  const ndc = new THREE.Vector2();
  const v = new THREE.Vector3();
  const ahead = new THREE.Vector3();
  const order = [...storeys].sort((a, b) => b.y - a.y); // top floor first
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

  if (!document.getElementById('arnheim-walk-style')) {
    const style = document.createElement('style');
    style.id = 'arnheim-walk-style';
    style.textContent = CSS;
    document.head.append(style);
  }
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
  card.append(cardText, button('Open', () => ctx.leave(), 'Leave the walk and open this in the list'));
  const help = el('p', 'aw-help', coarse
    ? 'Walk with the stick and drag to look. Tap the floor to go there, or something to open it. Double-tap to burn this floor and rebuild it.'
    : 'WASD or the arrow keys to walk, Shift to hurry, drag to look. Click the floor to go there, or something to open it. Double-click to burn this floor and rebuild it. Esc to leave.');
  const stickEl = el('div', 'aw-stick');
  const knob = el('span');
  stickEl.append(knob);
  stickEl.setAttribute('aria-hidden', 'true');
  stage.append(hud, picker, card, help, stickEl);
  stage.classList.add('arnheim-walking');
  const helpTimer = setTimeout(() => help.classList.add('aw-faded'), 9000);

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

  function showCard(hit) {
    const info = ctx.describe(hit) || {};
    cardTitle.textContent = info.title || hit.title || '';
    cardSub.textContent = info.sub || '';
    cardSub.hidden = !cardSub.textContent;
    card.hidden = false;
    clearTimeout(cardTimer);
    cardTimer = setTimeout(() => { card.hidden = true; }, 7000);
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
    entry = buildHall(s, { company: ctx.org.company, mission: ctx.org.mission });
    const person = ctx.personRoom;
    if (entry.poe && person?.storey === s) {
      const P = person.spec.person;
      const hit = new THREE.Mesh(new THREE.BoxGeometry(0.8, 1.1, 0.6), hitMaterial);
      hit.position.set(entry.poe.x, 1.05, entry.poe.z);
      hit.visible = false;
      hit.userData = { hit: true, floorId: person.floorId, roomId: person.roomId, href: P.href, title: P.name, sub: 'The receptionist. Tap to talk.' };
      entry.group.add(hit);
      entry.picks.push(hit);
    }
    halls.set(s.id, entry);
    return entry;
  }

  // The rooms open onto the hall: no front walls, and a full wall at the far end.
  function setWalls(s, on) {
    for (const r of s.rooms) r.walls.s.visible = !on;
    const last = s.rooms[s.rooms.length - 1];
    if (last) last.walls.e.scale.y = on ? H : CURB;
  }

  // Poe stands behind the reception desk while you walk, and goes back to their room after.
  function placePoe(on) {
    const room = ctx.personRoom;
    if (!room?.person || room.storey !== here || !hall?.poe) return;
    const P = room.spec.person;
    const body = room.person.group;
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
    placePoe(true);
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
    hall.lift.open = 0;
    hall.setDoors(0);
    inLift = hall.inLift(me.x, me.z);
    floorName.textContent = s.label;
    const p = s.group.position;
    ctx.shadows(new THREE.Vector3(p.x + (hall.west + hall.east) / 2, p.y + 1, p.z + hall.front / 2), Math.max(hall.east - hall.west, hall.front) / 2 + 2);
  }

  function leave(s) {
    setWalls(s, false);
    placePoe(false);
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
    const z0 = -0.4;
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
    if (thing && (!surface || thing.distance <= surface.distance + 0.3)) {
      const hit = thing.object.userData;
      if (hit.lift) { openPicker(); return; }
      showCard(hit);
      ctx.onPick?.({ ...hit, walk: true });
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
    if (!ride && ctx.version() !== seen && now - surveyed > 1500) look();

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
      const dx = me.target.x - me.x;
      const dz = me.target.z - me.z;
      const dist = Math.hypot(dx, dz);
      if (dist < 0.12) me.target = null;
      else {
        const pace = Math.min(WALK, 0.3 + dist * 1.4);
        wx = (dx / dist) * pace;
        wz = (dz / dist) * pace;
        let face = Math.atan2(-dx, -dz) - me.yawGoal;
        face = Math.atan2(Math.sin(face), Math.cos(face));
        if (dist > 0.6) me.yawGoal += face * Math.min(1, dt * 2.4);
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
    }
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
    return busy;
  }

  // Names over the nearest open rooms, and Poe's, for the building's label layer.
  function labels() {
    if (!here || ride) return [];
    const out = [];
    camera.getWorldDirection(ahead);
    for (const room of here.rooms) {
      ctx.roomWorld(room, v, W / 2, H - 0.3, D + 0.02);
      const d = v.distanceTo(camera.position);
      if (d > 16 || v.sub(camera.position).normalize().dot(ahead) < 0.35 || !inView(room.g.position.x + W / 2, D + 0.02)) continue;
      out.push({ key: `w:${room.key}`, title: room.label, sub: ctx.infoText(room.info), kind: room.mood, align: 'center', room, local: [W / 2, H - 0.3, D + 0.02], rank: d });
    }
    const person = ctx.personRoom;
    if (hall.poe && person?.storey === here) {
      const p = here.group.position;
      v.set(p.x + hall.poe.x, p.y + 2.05, p.z + hall.poe.z);
      if (v.distanceTo(camera.position) < 12 && inView(hall.poe.x, hall.poe.z)) out.push({ key: 'w:poe', title: person.spec.person.name, sub: 'Receptionist', kind: 'quiet', align: 'center', at: v.toArray(), rank: 0 });
    }
    return out.sort((a, b) => a.rank - b.rank).slice(0, 5);
  }

  // Where the walker is, for tests.
  function info() {
    const r2 = (n) => Math.round(n * 100) / 100;
    return {
      floor: here?.id, x: r2(me.x), z: r2(me.z), yaw: r2(me.yaw), speed: r2(me.speed), riding: ride?.phase || null,
      burning: burn.active, points: burn.count, inLift, doors: r2(hall?.lift.open || 0), picker: !picker.hidden, card: card.hidden ? null : cardTitle.textContent,
    };
  }

  function dispose() {
    listeners.abort();
    clearTimeout(cardTimer);
    clearTimeout(helpTimer);
    if (here) { placePoe(false); setWalls(here, false); }
    for (const entry of halls.values()) {
      entry.group.removeFromParent();
      entry.dispose();
    }
    halls.clear();
    burn.dispose();
    hitMaterial.dispose();
    for (const node of [hud, picker, card, help, stickEl]) node.remove();
    stage.classList.remove('arnheim-walking');
    here = null;
  }

  /* ---------- start: at the reception's door, or at the lift of the floor in view ---------- */

  const first = storeys.find((s) => s.id === ctx.start) || storeys.find((s) => s.role === 'lobby') || order[0];
  for (const s of storeys) s.group.visible = false; // one floor at a time
  enter(first, first.role === 'lobby' ? 'entrance' : 'lift');
  if (!still()) {
    ride = { to: here, same: true, phase: 'in', t: 0 };
    here.group.visible = false;
    const eye = chest(new THREE.Vector3());
    burn.start({ root: here.group, origin: eye, inward: true, eye });
  }

  return { update, labels, info, dispose };
}
