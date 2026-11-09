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

With control switched on (serve.py --control, and connect/control.py), it also hands Claude what you
say to it in the building, at its next step; while the building is open, it shows a permission
Claude asks for there and waits a while for your answer; and it stops Claude when you ask. Otherwise
it prints nothing, so Claude Code goes on as if it weren't there. Standard library only.
"""
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import control  # noqa: E402  (beside this file: what the building has for Claude Code)

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
    talks = [c for c in talks if c.get("id") not in gone]
    tasks = [t for t in tasks if t.get("session") not in gone]
    if ends:
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

    if name == "SessionEnd":
        talk.update(working=False)
    elif name == "SessionStart" and event.get("source") in (None, "startup", "clear"):
        talk.update(working=False, check=False)
    elif name == "UserPromptSubmit":
        said = line(event.get("prompt"), 100)
        if talk["title"] == NEW and said:
            talk["title"] = line(event.get("prompt"), 70)
        talk.update(working=True, check=False, says={"now": f'I\'m working on what you asked: "{said}".' if said else "I'm working on it."})
        drop(ask)
    elif name == "PostToolUse" and extra.get("stopped"):
        talk.update(working=False, check=True, says={"now": "I stopped, as you asked.", "next": "It's your turn now."})
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
    elif name == "PermissionRequest":
        message = line(f"I'm waiting for your permission: {extra.get('asking') or event.get('tool_name') or 'a tool'}", 140)
        talk.update(working=False, check=True)
        talk["says"] = {**talk.get("says", {}), "needs": f"{message}."}
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
    return talks, tasks


def update(event, extra=None):
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
        talks, tasks = change(event, feed, project, time.time(), extra)
        out = {
            "about": "Kept up to date by connect/claude_code.py, from Claude Code's hooks (docs/connect.md). Safe to delete.",
            "conversations": talks,
            "tasks": tasks,
        }
        part = f"{FEED}.{os.getpid()}.part"
        with open(part, "w", encoding="utf-8") as handle:
            json.dump(out, handle, ensure_ascii=False, indent=1)
        os.replace(part, FEED)  # whole, so the page never reads half a file


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
        update(event, extra)
    except Exception as error:  # the feed's trouble never costs Claude your message or answer
        note(error)


def respond(event):
    """Keeps the feed up to date, and gives what Claude Code should hear back, if anything: your
    messages from the building, your answer there to a permission, or your request to stop.
    None means nothing: Claude Code carries on as usual."""
    name = event.get("hook_event_name")
    if not event.get("session_id"):
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
    stop = box.stopping(key) if name in ("PostToolUse", "UserPromptSubmit", "Stop") else False
    if stop and name == "PostToolUse":
        keep(event, {"stopped": True})
        return {"continue": False, "stopReason": "Stopped from Arnheim, the building."}
    # A new message from you, or a turn that ends anyway, spends a request to stop.
    rows = box.take(key) if name in ("PostToolUse", "UserPromptSubmit") or (name == "Stop" and not stop) else []
    if not rows:
        keep(event, {"started_here": os.path.exists(box.path("runs", key + ".json"))} if name == "SessionEnd" else None)
        return None
    heard = rows[-1].get("id")
    if name == "Stop":
        keep(event, {"heard": heard, "going_on": True})
        return {"decision": "block", "reason": control.message(rows, stopping=True)}
    keep(event, {"heard": heard})
    return {"hookSpecificOutput": {"hookEventName": name, "additionalContext": control.message(rows)}}


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
