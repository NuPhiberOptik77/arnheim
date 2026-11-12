#!/usr/bin/env python3
"""Routines: jobs that run on a schedule, and tell you only when something needs you.

A floor in data/company.json can list routines (docs/connect.md, "Routines"):

    "routines": [
      {"id": "outdated", "label": "Outdated packages", "every": "monday", "at": "09:00", "run": ["npm", "outdated"]},
      {"id": "scan", "label": "Security scan", "every": "weekday", "at": "07:30",
       "ask": "Look for secrets or unsafe code added since yesterday, and fix what you safely can."}
    ]

`every` is hour, day, weekday (Monday to Friday), week (with "on", a day's name: Monday if left out), or
a day's name. `at` is the time of day on this computer's clock, 24-hour (09:00 if left out; for hour, its
minutes). A routine runs a command (`run`, as a floor's check does: no shell, in the floor's folder, with
a time limit) or starts a Claude Code agent on the floor with a job (`ask`), told to end with "All clear"
when nothing needs you. `timeout` is its time limit in seconds: ten minutes for a command and an hour for
an agent if left out.

`python3 connect/routines.py` starts the routines that are due, each in the background, and gives back at
once: `serve.py --routines` does it every minute, or a scheduler of your own can (cron, launchd). A new
routine waits for its first time after Arnheim first sees it, and one missed while this computer slept
runs once when it is next checked. `--run <id>` runs one now and waits for it.

It keeps data/feeds/routines.json, a feed the building reads: each routine, its schedule in words, its
last run and its next. A command that fails, or an agent that doesn't end all clear, adds a task that
needs you; a later run that is all clear takes it away. Standard library only.
"""
import argparse
import datetime
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
import uuid

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import claude_code  # noqa: E402  (beside this file)
import control  # noqa: E402
import prove  # noqa: E402

ABOUT = "Kept up to date by connect/routines.py, from the routines in company.json (docs/connect.md). Safe to delete."
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
EVERY = {"hour", "day", "weekday", "week", *DAYS}
COMMAND_WAIT = 600
AGENT_WAIT = 3600
ALL_CLEAR = re.compile(r"\ball[\s-]+clear\b", re.I)
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$")


def key_of(project, rid):
    return "rt-" + re.sub(r"[^a-z0-9]+", "-", f"{project}-{rid}".lower()).strip("-")[:60]


def routines_of(data=None):
    """Every routine the company's floors list that can run on this computer, as {key, id, project, label,
    floor, folder, every, on, at, run | ask, timeout}. Ones that can't are left out."""
    data = data or claude_code.DATA
    company = control.read(os.path.join(data, "company.json")) or {}
    here = {f["project"]: f for f in control.floors_of(data)}
    out = []
    for floor in company.get("floors") or []:
        if not isinstance(floor, dict) or not isinstance(floor.get("routines"), list):
            continue
        project = str(floor.get("project") or floor.get("label") or floor.get("id") or "")
        place = here.get(project)
        if not place:
            continue
        for given in floor["routines"]:
            if not isinstance(given, dict) or not ID.match(str(given.get("id") or "")):
                continue
            every = str(given.get("every") or "").strip().lower()
            on = str(given.get("on") or "monday").strip().lower()
            at = re.match(r"^(\d{1,2}):(\d{2})$", str(given.get("at") or "09:00").strip())
            if every not in EVERY or on not in DAYS or not at or int(at.group(1)) > 23 or int(at.group(2)) > 59:
                continue
            run = given.get("run")
            ask = given.get("ask")
            if isinstance(run, list) and 0 < len(run) <= 64 and all(isinstance(a, str) and a for a in run):
                job = {"run": list(run)}
            elif isinstance(ask, str) and ask.strip():
                job = {"ask": control.one_line(ask, 1000)}
            else:
                continue
            try:
                wait = int(given.get("timeout") or (COMMAND_WAIT if "run" in job else AGENT_WAIT))
            except (TypeError, ValueError):
                wait = COMMAND_WAIT if "run" in job else AGENT_WAIT
            out.append({"key": key_of(project, given["id"]), "id": given["id"], "project": project, "label": control.one_line(given.get("label") or given["id"], 60),
                        "floor": place, "folder": place["folder"], "every": every, "on": on, "at": (int(at.group(1)), int(at.group(2))),
                        "timeout": max(1, min(4 * 3600, wait)), **job})
    return out


def matches(r, day):
    if r["every"] == "day":
        return True
    if r["every"] == "weekday":
        return day.weekday() < 5
    want = r["on"] if r["every"] == "week" else r["every"]
    return DAYS[day.weekday()] == want


def times_near(r, now):
    """The routine's times from about eight days before `now` to eight days after, on this computer's clock."""
    here = datetime.datetime.fromtimestamp(now)
    hour, minute = r["at"]
    if r["every"] == "hour":
        start = here.replace(minute=0, second=0, microsecond=0)
        return [(start + datetime.timedelta(hours=h)).replace(minute=minute).timestamp() for h in range(-2, 3)]
    out = []
    for d in range(-8, 9):
        day = here.date() + datetime.timedelta(days=d)
        if matches(r, day):
            out.append(datetime.datetime.combine(day, datetime.time(hour, minute)).timestamp())
    return out


def last_time(r, now):
    return max((t for t in times_near(r, now) if t <= now), default=0)


def next_time(r, now):
    return min((t for t in times_near(r, now) if t > now), default=None)


def when(r):
    """The schedule in words: "Every Monday at 09:00"."""
    at = "%02d:%02d" % r["at"]
    if r["every"] == "hour":
        return f"Every hour at {r['at'][1]:02d} past"
    if r["every"] == "day":
        return f"Every day at {at}"
    if r["every"] == "weekday":
        return f"Every weekday at {at}"
    return f"Every {(r['on'] if r['every'] == 'week' else r['every']).capitalize()} at {at}"


def running(last, r, now):
    return isinstance(last, dict) and last.get("state") in ("starting", "running") and now < float(last.get("at") or 0) + r["timeout"] + 120


def edit(change, data=None, now=None):
    """Changes the feed under its lock: change(rows by key, tasks) may change both in place."""
    data = data or claude_code.DATA
    path = os.path.join(data, "feeds", "routines.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with claude_code.Lock(path + ".lock"):
        feed = claude_code.read_feed(path)
        now = now or time.time()
        old = {row.get("id"): row for row in feed.get("routines") or [] if isinstance(row, dict)}
        rows = {}
        for r in routines_of(data):
            row = old.get(r["key"]) or {"id": r["key"], "since": now}
            row.update(project=r["project"], label=r["label"], when=when(r), kind="agent" if "ask" in r else "command", next=next_time(r, now))
            rows[r["key"]] = row
        tasks = [t for t in feed.get("tasks") or [] if isinstance(t, dict) and t.get("routine") in rows]
        out = change(rows, tasks)
        part = f"{path}.{os.getpid()}.part"
        with open(part, "w", encoding="utf-8") as handle:
            json.dump({"about": ABOUT, "routines": list(rows.values()), "tasks": tasks}, handle, ensure_ascii=False, indent=1)
        os.replace(part, path)
        return out


def due(now=None, data=None):
    """Marks the routines that are due as starting, and gives back their keys."""
    now = now or time.time()
    by_key = {r["key"]: r for r in routines_of(data)}

    def change(rows, tasks):
        out = []
        for key, row in rows.items():
            r = by_key.get(key)
            if not r:
                continue
            last = row.get("last") if isinstance(row.get("last"), dict) else {}
            if running(last, r, now):
                continue
            if last_time(r, now) > max(float(row.get("since") or now), float(last.get("at") or 0)):
                row["last"] = {"state": "starting", "at": now}
                out.append(key)
        return out
    return edit(change, data, now)


def tick(data=None):
    """Starts each routine that is due, in the background. Gives back their keys."""
    data = data or claude_code.DATA
    keys = due(data=data)
    for key in keys:
        subprocess.Popen([sys.executable, os.path.realpath(__file__), "--run", key], cwd=HERE, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=dict(os.environ, ARNHEIM_DATA=data),
                         close_fds=True, start_new_session=hasattr(os, "setsid"))
    return keys


def agent(r, data):
    """Starts a Claude Code agent with the routine's job, and waits for it. What came of it."""
    sid = str(uuid.uuid4())
    key = "cc-" + sid.replace("-", "")[:12]
    job = control.brief(data, r["ask"], r["floor"], more=f"as the routine \"{r['label']}\" ({when(r).lower()}), with no one watching")
    job += (" If nothing needs the person you work for, end your last message with the words \"All clear\". If something "
            "does need them, a decision, a problem you couldn't fix or a change to look at, say what, and don't say all clear.")
    command = shlex.split(os.environ.get("ARNHEIM_CLAUDE") or "claude")
    env = {name: value for name, value in os.environ.items() if name != "CLAUDECODE"}
    started = time.time()
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as given:
        given.write(job.encode("utf-8"))
        given.seek(0)
        try:
            proc = subprocess.Popen(command + ["-p", "--output-format", "json", "--session-id", sid], cwd=r["folder"], stdin=given, stdout=out,
                                    stderr=subprocess.DEVNULL, env=env, start_new_session=hasattr(os, "setsid"))
        except OSError as error:
            return {"state": "error", "said": f"Claude Code didn't start: {error.strerror or error}.", "key": key}
        try:
            code = proc.wait(timeout=r["timeout"])
        except subprocess.TimeoutExpired:
            prove.halt(proc)
            return {"state": "timeout", "said": f"The agent was still at work after {r['timeout'] // 60} minutes, so it was stopped.", "key": key,
                    "took": round(time.time() - started, 1)}
        out.seek(0)
        raw = out.read(2_000_000).decode("utf-8", "replace")
    try:
        answer = json.loads(raw)
    except ValueError:
        answer = {"result": raw, "is_error": code != 0}
    text = str((answer if isinstance(answer, dict) else {}).get("result") or "").strip()
    took = round(time.time() - started, 1)
    if code != 0 or (isinstance(answer, dict) and answer.get("is_error")):
        return {"state": "error", "said": claude_code.line(text or f"Claude Code ended with code {code}.", 300), "key": key, "took": took}
    clear = bool(ALL_CLEAR.search(text[-200:]))
    return {"state": "all clear" if clear else "needs you", "said": claude_code.sentences(text, 400) or "It finished without a word.", "key": key, "took": took}


def quiet(key, data):
    """An agent that ended all clear: its conversation stays in the building, but doesn't wait on you."""
    def change(talk):
        talk["check"] = False
        talk["says"] = {**(talk.get("says") or {}), "next": "All clear: nothing needs you."}
    claude_code.edit_talk({"session_id": key[3:]}, change)


def run(key, data=None):
    """Runs one routine now, and waits for it. What came of it, or None if there's no such routine, or "busy"."""
    data = data or claude_code.DATA
    r = next((x for x in routines_of(data) if x["key"] == key or x["id"] == key), None)
    if not r:
        return None
    os.makedirs(os.path.join(data, "feeds", "routines"), exist_ok=True)
    with open(os.path.join(data, "feeds", "routines", r["key"] + ".lock"), "a") as lock:
        if not prove.take(lock):
            return "busy"
        started = time.time()

        def begin(rows, tasks):
            rows[r["key"]]["last"] = {"state": "running", "at": started}
        edit(begin, data)
        if "run" in r:
            got = prove.run({"run": r["run"], "folder": r["folder"], "timeout": r["timeout"]})
            result = {"state": {"passed": "all clear"}.get(got["state"], got["state"]), "tail": got["tail"], "took": got["took"]}
        else:
            result = agent(r, data)
        result["at"] = started
        result["done"] = time.time()

        def end(rows, tasks):
            rows[r["key"]]["last"] = result
            tasks[:] = [t for t in tasks if t.get("routine") != r["key"]]
            if result["state"] != "all clear":
                why = {"failed": "It failed.", "timeout": "It ran too long and was stopped.", "error": "It couldn't run."}.get(result["state"], "")
                lines = (result.get("tail") or "").strip().splitlines()
                said = result.get("said") or (lines[-1] if lines else "")
                tasks.append({"id": f"{r['key']}-needs", "routine": r["key"], "project": r["project"], "status": "needs_you",
                              "title": f"The routine \"{r['label']}\" needs you", "note": claude_code.line(" ".join(w for w in (why, said or "") if w), 240),
                              **({"session": result["key"]} if result.get("key") else {})})
        edit(end, data)
        if result["state"] == "all clear" and result.get("key"):
            try:
                quiet(result["key"], data)
            except Exception as error:  # its conversation may not be in the building at all
                claude_code.note(error)
        return result


def main():
    parser = argparse.ArgumentParser(description="Runs the routines in company.json that are due (docs/connect.md, \"Routines\").")
    parser.add_argument("--run", metavar="ID", help="run this routine now, and wait for it")
    parser.add_argument("--list", action="store_true", help="say each routine and when it runs next")
    args = parser.parse_args()
    try:
        if args.list:
            for r in routines_of():
                nxt = next_time(r, time.time())
                print(f"{r['label']} ({r['project']}, {r['id']}): {when(r)}. Next: {time.strftime('%a %d %b %H:%M', time.localtime(nxt)) if nxt else 'unknown'}.")
            return
        if args.run:
            result = run(args.run)
            if result is None:
                sys.exit(f"No routine called {args.run} can run here. python3 connect/routines.py --list says which can.")
            print(result if result == "busy" else result["state"])
            return
        tick()
    except Exception as error:  # trouble goes to the feed's log, as the hook's does
        claude_code.note(error)
        sys.exit(1)


if __name__ == "__main__":
    main()
