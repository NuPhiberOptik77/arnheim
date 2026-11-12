// The brief: what happened since you were last here, and what waits on you now. The receptionist greets you
// with it on a walk and says it when asked, and the Overview shows it. connect/ping.py sends the same kind of
// bundle to your phone. It comes from what the building already keeps: the day's moments (replay.js), each
// conversation's proof and review, the routines' last runs, and the one list of what waits on you (queue.js).
// Plain modules only, so tests/test_brief_words.py can run it under Node.

import { proofOf } from './proof.js';
import { reviewOf } from './review.js';
import { routineNow, whenSaid } from './routines.js';

const HOUR = 3600;
export const BRIEF_MOST = 24 * HOUR; // never further back than a day
export const BRIEF_FIRST = 12 * HOUR; // with no last visit known
const NAMED = 3; // finished conversations named one by one; the rest are counted

// Where the brief starts: your last visit (seconds), but no more than a day back.
export function sinceOf(seen, now = Date.now() / 1000) {
  const s = Number(seen) || 0;
  return s > 0 && s < now ? Math.max(s, now - BRIEF_MOST) : now - BRIEF_FIRST;
}

// What happened between `since` and `now`: { since, worked, finished: [{ key, title, project, proof }],
// stopped: [{ key, title, project }], ran, clear, needs: [{ id, label, project }], waiting: { permission,
// question, task }, quiet }. `waiting` is queue.js's list as it stands now.
export function briefOf({ moments = [], conversations = [], routines = [], waiting = [], since, now = Date.now() / 1000 } = {}) {
  const inside = moments.filter((m) => m && m.key && Number(m.at) > since && Number(m.at) <= now).sort((a, b) => a.at - b.at);
  const talks = new Map(conversations.filter((c) => c && c.id).map((c) => [c.id, c]));
  const last = new Map();
  for (const m of inside) if (m.kind !== 'left') last.set(m.key, m); // where each conversation got to
  const finished = [];
  const stopped = [];
  for (const m of last.values()) {
    const c = talks.get(m.key);
    const one = { key: m.key, title: c?.title || m.title || 'A conversation', project: c?.project || m.project };
    if (m.kind === 'stopped') stopped.push(one);
    if (m.kind !== 'finished') continue;
    const rv = c ? reviewOf(c, now) : null;
    const pr = c ? proofOf(c, now) : null;
    finished.push({ ...one, proof: rv?.state === 'failed' ? 'failed the review line' : pr?.state === 'proven' ? 'proven' : pr?.state === 'failed' ? 'not proven' : null });
  }
  const ran = routines.filter((r) => r && r.last && Number(r.last.at) > since && Number(r.last.at) <= now);
  const needs = routines.filter((r) => r && r.last && routineNow(r, now).state === 'needs').map((r) => ({ id: r.id, label: r.label, project: r.project }));
  const count = (kind) => waiting.filter((i) => i && i.kind === kind).length;
  const out = {
    since, worked: last.size, finished, stopped, ran: ran.length, clear: ran.filter((r) => r.last.state === 'all clear').length, needs,
    waiting: { permission: count('permission'), question: count('question'), task: count('task') },
  };
  out.quiet = !out.worked && !out.ran && !needs.length && !out.waiting.permission && !out.waiting.question && !out.waiting.task;
  return out;
}

// "Since yesterday at 18:00", "Since 04:30", "Since Monday at 09:00".
export function sinceSaid(since, now = Date.now() / 1000) {
  return `Since ${whenSaid(since, now).replace(/^today at /, '').replace(/^last /, '')}`;
}

const n = (k, one, many) => (k === 1 ? `1 ${one}` : `${k} ${many}`);
const list = (parts) => (parts.length < 2 ? parts.join('') : `${parts.slice(0, -1).join(', ')} and ${parts[parts.length - 1]}`);

// The brief in words, for the receptionist and the Overview.
export function sayBrief(b, label = (p) => p, now = Date.now() / 1000) {
  const from = sinceSaid(b.since, now);
  const on = (x) => `"${x.title}"${x.project ? ` on ${label(x.project)}` : ''}`;
  const out = [];
  if (!b.worked && !b.ran) out.push(`${from}, all was quiet.`);
  if (b.worked) {
    out.push(`${from}, ${n(b.worked, 'agent was', 'agents were')} at work.`);
    if (b.finished.length) {
      const named = b.finished.slice(0, NAMED).map((f) => `${on(f)}${f.proof ? `, ${f.proof}` : ''}`);
      const more = b.finished.length - named.length;
      out.push(`${b.finished.length === 1 ? 'One' : b.finished.length} finished: ${named.join('; ')}${more ? `; and ${more} more` : ''}.`);
    }
    if (b.stopped.length) out.push(`${b.stopped.length === 1 ? 'One was' : `${b.stopped.length} were`} stopped: ${b.stopped.slice(0, NAMED).map(on).join('; ')}.`);
  }
  if (b.ran) {
    const clear = b.clear === b.ran ? (b.ran === 1 ? ', all clear' : ', all of them all clear') : b.clear ? `, ${b.clear} all clear` : '';
    out.push(`${n(b.ran, 'routine', 'routines')} ran${clear}.`);
  }
  if (b.needs.length) out.push(`${b.needs.length === 1 ? 'A routine needs' : `${b.needs.length} routines need`} you: ${list(b.needs.slice(0, NAMED).map((r) => on({ title: r.label, project: r.project })))}.`);
  const w = b.waiting;
  const waits = [w.permission && n(w.permission, 'permission request', 'permission requests'), w.question && n(w.question, 'question', 'questions'),
    w.task && n(w.task, 'of your tasks', 'of your tasks')].filter(Boolean);
  out.push(waits.length ? `Waiting on you now: ${list(waits)}. Ask me "what's waiting on me?" to hear them.` : 'Nothing is waiting on you.');
  return out.join(' ');
}

export const BRIEF_ASKED = /\b(?:brief me|(?:morning|daily|the|my) brief(?:ing)?|what did i miss|what have i missed|catch me up|what happened (?:overnight|last night|while i was (?:away|out|gone)|since (?:yesterday|i left|last night))|(?:anything|what'?s) new since (?:yesterday|last night|i left))\b/i;
