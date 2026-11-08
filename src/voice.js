// Talking with the people in the building, out loud or by typing. Stand in the ring by someone
// (walk.js) and a conversation opens with them: what you say is heard, the page answers for them
// (createBuilding's `talk`), and they say it back in their own voice, with the words shown.
// The voice is Kokoro, an open text-to-speech model, run by the server that serves this page
// (voice/ in this repository), so this device downloads nothing but the sound itself. It is off
// until someone turns it on; ?lite, data saver and low-memory devices never use it; typing always
// works. Nothing is listened to unless the voice is on, someone is in a ring, and something can
// hear: the page's own `hear`, or else the server (it says so in /voice/status).
//
// A page passes `talk` to createBuilding:
//   answer(who, text, said)  what they say back: a string, a promise of one, or an async iterable
//                            of pieces (spoken a sentence at a time as the pieces arrive)
//   greet(who)               optional: what they say when you first step up to them
//   name(who)                optional: a short name for them in the captions
//   voice(who)               optional: which Kokoro voice is theirs
//   hear(sound)              optional: the page's own listening, such as the system's speech
//                            recognition: given what was said as a WAV file (a Blob, 16-bit mono
//                            at 16 kHz), it resolves to the words. If it fails, the server listens.
//   headers()                optional: headers for the page's own server, such as a page token
//   base                     optional: where the voice server is (by default ../voice/ beside src)

import { icon } from './icons.js';

const BASE = new URL('../voice/', import.meta.url).href;
const EAR = new URL('./voice-ear.js', import.meta.url).href;
const SAVED = 'arnheim-voice';
const POE_VOICE = 'af_heart';
const END = /[.!?]["')\]]*\s+/g; // where a sentence ends, mid-stream

// The same short number from an id that rooms.js uses for how someone looks.
function identity(id) {
  let n = 2166136261;
  for (const ch of String(id)) n = Math.imul(n ^ ch.charCodeAt(0), 16777619);
  return n >>> 0;
}

export function voiceWanted() {
  try {
    if (new URLSearchParams(location.search).has('lite')) return false;
    if (navigator.connection?.saveData) return false;
    if (navigator.deviceMemory && navigator.deviceMemory < 4) return false;
    return typeof (window.AudioContext || window.webkitAudioContext) === 'function';
  } catch {
    return false;
  }
}

const remember = (value) => { try { localStorage.setItem(SAVED, value); } catch { /* a private window */ } };
const recalled = () => { try { return localStorage.getItem(SAVED); } catch { return null; } };
const keyOf = (who) => (who ? who.href || who.title || '' : null);

// Words as they are said: no web addresses read out letter by letter, no markup.
const speakable = (text) => String(text).replace(/https?:\/\/\S+/g, 'the link on screen').replace(/[*_`#>|]+/g, ' ').replace(/\s+/g, ' ').trim();

// Hands on each whole sentence as the words come in.
function splitter(emit) {
  let rest = '';
  return {
    feed(piece) {
      rest += piece;
      let last = 0;
      END.lastIndex = 0;
      for (let m = END.exec(rest); m; m = END.exec(rest)) {
        const s = rest.slice(last, m.index + m[0].length).trim();
        if (s) emit(s);
        last = m.index + m[0].length;
      }
      rest = rest.slice(last);
    },
    end() {
      const s = rest.trim();
      rest = '';
      if (s) emit(s);
    },
  };
}

// The microphone's blocks, down to 16,000 samples a second as 16-bit numbers, for the server.
function to16k(parts, rate, keep) {
  const all = new Float32Array(keep);
  let at = 0;
  for (const p of parts) {
    const n = Math.min(p.length, keep - at);
    if (n <= 0) break;
    all.set(p.subarray(0, n), at);
    at += n;
  }
  const step = rate / 16000;
  const out = new Int16Array(Math.floor(all.length / step));
  for (let i = 0; i < out.length; i++) {
    const a = Math.floor(i * step);
    const b = Math.min(all.length, Math.floor((i + 1) * step));
    let sum = 0;
    for (let j = a; j < b; j++) sum += all[j];
    out[i] = Math.max(-32768, Math.min(32767, Math.round((sum / Math.max(1, b - a)) * 32767)));
  }
  return out;
}

function wavFile(pcm, rate) {
  const head = new DataView(new ArrayBuffer(44));
  const tag = (at, s) => { for (let i = 0; i < 4; i++) head.setUint8(at + i, s.charCodeAt(i)); };
  tag(0, 'RIFF'); head.setUint32(4, 36 + pcm.byteLength, true); tag(8, 'WAVE'); tag(12, 'fmt ');
  head.setUint32(16, 16, true); head.setUint16(20, 1, true); head.setUint16(22, 1, true); head.setUint32(24, rate, true);
  head.setUint32(28, rate * 2, true); head.setUint16(32, 2, true); head.setUint16(34, 16, true); tag(36, 'data');
  head.setUint32(40, pcm.byteLength, true);
  return new Blob([head, pcm], { type: 'audio/wav' });
}

export function createVoice({ hud, card, ctx, el, button, signal }) {
  const talk = ctx.talk || null;
  const allowed = voiceWanted();
  const ownEar = typeof talk?.hear === 'function';
  const base = talk?.base || BASE;
  const poeHref = ctx.personRoom?.spec?.person?.href;
  let on = allowed && recalled() === 'on';
  let audio = null; // made on a touch, as browsers ask
  let worklet = null;
  let server = null; // the last /voice/status
  let who = null;
  let mode = 'idle'; // idle, listening, hearing, thinking, speaking
  let gen = 0; // moves on to drop whatever was being said or fetched
  let playing = [];
  let owed = 0; // sentences on their way to being said
  let until = 0; // when, in audio time, the last queued sound ends
  let chain = Promise.resolve();
  let deafUntil = 0;
  let ear = null;
  let micTrouble = '';
  let poll = 0;
  let sounds = 0;
  let heard = '';
  let reply = '';
  const times = {};
  const logs = new Map(); // what was said with each person on this walk

  /* ---------- on the page: a Voice button beside Leave, and the conversation in the card ---------- */

  const toggle = button('', () => setOn(!on), 'Voice');
  toggle.classList.add('aw-voice');
  toggle.hidden = !talk || !allowed;
  hud.firstElementChild?.after(toggle);
  const box = el('div', 'aw-talk');
  const said = el('ol', 'aw-said');
  const line = el('p', 'aw-mic');
  const form = el('form', 'aw-ask');
  const input = el('input');
  input.type = 'text';
  input.maxLength = 300;
  input.autocomplete = 'off';
  input.enterKeyHint = 'send';
  const send = el('button', 'aw-btn', 'Ask');
  send.type = 'submit';
  form.append(input, send);
  box.append(said, line, form);
  box.hidden = !talk;
  card.append(box);
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const text = input.value.trim();
    if (!text || !who) return;
    input.value = '';
    ask(text);
  }, { signal });
  input.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') { event.stopPropagation(); input.blur(); }
  }, { signal });
  // A voice turned on before still needs one touch on this page before it may sound.
  const unlock = () => { if (on) arm(); };
  window.addEventListener('pointerdown', unlock, { signal, capture: true });
  window.addEventListener('keydown', unlock, { signal, capture: true });

  function drawToggle() {
    // The words, or on a narrow screen a microphone (walk.css); aria-pressed says which.
    toggle.replaceChildren(icon(on ? 'mic' : 'mic-off', 18), el('span', 'aw-voice-word', on ? 'Voice on' : 'Voice off'));
    toggle.setAttribute('aria-pressed', String(on));
  }

  // A page's own short name for someone; its slip never stops the walk.
  const nameOf = (person) => {
    if (!person) return 'They';
    try { return talk?.name?.(person) || person.title || 'They'; } catch { return person.title || 'They'; }
  };

  function drawLine() {
    const name = nameOf(who);
    let text;
    let state = mode;
    if (!allowed) { text = 'Type to talk. This device keeps the voice off.'; state = 'off'; }
    else if (!on) { text = 'Type to talk, or turn the voice on.'; state = 'off'; }
    else if (!server || server.state === 'starting' || server.state === 'off') { text = 'Waking the voice'; state = 'thinking'; }
    else if (!server.say) { text = 'Type to talk. This computer has no voice set up.'; state = 'off'; }
    else if (server.state === 'failed') { text = `Type to talk. The voice stopped: ${server.error || 'no reason given'}`; state = 'off'; }
    else if (mode === 'hearing') text = 'Hearing you';
    else if (mode === 'thinking') text = `${name} is thinking`;
    else if (mode === 'speaking') text = `${name} is speaking`;
    else if (!canHear()) { text = 'Type to talk. Listening is not set up on this computer yet.'; state = 'off'; }
    else if (micTrouble) { text = `Type to talk. ${micTrouble}`; state = 'off'; }
    else text = 'Listening. Just speak.';
    line.textContent = text;
    line.className = `aw-mic aw-${state}`;
  }

  function drawLog() {
    const list = logs.get(keyOf(who)) || [];
    said.replaceChildren(...list.slice(-4).map((e) => {
      const item = el('li', e.you != null ? 'aw-you' : 'aw-them');
      item.append(el('b', null, e.you != null ? 'You' : nameOf(who)), document.createTextNode(` ${e.you ?? e.them}`));
      return item;
    }));
    said.hidden = !list.length;
    said.scrollTop = said.scrollHeight;
  }

  function add(entry) {
    const k = keyOf(who);
    const list = logs.get(k) || [];
    list.push(entry);
    while (list.length > 12) list.shift();
    logs.set(k, list);
    drawLog();
    return entry;
  }

  /* ---------- the server: whether it can speak and hear, and asking it to ---------- */

  async function request(name, body, sound) {
    const init = body === undefined
      ? { method: 'GET' }
      : { method: 'POST', headers: { ...(talk?.headers?.() || {}), 'Content-Type': sound ? 'audio/wav' : 'application/json' }, body: sound ? body : JSON.stringify(body) };
    const r = await fetch(base + name, { ...init, cache: 'no-store', credentials: 'same-origin' });
    if (name === 'say') {
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || `The voice answered ${r.status}`);
      return { data: await r.arrayBuffer(), ms: Number(r.headers.get('X-Voice-Ms')) || 0 };
    }
    return r.json();
  }

  async function wake() {
    clearTimeout(poll);
    server = await request('status').catch(() => ({ say: false, state: 'missing', hear: false }));
    if (server.say && server.state !== 'ready') {
      server = await request('wake', {}).catch(() => server);
      const check = async () => {
        if (!on) return;
        server = await request('status').catch(() => server);
        drawLine();
        if (server.state === 'starting') poll = setTimeout(check, 1000);
        else if (server.state === 'ready') listen();
      };
      poll = setTimeout(check, 800);
    }
    drawLine();
    if (server.state === 'ready') listen();
  }

  function arm() {
    if (!audio) {
      const Context = window.AudioContext || window.webkitAudioContext;
      try { audio = new Context(); } catch { return; }
    }
    if (audio.state !== 'running') audio.resume().catch(() => {});
  }

  function setOn(value) {
    on = !!value && allowed;
    remember(on ? 'on' : 'off');
    drawToggle();
    if (on) {
      arm();
      wake();
      greet();
    } else {
      gen += 1;
      hush();
      stopEar();
      clearTimeout(poll);
      if (mode !== 'thinking') mode = who ? 'listening' : 'idle';
    }
    drawLine();
  }

  /* ---------- saying it: a sentence at a time, each fetched while the one before plays ---------- */

  function voiceOf(person) {
    const own = talk?.voice?.(person);
    if (own) return own;
    const list = server?.voices || [];
    if (!list.length) return null;
    if (person.href && person.href === poeHref) return list.includes(POE_VOICE) ? POE_VOICE : list[0];
    // Everyone else: one of the voices, or an even mix of two with the same accent.
    const singles = list.filter((v) => v !== POE_VOICE);
    const mixes = [];
    for (let i = 0; i < singles.length; i++) for (let j = i + 1; j < singles.length; j++) if (singles[i][0] === singles[j][0]) mixes.push(`${singles[i]},${singles[j]}`);
    const all = [...singles, ...mixes];
    return all.length ? all[(identity(keyOf(person)) >>> 14) % all.length] : list[0];
  }

  function hush() {
    for (const s of playing) { try { s.onended = null; s.stop(); } catch { /* already stopped */ } }
    playing = [];
    owed = 0;
    until = 0;
    chain = Promise.resolve();
  }

  function settle(g) {
    if (g !== gen || playing.length || owed) return;
    mode = 'listening';
    deafUntil = performance.now() + 350; // the room's echo of the last word
    drawLine();
  }

  function play(buffer, g, ms) {
    arm();
    const src = audio.createBufferSource();
    src.buffer = buffer;
    src.connect(audio.destination);
    const at = Math.max(audio.currentTime + 0.03, until);
    src.start(at);
    until = at + buffer.duration;
    playing.push(src);
    sounds += 1;
    if (times.firstSound == null) {
      times.firstSound = performance.now() + (at - audio.currentTime) * 1000;
      times.sayMs = ms;
    }
    mode = 'speaking';
    drawLine();
    src.onended = () => {
      playing = playing.filter((s) => s !== src);
      settle(g);
    };
  }

  function queue(text, voice, g) {
    const words = speakable(text);
    if (!words || !voice || !audio) return;
    owed += 1;
    const fetching = request('say', { text: words, voice }).catch((error) => {
      console.warn('Arnheim: the voice could not say that.', error);
      return null;
    });
    chain = chain.then(async () => {
      const got = await fetching;
      if (g !== gen) return;
      owed -= 1;
      let buffer = null;
      if (got) {
        try { buffer = await audio.decodeAudioData(got.data); } catch { buffer = null; }
      }
      if (g !== gen) return;
      if (buffer) play(buffer, g, got.ms);
      else settle(g);
    });
  }

  function say(text, person = who) {
    const g = gen;
    const voice = on && server?.state === 'ready' ? voiceOf(person) : null;
    if (!voice) return;
    const split = splitter((s) => queue(s, voice, g));
    split.feed(text);
    split.end();
  }

  /* ---------- talking ---------- */

  function greet() {
    if (!who || !on || logs.get(keyOf(who))?.length) return;
    let text = null;
    try { text = talk?.greet?.(who); } catch (error) { console.warn('Arnheim: no greeting.', error); }
    if (!text) return;
    add({ them: text });
    if (server?.state === 'ready') say(text);
  }

  async function ask(text, spokenEnd = null) {
    if (!who || !talk) return;
    const asked = who;
    gen += 1;
    const g = gen;
    hush();
    const before = (logs.get(keyOf(asked)) || []).map((e) => (e.you != null ? { you: e.you } : { them: e.them }));
    add({ you: text });
    heard = text;
    mode = 'thinking';
    drawLine();
    times.asked = performance.now();
    times.spokenEnd = spokenEnd;
    times.firstSound = null;
    times.sayMs = null;
    let out;
    try {
      out = await talk.answer?.(asked, text, before);
    } catch (error) {
      console.warn('Arnheim: no answer.', error);
      out = null;
    }
    if (g !== gen) return;
    const entry = add({ them: '' });
    const voice = on && server?.state === 'ready' ? voiceOf(asked) : null;
    const split = splitter((s) => { if (voice && g === gen) queue(s, voice, g); });
    const take = (piece) => {
      entry.them += piece;
      if (keyOf(who) === keyOf(asked)) drawLog();
      split.feed(piece);
    };
    if (out == null) take("Sorry, I can't answer that here.");
    else if (typeof out === 'string') take(out);
    else if (typeof out[Symbol.asyncIterator] === 'function') {
      try {
        for await (const piece of out) {
          if (g !== gen) return;
          take(String(piece));
        }
      } catch (error) {
        console.warn('Arnheim: the answer was cut off.', error);
        take(' (The answer was cut off.)');
      }
    } else take(String(out));
    split.end();
    reply = entry.them;
    settle(g);
  }

  /* ---------- listening: the microphone, only while someone is in a ring with the voice on ---------- */

  const vad = { floor: -55, on: false, voiced: 0, quiet: 0, len: 0, pre: [], parts: [] };

  async function listen() {
    if (ear || !on || !who || !canHear() || !audio || !navigator.mediaDevices?.getUserMedia) { drawLine(); return; }
    const mine = { stage: 'asking' }; // asking for the microphone, then loading the worklet
    ear = mine;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 } });
      if (ear !== mine) { for (const t of stream.getTracks()) t.stop(); return; }
      mine.stage = 'worklet';
      worklet ??= audio.audioWorklet.addModule(EAR);
      await worklet;
      if (ear !== mine) { for (const t of stream.getTracks()) t.stop(); return; }
      const source = audio.createMediaStreamSource(stream);
      const node = new AudioWorkletNode(audio, 'arnheim-ear');
      const sink = audio.createGain();
      sink.gain.value = 0;
      source.connect(node);
      node.connect(sink);
      sink.connect(audio.destination);
      node.port.onmessage = (event) => hearBlock(event.data);
      Object.assign(mine, { stage: 'on', stream, source, node, sink, rate: audio.sampleRate });
      Object.assign(vad, { on: false, voiced: 0, quiet: 0, len: 0, pre: [], parts: [] });
      micTrouble = '';
    } catch (error) {
      if (ear === mine) ear = null;
      micTrouble = error?.name === 'NotAllowedError' ? 'The microphone is not allowed here.' : 'The microphone did not start.';
      console.warn('Arnheim: no microphone.', error);
    }
    drawLine();
  }

  function stopEar() {
    const was = ear;
    ear = null;
    if (!was?.stream) return;
    for (const t of was.stream.getTracks()) t.stop();
    was.node.port.onmessage = null;
    was.source.disconnect();
    was.node.disconnect();
    was.sink.disconnect();
    vad.on = false;
  }

  // Decides when someone starts and stops speaking, from how loud each block is against the
  // room's own level. Deaf while they are answering, so they never hear themselves.
  function hearBlock(block) {
    if (!ear?.stream || !who) return;
    const dur = block.length / ear.rate;
    let sum = 0;
    for (let i = 0; i < block.length; i++) sum += block[i] * block[i];
    const db = 10 * Math.log10(sum / block.length + 1e-12);
    if (!vad.on) {
      vad.floor += (db - vad.floor) * (db < vad.floor ? 0.3 : 0.02);
      if (mode === 'speaking' || mode === 'thinking' || performance.now() < deafUntil) { vad.voiced = 0; vad.pre = []; return; }
      vad.pre.push(block);
      while (vad.pre.length * dur > 0.35) vad.pre.shift();
      if (db > Math.max(vad.floor + 12, -52)) {
        vad.voiced += dur;
        if (vad.voiced >= 0.12) {
          Object.assign(vad, { on: true, parts: [...vad.pre], len: vad.pre.length * dur, quiet: 0 });
          mode = 'hearing';
          drawLine();
        }
      } else vad.voiced = 0;
      return;
    }
    vad.parts.push(block);
    vad.len += dur;
    vad.quiet = db > Math.max(vad.floor + 7, -57) ? 0 : vad.quiet + dur;
    if (vad.quiet >= 0.7 || vad.len >= 15) {
      const { parts, quiet } = vad;
      Object.assign(vad, { on: false, parts: [], pre: [], voiced: 0 });
      finish(parts, ear.rate, quiet);
    }
  }

  async function finish(parts, rate, quiet) {
    const length = parts.reduce((n, p) => n + p.length, 0);
    if (length / rate - quiet < 0.3) { mode = 'listening'; drawLine(); return; }
    const ended = performance.now() - quiet * 1000; // when they stopped speaking
    mode = 'thinking';
    drawLine();
    const asked = who;
    const g = gen;
    const pcm = to16k(parts, rate, length - Math.floor(quiet * rate * 0.6));
    const text = await heardWords(wavFile(pcm, 16000));
    if (keyOf(asked) !== keyOf(who) || g !== gen) return;
    times.hearMs = Math.round(performance.now() - ended);
    if (!text) { mode = 'listening'; drawLine(); return; }
    ask(text, ended);
  }

  function canHear() {
    return ownEar || !!server?.hear;
  }

  // The words in what was said: the page's own listening if it has one, else the server's.
  async function heardWords(sound) {
    if (ownEar) {
      try {
        const words = await talk.hear(sound);
        if (typeof words === 'string') { times.heardBy = 'page'; return words.trim(); }
      } catch { /* the server listens instead, if it can */ }
    }
    if (!server?.hear) return '';
    const got = await request('hear', sound, true).catch(() => null);
    times.heardBy = 'server';
    return got?.ok ? String(got.text || '').trim() : '';
  }

  /* ---------- the walk's hooks ---------- */

  // Someone stepped into a ring (or out of one, with null).
  function talkTo(next) {
    if (!talk || keyOf(next) === keyOf(who)) return;
    gen += 1;
    hush();
    stopEar();
    who = next;
    if (!who) { mode = 'idle'; return; }
    input.placeholder = `Type to ${nameOf(who)}`;
    input.setAttribute('aria-label', `Say something to ${nameOf(who)}`);
    mode = 'listening';
    drawLog();
    drawLine();
    if (!on) return;
    arm();
    if (!server || server.state !== 'ready') wake();
    else listen();
    greet();
  }

  function info() {
    const since = (t) => (times.firstSound != null && t != null ? Math.round(times.firstSound - t) : null);
    return {
      allowed, on, mode, who: who?.title || null, voice: who ? voiceOf(who) : null,
      server: server && { say: !!server.say, state: server.state, hear: !!server.hear, voices: server.voices?.length || 0 },
      ear: ear?.stage || false, mic: micTrouble || null, heard, reply, sounds,
      firstSoundMs: since(times.asked), fromSpeechEndMs: since(times.spokenEnd), hearMs: times.hearMs ?? null, sayMs: times.sayMs ?? null,
      ownEar, heardBy: times.heardBy || null,
    };
  }

  function dispose() {
    gen += 1;
    hush();
    stopEar();
    clearTimeout(poll);
    box.remove();
    toggle.remove();
    audio?.close?.().catch(() => {});
    audio = null;
  }

  drawToggle();
  drawLine();
  if (on && talk) wake();
  return { talkTo, info, dispose };
}
