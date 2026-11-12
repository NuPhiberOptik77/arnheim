// How long things wait on you: each time an agent stopped to ask (a permission or a question) until it went
// on, from the day's moments (connect/claude_code.py), and how long each thing waiting now has waited. The
// Overview's meter fills as the longest wait now grows: amber past five minutes, red and full past fifteen.
// Plain module, so tests/test_waiting.py can run it under Node.
//
// A moment: { at (seconds), key, project, title, kind, what }. "asked" starts a wait; the agent's next moment
// of any other kind (it went on, finished, stopped or ended) ends it.

export const SLOW = 5 * 60; // seconds: past this, a wait shows amber
export const LONG = 15 * 60; // and past this, red, and the meter is full
const GOES_ON = new Set(['working', 'changed', 'answered', 'finished', 'stopped', 'left']);
const BLOCKED = new Set(['permission', 'question']); // what holds an agent up, of what waits on you (queue.js)

// "How long have they waited on me?", "waiting time today".
export const WAITED_ASKED = /\b(?:how long (?:have|has|did|was|were|had|do|does)\b.*\bwait\w*|wait(?:ed|ing) (?:on|for) (?:me|you) (?:today|this week|so long|for how long|in all)|waiting time|time (?:spent )?waiting)\b/i;

const valid = (m) => m && m.key && Number.isFinite(m.at);

// Every wait in the moments, oldest first: { key, title, project, what, from, to (null while open), seconds }.
// stillWaiting, a Set of conversation keys, keeps only the open waits of those that wait now: one whose agent
// went quiet without a word since can't be timed, so it is left out.
export function waits(moments, now = Date.now() / 1000, stillWaiting = null) {
  const open = new Map();
  const out = [];
  for (const m of (Array.isArray(moments) ? moments : []).filter(valid).sort((a, b) => a.at - b.at)) {
    if (m.kind === 'asked') {
      if (!open.has(m.key)) open.set(m.key, { key: m.key, title: m.title || 'A conversation', project: m.project, what: m.what, from: m.at, to: null });
    } else if (GOES_ON.has(m.kind) && open.has(m.key)) {
      const w = open.get(m.key);
      open.delete(m.key);
      out.push({ ...w, to: m.at, seconds: Math.max(0, m.at - w.from) });
    }
  }
  for (const w of open.values()) if (!stillWaiting || stillWaiting.has(w.key)) out.push({ ...w, seconds: Math.max(0, now - w.from) });
  return out.sort((a, b) => a.from - b.from);
}

// The waits added up: { total, count, longest (a wait, or null) }.
export function waitedSum(list) {
  let total = 0;
  let longest = null;
  for (const w of list) {
    total += w.seconds;
    if (!longest || w.seconds > longest.seconds) longest = w;
  }
  return { total, count: list.length, longest };
}

// A length of time in words: "under a minute", "6 min", "1 h 5 min".
export function waitFor(seconds) {
  const m = Math.floor((Number(seconds) || 0) / 60);
  if (m < 1) return 'under a minute';
  if (m < 60) return `${m} min`;
  const hours = Math.floor(m / 60);
  return m % 60 ? `${hours} h ${m % 60} min` : `${hours} h`;
}

// The mood a wait shows in: amber past SLOW, red past LONG.
export const waitMood = (seconds) => (seconds >= LONG ? 'failed' : seconds >= SLOW ? 'needs' : 'working');

// The meter, from what waits on you now (queue.js's items): the longest an agent has been held up, how full
// the meter is (full at LONG) and its mood. Null when no agent is held up.
export function meter(items, now = Date.now() / 1000) {
  let item = null;
  for (const i of Array.isArray(items) ? items : []) {
    if (BLOCKED.has(i?.kind) && Number.isFinite(i.at) && i.at > 0 && (!item || i.at < item.at)) item = i;
  }
  if (!item) return null;
  const seconds = Math.max(0, now - item.at);
  return { item, seconds, share: Math.min(1, seconds / LONG), mood: waitMood(seconds) };
}

// How long one thing has waited, for its line in the list: "Waiting 6 min", or null for one that doesn't hold
// an agent up.
export const waitingLine = (i, now = Date.now() / 1000) => (BLOCKED.has(i?.kind) && Number.isFinite(i.at) && i.at > 0 ? `Waiting ${waitFor(now - i.at)}` : null);

// The receptionist's answer: today's waits, and what waits now.
export function sayWaited(list, items, label = (p) => p, now = Date.now() / 1000) {
  const sum = waitedSum(list);
  const m = meter(items, now);
  const today = !sum.count ? 'No agent has waited on you today.'
    : `Agents waited on you ${waitFor(sum.total)} today, ${sum.count === 1 ? 'once' : `${sum.count} times`}. The longest was ${waitFor(sum.longest.seconds)}: "${sum.longest.title}"${sum.longest.project ? ` on ${label(sum.longest.project)}` : ''}.`;
  const held = (Array.isArray(items) ? items : []).filter((i) => BLOCKED.has(i?.kind)).length;
  const nowWords = m ? ` ${held === 1 ? 'One is waiting now' : `${held} are waiting now`}, the longest for ${waitFor(m.seconds)}.` : '';
  return today + nowWords;
}
