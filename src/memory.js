// The company's memory: the decisions every agent is told as it starts (data/memory.json, written through
// connect/control.py; docs/connect.md, "Company memory"). What you say to the receptionist to add one, what
// they say back, and which decisions answer a question an agent is asking. Plain module, so
// tests/test_memory_words.py can run it under Node.

// "Remember that we never push on a Friday", "remember: ...", "from now on, ...": the decision, as it is kept.
const REMEMBER = /^(?:please\s+)?(?:remember|note|keep in mind)(?:\s+that|\s*:|\s*,)?\s+(.+)$/i;
const FROM_NOW = /^(?:from now on|from today|going forward|in future|in the future)\b[,:]?\s+(.+)$/i;
const NOT_A_DECISION = /^(?:me\b|to\b|when\b|what\b|who\b|where\b|how\b|why\b|which\b|if\b|this\b|that\??$|it\??$)/i;

const tidy = (text) => {
  const t = String(text).trim().replace(/\s+/g, ' ').replace(/[\s.!]+$/, '');
  return t ? `${t[0].toUpperCase()}${t.slice(1)}.` : '';
};

export function rememberAsked(text) {
  const said = String(text || '').trim();
  const m = REMEMBER.exec(said);
  if (m && !NOT_A_DECISION.test(m[1].trim())) return tidy(m[1].replace(/^that\s+/i, ''));
  const f = FROM_NOW.exec(said);
  if (f && f[1].trim().length > 3) return tidy(said);
  return null;
}

// "What have we decided?", "what do the agents know?", "company memory".
export const MEMORY_ASKED = /\b(?:what (?:have|did) (?:we|i) decide[ds]?|what (?:do|does) (?:the |our |my )?agents? (?:know|get told)|(?:company|our|the) memory|what (?:is|'s) remembered|what do you remember|decisions so far)\b/i;

export function sayMemory(rows, most = 5) {
  if (!rows.length) return 'Nothing is remembered yet. Say "remember that ..." and every agent will be told it as it starts.';
  const n = rows.length === 1 ? 'One thing' : `${rows.length} things`;
  const list = rows.slice(-most).map((r) => r.text).join(' ');
  return `${n} every agent is told as it starts${rows.length > most ? `, the latest ${most}` : ''}: ${list}`;
}

// Which decisions answer what an agent is asking: those that share at least two words that carry meaning
// with it, most shared first. A plain word match, so it only suggests: you choose whether to send it.
const SKIP = new Set(['the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'any', 'can', 'had', 'her', 'was', 'one', 'our', 'out',
  'has', 'have', 'his', 'how', 'its', 'may', 'new', 'now', 'old', 'see', 'two', 'way', 'who', 'did', 'get', 'got', 'let', 'say',
  'she', 'too', 'use', 'that', 'this', 'with', 'from', 'they', 'them', 'then', 'than', 'there', 'their', 'what', 'when', 'where',
  'which', 'while', 'will', 'would', 'should', 'could', 'shall', 'into', 'onto', 'about', 'your', 'yours', 'just', 'like', 'want',
  'need', 'needs', 'does', 'done', 'doing', 'make', 'made', 'some', 'every', 'each', 'also', 'only', 'very', 'more', 'most', 'been',
  'being', 'were', 'here', 'okay', 'yes', 'please', 'never', 'always', 'before', 'after', 'again', 'first', 'next', 'last', 'one',
  'it’s', "it's", 'i’m', "i'm", 'do', 'is', 'to', 'of', 'in', 'on', 'at', 'or', 'an', 'a', 'we', 'i', 'me', 'my', 'be', 'so', 'if']);
const stem = (w) => w.replace(/(?:ing|ed|es|s)$/, '') || w;
const words = (text) => new Set(String(text || '').toLowerCase().match(/[a-z][a-z’'-]+/g)?.filter((w) => w.length > 2 && !SKIP.has(w)).map(stem) || []);

export function decidedFor(question, rows, most = 2) {
  const asked = words(question);
  if (!asked.size) return [];
  return rows.map((r) => ({ r, n: [...words(r.text)].filter((w) => asked.has(w)).length }))
    .filter((x) => x.n >= 2)
    .sort((a, b) => b.n - a.n)
    .slice(0, most)
    .map((x) => x.r);
}
