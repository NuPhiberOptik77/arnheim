// The receptionist's and the assistant's brain (connect/brain.py; docs/brain.md). It is off unless
// the server was started with --brain, and only for the page on that computer. Then what you ask
// them goes to Claude, through the Claude Code on that computer, with the building's facts, and the
// answer comes back a piece at a time, for voice.js to speak a sentence at a time.
//
// createBrain({ base, headers }) talks to the server: `base` is where /brain/ is (by default
// ../brain/ beside src), `headers()` adds a page token for a server of its own. check() asks once
// whether it is on, and `on` says so after. `who` is { role, name, company }, where role is
// 'receptionist' or 'assistant'; `facts` is a list of [section, text]. The server gives Claude all
// of them the first time, and after that only the sections that changed.

const BASE = new URL('../brain/', import.meta.url).href;
const STATUS_MS = 1500; // a server with no brain, or one too slow to say, means off

export function createBrain({ base = BASE, headers = () => ({}) } = {}) {
  let status = { on: false };
  let asked = null;

  function check() {
    if (!asked) {
      const stop = new AbortController();
      const timer = setTimeout(() => stop.abort(), STATUS_MS);
      asked = fetch(`${base}status`, { cache: 'no-store', credentials: 'same-origin', signal: stop.signal })
        .then((r) => (r.ok ? r.json() : { on: false }))
        .catch(() => ({ on: false }))
        .then((s) => {
          clearTimeout(timer);
          status = s && s.on ? s : { on: false };
          return status;
        });
    }
    return asked;
  }

  // A request with the page's token. If the server started again since (a new token), the status
  // is read again, once.
  async function post(name, body, signal) {
    for (let again = false; ; again = true) {
      const r = await fetch(base + name, {
        method: 'POST',
        cache: 'no-store',
        credentials: 'same-origin',
        signal,
        headers: { ...(headers() || {}), 'Content-Type': 'application/json', 'X-Arnheim-Brain': status.token || '' },
        body: JSON.stringify(body),
      });
      if (r.status !== 403 || again) return r;
      asked = null;
      if (!(await check()).on) return r;
    }
  }

  const said = (who, facts, text) => ({ who: who.role, name: who.name || '', company: who.company || '', facts, ...(text == null ? {} : { text }) });

  return {
    check,
    get on() { return !!status.on; },
    get model() { return status.model || null; },
    // Reads them the facts before they are asked anything, so the first answer comes sooner.
    // Resolves to whether it did; nothing else comes back.
    prime(who, facts) {
      if (!status.on) return Promise.resolve(false);
      return post('prime', said(who, facts)).then((r) => r.ok, () => false);
    },
    // Their answer, a piece at a time. It throws if there is none (no Claude Code, not signed in, an
    // error, too slow), so the page can answer from the building's files instead.
    async* ask(who, text, facts) {
      if (!status.on) throw new Error('The brain is off.');
      const stop = new AbortController();
      let ended = false;
      try {
        const r = await post('ask', said(who, facts, text), stop.signal);
        if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || `The brain answered ${r.status}.`);
        const reader = r.body.getReader();
        const decoder = new TextDecoder();
        let rest = '';
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          rest += decoder.decode(value, { stream: true });
          for (let at = rest.indexOf('\n'); at >= 0; at = rest.indexOf('\n')) {
            let got = null;
            try { got = JSON.parse(rest.slice(0, at)); } catch { got = null; }
            rest = rest.slice(at + 1);
            if (got?.error) throw new Error(got.error);
            if (got?.done) { ended = true; return; }
            if (got?.text) yield got.text;
          }
        }
        throw new Error('The answer was cut off.');
      } finally {
        if (!ended) stop.abort(); // nobody is listening any more: the server lets Claude finish on its own
      }
    },
  };
}
