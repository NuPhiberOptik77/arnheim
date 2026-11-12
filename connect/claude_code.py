#!/usr/bin/env python3
"""Arnheim's Claude Code connector: a hook that shows each Claude Code conversation in the building.

Claude Code runs it at the moments docs/connect.md lists, and hands it what happened as JSON on
stdin. It finds the floor whose "folder" (in data/company.json) holds the conversation's folder, and
keeps data/feeds/claude-code.json up to date for the page, which reads it every few seconds:

- a seat in that floor's Conversations room for each conversation, with someone in it while
  Claude works, and a blue light once Claude has finished and it is your turn;
- an amber desk while Claude waits for your permission or an answer, which the receptionist lists under
  "Needs you";
- a desk for each task on Claude's task list, someone at it while it is being done;
- what the conversation says if you stand at its seat on a walk: the last thing Claude said.

It keeps a title for each conversation (its own, or the first line of your first message), the
first sentences of the last thing Claude said, your latest message's first words and task titles,
all in data/, on this computer. Any trouble goes to data/feeds/claude-code.log, and Claude carries on.

It hands every conversation in the company's folders the company's how-tos for its floor as it starts
(data/company.json's "howtos", docs/data.md), to read before work one of them covers. It also hands it
the company's memory as it starts (data/memory.json:
the decisions you asked the building to remember), and one at work the decisions made since, with your
next message to it.

It counts what each conversation spends each day, in new tokens, from its own transcript. When a
floor's agents pass the floor's budget for the day (connect/budget.py), it stops the one at work at its
next step, once, and asks you in the building whether they may go on. Paused from the building, every
conversation stops at its next step, and a message you send one in Claude Code waits until you resume.

With a PreToolUse hook too, it takes a restore point of the project's files before the first file a
conversation changes after each message you send it, and before any command that deletes or overwrites
files in bulk, so you can go back from the building (connect/restore.py).

It keeps a short log of each day's moments for the building's replay: when each conversation started
work, which files it changed (as paths inside its floor's folder), what it asked, and when it finished
or stopped (data/feeds/history/, a file a day, kept for a week).

When two conversations change the same file within two hours, the one that just did is told who
else is changing it, so it can check their work first, and the building shows the pair.

When a conversation changes files and its floor names a check (docs/connect.md, "Done means proven"), it
starts that check in the background as the turn ends (connect/prove.py), and the building shows whether
the work is proven. On a floor with a review line, it holds the turn instead while the check and a reader
look at the work (connect/review.py), and sends it back to Claude with the reason if it isn't ready.

With control switched on (serve.py --control, and connect/control.py), it also hands Claude what you
say to it in the building, at its next step; while the building is open, it shows a permission
Claude asks for there and waits a while for your answer; and it stops Claude when you ask. Otherwise
it prints nothing, so Claude Code goes on as if it weren't there. Standard library only.
"""
import datetime
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import budget  # noqa: E402  (beside this file: what each conversation spends)
import control  # noqa: E402  (beside this file: what the building has for Claude Code)
import restore  # noqa: E402  (beside this file: restore points before an agent changes files)

DATA = os.environ.get("ARNHEIM_DATA") or os.path.join(os.path.dirname(HERE), "data")
FEED = os.path.join(DATA, "feeds", "claude-code.json")
LOG = os.path.join(DATA, "feeds", "claude-code.log")
KEEP = 12 * 3600  # a conversation not heard from for this long has gone
ASKS = {"permission_prompt", "elicitation_dialog", "agent_needs_input"}  # Claude waits for you to decide
CHANGES = {"Edit", "MultiEdit", "Write", "NotebookEdit"}  # tools that change files: then its floor's check is due
NEW = "A new conversation"
CLASH = 2 * 3600  # seconds: two conversations changing one file this close together may trip over each other
FILES_KEPT = 30
HISTORY = os.path.join(DATA, "feeds", "history")
HISTORY_DAYS = 7
HISTORY_MOST = 5000  # moments in a day at most
COUNT = {"PostToolUse", "Stop", "UserPromptSubmit", "SubagentStop", "SessionEnd", "PreCompact"}  # moments its spending is counted


def line(text, most):
    """One line of plain words, at most `most` characters, cut at a word."""
    text = " ".join(re.sub(r"```.*?```", " ", str(text or ""), flags=re.S).split())
    if len(text) <= most:
        return text
    cut = text.rfind(" ", 0, most - 1)
    return text[: cut if cut > most // 2 else most - 1].rstrip(" ,;:") + "…"


def sentences(text, most=300):
    """The first whole sentences of what Claude said, up to about `most` characters."""
    text = line(text, 4000)
    out = ""
    for part in re.findall(r"[^.!?]+[.!?]+[\"')\]]*\s*|[^.!?]+$", text):
        if out and len(out) + len(part) > most:
            break
        out += part
    return line(out or text, most)


def project_for(cwd):
    """The project of the floor whose folder holds cwd (the deepest, if folders nest), or None."""
    try:
        with open(os.path.join(DATA, "company.json"), encoding="utf-8-sig") as handle:
            company = json.load(handle)
    except (OSError, ValueError):
        return None
    here = os.path.realpath(os.path.expanduser(str(cwd or "")))
    best = None
    for floor in company.get("floors") or []:
        if not isinstance(floor, dict):
            continue
        folders = floor.get("folders") or ([floor["folder"]] if floor.get("folder") else [])
        for folder in folders if isinstance(folders, list) else []:
            root = os.path.realpath(os.path.expanduser(str(folder)))
            inside = here == root or here.startswith(root.rstrip(os.sep) + os.sep)
            if inside and (best is None or len(root) > len(best[0])):
                best = (root, floor.get("project") or floor.get("label"))
    return best[1] if best else None


class Lock:
    """One writer at a time: Claude Code runs hooks for several conversations at once."""

    def __init__(self, path):
        self.path = path

    def __enter__(self):
        self.handle = open(self.path, "a")
        try:
            import fcntl
            fcntl.flock(self.handle, fcntl.LOCK_EX)
        except ImportError:  # Windows has no flock; a clash there costs one update at most
            pass
        return self

    def __exit__(self, *_):
        self.handle.close()  # closing lets go of the lock


def key_of(event):
    return "cc-" + re.sub(r"[^A-Za-z0-9]", "", str(event["session_id"]))[:12]


def change(event, feed, project, now, extra=None):
    """What this event changes in the feed's conversations and tasks. `extra` says what the
    building's control did: handed over a message (heard), had Claude go on rather than stop
    (going_on), stopped it (stopped), or asks for your permission (asking); or that the
    conversation was started from the building (started_here), so it stays when it ends."""
    extra = extra or {}
    name = event.get("hook_event_name")
    key = key_of(event)
    talks = [c for c in feed.get("conversations") or [] if isinstance(c, dict)]
    tasks = [t for t in feed.get("tasks") or [] if isinstance(t, dict)]
    def old(c):
        try:
            return now - float(c.get("at") or 0) > KEEP
        except (TypeError, ValueError):
            return True

    gone = {c.get("id") for c in talks if old(c)}
    ends = name == "SessionEnd" and not extra.get("started_here")  # one started from the building stays, to talk to
    if ends:
        gone.add(key)
    day = budget.local_day()
    budget.leave(feed, [c for c in talks if c.get("id") in gone], day)  # what they spent today still counts
    talks = [c for c in talks if c.get("id") not in gone]
    tasks = [t for t in tasks if t.get("session") not in gone]
    if ends:
        return talks, tasks

    talk = next((c for c in talks if c.get("id") == key), None)
    if talk is None:
        talk = {"id": key, "project": project, "title": NEW, "working": False, "check": False, "says": {}}
        back = budget.come_back(feed, key, day)
        if back:  # one that left earlier today: its spending goes on from where it was
            talk.update(spent={"day": day, "tokens": back.get("tokens") or 0}, read=back.get("read"))
        talks.append(talk)
    talk.update(project=project, at=now)
    if event.get("session_title"):
        talk["title"] = line(event["session_title"], 70)
    ask = f"{key}-ask"

    def task(tid, **fields):
        found = next((t for t in tasks if t.get("id") == tid), None)
        if found is None:
            found = {"id": tid, "session": key, "project": project}
            tasks.append(found)
        found.update(fields)

    def drop(tid):
        tasks[:] = [t for t in tasks if t.get("id") != tid]

    if name == "SessionEnd":
        talk.update(working=False)
    elif name == "SessionStart" and event.get("source") in (None, "startup", "clear"):
        talk.update(working=False, check=False)
    elif name == "UserPromptSubmit":
        said = line(event.get("prompt"), 100)
        if talk["title"] == NEW and said:
            talk["title"] = line(event.get("prompt"), 70)
        talk.update(working=True, check=False, says={"now": f'I\'m working on what you asked: "{said}".' if said else "I'm working on it."},
                    asked=said, asked_at=now)
        talk.pop("review", None)  # a new piece of work: the review line starts afresh
        drop(ask)
    elif name == "PostToolUse" and extra.get("stopped"):
        talk.update(working=False, check=True, says={"now": "I stopped, as you asked.", "next": "It's your turn now."})
        drop(ask)
    elif name == "PostToolUse":
        talk.update(working=True, check=False)
        drop(ask)
        given = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
        path = str(given.get("file_path") or given.get("notebook_path") or "")
        if event.get("tool_name") in CHANGES:
            talk["changed"] = now
        if event.get("tool_name") in CHANGES and path:  # which files it changed lately, for clashes
            where = inside(path, event.get("cwd"))
            files = [f for f in talk.get("files") or [] if isinstance(f, dict) and f.get("path") != where]
            talk["files"] = (files + [{"path": where, "at": now}])[-FILES_KEPT:]
        if event.get("tool_name") == "TaskUpdate":  # its own task list: in progress, done or deleted
            tid = given.get("taskId") or given.get("task_id")
            state = given.get("status")
            if tid and state in ("completed", "deleted"):
                drop(f"{key}-t{tid}")
            elif tid and state in ("in_progress", "pending"):
                task(f"{key}-t{tid}", status="working" if state == "in_progress" else "open")
        elif event.get("tool_name") == "TodoWrite":  # the older to-do list: the whole list each time
            tasks[:] = [t for t in tasks if not str(t.get("id", "")).startswith(f"{key}-todo")]
            for i, todo in enumerate(given.get("todos") or []):
                if isinstance(todo, dict) and todo.get("status") in ("pending", "in_progress"):
                    task(f"{key}-todo{i}", title=line(todo.get("content"), 90), status="working" if todo["status"] == "in_progress" else "open")
    elif name == "Notification":
        kind = event.get("notification_type")
        if kind in ASKS:
            message = line(event.get("message") or "Claude is waiting for you.", 90)
            talk.update(working=False, check=True)
            talk["says"] = {**talk.get("says", {}), "needs": f"{message}."}
            if kind == "permission_prompt":  # a permission, not a question: pings name only its kind (connect/ping.py)
                talk["says"].setdefault("permission", "")
            else:
                talk["says"].pop("permission", None)
            task(ask, title=f"{talk['title']}: {message}", status="needs_you", note=message)
        elif kind == "idle_prompt":
            talk.update(working=False, check=True)
    elif name == "PermissionRequest":
        message = line(f"I'm waiting for your permission: {extra.get('asking') or event.get('tool_name') or 'a tool'}", 140)
        talk.update(working=False, check=True)
        talk["says"] = {**talk.get("says", {}), "needs": f"{message}.", "permission": str(event.get("tool_name") or "")}
        task(ask, title=line(f"{talk['title']}: {message}", 120), status="needs_you", note=message)
    elif name == "Stop" and extra.get("going_on"):  # it has your message to answer first
        said = sentences(event.get("last_assistant_message"))
        talk.update(working=True, check=False)
        if said:
            talk["says"] = {"now": said}
        drop(ask)
    elif name == "Stop":
        said = sentences(event.get("last_assistant_message"))
        talk.update(working=bool(event.get("background_tasks")), check=True,
                    says={"now": said or "I've finished for now.", "next": "It's your turn now."})
        if talk.get("heard"):  # what it just said answers your message
            talk["answered"] = talk.pop("heard")
        talk["stopped"] = now
        drop(ask)
    elif name == "TaskCreated" and event.get("task_id"):
        task(f"{key}-t{event['task_id']}", title=line(event.get("task_subject") or "A task", 90), status="open")
    elif name == "TaskCompleted" and event.get("task_id"):
        drop(f"{key}-t{event['task_id']}")
    if extra.get("heard"):
        talk["heard"] = extra["heard"]
    if extra.get("memory_at"):
        talk["memory_at"] = extra["memory_at"]
    return talks, tasks


def read_feed(path=None):
    try:
        with open(path or FEED, encoding="utf-8") as handle:
            feed = json.load(handle)
    except (OSError, ValueError):
        feed = {}
    return feed if isinstance(feed, dict) else {}


def edit_feed(edit, path=None, about=None):
    """Changes the feed, one writer at a time: edit(feed) gives the new conversations and tasks, or None
    to leave it as it is. Another connector's feed can be named by `path`, with its own `about`."""
    path = path or FEED
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with Lock(path + ".lock"):
        feed = read_feed(path)
        out = edit(feed)
        if out is None:
            return
        talks, tasks = out
        out = {
            "about": about or "Kept up to date by connect/claude_code.py, from Claude Code's hooks (docs/connect.md). Safe to delete.",
            "conversations": talks,
            "tasks": tasks,
        }
        if isinstance(feed.get("ended"), dict):  # today's spending by conversations that have left (connect/budget.py)
            out["ended"] = feed["ended"]
        part = f"{path}.{os.getpid()}.part"
        with open(part, "w", encoding="utf-8") as handle:
            json.dump(out, handle, ensure_ascii=False, indent=1)
        os.replace(part, path)  # whole, so the page never reads half a file


def update(event, extra=None):
    """Keeps the feed up to date with this event. What the building's rules then ask of Claude Code:
    {"stop": why} to stop at this step (a budget passed, or every agent paused), or {}."""
    verdict = {}
    if not event.get("session_id"):
        return verdict
    project = project_for(event.get("cwd"))
    if not project and not os.path.isfile(FEED):
        return verdict  # a conversation in a folder no floor names: not part of this company

    def edit(feed):
        where = project
        if not where:  # one already in the building that has moved out of its folder stays where it was
            seat = next((c for c in feed.get("conversations") or [] if isinstance(c, dict) and c.get("id") == key_of(event)), None)
            where = seat and seat.get("project")
            if not where:
                return None
        before = next((dict(c) for c in feed.get("conversations") or [] if isinstance(c, dict) and c.get("id") == key_of(event)), None)
        talks, tasks = change(event, feed, where, time.time(), extra)
        talk = next((c for c in talks if c.get("id") == key_of(event)), None)
        if talk is not None:
            weigh(event, talk, talks, tasks, where, extra or {}, verdict, feed.get("ended"))
        try:
            if talk is not None or before is not None:  # one that ended has left the feed: log it as it was
                said = dict(extra or {})
                was = before or {}
                if was.get("check") and (was.get("says") or {}).get("needs") and talk is not None and talk.get("working"):
                    said["answered"] = True  # it waited on you, and went on: the wait ends here (src/waiting.js)
                day = budget.local_day()
                spent = {p: budget.spent_today(talks, p, day, feed.get("ended"))
                         for p in {c.get("project") for c in talks if c.get("project")} | {where}}
                log(event, talk if talk is not None else before, where, said, verdict, spent)
        except Exception as error:  # the replay's trouble never costs the feed
            note(error)
        return talks, tasks

    edit_feed(edit)
    return verdict


def moment(event, talk, extra, verdict):
    """What this event was, for the day's replay: (kind, words), or None for nothing worth keeping."""
    name = event.get("hook_event_name")
    given = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
    if verdict.get("stop") or extra.get("stopped"):
        return "stopped", (talk.get("says") or {}).get("now") or "It stopped."
    if name == "UserPromptSubmit" and not extra.get("paused_prompt"):
        said = line(event.get("prompt"), 80)
        return "working", f'You asked: "{said}"' if said else "It started work."
    if name == "PostToolUse" and event.get("tool_name") in CHANGES:
        path = str(given.get("file_path") or given.get("notebook_path") or "")
        return "changed", inside(path, event.get("cwd")) if path else "a file"
    if name in ("PermissionRequest", "Notification") and (talk.get("says") or {}).get("needs"):
        return "asked", talk["says"]["needs"]
    if name == "Stop" and not extra.get("going_on"):
        return "finished", (talk.get("says") or {}).get("now") or "It finished."
    if name == "SessionEnd":
        return "left", "The conversation ended."
    if extra.get("answered"):
        return "answered", "It went on."
    return None


def inside(path, cwd):
    """A changed file as a path inside the floor's folder, never this computer's own folders."""
    folder = os.path.realpath(os.path.expanduser(str(cwd or "")))
    full = os.path.realpath(os.path.join(folder, os.path.expanduser(path)))
    if full.startswith(folder.rstrip(os.sep) + os.sep):
        return os.path.relpath(full, folder)
    return os.path.basename(full)


def log(event, talk, project, extra, verdict, spent=None):
    """Adds this event's moment to today's history, under the feed's lock, with what each floor's agents
    have spent today so far (for the weekly report, src/weekly.js)."""
    found = moment(event, talk, extra, verdict)
    if not found:
        return
    add_moment(talk, project, *found, spent=spent)


def add_moment(talk, project, kind, what, spent=None):
    """Adds a moment to today's history, for the replay. Any connector can (connect/agents.py). `spent`, tokens
    by project, keeps the day's highest for each."""
    now = time.time()
    day = budget.local_day()
    path = os.path.join(HISTORY, day + ".json")
    try:
        with open(path, encoding="utf-8") as handle:
            kept = json.load(handle)
        rows = kept.get("moments") or []
        had = kept.get("spent") if isinstance(kept.get("spent"), dict) else {}
    except (OSError, ValueError, AttributeError):
        rows, had = [], {}
    spent_now = dict(had)
    for p, tokens in (spent or {}).items():
        if isinstance(p, str) and isinstance(tokens, int) and tokens > (had.get(p) if isinstance(had.get(p), int) else -1):
            spent_now[p] = tokens
    key = talk.get("id")
    if kind == "changed" and any(r.get("key") == key and r.get("kind") == "changed" and r.get("what") == what and now - r.get("at", 0) < 300
                                 for r in rows[-40:]):
        return  # the same file again within five minutes: once is enough
    rows = (rows + [{"at": round(now, 1), "key": key, "project": project, "title": talk.get("title"), "kind": kind, "what": line(what, 160)}])[-HISTORY_MOST:]
    os.makedirs(HISTORY, exist_ok=True)
    part = f"{path}.{os.getpid()}.part"
    with open(part, "w", encoding="utf-8") as handle:
        json.dump({"about": "The day's moments, for the building's replay and its history (docs/connect.md, \"Replay the day\"). Safe to delete.",
                   "moments": rows, "spent": spent_now}, handle, ensure_ascii=False)
    os.replace(part, path)
    oldest = (datetime.date.today() - datetime.timedelta(days=HISTORY_DAYS)).isoformat()
    for name in os.listdir(HISTORY):  # a week is kept
        if name.endswith(".json") and name[:10] < oldest:
            try:
                os.remove(os.path.join(HISTORY, name))
            except OSError:
                pass


def clash(talk, talks, project, now):
    """The other conversations on this floor that changed a file this one just changed, within CLASH
    seconds: [(their title, the file)]."""
    files = talk.get("files") or []
    mine = files[-1].get("path") if files and isinstance(files[-1], dict) else None
    if not mine:
        return []
    out = []
    for c in talks:
        if c is talk or c.get("project") != project:
            continue
        for f in c.get("files") or []:
            if isinstance(f, dict) and f.get("path") == mine and now - float(f.get("at") or 0) < CLASH:
                out.append((c.get("title") or "another conversation", mine))
    return out


def halt(talk, words):
    talk.update(working=False, check=True, says={"now": words, "next": "It's your turn now."})


def weigh(event, talk, talks, tasks, project, extra, verdict, ended=None):
    """What the conversation has spent today, its floor's budget, and every agent paused (connect/budget.py)."""
    name = event.get("hook_event_name")
    day = budget.local_day()
    if event.get("transcript_path") and name in COUNT:
        spent, talk["read"] = budget.new_tokens(event["transcript_path"], talk.get("read"))
        had = talk.get("spent") if isinstance(talk.get("spent"), dict) and talk["spent"].get("day") == day else {}
        talk["spent"] = {"day": day, "tokens": int(had.get("tokens") or 0) + spent.get(day, 0)}
    if extra.get("paused_prompt"):
        halt(talk, "Every agent is paused from the building. Resume them there, then send your message again.")
        return
    box = control.Box(DATA)
    tid = "budget-" + re.sub(r"[^A-Za-z0-9]+", "-", project).strip("-").lower()
    try:
        with open(os.path.join(DATA, "company.json"), encoding="utf-8-sig") as handle:
            per_day = budget.budget_of(json.load(handle), project)
    except (OSError, ValueError):
        per_day = None
    limit = per_day * (1 + box.allowances(day).get(project, 0)) if per_day else None
    used = budget.spent_today(talks, project, day, ended)
    if not limit or used < limit:
        tasks[:] = [t for t in tasks if t.get("id") != tid]  # under budget again: nothing to ask
    if name == "PostToolUse" and event.get("tool_name") in CHANGES:
        others = clash(talk, talks, project, time.time())
        if others:
            who = ", ".join(f'"{title}"' for title, _ in others[:3])
            verdict["warn"] = (f"Arnheim, the building, saw that {who} also changed {others[0][1]} in the last two hours, in another "
                               "conversation. Look at what changed there before going on, so you don't undo each other's work.")
    if name != "PostToolUse" or extra.get("heard") or extra.get("stopped"):
        return  # it stops only between steps, and never instead of handing over your message
    paused = box.paused()
    if paused and talk.get("paused") != paused:
        talk["paused"] = paused
        halt(talk, "I stopped: every agent is paused from the building.")
        verdict["stop"] = "Paused from Arnheim, the building: every agent is paused until the person you work for resumes them there."
    elif limit and used >= limit and talk.get("braked") != limit:
        talk["braked"] = limit
        halt(talk, f"I stopped: {project}'s agents have used today's budget.")
        tasks[:] = [t for t in tasks if t.get("id") != tid] + [{
            "id": tid, "project": project, "budget": project, "status": "needs_you",
            "title": f"{project}'s agents have used today's budget",
            "note": f"{budget.tokens(used)} new tokens of {budget.tokens(limit)}. Let them go on, or leave them until tomorrow.",
        }]
        verdict["stop"] = (f"Stopped by Arnheim, the building: {project}'s agents have used today's budget of {budget.tokens(limit)} "
                           "new tokens. Wait until the person you work for lets you go on.")


def due(talk):
    """Whether a conversation changed files that no check has covered since."""
    proof = talk.get("proof") if isinstance(talk.get("proof"), dict) else {}
    try:
        return float(talk.get("changed") or 0) > float(proof.get("at") or 0)
    except (TypeError, ValueError):
        return False


def prove(event):
    """As a turn ends: if the conversation changed files since its floor's check last ran, starts the
    check in the background (connect/prove.py). Claude Code doesn't wait for it."""
    try:
        talk = next((c for c in read_feed().get("conversations") or [] if isinstance(c, dict) and c.get("id") == key_of(event)), None)
        if talk and due(talk) and control.check_for(talk.get("project"), DATA):
            control.prove_later(talk["project"], DATA)
    except Exception as error:  # a check that can't start never troubles Claude Code
        note(error)


def edit_talk(event, change_it):
    """Changes one conversation in the feed: change_it(talk) under the feed's lock."""
    def edit(feed):
        talks = [c for c in feed.get("conversations") or [] if isinstance(c, dict)]
        talk = next((c for c in talks if c.get("id") == key_of(event)), None)
        if talk is None:
            return None
        change_it(talk)
        return talks, [t for t in feed.get("tasks") or [] if isinstance(t, dict)]
    edit_feed(edit)


def restore_point(event):
    """Before an agent changes files: a restore point (connect/restore.py), once after each message you send
    it, and before every command that deletes or overwrites files in bulk. Tried once a turn, so a folder
    that isn't in git, or one too big to save quickly, costs nothing more after the first try."""
    tool = event.get("tool_name")
    given = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
    bulk = tool == "Bash" and restore.risky(given.get("command"))
    if tool not in CHANGES and not bulk:
        return None
    project = project_for(event.get("cwd"))
    if not project:
        return None  # not this company's work
    key = key_of(event)
    talk = next((c for c in read_feed().get("conversations") or [] if isinstance(c, dict) and c.get("id") == key), None) or {}

    def number(value):
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0
    if not bulk and talk.get("restore_at") and number(talk.get("restore_at")) >= number(talk.get("asked_at")):
        return None  # one already since your last message
    asked = talk.get("asked")
    why = f"before: {line(given.get('command'), 70)}" if bulk else (f'before changing files for "{asked}"' if asked else "before changing files")
    now = time.time()
    try:
        return restore.take(event.get("cwd"), why, key=key, project=project, title=talk.get("title") or NEW, data=DATA, now=now)
    finally:
        edit_talk(event, lambda t: t.update(restore_at=round(now, 1)))


def review(event):
    """As a turn ends on a floor with a review line (connect/review.py): holds it while the floor's check and
    the reader look at what changed. What Claude Code hears back: the work sent back with the reason, or None,
    when it passed, failed as often as allowed (it reaches you anyway), or the floor has no line."""
    try:
        import review as line  # noqa: E402  (beside this file; only when a turn ends)
        talk = next((c for c in read_feed().get("conversations") or [] if isinstance(c, dict) and c.get("id") == key_of(event)), None)
        project = talk and talk.get("project")
        floor = project and line.floor_of(project, DATA)
        given = line.review_of(floor)
        if not given or not line.due(talk):
            return None
        check = control.check_of(floor)
        now = time.time()
        said = dict(talk.get("says") or {})
        before = dict(talk.get("review") or {}) if isinstance(talk.get("review"), dict) else {}
        until = now + (check["timeout"] if check else 0) + (given["timeout"] if given["read"] else 0)

        def held(t):
            t.update(working=True, check=False, says={"now": "The review line is checking my work before it reaches you."},
                     review={**before, "state": "reviewing", "at": now, "until": until})
            if check:
                t["proof"] = {"state": "checking", "check": check["label"], "at": now, "until": now + check["timeout"]}
        edit_talk(event, held)
        try:
            result = line.run(event, talk, project, DATA)
        except Exception as error:  # noted, and the work reaches you unreviewed rather than stuck
            note(error)
            result = None
        if result is None:
            result = {"state": "error", "by": "The review line", "said": "It met an error (see data/feeds/claude-code.log).", "at": now}
        why = result.get("why") or ""

        def done(t):
            t["review"] = {k: result[k] for k in ("state", "by", "said", "why", "times", "most", "at") if result.get(k) not in (None, "")}
            t["review"]["done"] = time.time()
            if result.get("proof"):
                t["proof"] = result["proof"]
            if result.get("tokens"):
                day = budget.local_day()
                had = t.get("spent") if isinstance(t.get("spent"), dict) and t["spent"].get("day") == day else {}
                t["spent"] = {"day": day, "tokens": int(had.get("tokens") or 0) + int(result["tokens"])}
            if result["state"] == "sent back":
                t.update(working=True, check=False, says={"now": f"The review line sent my work back, so I'm fixing it: {why.splitlines()[0] if why else ''}"})
                add_moment(t, project, "working", f"The review line sent it back: {why.splitlines()[0] if why else ''}")
            else:
                t.update(working=False, check=True, says=said)
                if result["state"] == "passed":
                    add_moment(t, project, "finished", f"It passed the review line ({result.get('by')}).")
                elif result["state"] == "failed":
                    add_moment(t, project, "finished", f"It reached you after failing the review line: {why.splitlines()[0] if why else ''}")
        edit_talk(event, done)
        return {"decision": "block", "reason": line.sent_back(result)} if result["state"] == "sent back" else None
    except Exception as error:  # the review line's trouble never keeps Claude from finishing
        note(error)
        return None


def note(error):
    """Trouble goes to the log, never to Claude Code."""
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        mode = "w" if os.path.isfile(LOG) and os.path.getsize(LOG) > 100_000 else "a"
        with open(LOG, mode, encoding="utf-8") as handle:
            handle.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {type(error).__name__}: {error}\n")
    except OSError:
        pass


def keep(event, extra=None):
    try:
        return update(event, extra)
    except Exception as error:  # the feed's trouble never costs Claude your message or answer
        note(error)
        return {}


def remembered(event, name):
    """The company's memory to hand this conversation now, as (words, when), or None: all of it as a
    conversation in the company's folders starts (or starts again after its context was compacted), and
    what was decided since it was last told when you send it a message."""
    if name not in ("SessionStart", "UserPromptSubmit"):
        return None
    rows = control.memory(DATA)
    if not rows:
        return None
    talk = next((c for c in read_feed().get("conversations") or [] if isinstance(c, dict) and c.get("id") == key_of(event)), None)
    if not project_for(event.get("cwd")) and not talk:
        return None  # not this company's work
    now = time.time()
    if name == "UserPromptSubmit":
        try:
            since = float((talk or {}).get("memory_at") or 0)
        except (TypeError, ValueError):
            since = 0
        rows = [row for row in rows if isinstance(row.get("at"), (int, float)) and row["at"] > since] if since else rows
        if not rows:
            return None
        return control.told(rows, new=bool(since)), now
    return control.told(rows), now


HOWTO_FILE = re.compile(r"^(?:[\w-]+/)*[\w-]+\.md$")
HOWTOS_TOLD = 20


def shelf(event):
    """The company's how-tos for this conversation's floor, and those for every floor, as an agent is handed them
    as it starts: each title with its file, to read before work it covers. None if there are none."""
    project = project_for(event.get("cwd"))
    if not project:
        return None
    try:
        with open(os.path.join(DATA, "company.json"), encoding="utf-8-sig") as handle:
            company = json.load(handle)
    except (OSError, ValueError):
        return None
    home = os.path.realpath(DATA)
    rows = []
    for item in company.get("howtos") or [] if isinstance(company, dict) else []:
        if not isinstance(item, dict) or item.get("project") not in (None, "", project):
            continue
        name, title = str(item.get("file") or ""), line(item.get("title"), 80)
        path = os.path.realpath(os.path.join(home, name))
        if title and HOWTO_FILE.match(name) and path.startswith(home + os.sep) and os.path.isfile(path):
            rows.append(f'"{title}" ({path})')
    if not rows:
        return None
    return ("The people you work for keep how-tos for their own ways of doing things, in Arnheim, the building that shows "
            "their company's work. Before you do something one of them covers, read it and follow it: " + "; ".join(rows[:HOWTOS_TOLD]) + ".")


def respond(event):
    """Keeps the feed up to date, and gives what Claude Code should hear back, if anything: your
    messages from the building, your answer there to a permission, or your request to stop.
    None means nothing: Claude Code carries on as usual."""
    name = event.get("hook_event_name")
    if not event.get("session_id") or os.environ.get("ARNHEIM_REVIEWER"):
        return None  # the review line's own reader is never a conversation of its own
    if name == "PreToolUse":
        try:
            restore_point(event)
        except Exception as error:  # a restore point's trouble never holds Claude up
            note(error)
        return None
    key = key_of(event)
    box = control.Box(DATA)
    if name == "PermissionRequest":
        tool = str(event.get("tool_name") or "a tool")
        what = control.describe(tool, event.get("tool_input"))
        keep(event, {"asking": what})
        got = control.await_answer(box, key, tool, what)
        if got == "allow":  # this one request, as it was shown: never a rule for later ones
            return {"hookSpecificOutput": {"hookEventName": name, "decision": {"behavior": "allow"}}}
        if got in ("deny", "stop"):
            decision = {"behavior": "deny", "message": "Denied from Arnheim, the building." if got == "deny" else "Stopped from Arnheim, the building."}
            if got == "stop":
                decision["interrupt"] = True
            return {"hookSpecificOutput": {"hookEventName": name, "decision": decision}}
        return None
    if name == "UserPromptSubmit" and box.paused() and (project_for(event.get("cwd")) or any(
            isinstance(c, dict) and c.get("id") == key for c in read_feed().get("conversations") or [])):
        keep(event, {"paused_prompt": True})
        return {"decision": "block", "reason": "Arnheim, the building, has paused every agent. Resume them there, then send this again."}
    stop = box.stopping(key) if name in ("PostToolUse", "UserPromptSubmit", "Stop") else False
    if stop and name == "PostToolUse":
        keep(event, {"stopped": True})
        return {"continue": False, "stopReason": "Stopped from Arnheim, the building."}
    # A new message from you, or a turn that ends anyway, spends a request to stop.
    rows = box.take(key) if name in ("PostToolUse", "UserPromptSubmit") or (name == "Stop" and not stop) else []
    try:
        memo = remembered(event, name)
    except Exception as error:  # the memory's trouble never costs Claude your message
        note(error)
        memo = None
    told = {"memory_at": memo[1]} if memo else {}
    if not rows:
        extra = {"started_here": os.path.exists(box.path("runs", key + ".json"))} if name == "SessionEnd" else {}
        verdict = keep(event, {**extra, **told} or None)
        if verdict.get("stop"):
            return {"continue": False, "stopReason": verdict["stop"]}
        if name == "Stop" and not stop:
            held = review(event)
            if held:
                return held
        if name == "Stop":
            prove(event)
        howtos = None
        if name == "SessionStart":
            try:
                howtos = shelf(event)
            except Exception as error:  # the shelf's trouble never costs Claude its start
                note(error)
        words = "\n\n".join(w for w in (howtos, memo[0] if memo else None, verdict.get("warn")) if w)
        return {"hookSpecificOutput": {"hookEventName": name, "additionalContext": words}} if words else None
    heard = rows[-1].get("id")
    if name == "Stop":
        keep(event, {"heard": heard, "going_on": True})
        return {"decision": "block", "reason": control.message(rows, stopping=True)}
    verdict = keep(event, {"heard": heard, **told})
    words = "\n\n".join(w for w in (control.message(rows), memo[0] if memo else None, verdict.get("warn")) if w)
    return {"hookSpecificOutput": {"hookEventName": name, "additionalContext": words}}


def main():
    out = None
    try:
        raw = sys.stdin.read()
        event = json.loads(raw) if raw.strip() else {}
        if isinstance(event, dict):
            out = respond(event)
    except Exception as error:  # never trouble Claude Code: note it and carry on
        note(error)
    if out:
        try:
            sys.stdout.write(json.dumps(out, ensure_ascii=False))
            sys.stdout.flush()
        except (OSError, ValueError):
            pass
    sys.exit(0)


if __name__ == "__main__":
    main()
