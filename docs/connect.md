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
  When two or more requests only read a file, "Allow all" answers them together. Ask the
  receptionist "what's waiting on me?" to hear it, and say "allow all the reads" to let those go
  ahead. Commands, changes, searches and reads of anything that looks like a key, a password, a token
  or a credentials file are never allowed together: each needs its own answer.
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
company's folders at its next step, and a message you send one in Claude Code is turned away with a
note saying so: send it again after you **Resume everyone**. Nothing is ever stopped in the middle of a step, and a message you send from the
building is always handed over first.

## 8. Replay the day, ask its history, and the week

When something went wrong, or you were away, drag the slider under "Replay the day" on the Overview
back through today. The building shows who was at work at that moment, who was waiting on you and who
had finished, with a banner saying which time you are looking at, and the list beside it shows the
last moments before then: when each conversation started work, which files it changed, what it asked
you and what it said when it finished. Tap a moment to read that conversation, or press Back to now.

It needs only step 2's hooks. A file changed inside a floor's folder is named by its path there; one
outside it, by its name alone.

The building keeps a week of these days, and you can ask about them. Ask the receptionist **"What
happened yesterday?"**, **"What did the agents do on Tuesday?"**, **"What happened on Lantern this
week?"** or **"Who changed reader/bookmark.js?"**, and they answer from the moments.

**This week**, on the Overview, is the weekly report: each floor's conversations, the instructions you
gave, the files they changed, how many finished or stopped, how long they waited on you, and what they
spent. **Copy the report** copies it as plain text, for a message or a document. Ask **"How was the
week?"** to hear it summed up.

**How long things wait on you**: each line under "Waiting on you" says how long it has waited, and a
meter fills as the longest an agent has been held up grows, amber past five minutes and red past
fifteen. Under it, how long agents waited on you today in all. A wait starts when an agent asks you
for a permission or an answer, and ends when it goes on. Ask **"How long have the agents waited on
me?"** for the same in words.

## 9. Any agent, not just Claude Code

Other agents can sit in the building too, in the same rooms, the same list of what waits on you and
the same replay. Add their feed to `data/company.json`'s `feeds`, beside Claude Code's:

```json
"feeds": ["feeds/claude-code.json", "feeds/agents.json", "feeds/projects.json"]
```

**OpenAI's Codex CLI** runs a program when it finishes a turn. In `~/.codex/config.toml`:

```toml
notify = ["python3", "/path/to/arnheim/connect/codex.py"]
```

Each Codex conversation in a floor's folder then shows on that floor when a turn ends, finished and
waiting for your next step. Codex says nothing while it works, so the building doesn't see it at work.

**Any other agent, script or tool** can say where it is with one command, from its own hooks or
wrapper, each time something changes:

```bash
python3 connect/agents.py --agent Gemini --session 42 --cwd ~/code/lantern --state working --says "Fixing the login"
```

`--state` is `working`, `asking` (it shows in the list of what waits on you), `finished` or `ended`.
`--session` is the conversation's own id, the same each time. The building names the agent on each
conversation. Answering, stopping and starting work from the building (step 4) is for Claude Code
alone, since only it lets another program hand it words.

## 10. Collision warnings

Two agents changing the same file can undo each other's work. When a conversation changes a file that
another conversation on the same floor changed in the last two hours, Arnheim tells it at once, with the
other's name, so it looks at their work before going on. The Overview lists the pair under "Two agents
on the same files", and the floor says so. With control on, "Make ... wait" tells either one to wait
until the other has finished. It needs only step 2's hooks, and sees changes made with Claude Code's
own tools for editing files.

## 11. Hand out work by talking

With control on (step 4), tell the receptionist what you want done, in everyday words: "get someone to
fix the login bug on Lantern", "have an agent on Tidepool tidy the tests", "ask Claude to write the
release notes". If you don't name a floor, they ask which. They tell you what they will start, and it
starts when you say "start it" (or tap Start). It works the same on a walk and in the panel's chat.

The new agent is a Claude Code conversation in the floor's folder, with your own settings. It is
given a brief: the job, that it was started from the building by the person it works for, the
company's memory (step 6), and, on a floor with a check (step 5), that the check must pass for the
work to count as done. From the panel, the building turns to the Conversations room where it sits
down.

## 12. A review line

A floor can say that every change gets checked before it reaches you:

```json
{ "id": "lantern", "label": "Lantern", "folder": "~/code/lantern", "review": true,
  "check": { "run": ["npm", "test"], "label": "The tests" } }
```

Then, when a Claude Code conversation there finishes a turn in which it changed files, Arnheim holds
the turn while the work goes through the line:

1. the floor's check (step 5), if it has one, and, if that passes,
2. a reader: a second Claude Code, which can only read files, is shown what changed (from git) and
   what you asked for, and says whether the work is ready for you.

Work that passes reaches you as usual, and its page says it passed and what the reader thought.
Work that doesn't goes back to the agent with the reason, and it carries on fixing it; meanwhile it
isn't listed as waiting on you. After two sends back it reaches you anyway, marked as having failed,
so nothing goes round for ever.

`"review": { "read": false }` leaves the reader out, so only the check decides. `"times"` sets how
often work can be sent back (0 to 5, two if left out), and `"timeout"` the reader's time limit in
seconds (five minutes if left out). The reader runs with Claude Code's `claude` command
(`ARNHEIM_CLAUDE` names another), in the floor's folder, with only the tools that read and search
files, no MCP servers, and nothing saved to your Claude Code history. What it spends counts towards
the floor's budget (step 7): a few thousand new tokens for a small change.

The line runs while Claude Code waits for the turn to end, so give step 2's Stop hook a time limit
longer than the check's and the reader's together:

```json
"Stop": [{ "hooks": [{ "type": "command", "command": "python3 /path/to/arnheim/connect/claude_code.py", "timeout": 1200 }] }]
```

If the limit runs out first, the turn ends as usual and the building says the work wasn't reviewed.
A conversation you stop from the building isn't reviewed. Agents other than Claude Code (step 9)
aren't held, since the building only hears from them once they have finished.

## 13. Routines

Jobs that run on a schedule, such as a weekly look for outdated packages, a nightly security scan or
a check that a release is ready. List them on their floor:

```json
{ "id": "lantern", "label": "Lantern", "folder": "~/code/lantern",
  "routines": [
    { "id": "outdated", "label": "Outdated packages", "every": "monday", "at": "09:00", "run": ["npm", "outdated"] },
    { "id": "scan", "label": "Security scan", "every": "weekday", "at": "07:30",
      "ask": "Look for secrets or unsafe code added since yesterday, and fix what you safely can." }
  ] }
```

- `id`: a short name of its own on the floor (letters, numbers, `-` and `_`).
- `every`: `hour`, `day`, `weekday` (Monday to Friday), a day's name such as `monday`, or `week` with
  `"on": "saturday"`. `at` is the time of day on this computer's clock, 24-hour: 09:00 if left out.
- `run`: a command, which runs as a floor's check does (step 5): in the floor's folder, with no shell,
  and stopped after `timeout` seconds (ten minutes if left out). It is all clear if it succeeds.
- `ask`: instead of a command, a job for a new Claude Code agent on the floor, which gets a brief as
  in step 11 and is asked to end with "All clear" when nothing needs you. It can do what your Claude
  Code settings let it do without asking, and is stopped after `timeout` seconds (an hour if left
  out). Its conversation shows in the building as any other does.

To run them, start Arnheim with `--routines`, which checks every minute while it runs:

```bash
python3 serve.py --routines
```

Or have your computer's own scheduler run `python3 /path/to/arnheim/connect/routines.py` every few
minutes (cron or launchd), which starts the routines that are due and gives back at once. Add
`"feeds/routines.json"` to `feeds` in `company.json` too.

The Overview lists each routine, when it runs and what its last run came to. You only hear about one
when it needs you: a command that fails or runs too long, or an agent that doesn't end all clear, puts
a task in "Waiting on you", which goes when a later run is all clear. With control on, "Run it now"
and "Run it again" run one at once. A new routine waits for its first time after Arnheim first sees
it, and one missed while the computer slept runs once when it is next checked, not once for each time
it missed. Ask the receptionist "what routines are there?" to hear them.
`python3 connect/routines.py --list` says each one and when it runs next, and `--run <id>` runs one
now and waits for it.

## 14. Project health

Each floor says at a glance whether it is well, from what the building already knows. A floor needs
looking at while:

- an agent's work there failed its check (step 5), and the agent isn't back at work on it,
- work failed the review line (step 12),
- a routine needs you (step 13).

It has a warning while a pull request that isn't a draft has waited a week or more since it was last
updated (step 3). The floor shows a chip ("One thing to fix", "A pull request waiting"), its page
lists each thing in words, and the Overview's "Project health" card, after "Waiting on you", puts
every floor together. With control on, each thing has "Send an agent", which starts one on the floor
with a brief that says what is wrong and asks it to fix it, or, for a pull request, to say what it
needs without merging or closing it. Ask the receptionist "is anything broken?" or "how are the
projects doing?" to hear it.

## 15. A morning brief, and pings on your phone

The receptionist tells you what happened since you were last here: how many agents were at work,
which finished and whether their work was proven, which were stopped, which routines ran, and what
waits on you now. On a walk they greet you with it the first time you come to the desk, out loud
with Voice on. Ask "brief me", "what did I miss?" or "what happened overnight?" to hear it again.
The Overview shows it too, as "Since you were last here". Your last visit is kept in that browser,
and the brief never reaches back more than a day.

To have it on your phone, add "pings" to company.json, and Arnheim sends the brief at the first time
of the day. At each later time it sends only when a decision has come up since the last ping: a
permission an agent asks for, a question it stopped to ask, or a task marked as needing you. A quiet
night sends nothing.

```json
"pings": { "ntfy": "https://ntfy.sh/a-long-topic-name-nobody-could-guess", "at": ["08:00", "13:00", "17:30"] }
```

[ntfy](https://ntfy.sh) is free and open source: install its app on your phone and subscribe to the
same topic. The words go to that server, which hands them to the app. They are the counts in the
brief, the titles of your agents' work and the floors they are on, the questions agents stop to ask
you in their own words, the titles of your tasks that need you, and for a permission only its kind
("wants your permission to run a command"), never the command or the file. Anyone who knows the
topic can read them, so pick a name nobody could guess, or run your own ntfy server. The address
must be https, or plain http to a server on this computer, and the page is never shown the topic:
serve.py leaves "pings" out of the company.json it gives the page. Or send them your own way:
`"run": ["/path/to/your/notifier"]` gets each ping on its standard input, its first line the title.

```bash
python3 serve.py --pings
python3 connect/ping.py --test
```

`--pings` checks every minute while Arnheim runs (or have your computer's scheduler run `python3
connect/ping.py` every few minutes). `--test` sends a hello now, to check it reaches you, `--show`
prints what the brief would say without sending it, and `--now` sends the brief now. A new setting
waits for its first time, and a time missed while the computer slept sends once.

## 16. Restore points

Before an agent changes a project's files, Arnheim can keep how they were, so you can go back. Add
this hook beside step 2's, in the same settings file:

```json
"PreToolUse": [{ "matcher": "Edit|MultiEdit|Write|NotebookEdit|Bash", "hooks": [{ "type": "command", "command": "python3 /path/to/arnheim/connect/claude_code.py" }] }]
```

and `"feeds/restore.json"` to `feeds` in `company.json`. Then, before the first file an agent changes
after each message you send it, and before any command that deletes or overwrites files in bulk (`rm
-r`, `git reset --hard`, `git clean -f`, `git checkout -- ...`, `git stash` and the like), the hook
saves the floor's files as a restore point: every file in the floor's own folder that git doesn't
ignore, and nothing outside it, even when that folder sits inside a bigger repository. Files that look
like secrets (`.env` files, keys, certificates, credentials and the like) are never saved, even ones
git tracks. It knows them by their names only, so keep anything private in `.gitignore` as well: that
is what really keeps it out. It uses git, beside the project's own history: your branch, what you have
staged and your files are left as they are, and `git log` shows nothing new unless you ask it for
`--all`. A folder that isn't in git gets none. The hook keeps a list of its own for each floor inside
the repository's `.git` folder, so after the first restore point the next ones are quick. A floor's
folder so big that saving takes longer than 20 seconds gets no restore points for six hours, so its
agents aren't held up.

Each conversation's page and each floor's page list its restore points. With control on (step 4), **Go
back to here** puts the floor's files as they were then: those changed since are put back and those
deleted since come back. Files that weren't there then, made or committed since, are left where they
are, and listed. Secret-looking files are left as they are. It keeps how things are first, as a restore
point of its own, so going back can be undone too, and if it can't keep that, it doesn't go back. It
won't while an agent working in the same folder is at work or waiting on you: let it finish, or stop
it, first. The last 40 restore points are kept; git tidies older ones away in its own time.

## 17. A shelf of how-tos

Write down how your company does things, a short Markdown file each, and list them in `company.json`'s
`howtos` (docs/data.md, "How-tos"). Each agent in a floor's folder is told that floor's how-tos, and
those every floor shares, as it starts, with where to read each one, and is asked to follow the one
that covers what it is about to do. In the building they stand on the Library's shelf.

## What is kept, and where

The connectors write `data/feeds/claude-code.json` and `data/feeds/projects.json`. From Claude Code
they keep, for each conversation: its title, or the first line of your first message; the first
words of your latest message; the first sentences of the last thing Claude said; what it asks you
for; and its task titles. Nothing else from the conversation is kept, and nothing leaves this
computer, unless you serve Arnheim with `--lan`, when anyone on your network can open it, or with
`--share`, when those you give its view-only link can (README, "A view-only link").

A floor's check keeps the last lines it printed beside each conversation it checked, and a lock and
a note for its next run in `data/feeds/proof/`. The company's memory is `data/memory.json`, and the
feed notes when each conversation was last told it. For the budget, the feed keeps each conversation's
new tokens for today and how far its transcript has been read; `data/control/` keeps a pause, and how
far each floor was let go past its budget today. On a floor with a review line, the feed also
keeps what the line made of each conversation's work. Routines keep `data/feeds/routines.json`: each
routine, when Arnheim first saw it, and its last run, with a command's last lines or an agent's last
words. Pings keep `data/feeds/pings.json`: when the last was sent, what each of the last fourteen said, and whether it arrived. The replay's moments are kept a file a day in
`data/feeds/history/`, for a week, with what each floor's agents spent that day. Restore points are
listed in `data/feeds/restore.json`, and their files kept by git in each project's own repository,
under `refs/arnheim/restore/`.

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
