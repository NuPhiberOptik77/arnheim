// The founder's notes in their office. The newest few hang as cards of lit paper on threads from the
// ceiling, where the office puts them (halls.js: in its library, in front of the shelves), and turn a
// little towards whoever comes near. A soft pool of light in front of each card is where to stand to
// read it. The page gives the notes (building.setNotes); walk-notes.js opens them in full. Nothing here
// reads anything by itself.
import * as THREE from '../../vendor/three/three.module.js';
import { decal, rng } from './kit.js';

export const MOST = 8; // cards that hang at once: the newest notes
const LONGEST = 20000; // characters of a note kept for reading; the rest stays in the original
const CW = 0.5; // a card, in metres
const CH = 0.66;
const PX = 512; // its picture, in pixels
const PY = Math.round((PX * CH) / CW);
const READ = 0.75; // where to stand to read a card: this far in front of it
const NEAR = 0.45; // how close to that spot counts as standing there
const TURN = 0.6; // how far a card turns towards someone, at most
const FONT = '-apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, sans-serif';
const RISE = [0, 0.06, -0.03, 0.05, 0.07, -0.04, 0.02, 0.05]; // each card hangs at its own height

/* ---------- the notes as given, made safe to show ---------- */

// Words only, the newest first, at most MOST of them. A note is { id, title, text, when, pictures,
// locked }: `text` is plain text, `when` when it was last changed (a date, its text, or milliseconds),
// `pictures` how many pictures or files it holds that are not shown here.
export function tidyNotes(list) {
  if (!Array.isArray(list)) return [];
  const out = [];
  const ids = new Set();
  list.forEach((n, i) => {
    if (!n || typeof n !== 'object') return;
    let text = typeof n.text === 'string' ? n.text.replace(/\r\n?|[\u2028\u2029]/g, '\n').replace(/[\ufffc\u0000]/g, '') : '';
    let title = (typeof n.title === 'string' ? n.title : '').replace(/\s+/g, ' ').trim();
    const first = text.trim().split('\n')[0].trim();
    if (!title) title = first || 'Untitled';
    if ([...title].length > 200) title = `${[...title].slice(0, 199).join('')}…`;
    // A note's first line is usually its title: no need to say it twice.
    if (first && first === title) text = text.trim().split('\n').slice(1).join('\n');
    text = text.replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').replace(/^\n+/, '').trimEnd();
    const cut = text.length > LONGEST || !!n.cut;
    if (text.length > LONGEST) text = `${text.slice(0, LONGEST).trimEnd()}…`;
    const t = n.when instanceof Date ? n.when.getTime() : typeof n.when === 'number' ? n.when : Date.parse(n.when);
    let id = String(n.id ?? `note-${i}`);
    if (ids.has(id)) id = `${id}#${i}`;
    ids.add(id);
    out.push({
      id, title, text, cut, when: Number.isFinite(t) ? t : null,
      pictures: Math.max(0, Math.floor(Number(n.pictures) || 0)), locked: !!n.locked,
    });
  });
  out.sort((a, b) => (b.when ?? 0) - (a.when ?? 0));
  return out.slice(0, MOST);
}

// "Today", "Yesterday", a weekday this week, then the date.
export function dayName(when, now = Date.now()) {
  if (when == null) return '';
  const d = new Date(when);
  const today = new Date(now);
  today.setHours(0, 0, 0, 0);
  const day = new Date(d);
  day.setHours(0, 0, 0, 0);
  const ago = Math.round((today - day) / 86400000);
  if (ago === 0) return 'Today';
  if (ago === 1) return 'Yesterday';
  if (ago > 1 && ago < 7) return d.toLocaleDateString(undefined, { weekday: 'long' });
  const year = d.getFullYear() === today.getFullYear() ? {} : { year: 'numeric' };
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', ...year });
}

export function timeOf(when) {
  return when == null ? '' : new Date(when).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
}

/* ---------- a card's face ---------- */

// Breaks text into lines that fit `width`, at most `most` of them; the last ends in … if there was more.
function wrap(g, text, width, most) {
  const out = [];
  const fits = (s) => g.measureText(s).width <= width;
  const full = (s) => { out.push(s); return out.length > most; };
  done: for (const para of text.split('\n')) {
    if (!para.trim()) {
      if (out.length && out[out.length - 1] !== '' && full('')) break;
      continue;
    }
    let line = '';
    for (const word of para.trim().split(/\s+/)) {
      const next = line ? `${line} ${word}` : word;
      if (fits(next)) { line = next; continue; }
      if (line && full(line)) break done;
      // A word longer than the line breaks where it has to.
      let chars = [...word];
      while (!fits(chars.join(''))) {
        let lo = 1;
        let hi = chars.length;
        while (lo < hi) {
          const mid = (lo + hi + 1) >> 1;
          if (fits(chars.slice(0, mid).join(''))) lo = mid;
          else hi = mid - 1;
        }
        if (full(chars.slice(0, lo).join(''))) break done;
        chars = chars.slice(lo);
      }
      line = chars.join('');
    }
    if (line && full(line)) break;
  }
  const more = out.length > most;
  const lines = out.slice(0, most);
  while (lines.length && lines[lines.length - 1] === '') lines.pop();
  if (more && lines.length) {
    let last = lines[lines.length - 1];
    while (last && !fits(`${last}…`)) last = [...last].slice(0, -1).join('');
    lines[lines.length - 1] = `${last.trimEnd()}…`;
  }
  return { lines, more };
}

function seedOf(text) {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 16777619);
  return (h >>> 0) % 100000 + 1;
}

// Dark ink on warm paper: the day it was last changed, the title as large as fits, and as much of the
// note as the card holds.
function paint(canvas, note, now) {
  const g = canvas.getContext('2d');
  const { width: w, height: h } = canvas;
  const paper = g.createLinearGradient(0, 0, 0, h);
  paper.addColorStop(0, '#fdf8ee');
  paper.addColorStop(1, '#efe3cf');
  g.fillStyle = paper;
  g.fillRect(0, 0, w, h);
  const rand = rng(seedOf(note.id));
  for (let i = 0; i < 240; i++) {
    g.fillStyle = `rgba(120, 90, 60, ${0.02 + rand() * 0.04})`;
    g.fillRect(rand() * w, rand() * h, 1 + rand() * 8, 1);
  }
  const pad = 40;
  const inner = w - pad * 2;
  g.textBaseline = 'alphabetic';
  let y = 58;
  const day = dayName(note.when, now);
  if (day) {
    g.font = `600 21px ${FONT}`;
    g.fillStyle = '#9b8064';
    g.fillText(day.toUpperCase(), pad, y);
  }
  y += 18;
  let size = 44;
  let title;
  for (;;) {
    g.font = `700 ${size}px ${FONT}`;
    title = wrap(g, note.title, inner, 3);
    if (!title.more || size <= 30) break;
    size -= 3;
  }
  g.fillStyle = '#2b221a';
  for (const line of title.lines) {
    y += Math.round(size * 1.14);
    g.fillText(line, pad, y);
  }
  y += 24;
  g.fillStyle = 'rgba(155, 128, 100, .5)';
  g.fillRect(pad, y, 46, 3);
  y += 14;
  const tag = note.locked ? 'Locked' : note.pictures ? `${note.pictures} ${note.pictures === 1 ? 'picture' : 'pictures'}` : '';
  const foot = tag ? h - 66 : h - 36;
  const step = 35;
  g.font = `400 25px ${FONT}`;
  const body = note.locked ? { lines: [], more: false } : wrap(g, note.text, inner, Math.max(0, Math.floor((foot - y) / step)));
  g.fillStyle = '#54473b';
  for (const line of body.lines) {
    y += step;
    g.fillText(line, pad, y);
  }
  if (tag) {
    g.font = `600 20px ${FONT}`;
    g.fillStyle = '#9b8064';
    g.fillText(tag, pad, h - 34);
  }
}

/* ---------- the cards, hung in the office ---------- */

// `at` says where they hang: `slots`, a place for each card with the newest first, as { x, z, turn }
// (turn: which way the card faces, as a turn about the vertical; 0 faces +z), the cards' height y and
// the ceiling they hang from (high). Returns the group to add to the office and what the walk needs.
export function createNoteCards(at) {
  const { slots, y: cy, high } = at;
  const group = new THREE.Group();
  const backM = new THREE.MeshBasicMaterial({ color: new THREE.Color('#ffd8a8').multiplyScalar(1.7) });
  const box = new THREE.BoxGeometry(CW + 0.03, CH + 0.03, 0.01);
  const face = new THREE.PlaneGeometry(CW, CH);
  const pickBox = new THREE.BoxGeometry(CW + 0.12, CH + 0.12, 0.14);
  const pickM = new THREE.MeshBasicMaterial();
  const poolM = (color, opacity) => {
    const d = decal(1, 1, 0, 0, { color, opacity, add: true }); // kit.js keeps one material per look
    d.geometry.dispose();
    return d.material;
  };
  const poolIdle = poolM('#ffcf96', 0.16);
  const poolLit = poolM('#ffd9a8', 0.5);
  const threadPos = new Float32Array(MOST * 6);
  const threadGeo = new THREE.BufferGeometry();
  threadGeo.setAttribute('position', new THREE.BufferAttribute(threadPos, 3));
  const threadM = new THREE.LineBasicMaterial({ color: '#d9c7ae', transparent: true, opacity: 0.3 });
  const threads = new THREE.LineSegments(threadGeo, threadM);
  threads.frustumCulled = false;
  group.add(threads);

  const cards = slots.slice(0, MOST).map((slot, i) => {
    const { x, z } = slot;
    const y = cy + RISE[i % RISE.length];
    const rest = slot.turn || 0;
    const fx = Math.sin(rest);
    const fz = Math.cos(rest);
    // Its pool of light is as wide as the room beside it allows.
    const room = Math.min(1, ...slots.filter((o) => o !== slot).map((o) => Math.hypot(o.x - x, o.z - z)));
    const canvas = document.createElement('canvas');
    canvas.width = PX;
    canvas.height = PY;
    const tex = new THREE.CanvasTexture(canvas);
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.anisotropy = 8;
    const faceM = new THREE.MeshBasicMaterial({ map: tex });
    const holder = new THREE.Group();
    holder.position.set(x, y, z);
    holder.rotation.y = rest;
    const back = new THREE.Mesh(box, backM);
    const front = new THREE.Mesh(face, faceM);
    front.position.z = 0.0056;
    const pick = new THREE.Mesh(pickBox, pickM);
    pick.visible = false;
    pick.userData = { hit: true, stay: true, note: null };
    holder.add(back, front, pick);
    const sx = x + fx * READ;
    const sz = z + fz * READ;
    const pool = decal(room * 0.92, 0.95, x + fx * 0.48, z + fz * 0.48, { color: '#ffcf96', opacity: 0.16, add: true, y: 0.016 });
    pool.material = poolIdle;
    threadPos.set([x, y + CH / 2 + 0.015, z, x, high, z], i * 6);
    const card = { i, holder, back, front, pick, pool, canvas, tex, faceM, x, z, rest, yaw: rest, spot: { x: sx, z: sz }, note: null, key: '' };
    pick.userData.card = card;
    return card;
  });
  threadGeo.attributes.position.needsUpdate = true;

  // Hangs these notes (tidied, newest first): a card for each, repainted only when its note changed.
  function set(notes, now = Date.now()) {
    const shown = [];
    cards.forEach((card, i) => {
      const note = notes[i] || null;
      card.note = note;
      card.pick.userData.note = note;
      card.pick.userData.title = note?.title || '';
      if (!note) {
        card.holder.removeFromParent();
        card.pool.removeFromParent();
        card.key = '';
        return;
      }
      const key = [note.id, note.when, note.title, note.text.slice(0, 900), note.pictures, note.locked, dayName(note.when, now)].join('\u0001');
      if (key !== card.key) {
        paint(card.canvas, note, now);
        card.tex.needsUpdate = true;
        card.key = key;
      }
      if (!card.holder.parent) group.add(card.holder, card.pool);
      shown.push(card);
    });
    threadGeo.setDrawRange(0, shown.length ? (shown[shown.length - 1].i + 1) * 2 : 0);
    return shown;
  }

  // The card whose pool of light (x, z) stands in, if any.
  function standing(x, z) {
    let best = null;
    let gap = NEAR;
    for (const card of cards) {
      if (!card.note) continue;
      const d = Math.hypot(x - card.spot.x, z - card.spot.z);
      if (d < gap) { gap = d; best = card; }
    }
    return best;
  }

  let lit = null;
  function light(card) {
    if (card === lit) return;
    if (lit) lit.pool.material = poolIdle;
    lit = card;
    if (card) card.pool.material = poolLit;
  }

  // Each card turns a little towards someone coming near, and back when they go; true while any moves.
  function update(dt, me, still) {
    let busy = false;
    const k = 1 - Math.exp(-dt * 3.2);
    for (const card of cards) {
      if (!card.note) continue;
      let goal = card.rest;
      if (!still) {
        const dx = me.x - card.x;
        const dz = me.z - card.z;
        const d = Math.hypot(dx, dz);
        const off = Math.atan2(Math.sin(Math.atan2(dx, dz) - card.rest), Math.cos(Math.atan2(dx, dz) - card.rest));
        if (d < 3.2 && Math.abs(off) < 1.5) goal = card.rest + THREE.MathUtils.clamp(off, -TURN, TURN) * Math.min(1, (3.2 - d) / 2);
      }
      const gap = goal - card.yaw;
      if (still || Math.abs(gap) < 0.002) card.yaw = goal;
      else { card.yaw += gap * k; busy = true; }
      card.holder.rotation.y = card.yaw;
    }
    return busy;
  }

  function dispose() {
    group.removeFromParent();
    for (const card of cards) {
      card.tex.dispose();
      card.faceM.dispose();
      card.pool.geometry.dispose();
    }
    for (const x of [box, face, pickBox, threadGeo, backM, pickM, threadM]) x.dispose();
  }

  return { group, cards, set, standing, light, update, dispose };
}
