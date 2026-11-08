// The Arnheim demo page: a company that is made up (sample/company.json and sample/work.json)
// shown as a building, with a panel to look around it and Poe at the front desk. The work moves
// on a loop (the story at the end of work.json), so there is always something to see. Nothing is
// saved anywhere: a reload starts the sample again.
import { icon } from './icons.js';
import { createPoe, has, insertAfter, poeBadge } from './poe-desk.js';

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

/* ---------- reading the sample ---------- */

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
      lines: [org.sample || `${org.company} is a sample.`, 'The work you see moving is a short story on a loop, so the building has something to show. The Live button at the top pauses it.'],
    },
  };
  const howTo = {
    id: 'how-to',
    answer: (c) => has(c.q, ['task', 'goal']) && has(c.q, ['add', 'new', 'set', 'write', 'make', 'create']) && {
      lines: ['Tell me "remind me to ..." and I will add it as a task, in this tab only.', 'Goals and everything else come from the sample files, sample/company.json and sample/work.json. Change them and reload to make the building your own.'],
    },
  };
  poe = createPoe({
    h, btn, title, row, taskHref, addTask, dropTask,
    org: () => org,
    facts: poeFacts,
    focusModel: (floorId) => (floorId ? building?.focus({ floor: floorId }) : focusBuilding()),
    reduced: reducedMotion,
    words: {
      place: `This is Arnheim, showing ${org.company}, a company that is made up. Each floor is a project and each room holds one kind of thing. The light shows what is happening.`,
      hints: ['What is Arnheim?', 'What needs me?', "What's running?", 'Who runs this company?', 'Where is the website?', 'Is this real?', 'What do the colours mean?'],
      role: 'Receptionist. Every answer comes from the sample company.',
      unknown: "I don't know that, and I won't guess. I only know what the sample company holds.",
      note: 'Poe can add a task and undo it, in this tab only. Nothing is saved, and Poe never merges, publishes, runs jobs or signs in.',
      added: 'It is in the Work room now, in this tab only.',
      keys: '1 Overview, 2 Company, 3 Poe. Esc goes back. Arrow keys turn the building, plus and minus zoom. They do nothing while you are typing.',
    },
    topics: (list) => insertAfter(insertAfter(list, 'thanks', [real]), 'tour', [howTo]),
  });
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
  const needs = openTasks().filter((t) => t.status === 'needs_you');
  const talking = byProject(work.conversations.filter((c) => c.working));
  const jobs = work.jobs.filter((j) => j.state === 'running');
  const tile = (glyph, mood, n, label) => h(`div.stat.glow.glow-${n ? mood : 'quiet'}`, h('span.stat-top', h('span.tile-icon', icon(glyph, 20)), h('span.stat-num', String(n))), h('span.stat-label', label));
  return {
    top: true,
    crumbs: [],
    body: [
      h('section.panel-card.intro',
        title(`${org.company}, a company that is made up`),
        h('p', org.sample),
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
            ...jobs.map((j) => row(`#/${org.basement.id}/${j.machine}`, j.name, `On the ${machineLabel(j.machine)}`, 'working')),
          ])
          : empty('Nothing is working right now.')),
      h('section.panel-card',
        sectHead('history', 'Just now'),
        happened.length
          ? h('ul.list.happened', happened.map((e) => h('li', h('div.row', dot('quiet'), h('span.row-main', h('span.row-title', e.line), h('span.row-sub', { 'data-at': e.at }, agoText(e.at)))))))
          : empty(playing ? 'The work starts moving in a few seconds.' : 'Paused. Press Live at the top to let the work move.')),
      h('p.small.muted.foot-note', 'Everything here comes from two files: sample/company.json (the building) and sample/work.json (what is going on in it). Change them and reload to make it your own.'),
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
    return show(e.name, [['Kind', room.label], ['Status', e.status], ['Address', e.link ? `${e.link} (made up: the .example ending is kept for examples)` : 'None written down'], ['Project', e.project], ['Last check', e.link ? (e.up ? 'Answered' : 'No answer') : null]]);
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
      labels: $('labels'),
      onStatus: onModelStatus,
      onWalk: setWalking,
      onPick(hit) {
        tip.hidden = true;
        if (hit.company) { location.hash = '#/company'; return; }
        if (hit.href === '#/poe') { location.hash = '#/poe'; return; }
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

async function boot() {
  try {
    const [map, now] = await Promise.all(['sample/company.json', 'sample/work.json'].map(async (path) => {
      const reply = await fetch(path, { cache: 'no-store' });
      if (!reply.ok) throw new Error(path);
      return reply.json();
    }));
    org = map;
    work = now;
  } catch {
    $('content').replaceChildren(h('p.banner.fail', 'The sample company could not be read. Serve this folder (python3 serve.py) and open the address it prints.'));
    return;
  }
  document.title = `Arnheim: ${org.company}, a made-up company`;
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
