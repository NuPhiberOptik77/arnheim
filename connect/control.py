#!/usr/bin/env python3
"""Control of your Claude Code agents from the building, for the person at this computer.

Off unless you switch it on: `python3 serve.py --control` (docs/connect.md, "Control your agents").
Then, on a walk and in the panel:

- what you say to an agent reaches its Claude Code conversation at its next step, and its answer
  comes back to you;
- a permission it asks for shows in the building, with Allow and Deny;
- you can start an agent on a floor's project with a first instruction, and stop one at work;
- you can have a floor's check run again on an agent's work (connect/prove.py);
- you can add to the company's memory, the decisions every agent is told, and take them out again.

The page and Claude Code meet in data/control/, on this computer. Control, below, answers the
page's /control/ requests for serve.py, or for a server of your own. Box is the mail between them.
On Claude Code's side the hook (connect/claude_code.py) reads it: it hands your messages to the
conversation, waits a while for your answer to a permission while someone is using the building,
and stops the conversation when you ask.

Nothing here allows anything by itself. An answer is for the one request it was shown with, and
with no answer Claude Code asks as it always does. It never works over --lan. Standard library only.
"""
import hmac
import json
import os
import re
import secrets
import shlex
import signal
import subprocess
import sys
import threading
import time
import uuid

HERE = os.path.dirname(os.path.realpath(__file__))
DATA = os.environ.get("ARNHEIM_DATA") or os.path.join(os.path.dirname(HERE), "data")
JSON = "application/json; charset=utf-8"
WATCHED = 20  # seconds: a page in use says so every few, so older than this, nobody is there to answer
MAX_TEXT = 2000
KEY = re.compile(r"^cc-[A-Za-z0-9]{1,12}$")  # a conversation, as the feed names it (claude_code.key_of)
ASK_ID = re.compile(r"^[A-Za-z0-9_-]{8,40}$")
KEEP_RUNS = 30
PROVE = os.path.join(HERE, "prove.py")
MEMORY_MOST = 100  # decisions kept at most
MEMORY_TEXT = 300  # characters in one


def wait_seconds():
    """How long a permission request waits for your answer in the building: two minutes, or
    ARNHEIM_CONTROL_WAIT seconds. Claude Code shows nothing else meanwhile."""
    try:
        return max(5, min(550, int(os.environ.get("ARNHEIM_CONTROL_WAIT") or 120)))
    except ValueError:
        return 120


def read(path):
    try:
        with open(path, encoding="utf-8-sig") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def write(path, data):
    """Whole, so a reader never sees half a file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    part = f"{path}.{os.getpid()}.{threading.get_ident()}.part"
    with open(part, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False)
    os.replace(part, path)


def gone(path):
    try:
        os.remove(path)
    except OSError:
        pass


def one_line(text, most):
    text = " ".join(str(text or "").split())
    return text if len(text) <= most else text[: most - 1].rstrip() + "…"


def check_of(floor):
    """A floor's check (connect/prove.py), as data/company.json gives it: {"run": [the command and its
    arguments], "label": what to call it, "folder": where to run it (the floor's first folder if left out),
    "timeout": seconds}, or just the list. None if it has none, or its folder isn't on this computer."""
    given = floor.get("check") if isinstance(floor, dict) else None
    if isinstance(given, list):
        given = {"run": given}
    if not isinstance(given, dict):
        return None
    run = given.get("run")
    if not isinstance(run, list) or not 0 < len(run) <= 64 or not all(isinstance(arg, str) and arg for arg in run):
        return None
    folders = floor.get("folders") or ([floor["folder"]] if floor.get("folder") else [])
    where = given.get("folder") or (folders[0] if isinstance(folders, list) and folders else None)
    if not isinstance(where, str) or not where:
        return None
    path = os.path.realpath(os.path.expanduser(where))
    if not os.path.isdir(path):
        return None
    try:
        wait = int(given.get("timeout") or 600)
    except (TypeError, ValueError):
        wait = 600
    return {"run": list(run), "folder": path, "timeout": max(1, min(3600, wait)), "label": one_line(given.get("label") or "Its check", 60)}


def check_for(project, data=DATA):
    """The check of the floor whose project (or label) this is, or None."""
    company = read(os.path.join(data, "company.json")) or {}
    for floor in company.get("floors") or []:
        if isinstance(floor, dict) and project and str(floor.get("project") or floor.get("label") or "") == project:
            return check_of(floor)
    return None


def prove_later(project, data=DATA, also=None):
    """Starts connect/prove.py for a floor in the background, and gives back at once."""
    args = [sys.executable, PROVE, project] + (["--also", also] if also else [])
    return subprocess.Popen(args, cwd=HERE, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            env=dict(os.environ, ARNHEIM_DATA=data), close_fds=True, start_new_session=hasattr(os, "setsid"))


def memory(data=DATA):
    """The company's memory, data/memory.json: the decisions every agent is told, oldest first."""
    rows = (read(os.path.join(data, "memory.json")) or {}).get("memory")
    return [row for row in rows if isinstance(row, dict) and str(row.get("text") or "").strip()] if isinstance(rows, list) else []


def told(rows, new=False):
    """The company's memory, as an agent is handed it."""
    said = " ".join(f"({i}) {one_line(row['text'], MEMORY_TEXT)}" for i, row in enumerate(rows, 1))
    when = "made new standing decisions since you started" if new else "keep standing decisions"
    return (f"The people you work for {when}, in Arnheim, the building that shows their company's work. "
            f"Follow them unless they tell you otherwise: {said}")


def describe(tool, given):
    """What a permission is for, in one line: the command, the file or the address."""
    given = given if isinstance(given, dict) else {}
    for field in ("command", "file_path", "notebook_path", "url", "query", "path", "pattern", "description"):
        if isinstance(given.get(field), str) and given[field].strip():
            return one_line(f"{tool}: {given[field]}", 300)
    return one_line(f"{tool}: {json.dumps(given, ensure_ascii=False)}" if given else tool, 300)


def message(rows, stopping=False):
    """Your messages, as Claude Code is handed them."""
    said = [one_line(row.get("text"), MAX_TEXT) for row in rows]
    words = f'"{said[0]}"' if len(said) == 1 else " ".join(f'({i}) "{text}"' for i, text in enumerate(said, 1))
    when = "Before you stop: the person you are working for" if stopping else "While you worked, the person you are working for"
    what = "this message" if len(said) == 1 else "these messages"
    return (f"{when} sent you {what} from Arnheim, the building that shows their company's work: {words}. "
            "Take it into account, and reply to it in your next message.")


class Box:
    """data/control/: your messages, Claude Code's permission requests and your answers, and
    requests to stop. Claude Code's side reads it through the hook, the page's through Control."""

    def __init__(self, data=DATA):
        self.root = os.path.join(data, "control")

    def path(self, *parts):
        return os.path.join(self.root, *parts)

    # Someone is using the building: its page says so every few seconds while they walk, or have
    # touched it in the last two minutes (src/control.js). A page left open on its own doesn't count.
    def watch(self):
        os.makedirs(self.root, exist_ok=True)
        with open(self.path("watched"), "w") as handle:
            handle.write(str(time.time()))

    def watched(self):
        try:
            return time.time() - os.path.getmtime(self.path("watched")) < WATCHED
        except OSError:
            return False

    # What you say to a conversation, for it to read at its next step.
    def post(self, key, text):
        os.makedirs(self.path("inbox"), exist_ok=True)
        row = {"id": secrets.token_hex(6), "text": text, "at": time.time()}
        fd = os.open(self.path("inbox", key + ".jsonl"), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, (json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8"))
        finally:
            os.close(fd)
        return row["id"]

    def waiting(self, key):
        try:
            return os.path.getsize(self.path("inbox", key + ".jsonl"))
        except OSError:
            return 0

    def take(self, key):
        """The conversation's waiting messages, oldest first, each handed over once."""
        path = self.path("inbox", key + ".jsonl")
        mine = f"{path}.{os.getpid()}.taken"
        try:
            os.rename(path, mine)  # whoever renames it first has them
        except OSError:
            return []
        try:
            with open(mine, encoding="utf-8") as handle:
                lines = handle.read().splitlines()
        finally:
            gone(mine)
        rows = []
        for raw in lines:
            try:
                row = json.loads(raw)
            except ValueError:
                continue
            if isinstance(row, dict) and str(row.get("text") or "").strip():
                rows.append(row)
        return rows

    # A permission a conversation is waiting for, and the one answer to it.
    def ask(self, key, tool, what, until):
        aid = secrets.token_urlsafe(12)
        write(self.path("asks", aid + ".json"), {"id": aid, "key": key, "tool": tool, "what": what, "at": time.time(), "until": until})
        return aid

    def asks(self):
        """The requests still waiting for an answer, oldest first."""
        try:
            names = os.listdir(self.path("asks"))
        except OSError:
            return []
        now = time.time()
        out = []
        for name in names:
            if not name.endswith(".json"):
                continue
            row = read(self.path("asks", name))
            until = float((row or {}).get("until") or 0)
            if row and until > now and not os.path.exists(self.path("answers", name)):
                out.append(row)
            elif until < now - 60:  # left behind by a hook that was cut short
                gone(self.path("asks", name))
                gone(self.path("answers", name))
        return sorted(out, key=lambda row: row.get("at") or 0)

    def answer(self, aid, behavior):
        """Answers a request that is still waiting, once. False for any other."""
        if behavior not in ("allow", "deny") or not isinstance(aid, str) or not ASK_ID.match(aid):
            return False
        row = read(self.path("asks", aid + ".json"))
        if not row or float(row.get("until") or 0) < time.time():
            return False
        os.makedirs(self.path("answers"), exist_ok=True)
        try:
            fd = os.open(self.path("answers", aid + ".json"), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            return False
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"id": aid, "behavior": behavior, "at": time.time()}, handle)
        return True

    def answered(self, aid):
        row = read(self.path("answers", aid + ".json"))
        return row.get("behavior") if row and row.get("behavior") in ("allow", "deny") else None

    def close(self, aid):
        gone(self.path("asks", aid + ".json"))
        gone(self.path("answers", aid + ".json"))

    # Stopping a conversation at its next step.
    def stop(self, key):
        os.makedirs(self.path("stop"), exist_ok=True)
        with open(self.path("stop", key), "w") as handle:
            handle.write(str(time.time()))

    def stopping(self, key, keep=False):
        path = self.path("stop", key)
        if not os.path.exists(path):
            return False
        if not keep:
            gone(path)
        return True


def await_answer(box, key, tool, what):
    """For the hook: shows a permission request in the building, if someone is using it, and waits
    for your answer there. Gives "allow", "deny", "stop" (deny and stop the conversation), or None: no
    answer, so Claude Code asks as it always does."""
    if not box.watched():
        return None
    until = time.time() + wait_seconds()
    aid = box.ask(key, tool, what, until)
    try:
        while time.time() < until:
            got = box.answered(aid)
            if got:
                return got
            if box.stopping(key):
                return "stop"
            if not box.watched():  # nobody is using the building now
                return None
            time.sleep(0.25)
        return None
    finally:
        box.close(aid)


class Refused(Exception):
    """A request the building can't carry out, in words for the person who made it."""


class Control:
    """The page's side: answers /control/ requests (handle), and looks after the agents started
    from the building, each a `claude -p` in its floor's folder, with your own Claude Code
    settings, as if you had started it there yourself."""

    def __init__(self, data=DATA, claude=None):
        self.data = data
        self.box = Box(data)
        self.token = secrets.token_urlsafe(24)
        self.claude = list(claude) if claude else shlex.split(os.environ.get("ARNHEIM_CLAUDE") or "claude")
        self.lock = threading.Lock()
        self.runs = {}
        self.procs = {}
        self.load()

    # ---------- requests ----------

    def handle(self, method, name, body=b"", token=""):
        """One request under /control/: (status, content type, bytes, extra headers). Every request
        but `token` needs the token, in the X-Arnheim-Control header. `state` is what waits; `here` is
        the same, from a page someone is using, so permission requests wait for them."""
        def answer(code, data):
            return code, JSON, json.dumps(data, ensure_ascii=False).encode("utf-8"), {}

        if name == "token":
            return answer(200, {"on": True, "token": self.token}) if method == "GET" else answer(405, {"error": "Use GET."})
        if not isinstance(token, str) or not hmac.compare_digest(token.encode(), self.token.encode()):
            return answer(403, {"error": "This page can't control anything. Reload it."})
        if name in ("state", "here"):
            if method != "GET":
                return answer(405, {"error": "Use GET."})
            if name == "here":
                self.box.watch()
            return answer(200, self.state())
        if method != "POST":
            return answer(405, {"error": "Use POST."})
        try:
            given = json.loads((body or b"{}").decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return answer(400, {"error": "That wasn't JSON."})
        if not isinstance(given, dict):
            return answer(400, {"error": "That wasn't a JSON object."})
        try:
            if name == "say":
                return answer(200, self.say(given.get("key"), given.get("text")))
            if name == "answer":
                if not self.box.answer(given.get("id"), given.get("behavior")):
                    raise Refused("That request isn't waiting any more: it was answered, or Claude Code asked there instead.")
                return answer(200, {"ok": True})
            if name == "start":
                return answer(200, self.start(given.get("project"), given.get("text")))
            if name == "stop":
                return answer(200, self.stop(given.get("key")))
            if name == "prove":
                return answer(200, self.prove(given.get("key")))
            if name == "remember":
                return answer(200, self.remember(given.get("text")))
            if name == "forget":
                return answer(200, self.forget(given.get("id")))
        except Refused as why:
            return answer(400, {"error": str(why)})
        return answer(404, {"error": "No such request."})

    def state(self):
        with self.lock:
            runs = sorted(self.runs.values(), key=lambda run: run.get("at") or 0, reverse=True)
            runs = [{k: run.get(k) for k in ("key", "project", "title", "state", "said", "answered", "at")} for run in runs[:KEEP_RUNS]]
        return {
            "on": True,
            "wait": wait_seconds(),
            "asks": [{k: row.get(k) for k in ("id", "key", "tool", "what", "at", "until")} for row in self.box.asks()],
            "runs": runs,
            "projects": [{k: f[k] for k in ("project", "label", "floor", "check")} for f in self.floors()],
        }

    # ---------- talking, starting and stopping ----------

    def say(self, key, text):
        key = self.conversation(key)
        text = self.words(text)
        with self.lock:
            run = self.runs.get(key)
            if run and run.get("sid") and run.get("folder") and not self.alive(run):
                # An agent started here that has finished: it carries on with what you said.
                said = secrets.token_hex(6)
                self.box.stopping(key)  # an old request to stop isn't for this new turn
                self.spawn(run, ["--resume", run["sid"]], text, answering=said)
                return {"id": said, "sent": "resumed"}
        if self.box.waiting(key) > 64_000:
            raise Refused("It has a lot waiting for it already. Let it catch up first.")
        return {"id": self.box.post(key, text), "sent": "queued"}

    def start(self, project, text):
        text = self.words(text)
        floor = next((f for f in self.floors() if f["project"] == project), None)
        if not floor:
            raise Refused("That project has no folder on this computer. Give its floor a folder in data/company.json.")
        sid = str(uuid.uuid4())
        key = "cc-" + sid.replace("-", "")[:12]
        run = {"key": key, "sid": sid, "project": floor["project"], "folder": floor["folder"], "title": one_line(text[:1].upper() + text[1:], 70), "said": "", "at": time.time()}
        with self.lock:
            self.spawn(run, ["--session-id", sid], text)
        return {"key": key, "project": floor["project"]}

    def stop(self, key):
        key = self.conversation(key)
        self.box.stop(key)  # wherever it runs, the hook stops it at its next step
        with self.lock:
            run = self.runs.get(key)
            if run and self.alive(run):  # one started here stops now
                run["stopping"] = True
                self.send(run, signal.SIGINT)
                threading.Timer(6, self.send, args=(run, getattr(signal, "SIGTERM", signal.SIGINT))).start()
        return {"ok": True}

    def prove(self, key):
        """Runs the conversation's floor's check again on its work, in the background (connect/prove.py)."""
        key = self.conversation(key)
        feed = read(os.path.join(self.data, "feeds", "claude-code.json")) or {}
        talk = next((c for c in feed.get("conversations") or [] if isinstance(c, dict) and c.get("id") == key), None)
        with self.lock:
            project = (talk or {}).get("project") or (self.runs.get(key) or {}).get("project")
        check = check_for(project, self.data) if project else None
        if not check:
            raise Refused('Its floor has no check to run. Give it one in data/company.json (docs/connect.md, "Done means proven").')
        try:
            proc = prove_later(project, self.data, also=key)
        except OSError as error:
            raise Refused(f"The check didn't start ({error.strerror or error}).")
        threading.Thread(target=proc.wait, daemon=True).start()  # so it leaves nothing behind when it ends
        return {"ok": True, "check": check["label"]}

    # ---------- the company's memory ----------

    def remember(self, text):
        """Adds a decision to data/memory.json. Every agent that starts from now is told it, and those at
        work are told it with your next message to them (connect/claude_code.py)."""
        text = " ".join(str(text or "").split())
        if not text:
            raise Refused("Say what to remember first.")
        if len(text) > MEMORY_TEXT:
            raise Refused(f"That's too long to remember: keep it under {MEMORY_TEXT} characters.")
        with self.lock:
            rows = memory(self.data)
            if any(row["text"].strip().lower() == text.lower() for row in rows):
                raise Refused("That's remembered already.")
            if len(rows) >= MEMORY_MOST:
                raise Refused(f"The memory holds {MEMORY_MOST} decisions. Forget one first.")
            row = {"id": "m-" + secrets.token_hex(4), "text": text, "at": time.time()}
            self.keep_memory(rows + [row])
        return row

    def forget(self, mid):
        with self.lock:
            rows = memory(self.data)
            kept = [row for row in rows if row.get("id") != mid]
            if len(kept) == len(rows):
                raise Refused("That isn't in the memory any more.")
            self.keep_memory(kept)
        return {"ok": True}

    def keep_memory(self, rows):
        write(os.path.join(self.data, "memory.json"), {
            "about": "The decisions every Claude Code agent in this company is told (docs/connect.md, \"Company memory\"). Yours to edit.",
            "memory": rows,
        })

    # ---------- the agents started here ----------

    def spawn(self, run, extra, text, answering=None):
        """Starts `claude -p` in the run's folder, with the words on stdin. Under the lock."""
        os.makedirs(self.box.path("runs"), exist_ok=True)
        log = open(self.box.path("runs", run["key"] + ".log"), "ab")  # what Claude Code says went wrong, if anything
        args = self.claude + ["-p", "--output-format", "stream-json", "--verbose"] + extra
        try:
            proc = subprocess.Popen(args, cwd=run["folder"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log,
                                    start_new_session=hasattr(os, "setsid"))
        except OSError as error:
            log.close()
            raise Refused(f"Claude Code didn't start ({error.strerror or error}). Is its claude command installed? ARNHEIM_CLAUDE can name another.")
        try:
            proc.stdin.write(text.encode("utf-8"))
            proc.stdin.close()
        except OSError:
            pass
        run.update(state="working", pid=proc.pid, at=time.time(), stopping=False)
        self.runs[run["key"]] = run
        self.procs[run["key"]] = proc
        self.save(run)
        threading.Thread(target=self.follow, args=(run, proc, log, answering), daemon=True).start()

    def follow(self, run, proc, log, answering):
        """Reads what the agent says as it goes, and keeps its last words."""
        said = ""
        try:
            for raw in proc.stdout:
                try:
                    event = json.loads(raw)
                except ValueError:
                    continue
                if not isinstance(event, dict):
                    continue
                if event.get("type") == "assistant":
                    content = (event.get("message") or {}).get("content") or []
                    words = " ".join(b.get("text") or "" for b in content if isinstance(b, dict) and b.get("type") == "text").strip()
                    said = words or said
                elif event.get("type") == "result" and isinstance(event.get("result"), str):
                    said = event["result"] or said
        except (OSError, ValueError):
            pass
        finally:
            proc.wait()
            proc.stdout.close()
            log.close()
        with self.lock:
            run["state"] = "stopped" if run.get("stopping") else "done" if proc.returncode == 0 else "failed"
            run.update(said=one_line(said, 1200), at=time.time(), pid=None)
            if answering:
                run["answered"] = answering
            if self.procs.get(run["key"]) is proc:
                del self.procs[run["key"]]
            self.save(run)

    def alive(self, run):
        proc = self.procs.get(run["key"])
        if proc is not None:
            return proc.poll() is None
        pid = run.get("pid")
        if not pid:
            return False
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def send(self, run, sig):
        if not self.alive(run):
            return
        try:
            if hasattr(os, "killpg"):
                os.killpg(run["pid"], sig)  # it runs in a process group of its own, with its tools
            else:
                os.kill(run["pid"], sig)
        except OSError:
            pass

    def save(self, run):
        write(self.box.path("runs", run["key"] + ".json"), {k: v for k, v in run.items() if k != "stopping"})

    def load(self):
        """The agents started here before, including any still at work after a restart."""
        try:
            names = sorted(os.listdir(self.box.path("runs")))
        except OSError:
            return
        found = [run for run in (read(self.box.path("runs", n)) for n in names if n.endswith(".json")) if run and KEY.match(str(run.get("key")))]
        found.sort(key=lambda run: run.get("at") or 0, reverse=True)
        for run in found[KEEP_RUNS:]:
            gone(self.box.path("runs", run["key"] + ".json"))
            gone(self.box.path("runs", run["key"] + ".log"))
        for run in found[:KEEP_RUNS]:
            if run.get("state") == "working" and not self.alive(run):
                run.update(state="done", pid=None)
            self.runs[run["key"]] = run

    # ---------- what the requests may name ----------

    def floors(self):
        """Each floor that names a folder on this computer: its project, its label, and the folder an
        agent starts in (its first)."""
        company = read(os.path.join(self.data, "company.json")) or {}
        out = []
        for floor in company.get("floors") or []:
            if not isinstance(floor, dict):
                continue
            folders = floor.get("folders") or ([floor["folder"]] if floor.get("folder") else [])
            for folder in folders if isinstance(folders, list) else []:
                path = os.path.realpath(os.path.expanduser(str(folder)))
                if os.path.isdir(path):
                    project = str(floor.get("project") or floor.get("label") or floor.get("id") or "")
                    check = check_of(floor)
                    out.append({"project": project, "label": str(floor.get("label") or project), "floor": str(floor.get("id") or ""), "folder": path,
                                "check": check and check["label"]})
                    break
        return out

    def working(self, key):
        """Whether a conversation the building knows is at work now: one started here that is still
        running, or one the Claude Code feed says is working."""
        with self.lock:
            run = self.runs.get(key)
            if run and self.alive(run):
                return True
        feed = read(os.path.join(self.data, "feeds", "claude-code.json")) or {}
        return any(isinstance(c, dict) and c.get("id") == key and c.get("working") for c in feed.get("conversations") or [])

    def conversation(self, key):
        """A conversation the building knows: in the Claude Code feed, or started here."""
        if not isinstance(key, str) or not KEY.match(key):
            raise Refused("No such conversation.")
        if key in self.runs:
            return key
        feed = read(os.path.join(self.data, "feeds", "claude-code.json")) or {}
        if any(isinstance(c, dict) and c.get("id") == key for c in feed.get("conversations") or []):
            return key
        raise Refused("That conversation has left the building.")

    @staticmethod
    def words(text):
        text = str(text or "").strip()
        if not text:
            raise Refused("Say something first.")
        if len(text) > MAX_TEXT:
            raise Refused(f"That's too long: keep it under {MAX_TEXT} characters.")
        return text
