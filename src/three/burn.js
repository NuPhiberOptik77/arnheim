// The burn between floors: a floor turns into glowing points that spread out from one spot and
// drift up and away, then the next floor gathers back out of points the same way. The points are
// sampled from the floor's own shapes and drawn in a single call, about twenty thousand of them
// on a phone. Nothing is downloaded.
import * as THREE from '../../vendor/three/three.module.js';

const FADE = 0.35; // seconds the points take to give way to the solid floor after gathering

const VERTEX = /* glsl */ `
attribute vec3 tint;
attribute float seed;
uniform float uTime;
uniform float uSpeed;
uniform float uLife;
uniform float uIn;
uniform float uScale;
uniform float uSize;
uniform float uFade;
uniform vec3 uOrigin;
varying vec3 vColor;
varying float vAlpha;
void main() {
  float d = distance(position, uOrigin);
  float k = clamp((uTime - d / uSpeed - seed * 0.2) / uLife, 0.0, 1.0);
  float e = uIn > 0.5 ? 1.0 - k : k;
  vec3 away = normalize(position - uOrigin + vec3(0.0, 0.4, 0.0));
  vec3 swirl = vec3(sin(seed * 91.7 + e * 5.0), 0.0, cos(seed * 57.3 + e * 4.0));
  vec3 rise = vec3(0.0, 1.0 + seed * 1.8, 0.0);
  vec3 p = position + (away * (0.5 + seed) + swirl * 0.45 + rise) * (e * e * 1.7);
  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  gl_Position = projectionMatrix * mv;
  float heat = smoothstep(0.0, 0.1, e) * (1.0 - smoothstep(0.25, 0.85, e));
  vColor = mix(tint, vec3(2.8, 1.25, 0.42), heat);
  vAlpha = (1.0 - smoothstep(0.55, 1.0, e)) * uFade;
  gl_PointSize = min(64.0, uSize * (1.0 + heat * 1.4) * uScale / max(0.1, -mv.z));
}`;

const FRAGMENT = /* glsl */ `
varying vec3 vColor;
varying float vAlpha;
void main() {
  vec2 c = gl_PointCoord - 0.5;
  float r = dot(c, c);
  if (r > 0.25 || vAlpha < 0.01) discard;
  gl_FragColor = vec4(vColor, vAlpha * (1.0 - smoothstep(0.12, 0.25, r)));
}`;

const A = new THREE.Vector3();
const B = new THREE.Vector3();
const C = new THREE.Vector3();
const P = new THREE.Vector3();
const Q = new THREE.Vector3();

function corner(geometry, f, matrix) {
  const pos = geometry.attributes.position;
  const idx = geometry.index;
  const i = f * 3;
  A.fromBufferAttribute(pos, idx ? idx.getX(i) : i).applyMatrix4(matrix);
  B.fromBufferAttribute(pos, idx ? idx.getX(i + 1) : i + 1).applyMatrix4(matrix);
  C.fromBufferAttribute(pos, idx ? idx.getX(i + 2) : i + 2).applyMatrix4(matrix);
}

// The colour a point takes from its material: the base colour, plus a little of any glow.
function tintOf(m) {
  const c = new THREE.Color();
  if (m.map) c.setRGB(0.42, 0.36, 0.3);
  else if (m.color) c.copy(m.color);
  else c.setRGB(0.6, 0.6, 0.6);
  if (m.emissive && m.emissiveIntensity > 0) c.add(new THREE.Color().copy(m.emissive).multiplyScalar(Math.min(2.5, m.emissiveIntensity) * 0.5));
  return c.multiplyScalar(0.8);
}

// Points spread over the surfaces under root, more of them on big surfaces and near the eye.
// The root itself may be hidden (a floor that is about to gather); its children are read as shown.
function sample(root, origin, eye, count) {
  root.updateMatrixWorld(true);
  const meshes = [];
  const visit = (o, top) => {
    if (!top && !o.visible) return;
    if (o.isMesh && !o.userData.hit) {
      const m = Array.isArray(o.material) ? o.material[0] : o.material;
      if (m && m.colorWrite !== false && (!m.transparent || o.userData.solid)) meshes.push({ mesh: o, color: tintOf(m) });
    }
    for (const child of o.children) visit(child, false);
  };
  visit(root, true);
  let tris = 0;
  for (const it of meshes) {
    const g = it.mesh.geometry;
    it.first = tris;
    it.n = Math.floor((g.index ? g.index.count : g.attributes.position.count) / 3);
    tris += it.n;
  }
  const cum = new Float64Array(tris);
  const owner = new Uint32Array(tris);
  let total = 0;
  meshes.forEach((it, k) => {
    for (let f = 0; f < it.n; f++) {
      corner(it.mesh.geometry, f, it.mesh.matrixWorld);
      const area = P.subVectors(B, A).cross(Q.subVectors(C, A)).length() * 0.5;
      const dx = (A.x + B.x + C.x) / 3 - eye.x;
      const dy = (A.y + B.y + C.y) / 3 - eye.y;
      const dz = (A.z + B.z + C.z) / 3 - eye.z;
      total += area / (1 + (dx * dx + dy * dy + dz * dz) / 64);
      cum[it.first + f] = total;
      owner[it.first + f] = k;
    }
  });
  const positions = new Float32Array(count * 3);
  const tints = new Float32Array(count * 3);
  const seeds = new Float32Array(count);
  let reach = 1;
  let made = 0;
  if (total > 0) {
    for (let i = 0; i < count; i++) {
      const r = Math.random() * total;
      let lo = 0;
      let hi = tris - 1;
      while (lo < hi) {
        const mid = (lo + hi) >> 1;
        if (cum[mid] < r) lo = mid + 1;
        else hi = mid;
      }
      const it = meshes[owner[lo]];
      corner(it.mesh.geometry, lo - it.first, it.mesh.matrixWorld);
      let u = Math.random();
      let w = Math.random();
      if (u + w > 1) { u = 1 - u; w = 1 - w; }
      P.copy(A).addScaledVector(Q.subVectors(B, A), u).addScaledVector(Q.subVectors(C, A), w);
      positions[i * 3] = P.x;
      positions[i * 3 + 1] = P.y;
      positions[i * 3 + 2] = P.z;
      const shade = 0.85 + Math.random() * 0.3;
      tints[i * 3] = it.color.r * shade;
      tints[i * 3 + 1] = it.color.g * shade;
      tints[i * 3 + 2] = it.color.b * shade;
      seeds[i] = Math.random();
      reach = Math.max(reach, P.distanceTo(origin));
      made += 1;
    }
  }
  return { positions, tints, seeds, reach, made };
}

export function createBurn(scene, { count = 30000 } = {}) {
  const uniforms = {
    uTime: { value: 0 }, uSpeed: { value: 10 }, uLife: { value: 0.62 }, uIn: { value: 0 }, uScale: { value: 500 },
    uSize: { value: 0.045 }, uFade: { value: 1 }, uOrigin: { value: new THREE.Vector3() },
  };
  const material = new THREE.ShaderMaterial({ uniforms, vertexShader: VERTEX, fragmentShader: FRAGMENT, transparent: true, depthWrite: false });
  const points = new THREE.Points(new THREE.BufferGeometry(), material);
  points.frustumCulled = false;
  points.visible = false;
  points.renderOrder = 5;
  scene.add(points);
  const size = new THREE.Vector2();
  let length = 0;
  let fading = 0;
  let running = false;
  let made = 0;

  // Burn root away from origin (inward false), or gather it out of points towards origin (true).
  function start({ root, origin, inward, eye }) {
    const s = sample(root, origin, eye || origin, count);
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(s.positions, 3));
    geo.setAttribute('tint', new THREE.BufferAttribute(s.tints, 3));
    geo.setAttribute('seed', new THREE.BufferAttribute(s.seeds, 1));
    points.geometry.dispose();
    points.geometry = geo;
    made = s.made;
    uniforms.uOrigin.value.copy(origin);
    uniforms.uSpeed.value = Math.max(5, s.reach / 0.8);
    uniforms.uIn.value = inward ? 1 : 0;
    uniforms.uTime.value = 0;
    uniforms.uFade.value = 1;
    length = s.reach / uniforms.uSpeed.value + 0.2 + uniforms.uLife.value;
    fading = inward ? FADE : 0;
    running = true;
    points.visible = true;
  }

  // Moves the burn on; true while there is anything to draw.
  function update(dt, camera, renderer) {
    if (!points.visible) return false;
    renderer.getDrawingBufferSize(size);
    uniforms.uScale.value = size.y / (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2));
    if (running) {
      uniforms.uTime.value += dt;
      if (uniforms.uTime.value >= length) running = false;
    } else if (fading > 0) {
      fading = Math.max(0, fading - dt);
      uniforms.uFade.value = fading / FADE;
    } else points.visible = false;
    return true;
  }

  return {
    start,
    update,
    get running() { return running; },
    get active() { return points.visible; },
    get count() { return made; },
    dispose() {
      points.removeFromParent();
      points.geometry.dispose();
      material.dispose();
    },
  };
}
