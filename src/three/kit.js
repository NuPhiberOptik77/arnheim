// Small modelling kit: cached materials, primitive helpers and procedural floor textures.
// Adapted from House Control by 0xProbability, MIT licence: see THIRD_PARTY_NOTICES.md.
// Added here: a material "scope" per room, so each room's own lamp lights that room and
// nothing else, however many rooms there are, and decals and merging to keep draw calls low.
import * as THREE from '../../vendor/three/three.module.js';
import { RoundedBoxGeometry } from '../../vendor/three/addons/geometries/RoundedBoxGeometry.js';
import { mergeGeometries } from '../../vendor/three/addons/utils/BufferGeometryUtils.js';

const shared = new Map();
let scope = null;

export function newScope() {
  return {
    materials: new Map(),
    uniforms: {
      uLampPos: { value: new THREE.Vector3() }, uLampCol: { value: new THREE.Color(0, 0, 0) },
      uLamp2Pos: { value: new THREE.Vector3() }, uLamp2Col: { value: new THREE.Color(0, 0, 0) },
    },
  };
}
export function useScope(next) { scope = next; }

// Two local lamps added to the standard lighting, for this room's materials only.
function lit(m) {
  if (!scope) return m;
  const u = scope.uniforms;
  m.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, u);
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', `#include <common>
uniform vec3 uLampPos; uniform vec3 uLampCol; uniform vec3 uLamp2Pos; uniform vec3 uLamp2Col;
vec3 roomLamp(vec3 pos, vec3 col, vec3 n, vec3 viewPos, vec3 albedo) {
  vec3 to = (viewMatrix * vec4(pos, 1.0)).xyz + viewPos;
  float d2 = dot(to, to);
  float wrap = clamp((dot(n, to / sqrt(d2)) + 0.3) / 1.3, 0.0, 1.0);
  return col * wrap / (0.7 + d2 * 0.42) * albedo * RECIPROCAL_PI;
}`)
      .replace('#include <lights_fragment_end>', `#include <lights_fragment_end>
reflectedLight.directDiffuse += roomLamp(uLampPos, uLampCol, normal, vViewPosition, material.diffuseContribution);
reflectedLight.directDiffuse += roomLamp(uLamp2Pos, uLamp2Col, normal, vViewPosition, material.diffuseContribution);
reflectedLight.indirectDiffuse += (uLampCol + uLamp2Col) * 0.012 * material.diffuseContribution;`);
  };
  m.customProgramCacheKey = () => 'room-lamp';
  return m;
}

export function mat(color, { rough = 0.85, metal = 0, emissive = null, emissiveIntensity = 1, opacity = 1 } = {}) {
  const key = [color, rough, metal, emissive, emissiveIntensity, opacity].join('|');
  const cache = scope ? scope.materials : shared;
  let m = cache.get(key);
  if (!m) {
    m = new THREE.MeshStandardMaterial({ color, roughness: rough, metalness: metal });
    if (emissive) {
      m.emissive = new THREE.Color(emissive);
      m.emissiveIntensity = emissiveIntensity;
      m.userData.baseEmissive = emissiveIntensity;
    }
    if (opacity < 1) { m.transparent = true; m.opacity = opacity; }
    lit(m);
    cache.set(key, m);
  }
  return m;
}

// A lamp body whose glow the world drives every frame.
export function lampGlow() {
  return lit(new THREE.MeshStandardMaterial({ color: '#8d8f96', roughness: 0.6, emissive: '#000000' }));
}

/* ---------- soft decals: contact shadows under furniture, small pools of light ---------- */

let softTexture = null;
const decals = new Map();
function soft() {
  if (!softTexture) {
    const c = document.createElement('canvas');
    c.width = c.height = 128;
    const g = c.getContext('2d');
    const fill = g.createRadialGradient(64, 64, 4, 64, 64, 64);
    fill.addColorStop(0, 'rgba(255,255,255,1)');
    fill.addColorStop(0.55, 'rgba(255,255,255,.55)');
    fill.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = fill;
    g.fillRect(0, 0, 128, 128);
    softTexture = new THREE.CanvasTexture(c);
    softTexture.colorSpace = THREE.SRGBColorSpace;
  }
  return softTexture;
}

export function decal(w, d, x, z, { color = '#000000', opacity = 0.4, add = false, y = 0.014 } = {}) {
  const key = [color, opacity, add].join('|');
  let m = decals.get(key);
  if (!m) {
    m = new THREE.MeshBasicMaterial({
      map: soft(), color, opacity, transparent: true, depthWrite: false,
      blending: add ? THREE.AdditiveBlending : THREE.NormalBlending,
    });
    decals.set(key, m);
  }
  const geo = new THREE.PlaneGeometry(w, d);
  geo.rotateX(-Math.PI / 2);
  const mesh = new THREE.Mesh(geo, m);
  mesh.position.set(x, y, z);
  mesh.userData.flat = true;
  return mesh;
}

// Merges everything under root by material, so a room is a handful of draw calls.
// Meshes marked live (they move) or hit (invisible pick boxes) are left alone.
export function freeze(root) {
  root.updateMatrixWorld(true);
  const inverse = new THREE.Matrix4().copy(root.matrixWorld).invert();
  const relative = new THREE.Matrix4();
  const buckets = new Map();
  const merged = [];
  root.traverse((o) => {
    if (!o.isMesh || o.userData.live || o.userData.hit || Array.isArray(o.material)) return;
    const flat = o.userData.flat || o.material.transparent === true;
    const key = `${o.material.uuid}${flat ? 'f' : 's'}`;
    if (!buckets.has(key)) buckets.set(key, { material: o.material, flat, geos: [] });
    const geo = o.geometry.index ? o.geometry.toNonIndexed() : o.geometry.clone();
    geo.applyMatrix4(relative.multiplyMatrices(inverse, o.matrixWorld));
    for (const name of Object.keys(geo.attributes)) {
      if (!['position', 'normal', 'uv'].includes(name)) geo.deleteAttribute(name);
    }
    buckets.get(key).geos.push(geo);
    merged.push(o);
  });
  for (const o of merged) { o.parent.remove(o); o.geometry.dispose(); }
  for (const { material, flat, geos } of buckets.values()) {
    const mesh = new THREE.Mesh(mergeGeometries(geos, false), material);
    for (const g of geos) g.dispose();
    mesh.castShadow = !flat;
    mesh.receiveShadow = !flat;
    root.add(mesh);
  }
}

export function disposeTree(root) {
  root.traverse((o) => { if (o.isMesh || o.isInstancedMesh) o.geometry?.dispose?.(); });
}

// Box standing on y = 0, centred on x/z.
export function box(w, h, d, material, { r = 0.02 } = {}) {
  const radius = Math.max(0, Math.min(r, Math.min(w, h, d) / 2 - 0.001));
  const geo = radius > 0.002 ? new RoundedBoxGeometry(w, h, d, radius >= 0.04 ? 2 : 1, radius) : new THREE.BoxGeometry(w, h, d);
  geo.translate(0, h / 2, 0);
  return new THREE.Mesh(geo, material);
}

// Cylinder standing on y = 0.
export function cyl(rTop, rBottom, h, material, seg = 28) {
  const geo = new THREE.CylinderGeometry(rTop, rBottom, h, seg);
  geo.translate(0, h / 2, 0);
  return new THREE.Mesh(geo, material);
}

export function at(mesh, x = 0, y = 0, z = 0) {
  mesh.position.set(x, y, z);
  return mesh;
}

export function shadows(root, cast = true, receive = true) {
  root.traverse((o) => {
    if (o.isMesh) { o.castShadow = cast; o.receiveShadow = receive; }
  });
  return root;
}

// Deterministic pseudo-random so a plan always renders identically.
export function rng(seed) {
  let s = seed >>> 0 || 1;
  return () => {
    s = (s + 0x6d2b79f5) | 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/* ---------- floor textures ---------- */

const TILE = 2.4; // metres covered by one texture repeat

function canvasTexture(size, draw) {
  const c = document.createElement('canvas');
  c.width = c.height = size;
  draw(c.getContext('2d'), size);
  const tex = new THREE.CanvasTexture(c);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8;
  return tex;
}

function shade(hex, amount) {
  const c = new THREE.Color(hex);
  const hsl = {};
  c.getHSL(hsl);
  c.setHSL(hsl.h, hsl.s, Math.min(1, Math.max(0, hsl.l + amount)));
  return `#${c.getHexString()}`;
}

function planks(base) {
  return canvasTexture(1024, (g, s) => {
    const rand = rng(base.length * 97 + base.charCodeAt(3));
    const rows = 16;
    const rh = s / rows;
    for (let r = 0; r < rows; r++) {
      let x = -rand() * s * 0.5;
      while (x < s) {
        const len = s * (0.35 + rand() * 0.35);
        g.fillStyle = shade(base, (rand() - 0.5) * 0.09);
        g.fillRect(x, r * rh, len, rh);
        g.fillStyle = 'rgba(0,0,0,0.28)';
        g.fillRect(x, r * rh, 1.5, rh);
        // faint grain
        g.strokeStyle = 'rgba(0,0,0,0.05)';
        for (let k = 0; k < 3; k++) {
          const y = r * rh + rand() * rh;
          g.beginPath(); g.moveTo(x, y); g.lineTo(x + len, y + (rand() - 0.5) * 3); g.stroke();
        }
        x += len;
      }
      g.fillStyle = 'rgba(0,0,0,0.3)';
      g.fillRect(0, r * rh, s, 1.5);
    }
  });
}

function tiles(base, perSide, grout) {
  return canvasTexture(512, (g, s) => {
    const rand = rng(perSide * 31 + base.charCodeAt(2));
    const t = s / perSide;
    g.fillStyle = grout;
    g.fillRect(0, 0, s, s);
    for (let i = 0; i < perSide; i++) {
      for (let j = 0; j < perSide; j++) {
        g.fillStyle = shade(base, (rand() - 0.5) * 0.05);
        g.fillRect(i * t + 2, j * t + 2, t - 4, t - 4);
      }
    }
  });
}

const FLOORS = {
  oak: () => planks('#c7a47c'),
  walnut: () => planks('#94705a'),
  greywood: () => planks('#8e9095'),
  tile: () => tiles('#d5dade', 4, '#aab0b8'),
  stone: () => tiles('#a2a7ae', 3, '#7c828b'),
  slate: () => tiles('#4b4e52', 3, '#3b3d41'),
};

const floorTextures = new Map();

export function floorMaterial(kind) {
  const name = FLOORS[kind] ? kind : 'oak';
  if (!floorTextures.has(name)) floorTextures.set(name, FLOORS[name]());
  const key = `floor:${name}`;
  const cache = scope ? scope.materials : shared;
  if (!cache.has(key)) {
    cache.set(key, lit(new THREE.MeshStandardMaterial({
      map: floorTextures.get(name),
      roughness: name === 'tile' || name === 'stone' || name === 'slate' ? 0.55 : 0.75,
    })));
  }
  return cache.get(key);
}

// Floor quad whose UVs are in world metres, so every room shares one texture scale.
export function floorMesh(room, kind) {
  const geo = new THREE.PlaneGeometry(room.w, room.d);
  geo.rotateX(-Math.PI / 2);
  geo.translate(room.x + room.w / 2, 0, room.z + room.d / 2);
  const pos = geo.attributes.position;
  const uv = geo.attributes.uv;
  for (let i = 0; i < pos.count; i++) uv.setXY(i, pos.getX(i) / TILE, pos.getZ(i) / TILE);
  const mesh = new THREE.Mesh(geo, floorMaterial(kind));
  mesh.receiveShadow = true;
  return mesh;
}
