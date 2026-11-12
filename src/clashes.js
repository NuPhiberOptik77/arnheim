// Collision warnings: two conversations on one floor that changed the same file within two hours, which may
// undo each other's work. The Claude Code hook keeps each conversation's latest files (connect/claude_code.py);
// the made-up sample's have no times. Plain module, so tests/test_clashes.py can run it under Node.

export const CLASH = 2 * 3600; // seconds

const recent = (f, now, within) => f && typeof f.path === 'string' && (f.at == null || now - Number(f.at) < within);

// Each pair once: { project, a, b, files, working }, those with someone at work first.
export function clashesOf(conversations, now = Date.now() / 1000, within = CLASH) {
  const out = [];
  const talks = conversations.filter((c) => c && c.id && Array.isArray(c.files));
  for (let i = 0; i < talks.length; i += 1) {
    for (let j = i + 1; j < talks.length; j += 1) {
      const [a, b] = [talks[i], talks[j]];
      if (a.project !== b.project) continue;
      const theirs = new Set(b.files.filter((f) => recent(f, now, within)).map((f) => f.path));
      const files = [...new Set(a.files.filter((f) => recent(f, now, within) && theirs.has(f.path)).map((f) => f.path))];
      if (files.length) out.push({ project: a.project, a, b, files, working: !!(a.working || b.working) });
    }
  }
  return out.sort((x, y) => Number(y.working) - Number(x.working));
}

// A clash in words.
export function sayClash(c) {
  const files = c.files.length > 2 ? `${c.files.slice(0, 2).join(', ')} and ${c.files.length - 2} more` : c.files.join(' and ');
  return `"${c.a.title}" and "${c.b.title}" both changed ${files}.`;
}

// What one of them is told, to wait for the other.
export const waitWords = (c, waiting) => {
  const other = waiting === c.a ? c.b : c.a;
  return `Another agent, on "${other.title}", is changing the same files as you (${c.files.join(', ')}). Wait until it has finished before you change them again, then look at what it changed.`;
};
