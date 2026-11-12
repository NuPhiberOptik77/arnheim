// A shelf of how-tos: the company's own ways of doing things, each a short Markdown file beside company.json
// (its "howtos": [{ id, title, file, project? }]). They stand on the Library's shelf, each floor lists its
// own, the receptionist points to the one that fits a question, and each agent is told its floor's as it
// starts (connect/claude_code.py). Plain module, so tests/test_howto.py can run it under Node.

const ID = /^[a-z0-9][a-z0-9-]{0,60}$/;
const FILE = /^(?:[\w-]+\/)*[\w-]+\.md$/; // inside the company's folder, a Markdown file: no "..", no absolute paths

// The how-tos company.json lists, the ones it gives properly, for one floor (with those for every floor) or all.
export function howtosOf(org, project = null) {
  const list = Array.isArray(org?.howtos) ? org.howtos : [];
  return list.filter((x) => x && ID.test(String(x.id || '')) && typeof x.title === 'string' && x.title.trim() && FILE.test(String(x.file || ''))
    && (project == null || !x.project || x.project === project));
}

// "How do I ship Lantern?", "is there a how-to for the sensors?", "what how-tos are there?"
export const HOWTO_ASKED = /\b(?:how (?:do|can|should|would) (?:i|we|you|one|they)|how to|how-tos?|howtos?|is there a (?:guide|how-to|howto|way)|what(?:'s| is) the (?:way|process|steps) (?:to|for))\b/i;
const LIST_ASKED = /\b(?:what|which|any|list|show)\b.*\b(?:how-tos|howtos|guides)\b|\bthe shelf\b/i;
const SMALL = new Set(['a', 'an', 'the', 'to', 'of', 'for', 'and', 'or', 'in', 'on', 'at', 'with', 'how', 'do', 'i', 'we', 'you', 'can', 'should',
  'is', 'there', 'what', 'whats', 'it', 'my', 'our', 'new', 'make', 'get', 'one', 'this', 'that', 'way', 'guide', 'howto', 'howtos', 'steps']);
const words = (text) => String(text || '').toLowerCase().replace(/[^a-z0-9\s-]/g, ' ').split(/[\s-]+/)
  .map((w) => w.replace(/(?:ing|es|s)$/, '')).filter((w) => w.length > 1 && !SMALL.has(w));

// The how-to that best fits a question, or null: the one sharing the most words with it, at least one, and
// two when its title has three or more.
export function howtoFor(text, list) {
  if (!HOWTO_ASKED.test(String(text || ''))) return null;
  const asked = new Set(words(text));
  let best = null;
  for (const x of list) {
    const title = [...new Set(words(x.title))];
    const shared = title.filter((w) => asked.has(w)).length;
    const enough = shared >= (title.length >= 3 ? 2 : 1);
    if (enough && (!best || shared > best.shared)) best = { howto: x, shared };
  }
  return best ? best.howto : null;
}

// Whether a question asks what the shelf holds.
export const shelfAsked = (text) => LIST_ASKED.test(String(text || ''));

// The receptionist's words for the shelf as a whole.
export function sayShelf(list, label = (p) => p) {
  if (!list.length) return 'The shelf holds no how-tos yet. Add them to company.json\'s "howtos", each a short Markdown file (docs/data.md, "How-tos").';
  const named = list.slice(0, 5).map((x) => `"${x.title}"${x.project ? ` for ${label(x.project)}` : ''}`);
  const more = list.length > 5 ? `, and ${list.length - 5} more` : '';
  return `The shelf in the Library holds ${list.length === 1 ? 'one how-to' : `${list.length} how-tos`}: ${named.join(', ')}${more}. Every agent is told its floor's as it starts.`;
}

// A how-to's Markdown, as blocks to draw with text only (never as HTML): headings, paragraphs, lists and code.
// { kind: 'h', level, text } | { kind: 'p', text } | { kind: 'ul' | 'ol', items } | { kind: 'code', text }
export function blocks(markdown) {
  const out = [];
  const lines = String(markdown || '').replace(/\r\n?/g, '\n').split('\n');
  let para = [];
  let list = null;
  const endPara = () => { if (para.length) out.push({ kind: 'p', text: para.join(' ') }); para = []; };
  const endList = () => { if (list) out.push(list); list = null; };
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    if (/^\s*```/.test(line)) {
      endPara(); endList();
      const code = [];
      for (i += 1; i < lines.length && !/^\s*```/.test(lines[i]); i += 1) code.push(lines[i]);
      out.push({ kind: 'code', text: code.join('\n') });
      continue;
    }
    const head = /^(#{1,6})\s+(.*)$/.exec(line);
    const item = /^\s*(?:([-*+])|(\d+)[.)])\s+(.*)$/.exec(line);
    if (head) {
      endPara(); endList();
      out.push({ kind: 'h', level: head[1].length, text: head[2].replace(/\s*#+\s*$/, '').trim() });
    } else if (item) {
      endPara();
      const kind = item[1] ? 'ul' : 'ol';
      if (!list || list.kind !== kind) { endList(); list = { kind, items: [] }; }
      list.items.push(item[3].trim());
    } else if (!line.trim()) {
      endPara(); endList();
    } else if (list && /^\s{2,}\S/.test(line)) {
      list.items[list.items.length - 1] += ` ${line.trim()}`; // a list item's next line
    } else {
      endList();
      para.push(line.trim());
    }
  }
  endPara(); endList();
  return out;
}

// Inline marks in a line of text: `code`, **strong** and plain text, as runs to draw.
export function runs(text) {
  const out = [];
  const re = /`([^`]+)`|\*\*([^*]+)\*\*/g;
  let at = 0;
  for (let m = re.exec(text); m; m = re.exec(text)) {
    if (m.index > at) out.push({ kind: 'text', text: text.slice(at, m.index) });
    out.push(m[1] != null ? { kind: 'code', text: m[1] } : { kind: 'strong', text: m[2] });
    at = m.index + m[0].length;
  }
  if (at < text.length) out.push({ kind: 'text', text: text.slice(at) });
  return out;
}
