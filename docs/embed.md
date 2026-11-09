# Arnheim in your own page

The world knows nothing about the page around it. `index.html` and `src/demo.js` show the whole
contract.

## The building

`createBuilding(canvas, map, options)` from `src/building.js` draws the company map (company.json)
on a canvas. Its options:

- `labels`: an element over the canvas, for the names that float over floors and rooms. Their look
  is the `.label` rules in `src/demo.css`, for your page to copy or restyle. The walk brings its own
  styles (`src/walk.css` and `src/notes.css`).
- `onPick(hit)`: something was tapped. `hit.href` is what it opens, and `hit.floorId` and
  `hit.roomId` where it is.
- `onHover(info, x, y)`: the pointer is over something (`info.title`, `info.sub`), or nothing.
- `onStatus(status)`: the browser took the graphics away (`lost`) or gave back a blank picture
  (`blank`), so the page can start the building again, as `demo.js` does.
- `onWalk(on)`: a walk started or ended.
- `onNotes()`: someone walked into the founder's office, so the page can answer with fresh notes.
- `talk`: lets the people in the walk talk back (below).

The building it gives back:

- `setLive(model)` lights it: one plain object per room, keyed `floor/room`, plus `floor:<id>` for
  the line under each floor's name ([data.md](data.md), "The live model").
- `setNotes(notes)` hangs the founder's newest notes in their office, each
  `{ id, title, text, when, pictures, locked }` in plain text. `onNotes` is called when someone
  walks into the office and every two minutes while they stay.
- `setScene({ mode })` relights it: `all`, `needs` or `working`, or `{ mode: 'floor', floor }` for
  one floor.
- `setTheme(dark)`, `focus({ floor, room, item })`, `highlight({ floor, room })`, `zoomBy(k)`,
  `turn(x, y)`, `resetView()`, `walk(on)` (a promise of whether it is walking now), `walking()`
  and `dispose()`.

## The receptionist's desk

`createPoe(kit)` from `src/poe-desk.js` gives you the receptionist's desk for the panel. They answer
by keyword matching over the facts you pass in, with no AI, and a page can teach them its own words
(`kit.words`) and topics (`kit.topics`). Their name is the map's `receptionist.name`, or
`kit.name`. `poeBadge(size, look)` draws a small picture of them in their look's colours.

## Talking in the walk

`talk`, in `createBuilding`'s options, turns the rings into conversations (`src/voice.js` says
more). Only `answer` is needed:

- `answer(who, text, said)`: their reply to `text`: words, a promise of words, or a stream of them
  (an async iterable), spoken a sentence at a time as it comes.
- `greet(who)`: what they say when you step up.
- `name(who)`: a short name for them, for the captions.
- `voice(who)`: which Kokoro voice is theirs.
- `hear(sound)`: the page's own listening, such as the system's speech recognition in a desktop
  app. Given what was said as a WAV file (a Blob of 16-bit mono sound at 16 kHz), it resolves to
  the words. If it fails, the server listens.
- `headers()`: headers for the voice server, such as a page token.
- `base`: where the voice server is, if not `../voice/` beside `src`.
- `controls(who)`: buttons for their card while you stand with them, as
  `{ note, buttons: [{ label, run }] }`, or null. `run` gives what they say about it after.

`who` is the person: `{ title, href }`. The receptionist's `href` is `#/front-desk` and the
assistant's `#/assistant`, unless the map gives them another; anyone else's is what they are
working on. Without `talk`, the rings only open what someone is working on.

The voice is a few requests under `/voice/`. `serve.py` answers them, and so can a server of your
own: `voice/bridge.py` is standard-library Python, with one call (`Voice.handle`) for all of them.

## Controlling agents

`src/control.js` is the page's side of controlling Claude Code agents ([connect.md](connect.md),
step 4). `createControl({ base, headers, busy })` talks to the server, by default `../control/`
beside `src`. A permission request waits for an answer only while someone uses the page: while
`busy()` says so (walking, say), and for two minutes after a touch. `agentReply` and `agentControls`
give an agent's answers and card buttons for `talk` (`agentQuick` only allow, deny and stop), and
`deskStart` and `deskControls` let the receptionist start agents; `src/demo.js` shows how. On the
server, `connect/control.py` is standard-library Python with one call (`Control.handle`) for every
request, as the voice has. Answer it only for the page on this computer.

## Serving it

A server that shows Arnheim must send `.jpg` and `.hdr` files, as `serve.py` does: a walk loads
about 6 MB of photographed materials (CC0, from Poly Haven) once someone presses Walk. A phone
short of memory, or a browser with data saver on, keeps the drawn materials instead.

## Address options

- `?sample` shows the sample even when `data/` has a company.
- `?lite` keeps the drawn materials and leaves the voice off.
- `?list` shows the panel alone, with no 3D.
- `?live=off` starts with the sample's story paused.
- `?theme=light` or `?theme=dark` picks the look.
- `?scene=needs`, `?scene=working`, or `?scene=` and a floor's `id`, lights only part of the
  building.
