// Shows Arnheim's building floor by floor with its light baked by Cycles: every surface carries its own light in a
// texture, so the page draws it without lamps. Drag to look round, use the arrow keys or WASD to walk, the floor
// buttons to go up or down, and the room buttons to stand where each room's photograph was taken.
import * as THREE from '../../vendor/three/three.module.js';

// the building's floors, lowest first; a floor that has not been baked yet is left out
const FLOORS = [
  { id: 'lobby', name: 'Ground floor: the lobby', base: '../out/viewer/lobby/' },
  { id: 'studio', name: 'First floor: the Studio project', base: '../out/viewer/' },
];
const JOBS = {
  RECEPTION: 'Reception: the receptionist at the desk, the company\'s name and mission behind her, a screen for each of its websites.',
  GOALS: "Goals: a flag for each goal on the wall, red while open, gold once reached.",
  WORK: 'Work: a desk for each task.',
  CONVERSATIONS: 'Conversations: a seat for each chat where the work is talked through.',
  CODE: 'Code: open changes as books, copies with unsaved work as crates.',
  COMPANY: 'Company: a filing cabinet each for money, legal, subscriptions and key dates.',
};

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
renderer.toneMapping = THREE.NoToneMapping; // the bake already went through the photos' view transform
renderer.outputColorSpace = THREE.SRGBColorSpace;
document.body.prepend(renderer.domElement);

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(70, innerWidth / innerHeight, 0.05, 2000);
window.studio = { scene, camera, renderer }; // for checking the page from the browser's console
camera.rotation.order = 'YXZ';
let yaw = 0;
let pitch = 0;

function hfovToVfov(lensMm) {
  const h = 2 * Math.atan(18 / lensMm);
  return THREE.MathUtils.radToDeg(2 * Math.atan(Math.tan(h / 2) / camera.aspect));
}

async function bin(f, name) {
  const res = await fetch(f.base + name + f.stamp);
  if (!res.ok) throw new Error(`${name}: ${res.status}`);
  return res.arrayBuffer();
}

// Loads one floor into a group of its own (once), with its view out of the windows.
async function loadFloor(f) {
  if (f.group) return f;
  const floor = f.manifest;
  f.stamp = `?v=${floor.baked || Date.now()}`; // the bake's time, so a browser never mixes files from two bakes out of its cache
  f.group = new THREE.Group();
  const loader = new THREE.TextureLoader();
  if (floor.outside) {
    f.sky = await loader.loadAsync(f.base + floor.outside.image + f.stamp);
    f.sky.mapping = THREE.EquirectangularReflectionMapping;
    f.sky.colorSpace = THREE.SRGBColorSpace;
  }
  for (const g of floor.groups) {
    const buf = await bin(f, g.bin);
    const n = g.vertices;
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(buf, 0, n * 3), 3));
    geo.setAttribute('uv', new THREE.BufferAttribute(new Float32Array(buf, n * 12, n * 2), 2));
    geo.setIndex(new THREE.BufferAttribute(new Uint32Array(buf, n * 20, g.indices), 1));
    const map = await loader.loadAsync(f.base + g.image + f.stamp);
    map.colorSpace = THREE.SRGBColorSpace;
    map.anisotropy = renderer.capabilities.getMaxAnisotropy();
    f.group.add(new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ map })));
  }
  if (floor.glass) {
    const buf = await bin(f, floor.glass.bin);
    const n = floor.glass.vertices;
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(buf, 0, n * 3), 3));
    geo.setIndex(new THREE.BufferAttribute(new Uint32Array(buf, n * 12, floor.glass.indices), 1));
    f.group.add(new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: 0xdfe8ec, transparent: true, opacity: 0.07, depthWrite: false, side: THREE.DoubleSide })));
  }
  scene.add(f.group);
  return f;
}

let floors = [];
const floorButtons = [];

// Shows one floor: its rooms, its view out, and a button for each of its photographs' places.
async function show(f) {
  document.getElementById('what').textContent = `Loading ${f.name.toLowerCase()}.`;
  await loadFloor(f);
  floors.forEach((o) => { if (o.group) o.group.visible = o === f; });
  scene.background = f.sky || null;
  floorButtons.forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.floor === f.id)));
  document.getElementById('where').textContent = f.name;
  const rooms = document.getElementById('rooms');
  rooms.replaceChildren();
  const buttons = [];
  f.manifest.cameras.forEach((c, i) => {
    const b = document.createElement('button');
    b.textContent = c.room.charAt(0) + c.room.slice(1).toLowerCase();
    b.onclick = () => { stand(c); buttons.forEach((x) => x.setAttribute('aria-pressed', String(x === b))); };
    rooms.append(b);
    buttons.push(b);
    if (i === 0) b.click();
  });
  if (location.hash.slice(1) !== f.id) history.replaceState(null, '', `#${f.id}`);
}

async function load() {
  const found = await Promise.all(FLOORS.map(async (f) => {
    try {
      const res = await fetch(f.base + 'floor.json', { cache: 'no-cache' });
      return res.ok ? { ...f, manifest: await res.json() } : null;
    } catch { return null; }
  }));
  floors = found.filter(Boolean);
  if (!floors.length) throw new Error('no floor has been baked yet');
  const bar = document.getElementById('floors');
  for (const f of [...floors].reverse()) { // the top floor first, the way a lift's buttons read
    const b = document.createElement('button');
    b.textContent = f.name.split(':')[0];
    b.dataset.floor = f.id;
    b.onclick = () => show(f);
    bar.append(b);
    floorButtons.push(b);
  }
  await show(floors.find((f) => f.id === location.hash.slice(1)) || floors[0]);
}

function stand(c) {
  camera.position.set(...c.at);
  const d = new THREE.Vector3(c.look[0] - c.at[0], 0, c.look[2] - c.at[2]);
  yaw = Math.atan2(-d.x, -d.z);
  pitch = 0;
  camera.fov = hfovToVfov(c.lens_mm || 16);
  camera.updateProjectionMatrix();
  document.getElementById('what').textContent = JOBS[c.room] || c.room;
}

// look round by dragging, walk with the keys
let drag = null;
renderer.domElement.addEventListener('pointerdown', (e) => { drag = { x: e.clientX, y: e.clientY }; renderer.domElement.setPointerCapture(e.pointerId); });
renderer.domElement.addEventListener('pointermove', (e) => {
  if (!drag) return;
  yaw += (e.clientX - drag.x) * 0.004;
  pitch = THREE.MathUtils.clamp(pitch + (e.clientY - drag.y) * 0.004, -1.2, 1.2);
  drag = { x: e.clientX, y: e.clientY };
});
renderer.domElement.addEventListener('pointerup', () => { drag = null; });
const keys = new Set();
addEventListener('keydown', (e) => keys.add(e.key.toLowerCase()));
addEventListener('keyup', (e) => keys.delete(e.key.toLowerCase()));
addEventListener('resize', () => {
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
});

const clock = new THREE.Clock();
renderer.setAnimationLoop(() => {
  const dt = Math.min(clock.getDelta(), 0.05);
  const fwd = (keys.has('w') || keys.has('arrowup') ? 1 : 0) - (keys.has('s') || keys.has('arrowdown') ? 1 : 0);
  const side = (keys.has('d') || keys.has('arrowright') ? 1 : 0) - (keys.has('a') || keys.has('arrowleft') ? 1 : 0);
  if (fwd || side) {
    const v = new THREE.Vector3(side, 0, -fwd).normalize().multiplyScalar(1.4 * dt).applyAxisAngle(new THREE.Vector3(0, 1, 0), yaw);
    camera.position.add(v);
  }
  camera.rotation.set(pitch, yaw, 0);
  renderer.render(scene, camera);
});

load().catch((e) => { document.getElementById('what').textContent = `Could not load the baked floors: ${e.message}`; });
