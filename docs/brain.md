# Talk about anything

Switch on the brain, and the receptionist and your assistant answer with Claude. Ask them anything,
out loud on a walk or typed at the front desk, and follow up as you would with a person: they keep
the conversation going. About your company they still say only what the building shows, and when it
doesn't say, they say so.

The brain uses Claude Code on the computer that runs `serve.py`, and your own Claude plan. Arnheim
stays free: it costs nothing more than your plan's own use.

## What you will see

- **Answers to anything.** "What's the capital of Japan?" gets an answer, and so does "What needs
  me today?", from the building's facts. They answer in a sentence or three, read aloud on a walk
  as the words come in, and shown as they come at the front desk.
- **Follow-ups.** "And which floor is the second one on?" works: each of them keeps their own
  conversation with you until they have been quiet for ten minutes.
- **Your company, from your files.** The facts come from whichever company the building shows: the
  sample, or yours in `data/`, with your Claude Code conversations when you have connected them
  ([connect.md](connect.md)). Ask "What is the agent on Lantern doing?" and they tell you what it
  last said, and whether it is working or waiting for you.
- **The same rules.** A greeting gets its usual answer at once. Asked to merge, publish, deploy,
  run jobs, sign in, send email, buy or pay, they still say no and offer to take it down as a task.
  "Remind me to ..." still adds a task, a tour still starts from the desk, and with control on the
  receptionist still starts agents. None of these go to Claude.
- **Where the answers come from.** The receptionist's tab says they answer with Claude, through
  Claude Code on this computer.
- **The rules when Claude can't answer.** If Claude Code is missing, not signed in, or too slow,
  they answer from the building's files as they do with the brain off.

## Switch it on

You need Claude Code installed and signed in on the computer that runs `serve.py`: check that
`claude` works in a terminal there. Then start Arnheim with `--brain`:

```bash
python3 serve.py --brain
```

They answer with Sonnet. `ARNHEIM_BRAIN_MODEL` names another model: `haiku` is quicker and uses
less of your plan.

```bash
ARNHEIM_BRAIN_MODEL=haiku python3 serve.py --brain
```

`ARNHEIM_CLAUDE` names another `claude` command, if yours isn't on the path. The brain works with
`--control` too, but never with `--lan`.

When it is on, Arnheim says so in its terminal ("The brain is on"), the receptionist's tab says
they answer with Claude, and the receptionist greets you with "Ask me what's happening, or
anything at all."

## Switch it off

Stop Arnheim (Ctrl-C in its terminal) and start it again without `--brain`:

```bash
python3 serve.py
```

That's all: the brain changes no settings, adds nothing to your Claude Code and keeps nothing on
disk, and its Claude stops when Arnheim does. With the brain off, the receptionist and your
assistant answer from the building's files alone, as before.

## Pass something on to an agent

With control on too (`python3 serve.py --brain --control`, with the hooks from
[connect.md](connect.md), step 4), your assistant can pass an instruction of yours on to an agent at
work. Ask them plainly, such as "Please tell the Lantern agent to check the login page on tablets
too". They say they are passing it on, and it reaches that agent's Claude Code conversation at its
next step, as a message sent from the building does.

They only do it when you clearly ask, only to an agent that is working now, and never with
anything the receptionist would refuse: asked to have an agent deploy, publish or merge, they say
no, as the rules do. If it can't go, they say why. The receptionist doesn't pass things on; with
control on, they can start a new agent instead.

## What is sent, and what is kept

What goes to Claude, through your Claude Code: the building's facts and what you say to the
receptionist or the assistant. The facts are what the building shows: the company's name and
whether it is made up, its floors, tasks, goals and pull requests, each conversation's agent and
what it last said, the websites and email written down in the lobby, the machines and jobs, and
the company's notes. With control on, the facts also give each conversation's id, so your
assistant can pass things on. They go whole with the first question, and after that only what
changed.

When you step up to the receptionist or the assistant on a walk, or open the receptionist's tab,
the page reads them the facts straight away, so their first answer comes sooner. That is a short
exchange with Claude of its own.

Nothing is kept on disk: Arnheim writes no transcript and no log of what was said, and Claude Code
runs with `--no-session-persistence`, so it keeps no session either. When the server stops, so do
the conversations.

## How it works

Each of them has a `claude` of their own, started the first time you step up or ask. It runs in
an empty folder made for it, which goes when it does, and it stays for follow-ups until it has been
quiet for ten minutes. An answer gets 90 seconds at most.

Their Claude can only talk. It starts with no tools, no settings and no MCP servers: none of your
hooks or permissions apply, and their conversations never show in the building as Claude Code
conversations of yours. It starts without Claude Code's own `CLAUDECODE` and `CLAUDE_*` variables
(`CLAUDE_CONFIG_DIR` stays), so a server started inside a Claude Code session still starts a plain,
separate `claude`.

With control on, the assistant's Claude may end an answer with a line that names a conversation
and an instruction ("PASS ON", then the conversation's id and the words). That line is never said or
shown. The server checks that the agent is working now and that the instruction is nothing the
receptionist would refuse, then sends it through control's own message path
(`connect/control.py`), and otherwise the assistant says why it didn't go.

The brain answers only the page on the computer that runs `serve.py`, with the token that page is
given, as control does. `connect/brain.py` is standard-library Python with one call
(`Brain.handle`) for its three requests (`/brain/status`, `/brain/prime` and `/brain/ask`), for a
server of your own; `src/brain.js` is the page's side.

## If they don't answer with Claude

They answer from the building's files instead, and the terminal that runs `serve.py` says why
("The brain had no answer: ..."), once for each new reason. The browser's console says it too.

- **"Claude Code didn't start":** install Claude Code, or name its command with `ARNHEIM_CLAUDE`.
- **Not signed in:** run `claude` in a terminal and sign in.
- **"Claude took too long to answer":** try again, or try `ARNHEIM_BRAIN_MODEL=haiku`.
