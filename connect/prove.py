#!/usr/bin/env python3
"""Done means proven: runs a floor's own check on an agent's work, and keeps what came of it.

A floor in data/company.json can name a check, the command that shows its work is sound, such as its
tests (docs/connect.md, "Done means proven"):

    "check": {"run": ["python3", "-m", "unittest"], "label": "The tests"}

When a Claude Code conversation on that floor ends a turn in which it changed files with its edit
tools, the hook (connect/claude_code.py) starts this in the background, as `prove.py <project>`. It runs
the check in the floor's folder, as an argument list with no shell and with a time limit, and writes
what came of it beside each conversation whose changes it covers, in data/feeds/claude-code.json. The
building then shows that work as proven (the check passed after its last change), not proven (the
check failed, with its last lines), or claimed (it changed files, and nothing has checked them since).

One check runs per floor at a time. Turns that end while it runs get one more run when it ends.
`--also <key>` checks that conversation's work again even if it hasn't changed since (the page's
"Check it again", with control on). Standard library only.
"""
import argparse
import hashlib
import os
import re
import signal
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import claude_code  # noqa: E402  (beside this file: the feed it writes to)
import control  # noqa: E402  (beside this file: what a floor's check is)

ROUNDS = 4  # at most this many runs back to back, for turns that ended meanwhile
TAIL_LINES = 14
TAIL_CHARS = 1500
ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")  # colours and cursor moves in a terminal


def tail(raw):
    """The last lines a check printed, as plain text."""
    text = ANSI.sub("", raw.decode("utf-8", "replace")).replace("\r\n", "\n").replace("\r", "\n")
    lines = [part.rstrip() for part in text.split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines[-TAIL_LINES:])[-TAIL_CHARS:]


def halt(proc):
    """Stops a check that ran too long, with everything it started."""
    def send(sig):
        try:
            if hasattr(os, "killpg"):
                os.killpg(proc.pid, sig)
            else:
                proc.kill()
        except OSError:
            pass
    send(signal.SIGTERM)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        send(getattr(signal, "SIGKILL", signal.SIGTERM))
        proc.wait()


def run(check):
    """Runs a check once: passed, failed, timeout (stopped at its time limit) or error (didn't start)."""
    started = time.time()
    with tempfile.TemporaryFile() as out:  # on disk, so a check that prints a lot costs no memory
        try:
            proc = subprocess.Popen(check["run"], cwd=check["folder"], stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                                    start_new_session=hasattr(os, "setsid"))
        except OSError as error:
            return {"state": "error", "code": None, "took": 0, "tail": f"It didn't start: {error.strerror or error}."}
        try:
            code = proc.wait(timeout=check["timeout"])
            state = "passed" if code == 0 else "failed"
        except subprocess.TimeoutExpired:
            halt(proc)
            code, state = None, "timeout"
        out.seek(0, os.SEEK_END)
        out.seek(max(0, out.tell() - 16384))
        raw = out.read()
    return {"state": state, "code": code, "took": round(time.time() - started, 1), "tail": tail(raw)}


def covered(project, also):
    """The conversations on this floor a run now covers: those with changes no check has covered, and `also`."""
    talks = claude_code.read_feed().get("conversations") or []
    return {c["id"] for c in talks if isinstance(c, dict) and c.get("id") and c.get("project") == project
            and (claude_code.due(c) or c["id"] in also)}


def mark(project, keys, proof):
    def edit(feed):
        talks = [c for c in feed.get("conversations") or [] if isinstance(c, dict)]
        for c in talks:
            if c.get("id") in keys and c.get("project") == project:
                c["proof"] = dict(proof)
        return talks, [t for t in feed.get("tasks") or [] if isinstance(t, dict)]
    claude_code.edit_feed(edit)


def take(lock):
    """The floor's lock, if no other run holds it."""
    try:
        import fcntl
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except ImportError:  # Windows has no flock: two runs at once only cost time
        pass
    except OSError:
        return False
    return True


def prove(project, also=None):
    """Runs the floor's check for its conversations' changes, again while turns keep ending, ROUNDS times at
    most. What it did, in a word: no-check, nothing, busy (the run going on takes it), or done."""
    check = control.check_for(project, claude_code.DATA)
    if not check:
        return "no-check"
    folder = os.path.join(claude_code.DATA, "feeds", "proof")
    os.makedirs(folder, exist_ok=True)
    name = re.sub(r"[^A-Za-z0-9]+", "-", project).strip("-")[:40] + "-" + hashlib.sha256(project.encode("utf-8")).hexdigest()[:8]
    again = os.path.join(folder, name + ".again")
    asked = {also} if also else set()
    did, rounds = "nothing", 0
    while rounds < ROUNDS:
        with open(os.path.join(folder, name + ".lock"), "a") as lock:
            if not take(lock):
                # One is running: leave word, so it runs again when it ends. If it ended meanwhile, run here.
                with open(again, "a", encoding="utf-8") as handle:
                    handle.write("\n".join(sorted(asked)) + "\n")
                if not take(lock):
                    return "busy" if did == "nothing" else did
            while rounds < ROUNDS:
                try:
                    with open(again, encoding="utf-8") as handle:
                        asked |= {line.strip() for line in handle if line.strip()}
                    os.remove(again)
                except OSError:
                    pass
                keys = covered(project, asked)
                if not keys:
                    break
                rounds += 1
                started = time.time()
                mark(project, keys, {"state": "checking", "check": check["label"], "at": started, "until": started + check["timeout"]})
                result = run(check)
                mark(project, keys, {**result, "check": check["label"], "at": started, "done": time.time()})
                did, asked = "done", set()
                if not os.path.exists(again):
                    break
        if not os.path.exists(again):  # word left as this run let go: take it too
            return did
    return did


def main():
    parser = argparse.ArgumentParser(description="Runs a floor's check on its agents' work (docs/connect.md, \"Done means proven\").")
    parser.add_argument("project", help="the floor's project, as data/company.json names it")
    parser.add_argument("--also", help="a conversation to check again even if it hasn't changed since")
    args = parser.parse_args()
    if args.also and not control.KEY.match(args.also):
        parser.error("--also takes a conversation's key, such as cc-abc123")
    try:
        print(prove(args.project, args.also))
    except Exception as error:  # trouble goes to the feed's log, as the hook's does
        claude_code.note(error)
        sys.exit(1)


if __name__ == "__main__":
    main()
