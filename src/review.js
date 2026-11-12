// The review line (connect/review.py): on a floor that asks for one, an agent's changes are checked before
// they reach you, and sent back with the reason when they aren't ready. No imports, so
// tests/test_review_words.py can run it under Node.
//
// A conversation in a feed may carry `review`: { state: reviewing | passed | sent back | failed | error, by,
// said?, why?, times?, most?, at?, until? }.

const first = (text) => String(text || '').split('\n')[0].trim();
const end = (text) => (/[.?!]$/.test(text) ? text : `${text}.`);
const timesSaid = (n) => (n === 1 ? 'once' : n === 2 ? 'twice' : `${n} times`);
const NTH = { 2: 'second', 3: 'third', 4: 'fourth', 5: 'fifth' };

// What to show: { state, word, line }, or null when its floor has no review line (or it changed nothing).
export function reviewOf(c, now = Date.now() / 1000) {
  const r = c?.review && typeof c.review === 'object' ? c.review : null;
  if (!r) return null;
  const by = String(r.by || 'The review line');
  const times = Number(r.times) || 0;
  if (r.state === 'reviewing') {
    const until = Number(r.until) || 0;
    if (until && now > until + 60) return { state: 'error', word: 'Not reviewed', line: 'The review line was cut short, so this work reached you unchecked.' };
    return { state: 'reviewing', word: 'In review', line: 'The review line is checking its work before it reaches you.' };
  }
  if (r.state === 'passed') {
    const after = times ? `, after it was sent back ${timesSaid(times)}` : '';
    const said = r.said ? ` ${end(String(r.said))}` : by !== 'The reader' && by !== 'The review line' ? ` ${by} passed.` : '';
    return { state: 'passed', word: 'Passed review', line: `It passed the review line${after}.${said}` };
  }
  if (r.state === 'sent back') {
    return { state: 'sent back', word: 'Sent back', line: end(`The review line sent it back${NTH[times] ? ` a ${NTH[times]} time` : ''}, so it is fixing it: ${first(r.why) || 'it wasn\'t ready'}`) };
  }
  if (r.state === 'failed') {
    return { state: 'failed', word: 'Failed review', line: end(`It ${times ? `still failed the review line after being sent back ${timesSaid(times)}` : 'failed the review line'}, so it reached you anyway: ${first(r.why) || 'it wasn\'t ready'}`) };
  }
  if (r.state === 'error') return { state: 'error', word: 'Not reviewed', line: end(`The review line couldn't finish, so this work reached you unchecked. ${first(r.said)}`.trim()) };
  return null;
}

// The mood a list or the building shows it in.
export const reviewMood = (rv) => (rv?.state === 'passed' ? 'ok' : rv?.state === 'failed' ? 'failed' : null);
