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
all in data/, on this computer. It prints nothing, never stops Claude Code, and always ends well:
any trouble goes to data/feeds/claude-code.log. Standard library only.
"""
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.realpath(__file__))
DATA = os.environ.get("ARNHEIM_DATA") or os.path.join(os.path.dirname(HERE), "data")
FEED = os.path.join(DATA, "feeds", "claude-code.json")
LOG = os.path.join(DATA, "feeds", "claude-code.log")
KEEP = 12 * 3600  # a conversation not heard from for this long has gone
ASKS = {"permission_prompt", "elicitation_dialog", "agent_needs_input"}  # Claude waits for you to decide
NEW = "A new conversation"


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


def change(event, feed, project, now):
    """What this event changes in the feed's conversations and tasks."""
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
    if name == "SessionEnd":
        gone.add(key)
    talks = [c for c in talks if c.get("id") not in gone]
    tasks = [t for t in tasks if t.get("session") not in gone]
    if name == "SessionEnd":
        return talks, tasks

    talk = next((c for c in talks if c.get("id") == key), None)
    if talk is None:
        talk = {"id": key, "project": project, "title": NEW, "working": False, "check": False, "says": {}}
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

    if name == "SessionStart" and event.get("source") in (None, "startup", "clear"):
        talk.update(working=False, check=False)
    elif name == "UserPromptSubmit":
        said = line(event.get("prompt"), 100)
        if talk["title"] == NEW and said:
            talk["title"] = line(event.get("prompt"), 70)
        talk.update(working=True, check=False, says={"now": f'I\'m working on what you asked: "{said}".' if said else "I'm working on it."})
        drop(ask)
    elif name == "PostToolUse":
        talk.update(working=True, check=False)
        drop(ask)
        given = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
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
            task(ask, title=f"{talk['title']}: {message}", status="needs_you", note=message)
        elif kind == "idle_prompt":
            talk.update(working=False, check=True)
    elif name == "Stop":
        said = sentences(event.get("last_assistant_message"))
        talk.update(working=bool(event.get("background_tasks")), check=True,
                    says={"now": said or "I've finished for now.", "next": "It's your turn now."})
        drop(ask)
    elif name == "TaskCreated" and event.get("task_id"):
        task(f"{key}-t{event['task_id']}", title=line(event.get("task_subject") or "A task", 90), status="open")
    elif name == "TaskCompleted" and event.get("task_id"):
        drop(f"{key}-t{event['task_id']}")
    return talks, tasks


def update(event):
    if not event.get("session_id"):
        return
    project = project_for(event.get("cwd"))
    if not project and not os.path.isfile(FEED):
        return  # a conversation in a folder no floor names: not part of this company
    os.makedirs(os.path.dirname(FEED), exist_ok=True)
    with Lock(FEED + ".lock"):
        try:
            with open(FEED, encoding="utf-8") as handle:
                feed = json.load(handle)
        except (OSError, ValueError):
            feed = {}
        feed = feed if isinstance(feed, dict) else {}
        if not project:  # one already in the building that has moved out of its folder stays where it was
            seat = next((c for c in feed.get("conversations") or [] if isinstance(c, dict) and c.get("id") == key_of(event)), None)
            project = seat and seat.get("project")
            if not project:
                return
        talks, tasks = change(event, feed, project, time.time())
        out = {
            "about": "Kept up to date by connect/claude_code.py, from Claude Code's hooks (docs/connect.md). Safe to delete.",
            "conversations": talks,
            "tasks": tasks,
        }
        part = f"{FEED}.{os.getpid()}.part"
        with open(part, "w", encoding="utf-8") as handle:
            json.dump(out, handle, ensure_ascii=False, indent=1)
        os.replace(part, FEED)  # whole, so the page never reads half a file


def main():
    try:
        raw = sys.stdin.read()
        event = json.loads(raw) if raw.strip() else {}
        if isinstance(event, dict):
            update(event)
    except Exception as error:  # never trouble Claude Code: note it and carry on
        try:
            os.makedirs(os.path.dirname(LOG), exist_ok=True)
            mode = "w" if os.path.isfile(LOG) and os.path.getsize(LOG) > 100_000 else "a"
            with open(LOG, mode, encoding="utf-8") as handle:
                handle.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {type(error).__name__}: {error}\n")
        except OSError:
            pass
    sys.exit(0)


if __name__ == "__main__":
    main()
