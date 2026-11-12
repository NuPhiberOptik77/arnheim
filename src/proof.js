// Done means proven (connect/prove.py): whether a conversation's work stands up, from what came of its
// floor's own check after its last change. No imports, so tests/test_proof.py can run it under Node.
//
// A conversation in a feed may carry `changed` (when it last changed files) and `proof` (the check's last
// run on them: { state: checking | passed | failed | timeout | error, check, at, until?, code?, tail? }).
// The sample's conversations carry a proof with no times.

// "The tests" in the middle of a sentence; "CI" stays as it is.
export const inner = (name) => (/^[A-Z][a-z]/.test(name) ? name[0].toLowerCase() + name.slice(1) : name);

// What to show: { state: proven | failed | checking | claimed, word, line, tail? }, or null for a
// conversation that changed nothing.
export function proofOf(c, now = Date.now() / 1000) {
  const changed = Number(c?.changed) || 0;
  const p = c?.proof && typeof c.proof === 'object' ? c.proof : null;
  if (!changed && !p) return null;
  const name = String(p?.check || 'Its check');
  const at = Number(p?.at) || 0;
  const running = p?.state === 'checking' && now < (Number(p.until) || at + 3600) + 60; // after that, it was cut short
  if (running && at >= changed) return { state: 'checking', word: 'Checking', line: `Running ${inner(name)} on its work now.` };
  if (!p || p.state === 'checking' || at < changed) {
    return {
      state: 'claimed', word: 'Claimed',
      line: running ? `It changed files again while ${inner(name)} ran, so they wait for the next run.`
        : p && p.state !== 'checking' ? `It changed files after ${inner(name)} last ran on them.` : 'It changed files, and nothing has checked them yet.',
    };
  }
  const tail = p.tail ? String(p.tail) : '';
  if (p.state === 'passed') return { state: 'proven', word: 'Proven', line: `${name} passed after its last change.` };
  if (p.state === 'timeout') return { state: 'failed', word: 'Not proven', line: `${name} ran too long and was stopped.`, tail };
  if (p.state === 'error') return { state: 'failed', word: 'Not proven', line: `${name} couldn't run.`, tail };
  return { state: 'failed', word: 'Not proven', line: `${name} failed.`, tail };
}

// The mood a list or the building shows it in: green when proven, red when not.
export const proofMood = (pr) => (pr?.state === 'proven' ? 'ok' : pr?.state === 'failed' ? 'failed' : null);
