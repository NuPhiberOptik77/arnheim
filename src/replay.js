// Replay the day: the building as it was at any moment today, from the day's history (connect/claude_code.py
// keeps it in data/feeds/history/, a file a day; the made-up sample has sample/history.json). Plain module,
// so tests/test_replay.py can run it under Node.
//
// A moment: { at (seconds), key, project, title, kind: working | changed | asked | finished | stopped | left, what }.

const sorted = (moments) => moments.filter((m) => m && m.key && Number.isFinite(m.at)).sort((a, b) => a.at - b.at);

// The conversations as they stood at time t: someone at work, waiting on you, or finished.
export function conversationsAt(moments, t) {
  const last = new Map();
  for (const m of sorted(moments)) if (m.at <= t) last.set(m.key, m);
  const out = [];
  for (const m of last.values()) {
    if (m.kind === 'left') continue;
    const working = m.kind === 'working' || m.kind === 'changed';
    out.push({
      id: m.key, project: m.project, title: m.title || 'A conversation', at: m.at, working, check: !working,
      says: m.kind === 'asked' ? { needs: m.what } : { now: m.kind === 'changed' ? `Changing ${m.what}.` : m.what },
    });
  }
  return out;
}

// The last few moments up to time t, newest first.
export const momentsBefore = (moments, t, most = 6) => sorted(moments).filter((m) => m.at <= t).slice(-most).reverse();

// The files a conversation changed up to time t, each once, in the order it first changed them.
export function touchedBy(moments, key, t) {
  const files = [];
  for (const m of sorted(moments)) if (m.key === key && m.kind === 'changed' && m.at <= t && !files.includes(m.what)) files.push(m.what);
  return files;
}

// A moment in words.
export function sayMoment(m) {
  const who = m.title || 'A conversation';
  const end = (text) => (/[.?!"]$/.test(text) ? text : `${text}.`);
  if (m.kind === 'working') return end(`${who} started work${m.what ? `. ${m.what}` : ''}`);
  if (m.kind === 'changed') return end(`${who} changed ${m.what}`);
  if (m.kind === 'asked') return end(`${who} asked: ${m.what}`);
  if (m.kind === 'finished') return end(`${who} finished${m.what ? `. ${m.what}` : ''}`);
  if (m.kind === 'stopped') return end(`${who} stopped${m.what ? `. ${m.what}` : ''}`);
  return `${who} ended.`;
}

// The mood each kind of moment shows in.
export const MOMENT_MOOD = { working: 'working', changed: 'working', asked: 'needs', finished: 'check', stopped: 'failed', left: 'quiet' };
