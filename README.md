# Arnheim

A company as a building you can turn and walk through. Each project is a floor, each kind of work
is a room, a receptionist called Poe answers questions at the front desk, and the live work lights
up as it happens: warm while something is working, amber when something needs you, dim when all is
quiet.

It is named after Edgar Allan Poe's story "The Domain of Arnheim", about a man who shapes a
landscape into a world of its own. Arnheim is free and open, and never sold.

## Try it

You need Python 3 and a browser with WebGL. There is nothing to install, build or download.

```bash
python3 serve.py
```

Then open http://127.0.0.1:8740.

It opens on Fernhollow, a company that is made up. Its people, projects, websites and numbers are
all invented, and the work you see moving is a short story on a loop. Tap a floor to bring it out,
a room to look inside, and Poe to ask a question. The Live button pauses the story.

## Walk through it

Press Walk to step inside. You start at the door of the reception, with Poe behind the desk. On a
computer, walk with WASD or the arrow keys and drag to look around; on a phone, use the stick and
drag. Tap the floor to walk there, and tap a desk, a screen or Poe to open it. The lift at the end
of each floor takes you up and down: the floor you leave burns away into glowing points, and the
next one gathers out of them. Double-tap anywhere to burn the floor you are on and rebuild it.
With reduced motion on, the camera keeps still and floors change at once.

## Make it yours

The building comes from two files:

- `sample/company.json` is the map: the company's name and mission, its floors (one per project),
  the rooms on each floor, the lobby (Front of house) and the basement (shared machines and the
  Library). Every floor and room has an `about` line, which Poe uses to answer questions.
- `sample/work.json` is what is going on: tasks, goals, conversations, pull requests, websites,
  machines and their jobs, and the story that plays on a loop.

Change them and reload. A floor can choose its colours with `palette`: terracotta, harbour, sage,
indigo, plum, teal, sand or slate.

## Use it in your own page

The world knows nothing about the page around it. `src/demo.js` shows the whole contract:

- `createBuilding(canvas, map, { labels, onPick, onHover, onStatus })` from `src/building.js`
  draws the company map.
- `building.setLive(rooms)` lights it: one plain object per room, keyed `floor/room`, plus
  `floor:<id>` for the line under each floor's name.
- `createPoe(kit)` from `src/poe-desk.js` gives you Poe's desk. Poe answers by keyword matching over
  the facts you pass in, with no AI, and a page can teach Poe its own words and topics.

## How it is made

Plain ES modules and Three.js, with no build step. The building draws only when something changes,
rests when the tab is hidden, and starts afresh by itself if the browser takes the graphics away.
Everything in the 3D view is also in the panel as a list, and reduced motion is respected.

## Licence

MIT: see `LICENSE`. Arnheim builds on House Control (MIT), Three.js (MIT) and Lucide icons (ISC);
their notices are in `THIRD_PARTY_NOTICES.md`.
