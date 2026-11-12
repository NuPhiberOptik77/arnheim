# Your company's files

Arnheim draws a company from three JSON files. The made-up sample is in `sample/`. Yours goes in a
folder called `data/` beside it. Git ignores `data/`, so your company's files never go into a
commit by mistake. When `data/company.json` is there, the page shows your company; otherwise it
shows the sample. Add `?sample` to the address to see the sample anyway.

- `company.json` is the map: the floors, their rooms, and who is who. It is the only file you need.
- `work.json` is what is going on: tasks, goals, conversations and the rest. Every list in it is
  optional, and so is the file itself: without it the building stands quiet.
- `notes.json` is the founder's notes, which hang in their office on a walk. Also optional.

Change a file and the page follows: for your own company it reads `work.json` again every few
seconds, so the building changes without a reload; after changing `company.json`, reload. If
`company.json` or `work.json` has a mistake, the page says which file and why, and `serve.py` says
when it starts if any file in `data/` is not valid JSON, with the line and column.

## A company with one floor

The smallest company there is. Put this in `data/company.json`:

```json
{
  "company": "Example Bakery",
  "mission": "Good bread, early",
  "about": "A small bakery with one project, here as an example.",
  "founder": { "name": "Rowan", "title": "founder" },
  "rooms": [
    { "id": "goals", "label": "Goals", "about": "What the shop is working toward." },
    { "id": "work", "label": "Work", "about": "The shop's tasks, a desk each." }
  ],
  "floors": [
    { "id": "shop", "label": "Shop", "about": "The shop, its ovens and its website." }
  ]
}
```

And this in `data/work.json`:

```json
{
  "tasks": [
    { "id": "t1", "project": "Shop", "title": "Bake a test loaf", "status": "working" },
    { "id": "t2", "project": "Shop", "title": "Choose a flour supplier", "status": "needs_you", "note": "Two quotes are in." }
  ],
  "goals": [
    { "id": "g1", "project": "Shop", "title": "Open on Saturdays", "status": "open" }
  ]
}
```

Reload, and the Shop floor has a Goals room with a red flag in it and a Work room with two desks:
one glows amber because the flour supplier needs you, and someone sits at the other while the test
loaf is baked. Ask the receptionist "what needs me?" and they name the flour supplier.

From there, add floors, a lobby and a basement, more rooms and more lists, as below. The sample's
own files show every one of them in use.

## company.json

| Field | | What it is |
| --- | --- | --- |
| `company` | needed | The company's name: on the building's sign, in the panel and in the receptionist's answers. |
| `mission` | | A few words, on the sign under the name. The receptionist quotes it. |
| `about` | | A sentence about the company, for the panel and the receptionist. |
| `founder` | | `{ "name": "...", "title": "..." }`. The receptionist says "*name* is *company*'s *title*", so a title reads like `founder`. The top of the lift, on a walk, is their office, named with their first name (or `firstName`, if the first word of `name` isn't it). |
| `receptionist` | | Who stands at the front desk: their name, look and voice (below). |
| `assistant` | | Someone who works in the founder's office and talks as the receptionist does (below). |
| `rooms` | needed, unless every floor lists its own | The rooms each floor has, in order. |
| `floors` | needed | One floor for each project, the top floor first. |
| `lobby` | | The ground floor, Front of house: websites, email, social media and domains, with the receptionist at the front desk. Without it, the receptionist has no desk in the building, though their tab still answers. |
| `basement` | | The machines every project shares, and the Library. |
| `feeds` | | Files in `data/` that tools keep up to date, such as `["feeds/claude-code.json"]`. The page adds their lists to `work.json`'s and reads them every few seconds ([docs/connect.md](connect.md)). |
| `quote` | | Words the company lives by, painted in a script hand on the long wall of each project floor's corridor in the photo-real building: `{"text": "...", "by": "who said them"}`. |
| `sample` | only for a made-up company | A sentence saying the company is made up. While it is there, the page says "made up" wherever it shows the company. Leave it out for a real one. |

### A floor (and the lobby, and the basement)

| Field | | What it is |
| --- | --- | --- |
| `id` | needed | Letters, numbers, dashes or underscores. Links use it, as in `#/shop/work`. |
| `label` | needed | Its name. |
| `project` | | The name `work.json` gives this floor's things in their `project`. Its `label` if left out. |
| `about` | | A sentence about it. The receptionist says it when asked about the floor. |
| `story` | | A longer line about it, in the panel and in the receptionist's answer. |
| `palette` | | Its colours: `terracotta`, `harbour`, `sage`, `indigo`, `plum`, `teal`, `sand` or `slate`. If left out, floors take the first six in turn, the lobby is `sand` and the basement `slate`. |
| `icon` | | The panel's picture for it: one of the names in `src/icons.js`, such as `building-2`, `library`, `gauge`, `shapes`, `globe`, `server` or `heart-pulse`. |
| `rooms` | | This floor's own rooms, in place of the company's `rooms`. |
| `extraRooms` | | More rooms, after the company's `rooms`, on this floor only. |
| `folder` | | The folder this project is in on your computer, such as `"~/code/lantern"`, or `folders` for several. The connectors use it to know which floor work belongs to ([docs/connect.md](connect.md)). |
| `budget` | | What this floor's agents may spend in a day, in new tokens, such as `2000000`. The company can give every floor one with its own `budget`. When they pass it, the one at work stops at its next step and you are asked ([docs/connect.md](connect.md), "A budget per floor"). |
| `check` | | The command that shows this project's work is sound, such as `["npm", "test"]`, or `{"run": [...], "label": "The tests", "timeout": 600}`. Arnheim runs it after an agent changes files here, and shows the work as proven or not ([docs/connect.md](connect.md), "Done means proven"). |
| `routines` | | Jobs that run on a schedule: `[{"id": "outdated", "label": "Outdated packages", "every": "monday", "at": "09:00", "run": ["npm", "outdated"]}]`, or `"ask": "..."` for a job for a new agent instead of `run` ([docs/connect.md](connect.md), "Routines"). |
| `review` | | `true` to check every change before it reaches you: the floor's `check`, then a second Claude Code that reads what changed. Work that isn't ready goes back to the agent with the reason. Or `{"read": false, "times": 2, "timeout": 300}` to leave the reader out, set how often work can be sent back, and the reader's time limit ([docs/connect.md](connect.md), "A review line"). |

A floor holds up to five rooms. The fifth carries the back row on to the right, so no other room
gets smaller.

### A room

| Field | | What it is |
| --- | --- | --- |
| `id` | needed | Letters, numbers, dashes or underscores. It also says what kind of room it is, unless `kind` does. |
| `label` | needed | Its name. |
| `about` | | A sentence about it, for the receptionist. |
| `kind` | | What stands in it, if not what its `id` says: one of the kinds below. A room of no kind Arnheim knows is a lounge. |
| `order` | | A number for where it goes on the floor plan, lowest first. Goals, Code, Conversations and Work go in that order otherwise. |
| `words` | | Other names the receptionist knows it by, such as `["build server", "build machine"]`. |

| Kind | On | What stands in it, from work.json |
| --- | --- | --- |
| `goals` | a floor | A flag for each of the floor's goals: red while open, gold once reached. |
| `work` | a floor | A desk for each open task. It glows amber when the task needs you, and someone sits at it while it is being worked on. |
| `conversations` | a floor | A seat for each conversation. Someone sits in it while it is working, and a light shows when there is something to check: blue, or green when its work is proven, red when its check failed. |
| `code` | a floor | Open pull requests as books, and copies of the code with unsaved changes as crates. |
| `company` | a floor | A filing cabinet each for Money, Legal, Subscriptions and Key dates. |
| `websites`, `email`, `social`, `domains` | the lobby | A screen, pigeonhole, signboard or brass plaque for each entry in `presence` of that type. |
| `machine` | the basement | A machine and its jobs. Every basement room is a machine unless its `id` is `library`. |
| `library` | the basement | Shelves of the `library` list. |
| `lounge` | anywhere | Somewhere to sit. |

### The receptionist and the assistant

The receptionist stands at the front desk, and the assistant at their own desk in the founder's
office. Name them, choose how they look and give them a voice. Without `receptionist`, the desk
still has a receptionist, with no name; without `assistant`, the office has no assistant.

```json
"receptionist": { "name": "Iris", "voice": "af_heart", "look": { "skin": "#a26b48", "hair": "#2b1d18", "coat": "#5b3b5e" } },
"assistant": { "name": "Wren", "title": "Your assistant", "voice": "bf_emma", "look": { "style": "bun", "hair": "#5a3926" } }
```

| Field | | What it is |
| --- | --- | --- |
| `name` | needed for the assistant | Their name, on their label and on the card when you step up. |
| `title` | | A few words under the name. `Receptionist` or `Assistant` if left out. |
| `look` | | How they look (below). Anything left out is as the default receptionist. |
| `voice` | | A Kokoro voice (README, "Voice"), used if the computer has it. |
| `href` | | Only for a page with its own routes: what tapping them opens. Arnheim's own page uses `#/front-desk` and `#/assistant`, so leave it out there. |

In `look`, colours are hex, like `"#a8752b"`: `skin`, `hair`, `lips`, `coat`, `shirt`,
`trousers`, and `accent` for the buttons and pocket square. `style` is `braids` (a centre parting
and a braid each side, with `ties` and `clips` colours) or `bun`, or the default swept cut if left out.
`collar: "round"` makes the coat a cardigan buttoned to the neck with a rounded collar, and
`brooch` pins a flower on it: one colour, or `[petals, centre]`. `earrings` is `studs` or `hoops`,
in the colour `gold` (the accent if left out). `pocket: false` leaves out the pocket square, and
`face: "round"` gives a rounder face with larger eyes.

## work.json

Every list is optional. Each thing's `project` is the `project` of the floor it belongs on (or that
floor's `label`), and each `id` is unique within its list.

| List | Each entry |
| --- | --- |
| `tasks` | `id`, `project`, `title` and `status`, which is `needs_you`, `working`, `waiting`, `open`, `done` or `dropped`. Done and dropped tasks leave the building. Optionally a `note`, and `says` (below). |
| `goals` | `id`, `project`, `title` and `status`: `open` or `reached`. |
| `conversations` | `id`, `project` and `title`. Optionally `working: true` while it is working, `check: true` when there is something to look at, `says`, and `changed` and `proof`: when it last changed files, and what its floor's check made of them, such as `{"state": "passed", "check": "The tests"}` (state `passed`, `failed`, `timeout`, `error` or `checking`, and `tail`, the check's last lines). `spent`: what it spent today, `{"day": "2026-11-12", "tokens": 900000}` (with no `day`, today). `review`: what the floor's review line made of its work, such as `{"state": "passed", "by": "The reader", "said": "..."}` (state `reviewing`, `passed`, `sent back`, `failed` once sent back as often as allowed, or `error`; `why`, the reason it was sent back; `times`, how often it was). |
| `pullRequests` | `number`, `project` and `title`, and `draft: true` for a draft. |
| `copies` | `id`, `project`, `name`, and `changes`: how many changes are not saved yet. |
| `company` | `id`, `section` (`Money`, `Legal`, `Subscriptions` or `Key dates`) and `name`. Optionally a `note`. |
| `presence` | `id`, `type` (`website`, `email`, `social` or `domain`), `name`, `project`, and `status` in your own words, where `Live` lights it up. Optionally `link`, and `up`: `true` if the link answered when last checked, `false` if not. |
| `machines` | `id`, the `id` of a room in the basement, and `online`: `true` or `false`. |
| `jobs` | `id`, `name`, `machine` (a basement room's `id`) and `state`: `queued`, `running` or `done`. |
| `routines` | Written by connect/routines.py (docs/connect.md, "Routines"): `id`, `project`, `label`, `when` (its schedule in words), `kind` (`command` or `agent`), `next`, and `last`: `{"state": "all clear", "at": ..., "tail": ...}` (state `starting`, `running`, `all clear`, `needs you`, `failed`, `timeout` or `error`). |
| `library` | `id`, `name`, and `status` in your own words. The sample uses Using, Copied from, Considered, Dropped and Not looked at. |

`says` is what the person at a desk or in a seat answers when you talk to them on a walk, with no
AI: `{ "now": "...", "next": "...", "when": "...", "needs": "..." }`, each a sentence or two. `now`
is what they are doing, `next` what comes after, `when` how long it will take, and `needs` whether
they need you.

The sample also has a `story`, so that something always moves: a list of steps, played in a loop,
one every `every` seconds (6 if left out, and at least 2). Each step is
`{ "line": "What happened", "change": [["tasks", "t1", { "status": "done" }]] }`, where each change
names a list, an `id` in it and the fields to change. A real company leaves it out or empties it
(`"story": []`), and the Live button, which pauses the story, only shows when there is one.

## notes.json

`{ "notes": [ ... ] }`. The newest eight hang in the founder's office on a walk.

| Field | | What it is |
| --- | --- | --- |
| `id` | needed | Unique among the notes. |
| `title` | | The note's title. Its first line if left out. |
| `text` | | Plain text, with a blank line between paragraphs. |
| `when` | | When it last changed: a date and time like `"2026-11-08T09:30"`, or milliseconds since 1970. The sample gives `hoursAgo` instead, counted back from when the page opened. |
| `pictures` | | How many pictures or files it holds that the card doesn't show. |
| `locked` | | `true` for a locked note: its card shows no text. |

## The live model, for your own page

A page that draws the building itself (README, "Use it in your own page") lights it with
`building.setLive(model)`. `src/demo.js` makes this model from `work.json` in `roomModel()`, which
is the fullest example. One plain object, keyed:

- `"floor:<floor id>"`: `{ "lines": [{ "text", "kind" }] }`, the lines under the floor's name, where
  `kind` is one of the states below.
- `"<floor id>/<room id>"`: one room, as in this table.

| Field | What it is |
| --- | --- |
| `state` | The room's light: `quiet`, `working` (warm), `needs` (amber), `check` (blue) or `failed` (red). |
| `big`, `detail` | The number and words on its label, such as `3` and `open, 1 needs you`. |
| `sub` | Words for its label in place of `big` and `detail`. |
| `working` | `true` while something in it is working, for the Working now scene. |
| `items` | What stands in it: `{ id, title, sub, href, mood }` each, where `mood` is a state. A goal adds `reached: true` once reached; a conversation `working` or `check`; a lobby entry `up` or `live`. |
| `prs`, `copies` | A Code room's books (`{ id, title, sub, href, draft }`) and crates (`{ id, title, sub, href }`). |
| `sections` | A Company room's cabinets: `{ id, title, sub, href, count }`. |
| `running`, `online` | A machine room's running jobs (a number) and whether it is on. |

`href` is what opens when someone taps the thing: the building hands it to your page's `onPick`.
