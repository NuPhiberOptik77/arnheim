// Poe, the receptionist, at the desk: a greeting, answers to plain questions, a message taken
// down as a task, a short tour of the building and an optional voice.
// No AI and nothing invented: every answer is built from the company map and the plain facts the
// page passes in, by simple keyword matching. When Poe doesn't know, Poe says so.
// A page can teach Poe more without changing this file: its own words (kit.words) and its own
// topics (kit.topics), each a function that answers a question or passes. Poe only changes
// anything if the page hands over addTask and dropTask, and then only adds the task it was asked
// to add, or drops it again on Undo. Poe never merges, publishes, runs jobs or signs in.

const WORDS = {
  // What this place is, and more ways people ask about it.
  place: 'This is Arnheim: a company as a building you can turn and walk through. Each floor is a project and each room holds one kind of thing. The light shows what is happening.',
  placeWords: [],
  // What Arnheim itself is, for a building that has no floor called Arnheim.
  arnheim: [
    'Arnheim is a 3D company world: the company is a building, each project a floor, each kind of work a room, and the live work lights up as it happens.',
    'It is named after Edgar Allan Poe\'s story "The Domain of Arnheim", about a man who shapes a landscape into a world of its own. It is free and open, and never sold.',
  ],
  me: null, // what Poe says about Poe; built below unless a page gives its own
  role: 'Receptionist. Every answer comes from what this building holds.',
  note: 'Poe never merges, publishes, runs jobs or signs in.',
  hints: ['What needs me?', "What's running?", 'What is this place?', 'Where is the website?', 'What do the colours mean?'],
  refuse: null, // built below unless a page gives its own
  unknown: "I don't know that, and I won't guess. I only know what this building holds.",
  helper: null, // who else can take on a task, such as an assistant: "tell <helper> to ..."
  working: '', // how "working now" is decided, said after the count
  queue: 'job queue',
  missionBy: "in its founder's words",
  emailNote: 'I never read an inbox.',
  addHere: '',
  added: 'It is in the Work room now.',
  addedHelper: '',
  scenes: 'The buttons above the building relight it: Everything, Only what needs me, Working now, or one project.',
  keys: null, // the page's keyboard shortcuts, in a sentence
  searchLabel: 'Search for',
};

const REFUSE = / (merge|merging|publish|deploy|tweet|sign in|sign me in|signin|log in|log me in|login|password|run (a |the |my )?(job|command|script|tests?|build)|start (a |the )?(job|build)|post (it|this|that|on|to)|send (an |the |a )?(email|message|post)|buy|pay|transfer) /;
const STOP = new Set(['what', 'where', 'when', 'which', 'about', 'there', 'their', 'this', 'that', 'with', 'from', 'have', 'does', 'show', 'tell', 'anything', 'something', 'thing', 'things', 'please', 'could', 'would', 'should', 'into', 'your', 'mine', 'need', 'needs', 'know', 'want']);
const PRESENCE_WORDS = [['website', ['website', 'site', 'web']], ['email', ['email', 'mail', 'inbox']], ['domain', ['domain']], ['social', ['social', 'handle', 'account']]];
// Words for each kind of room. A room in the company map can add its own with "words".
const ROOM_WORDS = {
  conversations: ['conversation', 'chats'], code: ['code', 'working cop'], company: ['company room', 'money', 'legal', 'subscription', 'key date', 'decisions'],
  library: ['library'], work: ['work room'], goals: ['goals room'],
};
const BADGE = '<svg viewBox="0 0 40 40" aria-hidden="true" focusable="false"><circle cx="20" cy="20" r="20" fill="#f3d9b4"/><path d="M6 40c1-8 6-12 14-12s13 4 14 12z" fill="#2f4a5c"/><path d="M16.5 28l3.5 6 3.5-6z" fill="#efe6d6"/><rect x="17" y="22" width="6" height="7" rx="3" fill="#c8926e"/><ellipse cx="20" cy="17.5" rx="7" ry="8.8" fill="#c8926e"/><path d="M12.7 15.6c-.4-6 3.1-9.4 7.9-9.4 5.3 0 8.7 3.7 8.5 9.5.3 4 .6 7.8-.6 10.6-1.2-3.6-1.6-6.7-1.8-9.7-2.6-.6-5.8-2.4-7.6-5-1.8 2-3.7 3.4-5.6 4.1-.3.1-.5.1-.8-.1z" fill="#3a261f"/><circle cx="17.3" cy="18" r=".95" fill="#241815"/><circle cx="22.7" cy="18" r=".95" fill="#241815"/><path d="M18.4 22.4c1 .6 2.2.6 3.2 0" stroke="#a65f57" stroke-width=".9" fill="none" stroke-linecap="round"/></svg>';

export const count = (n, one, many) => `${n} ${n === 1 ? one : many}`;
export const needWord = (n) => (n === 1 ? '1 thing needs you' : `${n} things need you`);
export const norm = (text) => ` ${String(text).toLowerCase().replace(/['’]/g, '').replace(/[^a-z0-9]+/g, ' ').trim()} `;
export const has = (q, words) => words.some((w) => q.includes(` ${w}`));
export const exact = (q, phrase) => phrase && q.includes(` ${norm(phrase).trim()} `);
// A room's own words: short ones (three letters or fewer) must be whole words.
const roomHas = (q, words) => words.some((w) => (w.length <= 3 ? q.includes(` ${w} `) : q.includes(` ${w}`)));
const escape = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

export function poeBadge(size = 18) {
  const span = document.createElement('span');
  span.className = 'poe-badge';
  span.style.width = `${size}px`;
  span.style.height = `${size}px`;
  span.innerHTML = BADGE; // a fixed drawing, never data
  return span;
}

// Puts topics in after the one with the given id, keeping everything else in order.
export function insertAfter(list, id, more) {
  const at = list.findIndex((t) => t.id === id);
  return at < 0 ? [...list, ...more] : [...list.slice(0, at + 1), ...more, ...list.slice(at + 1)];
}

export function createPoe(kit) {
  const { h, btn, title, row, focusModel, reduced, openSearch, taskHref } = kit;
  const org = kit.org;
  const facts = kit.facts;
  const canAdd = typeof kit.addTask === 'function';
  const W = { ...WORDS, ...(kit.words || {}) };
  const helper = W.helper || null;
  const helperRe = helper ? new RegExp(escape(helper.toLowerCase()), 'i') : null;
  const H = helper ? escape(helper.toLowerCase()) : null;
  const MESSAGE = new RegExp(`^\\s*(?:(?:please|poe|hey poe|ok poe|can you|could you|would you)[\\s,]+)*(remind me (?:to |about |that )?|${H ? `tell ${H} (?:to |that )?|ask ${H} (?:to )?|get ${H} to |have ${H} |` : ''}take a message:?\\s*|take a note:?\\s*|make a note (?:to |that )?|note down |add (?:a )?task:?\\s*(?:to )?|don'?t let me forget (?:to )?)(.*)$`, 'i');
  const me = W.me || [
    "I'm Poe, the receptionist. I can tell you what this place is, what each floor and room is for, what needs you, what's running, where the websites and email are written down, and who runs the company.",
    `${canAdd ? 'I can also take a message: say "remind me to ..." and I will add it as a task. ' : ''}I don't use AI. I only read what this building holds, so when I don't know, I say so.`,
  ];
  const refuse = W.refuse || ["I can't do that. I never merge, publish, run jobs or sign in.", ...(canAdd ? ['I can take it down as a task instead.'] : [])];
  const log = []; // newest first: { you, poe }
  let tour = null;
  let voice = false;
  const canSpeak = typeof window !== 'undefined' && 'speechSynthesis' in window;

  /* ---------- speaking ---------- */

  function speak(text) {
    if (!voice || !canSpeak || !text) return;
    try {
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(new SpeechSynthesisUtterance(text));
    } catch { /* no voice on this machine */ }
  }

  function hello() {
    const hr = new Date().getHours();
    if (hr >= 5 && hr < 12) return 'Good morning';
    if (hr >= 12 && hr < 18) return 'Good afternoon';
    if (hr >= 18 && hr < 23) return 'Good evening';
    return 'Hello';
  }

  function greeting() {
    const f = facts();
    const needs = f.needs || [];
    const first = needs[0];
    const name = kit.greetName?.();
    const said = [`${hello()}${name ? `, ${name}` : ''}.`];
    said.push(first ? `${needWord(needs.length)}. The first is "${first.title}", on ${first.sub}.` : 'Nothing needs you right now.');
    if (f.toCheck?.length) said.push(`${count(f.toCheck.length, 'conversation', 'conversations')} to check.`);
    if (f.working?.length) said.push(`${count(f.working.length, 'conversation is', 'conversations are')} working now.`);
    return { text: said.join(' '), first };
  }

  /* ---------- finding things in a question ---------- */

  const allFloors = () => { const o = org(); return [...o.floors, o.lobby, o.basement].filter(Boolean); };
  const kindOf = (fl, r) => r.kind || (fl === org().basement ? (r.id === 'library' ? 'library' : 'machine') : r.id);
  const wordsFor = (fl, r) => [...(ROOM_WORDS[kindOf(fl, r)] || []), ...(r.words || [])];

  function floorIn(q) {
    const o = org();
    if (o.lobby && has(q, ['lobby', 'reception', 'front desk', norm(o.lobby.label).trim()])) return o.lobby;
    if (o.basement && has(q, ['basement', norm(o.basement.label).trim()])) return o.basement;
    return o.floors.find((f) => exact(q, f.label) || exact(q, f.project) || exact(q, f.id)) || null;
  }
  function roomIn(q, floor) {
    const o = org();
    for (const fl of [o.lobby, o.basement].filter(Boolean)) {
      for (const r of fl.rooms) if (exact(q, `${r.label} room`) || roomHas(q, wordsFor(fl, r))) return { floor: fl, room: r };
    }
    const extra = o.floors.flatMap((fl) => (fl.extraRooms || []).map((r) => ({ floor: fl, room: r })));
    for (const x of extra) if (roomHas(q, wordsFor(x.floor, x.room))) return x;
    for (const r of o.rooms) if (roomHas(q, wordsFor(null, r))) return { floor: floor?.project ? floor : null, room: r };
    return null;
  }

  /* ---------- answers ---------- */

  const go = (href, label = 'Take me there') => href && { label, href };

  function needsAnswer(f, floor) {
    const all = f.needs || [];
    const list = floor?.project ? all.filter((t) => t.sub === floor.project) : all;
    const where = floor?.project ? ` on ${floor.label}` : '';
    const lines = [list.length ? `${needWord(list.length)}${where}.${list.length > 3 ? ' The first three:' : ''}` : `Nothing needs you${where} right now.`];
    if (!floor) {
      if (f.later) lines.push(`${count(f.later, 'more is', 'more are')} put off until later.`);
      if (f.toCheck?.length) lines.push(`${count(f.toCheck.length, 'conversation', 'conversations')} to check.`);
      if (f.withHelper?.length) lines.push(`${count(f.withHelper.length, 'task is', 'tasks are')} with ${helper || 'a helper'}.`);
      if (f.waiting?.length) lines.push(`${count(f.waiting.length, 'task is', 'tasks are')} waiting on something else.`);
    }
    return { lines, links: list.slice(0, 3), go: go(floor?.project ? `#/${floor.id}/work` : '#/') };
  }

  function runningAnswer(f, floor) {
    const all = f.working || [];
    const convos = floor?.project ? all.filter((c) => c.sub === floor.project) : all;
    const lines = [convos.length ? `${count(convos.length, 'conversation is', 'conversations are')} working now${W.working}.` : 'No conversation is working right now.'];
    const queue = f.queue;
    if (queue) {
      if (queue.ok === false) lines.push(`The ${W.queue} could not be read, so I can't say which jobs are running.`);
      else if (queue.ok == null) lines.push(`I am still checking the ${W.queue}.`);
      else if (queue.running.length) lines.push(`${count(queue.running.length, 'job is', 'jobs are')} running: ${queue.running.map((j) => `${j.title} on ${j.sub}`).join(', ')}.`);
      else lines.push('No job is running.');
      if (queue.ok && queue.waiting) lines.push(`${count(queue.waiting, 'job is', 'jobs are')} waiting in the queue.`);
    }
    return { lines, links: convos.slice(0, 3) };
  }

  // "What's happening?": what is working, then what needs you.
  function happeningAnswer(f, floor) {
    const run = runningAnswer(f, floor);
    const need = needsAnswer(f, floor);
    return { lines: [...run.lines, need.lines[0]], links: (run.links || []).slice(0, 3), go: need.go };
  }

  function machinesAnswer(f) {
    const o = org();
    return { lines: (f.machines || []).map((m) => `${m.label}: ${m.big}${m.detail ? `, ${String(m.detail).toLowerCase()}` : ''}.`), go: go(o.basement && `#/${o.basement.id}`) };
  }

  function prAnswer(f) {
    const o = org();
    const prs = f.prs || {};
    const lines = Object.entries(prs).map(([p, n]) => (n == null ? `${p}: the pull requests could not be read.` : `${p}: ${count(n, 'open pull request', 'open pull requests')}.`));
    const first = Object.keys(prs)[0];
    const floor = o.floors.find((x) => x.project === first);
    return { lines: lines.length ? lines : ['No pull requests are read here.'], go: go(floor && `#/${floor.id}/code`) };
  }

  function presenceAnswer(q, f) {
    const all = f.presence || [];
    let list = all.filter((e) => exact(q, e.name));
    let type = null;
    if (!list.length) {
      type = PRESENCE_WORDS.find(([, words]) => has(q, words))?.[0] || null;
      if (!type) return null;
      list = all.filter((e) => e.type === type);
    }
    const o = org();
    if (!o.lobby) return null;
    const roomId = { website: 'websites', email: 'email', domain: 'domains', social: 'social' }[type || list[0].type] || 'websites';
    if (!list.length) return { lines: [`No ${type} is written down in ${o.lobby.label} yet.${W.addHere ? ` ${W.addHere}` : ''}`], go: go(`#/${o.lobby.id}/${roomId}`) };
    const lines = list.slice(0, 4).map((e) => `${e.name}: ${e.link || 'no link written down yet'}. ${e.status || ''}${e.status ? '.' : ''}`.replace(/\.\.$/, '.'));
    if (list.length > 4) lines.push(`And ${count(list.length - 4, 'more', 'more')}.`);
    if ((type || list[0].type) === 'email' && W.emailNote) lines.push(W.emailNote);
    return { lines, links: list.slice(0, 4).map((e) => ({ title: e.name, sub: e.project, href: e.href })), go: go(list.length === 1 ? list[0].href : `#/${o.lobby.id}/${roomId}`) };
  }

  function floorAnswer(fl, f) {
    const o = org();
    const lines = [`${fl.label}: ${fl.about || 'nothing is written about it yet.'}`];
    if (fl.story) lines.push(fl.story);
    if (fl.folder) lines.push(`Its folder is ${fl.folder}.`);
    if (fl.project) {
      const goals = (f.goals || []).filter((g) => g.project === fl.project).length;
      lines.push(`${count(f.openBy?.[fl.project] || 0, 'open task', 'open tasks')}, ${f.needsBy?.[fl.project] || 0} needing you. ${count(goals, 'goal', 'goals')} written.`);
    }
    lines.push(`Rooms: ${[...(fl.rooms || o.rooms), ...(fl.extraRooms || [])].map((r) => r.label).join(', ')}.`);
    return { lines, go: go(`#/${fl.id}`) };
  }

  function roomAnswer(found, f) {
    const { floor, room } = found;
    const lines = [`${room.label}: ${room.about || 'nothing is written about it yet.'}`];
    const machine = (f.machines || []).find((m) => m.id === room.id);
    if (machine) lines.push(`Right now: ${machine.big}${machine.detail ? `, ${String(machine.detail).toLowerCase()}` : ''}.`);
    if (!floor) lines.push('Every project floor has one. Name a project and I will take you to its room.');
    return { lines, go: go(floor ? `#/${floor.id}/${room.id}` : '#/company') };
  }

  function goalsAnswer(floor, f) {
    const all = f.goals || [];
    const list = floor?.project ? all.filter((g) => g.project === floor.project) : all;
    const where = floor?.project ? ` for ${floor.label}` : '';
    if (!list.length) return { lines: [`No open goals are written${where} yet. Goals are only ever written by you.`], go: go(floor?.project && `#/${floor.id}/goals`) };
    return { lines: [`${count(list.length, 'open goal', 'open goals')}${where}.`], links: list.slice(0, 5), go: go(floor?.project && `#/${floor.id}/goals`) };
  }

  function unknown(text, f) {
    const words = norm(text).trim().split(' ').filter((w) => w.length >= 4 && !STOP.has(w));
    const o = org();
    const pool = [...(f.tasks || []), ...(f.goals || []), ...(f.presence || []).map((e) => ({ title: e.name, sub: o.lobby?.label, href: e.href }))];
    const hits = words.length ? pool.filter((x) => words.some((w) => norm(x.title).includes(` ${w}`))).slice(0, 4) : [];
    if (hits.length) return { lines: ["I don't have a ready answer for that. These mention it:"], links: hits, search: text };
    return { lines: [W.unknown], search: text };
  }

  function messageOffer(rest, who) {
    if (!canAdd) return { lines: ["I can't take messages here, so nothing was written down."] };
    const text = String(rest || '').trim().replace(/[.!?\s]+$/, '').slice(0, 200);
    if (!text) return { lines: ['What should the message say? Try "remind me to ..." with the words after it.'] };
    const taskTitle = text[0].toUpperCase() + text.slice(1);
    const guess = floorIn(norm(text));
    return {
      lines: [`I can add "${taskTitle}" as a task ${helper && who === helper ? `for ${helper}` : 'for you'}. Which project is it for?`],
      offer: { title: taskTitle, who, guess: guess?.project || null, state: null },
    };
  }

  // The questions Poe knows, in the order they are tried. Each answers or passes (null).
  const TOPICS = [
    { id: 'refuse', answer: (c) => REFUSE.test(c.q) && { lines: refuse, task: canAdd, taskText: c.text } },
    { id: 'greeting', answer: (c) => /^ (hi|hello|hey|morning|evening|good (morning|afternoon|evening))( poe)? $/.test(c.q) && (() => { const g = greeting(); return { lines: [g.text], go: go(g.first?.href) }; })() },
    { id: 'thanks', answer: (c) => has(c.q, ['thank', 'cheers']) && { lines: ["You're welcome."] } },
    { id: 'founder', answer: (c) => has(c.q, ['ceo', 'founder', 'who runs', 'in charge', 'boss']) && { lines: [c.o.founder ? `${c.o.founder.name} is ${c.o.company}'s ${c.o.founder.title}.` : "I don't know that, and I won't guess."] } },
    { id: 'poe', answer: (c) => has(c.q, ['who are you', 'what are you', 'your name', 'what can you', 'what do you do', 'help']) && { lines: me } },
    { id: 'tour', answer: (c) => has(c.q, ['tour', 'show me round', 'show me around', 'look around']) && (setTimeout(startTour, 0), { lines: ['Follow me. Press Back or Esc to stop.'] }) },
    { id: 'keys', answer: (c) => W.keys && has(c.q, ['shortcut', 'keyboard', 'keys']) && { lines: [W.keys] } },
    { id: 'scenes', answer: (c) => has(c.q, ['scene', 'filter']) && { lines: [W.scenes] } },
    { id: 'colours', answer: (c) => has(c.q, ['colour', 'color', 'light', 'amber', 'glow', 'warm', 'dim']) && { lines: ['The light means something. Warm: working now. Amber: needs you. Dim: quiet.'] } },
    { id: 'happening', answer: (c) => has(c.q, ['happening', 'going on', 'whats new', 'news', 'catch me up', 'latest']) && happeningAnswer(c.f, c.floor) },
    { id: 'running', answer: (c) => has(c.q, ['running', 'working', 'busy', 'queue', 'jobs', 'doing', 'progress']) && runningAnswer(c.f, c.floor) },
    { id: 'needs', answer: (c) => has(c.q, ['need', 'waiting', 'to do', 'todo', 'pending', 'urgent', 'first', 'today', 'next', 'on my plate', 'what should']) && needsAnswer(c.f, c.floor) },
    { id: 'prs', answer: (c) => has(c.q, ['pull request', 'prs', 'pr ']) && prAnswer(c.f) },
    { id: 'presence', answer: (c) => presenceAnswer(c.q, c.f) },
    {
      id: 'room',
      answer: (c) => {
        const room = roomIn(c.q, c.floor);
        if (has(c.q, ['machine', 'online', 'computer']) && !room) return machinesAnswer(c.f);
        return room && roomAnswer(room, c.f);
      },
    },
    { id: 'goals', answer: (c) => has(c.q, ['goal']) && goalsAnswer(c.floor, c.f) },
    { id: 'floor', answer: (c) => c.floor && floorAnswer(c.floor, c.f) },
    { id: 'arnheim', answer: (c) => has(c.q, ['arnheim']) && { lines: W.arnheim } },
    {
      id: 'place',
      answer: (c) => has(c.q, ['what is this', 'this place', 'how does this work', 'what is here', 'building', ...W.placeWords]) && {
        lines: [W.place, `Floors, top to bottom: ${c.o.floors.map((x) => x.label).join(', ')}${c.o.lobby && c.o.basement ? `, then ${c.o.lobby.label} and ${c.o.basement.label}` : ''}.`],
      },
    },
    {
      id: 'company',
      answer: (c) => has(c.q, [norm(c.o.company).trim(), 'mission', 'company']) && {
        lines: [`${c.o.company}: ${c.o.about || ''} ${c.o.mission ? `Its mission, ${W.missionBy}: "${c.o.mission}".` : 'Its mission is not written yet.'}`.replace(':  ', ': ')],
        go: go('#/company'),
      },
    },
  ];
  const topics = kit.topics ? kit.topics(TOPICS) : TOPICS;

  function answer(text) {
    const q = norm(text);
    const m = MESSAGE.exec(text);
    if (m) return messageOffer(m[2], helperRe?.test(m[1]) ? helper : 'You');
    const c = { text, q, f: facts(), o: org(), floor: null, go, has, exact, norm, count, needWord };
    c.floor = floorIn(q);
    for (const t of topics) {
      const a = t.answer(c);
      if (a) return a;
    }
    return unknown(text, c.f);
  }

  /* ---------- taking a message ---------- */

  async function addTask(a, project) {
    if (a.offer.state) return;
    a.offer.state = 'saving';
    draw();
    const { title: taskTitle, who } = a.offer;
    const forHelper = !!helper && who === helper;
    const reply = await kit.addTask({ project, title: taskTitle, forHelper });
    if (!reply.ok) {
      a.offer.state = null;
      say({ lines: [`That didn't save: ${reply.error}`] });
      return;
    }
    a.offer.state = 'done';
    const floor = org().floors.find((x) => x.project === project);
    say({
      lines: [`Done. "${reply.task.title}" is on ${floor?.label || project}'s list, for ${forHelper ? helper : 'you'}.`, forHelper ? W.addedHelper : W.added].filter(Boolean),
      go: go(taskHref?.(reply.task)),
      undo: reply.task.id,
    });
  }

  async function undo(a) {
    if (a.undone) return;
    a.undone = true;
    const reply = await kit.dropTask(a.undo);
    if (!reply.ok) { a.undone = false; say({ lines: [`That didn't undo: ${reply.error}`] }); return; }
    say({ lines: ['Undone. That task is dropped, so it is off your lists.'] });
  }

  /* ---------- the tour ---------- */

  function stops() {
    const o = org();
    const f = facts();
    const here = (fl) => (f.needsBy?.[fl.project] ? `${needWord(f.needsBy[fl.project])} here.` : 'Nothing needs you here right now.');
    return [
      o.lobby && { floor: o.lobby.id, line: `This is ${o.lobby.label}, where I sit. ${o.lobby.about || ''}` },
      ...o.floors.map((fl) => ({ floor: fl.id, line: `${fl.label}. ${fl.about || ''} ${here(fl)}` })),
      o.basement && { floor: o.basement.id, line: `${o.basement.label}. ${o.basement.about || ''}` },
    ].filter(Boolean);
  }

  function showStop() {
    const list = stops();
    const s = list[tour.i];
    focusModel(s.floor);
    speak(s.line);
    draw();
    clearTimeout(tour.timer);
    if (!reduced()) tour.timer = setTimeout(() => next(), 7000);
  }

  function startTour() {
    if (tour) return;
    tour = { i: 0, timer: 0 };
    showStop();
  }

  function next() {
    if (!tour) return;
    tour.i += 1;
    if (tour.i >= stops().length) {
      stopTour(true);
      say({ lines: ["That's the whole building. I'm at the front desk whenever you need me."] });
      return;
    }
    showStop();
  }

  function stopTour(refocus) {
    if (!tour) return;
    clearTimeout(tour.timer);
    tour = null;
    if (canSpeak) window.speechSynthesis.cancel();
    if (refocus) focusModel(null);
    draw();
  }

  /* ---------- drawing ---------- */

  function say(a) {
    log.unshift({ poe: a });
    draw();
    speak(a.lines.join(' '));
  }

  function ask(text) {
    const a = answer(text);
    log.unshift({ you: text, poe: a });
    draw();
    speak(a.lines.join(' '));
  }

  function reply(a) {
    const o = org();
    const buttons = [];
    if (a.go) buttons.push(h('a.btn', { href: a.go.href }, a.go.label));
    if (a.offer && !a.offer.state) {
      const projects = o.floors.map((fl) => fl.project).filter(Boolean).sort((x, y) => Number(y === a.offer.guess) - Number(x === a.offer.guess));
      for (const p of projects) buttons.push(btn(o.floors.find((fl) => fl.project === p).label, () => addTask(a, p), p === a.offer.guess ? '.primary' : ''));
      buttons.push(btn('Not now', () => { a.offer.state = 'cancelled'; draw(); }));
    }
    if (a.offer?.state === 'saving') buttons.push(h('span.small.muted', 'Adding it.'));
    if (a.offer?.state === 'cancelled') buttons.push(h('span.small.muted', 'Nothing was added.'));
    if (a.task && canAdd) buttons.push(btn(helper ? `Make it a task for ${helper}` : 'Make it a task', () => { a.task = null; say(messageOffer(a.taskText || '', helper || 'You')); }));
    if (a.undo && !a.undone) buttons.push(btn('Undo', () => undo(a)));
    if (openSearch && a.search != null && a.search !== '') buttons.push(btn(`${W.searchLabel} "${a.search.slice(0, 40)}"`, () => openSearch(a.search), '', 'search'));
    return h('li.poe-reply',
      h('span.offscreen', 'Poe: '),
      a.lines.map((line) => h('p', line)),
      a.links?.length > 0 && h('ul.list', a.links.map((x) => row(x.href, x.title, x.sub, x.mood))),
      buttons.length > 0 && h('div.poe-row', buttons));
  }

  function tourCard() {
    const list = stops();
    const s = list[tour.i];
    return h('section.panel-card.poe-tour', { 'aria-live': 'polite' },
      h('p.small.muted', `Tour, stop ${tour.i + 1} of ${list.length}`),
      h('p.poe-say', s.line),
      h('div.poe-row',
        btn(tour.i + 1 < list.length ? 'Next' : 'Finish', () => next(), '.primary'),
        btn('Back', () => stopTour(true), '', 'arrow-left'),
        h('span.small.muted', 'Esc also stops the tour.')));
  }

  function live() {
    return [
      tour && tourCard(),
      h('ol.poe-log', { 'aria-live': 'polite' }, log.slice(0, 12).flatMap((e) => [e.you && h('li.poe-you', h('span.offscreen', 'You: '), e.you), reply(e.poe)])),
    ];
  }

  function draw() {
    const el = document.getElementById('poe-live');
    if (el) el.replaceChildren(...live().filter(Boolean));
  }

  function view() {
    const g = greeting();
    const input = h('input', { id: 'poe-ask', type: 'text', maxlength: 300, autocomplete: 'off', placeholder: canAdd ? 'Ask Poe, or say "remind me to ..."' : 'Ask Poe a question', 'aria-label': 'Ask Poe' });
    return {
      top: true,
      crumbs: [],
      body: [
        h('section.panel-card.poe-hello',
          poeBadge(52),
          h('div.poe-hello-text',
            title('Poe'),
            h('p.small.muted.poe-role', W.role),
            h('p.poe-say', g.text),
            g.first && h('a.btn', { href: g.first.href }, 'Take me there'))),
        h('form.poe-ask', {
          onsubmit: (event) => {
            event.preventDefault();
            const text = input.value.trim();
            if (!text) return;
            input.value = '';
            ask(text);
          },
        }, input, h('button.btn.primary', { type: 'submit' }, 'Ask')),
        h('div.poe-hints', { role: 'group', 'aria-label': 'Things you can ask' }, W.hints.map((q) => btn(q, () => ask(q)))),
        h('div.poe-tools',
          btn('Show me round', () => startTour()),
          canSpeak && h('button.btn', {
            type: 'button',
            'aria-pressed': String(voice),
            onclick: (event) => {
              voice = !voice;
              if (!voice) window.speechSynthesis.cancel();
              event.currentTarget.setAttribute('aria-pressed', String(voice));
              event.currentTarget.textContent = voice ? 'Read aloud: on' : 'Read aloud: off';
            },
          }, voice ? 'Read aloud: on' : 'Read aloud: off')),
        h('div', { id: 'poe-live' }, live()),
        h('p.small.muted.poe-note', W.note),
      ],
    };
  }

  return { view, ask, answer, touring: () => !!tour, stopTour, allFloors };
}
