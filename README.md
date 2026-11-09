# Arnheim

![Fernhollow, the made-up sample company, as a building: four floors of projects above the lobby and the shared machines, rooms lit warm and amber, and the panel beside it listing what needs you and what is working now](docs/building.jpg)

A company as a building you can turn and walk through. Each project is a floor, each kind of work
is a room, a receptionist called Poe answers questions at the front desk, and the live work shows
as it happens: someone sits at a desk or in a chair while a thing is being worked on, and the rooms
glow warm while something is working, amber when something needs you, and dim when all is quiet.

It is for anyone who runs several projects, alone, with a team or with AI agents, and wants to see
at a glance what needs them and what is being worked on, and then ask about it, instead of reading
through lists. It shows the work and never does it: it reads plain files, or what your own page
gives it, and changes none of them.

It is named after Edgar Allan Poe's story "The Domain of Arnheim", about a man who shapes a
landscape into a world of its own. Arnheim is free and open, and never sold.

## What you need

- **Python 3.7 or newer.** Most Linux systems have it already. On a Mac, the first `python3` may
  offer to install Apple's command line tools, which bring it: say yes. The server is one file that
  uses nothing beyond Python itself, so there is nothing more to install.
- **A browser with WebGL 2**, which every current Chrome, Edge, Firefox and Safari has, on a
  computer, a tablet or a phone.

Everything the page uses is in this repository, Three.js included, so once it is cloned it needs no
internet. Only the voice, which is optional, downloads anything ("Voice", below).

Arnheim has been used on macOS, in Chrome and in Safari. It is plain Python and plain browser code,
so Linux and Windows should work too, but they have not been tried yet.

## Try it

Clone this repository, then in its folder:

```bash
python3 serve.py
```

Then open http://127.0.0.1:8740. (On Windows, `py serve.py`.) Ctrl-C stops it, and
`python3 serve.py 8741` uses another port.

It opens on Fernhollow, a company that is made up. Its people, projects, websites and numbers are
all invented, and the work you see moving is a short story on a loop. Tap a floor to bring it out,
a room to look inside, and Poe to ask a question. The Live button pauses the story.

## Walk through it

![Inside the walk: Poe behind the reception desk, under the sign with the company's name and mission](docs/walk.jpg)

Press Walk to step inside. You start at the door of the reception, with Poe behind the desk. On a
computer, walk with WASD or the arrow keys and drag to look around; on a phone, use the stick and
drag. Tap the floor to walk there, and tap a desk, a screen or Poe to open it. The lift at the end
of each floor takes you up and down: the floor you leave burns away into glowing points, and the
next one gathers out of them. Double-tap anywhere to burn the floor you are on and rebuild it.
With reduced motion on, the camera keeps still and floors change at once.

A ring of light lies on the floor beside each person at work, and in front of Poe's desk. Stand in
it and the walk knows who you mean: the ring brightens, a card names them, and the page opens what
they are working on, as if you had tapped it. Tap Poe herself and you walk onto her ring, round
anything in the way, and turn to face her.

At the top of the lift is the founder's office, a floor only the walk has, named after the founder
in the map ("Ellison's office" in the sample). It is one wide room under a high ceiling, with glass
on three sides and a dusk beyond. The lift opens onto a desk of pale oak that seems to float, with
two rings of light round a small sun behind it. A cloud of small lights hangs over the way in, with
a library on one side and a lounge on the other. Tap the desk to see whose it is.

If the map names the founder's assistant, she stands at a slim desk of her own on the left as you
step out of the lift, facing you, with a ring in front of her desk: tap her, or step in, to talk to
her as you would to Poe. In the sample she is Wren, made up, and answers as Poe does. A page with
its own answers can make her the one who knows everything (`talk`, under "Use it in your own page").

The founder's newest notes hang in the library there, up to eight cards of lit paper on threads in
front of the shelves, to the right as you step out of the lift. Each turns a little towards you as
you come near. Tap one, or stand in the pool of light in front of it, to read it in full; walk on or
press Esc to put it down. The page gives the notes and is asked for fresh ones whenever someone
walks into the office, so an edited note shows the next time you come up. The sample's notes are
made up.

Walking brings in real materials: photographed terrazzo, white oak and plaster, and the light of a
real entrance hall reflected in the glass, stone and metal. They are about 6 MB of free CC0
pictures from Poly Haven (see `THIRD_PARTY_NOTICES.md`). They load only once you press Walk, and
the walk opens on the finished rooms; if they take more than a couple of seconds, it opens with the
drawn look and a small bar until they arrive. The page itself never waits for them. A phone short of
memory, or a browser with data saver on, keeps the drawn materials; add `?lite` to the address to
see those anywhere. A server that shows Arnheim needs to send `.jpg` and `.hdr` files for them, as
`serve.py` does. The camera moves like a phone held in the hand: a little bob and sway as you walk,
light motion blur as you turn, softer corners and fine grain. Reduced motion turns all of that off.

## Talk with them

Stand in a ring and a conversation opens in the card: type a question and they answer there. Poe
answers from what the building holds, as at the desk. In the sample, the people at work answer from
lines written for them in `sample/work.json`, and say so: they are made up. A page with real agents
passes its own answers (`talk`, under "Use it in your own page"), and there what you say can reach
the agent doing the work.

If the computer that runs `serve.py` has the voice ("Voice", below), turn on Voice, beside Leave (a
microphone on a phone), and they say it aloud, each in a voice of their own, and listen for you
with no button to press: they hear you when you start talking and answer when you stop. While they
speak they don't listen, so they never hear themselves. The microphone is used only while the
voice is on and you stand in a ring, and what you say goes no further than that computer. Voice
stays off until you turn it on, and `?lite`, data saver and phones short of memory never use it.
Typing always works.

## Make it yours

Your own company goes in a folder called `data`, beside `sample`. Start from a copy of the sample:

```bash
mkdir data
cp sample/*.json data/
```

(On Windows: `mkdir data`, then `copy sample\*.json data`.)

Then, in `data/company.json`, take out the `"sample"` line, which marks a company as made up, and
put in your own: the company's name, a floor for each project, and their rooms. In
`data/work.json`, put what is going on, and empty the `story` at the end so that it reads
`"story": []`: the story only makes the sample move. Reload the page, and it shows your company. To start smaller,
[docs/data.md](docs/data.md) has a company with one floor that you can copy in whole.

- `company.json` is the map: the company's name and mission, its floors, the rooms on each floor,
  the lobby (Front of house), the basement (shared machines and the Library), the founder, whose
  office is at the top of the lift in the walk, and the founder's assistant, if they have one.
  Poe answers questions from the `about` line every floor and room has.
- `work.json` is what is going on: tasks, goals, conversations, pull requests, websites, machines
  and their jobs. Every part of it is optional.
- `notes.json` is the founder's notes, which hang in their office on a walk. Also optional.

[docs/data.md](docs/data.md) lists every field and the values each one takes. If `company.json`
or `work.json` has a mistake, the page says which file and what is wrong, and `serve.py` checks
when it starts that each file in `data/` is valid JSON.

The page shows `data/` whenever `data/company.json` is there, and the sample otherwise; add
`?sample` to the address to see the sample anyway. Git ignores `data/`, so your company's files
stay on your computer and never go into a commit.

## Connect it to Claude Code

Arnheim can follow your real work as it happens. Connect it to Claude Code, and each conversation
you have with Claude in one of your projects shows on that project's floor: someone sits in its
seat while Claude works, the floor turns amber when Claude needs your permission or an answer, and
a blue light shows when it has finished and it is your turn. Claude's task list, when it keeps
one, becomes desks, and on a walk you can stand at the conversation and ask how it's going: it
tells you the last thing Claude said. git and GitHub add each project's unsaved changes and open pull requests, and any
other tool that can write a small file can add its own.

It takes three steps, all in [docs/connect.md](docs/connect.md):

1. In `data/company.json`, give each floor its project's folder, and name the connectors' files
   as `feeds`.
2. Add Arnheim's hooks to Claude Code's settings, so Claude Code tells it what is happening.
3. For git and GitHub, run `python3 connect/projects.py --every 60` beside `serve.py`.

Everything stays on your computer, in `data/`, which git ignores.

## Voice

The people in the walk can speak and listen, with models that run on the computer that runs
`serve.py`. It is optional: without it, you type and read, and everything else is the same.

Kokoro speaks: an open text-to-speech model (82 million parameters, Apache 2.0). Whisper listens:
OpenAI's open speech recognition, its 145 MB `base.en` model (MIT). A phone or laptop that opens
the page downloads nothing but the sound. On a recent Mac each sentence takes about half a second
to make, and the next is made while the first plays; a short question takes Whisper about a sixth
of a second to hear.

The voice needs Python 3.10, 3.11 or 3.12, and about 1.2 GB of disk, most of it PyTorch. In
Arnheim's folder:

1. Give the voice a Python of its own, in a folder called `.voice`, with the two models' packages:

   ```bash
   python3.12 -m venv .voice
   .voice/bin/pip install kokoro openai-whisper
   ```

   To have them speak but not listen, leave out `openai-whisper`; you then type your side. On
   Linux, pip brings PyTorch with its graphics-card libraries, several GB more; to keep it small,
   run `.voice/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu` first.

2. Download the models, once. It is about 470 MB, so it can take a while, and it ends with a line
   that says `"ready": true`:

   ```bash
   ARNHEIM_VOICE_FETCH=1 .voice/bin/python -I voice/worker.py < /dev/null
   ```

   Kokoro's model and seven voices come from Hugging Face (`hexgrad/Kokoro-82M`) into its cache in
   your home folder (`~/.cache/huggingface`), and Whisper's model into `.voice/whisper`.

3. Start Arnheim as usual, with `python3 serve.py`. It finds the voice in `.voice` and fetches
   nothing more.

On a walk, turn on Voice. The first answer takes a few seconds while the voice wakes; after that
it is quick. The seven voices are `af_heart` (Poe's), `af_bella`, `af_nicole`, `am_michael`,
`am_fenrir`, `bf_emma` and `bm_george`. Each person at work gets one of the others, or an even mix
of two with the same accent, and keeps it; the assistant can be given one in `company.json`.
http://127.0.0.1:8740/voice/status says whether this computer can speak and, once the voice has
woken, whether it can listen, with the last error if something failed.

`ARNHEIM_VOICE_PYTHON` points at another Python that already has the packages. On Windows the
folder's Python is `.voice\Scripts\python.exe`, which `serve.py` looks for, but the voice has not
been tried on Windows yet.

## Phones

`serve.py` shows Arnheim to this computer only. To open it on a phone or tablet on the same Wi-Fi:

```bash
python3 serve.py --lan
```

It prints a second address, such as `http://192.168.1.20:8740`: open that on the phone. The first
time, the computer may ask whether Python may accept connections from the network: allow it. While
it runs like this, anyone on the same network can open Arnheim, your `data/` included, so use it
on a network you trust and stop it when you are done.

On the phone the people speak, if the computer has the voice, and you type your side: browsers only
let a page use the microphone over HTTPS, or on the computer it runs on, and `serve.py` doesn't do
HTTPS. A server of your own that does can serve Arnheim and its voice instead ("Use it in your own
page").

## Use it in your own page

The world knows nothing about the page around it. `index.html` and `src/demo.js` show the whole
contract:

- `createBuilding(canvas, map, options)` from `src/building.js` draws the company map
  (company.json) on a canvas. Its options:
  - `labels`: an element over the canvas, for the names that float over floors and rooms. Their
    look is the `.label` rules in `src/demo.css`, for your page to copy or restyle. The walk brings
    its own styles (`src/walk.css` and `src/notes.css`).
  - `onPick(hit)`: something was tapped. `hit.href` is what it opens, and `hit.floorId` and
    `hit.roomId` where it is.
  - `onHover(info, x, y)`: the pointer is over something (`info.title`, `info.sub`), or nothing.
  - `onStatus(status)`: the browser took the graphics away (`lost`) or gave back a blank picture
    (`blank`), so the page can start the building again, as `demo.js` does.
  - `onWalk(on)`: a walk started or ended.
  - `onNotes()`: someone walked into the founder's office, so the page can answer with fresh notes.
  - `talk`: lets people in the walk talk back (below).
- The building it gives back:
  - `setLive(model)` lights it: one plain object per room, keyed `floor/room`, plus `floor:<id>`
    for the line under each floor's name ([docs/data.md](docs/data.md), "The live model").
  - `setNotes(notes)` hangs the founder's newest notes in their office, each
    `{ id, title, text, when, pictures, locked }` in plain text. `onNotes` is called when someone
    walks into the office and every two minutes while they stay.
  - `setScene({ mode })` relights it: `all`, `needs` or `working`, or `{ mode: 'floor', floor }`
    for one floor.
  - `setTheme(dark)`, `focus({ floor, room, item })`, `highlight({ floor, room })`, `zoomBy(k)`,
    `turn(x, y)`, `resetView()`, `walk(on)` (a promise of whether it is walking now), `walking()`
    and `dispose()`.
- `createPoe(kit)` from `src/poe-desk.js` gives you Poe's desk. Poe answers by keyword matching over
  the facts you pass in, with no AI, and a page can teach Poe its own words and topics.
- `talk`, in `createBuilding`'s options, turns the rings into conversations (`src/voice.js` says
  more). Only `answer` is needed:
  - `answer(who, text, said)`: their reply to `text`: words, a promise of words, or a stream of
    them (an async iterable), spoken a sentence at a time as it comes.
  - `greet(who)`: what they say when you step up.
  - `name(who)`: a short name for them, for the captions.
  - `voice(who)`: which Kokoro voice is theirs.
  - `hear(sound)`: the page's own listening, such as the system's speech recognition in a desktop
    app. Given what was said as a WAV file (a Blob of 16-bit mono sound at 16 kHz), it resolves to
    the words. If it fails, the server listens.
  - `headers()`: headers for the voice server, such as a page token.
  - `base`: where the voice server is, if not `../voice/` beside `src`.

  `who` is the person: `{ title, href }`, where `href` is `#/poe` for Poe and otherwise what they
  are working on. Without `talk`, the rings only open what someone is working on.

The voice is a few requests under `/voice/`. `serve.py` answers them, and so can a server of your
own: `voice/bridge.py` is standard-library Python, with one call (`Voice.handle`) for all of them.

## If something is wrong

- **"Port 8740 is already in use"**: another copy of Arnheim, or another program, has that port.
  Stop it, or give another: `python3 serve.py 8741`.
- **The page says the company could not be shown**: it names the file and what is wrong, such as
  a missing comma and where. [docs/data.md](docs/data.md) has every field.
- **The sample shows, not your company**: the page looks for `data/company.json` in the folder
  that `serve.py` is in. Check the folder and file names, and that the address has no `?sample`.
  A "404" for `data/company.json` in the browser's console is the page looking for it, not a fault.
- **The building stays blank, or says it is not showing**: the browser has no WebGL 2, or has
  turned graphics off. Everything is still in the panel, and `?list` shows the panel alone.
- **It is slow on an older computer or phone**: `?lite` keeps the drawn materials and leaves the
  voice off.
- **The voice doesn't start**: http://127.0.0.1:8740/voice/status says what it found and the last
  error. Check the steps under "Voice", and that the models were downloaded (step 2).
- **A phone can't open it**: start it with `--lan`, use the second address it prints, and check
  the phone is on the same Wi-Fi. Some networks, such as guest Wi-Fi, keep devices apart.

The address takes these too: `?live=off` starts with the story paused, `?theme=light` or
`?theme=dark` picks the look, and `?scene=needs`, `?scene=working` or `?scene=` and a floor's `id`
lights only part of the building.

## How it is made

Plain ES modules and Three.js, with no build step. The building draws only when something changes,
rests when the tab is hidden, and starts afresh by itself if the browser takes the graphics away.
Everything in the 3D view is also in the panel as a list, and reduced motion is respected.

To help, see [CONTRIBUTING.md](CONTRIBUTING.md). The tests are standard-library Python:
`python3 -m unittest discover tests`.

## Licence

MIT: see `LICENSE`. Arnheim builds on [House Control](https://github.com/0xProbabillity/house-control)
(MIT), Three.js (MIT) and Lucide icons (ISC), and its photographed materials are CC0, from Poly
Haven. Their notices are in `THIRD_PARTY_NOTICES.md`.
