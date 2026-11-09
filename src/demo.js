// The Arnheim page: a company shown as a building, with a panel to look around it and Poe at the
// front desk. It shows your own company from data/ (company.json, work.json and notes.json) when
// data/company.json is there, and otherwise the sample, a company that is made up (sample/). The
// sample's work moves on a loop (the story at the end of its work.json), so there is always
// something to see. Nothing is saved anywhere: a reload reads the files again.
import { icon } from './icons.js';
import { createPoe, has, insertAfter, norm, poeBadge } from './poe-desk.js';

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
const TOP_ROUTES = new Set([undefined, 'company', 'poe']);
const TAB_KEYS = { 1: '#/', 2: '#/company', 3: '#/poe' };

let org = null; // the company map: floors and rooms
let work = null; // what is going on in it
let dir = 'sample'; // where they came from: data (your own company) or sample (made up)
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
    const list = work.conversations.filter((c) => c.project === project).sort((a, b) => (!!b.working - !!a.working) || (!!b.check - !!a.check));
    const working = list.filter((c) => c.working).length;
    const checks = list.filter((c) => c.check).length;
    return {
      state: checks ? 'check' : working ? 'working' : 'quiet', big: list.length, detail: checks ? `open, ${checks} to check` : 'open', working: working > 0,
      items: list.map((c) => ({ id: c.id, title: c.title, working: !!c.working, check: !!c.check, sub: c.working ? 'Working now' : c.check ? 'To check' : 'Quiet', href: convoHref(c) })),
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

/* ---------- Poe: plain facts from the sample, no AI ---------- */

function poeFacts() {
  const open = openTasks();
  const link = (t) => ({ title: t.title, sub: t.project, href: taskHref(t) });
  const convo = (c) => ({ title: c.title, sub: c.project, href: convoHref(c) });
  const needs = open.filter((t) => t.status === 'needs_you');
  const machines = org.basement ? org.basement.rooms.filter((r) => kindOf(org.basement, r) === 'machine').map((r) => ({ id: r.id, label: r.label, ...roomModel(org.basement, r) })) : [];
  return {
    needs: needs.map((t) => ({ ...link(t), mood: 'needs' })),
    needsBy: Object.fromEntries(org.floors.map((f) => [f.project, needs.filter((t) => t.project === f.project).length])),
    openBy: Object.fromEntries(org.floors.map((f) => [f.project, open.filter((t) => t.project === f.project).length])),
    later: 0,
    toCheck: byProject(work.conversations.filter((c) => c.check)).map(convo),
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

// Poe can add a task and drop it again, in this tab only.
async function addTask({ project, title: text }) {
  added += 1;
  const task = { id: `new${added}`, project, title: text, status: 'needs_you', note: 'Taken down by Poe when you asked. It lives in this tab only: nothing is saved.' };
  work.tasks.push(task);
  refresh();
  return { ok: true, task };
}

async function dropTask(id) {
  const task = work.tasks.find((t) => t.id === id);
  if (!task) return { ok: false, error: 'that task is not here any more' };
  task.status = 'dropped';
  refresh();
  return { ok: true };
}

function setupPoe() {
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
        ? 'Goals and everything else come from the company\'s own files, data/company.json and data/work.json. Change them and reload.'
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
      role: madeUp() ? 'Receptionist. Every answer comes from the sample company.' : `Receptionist. Every answer comes from ${org.company}'s own files.`,
      unknown: `I don't know that, and I won't guess. I only know what ${madeUp() ? 'the sample company holds' : `${org.company}'s files hold`}.`,
      note: 'Poe can add a task and undo it, in this tab only. Nothing is saved, and Poe never merges, publishes, runs jobs or signs in.',
      added: 'It is in the Work room now, in this tab only.',
      keys: '1 Overview, 2 Company, 3 Poe. Esc goes back. Arrow keys turn the building, plus and minus zoom. They do nothing while you are typing.',
    },
    topics: (list) => insertAfter(insertAfter(list, 'thanks', [real]), 'tour', [howTo]),
  });
}

/* ---------- talking in the walk (voice.js) ---------- */

// Poe answers as at the desk. The people at work answer from their own lines in work.json ("says"),
// with no AI; in the sample they are made up, and so is what they say. A page with real agents
// passes its own answers, and there what you say reaches the agent doing the work.
const talkItem = (who) => work.conversations.find((c) => convoHref(c) === who.href) || work.tasks.find((t) => taskHref(t) === who.href) || null;

function poeSays(text) {
  if (has(norm(text), ['tour', 'show me round', 'show me around', 'look around'])) return 'I can show you round from the Poe tab, once you leave the walk.';
  const a = poe.answer(text);
  if (a.offer) return `I can add "${a.offer.title}" as a task from the Poe tab, where you pick its project.`;
  const lines = [...a.lines];
  // The things an answer links to belong to its first line, so they are said right after it.
  if (a.links?.length && a.links.length <= 4) lines.splice(1, 0, `${a.links.map((x) => (x.sub ? `${x.title}, on ${x.sub}` : x.title)).join('. ')}.`);
  return lines.join(' ');
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

// The founder's assistant (org.assistant), in their office: in the sample she answers as Poe does.
const isAide = (who) => !!org.assistant && who.href === (org.assistant.href || '#/assistant');

const talk = {
  name(who) {
    if (who.href === '#/poe') return 'Poe';
    if (isAide(who)) return org.assistant.name;
    const item = talkItem(who);
    return item ? `${item.project} agent` : null;
  },
  greet(who) {
    if (who.href === '#/poe') {
      const hr = new Date().getHours();
      const hello = hr >= 5 && hr < 12 ? 'Good morning' : hr >= 12 && hr < 18 ? 'Good afternoon' : hr >= 18 && hr < 23 ? 'Good evening' : 'Hello';
      return `${hello}. Ask me what's happening, or anything about the building.`;
    }
    if (isAide(who)) {
      const hello = `Hello. I'm ${org.assistant.name}, ${org.founder?.name || 'the founder'}'s assistant.`;
      return madeUp() ? `${hello} This company is made up, and so am I. Ask me anything about it.` : `${hello} Ask me anything about ${org.company}.`;
    }
    const item = talkItem(who);
    return item ? `Hi. I'm on "${item.title}". Ask me how it's going.` : null;
  },
  answer(who, text) {
    if (who.href === '#/poe' || isAide(who)) return poeSays(text);
    const item = talkItem(who);
    return item ? sampleReply(item, text) : "I've finished here, so there's nothing new to tell.";
  },
};

/* ---------- the panel ---------- */

function crumbsFor(floor, room, last) {
  const list = [[org.company, '#/company']];
  if (floor) list.push([floor.label, `#/${floor.id}`]);
  if (room) list.push([room.label, `#/${floor.id}/${room.id}`]);
  if (last) list.push([last]);
  return list;
}

function viewOverview() {
  const needs = openTasks().filter((t) => t.status === 'needs_you');
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
        h('p.small.muted', 'Arnheim shows a company as a building. Each floor is a project and each room holds one kind of thing. Tap a floor to bring it out, then a room to look inside. Poe, at the front desk, answers questions.')),
      h('div.stats', tile('bell-ring', 'needs', needs.length, 'Need you'), tile('messages-square', 'working', talking.length, 'Working now'), tile('server', 'working', jobs.length, 'Jobs running')),
      h('section.panel-card',
        sectHead('bell', 'Needs you'),
        needs.length ? h('ul.list', needs.map((t) => row(taskHref(t), t.title, t.project, 'needs'))) : empty('Nothing needs you right now.')),
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
        ? 'Everything here comes from data/company.json (the building) and data/work.json (what is going on in it). Change them and reload.'
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
    ],
  };
}

function viewFloor(floor) {
  return {
    crumbs: crumbsFor(floor),
    body: [
      title(floor.label),
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
    return c ? show(c.title, [['Now', c.working ? 'Working' : c.check ? 'To check' : 'Quiet'], ['Project', c.project]]) : gone();
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
  if (r.floor === 'poe') return poe.view();
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
  const tab = !route.floor ? 'overview' : route.floor === 'poe' ? 'poe' : 'company';
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
  if (route.floor === 'poe' && org.lobby) {
    const desk = org.lobby.rooms.find((r) => kindOf(org.lobby, r) === 'websites') || org.lobby.rooms[0];
    if (!poe.touring()) building?.focus({ floor: org.lobby.id, room: desk?.id, item: '#/poe', close: true });
    return false;
  }
  const isFloor = floors().some((f) => f.id === route.floor);
  building?.focus(isFloor ? { floor: route.floor, room: route.room, item: location.hash } : {});
  return isFloor;
}

function onRoute() {
  readRoute();
  if (route.floor !== 'poe') poe.stopTour(false);
  render({ nav: true });
  const isFloor = focusBuilding();
  $('view-back').hidden = !isFloor;
  $('stage-help').textContent = route.floor === 'poe' ? 'Poe is at the front desk. Drag to turn, scroll to zoom.'
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
      talk,
      labels: $('labels'),
      onStatus: onModelStatus,
      onWalk: setWalking,
      onNotes: showNotes,
      onPick(hit) {
        tip.hidden = true;
        if (hit.company) { location.hash = '#/company'; return; }
        if (hit.href === '#/poe') { location.hash = '#/poe'; return; }
        if (isAide(hit)) return; // she has no page of her own: the talk opens in the walk
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
    window.__arnheim = { building, model: liveModel, poe };
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
  $('tab-poe').prepend(poeBadge(18));
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
    } catch (error) {
      if (error.status !== 404) throw error;
    }
  }
  const [mapRead, now] = await Promise.all([
    map || readJson(`${dir}/company.json`),
    readJson(`${dir}/work.json`).catch((error) => {
      if (dir === 'data' && error.status === 404) return {};
      throw error;
    }),
  ]);
  if (!now || typeof now !== 'object' || Array.isArray(now)) throw problem(`${dir}/work.json: it should be one object, between { and }.`);
  for (const key of LISTS) if (!Array.isArray(now[key])) now[key] = [];
  return [checkMap(mapRead, `${dir}/company.json`), now];
}

async function boot() {
  try {
    [org, work] = await readCompany();
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
  setupPoe();
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
}

boot();
