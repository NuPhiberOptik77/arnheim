// Control of your Claude Code agents from the building (connect/control.py; docs/connect.md,
// "Control your agents"). It is off unless the server was started with --control, and only for the
// page on that computer. While it is on and the page is in view, the page asks every few seconds for
// what is waiting (permission requests), what was started here, and which projects have a folder.
//
// createControl({ base, headers, busy }) talks to the server: `base` is where /control/ is (by
// default ../control/ beside src), `headers()` adds a page token for a server of its own, and
// `busy()` says the person is using the page. The rest are the words for the walk: agentReply (or
// agentQuick) and agentControls for an agent in its ring, deskStart for the receptionist, who can
// start an agent on a project.

const BASE = new URL('../control/', import.meta.url).href;
const OFF = { on: false, asks: [], runs: [], projects: [] };
const sleep = (ms) => new Promise((done) => setTimeout(done, ms));

// Someone is using the page while `busy()` says so (walking, say) and for two minutes after they
// last touched it. Only then does a permission request wait for an answer here.
export function createControl({ base = BASE, headers = () => ({}), every = 3000, busy = () => false } = {}) {
  let token = null;
  let touched = 0;
  for (const kind of ['pointerdown', 'keydown', 'wheel', 'touchstart']) {
    window.addEventListener(kind, () => { touched = Date.now(); }, { passive: true, capture: true });
  }
  const using = () => { try { return !!busy() || Date.now() - touched < 120000; } catch { return false; } };
  let state = OFF;
  let timer = 0;
  let running = false;
  const watchers = new Set();

  async function call(name, body) {
    const head = { ...(headers() || {}), ...(token ? { 'X-Arnheim-Control': token } : {}) };
    const init = body === undefined
      ? { method: 'GET', headers: head }
      : { method: 'POST', headers: { ...head, 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
    const r = await fetch(base + name, { ...init, cache: 'no-store', credentials: 'same-origin' });
    const data = await r.json().catch(() => ({}));
    if (r.status === 403) token = null; // the server started again, with a new token
    if (!r.ok) throw new Error(data.error || `The building's control answered ${r.status}.`);
    return data;
  }

  function set(next) {
    state = next && typeof next === 'object' ? { ...OFF, ...next } : OFF;
    for (const watcher of watchers) {
      try { watcher(state); } catch (error) { console.warn('Arnheim: control watcher failed.', error); }
    }
  }

  // Only while the page is in view. It says `here` while someone is using it: only then does a
  // permission request wait for an answer here (connect/control.py, WATCHED).
  async function poll() {
    clearTimeout(timer);
    if (!running) return;
    if (!document.hidden) {
      try {
        if (!token) {
          const t = await call('token');
          if (!t.on) { running = false; set(OFF); return; } // switched off: ask no more
          token = t.token;
        }
        set(await call(using() ? 'here' : 'state'));
      } catch {
        // the server is restarting, or away: look again shortly
      }
    }
    if (running) timer = setTimeout(poll, every);
  }

  const after = (promise) => promise.then((out) => { poll(); return out; });

  return {
    start() { if (!running) { running = true; poll(); } return this; },
    stop() { running = false; clearTimeout(timer); },
    get on() { return !!state.on; },
    state: () => state,
    watch(fn) { watchers.add(fn); return () => watchers.delete(fn); },
    askFor: (key) => state.asks.find((a) => a.key === key) || null,
    run: (key) => state.runs.find((r) => r.key === key) || null,
    projects: () => state.projects,
    say: (key, text) => call('say', { key, text }),
    answer: (id, behavior) => after(call('answer', { id, behavior })),
    begin: (project, text) => after(call('start', { project, text })),
    halt: (key) => after(call('stop', { key })),
    // Done means proven (connect/prove.py): the name of a floor's check, if it has one, and running it again.
    checkOf: (project) => state.projects.find((p) => p.project === project)?.check || null,
    prove: (key) => after(call('prove', { key })),
    // Routines (connect/routines.py): run one now.
    runRoutine: (key) => after(call('run_routine', { key })),
    // The company's memory (connect/control.py): what every agent is told.
    remember: (text) => after(call('remember', { text })),
    // A budget per floor, and every agent paused at once (connect/budget.py).
    paused: () => state.paused || null,
    timesAllowed: (project) => 1 + (state.allowed?.[project] || 0),
    allowMore: (project) => after(call('allow_more', { project })),
    pauseAll: () => after(call('pause', {})),
    resumeAll: () => after(call('resume', {})),
    forget: (id) => after(call('forget', { id })),
    refresh: poll,
  };
}

/* ---------- an agent in its ring ---------- */

// Spoken or typed, the whole of what was said: a stray "yes" never allows anything.
const ALLOW = /^(?:yes[,.!]?\s+)?(?:allow|approve)(?: it| that| this)?(?: once| please)?[.!]?$/i;
const DENY = /^(?:no[,.!]?\s+)?(?:no|nope|deny|refuse|reject|don'?t|do not)(?: allow)?(?: it| that| this)?(?: please)?[.!]?$/i;
const NEARLY = /^(?:yes|yeah|yep|ok|okay|sure|go ahead|do it)\b/i;
const STOP = /^(?:please\s+)?stop(?: now| working| it| that| there| please)*[.!]?$/i;

// What you said in an agent's ring, if it was "allow" or "deny" for an open permission request
// (the whole of what you said), or "stop": its answer. Null for anything else, for a page whose
// agents answer the rest in their own way. `latest()` gives the conversation as the page last read it.
export function agentQuick(control, item, text, latest = () => item) {
  const key = item.id;
  const words = String(text || '').trim();
  const ask = control.askFor(key);
  const fail = (error) => error.message;
  if (ask && ALLOW.test(words)) return control.answer(ask.id, 'allow').then(() => 'Allowed, just this once. Carrying on.', fail);
  if (ask && DENY.test(words)) return control.answer(ask.id, 'deny').then(() => "Denied. I won't do that.", fail);
  if (ask && NEARLY.test(words)) return `Say "allow" to let me, or "deny". It's for ${ask.what}.`;
  if (STOP.test(words)) {
    const run = control.run(key);
    if (!latest()?.working && run?.state !== 'working') return "I'm not working on anything right now.";
    return control.halt(key).then(() => 'Stopping now.', fail);
  }
  return null;
}

// An agent's answer to what you said in its ring, with control on: agentQuick's, or else the words
// go to its Claude Code conversation, and its reply comes back when it has one.
export function agentReply(control, item, text, latest = () => item) {
  const key = item.id;
  const words = String(text || '').trim();
  const quick = agentQuick(control, item, words, latest);
  if (quick != null) return quick;
  return (async function* reply() {
    let sent;
    try {
      sent = await control.say(key, words);
    } catch (error) {
      yield error.message;
      return;
    }
    const resumed = sent.sent === 'resumed';
    if (!resumed && !latest()?.working) {
      yield "I'm waiting for you in Claude Code, so I'll see this the next time you send me something there.";
      return;
    }
    yield resumed ? 'On it. ' : "Got it. I'll read that at my next step. ";
    const until = Date.now() + 3 * 60 * 1000;
    while (Date.now() < until) {
      await sleep(1500);
      const run = control.run(key);
      if (run?.answered === sent.id) { yield run.said || "I've done that."; return; }
      const now = latest();
      if (now?.answered === sent.id) { yield now.says?.now || "I've done that."; return; }
    }
    yield "I'm still on it. My answer will show here and in the panel.";
  })();
}

// The buttons on an agent's card in the walk: Allow and Deny while it waits for your permission,
// Stop while it works. Each gives the words for the conversation when it is done.
export function agentControls(control, item) {
  if (!control?.on || !item?.id) return null;
  const ask = control.askFor(item.id);
  const fail = (error) => error.message;
  if (ask) {
    return {
      note: `Wants your permission for ${ask.what}`,
      buttons: [
        { label: 'Allow', run: () => control.answer(ask.id, 'allow').then(() => 'Allowed, just this once.', fail) },
        { label: 'Deny', run: () => control.answer(ask.id, 'deny').then(() => 'Denied.', fail) },
      ],
    };
  }
  const run = control.run(item.id);
  if (item.working || run?.state === 'working') return { note: null, buttons: [{ label: 'Stop', run: () => control.halt(item.id).then(() => 'Stopping now.', fail) }] };
  return null;
}

/* ---------- the receptionist starts an agent ---------- */

const START = /^(?:please\s+|can you\s+|could you\s+)?(?:start|begin|launch)\s+(?:an?\s+)?(?:new\s+)?(?:agent|conversation|claude)\s+(?:on|for|in|at)\s+(?:the\s+)?(.+?)(?:\s+(?:floor|project))?\s*(?::|,|\s+to\s+|\s+and\s+(?:have it\s+|ask it to\s+)?)\s*(.+)$/i;
const GO = /^(?:yes[,.!]?\s+)?(?:start it|start|go ahead|do it)(?: please| now)?[.!]?$/i;
const CANCEL = /^(?:no|nope|cancel|don'?t|never ?mind|stop)\b/i;

// The receptionist, asked to start an agent ("start an agent on Lantern to fix the login page"):
// they check the project has a folder here and ask you to say "start it", or tap Start. `pending`
// holds what waits for that, between calls. Gives { reply, pending } or null if it wasn't about this.
// "Get someone to fix the login bug on Lantern", "have an agent on Lantern tidy the tests", "ask Claude to
// fix the login": work handed out in everyday words. The floor can come at the end, after "on", "for" or
// "in", or not at all, and then the receptionist asks which.
const HAND_OUT = /^(?:please\s+|can you\s+|could you\s+)?(get|have|ask|send|find)\s+(?:someone|somebody|an?\s+(?:new\s+)?agent|claude)\s+(?:(?:on|from|for)\s+(?:the\s+)?(.+?)(?:\s+(?:floor|project))?\s+)?(to\s+)?(.+)$/i;

// The floor a name means, among those control can start agents on.
const projectNamed = (list, name) => {
  const asked = String(name || '').trim().toLowerCase().replace(/^the\s+/, '').replace(/\s+(?:floor|project)$/, '').replace(/[.!?]+$/, '');
  return list.find((x) => x.label.toLowerCase() === asked || x.project.toLowerCase() === asked)
    || list.find((x) => asked && (x.label.toLowerCase().startsWith(asked) || asked.startsWith(x.label.toLowerCase()))) || null;
};

// A question to pass on, not work to hand out: "ask Claude what is waiting on me", "ask an agent how it's going",
// "ask Claude do the tests pass". With "to" ("ask Claude to do the release notes"), or after "have", "get", "send"
// or "find" ("have someone do the release notes"), it is work.
const ASKS = /^(?:what|what's|whats|how|how's|whether|if|where|when|why|who|who's|whom|which|about|is|isn't|are|aren't|am|was|wasn't|were|weren't|do|don't|does|doesn't|did|didn't|has|hasn't|have|haven't|had|can|can't|could|couldn't|should|shouldn't|shall|may|might|would|wouldn't|will|won't)\b/i;

// The job and its floor from handed-out words: the floor is the last "on/for/in <a floor's name>".
export function handedOut(words, list) {
  const said = String(words || '').trim();
  const m = HAND_OUT.exec(said);
  if (!m || /\?$/.test(said) || (/^ask$/i.test(m[1]) && !m[3] && ASKS.test(m[4].trim()))) return null;
  if (m[2]) return { project: projectNamed(list, m[2]), job: m[4], named: m[2] };
  const job = m[4];
  const at = [...job.matchAll(/\s(?:on|for|in)\s+(?:the\s+)?/gi)].reverse();
  for (const cut of at) {
    const p = projectNamed(list, job.slice(cut.index + cut[0].length));
    if (p) return { project: p, job: job.slice(0, cut.index) };
  }
  return { project: null, job };
}

const offer = (p, job) => ({ pending: { project: p.project, label: p.label, text: job, check: p.check || null },
  reply: `Start an agent on ${p.label} to ${job}?${p.check ? ` When it says it's done, Arnheim runs ${p.check.replace(/^The /, 'the ')} on its work.` : ''} Say "start it", or tap Start.` });

export function deskStart(control, text, pending) {
  if (!control?.on) return null;
  const words = String(text || '').trim();
  if (pending?.project && GO.test(words)) {
    return {
      pending: null,
      started: pending,
      reply: control.begin(pending.project, pending.text).then(
        () => `Started. The new agent is on ${pending.label}, with your brief and the company's memory. Watch it sit down in ${pending.label}'s Conversations room.`,
        (error) => error.message),
    };
  }
  if (pending && CANCEL.test(words)) return { pending: null, reply: "All right, I won't start it." };
  const list = control.projects();
  if (pending && !pending.project) { // which floor, asked for last time
    const p = projectNamed(list, words.replace(/^(?:on|for|in)\s+/i, ''));
    if (p) return offer(p, pending.text);
  }
  const given = handedOut(words, list);
  if (given && given.job.trim().length > 2) {
    const job = given.job.trim().replace(/[.!]+$/, '');
    if (given.project) return offer(given.project, job);
    if (!list.length) return { pending: null, reply: "I can't start agents yet: no floor names its project's folder in company.json." };
    if (list.length === 1) return offer(list[0], job);
    return { pending: { project: null, text: job }, reply: `On which floor? ${list.map((x) => x.label).join(', ')}.` };
  }
  const m = START.exec(words);
  if (!m) return pending ? { pending, reply: null } : null;
  const p = projectNamed(list, m[1]);
  if (!p) {
    return {
      pending: null,
      reply: list.length
        ? `I can only start agents on projects whose folder I know: ${list.map((x) => x.label).join(', ')}.`
        : "I can't start agents yet: no floor names its project's folder in company.json.",
    };
  }
  return offer(p, m[2].trim().replace(/[.!]+$/, ''));
}

// The receptionist's card while a start waits for your word.
export function deskControls(pending, confirm, cancel) {
  if (!pending?.project) return null;
  return {
    note: `New agent on ${pending.label}: ${pending.text}`,
    buttons: [{ label: 'Start', run: confirm }, { label: 'Cancel', run: cancel }],
  };
}
