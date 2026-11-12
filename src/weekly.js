// A weekly report: the last seven days of the company's agents, floor by floor, from the history the hook
// keeps (data/feeds/history/: a file a day, with its moments and what each floor's agents spent that day).
// The Overview shows it and copies it as text, and the receptionist sums it up. Plain module, so
// tests/test_weekly.py can run it under Node.

import { tokensSaid } from './budget.js';
import { waitFor, waits } from './waiting.js';

// "How was the week?", "weekly report", "the week in review".
export const WEEKLY_ASKED = /\b(?:weekly report|week(?:'s|ly)? (?:report|summary|review)|report (?:on|for) the week|how (?:was|did|is|has|went) (?:the|this|last|our|my) week|(?:the )?week (?:so far|in review)|sum up the week)\b/i;

const valid = (m) => m && m.key && Number.isFinite(m.at);
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
const DAY_NAMES = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const dayName = (day) => DAY_NAMES[new Date(`${day}T12:00:00`).getDay()];

// days: [{ day: 'YYYY-MM-DD', moments, spent: { project: tokens } }], any order. Gives { from, to, floors,
// total, busiest } where each floor (and total) is { project, talks, asked, files, finished, stopped, waited,
// waits, spent }: conversations, instructions you gave, files changed, finished and stopped, time and times
// waited on you, and tokens.
export function weekReport(days, now = Date.now() / 1000) {
  const list = (Array.isArray(days) ? days : []).filter((d) => d && typeof d.day === 'string').sort((a, b) => (a.day < b.day ? -1 : 1));
  const floors = new Map();
  const blank = (project) => ({ project, talks: new Set(), asked: 0, files: new Set(), finished: 0, stopped: 0, waited: 0, waits: 0, spent: 0 });
  const of = (project) => {
    if (!floors.has(project)) floors.set(project, blank(project));
    return floors.get(project);
  };
  const all = list.flatMap((d) => (Array.isArray(d.moments) ? d.moments : []).filter(valid));
  for (const m of all) {
    const f = of(m.project || '');
    f.talks.add(m.key);
    if (m.kind === 'working') f.asked += 1;
    if (m.kind === 'changed') f.files.add(m.what);
    if (m.kind === 'finished') f.finished += 1;
    if (m.kind === 'stopped') f.stopped += 1;
  }
  for (const w of waits(all, now)) {
    const f = of(w.project || '');
    f.waited += w.seconds;
    f.waits += 1;
  }
  for (const d of list) {
    for (const [project, tokens] of Object.entries(d.spent && typeof d.spent === 'object' ? d.spent : {})) {
      if (Number.isFinite(tokens) && tokens > 0) of(project).spent += tokens;
    }
  }
  const rows = [...floors.values()].map((f) => ({ ...f, talks: f.talks.size, files: f.files.size }))
    .sort((a, b) => (b.asked + b.files) - (a.asked + a.files) || b.spent - a.spent);
  const total = rows.reduce((t, f) => {
    for (const k of ['talks', 'asked', 'files', 'finished', 'stopped', 'waited', 'waits', 'spent']) t[k] += f[k];
    return t;
  }, { project: null, talks: 0, asked: 0, files: 0, finished: 0, stopped: 0, waited: 0, waits: 0, spent: 0 });
  let busiest = null;
  for (const d of list) {
    const n = (Array.isArray(d.moments) ? d.moments : []).filter(valid).length;
    if (n && (!busiest || n > busiest.moments)) busiest = { day: d.day, moments: n };
  }
  return { from: list[0]?.day || null, to: list[list.length - 1]?.day || null, floors: rows, total, busiest };
}

// One floor (or the total) in a line: "6 conversations, 18 instructions, 48 files changed, 9 finished,
// 1 stopped. Waited on you 25 min. 1.2 million tokens."
export function floorLine(f) {
  const work = [plural(f.talks, 'conversation', 'conversations'), plural(f.asked, 'instruction', 'instructions'),
    `${plural(f.files, 'file', 'files')} changed`, `${f.finished} finished`, f.stopped ? `${f.stopped} stopped` : null].filter(Boolean).join(', ');
  const waited = f.waits ? ` Waited on you ${waitFor(f.waited)}${f.waits > 1 ? `, ${f.waits} times` : ''}.` : '';
  const spent = f.spent ? ` ${tokensSaid(f.spent)} tokens.` : '';
  return `${work}.${waited}${spent}`;
}

// The receptionist's summing up.
export function sayWeek(report, label = (p) => p) {
  const t = report.total;
  if (!t.talks) return 'Nothing happened this week, as far as the building knows. It keeps a week of history, from the day its hook was switched on.';
  const busiest = report.floors[0];
  const day = report.busiest ? ` The busiest day was ${dayName(report.busiest.day)}.` : '';
  return `This week, ${plural(t.talks, 'conversation', 'conversations')} on ${plural(report.floors.length, 'floor', 'floors')}: `
    + `${plural(t.asked, 'instruction', 'instructions')}, ${plural(t.files, 'file', 'files')} changed, ${t.finished} finished`
    + `${t.stopped ? ` and ${t.stopped} stopped` : ''}.${t.waits ? ` They waited on you ${waitFor(t.waited)} in all.` : ''}`
    + ` The busiest floor was ${label(busiest.project)}.${day}${t.spent ? ` ${tokensSaid(t.spent)} tokens.` : ''}`;
}

// The whole report as plain text, to copy into a message or a document.
export function weekText(report, label = (p) => p, company = '') {
  const head = `${company ? `${company}: ` : ''}the week from ${dayName(report.from || '')} ${report.from || ''} to ${dayName(report.to || '')} ${report.to || ''}`;
  if (!report.total.talks) return `${head}\n\nNothing happened, as far as the building knows.\n`;
  const lines = report.floors.map((f) => `${label(f.project) || 'No floor'}: ${floorLine(f)}`);
  const busiest = report.busiest ? `\nThe busiest day was ${dayName(report.busiest.day)}.` : '';
  return `${head}\n\n${lines.join('\n')}\n\nIn all: ${floorLine(report.total)}${busiest}\n\nFrom Arnheim, the building's own history.\n`;
}
