# Connect it to your work

Arnheim can follow your real work as it happens. Connect it to Claude Code, and each conversation
you have with Claude in one of your projects shows on that project's floor. Connect it to git and
GitHub, and each project's unsaved changes and open pull requests show in its Code room. Anything
else that can write a small file can join in too.

Everything stays on your computer. The connectors write into `data/feeds/`, inside the `data/`
folder that git ignores, and the page reads them from there every few seconds, so the building
follows along without a reload.

## What you will see

- **A seat for each Claude Code conversation**, in the project's Conversations room, named after
  the conversation, or after the first line of your first message.
- **Someone in the seat while Claude works**, and the room lit warm.
- **An amber desk when Claude needs you**: when it asks for your permission or asks you something,
  a desk in the Work room says what it is waiting for, the floor says "Needs you", and the receptionist lists it
  when you ask what needs you. It goes as soon as you answer.
- **A blue light when Claude has finished** and it is your turn, until you reply.
- **Claude's task list as desks**: one for each task, someone at it while it is being done. Finished
  tasks leave. Newer Claude models keep no written task list unless you ask for one: start Claude
  Code with `CLAUDE_CODE_ENABLE_TODO_TOOLS=1 claude` to have it keep one.
- **The conversation talks**: on a walk, stand at its ring and ask how it's going, and it answers
  with the first sentences of the last thing Claude said. What you say in the walk doesn't reach
  Claude: the page only shows.
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

## What is kept, and where

The connectors write `data/feeds/claude-code.json` and `data/feeds/projects.json`. From Claude Code
they keep, for each conversation: its title, or the first line of your first message; the first
words of your latest message; the first sentences of the last thing Claude said; what it asks you
for; and its task titles. Nothing else from the conversation is kept, and nothing leaves this
computer, unless you serve Arnheim with `--lan`, when anyone on your network can open it.

A conversation leaves the building when it ends, or after twelve hours with no word from it.
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
