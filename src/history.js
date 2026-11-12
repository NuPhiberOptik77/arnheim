// Ask the building about its history: what happened on a day this week, on one floor, or to one file, from
// the week's moments (connect/claude_code.py keeps a file a day for a week in data/feeds/history/; the
// made-up sample has sample/history.json and sample/week.json). The receptionist answers from these rules.
// Plain module, so tests/test_history.py can run it under Node.

import { localDay } from './budget.js';

const DAYS = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'];
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);

// "What happened yesterday?", "what did the agents do on Tuesday?", "who changed walk.js?", "history".
export const HISTORY_ASKED = /\b(?:what (?:happened|went on|got done|was done)|what did (?:the |my |our |your )?(?:agents?|conversations?|they|we|everyone|anyone|claude|people) (?:do|change|work on|get done|get up to)|who (?:changed|touched|worked on|edited)|when (?:did|was) .{1,80}? (?:last )?(?:changed?|edited|touched|finish(?:ed)?|work(?:ed)? on)|(?:the |its |building's )history|what changed)\b/i;

const back = (now, n) => localDay(new Date(now.getTime() - n * 864e5));

// What a question asks about: { days (newest first), label, file, project }. A day named ("yesterday", "on
// Tuesday", "this week") picks the days; with none, today, or the whole week for a file.
export function historyAsked(text, now = new Date(), project = null) {
  const q = String(text || '').toLowerCase();
  const file = fileAsked(text);
  const week = { days: [0, 1, 2, 3, 4, 5, 6].map((n) => back(now, n)), label: 'this week' };
  let when = null;
  if (/\b(?:this|last|past|the) (?:week|seven days|7 days)\b/.test(q)) when = week;
  else if (/\byesterday\b|\blast night\b/.test(q)) when = { days: [back(now, 1)], label: 'yesterday' };
  else if (/\btoday\b|\bthis (?:morning|afternoon|evening)\b/.test(q)) when = { days: [back(now, 0)], label: 'today' };
  else {
    const d = DAYS.findIndex((name) => new RegExp(`\\b${name}\\b`).test(q));
    if (d >= 0) {
      const n = (now.getDay() - d + 7) % 7;
      when = n === 0 ? { days: [back(now, 0)], label: 'today' } : { days: [back(now, n)], label: `on ${cap(DAYS[d])}` };
    }
  }
  return { ...(when || (file ? week : { days: [back(now, 0)], label: 'today' })), file, project: project || null };
}

// A file named in the question: "who changed src/walk.js?", "when was notes.md last changed?"
// A name with spaces in it goes in quotes: who changed "My File.txt"?
export function fileAsked(text) {
  const said = String(text || '');
  const quoted = /["'“‘`]([^"'”’`]*[^\s"'”’`/]\.\p{L}[\p{L}\p{N}]{0,7})["'”’`]/u.exec(said);
  if (quoted) return quoted[1];
  const m = /(?:^|[\s(])((?:[\p{L}\p{N}_.-]+\/)*[\p{L}\p{N}_-]+\.\p{L}[\p{L}\p{N}]{0,7})(?=$|[\s?),!:;]|\.(?:\s|$))/u.exec(said);
  return m ? m[1] : null;
}

const valid = (m) => m && m.key && Number.isFinite(m.at);
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

// When something was, from now: "at 16:20" today, "yesterday at 16:20", "on Tuesday at 16:20".
export function whenWas(at, clock, now = new Date()) {
  const day = localDay(new Date(at * 1000));
  const said = day === back(now, 0) ? '' : day === back(now, 1) ? 'yesterday ' : `on ${cap(DAYS[new Date(at * 1000).getDay()])} `;
  return `${said}at ${clock(at)}`;
}

// What one conversation did in the moments given, in a phrase: "changed 6 files and finished at 16:20".
function didWhat(list, clock, now, oneDay) {
  const files = new Set(list.filter((m) => m.kind === 'changed').map((m) => m.what));
  const last = list[list.length - 1];
  const parts = [];
  if (files.size) parts.push(`changed ${plural(files.size, 'file', 'files')}`);
  const end = { finished: 'finished', stopped: 'stopped', left: 'ended', asked: 'stopped to ask you something' }[last.kind];
  const when = oneDay ? `at ${clock(last.at)}` : whenWas(last.at, clock, now); // a day named already: just the time
  parts.push(end ? `${end} ${when}` : `was at work ${when}`);
  return parts.join(' and ');
}

// The receptionist's answer. moments: the week's, as many days as the page has; ask: from historyAsked.
export function sayHistory(moments, ask, label = (p) => p, clock = (t) => String(t), now = new Date(), most = 3) {
  const days = new Set(ask.days);
  const where = ask.project ? ` on ${label(ask.project)}` : '';
  const list = (Array.isArray(moments) ? moments : []).filter(valid).filter((m) => days.has(localDay(new Date(m.at * 1000)))
    && (!ask.project || m.project === ask.project)).sort((a, b) => a.at - b.at);
  if (ask.file) {
    const name = ask.file.toLowerCase();
    const hits = list.filter((m) => m.kind === 'changed' && typeof m.what === 'string'
      && (m.what.toLowerCase() === name || m.what.toLowerCase().endsWith(`/${name}`)));
    if (!hits.length) return `Nothing changed ${ask.file}${where} ${ask.label}, as far as the building knows. It keeps a week of history.`;
    const latest = new Map();
    for (const m of hits) latest.set(m.key, m); // each conversation's last change to it
    const by = [...latest.values()].sort((a, b) => b.at - a.at).slice(0, most)
      .map((m) => `"${m.title || 'A conversation'}"${!ask.project && m.project ? ` on ${label(m.project)}` : ''} ${whenWas(m.at, clock, now)}`);
    const more = latest.size > most ? `, and ${plural(latest.size - most, 'other', 'others')}` : '';
    return `${hits[hits.length - 1].what} was changed ${plural(hits.length, 'time', 'times')} ${ask.label}: last by ${by.join(', before that by ')}${more}.`;
  }
  if (!list.length) return `Nothing happened${where} ${ask.label}, as far as the building knows. It keeps a week of history.`;
  const byProject = new Map();
  for (const m of list) {
    if (!byProject.has(m.project)) byProject.set(m.project, new Map());
    const talks = byProject.get(m.project);
    if (!talks.has(m.key)) talks.set(m.key, []);
    talks.get(m.key).push(m);
  }
  const floors = [...byProject.entries()].sort((a, b) => b[1].size - a[1].size);
  const lines = floors.slice(0, 4).map(([project, talks]) => {
    const latest = [...talks.values()].sort((a, b) => b[b.length - 1].at - a[a.length - 1].at);
    const said = latest.slice(0, most).map((ms) => `"${ms[0].title || 'A conversation'}" ${didWhat(ms, clock, now, ask.days.length === 1)}`);
    const more = latest.length > most ? `, and ${plural(latest.length - most, 'other', 'others')}` : '';
    return `${ask.project ? '' : `On ${label(project)}, `}${plural(talks.size, 'conversation', 'conversations')} worked: ${said.join('; ')}${more}.`;
  });
  const rest = floors.length > 4 ? ` And ${plural(floors.length - 4, 'more floor', 'more floors')}.` : '';
  return `${cap(ask.label)}${where}: ${lines.join(' ')}${rest}`;
}
