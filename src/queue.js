// Everything waiting on you, from every agent and the work, as one list, most urgent first: permissions an
// agent is asking for now, questions an agent stopped to ask, your own tasks marked as needing you, and agents
// that finished and wait for your next word. The panel lists it with an answer beside each, and the
// receptionist reads it out and can answer the safe ones together ("allow all the reads"). No imports, so
// tests/test_queue.py can run it under Node.

// Tools that only look: reading files and searching. Allowing them all at once changes nothing.
export const READS = new Set(['Read', 'Glob', 'Grep', 'LS', 'NotebookRead']);
const RANK = { permission: 0, question: 1, task: 2, turn: 3 };
const RECENT = 2 * 3600; // seconds: an agent that finished longer ago than this is no longer waiting on you

// What a permission is for, in plain words: "to read notes.md", "to run npm test".
const DOES = { Read: 'to read', NotebookRead: 'to read', Glob: 'to look for', Grep: 'to search for', LS: 'to list',
  Bash: 'to run', Edit: 'to change', MultiEdit: 'to change', Write: 'to write', NotebookEdit: 'to change',
  WebFetch: 'to open', WebSearch: 'to search the web for' };
export function wantsTo(tool, what) {
  // control.py describes a request as "Read: notes.md", or just "Read" when it names nothing
  if (tool && typeof what === 'string') what = what === tool ? '' : what.startsWith(`${tool}: `) ? what.slice(tool.length + 2) : what;
  const does = DOES[tool] || (tool ? `to use ${tool} on` : 'to use a tool on');
  return what ? `${does} ${what}` : (tool ? `to use ${tool}` : 'to use a tool');
}

const seconds = (at) => {
  const n = Number(at) || 0;
  return n > 1e12 ? n / 1000 : n; // a time in milliseconds or in seconds
};

// asks and runs: the permissions waiting and the agents started from the page (control state), conversations
// and tasks: as the page reads them (feeds included). A run names an agent whose conversation isn't in a feed
// yet. Each item: { kind, id, key?, title, project?, what, at, until?, read?, ask?, task? }.
export function waitingOnYou({ asks = [], runs = [], conversations = [], tasks = [], now = Date.now() / 1000, recent = RECENT } = {}) {
  const items = [];
  const talks = new Map(conversations.filter((c) => c && c.id).map((c) => [c.id, c]));
  const started = new Map(runs.filter((r) => r && r.key).map((r) => [r.key, r]));
  const asking = new Set();
  for (const a of asks) {
    if (!a || !a.id) continue;
    const c = talks.get(a.key) || started.get(a.key);
    asking.add(a.key);
    items.push({ kind: 'permission', id: `ask:${a.id}`, key: a.key, title: c?.title || 'An agent', project: c?.project,
      what: wantsTo(a.tool, a.what), tool: a.tool, read: READS.has(a.tool), at: seconds(a.at), until: seconds(a.until), ask: a });
  }
  for (const c of talks.values()) {
    if (asking.has(c.id) || c.working) continue;
    if (c.says?.needs) {
      items.push({ kind: 'question', id: `talk:${c.id}`, key: c.id, title: c.title, project: c.project, what: c.says.needs, at: seconds(c.at) });
    } else if (c.check && now - seconds(c.stopped || c.at) < recent) {
      items.push({ kind: 'turn', id: `turn:${c.id}`, key: c.id, title: c.title, project: c.project, what: c.says?.now || 'It has finished for now.', at: seconds(c.stopped || c.at) });
    }
  }
  for (const t of tasks) {
    // a conversation's own "needs you" task is its question, listed above
    if (!t || t.status !== 'needs_you' || (t.session && talks.has(t.session))) continue;
    items.push({ kind: 'task', id: `task:${t.id}`, title: t.title, project: t.project, what: t.note || '', at: seconds(t.at), task: t });
  }
  return items.sort((a, b) => RANK[a.kind] - RANK[b.kind]
    || (a.kind === 'permission' ? a.until - b.until : 0) // the one whose wait runs out first
    || (a.kind === 'turn' ? b.at - a.at : a.at - b.at)); // the newest finished; otherwise the longest waiting
}

// The answers that can be given to several at once: every waiting read. Null when there are fewer than two.
export function together(items) {
  const reads = items.filter((i) => i.kind === 'permission' && i.read);
  return reads.length >= 2 ? { label: `Allow all ${reads.length} reads`, ids: reads.map((i) => i.ask.id) } : null;
}

// The list in words, for the receptionist: how many, and the first few, most urgent first.
export function sayWaiting(items, label = (p) => p, most = 4) {
  if (!items.length) return 'Nothing is waiting on you right now.';
  const kinds = {
    permission: (i) => `${i.title}${i.project ? ` on ${label(i.project)}` : ''} wants your permission ${i.what}`,
    question: (i) => `${i.title}${i.project ? ` on ${label(i.project)}` : ''} is asking: ${i.what}`,
    task: (i) => `your task "${i.title}"${i.project ? ` on ${label(i.project)}` : ''}`,
    turn: (i) => `${i.title}${i.project ? ` on ${label(i.project)}` : ''} has finished and waits for your next step`,
  };
  const lines = items.slice(0, most).map((i) => kinds[i.kind](i));
  const more = items.length > most ? ` And ${items.length - most} more in the panel.` : '';
  const n = items.length === 1 ? 'One thing is' : `${items.length} things are`;
  const reads = together(items);
  return `${n} waiting on you. ${lines.map((l) => `${l[0].toUpperCase()}${l.slice(1)}${/[.?!]$/.test(l) ? '' : '.'}`).join(' ')}${more}${reads ? ` Say "allow all the reads" to let the ${reads.ids.length} that only read go ahead.` : ''}`;
}

// What you said to the receptionist, if it was to allow every waiting read: the ids to allow. Null otherwise.
const ALL_READS = /^(?:please\s+)?(?:allow|approve)\s+(?:all|every)(?:\s+of)?\s+(?:the\s+)?(?:reads?|reading|read requests?)(?:\s+please)?[.!]?$/i;
export function allowReadsAsked(text, items) {
  if (!ALL_READS.test(String(text || '').trim())) return null;
  return items.filter((i) => i.kind === 'permission' && i.read).map((i) => i.ask.id);
}
