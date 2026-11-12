// The Arnheim page: a company shown as a building, with a panel to look around it and the
// receptionist at the front desk. It shows your own company from data/ (company.json, work.json and notes.json) when
// data/company.json is there, and otherwise the sample, a company that is made up (sample/). The
// sample's work moves on a loop (the story at the end of its work.json), so there is always
// something to see. Nothing is saved anywhere: a reload reads the files again.
import { createBrain } from './brain.js';
import { agentControls, agentReply, createControl, deskControls, deskStart } from './control.js';
import { allowReadsAsked, sayWaiting, together, waitingOnYou } from './queue.js';
import { inner, proofMood, proofOf } from './proof.js';
import { MEMORY_ASKED, decidedFor, rememberAsked, sayMemory } from './memory.js';
import { floorSpend, localDay } from './budget.js';
import { clashesOf, sayClash, waitWords } from './clashes.js';
import { MOMENT_MOOD, conversationsAt, momentsBefore, sayMoment, touchedBy } from './replay.js';
import { icon } from './icons.js';
import { createPoe, has, insertAfter, needWord, norm, poeBadge } from './poe-desk.js';

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
const enc = encodeURIComponent;
const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

const STATUS = { needs_you: 'Needs you', working: 'In progress', waiting: 'Waiting', open: 'Open', done: 'Done', dropped: 'Dropped' };
const CLOSED = new Set(['done', 'dropped']);
const PRESENCE_TYPE_OF = { websites: 'website', email: 'email', social: 'social', domains: 'domain' };
const COMPANY_SECTIONS = ['Money', 'Legal', 'Subscriptions', 'Key dates'];
const SCENE_NAMES = { all: 'Everything', needs: 'Only what needs me', working: 'Working now' };
const SCENE_ICON = { all: 'layers', needs: 'bell-ring', working: 'zap' };
const ROOM_ICON = {
  goals: 'target', work: 'list-checks', conversations: 'messages-square', code: 'git-pull-request', company: 'briefcase',
  library: 'library', machine: 'server', websites: 'globe', email: 'mail', social: 'at-sign', domains: 'link', lounge: 'shapes',
};
const DESK = '#/front-desk'; // the receptionist's tab, and what a tap on them opens
const TOP_ROUTES = new Set([undefined, 'company', 'front-desk']);
const TAB_KEYS = { 1: '#/', 2: '#/company', 3: DESK };
// The receptionist's name, from the company map (receptionist in company.json). With none, they
// are just the receptionist, and their tab says Reception.
const deskName = () => org?.receptionist?.name?.trim() || '';
const deskTab = () => deskName() || 'Reception';

let org = null; // the company map: floors and rooms
let work = null; // what is going on in it
let dir = 'sample'; // where they came from: data (your own company) or sample (made up)
let feeds = []; // files in data/ that tools keep up to date (docs/connect.md)
// Control of your Claude Code agents, with serve.py --control and your own company (control.js).
const control = createControl({ busy: () => !!building?.walking?.() });
// The receptionist's and the assistant's brain, with serve.py --brain: they answer with Claude,
// through Claude Code on the computer that serves the page (brain.js). Off otherwise.
const brain = createBrain();
let starting = null; // an agent the receptionist was asked to start, waiting for your word
let controlNote = ''; // what came of the last thing done from the panel
const lastFeed = new Map();
let workSig = ''; // the work as last read, to tell when it has changed
const mine = []; // tasks the receptionist took down in this tab, kept through each fresh read
const dropped = new Set(); // and the ones dropped in it
const mineMemory = []; // decisions remembered in this tab, for a made-up company
const forgotten = new Set(); // and the ones forgotten in it
const FOLLOW_MS = 4000;
let poe = null;
let building = null;
let route = {};
let sceneId = 'all';
let playing = true;
let storyAt = 0;
let pending = false;
let added = 0;
const happened = []; // newest first: { line, at }

/* ---------- small helpers ---------- */

function h(tag, props, ...kids) {
  const [name, ...classes] = tag.split('.');
  const el = document.createElement(name || 'div');
  if (classes.length) el.className = classes.join(' ');
  const isProps = props && typeof props === 'object' && !(props instanceof Node) && !Array.isArray(props);
  if (!isProps) kids.unshift(props);
  for (const [key, v] of Object.entries(isProps ? props : {})) {
    if (v == null || v === false) continue;
    if (key.startsWith('on')) el.addEventListener(key.slice(2), v);
    else el.setAttribute(key, v === true ? '' : v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false) continue;
    el.append(kid instanceof Node ? kid : String(kid));
  }
  return el;
}

const count = (n, one, many) => `${n} ${n === 1 ? one : many}`;
const title = (text) => h('h2', { id: 'view-title', tabindex: -1 }, text);
const dot = (mood) => h(`span.dot.s-${mood || 'quiet'}`, { 'aria-hidden': 'true' });
const row = (href, main, sub, mood) => h('li', h(href ? 'a.row' : 'div.row', href ? { href } : {},
  dot(mood), h('span.row-main', h('span.row-title', main), sub && h('span.row-sub', sub))));
const btn = (label, onclick, cls = '', glyph = null) => h(`button.btn${cls}`, { type: 'button', onclick }, glyph && icon(glyph, 15), label);
const sectHead = (glyph, text) => h('div.sect-head', icon(glyph, 18), h('h3.sect-title', text));
const chip = (line) => h(`span.state.k-${line.kind}`, line.text);
const empty = (text) => h('p.muted.small', text);

function agoText(at) {
  const s = Math.max(0, Math.round((Date.now() - at) / 1000));
  if (s < 10) return 'just now';
  if (s < 60) return `${s} seconds ago`;
  return s < 120 ? 'a minute ago' : `${Math.round(s / 60)} minutes ago`;
}

/* ---------- reading the company ---------- */

// A company map with "sample" in it is made up, and the page says so wherever it shows it.
const madeUp = () => !!org.sample;
const sampleLine = () => (typeof org.sample === 'string' ? org.sample : `${org.company} is made up.`);
const hasStory = () => work.story.length > 0;
const floors = () => [...org.floors, org.lobby, org.basement].filter(Boolean);
const roomsOf = (floor) => [...(floor.rooms || org.rooms), ...(floor.extraRooms || [])];
const floorOf = (project) => org.floors.find((f) => f.project === project);
const rank = (project) => { const i = org.floors.findIndex((f) => f.project === project); return i < 0 ? 99 : i; };
const byProject = (list) => [...list].sort((a, b) => rank(a.project) - rank(b.project));
const openTasks = () => byProject(work.tasks.filter((t) => !CLOSED.has(t.status)));
const kindOf = (floor, room) => room.kind || (floor === org.basement ? (room.id === 'library' ? 'library' : 'machine') : room.id);
const machineLabel = (id) => org.basement?.rooms.find((r) => r.id === id)?.label || id;
// Everything waiting on you, from every agent and the work, most urgent first (queue.js).
// What a floor's agents have spent today against its budget (budget.js), as far as control has let them go.
const spendOf = (floor) => (floor?.project ? floorSpend(org, floor, work.conversations, control.on ? control.timesAllowed(floor.project) : 1) : null);
const waitingNow = () => {
  const { asks, runs } = control.on ? control.state() : { asks: [], runs: [] };
  // a floor's budget question goes as soon as it is under budget again, without waiting for the hook
  const tasks = openTasks().filter((t) => !t.budget || spendOf(floorOf(t.budget))?.over !== false);
  return waitingOnYou({ asks: asks.filter((a) => !answered.has(a.id)), runs, conversations: work.conversations, tasks });
};
// Permissions answered here, left out of the list before the next look at control catches up.
const answered = new Set();
const answerAsk = (id, behavior) => {
  answered.add(id);
  return control.answer(id, behavior).catch((error) => { answered.delete(id); throw error; });
};
const moodOf = (t) => (t.status === 'needs_you' ? 'needs' : t.status === 'working' ? 'working' : 'quiet');
const taskHref = (t) => `#/${floorOf(t.project)?.id}/work/${enc(t.id)}`;
const goalHref = (g) => `#/${floorOf(g.project)?.id}/goals/${enc(g.id)}`;
const convoHref = (c) => `#/${floorOf(c.project)?.id}/conversations/${enc(c.id)}`;
const presenceRoom = (type) => Object.keys(PRESENCE_TYPE_OF).find((id) => PRESENCE_TYPE_OF[id] === type) || 'websites';
const presenceHref = (e) => `#/${org.lobby?.id}/${presenceRoom(e.type)}/${enc(e.id)}`;
const isDown = (e) => !!e.link && e.up === false;

// One room's live data, the same plain shape any page gives the building through setLive().
function roomModel(floor, room) {
  const kind = kindOf(floor, room);
  const base = `#/${floor.id}/${room.id}`;
  const project = floor.project;
  if (floor === org.lobby) {
    const list = work.presence.filter((e) => e.type === PRESENCE_TYPE_OF[room.id]);
    const down = list.filter(isDown).length;
    return {
      state: down ? 'failed' : 'quiet', big: list.length || null, detail: list.length ? (down ? `listed, ${down} not answering` : 'listed') : 'None yet',
      items: list.map((e) => ({ id: e.id, title: e.name, sub: e.status, href: presenceHref(e), live: e.status === 'Live', up: !!e.link && !!e.up, mood: isDown(e) ? 'failed' : undefined })),
    };
  }
  if (kind === 'library') {
    const n = work.library.length;
    return { state: 'quiet', big: n || null, detail: n ? 'on the shelves' : 'Nothing on the shelves yet', items: work.library.map((b) => ({ id: b.id, title: b.name, sub: b.status, status: b.status, href: `${base}/${enc(b.id)}` })) };
  }
  if (kind === 'machine') {
    const m = work.machines.find((x) => x.id === room.id) || {};
    const running = work.jobs.filter((j) => j.machine === room.id && j.state === 'running').length;
    const info = running ? { state: 'working', big: 'Running', detail: count(running, 'job', 'jobs'), working: true }
      : m.online ? { state: 'quiet', big: 'Online', detail: 'Idle' } : { state: 'quiet', big: 'Offline', detail: 'Switched off' };
    return { ...info, running, online: !!m.online, title: room.label, sub: `${info.big}. ${info.detail}`, href: base };
  }
  if (kind === 'goals') {
    const list = work.goals.filter((g) => g.project === project);
    const open = list.filter((g) => g.status !== 'reached').length;
    const reached = list.length - open;
    return {
      state: 'quiet', big: list.length ? open : null, detail: list.length ? (reached ? `open, ${reached} reached` : 'open') : 'None set yet',
      items: list.map((g) => ({ id: g.id, title: g.title, reached: g.status === 'reached', sub: g.status === 'reached' ? 'Reached' : 'Open', href: goalHref(g) })),
    };
  }
  if (kind === 'work') {
    const list = openTasks().filter((t) => t.project === project).sort((a, b) => Number(b.status === 'needs_you') - Number(a.status === 'needs_you'));
    const needs = list.filter((t) => t.status === 'needs_you').length;
    return {
      state: needs ? 'needs' : 'quiet', big: list.length, detail: needs ? `open, ${needs === 1 ? '1 needs you' : `${needs} need you`}` : 'open',
      items: list.map((t) => ({ id: t.id, title: t.title, sub: STATUS[t.status], href: taskHref(t), mood: moodOf(t) })),
    };
  }
  if (kind === 'conversations') {
    const list = work.conversations.filter((c) => c.project === project).sort((a, b) => (!!b.working - !!a.working) || (!!b.check - !!a.check) || ((b.at || 0) - (a.at || 0)));
    const working = list.filter((c) => c.working).length;
    const checks = list.filter((c) => c.check);
    const proofs = new Map(list.map((c) => [c.id, proofOf(c)]));
    const failed = list.filter((c) => !c.working && proofs.get(c.id)?.state === 'failed').length;
    const proven = checks.filter((c) => proofs.get(c.id)?.state === 'proven').length;
    // Its light: red while any work there failed its check, green once all that's finished is proven.
    const state = failed ? 'failed' : checks.length ? (proven === checks.length ? 'ok' : 'check') : working ? 'working' : 'quiet';
    return {
      state, big: list.length, working: working > 0,
      detail: [checks.length ? `open, ${checks.length} to check` : 'open', failed && `${failed} not proven`].filter(Boolean).join(', '),
      items: list.map((c) => {
        const pr = proofs.get(c.id);
        const now = [c.working ? 'Working now' : c.check ? 'To check' : 'Quiet', c.agent].filter(Boolean).join('. ');
        return { id: c.id, title: c.title, working: !!c.working, check: !!c.check, proof: pr?.state || null, sub: pr && !c.working ? `${now}. ${pr.word}` : now,
          mood: c.working ? 'working' : proofMood(pr) || undefined, href: convoHref(c) };
      }),
    };
  }
  if (kind === 'code') {
    const prs = work.pullRequests.filter((p) => p.project === project);
    const copies = work.copies.filter((c) => c.project === project);
    return {
      state: 'quiet', big: null, detail: `${count(prs.length, 'pull request', 'pull requests')}, ${copies.length ? `${copies.length} unsaved` : 'all saved'}`,
      prs: prs.map((p) => ({ id: p.number, title: `#${p.number} ${p.title}`, draft: !!p.draft, sub: p.draft ? 'Draft' : 'Ready for review', href: `${base}/pr/${p.number}` })),
      copies: copies.map((c) => ({ id: c.id, title: c.name, sub: count(c.changes, 'unsaved change', 'unsaved changes'), href: `${base}/copy/${enc(c.id)}` })),
    };
  }
  if (kind === 'company') {
    const n = work.company.length;
    return {
      state: 'quiet', big: n || null, detail: n ? (n === 1 ? 'note' : 'notes') : 'Nothing filed yet',
      sections: COMPANY_SECTIONS.map((name) => {
        const k = work.company.filter((e) => e.section === name).length;
        return { id: name, title: name, count: k, sub: k ? count(k, 'note', 'notes') : 'Nothing here yet', href: `${base}/section/${enc(name)}` };
      }),
    };
  }
  return { state: 'quiet', big: null, detail: '' };
}

function floorLines(floor) {
  if (floor === org.basement) {
    const running = work.jobs.filter((j) => j.state === 'running').length;
    const waiting = work.jobs.filter((j) => j.state === 'queued').length;
    if (!running && !waiting) return [{ text: 'Queue is empty', kind: 'quiet' }];
    return [{ text: `Queue: ${[running && `${running} running`, waiting && `${waiting} waiting`].filter(Boolean).join(', ')}`, kind: running ? 'working' : 'quiet' }];
  }
  if (floor === org.lobby) {
    const down = work.presence.filter(isDown).length;
    return [down ? { text: `${down} not answering`, kind: 'failed' } : { text: `${count(work.presence.length, 'place', 'places')} listed`, kind: 'quiet' }];
  }
  const lines = [];
  if (openTasks().some((t) => t.project === floor.project && t.status === 'needs_you')) lines.push({ text: 'Needs you', kind: 'needs' });
  if (work.conversations.some((c) => c.project === floor.project && c.working)) lines.push({ text: 'Working now', kind: 'working' });
  if (clashesOf(work.conversations).some((c) => c.project === floor.project)) lines.push({ text: 'Two agents on the same files', kind: 'failed' });
  const spend = spendOf(floor);
  if (spend) lines.push({ text: spend.text[0].toUpperCase() + spend.text.slice(1), kind: spend.over ? 'failed' : 'quiet' });
  return lines.length ? lines : [{ text: 'Quiet', kind: 'quiet' }];
}

function liveModel() {
  const model = {};
  for (const floor of floors()) {
    model[`floor:${floor.id}`] = { lines: floorLines(floor) };
    for (const room of roomsOf(floor)) model[`${floor.id}/${room.id}`] = roomModel(floor, room);
  }
  return model;
}

/* ---------- the receptionist: plain facts from the company's files, no AI ---------- */

function poeFacts() {
  const open = openTasks();
  const link = (t) => ({ title: t.title, sub: t.project, href: taskHref(t) });
  const convo = (c) => ({ title: c.title, sub: c.project, href: convoHref(c) });
  const needs = waitingNow(); // the one list: permissions, questions, your tasks and agents just finished
  const finished = new Set(needs.filter((i) => i.kind === 'turn').map((i) => i.key)); // already in it
  const machines = org.basement ? org.basement.rooms.filter((r) => kindOf(org.basement, r) === 'machine').map((r) => ({ id: r.id, label: r.label, ...roomModel(org.basement, r) })) : [];
  return {
    needs: needs.map(waitingLink),
    needsBy: Object.fromEntries(org.floors.map((f) => [f.project, needs.filter((i) => i.project === f.project).length])),
    openBy: Object.fromEntries(org.floors.map((f) => [f.project, open.filter((t) => t.project === f.project).length])),
    later: 0,
    toCheck: byProject(work.conversations.filter((c) => c.check && !finished.has(c.id))).map(convo),
    withHelper: [],
    waiting: open.filter((t) => t.status === 'waiting').map(link),
    tasks: open.map(link),
    working: byProject(work.conversations.filter((c) => c.working)).map(convo),
    queue: {
      ok: true,
      running: work.jobs.filter((j) => j.state === 'running').map((j) => ({ title: j.name, sub: machineLabel(j.machine) })),
      waiting: work.jobs.filter((j) => j.state === 'queued').length,
    },
    machines,
    presence: work.presence.map((e) => ({ name: e.name, type: e.type, link: e.link, status: e.status, project: e.project, href: presenceHref(e) })),
    goals: work.goals.filter((g) => g.status !== 'reached').map((g) => ({ title: g.title, sub: g.project, project: g.project, href: goalHref(g) })),
    prs: Object.fromEntries(org.floors.filter((f) => work.pullRequests.some((p) => p.project === f.project)).map((f) => [f.project, work.pullRequests.filter((p) => p.project === f.project).length])),
  };
}

// The receptionist can add a task and drop it again, in this tab only.
async function addTask({ project, title: text }) {
  added += 1;
  const task = { id: `new${added}`, project, title: text, status: 'needs_you', note: `Taken down by ${deskName() || 'the receptionist'} when you asked. It lives in this tab only: nothing is saved.` };
  mine.push(task);
  work.tasks.push(task);
  refresh();
  return { ok: true, task };
}

async function dropTask(id) {
  const task = work.tasks.find((t) => t.id === id);
  if (!task) return { ok: false, error: 'that task is not here any more' };
  task.status = 'dropped';
  dropped.add(id);
  refresh();
  return { ok: true };
}

// What the rules answer even with the brain on: at once, and nothing Claude could be talked into
// instead. A refusal stays a refusal.
const RULED = new Set(['refuse', 'greeting', 'tour', 'waiting', 'memory']);
const ruledBy = (t) => (RULED.has(t.id) ? { ...t, answer: (c) => { const a = t.answer(c); return a && { ...a, ruled: t.id }; } } : t);

function setupDesk() {
  const called = deskName() || 'The receptionist';
  // "What's waiting on me?", "what needs me?" for the whole building: the one list, said as on a walk.
  // For one floor, the rules' own answer, from the same list.
  // "What have we decided?": the company's memory.
  const memory = {
    id: 'memory',
    answer: (c) => MEMORY_ASKED.test(c.text) && { lines: [sayMemory(memoryNow())], go: c.go('#/company', 'Show me') },
  };
  const waiting = {
    id: 'waiting',
    answer: (c) => !c.floor && WAITING.test(c.text) && {
      lines: [sayWaiting(waitingNow(), (p) => floorOf(p)?.label || p)],
      go: c.go('#/', 'Show me the list'),
    },
  };
  const real = {
    id: 'sample',
    answer: (c) => has(c.q, ['real', 'made up', 'fake', 'sample', 'demo', 'invented', 'pretend']) && {
      lines: !madeUp() ? [`This is ${org.company}'s own building, drawn from its own files. I only say what they hold.`]
        : [sampleLine(), hasStory() && 'The work you see moving is a short story on a loop, so the building has something to show. The Live button at the top pauses it.'].filter(Boolean),
    },
  };
  const howTo = {
    id: 'how-to',
    answer: (c) => has(c.q, ['task', 'goal']) && has(c.q, ['add', 'new', 'set', 'write', 'make', 'create']) && {
      lines: ['Tell me "remind me to ..." and I will add it as a task, in this tab only.', dir === 'data'
        ? 'Goals and everything else come from the company\'s own files, data/company.json and data/work.json, and from any tools connected to it. A change to the work shows within a few seconds.'
        : 'Goals and everything else come from the sample files, sample/company.json and sample/work.json. Copy them into a folder called data beside them, change them and reload to make the building your own.'],
    },
  };
  poe = createPoe({
    h, btn, title, row, taskHref, addTask, dropTask,
    org: () => org,
    facts: poeFacts,
    focusModel: (floorId) => (floorId ? building?.focus({ floor: floorId }) : focusBuilding()),
    reduced: reducedMotion,
    words: {
      place: `This is Arnheim, showing ${org.company}${madeUp() ? ', a company that is made up' : ''}. Each floor is a project and each room holds one kind of thing. The light shows what is happening.`,
      hints: ['What is Arnheim?', 'What needs me?', "What's running?", 'Who runs this company?', 'Where is the website?', 'Is this real?', 'What do the colours mean?'],
      role: brain.on ? 'Receptionist. Answers with Claude, through Claude Code on this computer.'
        : madeUp() ? 'Receptionist. Every answer comes from the sample company.' : `Receptionist. Every answer comes from ${org.company}'s own files.`,
      me: brain.on ? [
        `I'm ${deskName() ? `${deskName()}, the receptionist` : 'the receptionist'}. I answer with Claude, through Claude Code on this computer, and about ${org.company} I only say what this building shows.`,
        'I can also take a message: say "remind me to ..." and I will add it as a task.',
      ] : undefined,
      unknown: `I don't know that, and I won't guess. I only know what ${madeUp() ? 'the sample company holds' : `${org.company}'s files hold`}.`,
      note: `${brain.on ? `${called} answers with Claude, through Claude Code on this computer and on your own Claude plan: your questions go there, with the building's facts. Greetings, refusals and tasks stay with the building's own rules. ` : ''}${called} can add a task and undo it, in this tab only. ${dir === 'data' ? `What you ask ${called} to remember is kept for every agent while control is on. ` : 'Nothing is saved. '}${called} never merges, publishes, runs jobs or signs in.`,
      added: 'It is in the Work room now, in this tab only.',
      keys: `1 Overview, 2 Company, 3 ${deskTab()}. Esc goes back. Arrow keys turn the building, plus and minus zoom. They do nothing while you are typing.`,
    },
    topics: (list) => {
      const all = insertAfter(insertAfter(list, 'thanks', [real]), 'tour', [howTo]);
      all.splice(Math.max(0, all.findIndex((t) => t.id === 'needs')), 0, waiting, memory);
      return brain.on ? all.map(ruledBy) : all;
    },
    // A typed question at the desk: Claude's answer as it comes, with the brain on.
    // "Allow all the reads", with control on: done, then said.
    think: (text, a) => {
      const reads = control.on ? allowReadsAsked(text, waitingNow()) : null;
      if (reads) return (async function* allowed() { yield await allowReads(reads); })();
      const decision = rememberAsked(text);
      if (decision) return (async function* remembered() { yield await rememberIt(decision); })();
      // Work handed out in words: "get someone to fix the login bug on Lantern", then "start it".
      const start = control.on ? deskStart(control, text, starting) : null;
      if (start && start.reply != null) {
        starting = start.pending;
        return (async function* started() {
          const said = await start.reply;
          if (start.started) watchStart(start.started);
          yield said;
        })();
      }
      return brain.on && !a.ruled && !a.offer ? claudeSays('receptionist', text) : null;
    },
  });
}

/* ---------- the brain: Claude answers for the receptionist and the assistant (brain.js) ---------- */

const BRAIN_LIST = 25; // at most this many of anything in one section, then how many more

// What the building knows, for Claude, in named sections: whichever company it shows (the sample,
// or yours from data/ with its feeds, such as your Claude Code conversations) and, with control on,
// the agents started from here and what waits for your permission. The server sends every section
// with the first question and then only those that changed, so any time in them is a clock time,
// never "a minute ago", which would change every minute.
function brainFacts() {
  const out = [];
  const add = (name, lines) => {
    const text = [lines].flat(Infinity).filter((x) => x != null && x !== false && x !== '').join('\n');
    if (text) out.push([name, text]);
  };
  const clock = (at) => new Date(at < 1e12 ? at * 1000 : at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  const some = (list, line) => [...list.slice(0, BRAIN_LIST).map(line), list.length > BRAIN_LIST && `And ${list.length - BRAIN_LIST} more.`];
  const q = (text) => `"${text}"`;
  const label = (project) => floorOf(project)?.label || project;
  const asks = control.on ? control.state().asks : [];
  const runs = control.on ? control.state().runs.filter((r) => !work.conversations.some((c) => c.id === r.key)) : [];
  const needs = openTasks().filter((t) => t.status === 'needs_you');
  const checks = byProject(work.conversations.filter((c) => c.check));
  const waiting = openTasks().filter((t) => t.status === 'waiting');
  const talking = byProject(work.conversations.filter((c) => c.working));
  const jobs = work.jobs.filter((j) => j.state === 'running');

  add('Company', [
    `${org.company}.${org.about ? ` ${org.about}` : ''}`,
    madeUp() ? [sampleLine(), hasStory() && 'Its work moves on a short loop, a story told over and over so the building has something to show.']
      : `This is ${org.company}'s own building, drawn from its own files.`,
    org.mission && `Its mission, in its founder's words: ${q(org.mission)}.`,
    org.founder?.name && `Its founder: ${org.founder.name}${org.founder.title ? `, ${org.founder.title}` : ''}.`,
    `The receptionist, at the front desk${org.lobby ? ` in ${org.lobby.label}` : ''}: ${deskName() || 'not named'}.`,
    org.assistant?.name && `The founder's assistant, in the founder's office at the top: ${org.assistant.name}${org.assistant.title ? `, ${org.assistant.title}` : ''}.`,
    `Today is ${new Date().toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}.`,
  ]);
  add('The building', [
    'Arnheim shows the company as a building you can turn and walk through: each project is a floor, each kind of work a room, and the people at work are its agents. The light shows what is happening: warm is working now, amber needs you, dim is quiet.',
    'Arnheim is free and open, and named after Edgar Allan Poe\'s story "The Domain of Arnheim", about a man who shapes a landscape into a world of its own.',
    `Floors, top to bottom: ${[org.founder && "the founder's office", ...org.floors.map((f) => f.label)].filter(Boolean).join(', ')}${org.lobby ? `, then ${org.lobby.label} (the lobby)` : ''}${org.basement ? `, and ${org.basement.label} (the basement)` : ''}. A lift joins them.`,
  ]);
  add('Waiting on you, as one list (agents and tasks)', [sayWaiting(waitingNow(), label)]);
  add('Company memory: what every agent is told as it starts', memoryNow().length ? memoryNow().map((r) => `- ${r.text}`) : ['Nothing is remembered yet.']);
  add('Today, moment by moment (newest first)', momentsBefore(history, Date.now() / 1000, 25).map((m) => `- At ${clock(m.at)}, on ${label(m.project)}: ${sayMoment(m)}`));
  add('Agents on the same files', clashesOf(work.conversations).map((x) => `- ${sayClash(x)} On ${label(x.project)}.`));
  add("Spent today, in new tokens, against each floor's budget", org.floors.map((f) => [f, spendOf(f)]).filter(([, s]) => s).map(([f, s]) => `- ${f.label}: ${s.text}.`));
  if (control.on && control.paused()) add('Every agent', ['Paused from the building, until it resumes them.']);
  add('Needs you', [
    needs.length ? [`${needWord(needs.length)}, in this order:`, some(needs, (t) => `- ${q(t.title)}, on ${label(t.project)}`)] : 'Nothing needs you right now.',
    checks.length > 0 && [`${count(checks.length, 'conversation has', 'conversations have')} something for you to check:`, some(checks, (c) => `- ${q(c.title)}, on ${label(c.project)}`)],
    waiting.length > 0 && [`${count(waiting.length, 'task is', 'tasks are')} waiting on something else:`, some(waiting, (t) => `- ${q(t.title)}, on ${label(t.project)}`)],
    asks.length > 0 && ['Waiting for your permission:', asks.map((a) => `- ${a.what}`)],
  ]);
  add('Working now', [
    !talking.length && !jobs.length && 'Nothing is working right now.',
    talking.length > 0 && [`${count(talking.length, 'conversation is', 'conversations are')} working:`, some(talking, (c) => `- ${q(c.title)}, on ${label(c.project)}`)],
    jobs.length > 0 && [`${count(jobs.length, 'job is', 'jobs are')} running:`, some(jobs, (j) => `- ${q(j.name)}, on the ${machineLabel(j.machine)}`)],
  ]);
  for (const floor of org.floors) {
    const p = floor.project;
    const tasks = openTasks().filter((t) => t.project === p);
    const goals = work.goals.filter((g) => g.project === p);
    const prs = work.pullRequests.filter((x) => x.project === p);
    const copies = work.copies.filter((c) => c.project === p);
    add(`Floor: ${floor.label}`, [
      `${floor.label}${p !== floor.label ? ` (the project ${p})` : ''}: ${floor.about || 'nothing is written about it yet.'}`,
      floor.story,
      `Rooms: ${roomsOf(floor).map((r) => r.label).join(', ')}.`,
      tasks.length ? ['Open tasks:', some(tasks, (t) => `- ${q(t.title)}: ${(STATUS[t.status] || t.status || 'open').toLowerCase()}`)] : 'No open tasks.',
      goals.length ? ['Goals:', some(goals, (g) => `- ${q(g.title)}: ${g.status === 'reached' ? 'reached' : 'open'}`)] : 'No goals written yet.',
      prs.length > 0 && ['Open pull requests:', some(prs, (x) => `- #${x.number} ${q(x.title)}${x.draft ? ', a draft' : ''}`)],
      copies.length > 0 && ['Working copies with unsaved changes:', some(copies, (c) => `- ${c.name}: ${count(c.changes, 'change', 'changes')}`)],
    ]);
    // The people at work on this floor: each conversation's agent, and agents started from here.
    const convos = work.conversations.filter((c) => c.project === p);
    const started = runs.filter((r) => r.project === p);
    add(`Agents on ${floor.label}`, [
      convos.length + started.length === 0 && 'No agents here.',
      some(convos, (c) => {
        const ask = asks.find((a) => a.key === c.id);
        const says = c.says || {};
        const now = [c.working && 'working now', (ask || says.needs) && 'waiting for you', c.check && 'finished, with something for you to check'].filter(Boolean).join(', ') || 'quiet';
        return [
          `- The ${p} agent on ${q(c.title)}${control.on ? ` (conversation ${c.id})` : ''}: ${now}.`,
          ask && `  Waiting for your permission: ${ask.what}.`,
          says.needs && `  It needs: ${says.needs}`,
          says.now && `  It last said: ${q(says.now)}`,
          says.next && `  Next: ${says.next}`,
          says.when && `  When: ${says.when}`,
          c.at && `  Last heard from at ${clock(c.at)}.`,
          proofOf(c) && `  Its work: ${proofOf(c).word.toLowerCase()}. ${proofOf(c).line}`,
        ];
      }),
      some(started, (r) => [
        `- An agent started from the building, on ${q(r.title)} (conversation ${r.key}): ${{ working: 'working now', stopped: 'stopped, as you asked', failed: 'stopped with an error' }[r.state] || 'finished'}.`,
        r.said && `  It last said: ${q(r.said)}`,
      ]),
    ]);
  }
  if (org.lobby) {
    add(`${org.lobby.label} (the lobby)`, [
      `Rooms: ${roomsOf(org.lobby).map((r) => r.label).join(', ')}.`,
      work.presence.length ? some(work.presence, (e) => `- ${e.name} (${e.type}${e.project ? `, ${e.project}` : ''}): ${e.status || 'no status'}${e.link ? `, at ${e.link}${isDown(e) ? ', not answering' : e.up ? ', answering' : ''}` : ', no address written down'}.`)
        : 'Nothing is written down here yet.',
    ]);
  }
  if (org.basement) {
    const machines = org.basement.rooms.filter((r) => kindOf(org.basement, r) === 'machine');
    add(`${org.basement.label} (the basement)`, [
      machines.length > 0 && ['Machines:', machines.map((r) => { const m = roomModel(org.basement, r); return `- ${r.label}: ${m.big}, ${String(m.detail).toLowerCase()}.`; })],
      work.jobs.length > 0 && ['Jobs:', some(work.jobs, (j) => `- ${q(j.name)}, on the ${machineLabel(j.machine)}: ${{ running: 'running', queued: 'waiting in the queue' }[j.state] || j.state}.`)],
      work.library.length > 0 && ['On the library shelves:', some(work.library, (b) => `- ${b.name}${b.status ? `: ${b.status}` : ''}`)],
    ]);
  }
  if (work.company.length) add('Company notes', ['Filed in the Company room:', some(work.company, (e) => `- ${e.section}: ${e.name}${e.note ? `. ${e.note}` : ''}`)]);
  if (hasStory() && happened.length) add('Just now', ['What happened lately, newest first:', happened.map((e) => `- At ${clock(e.at)}: ${e.line}`)]);
  return out;
}

const brainWho = (role) => ({ role, name: role === 'assistant' ? org.assistant?.name || '' : deskName(), company: org.company });

// Claude's answer for the receptionist or the assistant, a piece at a time. It throws if there is
// none, so the rules can answer instead.
async function* claudeSays(role, text) {
  try {
    yield* brain.ask(brainWho(role), text, brainFacts());
  } catch (error) {
    console.warn('Arnheim: no answer from Claude.', error.message);
    throw error;
  }
}

// Reads Claude the facts as someone steps up to the receptionist or the assistant, so their first
// answer comes sooner. The server does nothing if they know them all already.
const primed = {};
function primeBrain(role) {
  if (!brain.on || Date.now() - (primed[role] || 0) < 3000) return;
  primed[role] = Date.now();
  brain.prime(brainWho(role), brainFacts());
}

/* ---------- talking in the walk (voice.js) ---------- */

// The receptionist answers as at the desk. The people at work answer from their own lines in work.json ("says"),
// with no AI; in the sample they are made up, and so is what they say. A page with real agents
// passes its own answers, and there what you say reaches the agent doing the work.
const talkItem = (who) => work.conversations.find((c) => convoHref(c) === who.href) || work.tasks.find((t) => taskHref(t) === who.href) || null;
const isConvo = (item) => work.conversations.includes(item);
const convoNow = (id) => work.conversations.find((c) => c.id === id) || null;

const TOUR = ['tour', 'show me round', 'show me around', 'look around'];

function poeSays(text) {
  if (has(norm(text), TOUR)) return `I can show you round from the ${deskTab()} tab, once you leave the walk.`;
  const a = poe.answer(text);
  if (a.offer) return `I can add "${a.offer.title}" as a task from the ${deskTab()} tab, where you pick its project.`;
  const lines = [...a.lines];
  // The things an answer links to belong to its first line, so they are said right after it.
  if (a.links?.length && a.links.length <= 4) lines.splice(1, 0, `${a.links.map((x) => (x.sub ? `${x.title}, on ${x.sub}` : x.title)).join('. ')}.`);
  return lines.join(' ');
}

// What the receptionist or the assistant says on a walk. With the brain on, Claude answers, a piece at
// a time, except for what the rules keep (a greeting, a refusal, a message to take down, a tour).
// If Claude has no answer at all, the rules answer instead.
function deskSays(role, text) {
  if (!brain.on || has(norm(text), TOUR)) return poeSays(text);
  const a = poe.answer(text);
  if (a.ruled || a.offer) return poeSays(text);
  return (async function* thought() {
    let given = false;
    try {
      for await (const piece of claudeSays(role, text)) {
        given = true;
        yield piece;
      }
    } catch (error) {
      if (given) throw error; // voice.js says the answer was cut off
      yield poeSays(text);
    }
  })();
}

function sampleReply(item, text) {
  const q = norm(text);
  const says = item.says || {};
  const on = (words) => has(q, words);
  if (on(['thank', 'cheers', 'great', 'nice one', 'well done', 'good job'])) return "Thanks. I'll keep going.";
  if (on(['bye', 'see you', 'talk later'])) return 'Bye for now.';
  if (on(['who are you', 'your name', 'what are you'])) return `I'm the ${item.project} agent on "${item.title}".${madeUp() ? ' This company is a sample, so I am made up too.' : ''}`;
  if (on(['next', 'after that', 'plan', 'left', 'remaining', 'then what'])) return says.next || "I'll know what's next when this step is done.";
  if (on(['you should', 'instead', 'stop ', 'switch to', 'focus on', 'do this', 'can you', 'could you', 'i want you', 'please '])) {
    return madeUp() ? "I'm a made-up agent in a sample, so I can't take new work. With real agents, what you say here goes to the agent doing the work."
      : "I can only tell you what the company's files say, so I can't take new work from here. With real agents, what you say here goes to the agent doing the work.";
  }
  if (on(['need me', 'need anything', 'need you', 'stuck', 'blocked', 'help', 'problem', 'decide', 'decision'])) return says.needs || 'Nothing from you right now. I will ask if I need you.';
  if (on(['how long', 'when will', 'when did', 'started', 'finish', 'done by'])) return says.when || "I can't say exactly. I'll say when it's done.";
  return [says.now, says.next].filter(Boolean).join(' ') || `I'm working on "${item.title}".`;
}

// The founder's assistant (org.assistant), in their office: in the sample they answer as the receptionist does.
// "What's waiting on me?", "what needs me?": the receptionist reads out the one list (queue.js).
const WAITING = /\b(?:wait(?:s|ing)? (?:on|for) (?:me|you)|needs? me|need anything from me|my queue|what(?:'s| is) (?:on|in) my (?:plate|queue))\b/i;
const isAide = (who) => !!org.assistant && who.href === (org.assistant.href || '#/assistant');

const talk = {
  name(who) {
    if (who.href === DESK) return deskName() || 'Receptionist';
    if (isAide(who)) return org.assistant.name;
    const item = talkItem(who);
    return item ? `${item.project} agent` : null;
  },
  greet(who) {
    if (who.href === DESK || isAide(who)) primeBrain(who.href === DESK ? 'receptionist' : 'assistant'); // walked up to: read Claude the facts now
    if (who.href === DESK) {
      const hr = new Date().getHours();
      const hello = hr >= 5 && hr < 12 ? 'Good morning' : hr >= 12 && hr < 18 ? 'Good afternoon' : hr >= 18 && hr < 23 ? 'Good evening' : 'Hello';
      return `${hello}. Ask me what's happening, or anything ${brain.on ? 'at all' : 'about the building'}.${control.on ? ' I can start an agent on a project too.' : ''}`;
    }
    if (isAide(who)) {
      const hello = `Hello. I'm ${org.assistant.name}, ${org.founder?.name || 'the founder'}'s assistant.`;
      return madeUp() ? `${hello} This company is made up, and so am I. Ask me anything${brain.on ? '' : ' about it'}.` : `${hello} Ask me anything${brain.on ? '' : ` about ${org.company}`}.`;
    }
    const item = talkItem(who);
    return item ? `Hi. I'm on "${item.title}". Ask me how it's going.` : null;
  },
  answer(who, text) {
    if (who.href === DESK) {
      const waiting = waitingNow();
      const reads = control.on ? allowReadsAsked(text, waiting) : null;
      if (reads) return allowReads(reads);
      if (WAITING.test(String(text || ''))) return sayWaiting(waiting, (p) => floorOf(p)?.label || p);
      const decision = rememberAsked(text);
      if (decision) return rememberIt(decision);
      if (MEMORY_ASKED.test(String(text || ''))) return sayMemory(memoryNow());
      const start = deskStart(control, text, starting);
      if (start) {
        starting = start.pending;
        if (start.reply != null) return start.reply;
      }
    }
    if (who.href === DESK || isAide(who)) return deskSays(who.href === DESK ? 'receptionist' : 'assistant', text);
    const item = talkItem(who);
    if (item && control.on && isConvo(item)) return agentReply(control, item, text, () => convoNow(item.id));
    return item ? sampleReply(item, text) : "I've finished here, so there's nothing new to tell.";
  },
  // With control on: Allow and Deny, or Stop, on an agent's card; Start at the front desk.
  controls(who) {
    if (!control.on) return null;
    if (who.href === DESK) {
      return deskControls(starting, () => {
        const start = deskStart(control, 'start it', starting);
        starting = start?.pending || null;
        return start?.reply;
      }, () => { starting = null; return "All right, I won't start it."; });
    }
    const item = talkItem(who);
    return item && isConvo(item) ? agentControls(control, item) : null;
  },
};

/* ---------- control in the panel (control.js) ---------- */

function controlDone(promise, said) {
  promise.then((out) => { controlNote = said(out); render(); }, (error) => { controlNote = error.message; render(); });
}

// A conversation's page: its permission request with Allow and Deny, a box to say something to
// it, and Stop while it works.
function convoControls(c) {
  const ask = control.askFor(c.id);
  const run = control.run(c.id);
  const working = c.working || run?.state === 'working';
  const send = (event) => {
    event.preventDefault();
    const input = event.currentTarget.elements.text;
    const text = input.value.trim();
    if (!text) return;
    input.value = '';
    input.blur();
    controlDone(control.say(c.id, text), (r) => (r.sent === 'resumed' ? 'Sent. It is answering now.'
      : working ? 'Sent. It reads it at its next step, and its answer shows above.'
        : 'Sent. It is waiting for you in Claude Code, so it sees this the next time you send it something there.'));
  };
  return h('div.control',
    ask && h('div.control-ask',
      h('p', `Waiting for your permission: ${ask.what}`),
      h('div.control-row',
        btn('Allow', () => controlDone(control.answer(ask.id, 'allow'), () => 'Allowed, just this once.'), '.primary'),
        btn('Deny', () => controlDone(control.answer(ask.id, 'deny'), () => 'Denied.')))),
    h('form.control-say', { onsubmit: send },
      h('input', { name: 'text', type: 'text', maxlength: 2000, autocomplete: 'off', placeholder: 'Say something to it', 'aria-label': `A message for ${c.title}` }),
      h('button.btn', { type: 'submit' }, 'Send')),
    working && h('div.control-row', btn('Stop', () => controlDone(control.halt(c.id), () => 'Stopping. It stops at its next step.'))),
    controlNote && h('p.small.muted', { role: 'status' }, controlNote));
}

// Collision warnings (clashes.js): two agents changing the same files, and, with control on, a way to make
// one wait for the other.
function clashCard() {
  const list = clashesOf(work.conversations);
  if (!list.length) return null;
  const canTell = (c) => control.on && (REACHABLE.test(c.id) || control.run(c.id));
  return h('section.panel-card',
    sectHead('shield-check', 'Two agents on the same files'),
    h('ul.list', list.map((x) => {
      const li = row(convoHref(x.a), sayClash(x), [floorOf(x.project)?.label || x.project, x.working ? 'One is at work now' : null].filter(Boolean).join('. '), 'failed');
      const buttons = [x.a, x.b].filter(canTell).map((who) => btn(`Make "${who.title}" wait`, () => controlDone(control.say(who.id, waitWords(x, who)),
        () => `Told "${who.title}" to wait. It reads it at its next step.`)));
      if (buttons.length) li.append(h('div.control-row.waiting-do', buttons));
      return li;
    })),
    h('p.small.muted', 'Each was told as it changed the file. Look at both before either goes on.'),
    controlNote && h('p.small.muted', { role: 'status' }, controlNote));
}

// Every agent at once: paused from here until you resume them (connect/budget.py), with control on.
function pauseCard() {
  if (!control.on || dir !== 'data') return null;
  const paused = control.paused();
  return h(`section.panel-card.pause${paused ? '.paused' : ''}`, { 'aria-live': 'polite' },
    paused ? h('p', h('strong', 'Every agent is paused.'), ` Since ${new Date(paused * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}. Each stopped at its next step, and a message sent to one in Claude Code waits until you resume.`)
      : h('p.small.muted', 'Pause every agent at once: each stops at its next step, until you resume them.'),
    h('div.control-row', paused ? btn('Resume everyone', () => controlDone(control.resumeAll(), () => ''), '.primary', 'rotate-ccw')
      : btn('Pause everyone', () => controlDone(control.pauseAll(), () => ''), '', 'clock')));
}

// Replay the day (replay.js): the building's conversations as they were at a moment today. While it
// replays, the real ones wait in realTalks, and a banner on the building says so.
let replayAt = null;
let realTalks = null;
const clockOf = (at) => new Date(at * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
function replayed() {
  realTalks = work.conversations;
  work.conversations = conversationsAt(history, replayAt);
}
function showAt(t) {
  const now = Date.now() / 1000;
  if (t == null || t >= now - 30) {
    if (realTalks) work.conversations = realTalks;
    replayAt = realTalks = null;
  } else {
    if (realTalks) work.conversations = realTalks;
    replayAt = t;
    replayed();
  }
  replayBanner();
  refresh();
}
function replayBanner() {
  let el = $('replay-banner');
  if (replayAt == null) { el?.remove(); return; }
  if (!el) {
    el = h('div', { id: 'replay-banner', role: 'status' }, h('span'), btn('Back to now', () => showAt(null), '.primary'));
    $('stage').append(el);
  }
  el.firstChild.textContent = `Replaying the day at ${clockOf(replayAt)}`;
}

function replayCard() {
  if (!history.length) return null;
  const now = Date.now() / 1000;
  const first = Math.floor(Math.min(...history.map((m) => m.at)) - 60);
  const at = replayAt ?? now;
  const real = realTalks || work.conversations;
  const label = h('span.replay-at', replayAt == null ? 'Now' : clockOf(at));
  const list = h('ul.list.replay-moments');
  const fill = (t) => {
    const ms = momentsBefore(history, t);
    list.replaceChildren(...(ms.length ? ms.map((m) => {
      const c = real.find((x) => x.id === m.key);
      const files = m.kind === 'finished' ? touchedBy(history, m.key, t) : [];
      return row(c ? convoHref(c) : null, sayMoment(m), [clockOf(m.at), floorOf(m.project)?.label || m.project, files.length ? `Changed ${files.slice(0, 3).join(', ')}${files.length > 3 ? ` and ${files.length - 3} more` : ''}` : null].filter(Boolean).join('. '), MOMENT_MOOD[m.kind]);
    }) : [h('li', empty('Nothing had happened yet.'))]));
  };
  fill(at);
  const slider = h('input.replay-slider', { type: 'range', min: first, max: Math.ceil(now), step: 60, value: Math.round(at), 'aria-label': 'When in the day to show',
    oninput: (event) => { const t = Number(event.currentTarget.value); label.textContent = t >= now - 30 ? 'Now' : clockOf(t); fill(t); showAt(t); } });
  return h('section.panel-card.replay',
    sectHead('history', 'Replay the day'),
    h('p.small.muted', 'Drag back through today to see who was at work, and on what. Tap a moment to read that conversation.'),
    h('div.replay-row', slider, label),
    list,
    replayAt != null && h('div.control-row', btn('Back to now', () => showAt(null))));
}

// What each floor's agents have spent today, against its budget.
function spendCard() {
  const list = org.floors.map((f) => [f, spendOf(f)]).filter(([, s]) => s);
  if (!list.length) return null;
  return h('section.panel-card',
    sectHead('gauge', 'Spent today'),
    h('ul.list', list.map(([f, s]) => h('li', h('a.row.spend-row', { href: `#/${f.id}` }, dot(s.over ? 'failed' : 'quiet'),
      h('span.row-main', h('span.row-title', f.label), h('span.row-sub', s.text[0].toUpperCase() + s.text.slice(1)),
        s.share != null && h('span.spend-bar', { 'aria-hidden': 'true' }, h(`span${s.over ? '.over' : ''}`, { style: `width: ${Math.round(s.share * 100)}%` }))))))),
    h('p.small.muted', 'New tokens: what Claude read fresh and wrote. Re-reading its cache is left out.'));
}

// Done means proven (proof.js): the check's last lines when it didn't pass, and, with control on and a check
// on its floor, a way to run it again.
function proofPart(c, pr) {
  if (!pr) return null;
  const check = control.on ? control.checkOf(c.project) : null;
  return h('div.proof',
    pr.tail && h('pre.proof-tail', { 'aria-label': 'What the check printed last' }, pr.tail),
    check && pr.state !== 'checking' && h('div.control-row',
      btn('Check it again', () => controlDone(control.prove(c.id), (r) => `Running ${inner(r.check)} on its work now.`), '', 'rotate-ccw')));
}

// Everything waiting on you (queue.js), each with its answer: Allow and Deny for a permission, a reply for
// an agent that asked something or finished (with control on), and a link to look closer. Reads waiting
// together can be allowed together.
function waitingList(items) {
  if (!items.length) return empty('Nothing is waiting on you right now.');
  const reads = control.on ? together(items) : null;
  const allowAll = (ids) => controlDone(allowReads(ids), (said) => said);
  return h('div.waiting',
    reads && h('div.control-row', btn(reads.label, () => allowAll(reads.ids), '.primary')),
    h('ul.list', items.map(waitingItem)),
    controlNote && h('p.small.muted', { role: 'status' }, controlNote));
}

// A conversation control can pass a message to: one the Claude Code feed names (connect/control.py, KEY).
const REACHABLE = /^cc-[A-Za-z0-9]{1,12}$/;
const waitingHead = (i) => ({ permission: `${i.title} wants your permission`, question: `${i.title} is asking`, task: i.title, turn: `${i.title} has finished` })[i.kind];
const waitingHref = (i) => (i.key && i.project ? convoHref({ id: i.key, project: i.project }) : i.task ? taskHref(i.task) : null);
const waitingLink = (i) => ({ title: waitingHead(i), sub: i.project, href: waitingHref(i), mood: i.kind === 'turn' ? 'check' : 'needs' });

// The company's memory as it stands in this tab, and adding to it or taking from it: through control for
// your own company, in this tab only for a made-up one.
const memoryNow = () => [...(work.memory || []).filter((r) => !forgotten.has(r.id)), ...mineMemory];
const memoryWrites = () => dir === 'data' && control.on;
async function rememberIt(text) {
  if (dir === 'data' && !control.on) return "I can't keep that from here while control is off. Add it to data/memory.json, or start Arnheim with --control.";
  if (memoryNow().some((r) => r.text.toLowerCase() === text.toLowerCase())) return `That's remembered already: ${text}`;
  if (memoryWrites()) {
    try {
      const row = await control.remember(text);
      noMemoryUntil = 0; // the file is there now
      work.memory = [...(work.memory || []), row];
      refresh();
      return `Remembered: ${row.text} Every agent hears it as it starts, and those at work with your next message to them.`;
    } catch (error) {
      return error.message;
    }
  }
  mineMemory.push({ id: `tab-${mineMemory.length + 1}`, text, at: Date.now() / 1000 });
  refresh();
  return `Remembered, in this tab only, since this company is made up: ${text} With your own company, every agent would hear it as it starts.`;
}
function forgetIt(r) {
  const i = mineMemory.indexOf(r);
  if (i >= 0) { mineMemory.splice(i, 1); refresh(); return; }
  if (!memoryWrites()) return;
  controlDone(control.forget(r.id).then((out) => { forgotten.add(r.id); return out; }), () => 'Forgotten. Agents that start from now won\'t be told it.');
}

// After an agent is started from the panel: the building turns to the room where it sits down.
function watchStart(p) {
  const floor = org.floors.find((f) => f.project === p.project);
  const room = floor && roomsOf(floor).find((r) => kindOf(floor, r) === 'conversations');
  if (room && !building?.walking?.()) location.hash = `#/${floor.id}/${room.id}`;
}

// Allows every waiting read at once ("allow all the reads"): what to say when it's done.
const allowReads = (ids) => (!ids.length ? Promise.resolve('Nothing is waiting to read right now.')
  : Promise.allSettled(ids.map((id) => answerAsk(id, 'allow'))).then((out) => {
    const done = out.filter((o) => o.status === 'fulfilled').length;
    if (!done) return out[0].reason?.message || "They couldn't be allowed.";
    const gone = ids.length - done ? ` ${ids.length - done} of them had stopped waiting.` : '';
    return `Allowed ${count(done, 'read', 'reads')}, just this once.${gone} They carry on now.`;
  }));

function waitingItem(i) {
  const agent = i.key ? work.conversations.find((c) => c.id === i.key)?.agent : null; // another agent than Claude Code
  const where = [i.project ? (floorOf(i.project)?.label || i.project) : '', agent].filter(Boolean).join('. ');
  const href = waitingHref(i);
  const head = waitingHead(i);
  const what = i.kind === 'task' ? null : i.kind === 'permission' ? `It wants ${i.what}` : i.proof ? `${i.proof.word}. ${i.what}` : i.what;
  const sub = [what, where].filter(Boolean).map((part, n, all) => (n < all.length - 1 && !/[.?!]$/.test(part) ? `${part}.` : part)).join(' ');
  const li = row(href, head, sub, i.kind === 'turn' ? proofMood(i.proof) || 'check' : 'needs');
  if (i.kind === 'permission' && control.on) {
    li.append(h('div.control-row.waiting-do',
      btn('Allow', () => controlDone(answerAsk(i.ask.id, 'allow'), () => 'Allowed, just this once.'), '.primary'),
      btn('Deny', () => controlDone(answerAsk(i.ask.id, 'deny'), () => 'Denied.'))));
  }
  if (i.kind === 'task' && i.task?.budget && control.on && dir === 'data') {
    li.append(h('div.control-row.waiting-do',
      btn('Let them go on', () => controlDone(control.allowMore(i.task.budget), (r) => `${i.task.budget}'s agents may spend as much again today. Tell them to go on.`), '.primary')));
  }
  const decided = i.kind === 'question' ? decidedFor(i.what, memoryNow()) : [];
  const reachable = control.on && (REACHABLE.test(i.key) || control.run(i.key));
  if (decided.length) {
    li.append(h('div.waiting-do.decided',
      h('p.small', h('span.muted', 'You decided before: '), decided.map((r) => r.text).join(' ')),
      reachable && h('div.control-row', btn('Send it that', () => controlDone(control.say(i.key, `You decided this before: ${decided.map((r) => r.text).join(' ')}`),
        () => 'Sent. It is waiting for you in Claude Code, so it sees this the next time you send it something there.'), '.primary'))));
  }
  if ((i.kind === 'question' || i.kind === 'turn') && reachable) {
    const send = (event) => {
      event.preventDefault();
      const input = event.currentTarget.elements.text;
      const text = input.value.trim();
      if (!text) return;
      input.value = '';
      input.blur();
      controlDone(control.say(i.key, text), (r) => (r.sent === 'resumed' ? 'Sent. It is answering now.'
        : 'Sent. It is waiting for you in Claude Code, so it sees this the next time you send it something there.'));
    };
    li.append(h('form.control-say.waiting-do', { onsubmit: send },
      h('input', { name: 'text', type: 'text', maxlength: 2000, autocomplete: 'off', placeholder: i.kind === 'question' ? 'Answer it' : 'What next?', 'aria-label': `A reply to ${i.title}` }),
      h('button.btn', { type: 'submit' }, 'Send')));
  }
  return li;
}

// A floor's Conversations room: start an agent on its project, in its folder.
function startForm(floor) {
  const p = control.projects().find((x) => x.project === floor.project);
  if (!p) return null;
  const go = (event) => {
    event.preventDefault();
    const input = event.currentTarget.elements.text;
    const text = input.value.trim();
    if (!text) return;
    input.value = '';
    input.blur();
    controlDone(control.begin(p.project, text), () => `Started. It shows here once it begins.`);
  };
  return h('form.control.control-start', { onsubmit: go },
    h('h3', 'Start an agent here'),
    h('textarea', { name: 'text', rows: 3, maxlength: 2000, placeholder: `What should it do on ${floor.label}?`, 'aria-label': `What a new agent on ${floor.label} should do` }),
    h('div.control-row', h('button.btn.primary', { type: 'submit' }, 'Start')),
    h('p.small.muted', 'It runs in this project\'s folder with your own Claude Code settings, as if you had started it there.'),
    controlNote && h('p.small.muted', { role: 'status' }, controlNote));
}

/* ---------- the panel ---------- */

function crumbsFor(floor, room, last) {
  const list = [[org.company, '#/company']];
  if (floor) list.push([floor.label, `#/${floor.id}`]);
  if (room) list.push([room.label, `#/${floor.id}/${room.id}`]);
  if (last) list.push([last]);
  return list;
}

function viewOverview() {
  const waiting = waitingNow();
  const talking = byProject(work.conversations.filter((c) => c.working));
  const jobs = work.jobs.filter((j) => j.state === 'running');
  const tile = (glyph, mood, n, label) => h(`div.stat.glow.glow-${n ? mood : 'quiet'}`, h('span.stat-top', h('span.tile-icon', icon(glyph, 20)), h('span.stat-num', String(n))), h('span.stat-label', label));
  return {
    top: true,
    crumbs: [],
    body: [
      h('section.panel-card.intro',
        title(madeUp() ? `${org.company}, a company that is made up` : org.company),
        madeUp() ? h('p', sampleLine()) : org.about && h('p', org.about),
        h('p.small.muted', `Arnheim shows a company as a building. Each floor is a project and each room holds one kind of thing. Tap a floor to bring it out, then a room to look inside. Press Walk to go in and talk to the people at work, and to ${deskName() || 'the receptionist'} at the front desk.`)),
      h('div.stats', tile('bell-ring', 'needs', waiting.length, 'Need you'), tile('messages-square', 'working', talking.length, 'Working now'), tile('server', 'working', jobs.length, 'Jobs running')),
      pauseCard(),
      clashCard(),
      h('section.panel-card',
        sectHead('bell', 'Waiting on you'),
        waitingList(waiting)),
      replayCard(),
      spendCard(),
      h('section.panel-card',
        sectHead('zap', 'Working now'),
        talking.length || jobs.length
          ? h('ul.list', [
            ...talking.map((c) => row(convoHref(c), c.title, `${c.project}. A conversation`, 'working')),
            ...jobs.map((j) => row(`#/${org.basement?.id}/${j.machine}`, j.name, `On the ${machineLabel(j.machine)}`, 'working')),
          ])
          : empty('Nothing is working right now.')),
      hasStory() && h('section.panel-card',
        sectHead('history', 'Just now'),
        happened.length
          ? h('ul.list.happened', happened.map((e) => h('li', h('div.row', dot('quiet'), h('span.row-main', h('span.row-title', e.line), h('span.row-sub', { 'data-at': e.at }, agoText(e.at)))))))
          : empty(playing ? 'The work starts moving in a few seconds.' : 'Paused. Press Live at the top to let the work move.')),
      h('p.small.muted.foot-note', dir === 'data'
        ? 'Everything here comes from data/company.json (the building), and from data/work.json and any tools connected to it (what is going on in it). A change to the work shows within a few seconds; reload after changing the building.'
        : 'Everything here comes from two files: sample/company.json (the building) and sample/work.json (what is going on in it). To show your own company, copy them into a folder called data beside them, change them and reload.'),
    ],
  };
}

function floorCard(floor) {
  return h('li', h('a.floor-card', { href: `#/${floor.id}` },
    h('span.tile-icon.plain', icon(floor === org.lobby ? 'globe' : floor === org.basement ? 'server' : floor.icon || 'box', 20)),
    h('span.floor-main', h('span.floor-name', floor.label), floor.about && h('span.row-sub', floor.about)),
    h('span.floor-states', floorLines(floor).map(chip))));
}

function viewCompany() {
  return {
    top: true,
    crumbs: [],
    body: [
      title(org.company),
      org.mission && h('p.mission', h('span.muted', 'Mission: '), org.mission),
      org.about && h('p', org.about),
      h('ul.floor-list', floors().map(floorCard)),
      memoryCard(),
    ],
  };
}

// What every agent is told: the company's memory, with a way to add to it and take from it.
function memoryCard() {
  const rows = memoryNow();
  const canAdd = dir !== 'data' || control.on;
  const add = (event) => {
    event.preventDefault();
    const input = event.currentTarget.elements.text;
    const text = rememberAsked(`remember ${input.value}`);
    if (!text) return;
    input.value = '';
    input.blur();
    rememberIt(text).then((said) => { controlNote = said; render(); });
  };
  return h('section.panel-card.memory',
    sectHead('archive', 'What every agent is told'),
    h('p.small.muted', dir === 'data'
      ? 'Decisions you asked the building to remember. Every Claude Code agent in the company\'s folders hears them as it starts, and one at work hears new ones with your next message.'
      : 'Decisions the building remembers. With your own company, every Claude Code agent hears them as it starts. These are made up.'),
    rows.length ? h('ul.list', rows.map((r) => h('li', h('div.row.memory-row', dot('quiet'), h('span.row-main', h('span.row-title', r.text)),
      (memoryWrites() || mineMemory.includes(r)) && btn('Forget', () => forgetIt(r))))))
      : empty('Nothing yet. Tell the receptionist "remember that ...".'),
    canAdd ? h('form.control-say', { onsubmit: add },
      h('input', { name: 'text', type: 'text', maxlength: 300, autocomplete: 'off', placeholder: 'We never push on a Friday', 'aria-label': 'Something every agent should be told' }),
      h('button.btn', { type: 'submit' }, 'Remember'))
      : h('p.small.muted', 'To add from here, start Arnheim with --control. Or edit data/memory.json.'),
    controlNote && h('p.small.muted', { role: 'status' }, controlNote));
}

function viewFloor(floor) {
  return {
    crumbs: crumbsFor(floor),
    body: [
      title(floor.label),
      floor === org.lobby && pauseCard(),
      h('p.states', floorLines(floor).map(chip)),
      floor.about && h('p', floor.about),
      floor.story && h('p.muted', floor.story),
      h('ul.room-list', roomsOf(floor).map((room) => {
        const info = roomModel(floor, room);
        return h('li', h(`a.room-tile.glow.glow-${info.state || 'quiet'}`, { href: `#/${floor.id}/${room.id}` },
          h('span.tile-icon', icon(ROOM_ICON[kindOf(floor, room)] || 'box', 20)),
          h('span.room-main', h('span.room-name', room.label), h('span.row-sub', info.sub ?? [info.big, info.detail].filter((x) => x != null && x !== '').join(' '))),
        ));
      })),
    ],
  };
}

function roomItems(floor, room, info) {
  const kind = kindOf(floor, room);
  if (kind === 'machine') {
    const jobs = work.jobs.filter((j) => j.machine === room.id && j.state !== 'done');
    return [
      h('p.states', chip({ text: info.big, kind: info.state })),
      jobs.length ? h('ul.list', jobs.map((j) => row(null, j.name, j.state === 'running' ? 'Running now' : 'Waiting in the queue', j.state === 'running' ? 'working' : 'quiet'))) : empty('No jobs here right now.'),
    ];
  }
  if (kind === 'code') {
    return [
      h('h3', 'Pull requests'),
      info.prs.length ? h('ul.list', info.prs.map((p) => row(p.href, p.title, p.sub, p.draft ? 'quiet' : 'check'))) : empty('No open pull requests.'),
      h('h3', 'Copies with unsaved changes'),
      info.copies.length ? h('ul.list', info.copies.map((c) => row(c.href, c.title, c.sub))) : empty('Everything is saved.'),
    ];
  }
  if (kind === 'company') return [h('ul.list', info.sections.map((s) => row(s.href, s.title, s.sub)))];
  const list = info.items || [];
  if (!list.length) return [empty('Nothing here yet.')];
  return [h('ul.list', list.map((x) => row(x.href, x.title, x.sub, x.mood || (x.working ? 'working' : x.check ? 'check' : x.reached ? 'ok' : 'quiet'))))];
}

function viewRoom(floor, room) {
  const info = roomModel(floor, room);
  return {
    crumbs: crumbsFor(floor, room),
    body: [
      title(room.label),
      room.about && h('p', room.about),
      ...roomItems(floor, room, info),
      control.on && kindOf(floor, room) === 'conversations' ? startForm(floor) : null,
    ],
  };
}

function facts(pairs) {
  return h('dl.facts', pairs.filter(([, v]) => v != null && v !== '').flatMap(([k, v]) => [h('dt', k), h('dd', v)]));
}

function viewItem(floor, room, id) {
  const kind = kindOf(floor, room);
  const gone = () => ({ crumbs: crumbsFor(floor, room), body: [title('Not here any more'), h('p', `That is not in ${room.label} now.`), h('a.btn', { href: `#/${floor.id}/${room.id}` }, `Back to ${room.label}`)] });
  const show = (heading, pairs, extra) => ({ crumbs: crumbsFor(floor, room, heading), body: [title(heading), facts(pairs), extra, h('a.btn', { href: `#/${floor.id}/${room.id}` }, icon('arrow-left', 15), `Back to ${room.label}`)] });
  if (floor === org.lobby) {
    const e = work.presence.find((x) => x.id === id);
    if (!e) return gone();
    const address = e.link && madeUp() ? `${e.link} (made up: the .example ending is kept for examples)` : e.link;
    return show(e.name, [['Kind', room.label], ['Status', e.status], ['Address', address || 'None written down'], ['Project', e.project], ['Last check', e.link ? (e.up ? 'Answered' : 'No answer') : null]]);
  }
  if (kind === 'library') {
    const b = work.library.find((x) => x.id === id);
    return b ? show(b.name, [['Status', b.status]], h('p.small.muted', 'A shelf, not an install: nothing here fetches or runs it.')) : gone();
  }
  if (kind === 'work') {
    const t = work.tasks.find((x) => x.id === id && x.project === floor.project);
    return t ? show(t.title, [['Status', STATUS[t.status]], ['Project', t.project], ['Note', t.note]]) : gone();
  }
  if (kind === 'goals') {
    const g = work.goals.find((x) => x.id === id && x.project === floor.project);
    return g ? show(g.title, [['Status', g.status === 'reached' ? 'Reached' : 'Open'], ['Project', g.project]]) : gone();
  }
  if (kind === 'conversations') {
    const c = work.conversations.find((x) => x.id === id && x.project === floor.project);
    const pr = c && proofOf(c);
    return c ? show(c.title, [['Now', c.working ? 'Working' : c.check ? 'To check' : 'Quiet'], ['Agent', c.agent || (REACHABLE.test(c.id) ? 'Claude Code' : null)], ['Project', c.project], ['Last said', c.says?.now || control.run(c.id)?.said],
      ['Its work', pr && `${pr.word}. ${pr.line}`]], [proofPart(c, pr), control.on ? convoControls(c) : null]) : gone();
  }
  if (kind === 'code') {
    const [what, key] = id.split('/');
    if (what === 'pr') {
      const p = work.pullRequests.find((x) => String(x.number) === key && x.project === floor.project);
      return p ? show(`#${p.number} ${p.title}`, [['Status', p.draft ? 'Draft' : 'Ready for review'], ['Project', p.project]]) : gone();
    }
    const c = work.copies.find((x) => x.id === key && x.project === floor.project);
    return c ? show(c.name, [['Unsaved', count(c.changes, 'change', 'changes')], ['Project', c.project]]) : gone();
  }
  if (kind === 'company') {
    const name = id.split('/')[1];
    if (!COMPANY_SECTIONS.includes(name)) return gone();
    const list = work.company.filter((e) => e.section === name);
    return {
      crumbs: crumbsFor(floor, room, name),
      body: [title(name), list.length ? h('ul.list', list.map((e) => row(null, e.name, e.note))) : empty('Nothing here yet.'), h('a.btn', { href: `#/${floor.id}/${room.id}` }, icon('arrow-left', 15), `Back to ${room.label}`)],
    };
  }
  return gone();
}

function viewFor(r) {
  if (!r.floor) return viewOverview();
  if (r.floor === 'company') return viewCompany();
  if (r.floor === 'front-desk') return poe.view();
  const floor = floors().find((f) => f.id === r.floor);
  if (!floor) return viewOverview();
  const room = r.room && roomsOf(floor).find((x) => x.id === r.room);
  if (!room) return viewFloor(floor);
  return r.item ? viewItem(floor, room, r.item) : viewRoom(floor, room);
}

/* ---------- drawing ---------- */

function renderCrumbs(crumbs) {
  $('crumbs').replaceChildren(h('ol', crumbs.map(([label, href], i) => h('li',
    href && i < crumbs.length - 1 ? h('a', { href }, label) : h('span', { 'aria-current': 'page' }, label)))));
}

function renderTabs() {
  const tab = !route.floor ? 'overview' : route.floor === 'front-desk' ? 'poe' : 'company';
  for (const name of ['overview', 'company', 'poe']) {
    const el = $(`tab-${name}`);
    if (name === tab) el.setAttribute('aria-current', 'page');
    else el.removeAttribute('aria-current');
  }
}

function render({ nav = false } = {}) {
  const panel = $('content');
  const active = document.activeElement;
  // Never redraw under someone's typing: wait until they leave the box.
  if (!nav && panel.contains(active) && active.matches('input, select, textarea')) {
    pending = true;
    return;
  }
  pending = false;
  const focusHref = !nav && panel.contains(active) ? active.getAttribute('href') : null;
  const scroll = panel.scrollTop;
  const view = viewFor(route);
  renderCrumbs(view.crumbs || []);
  $('panel-head').hidden = !!view.top;
  renderTabs();
  panel.replaceChildren(...[view.body].flat(Infinity).filter(Boolean));
  if (nav) {
    panel.scrollTop = 0;
    $('view-title')?.focus({ preventScroll: true });
  } else {
    panel.scrollTop = scroll;
    if (focusHref) [...panel.querySelectorAll('a')].find((a) => a.getAttribute('href') === focusHref)?.focus({ preventScroll: true });
  }
}

function tick() {
  for (const el of document.querySelectorAll('[data-at]')) el.textContent = agoText(Number(el.dataset.at));
}

function refresh() {
  building?.setLive(liveModel());
  render();
}

/* ---------- the story: work moving on a loop ---------- */

function step() {
  if (!playing || document.hidden || !work.story?.length) return;
  const s = work.story[storyAt % work.story.length];
  storyAt += 1;
  for (const [list, id, patch] of s.change || []) {
    const thing = (work[list] || []).find((x) => x.id === id);
    if (thing) Object.assign(thing, patch);
  }
  happened.unshift({ line: s.line, at: Date.now() });
  happened.length = Math.min(happened.length, 6);
  refresh();
}

function setPlaying(on) {
  playing = on;
  const b = $('live');
  b.setAttribute('aria-pressed', String(on));
  b.replaceChildren(h('span.live-dot', { 'aria-hidden': 'true' }), on ? 'Live' : 'Paused');
  b.setAttribute('aria-label', on ? 'The work is moving. Press to pause it.' : 'Paused. Press to let the work move again.');
  if (!route.floor) render();
}

/* ---------- scenes, theme, routes ---------- */

function applyScene() {
  const mode = SCENE_NAMES[sceneId] ? { mode: sceneId } : { mode: 'floor', floor: sceneId };
  building?.setScene(mode);
  for (const el of $('scenes').children) el.setAttribute('aria-pressed', String(el.dataset.scene === sceneId));
}

function setupScenes() {
  let saved = params.get('scene');
  if (!saved) { try { saved = localStorage.getItem('arnheim-scene'); } catch { saved = null; } }
  const list = [...Object.entries(SCENE_NAMES), ...org.floors.map((f) => [f.id, f.label])];
  if (list.some(([id]) => id === saved)) sceneId = saved;
  $('scenes').replaceChildren(...list.map(([id, name]) => h('button.scene', {
    type: 'button',
    'data-scene': id,
    onclick: () => {
      sceneId = id;
      try { localStorage.setItem('arnheim-scene', id); } catch { /* it just won't be remembered */ }
      applyScene();
    },
  }, icon(SCENE_ICON[id] || org.floors.find((f) => f.id === id)?.icon || 'box', 18), h('span', name))));
}

function isDark() {
  const set = document.documentElement.dataset.theme;
  return set ? set === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches;
}

function applyTheme() {
  const dark = isDark();
  $('theme').replaceChildren(icon(dark ? 'sun' : 'moon', 15), dark ? 'Light' : 'Dark');
  $('theme').setAttribute('aria-label', dark ? 'Switch to light mode' : 'Switch to dark mode');
  building?.setTheme(dark);
}

function setupTheme() {
  let saved = params.get('theme');
  if (saved !== 'light' && saved !== 'dark') { try { saved = localStorage.getItem('arnheim-theme'); } catch { saved = null; } }
  if (saved === 'light' || saved === 'dark') document.documentElement.dataset.theme = saved;
  $('theme').addEventListener('click', () => {
    const next = isDark() ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem('arnheim-theme', next); } catch { /* it just won't be remembered */ }
    applyTheme();
  });
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', applyTheme);
  applyTheme();
}

function readRoute() {
  const parts = location.hash.replace(/^#\/?/, '').split('/').filter(Boolean).map((part) => {
    try { return decodeURIComponent(part); } catch { return ''; }
  });
  const [floor, room, ...rest] = parts;
  route = { floor, room, item: rest.join('/') };
}

function parentHash() {
  if (TOP_ROUTES.has(route.floor)) return '#/';
  if (route.item) return `#/${route.floor}/${route.room}`;
  if (route.room) return `#/${route.floor}`;
  return '#/company';
}

function focusBuilding() {
  if (route.floor === 'front-desk' && org.lobby) {
    const desk = org.lobby.rooms.find((r) => kindOf(org.lobby, r) === 'websites') || org.lobby.rooms[0];
    if (!poe.touring()) building?.focus({ floor: org.lobby.id, room: desk?.id, item: DESK, close: true });
    return false;
  }
  const isFloor = floors().some((f) => f.id === route.floor);
  building?.focus(isFloor ? { floor: route.floor, room: route.room, item: location.hash } : {});
  return isFloor;
}

function onRoute() {
  controlNote = ''; // a note on the last thing done belongs to the page it was done on
  readRoute();
  if (route.floor !== 'front-desk') poe.stopTour(false);
  else primeBrain('receptionist');
  render({ nav: true });
  const isFloor = focusBuilding();
  $('view-back').hidden = !isFloor;
  $('stage-help').textContent = route.floor === 'front-desk' ? `${deskName() || 'The receptionist'} is at the front desk. Drag to turn, scroll to zoom.`
    : !isFloor ? 'Tap a floor to bring it out. Drag to turn, scroll to zoom.'
      : !route.room ? 'Tap a room or anything in it. Drag to turn.' : 'Tap anything to open it. Drag to turn.';
}

/* ---------- starting the building, and bringing it back if the browser drops it ---------- */

const MODEL_WAITS = [1000, 5000, 15000]; // a fresh start after each of these, then a Try again button
const MODEL_HANDBACK_MS = 4000; // how long the browser gets to hand a lost picture back by itself
const MODEL_STEADY_MS = 60000; // this long with no trouble and fresh starts are available again
let modelTries = 0;
let modelTimer = 0;
let steadyTimer = 0;
let modelLoaded = false;

function stageMessage(text, canRetry = false) {
  $('stage-fail').hidden = !text;
  $('stage-fail-text').textContent = text;
  $('stage-retry').hidden = !canRetry;
  $('stage-help').hidden = !!text;
}

function restartModel() {
  clearTimeout(modelTimer);
  clearTimeout(steadyTimer);
  building?.dispose();
  setWalking(false);
  building = null;
  if (modelTries >= MODEL_WAITS.length) {
    stageMessage('The 3D building is not showing right now. Everything is still here in the panel.', true);
    return;
  }
  stageMessage('The 3D building dropped out. Bringing it back.');
  modelTimer = setTimeout(startBuilding, MODEL_WAITS[modelTries]);
  modelTries += 1;
}

function onModelStatus(status) {
  clearTimeout(modelTimer);
  clearTimeout(steadyTimer);
  if (status === 'lost') {
    stageMessage('The 3D building dropped out. Bringing it back.');
    modelTimer = setTimeout(restartModel, MODEL_HANDBACK_MS);
  } else if (status === 'blank') {
    restartModel();
  } else {
    stageMessage('');
    steadyTimer = setTimeout(() => { modelTries = 0; }, MODEL_STEADY_MS);
  }
}

async function startBuilding() {
  if (params.has('list')) {
    document.body.classList.add('no-3d');
    $('walk').hidden = true;
    return;
  }
  try {
    const { createBuilding } = await import('./building.js');
    modelLoaded = true;
    const tip = $('tip');
    // A canvas that has had graphics can't be given new ones, so every start gets its own.
    const canvas = $('scene').cloneNode(false);
    $('scene').replaceWith(canvas);
    building = createBuilding(canvas, org, {
      look: params.get('look') || undefined, // ?look=photo: the photo-real building
      talk,
      labels: $('labels'),
      onStatus: onModelStatus,
      onWalk: setWalking,
      onNotes: showNotes,
      onPick(hit) {
        tip.hidden = true;
        if (hit.company) { location.hash = '#/company'; return; }
        if (hit.href === DESK) { primeBrain('receptionist'); location.hash = DESK; return; }
        if (isAide(hit)) { primeBrain('assistant'); return; } // she has no page of her own: the talk opens in the walk
        if (hit.walk) { location.hash = hit.href || `#/${hit.floorId}/${hit.roomId}`; return; }
        if (route.floor !== hit.floorId) { location.hash = `#/${hit.floorId}`; return; }
        location.hash = hit.href || `#/${hit.floorId}/${hit.roomId}`;
      },
      onHover(info, x, y) {
        tip.hidden = !info;
        if (!info) return;
        tip.textContent = [info.title, info.sub].filter(Boolean).join('. ');
        tip.style.left = `${Math.min(x + 14, $('stage').clientWidth - 270)}px`;
        tip.style.top = `${Math.max(y - 40, 6)}px`;
      },
    });
    building.setTheme(isDark());
    building.setLive(liveModel());
    showNotes();
    applyScene();
    focusBuilding();
    window.__arnheim = { building, model: liveModel, poe, control, brain, talk, facts: brainFacts };
  } catch (error) {
    console.error(error);
    building = null;
    restartModel();
  }
}

/* ---------- walking through the building ---------- */

// The founder's notes, hung in their office on a walk, from notes.json beside the company's other
// files (made up in the sample). They are read again whenever someone walks into the office, so an
// edited note shows the next time. A company with no notes.json simply has none.
let notesFrom = 0;
let noNotes = false;
async function showNotes() {
  if (noNotes) return;
  try {
    const reply = await fetch(`${dir}/notes.json`, { cache: 'no-store' });
    if (reply.status === 404) noNotes = true; // not asked for again until the page is reloaded
    if (!reply.ok) return;
    const { notes = [] } = await reply.json();
    notesFrom ||= Date.now();
    building?.setNotes(notes.map((n) => ({ ...n, when: n.when ?? notesFrom - (Number(n.hoursAgo) || 0) * 3600000 })));
  } catch (error) {
    console.warn(`Arnheim: ${dir}/notes.json could not be read, so the office has no notes.`, error); // the office is simply as it was
  }
}

function setWalking(on) {
  $('walk').setAttribute('aria-pressed', String(!!on));
}

async function toggleWalk() {
  if (!building) return;
  const on = !building.walking();
  setWalking(on);
  document.activeElement?.blur?.(); // so Space and Enter don't press the button again mid-walk
  setWalking(await building.walk(on));
}

function setupStageTools() {
  $('zoom-in').addEventListener('click', () => building?.zoomBy(0.86));
  $('zoom-out').addEventListener('click', () => building?.zoomBy(1.16));
  $('view-reset').addEventListener('click', () => building?.resetView());
  $('view-back').addEventListener('click', () => { location.hash = '#/company'; });
  $('stage-retry').addEventListener('click', () => {
    if (!modelLoaded) { location.reload(); return; } // the files themselves never arrived
    modelTries = 0;
    stageMessage('Starting the 3D building again.');
    startBuilding();
  });
  $('stage').addEventListener('keydown', (event) => {
    if (event.target !== $('stage') || building?.walking?.()) return;
    const turns = { ArrowLeft: [-6, 0], ArrowRight: [6, 0], ArrowUp: [0, 4], ArrowDown: [0, -4] };
    if (turns[event.key]) { event.preventDefault(); building?.turn(...turns[event.key]); }
    else if (event.key === '+' || event.key === '=') building?.zoomBy(0.86);
    else if (event.key === '-') building?.zoomBy(1.16);
    else if (event.key === '0') building?.resetView();
  });
  // Hovering or focusing a link in the panel lights up the room it leads to.
  const light = (event) => {
    const link = event.target.closest?.('a[href^="#/"]');
    const [floor, room] = link ? link.getAttribute('href').replace(/^#\/?/, '').split('/') : [];
    building?.highlight(floors().some((f) => f.id === floor) ? { floor, room } : null);
  };
  for (const name of ['mouseover', 'focusin']) $('content').addEventListener(name, light);
  $('content').addEventListener('mouseleave', () => building?.highlight(null));
}

function setupIcons() {
  $('top').querySelector('h1').prepend(icon('building-2', 18));
  $('tab-overview').prepend(icon('layers', 15));
  $('tab-company').prepend(icon('building-2', 15));
  const desk = $('tab-poe');
  desk.textContent = deskTab();
  desk.prepend(poeBadge(18, org.receptionist?.look));
  $('back').prepend(icon('arrow-left', 15));
  $('view-back').prepend(icon('arrow-left', 15));
  $('view-reset').prepend(icon('rotate-ccw', 14));
}

/* ---------- reading the company's files ---------- */

const LISTS = ['tasks', 'goals', 'conversations', 'pullRequests', 'copies', 'company', 'presence', 'machines', 'jobs', 'library', 'story'];
const problem = (text, status) => Object.assign(new Error(text), { own: true, status });

// One of the company's files, or an error that says which one and why.
async function readJson(path) {
  const reply = await fetch(path, { cache: 'no-store' });
  if (!reply.ok) throw problem(`${path} could not be read: the server answered ${reply.status}.`, reply.status);
  const text = await reply.text();
  try {
    return JSON.parse(text);
  } catch (error) {
    throw problem(`${path} is not valid JSON (${error.message}).`);
  }
}

// Plain words for the mistakes in a company map that would otherwise leave the building blank.
function checkMap(map, path) {
  const fail = (why) => { throw problem(`${path}: ${why}`); };
  const named = (x) => typeof x?.id === 'string' && /^[A-Za-z0-9_-]+$/.test(x.id) && !!x.label;
  if (!map || typeof map !== 'object' || Array.isArray(map)) fail('it should be one object, between { and }.');
  if (!map.company) fail('it needs "company", the company\'s name.');
  if (!Array.isArray(map.floors) || !map.floors.length) fail('it needs "floors", a list of at least one floor.');
  const ids = new Set();
  for (const floor of [...map.floors, map.lobby, map.basement].filter(Boolean)) {
    if (!named(floor)) fail('every floor needs a "label" and an "id" made of letters, numbers, dashes or underscores.');
    if (ids.has(floor.id)) fail(`two floors have the id "${floor.id}".`);
    ids.add(floor.id);
    const rooms = floor.rooms || map.rooms;
    if (!Array.isArray(rooms)) fail(`the floor "${floor.id}" has no rooms. Give it "rooms", or give the company a "rooms" list that every floor shares.`);
    const all = [...rooms, ...(Array.isArray(floor.extraRooms) ? floor.extraRooms : [])];
    if (all.length > 5) fail(`the floor "${floor.id}" has ${all.length} rooms, and a floor holds at most five.`);
    if (!all.every(named)) fail(`on the floor "${floor.id}", every room needs a "label" and an "id" made of letters, numbers, dashes or underscores.`);
  }
  for (const floor of map.floors) floor.project ||= floor.label; // what work.json calls its project
  return map;
}

// Your own company from data/ when data/company.json is there, or else the made-up sample. ?sample
// in the address shows the sample anyway. Every list in work.json is optional, and so is
// data/work.json itself: without it the building stands quiet.
async function readCompany() {
  let map = null;
  if (!params.has('sample')) {
    try {
      map = await readJson('data/company.json');
      dir = 'data';
      feeds = feedList(map);
    } catch (error) {
      if (error.status !== 404) throw error;
    }
  }
  const [mapRead, now] = await Promise.all([map || readJson(`${dir}/company.json`), readWork()]);
  return [checkMap(mapRead, `${dir}/company.json`), now];
}

// The files that tools keep up to date for your own company, such as connect/claude_code.py's
// (docs/connect.md): "feeds" in company.json, each a path inside data/.
function feedList(map) {
  const list = Array.isArray(map?.feeds) ? map.feeds : [];
  return list.filter((path) => typeof path === 'string' && /^[\w-]+(\/[\w.-]+)*\.json$/.test(path) && !path.includes('..'));
}

// What is going on: work.json, with every list in each feed added to it. A feed that isn't written
// yet counts as empty; one caught mid-change keeps what it said last time.
async function readWork() {
  const now = await readJson(`${dir}/work.json`).catch((error) => {
    if (dir === 'data' && error.status === 404) return {};
    throw error;
  });
  if (!now || typeof now !== 'object' || Array.isArray(now)) throw problem(`${dir}/work.json: it should be one object, between { and }.`);
  for (const key of LISTS) if (!Array.isArray(now[key])) now[key] = [];
  for (const path of feeds) {
    let feed = lastFeed.get(path) || null;
    try {
      feed = await readJson(`data/${path}`);
    } catch (error) {
      if (error.status === 404) feed = null;
    }
    if (!feed || typeof feed !== 'object') continue;
    lastFeed.set(path, feed);
    for (const key of LISTS) if (Array.isArray(feed[key])) now[key].push(...feed[key].filter((x) => x && typeof x === 'object'));
  }
  now.memory = await readMemory();
  history = await readHistory();
  return now;
}

// Today's moments, for the replay: data/feeds/history/<today>.json for your own company, or the sample's,
// whose times count back from when the page opened.
let history = [];
let sampleHistory = null;
async function readHistory() {
  try {
    if (dir !== 'data') {
      if (!sampleHistory) {
        const opened = Date.now() / 1000;
        const m = await readJson(`${dir}/history.json`);
        sampleHistory = (Array.isArray(m?.moments) ? m.moments : []).map((x) => ({ ...x, at: opened - (Number(x.ago) || 0) }));
      }
      return sampleHistory;
    }
    const m = await readJson(`data/feeds/history/${localDay()}.json`);
    return Array.isArray(m?.moments) ? m.moments : [];
  } catch (error) {
    return error.status === 404 ? [] : history;
  }
}

// The company's memory: memory.json beside company.json, written through control (docs/connect.md,
// "Company memory"). None yet is an empty memory; one caught mid-change keeps what it said last time.
let lastMemory = [];
let noMemoryUntil = 0; // with no memory.json yet, look again every half a minute, not every few seconds
async function readMemory() {
  if (Date.now() < noMemoryUntil) return lastMemory;
  try {
    const m = await readJson(`${dir}/memory.json`);
    lastMemory = (Array.isArray(m?.memory) ? m.memory : []).filter((r) => r && typeof r === 'object' && typeof r.text === 'string' && r.text.trim());
  } catch (error) {
    if (error.status === 404) {
      lastMemory = [];
      noMemoryUntil = Date.now() + 30000;
    }
  }
  return lastMemory;
}

// Your own company's work is read again every few seconds, so the building follows it as it
// changes: an edit to work.json, or a tool writing its feed.
async function followWork() {
  if (document.hidden) return;
  try {
    const now = await readWork();
    const sig = JSON.stringify(now);
    if (sig === workSig) return;
    workSig = sig;
    now.tasks.push(...mine);
    for (const task of now.tasks) if (dropped.has(task.id)) task.status = 'dropped';
    work = now;
    if (replayAt != null) replayed();
    refresh();
  } catch {
    // a file mid-edit: the building stays as it was until the next look
  }
}

async function boot() {
  try {
    [[org, work]] = await Promise.all([readCompany(), brain.check()]); // the desk's words depend on the brain
    workSig = JSON.stringify(work);
  } catch (error) {
    console.error(error);
    $('content').replaceChildren(h('p.banner.fail', error.own
      ? `The company could not be shown. ${error.message}`
      : 'The company could not be read. Serve this folder (python3 serve.py) and open the address it prints.'));
    return;
  }
  document.title = madeUp() ? `Arnheim: ${org.company}, a made-up company` : `Arnheim: ${org.company}`;
  $('made-up').hidden = !madeUp();
  $('live').hidden = !hasStory();
  setupDesk();
  readRoute();
  setupTheme();
  setupIcons();
  setupScenes();
  setupStageTools();
  setPlaying(params.get('live') !== 'off');
  $('live').addEventListener('click', () => setPlaying(!playing));
  $('walk').addEventListener('click', toggleWalk);
  await startBuilding();
  onRoute();
  window.addEventListener('hashchange', onRoute);
  $('back').addEventListener('click', () => { location.hash = parentHash(); });
  $('content').addEventListener('focusout', () => { if (pending) setTimeout(render, 0); });
  document.addEventListener('keydown', (event) => {
    if (building?.walking?.()) return; // the walk has its own keys
    const typing = event.target.matches?.('input, select, textarea, [contenteditable]');
    const free = !typing && !event.metaKey && !event.ctrlKey && !event.altKey;
    if (event.key === 'Escape') {
      if (poe.touring()) poe.stopTour(true);
      else if (!typing && !TOP_ROUTES.has(route.floor)) location.hash = parentHash();
    } else if (TAB_KEYS[event.key] && free) {
      event.preventDefault();
      location.hash = TAB_KEYS[event.key];
    }
  });
  setInterval(step, Math.max(2, Number(work.every) || 6) * 1000);
  setInterval(tick, 1000);
  if (dir === 'data') setInterval(followWork, FOLLOW_MS);
  if (dir === 'data' && !madeUp()) {
    // Control is off unless serve.py says it is on; then the panel follows what waits for you.
    let seen = '';
    control.watch((s) => {
      const sig = JSON.stringify([s.on, s.asks.map((a) => a.id), s.runs.map((r) => [r.key, r.state, r.answered]), s.projects.length, s.paused, s.allowed]);
      if (sig === seen) return;
      seen = sig;
      refresh();
    });
    control.start();
  }
}

boot();
