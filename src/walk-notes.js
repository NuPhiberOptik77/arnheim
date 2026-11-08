// Reading the founder's notes on a walk. The cards hang in the office (three/notes.js); this opens one
// in full in a reading card when someone taps it or stands in its light, closes it when they walk on
// or press Esc, and asks the page for fresh notes when someone comes into the office and every few
// minutes while they stay. The page answers with building.setNotes; nothing here reads anything else.
import { createNoteCards, dayName, timeOf, tidyNotes } from './three/notes.js';

const STAND = 0.45; // seconds standing in a card's light before it opens
const SLOW = 0.35; // metres a second: slower than this counts as standing
const LEAVE = 0.95; // a note opened by standing closes once its reader is this far from the spot
const FRESH = 120; // seconds between asking for fresh notes while someone stays in the office

// The reading card's look is notes.css, added as a stylesheet link (not a <style> tag), as walk.css is.
let styled = null;
function loadStyle() {
  if (styled) return styled;
  const link = document.createElement('link');
  link.id = 'arnheim-notes-style';
  link.rel = 'stylesheet';
  link.href = new URL('./notes.css', import.meta.url).href;
  styled = new Promise((resolve) => {
    link.addEventListener('load', resolve, { once: true });
    link.addEventListener('error', resolve, { once: true });
    setTimeout(resolve, 4000);
  });
  document.head.append(link);
  return styled;
}

// stage: the element the walk's controls sit in. notes: what to hang to begin with. ask(): the page is
// asked for fresh notes. hideCard(): the walk's own card steps aside. remap(): the walk looks at the
// office again after the cards change. wake(n): draw a few frames.
export function createWalkNotes({ stage, signal, coarse = false, notes: given = [], ask, hideCard, remap, wake }) {
  loadStyle();
  let notes = tidyNotes(given);
  let cards = null;
  let hall = null;
  let shown = [];
  let inside = false;
  let open = null; // { id, how: 'tap' or 'stand' }
  let standCard = null;
  let standT = 0;
  let armed = false; // standing in a card's light opens it once per arrival
  let hinted = false;
  let hintTimer = 0;
  let refresh = 0;

  const el = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  };
  const button = (text, label, onClick) => {
    const b = el('button', 'aw-note-btn', text);
    b.type = 'button';
    b.setAttribute('aria-label', label);
    b.title = label;
    b.addEventListener('click', onClick, { signal });
    return b;
  };
  const panel = el('section', 'aw-note');
  panel.hidden = true;
  panel.setAttribute('role', 'dialog');
  panel.setAttribute('aria-labelledby', 'aw-note-title');
  const when = el('time');
  const title = el('h2');
  title.id = 'aw-note-title';
  const heading = el('div');
  heading.append(when, title);
  const newer = button('‹', 'Newer note', () => step(-1));
  const older = button('›', 'Older note', () => step(1));
  const shut = button('×', 'Close the note', () => closeNote());
  const tools = el('div', 'aw-note-tools');
  tools.append(newer, older, shut);
  const head = el('header');
  head.append(heading, tools);
  const text = el('div', 'aw-note-text');
  text.tabIndex = 0; // so the keys can scroll a long note
  const more = el('p', 'aw-note-more');
  panel.append(head, text, more);
  const hint = el('p', 'aw-note-hint');
  hint.hidden = true;
  hint.setAttribute('role', 'status');
  stage.append(panel, hint);

  // Esc closes the note before it would end the walk.
  window.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape' || panel.hidden) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    closeNote();
  }, { capture: true, signal });

  const cardOf = (id) => shown.find((c) => c.note.id === id) || null;

  function fill(note) {
    when.textContent = [dayName(note.when), timeOf(note.when)].filter(Boolean).join(', ');
    when.dateTime = note.when == null ? '' : new Date(note.when).toISOString();
    title.textContent = note.title;
    text.textContent = note.locked ? '' : note.text;
    text.hidden = !text.textContent;
    const bits = [];
    if (note.locked) bits.push('This note is locked, so its words stay in the original.');
    else if (!note.text && !note.pictures) bits.push('Nothing written under the title yet.');
    if (note.pictures) bits.push(`${note.pictures} ${note.pictures === 1 ? 'picture or file is' : 'pictures or files are'} not shown here.`);
    if (note.cut) bits.push('The rest is in the original note.');
    more.textContent = bits.join(' ');
    more.hidden = !bits.length;
    const i = notes.findIndex((n) => n.id === note.id);
    newer.disabled = i <= 0;
    older.disabled = i < 0 || i >= notes.length - 1;
  }

  function openNote(id, how) {
    const note = notes.find((n) => n.id === id);
    if (!note) return false;
    if (open?.id !== id) text.scrollTop = 0;
    open = { id, how };
    fill(note);
    panel.hidden = false;
    hint.hidden = true;
    hideCard?.();
    wake?.(2);
    return true;
  }

  function closeNote() {
    if (!open) return;
    open = null;
    panel.hidden = true;
    wake?.(2);
  }

  function step(dir) {
    const i = notes.findIndex((n) => n.id === open?.id);
    if (i >= 0 && notes[i + dir]) openNote(notes[i + dir].id, 'tap');
  }

  function showHint() {
    hinted = true;
    hint.textContent = `The newest notes hang here. ${coarse ? 'Tap' : 'Click'} one to read it, or stand in its light.`;
    hint.classList.remove('aw-faded');
    hint.hidden = false;
    clearTimeout(hintTimer);
    hintTimer = setTimeout(() => {
      hint.classList.add('aw-faded');
      hintTimer = setTimeout(() => { hint.hidden = true; }, 700);
    }, 6500);
  }

  // The cards that hang now, and the walk's list of things a tap can land on.
  function place() {
    shown = cards.set(notes);
    hall.picks = hall.picks.filter((p) => !p.userData.card).concat(shown.map((c) => c.pick));
  }

  // The office was built: hang the cards in it.
  function hang(entry) {
    if (!entry.notes) return;
    hall = entry;
    cards = createNoteCards(entry.notes);
    entry.group.add(cards.group);
    place();
  }

  // Fresh notes from the page.
  function set(list) {
    notes = tidyNotes(list);
    if (cards) {
      place();
      remap?.();
      if (open) {
        const note = notes.find((n) => n.id === open.id);
        if (note) fill(note);
        else closeNote();
      }
      if (inside && !hinted && shown.length) showHint();
    }
    wake?.(2);
  }

  function enter(on) {
    inside = on;
    clearInterval(refresh);
    standCard = null;
    armed = false;
    if (!on) {
      closeNote();
      cards?.light(null);
      hint.hidden = true;
      return;
    }
    ask?.();
    refresh = setInterval(() => ask?.(), FRESH * 1000);
    if (!hinted && shown.length) showHint();
  }

  // A tap the walk saw: a card opens its note; anything else closes an open one. True if it was a card.
  function tap(hit) {
    const card = hit?.card;
    if (card?.note && openNote(card.note.id, 'tap')) return true;
    closeNote();
    return false;
  }

  // Each frame, with where the walker is: the cards turn, and standing in a card's light opens it.
  function update(dt, me, office, still) {
    if (office !== inside) enter(office);
    if (!cards || !office) return false;
    let busy = cards.update(dt, me, still);
    const card = cards.standing(me.x, me.z);
    if (card !== standCard) {
      standCard = card;
      standT = 0;
      armed = !!card;
    }
    if (card && armed && me.speed < SLOW) {
      standT += dt;
      if (standT >= STAND) {
        armed = false;
        if (open?.id !== card.note.id) openNote(card.note.id, 'stand');
      }
    }
    if (armed) busy = true; // frames keep coming while the short wait runs
    if (open?.how === 'stand') {
      const c = cardOf(open.id);
      if (!c || Math.hypot(me.x - c.spot.x, me.z - c.spot.z) > LEAVE) closeNote();
    }
    cards.light(card || (open ? cardOf(open.id) : null));
    return busy;
  }

  // For tests: how many hang and where (in the floor's own frame, like the walker), which is open and
  // how, and whose light the walker stands in.
  function info() {
    const r2 = (n) => Math.round(n * 100) / 100;
    return {
      hung: shown.length, open: open?.id || null, how: open?.how || null, lit: standCard?.note.id || null,
      cards: shown.map((c) => [r2(c.x), r2(c.holder.position.y), r2(c.z)]), spots: shown.map((c) => [r2(c.spot.x), r2(c.spot.z)]),
    };
  }

  function dispose() {
    clearInterval(refresh);
    clearTimeout(hintTimer);
    cards?.dispose();
    cards = null;
    panel.remove();
    hint.remove();
  }

  return { hang, set, tap, update, info, dispose };
}
