// Routines (connect/routines.py): jobs that run on a schedule and tell you only when something needs you.
// The runner keeps data/feeds/routines.json, whose `routines` list the page reads like any feed's. No
// imports, so tests/test_routines_words.py can run it under Node.
//
// A routine: { id, project, label, when (its schedule in words), kind: command | agent, next?, last?: { state:
// starting | running | all clear | needs you | failed | timeout | error, at, done?, said?, tail?, key? } }.

const DAY = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const MONTH = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const two = (n) => String(n).padStart(2, '0');

// A time near now, in words, on this computer's clock: "today at 09:02", "yesterday at 18:30", "on Monday
// at 09:00", "tomorrow at 07:30", "on 3 Nov".
export function whenSaid(t, now = Date.now() / 1000) {
  const at = new Date(t * 1000);
  const today = new Date(now * 1000);
  const days = Math.round((new Date(at.getFullYear(), at.getMonth(), at.getDate()) - new Date(today.getFullYear(), today.getMonth(), today.getDate())) / 864e5);
  const clock = `${two(at.getHours())}:${two(at.getMinutes())}`;
  if (days === 0) return `today at ${clock}`;
  if (days === -1) return `yesterday at ${clock}`;
  if (days === 1) return `tomorrow at ${clock}`;
  if (Math.abs(days) < 7) return `${days < 0 ? 'last' : 'on'} ${DAY[at.getDay()]} at ${clock}`;
  return `on ${at.getDate()} ${MONTH[at.getMonth()]}`;
}

const end = (text) => (/[.?!]$/.test(text) ? text : `${text}.`);
const lastLine = (tail) => String(tail || '').trim().split('\n').pop() || '';

// What its last run came to: { state: waiting | running | clear | needs, line }.
export function routineNow(r, now = Date.now() / 1000) {
  const last = r?.last && typeof r.last === 'object' ? r.last : null;
  const next = Number(r?.next) ? ` Next ${whenSaid(Number(r.next), now)}.` : '';
  if (!last) return { state: 'waiting', line: `Not run yet.${next ? ` First run${next.slice(5)}` : ''}` };
  const ran = whenSaid(Number(last.done || last.at) || now, now);
  if (last.state === 'starting' || last.state === 'running') return { state: 'running', line: `Running now, since ${whenSaid(Number(last.at) || now, now).replace(/^today at /, '')}.` };
  if (last.state === 'all clear') return { state: 'clear', line: `All clear ${ran}.${next}` };
  if (last.state === 'needs you') return { state: 'needs', line: `${end(`It needs you, ${ran}: ${last.said || 'see its conversation'}`)}${next}` };
  if (last.state === 'timeout') return { state: 'needs', line: `It ran too long ${ran} and was stopped.${next}` };
  if (last.state === 'error') return { state: 'needs', line: `${end(`It couldn't run ${ran}: ${last.said || lastLine(last.tail) || 'see the log'}`)}${next}` };
  return { state: 'needs', line: `${end(`It failed ${ran}${lastLine(last.tail) ? `: ${lastLine(last.tail)}` : ''}`)}${next}` };
}

// The routines in words, for the receptionist.
export function sayRoutines(rows, label = (p) => p, now = Date.now() / 1000) {
  if (!rows.length) return 'There are no routines yet. A floor can list them in company.json, to run a command or start an agent on a schedule.';
  const needs = rows.filter((r) => routineNow(r, now).state === 'needs');
  const each = rows.slice(0, 5).map((r) => `${r.label} on ${label(r.project)}, ${r.when ? r.when[0].toLowerCase() + r.when.slice(1) : 'on a schedule'}. ${routineNow(r, now).line}`);
  const head = rows.length === 1 ? 'There is one routine.' : `There are ${rows.length} routines${needs.length ? `, and ${needs.length === 1 ? 'one needs' : `${needs.length} need`} you` : ', and none needs you'}.`;
  return `${head} ${each.join(' ')}${rows.length > 5 ? ` And ${rows.length - 5} more in the panel.` : ''}`;
}

// A routine's last and next times from its schedule ({ every, on?, at? }, as company.json gives it), on this
// computer's clock, as connect/routines.py works them out. The runner writes `next` itself; the sample uses this.
const WEEK = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'];
export function timesOf(r, now = Date.now() / 1000) {
  const m = /^(\d{1,2}):(\d{2})$/.exec(String(r?.at || '09:00'));
  const every = String(r?.every || '').toLowerCase();
  const on = String(r?.on || 'monday').toLowerCase();
  if (!m || !every) return { last: null, next: null };
  const [hour, minute] = [Number(m[1]), Number(m[2])];
  const fits = (d) => every === 'day' || (every === 'weekday' && d.getDay() >= 1 && d.getDay() <= 5) || WEEK[d.getDay()] === (every === 'week' ? on : every);
  const base = new Date(now * 1000);
  const list = [];
  for (let k = -8; k <= 8; k++) {
    const d = new Date(base);
    if (every === 'hour') {
      if (Math.abs(k) > 2) continue;
      d.setHours(base.getHours() + k, minute, 0, 0);
    } else {
      d.setDate(base.getDate() + k);
      d.setHours(hour, minute, 0, 0);
      if (!fits(d)) continue;
    }
    list.push(d.getTime() / 1000);
  }
  const past = list.filter((t) => t <= now);
  const ahead = list.filter((t) => t > now);
  return { last: past.length ? Math.max(...past) : null, next: ahead.length ? Math.min(...ahead) : null };
}

export const ROUTINES_ASKED = /\b(?:routines?|scheduled (?:jobs?|work)|what runs on (?:a )?schedule)\b/i;
