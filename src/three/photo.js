// Real materials for the walk: a photographed terrazzo floor, white oak and plaster, and the light
// of a real entrance hall for soft reflections on glass, stone and metal. All CC0, from Poly Haven
// (see THIRD_PARTY_NOTICES.md), about 6 MB in all. They load only once someone starts walking,
// never with the page, and a device short of memory keeps the drawn materials instead.
import * as THREE from '../../vendor/three/three.module.js';

const BASE = new URL('../../vendor/polyhaven/', import.meta.url);

// Each set of pictures, and how many metres of wall or floor one copy of them covers. Oak takes on
// the colour each piece was drawn in; terrazzo keeps its own, a little lighter; plaster keeps the
// drawn paint and lends only its surface (the relief and the gloss), at bump strength.
const SETS = {
  terrazzo: { name: 'terrazzo_tiles', metres: 2, own: 1.25 },
  oak: { name: 'white_oak_veneer', metres: 0.5 },
  plaster: { name: 'white_plaster_02', metres: 2, paint: true, bump: 0.4 },
};
const SKY = 'entrance_hall_1k.hdr';
const FILES = Object.values(SETS).reduce((n, s) => n + (s.paint ? 2 : 3), 1);
// How much of the real hall's light each kind shows: little on matt and polished stone, a lot on
// metal and glass, which look flat without something to reflect.
const SHEEN = { terrazzo: 0.3, oak: 0.25, plaster: 0.15, stone: 0.25, metal: 0.9 };

// Whether this device gets the real materials: not with ?lite in the address, not with data saver
// on, and not on a device short of memory or with a small graphics chip.
export function photoWanted(renderer) {
  try {
    if (new URLSearchParams(location.search).has('lite')) return false;
    if (navigator.connection?.saveData) return false;
    if (navigator.deviceMemory && navigator.deviceMemory < 4) return false;
    return renderer.capabilities.maxTextureSize >= 4096;
  } catch {
    return false;
  }
}

const toLinear = (v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);

// The average colour of a picture, in linear light, read from a small copy of it.
function average(image, srgb) {
  const c = document.createElement('canvas');
  c.width = c.height = 16;
  const g = c.getContext('2d', { willReadFrequently: true });
  g.imageSmoothingQuality = 'high';
  g.drawImage(image, 0, 0, 16, 16);
  const d = g.getImageData(0, 0, 16, 16).data;
  const sum = [0, 0, 0];
  for (let i = 0; i < d.length; i += 4) {
    for (let k = 0; k < 3; k++) sum[k] += srgb ? toLinear(d[i + k] / 255) : d[i + k] / 255;
  }
  return sum.map((s) => Math.max(0.02, s / 256));
}

// Reads a Radiance .hdr picture (run-length coded RGBE scanlines, as Poly Haven makes them) into a
// half-float texture the graphics chip can filter.
function readHDR(buffer) {
  const bytes = new Uint8Array(buffer);
  let pos = 0;
  const line = () => {
    const start = pos;
    while (pos < bytes.length && bytes[pos] !== 10) pos += 1;
    pos += 1;
    return String.fromCharCode(...bytes.subarray(start, pos - 1));
  };
  if (!line().startsWith('#?')) throw new Error('not a Radiance picture');
  for (let l = line(); l !== ''; l = line()) if (pos >= bytes.length) throw new Error('no picture after the header');
  const size = /^-Y (\d+) \+X (\d+)/.exec(line());
  if (!size) throw new Error('an unexpected Radiance layout');
  const height = Number(size[1]);
  const width = Number(size[2]);
  const half = THREE.DataUtils.toHalfFloat;
  const one = half(1);
  const data = new Uint16Array(width * height * 4);
  const row = new Uint8Array(width * 4);
  for (let y = 0; y < height; y++) {
    if (bytes[pos] !== 2 || bytes[pos + 1] !== 2 || ((bytes[pos + 2] << 8) | bytes[pos + 3]) !== width) throw new Error('an unsupported Radiance coding');
    pos += 4;
    for (let c = 0; c < 4; c++) {
      for (let x = 0; x < width;) {
        if (pos >= bytes.length) throw new Error('the picture ends early');
        let n = bytes[pos++];
        if (n > 128) {
          const b = bytes[pos++];
          for (n -= 128; n > 0 && x < width; n--) row[4 * x++ + c] = b;
        } else {
          for (; n > 0 && x < width; n--) row[4 * x++ + c] = bytes[pos++];
        }
      }
    }
    for (let x = 0; x < width; x++) {
      const e = row[4 * x + 3];
      const f = e ? 2 ** (e - 136) : 0;
      const i = 4 * (y * width + x);
      data[i] = half(row[4 * x] * f);
      data[i + 1] = half(row[4 * x + 1] * f);
      data[i + 2] = half(row[4 * x + 2] * f);
      data[i + 3] = one;
    }
  }
  const tex = new THREE.DataTexture(data, width, height, THREE.RGBAFormat, THREE.HalfFloatType);
  tex.colorSpace = THREE.LinearSRGBColorSpace;
  tex.mapping = THREE.EquirectangularReflectionMapping;
  tex.minFilter = tex.magFilter = THREE.LinearFilter;
  tex.generateMipmaps = false;
  tex.flipY = true;
  tex.needsUpdate = true;
  return tex;
}

// Loads every picture, telling onProgress how far along it is (0 to 1). Resolves with the sets and
// the hall's light; rejects if anything fails, and the walk then keeps its drawn materials.
export async function loadPhoto(renderer, onProgress = () => {}) {
  let done = 0;
  const tick = () => onProgress(++done / FILES);
  const sharp = Math.min(8, renderer.capabilities.getMaxAnisotropy());
  const loader = new THREE.TextureLoader();
  const owned = [];
  const picture = async (file, srgb) => {
    const t = await loader.loadAsync(new URL(file, BASE).href);
    owned.push(t);
    t.wrapS = t.wrapT = THREE.RepeatWrapping;
    t.anisotropy = sharp;
    if (srgb) t.colorSpace = THREE.SRGBColorSpace;
    tick();
    return t;
  };
  const sky = fetch(new URL(SKY, BASE)).then((r) => {
    if (!r.ok) throw new Error(`${SKY} answered ${r.status}`);
    return r.arrayBuffer();
  });
  sky.catch(() => {}); // seen below; this only stops an early failure being reported twice
  try {
    const sets = {};
    await Promise.all(Object.entries(SETS).map(async ([key, s]) => {
      const [normal, rough, map] = await Promise.all([
        picture(`${s.name}_nor_gl_1k.jpg`), picture(`${s.name}_rough_1k.jpg`), s.paint ? null : picture(`${s.name}_diff_1k.jpg`, true),
      ]);
      sets[key] = { ...s, map, normal, rough, avg: map ? average(map.image, true) : null, avgRough: average(rough.image, false)[1] };
    }));
    const equirect = readHDR(await sky);
    tick();
    const pmrem = new THREE.PMREMGenerator(renderer);
    const target = pmrem.fromEquirectangular(equirect);
    equirect.dispose();
    pmrem.dispose();
    return {
      sets,
      env: target.texture,
      dispose() {
        for (const t of owned) t.dispose();
        target.dispose();
      },
    };
  } catch (error) {
    for (const t of owned) t.dispose();
    throw error;
  }
}

// Texture coordinates in metres for a merged hall mesh: each triangle takes them from the side it
// faces, so a picture keeps its real size on every wall, floor and slat.
function metreUV(geo, metres) {
  const pos = geo.attributes.position;
  const nor = geo.attributes.normal;
  const uv = new Float32Array(pos.count * 2);
  for (let i = 0; i + 2 < pos.count; i += 3) {
    let nx = 0;
    let ny = 0;
    let nz = 0;
    for (let k = i; k < i + 3; k++) { nx += nor.getX(k); ny += nor.getY(k); nz += nor.getZ(k); }
    const ax = Math.abs(nx);
    const ay = Math.abs(ny);
    const az = Math.abs(nz);
    for (let k = i; k < i + 3; k++) {
      const x = pos.getX(k) / metres;
      const y = pos.getY(k) / metres;
      const z = pos.getZ(k) / metres;
      if (ay >= ax && ay >= az) uv.set([x, z], 2 * k);
      else if (ax >= az) uv.set([z, y], 2 * k);
      else uv.set([x, y], 2 * k);
    }
  }
  geo.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
}

// Dresses what a hall marked for it (halls.js sets material.userData.photo): plaster, oak and
// terrazzo get the real pictures, keeping on average the gloss they were drawn with; 'stone' and
// 'metal' things only gain the real hall's reflections.
export function dressHall(hall, photo) {
  hall.group.traverse((o) => {
    if (!o.isMesh || Array.isArray(o.material) || o.userData.dressed) return;
    const m = o.material;
    const kind = m.userData.photo;
    if (!kind) return;
    o.userData.dressed = true;
    const set = photo.sets[kind];
    if (set) {
      if (o.geometry.index) {
        const old = o.geometry;
        o.geometry = old.toNonIndexed();
        old.dispose();
      }
      metreUV(o.geometry, set.metres);
    }
    if (m.userData.dressed) return;
    m.userData.dressed = true;
    if (set) {
      if (set.map) {
        const [r, g, b] = set.avg;
        const base = set.own ? new THREE.Color(r * set.own, g * set.own, b * set.own) : m.userData.base || m.color.clone();
        m.userData.tint = base.clone(); // the colour the burn gives its points
        m.color.setRGB(Math.min(3, base.r / r), Math.min(3, base.g / g), Math.min(3, base.b / b));
        m.map = set.map;
      }
      m.roughness = Math.min(2.5, m.roughness / Math.max(0.05, set.avgRough));
      m.normalMap = set.normal;
      if (set.bump) m.normalScale.set(set.bump, set.bump);
      m.roughnessMap = set.rough;
    }
    m.envMap = photo.env;
    m.envMapIntensity = SHEEN[kind] ?? 0.4;
    m.needsUpdate = true;
  });
}
