# Connect it to your work

Arnheim can follow your real work as it happens. Connect it to Claude Code, and each conversation
you have with Claude in one of your projects shows on that project's floor. Switch on control, and
you can talk to those agents for real, answer their permission requests, and start and stop them
from the building. Connect it to git and GitHub, and each project's unsaved changes and open pull
requests show in its Code room. Anything else that can write a small file can join in too.

Everything stays on your computer. The connectors write into `data/feeds/`, inside the `data/`
folder that git ignores, and the page reads them from there every few seconds, so the building
follows along without a reload.

## What you will see

- **A seat for each Claude Code conversation**, in the project's Conversations room, named after
  the conversation, or after the first line of your first message.
- **Someone in the seat while Claude works**, and the room lit warm. They stay seated while it
  waits for you.
- **An amber desk when Claude needs you**: when it asks for your permission or asks you something,
  a desk in the Work room says what it is waiting for, the floor says "Needs you", and the receptionist lists it
  when you ask what needs you. It goes as soon as you answer.
- **A blue light when Claude has finished** and it is your turn, until you reply.
- **Claude's task list as desks**: one for each task, someone at it while it is being done. Finished
  tasks leave. Newer Claude models keep no written task list unless you ask for one: start Claude
  Code with `CLAUDE_CODE_ENABLE_TODO_TOOLS=1 claude` to have it keep one.
- **The conversation talks**: on a walk, stand at its ring and ask how it's going, and it answers
  with the first sentences of the last thing Claude said. Unless control is on (step 4), what you
  say there doesn't reach Claude: the page only shows.
- **From git**: a crate in the Code room when a project has changes not yet committed, with how
  many. **From GitHub**: a book for each open pull request.

## 1. Tell Arnheim where each project lives

Start with your own company in `data/` (README, "Make it yours"). Then, in `data/company.json`,
give each floor the folder its project is in, give it the rooms these things show in
(Conversations, Work and Code), and add the connectors' two files as `feeds`:

```json
{
  "company": "Example Studio",
  "feeds": ["feeds/claude-code.json", "feeds/projects.json"],
  "rooms": [
    { "id": "work", "label": "Work", "about": "Tasks, and what Claude is waiting on you for." },
    { "id": "conversations", "label": "Conversations", "about": "Claude Code conversations." },
    { "id": "code", "label": "Code", "about": "Unsaved changes and open pull requests." }
  ],
  "floors": [
    { "id": "lantern", "label": "Lantern", "folder": "~/code/lantern" },
    { "id": "tidepool", "label": "Tidepool", "folders": ["~/code/tidepool-app", "~/code/tidepool-kit"] }
  ]
}
```

A conversation belongs to a floor when it runs in that floor's folder or in any folder inside it.
`~` is your home folder. Work in folders that no floor names is left out, so nothing else shows.
Reload the page after changing `company.json`.

## 2. Connect Claude Code

Claude Code can run a command at set moments in a conversation: when it starts, when you send a
message, after Claude uses a tool, when it needs you, when it finishes, when a task is made or done,
and when it ends. These are its hooks. Add Arnheim's to Claude Code's settings: in
`~/.claude/settings.json` for every project on this computer, or in a project's own
`.claude/settings.json` for that project alone. Put the path to your copy of Arnheim where it says
`/path/to/arnheim`:

```json
{
  "hooks": {
    "SessionStart": [{ "hooks": [{ "type": "command", "command": "python3 /path/to/arnheim/connect/claude_code.py" }] }],
    "UserPromptSubmit": [{ "hooks": [{ "type": "command", "command": "python3 /path/to/arnheim/connect/claude_code.py" }] }],
    "PostToolUse": [{ "hooks": [{ "type": "command", "command": "python3 /path/to/arnheim/connect/claude_code.py" }] }],
    "Notification": [{ "hooks": [{ "type": "command", "command": "python3 /path/to/arnheim/connect/claude_code.py" }] }],
    "Stop": [{ "hooks": [{ "type": "command", "command": "python3 /path/to/arnheim/connect/claude_code.py" }] }],
    "TaskCreated": [{ "hooks": [{ "type": "command", "command": "python3 /path/to/arnheim/connect/claude_code.py" }] }],
    "TaskCompleted": [{ "hooks": [{ "type": "command", "command": "python3 /path/to/arnheim/connect/claude_code.py" }] }],
    "SessionEnd": [{ "hooks": [{ "type": "command", "command": "python3 /path/to/arnheim/connect/claude_code.py" }] }]
  }
}
```

If your settings file already has `"hooks"`, add these beside the ones there; if it has other
settings, keep them. Put the path in quotes inside the command if it has spaces, and on Windows
write `python` instead of `python3`. In Claude Code, `/hooks` shows what is set up.

The next conversation you start in one of the floors' folders appears in the building. The
connector prints nothing and always lets Claude carry on; each time it runs takes a few hundredths
of a second, the time Python takes to start.

To try it without Claude, hand it a moment yourself, with a folder one of your floors names:

```bash
echo '{"hook_event_name": "UserPromptSubmit", "session_id": "try", "cwd": "/path/to/a/project", "prompt": "Hello"}' | python3 connect/claude_code.py
```

A seat called "Hello" appears, with someone in it. This takes it away again:

```bash
echo '{"hook_event_name": "SessionEnd", "session_id": "try", "cwd": "/path/to/a/project"}' | python3 connect/claude_code.py
```

## 3. Connect git and GitHub

In a terminal beside `serve.py`, in Arnheim's folder:

```bash
python3 connect/projects.py --every 60
```

Every minute it counts each floor folder's changes that are not yet committed and, if GitHub's
`gh` command is installed and signed in, lists the folder's open pull requests. It only reads, and
never changes a repository. `--no-github` leaves out pull requests, and without `--every` it looks
once.

## 4. Control your agents from the building

Optional, and off unless you switch it on. Then the person at this computer can:

- **Talk to an agent.** What you type or say in its ring on a walk, or send from its page in the
  panel, reaches its Claude Code conversation at its next step, and its answer comes back to you.
  An agent waiting for you in Claude Code sees it the next time you send it something there.
- **Answer its permission requests.** When it asks to run a command or change a file, the request
  shows on its card in the walk and on its page in the panel, with Allow and Deny. In its ring you
  can also say "allow" or "deny". An answer is for that one request only. A request waits in the
  building only while you are using it (walking, or you touched it in the last two minutes), and for
  two minutes at most. Otherwise Claude Code asks as it always does.
- **See everything waiting on you in one list.** The Overview's "Waiting on you" puts together every
  agent's permission requests (the one whose wait runs out first at the top), the questions agents
  stopped to ask, your own tasks marked as needing you, and agents that finished in the last two
  hours and wait for your next step. Each has its answer beside it: Allow and Deny, or a box to reply.
  When two or more requests only read or search, "Allow all" answers them together. Ask the
  receptionist "what's waiting on me?" to hear it, and say "allow all the reads" to let those go
  ahead. Commands and changes are never allowed together: each needs its own answer.
- **Stop it.** Stop on its card, or say "stop": it stops at its next step.
- **Start one.** In a floor's Conversations room, or by asking the receptionist ("start an agent on
  Lantern to fix the login page", then "start it"). It runs in the floor's folder with your own
  Claude Code settings, as if you had started it there, and stays in the building to talk to.
- **Pass something on through your assistant.** With the brain on too ([brain.md](brain.md)), ask
  your assistant to tell an agent at work something, and it reaches that agent as a message from the
  building does.

To switch it on, connect Claude Code (step 2) and add one more hook beside those, for permission
requests. It waits for your answer, so it gets a longer time limit:

```json
"PermissionRequest": [{ "hooks": [{ "type": "command", "command": "python3 /path/to/arnheim/connect/claude_code.py", "timeout": 150 }] }]
```

Then start Arnheim with `--control`:

```bash
python3 serve.py --control
```

Control answers only the page on the computer that runs `serve.py`, with the token that page is
given, and never works with `--lan`. Starting agents needs Claude Code's `claude` command
(`ARNHEIM_CLAUDE` names another). `ARNHEIM_CONTROL_WAIT` sets how long a permission request waits
for an answer in the building, in seconds: keep the hook's `timeout` above it.

## 5. Done means proven

An agent saying it has finished isn't proof that its work holds up. Give a floor a check, the
command that shows its work is sound (its tests, say), and Arnheim runs it for you each time an agent
on that floor finishes a turn in which it changed files:

```json
{ "id": "lantern", "label": "Lantern", "folder": "~/code/lantern",
  "check": { "run": ["npm", "test"], "label": "The tests", "timeout": 600 } }
```

`run` is the command and its arguments, one to a string. It runs in the floor's folder (or in
`folder`, if the check names one), with no shell, as you, and is stopped after `timeout` seconds (ten
minutes if left out). `label` is what the building calls it. `"check": ["npm", "test"]` is enough.

Then each conversation that changed files says, in its seat's lamp, its room's light and its page in
the panel, which of these is true:

- **Proven**: the check passed after its last change. Its lamp turns green, and the room does too once
  everything finished there is proven.
- **Not proven**: the check failed, ran too long, or couldn't start. The lamp and the room turn red,
  and its page shows the check's last lines.
- **Claimed**: it changed files and nothing has checked them since, perhaps because the floor has no
  check, or it changed more while the check ran.

The check runs in the background, so Claude Code never waits for it, and one runs per floor at a
time: turns that end meanwhile get one more run when it ends. Arnheim only notices changes made with
Claude Code's own tools for editing files. With control on, "Check it again" on a conversation's page
runs it once more. It needs only step 2's hooks.

## 6. Company memory

Every agent should know what you have already decided, without being told again in each
conversation. Tell the receptionist, by typing or out loud:

> Remember that we never push on a Friday.

("Remember: ...", "from now on, ..." and "going forward, ..." work too.) Or type it under "What every
agent is told" in the Company tab, where Forget takes one out again. Saving needs control on (step 4).
The decisions are kept in `data/memory.json`, which you can also edit by hand:

```json
{ "memory": [{ "id": "m-1", "text": "We never push on a Friday." }] }
```

Then, through the hooks of step 2:

- **Every conversation in the company's folders is told them as it starts**, and again if its
  context is compacted. Conversations in other folders are told nothing.
- **One already at work is told decisions made since**, with the next message you send it.
- **When an agent asks you something you've decided before**, the list of what waits on you shows
  your decision under its question, with "Send it that". Arnheim matches the words of the question
  with your decisions, so it only suggests: nothing is sent until you press it.

Ask the receptionist "what have we decided?" to hear the memory. With the brain on, they know it too.

## 7. A budget per floor, and pausing everyone

Arnheim counts what each conversation spends each day, from Claude Code's own record of it: the new
tokens of each reply, that is what Claude read fresh, wrote to its cache, and wrote back. Re-reading
its cache is left out, since that is the same context again, and so is the work of its sub-agents.
The Overview shows each floor's total for today under "Spent today", and each floor's page says it too.

Give a floor a budget for a day, in new tokens, or give the company one for every floor:

```json
{ "company": "Example Studio", "budget": 3000000,
  "floors": [{ "id": "lantern", "label": "Lantern", "folder": "~/code/lantern", "budget": 1000000 }] }
```

When a floor's agents pass it, the one at work stops at its next step, and the list of what waits on
you asks whether they may go on. **Let them go on** (with control on) gives them as much again, for
today; or leave them, and the budget starts afresh tomorrow. Each conversation is stopped once for each
limit it passes, so if you carry on with it in Claude Code yourself, it lets you.

With control on, **Pause everyone** on the Overview, or in the lobby, stops every agent in the
company's folders at its next step, and a message you send one in Claude Code waits until you
**Resume everyone**. Nothing is ever stopped in the middle of a step, and a message you send from the
building is always handed over first.

## What is kept, and where

The connectors write `data/feeds/claude-code.json` and `data/feeds/projects.json`. From Claude Code
they keep, for each conversation: its title, or the first line of your first message; the first
words of your latest message; the first sentences of the last thing Claude said; what it asks you
for; and its task titles. Nothing else from the conversation is kept, and nothing leaves this
computer, unless you serve Arnheim with `--lan`, when anyone on your network can open it.

A floor's check keeps the last lines it printed beside each conversation it checked, and a lock and
a note for its next run in `data/feeds/proof/`. The company's memory is `data/memory.json`, and the
feed notes when each conversation was last told it. For the budget, the feed keeps each conversation's
new tokens for today and how far its transcript has been read; `data/control/` keeps a pause, and how
far each floor was let go past its budget today.

With control on, your messages wait in `data/control/` until Claude takes them, a permission
request and its answer are deleted once it is answered, and each agent started from the building
keeps its last words there.

A conversation leaves the building when it ends, or after twelve hours with no word from it. One
started from the building stays until then, to talk to.
Delete the files to start afresh. If the Claude Code connector meets any trouble, it writes it to
`data/feeds/claude-code.log` and lets Claude carry on.

## Anything else

Any tool can add to the building. Have it write a JSON file with any of `work.json`'s lists in it
([docs/data.md](data.md)) into `data/feeds/`, and add the file's path to `feeds` in
`company.json`. The page adds its lists to `work.json`'s, and reads it again every few seconds.
Write the whole file at once, as a new file renamed over the old one, so the page never reads half
of it.

A nightly build that shows on a machine in the basement (a basement room whose `id` is `build`),
in Python:

```python
import json, os

feed = {"jobs": [{"id": "nightly", "name": "Nightly build", "machine": "build", "state": "running"}]}
with open("data/feeds/builds.json.part", "w") as out:
    json.dump(feed, out)
os.replace("data/feeds/builds.json.part", "data/feeds/builds.json")
```

Other ideas: an issue tracker's open issues as tasks, a deploy pipeline's runs as jobs, your
websites' up-checks as `presence`. Give each item an `id` of its own, and a `project` that names a
floor.

## If nothing shows

- Feeds are read only for your own company in `data/`, not the sample, and only those named in
  `feeds`. Reload the page after changing `company.json`.
- A conversation shows only when it runs in a floor's folder, and only on a floor with a
  Conversations room. Check the folder in `company.json`.
- Try the connector by hand (above), and look in `data/feeds/claude-code.json`.
- `data/feeds/claude-code.log` says what went wrong, if anything did.
- `python3 connect/projects.py` without `--every` says what it found, and why a folder was left out.
