#!/usr/bin/env python3
"""Pings on your phone: a morning brief, and later in the day only the decisions that wait on you.

In data/company.json (docs/connect.md, "A morning brief, and pings on your phone"):

    "pings": {"ntfy": "https://ntfy.sh/<a long topic name nobody could guess>", "at": ["08:00", "13:00", "17:30"]}

or, to send them your own way, a command that gets each message on its standard input (its first line the title):

    "pings": {"run": ["/path/to/your/notifier"], "at": ["08:00"]}

`at` is the times of day on this computer's clock, 24-hour: 08:00 if left out. The first time of the day sends the
brief: what happened since the last ping, and every decision waiting on you. Each later time sends only when a
decision has come up since the last ping: a permission an agent asks for, a question it stopped to ask, or a task
marked as needing you. Nothing else pings you. A time missed while this computer slept sends once, when it is next
checked, and a new setting waits for its first time.

`python3 connect/ping.py` sends what is due and gives back at once: `serve.py --pings` runs it every minute, or a
scheduler of your own can (cron, launchd). `--show` prints what the brief would say now and sends nothing, `--test`
sends a hello, to check it reaches you, and `--now` sends the brief now.

With ntfy, the words go to that server (ntfy.sh, or one you run), which hands them to its phone app. They are the
titles of your agents' work and what they ask you: pick a topic name nobody could guess, run your own server, or
give `run` a command of your own. It keeps data/feeds/pings.json: when it last sent, what it sent, and whether it
arrived. Standard library only.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import claude_code  # noqa: E402  (beside this file)
import control  # noqa: E402

ABOUT = "Kept by connect/ping.py: when it last pinged your phone, and what it said (docs/connect.md). Safe to delete."
DAY = 86400
KEEP = 14           # bundles kept in the feed
LISTED = 8          # decisions named in one ping; the rest are counted
NAMED = 3           # finished conversations named in the brief
SEND_WAIT = 20      # seconds
TIME = re.compile(r"^(\d{1,2}):(\d{2})$")


def settings(data=None):
    """The pings set in company.json: {ntfy | run, at: [(hour, minute)]}, or None when there are none, or a
    reason (a string) when they can't be used."""
    data = data or claude_code.DATA
    given = (control.read(os.path.join(data, "company.json")) or {}).get("pings")
    if not given:
        return None
    if not isinstance(given, dict):
        return '"pings" in company.json should be an object, between { and }.'
    out = {}
    url = given.get("ntfy")
    run = given.get("run")
    if isinstance(url, str) and re.match(r"^https?://[^\s/]+/[^\s]+$", url.strip()):
        out["ntfy"] = url.strip()
    elif isinstance(run, list) and 0 < len(run) <= 64 and all(isinstance(a, str) and a for a in run):
        out["run"] = list(run)
    else:
        return '"pings" needs "ntfy", a web address such as https://ntfy.sh/your-topic, or "run", a command as a list.'
    times = given.get("at", ["08:00"])
    times = [times] if isinstance(times, str) else times
    out["at"] = []
    for t in times if isinstance(times, list) else []:
        m = TIME.match(str(t).strip())
        if m and int(m.group(1)) < 24 and int(m.group(2)) < 60:
            out["at"].append((int(m.group(1)), int(m.group(2))))
    if not out["at"]:
        return '"at" in "pings" should be times of day, such as ["08:00", "17:30"].'
    out["at"].sort()
    return out


def slot_of(at, now):
    """The latest of the times that has come, on this computer's clock: (when, whether it is the day's first)."""
    here = datetime.datetime.fromtimestamp(now)
    best = (0, False)
    for d in (0, -1):
        day = here.date() + datetime.timedelta(days=d)
        for i, (hour, minute) in enumerate(at):
            t = datetime.datetime.combine(day, datetime.time(hour, minute)).timestamp()
            if t <= now and t > best[0]:
                best = (t, i == 0)
    return best


def work_of(data):
    """The conversations and tasks the building reads: work.json, and each feed listed in company.json."""
    company = control.read(os.path.join(data, "company.json")) or {}
    sources = [os.path.join(data, "work.json")]
    for path in company.get("feeds") or []:
        if isinstance(path, str) and re.match(r"^[\w-]+(/[\w.-]+)*\.json$", path) and ".." not in path:
            sources.append(os.path.join(data, path))
    out = {"conversations": [], "tasks": [], "routines": []}
    for path in sources:
        feed = claude_code.read_feed(path)
        for key in out:
            out[key] += [x for x in feed.get(key) or [] if isinstance(x, dict)]
    return out


def labels(data):
    company = control.read(os.path.join(data, "company.json")) or {}
    out = {}
    for f in company.get("floors") or []:
        if isinstance(f, dict):
            project = str(f.get("project") or f.get("label") or f.get("id") or "")
            out[project] = str(f.get("label") or project)
    return out


def decisions(data, work=None):
    """What waits on you to decide, as [{id, line}]: permissions asked for, questions, and tasks that need you."""
    work = work or work_of(data)
    label = labels(data)
    talks = {c.get("id"): c for c in work["conversations"] if c.get("id")}

    def on(title, project):
        return f'"{control.one_line(title or "An agent", 80)}"' + (f" on {label.get(project, project)}" if project else "")
    out = []
    asking = set()
    for a in control.Box(data).asks():
        c = talks.get(a.get("key")) or {}
        asking.add(a.get("key"))
        out.append({"id": f"ask:{a.get('id')}", "line": f"{on(c.get('title'), c.get('project'))} wants your permission: {control.one_line(a.get('what') or a.get('tool') or 'a tool', 120)}"})
    for c in talks.values():
        needs = (c.get("says") or {}).get("needs") if isinstance(c.get("says"), dict) else None
        if needs and not c.get("working") and c.get("id") not in asking:
            out.append({"id": f"talk:{c['id']}", "line": f"{on(c.get('title'), c.get('project'))} asks: {control.one_line(needs, 160)}"})
    for t in work["tasks"]:
        if t.get("status") == "needs_you" and not (t.get("session") and t.get("session") in talks):
            out.append({"id": f"task:{t.get('id')}", "line": f"Your task {on(t.get('title'), t.get('project'))}"})
    return out


def moments(data, since, now):
    """The moments from the replay's history files (claude_code.add_moment) between since and now."""
    out = []
    day = datetime.date.fromtimestamp(since)
    while day <= datetime.date.fromtimestamp(now):
        feed = claude_code.read_feed(os.path.join(data, "feeds", "history", day.isoformat() + ".json"))
        out += [m for m in feed.get("moments") or [] if isinstance(m, dict) and since < float(m.get("at") or 0) <= now]
        day += datetime.timedelta(days=1)
    return sorted(out, key=lambda m: m.get("at") or 0)


def happened(data, since, now, work=None):
    """What happened between since and now, in a few sentences, or "" when nothing did."""
    work = work or work_of(data)
    talks = {c.get("id"): c for c in work["conversations"] if c.get("id")}
    last = {}
    for m in moments(data, since, now):
        if m.get("kind") != "left" and m.get("key"):
            last[m["key"]] = m
    out = []
    if last:
        out.append(f"{len(last)} agent{' was' if len(last) == 1 else 's were'} at work.")
    finished, stopped = [], []
    for key, m in last.items():
        c = talks.get(key) or {}
        title = f'"{control.one_line(c.get("title") or m.get("title") or "A conversation", 80)}"'
        if m.get("kind") == "stopped":
            stopped.append(title)
        elif m.get("kind") == "finished":
            review = (c.get("review") or {}).get("state") if isinstance(c.get("review"), dict) else None
            proof = (c.get("proof") or {}).get("state") if isinstance(c.get("proof"), dict) else None
            how = "failed the review line" if review == "failed" else "proven" if proof == "passed" else "not proven" if proof in ("failed", "timeout", "error") else ""
            finished.append(f"{title}{', ' + how if how else ''}")
    if finished:
        more = len(finished) - NAMED
        out.append(f"{'One' if len(finished) == 1 else len(finished)} finished: {'; '.join(finished[:NAMED])}{f'; and {more} more' if more > 0 else ''}.")
    if stopped:
        out.append(f"{'One was' if len(stopped) == 1 else f'{len(stopped)} were'} stopped: {'; '.join(stopped[:NAMED])}.")
    ran = [r for r in work["routines"] if isinstance(r.get("last"), dict) and since < float(r["last"].get("at") or 0) <= now]
    if ran:
        clear = sum(1 for r in ran if r["last"].get("state") == "all clear")
        out.append(f"{len(ran)} routine{'' if len(ran) == 1 else 's'} ran, {clear} all clear.")
    return " ".join(out)


def message(kind, data, since, now, work=None):
    """(title, text, decision ids, quiet) for the brief (kind "brief") or the decisions that came up ("new"). Quiet:
    nothing happened and nothing waits."""
    work = work or work_of(data)
    waiting = decisions(data, work)
    lines = [f"- {d['line']}" for d in waiting[:LISTED]] + ([f"- and {len(waiting) - LISTED} more"] if len(waiting) > LISTED else [])
    when = datetime.datetime.fromtimestamp(since).strftime("%H:%M")
    if kind == "brief":
        news = happened(data, since, now, work)
        text = f"Since {when}: {news}" if news else f"Since {when}, all was quiet."
        text += f"\n\n{'One thing waits' if len(waiting) == 1 else f'{len(waiting)} things wait'} on you:\n" + "\n".join(lines) if waiting else "\n\nNothing is waiting on you."
        return "Arnheim: your morning brief", text, [d["id"] for d in waiting], not news and not waiting
    return (f"Arnheim: {'a decision waits' if len(waiting) == 1 else f'{len(waiting)} decisions wait'} on you",
            "\n".join(lines), [d["id"] for d in waiting], not waiting)


def send(cfg, title, text):
    """Sends one ping. Gives back (arrived, why not)."""
    if "ntfy" in cfg:
        req = urllib.request.Request(cfg["ntfy"], data=text.encode("utf-8"), method="POST",
                                     headers={"Title": title.encode("ascii", "replace").decode("ascii"), "Tags": "office"})
        try:
            with urllib.request.urlopen(req, timeout=SEND_WAIT) as response:
                return 200 <= response.status < 300, None
        except urllib.error.HTTPError as error:
            return False, f"the server said {error.code}"
        except (urllib.error.URLError, OSError, ValueError) as error:
            return False, f"it couldn't be reached: {getattr(error, 'reason', error)}"
    try:
        done = subprocess.run(cfg["run"], input=f"{title}\n{text}\n", capture_output=True, text=True, timeout=SEND_WAIT)
    except (OSError, subprocess.SubprocessError) as error:
        return False, f"the command couldn't run: {error}"
    return done.returncode == 0, None if done.returncode == 0 else f"the command ended with {done.returncode}"


def edit(change, data):
    """Changes data/feeds/pings.json under its lock: change(state) changes it in place and gives back a result."""
    path = os.path.join(data, "feeds", "pings.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with claude_code.Lock(path + ".lock"):
        state = claude_code.read_feed(path)
        out = change(state)
        state["about"] = ABOUT
        state["bundles"] = (state.get("bundles") or [])[-KEEP:]
        part = f"{path}.{os.getpid()}.part"
        with open(part, "w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=1)
        os.replace(part, path)
        return out


def tick(data=None, now=None, force=False):
    """Sends the ping that is due, if any: gives back what was sent, as {title, text, ok, why}, or None."""
    data = data or claude_code.DATA
    now = now or time.time()
    cfg = settings(data)
    if not isinstance(cfg, dict):
        return None
    slot, first = slot_of(cfg["at"], now)

    def change(state):
        since = float(state.get("since") or 0)
        if not since:
            state["since"] = now  # a new setting waits for its first time
            if not force:
                return None
        last = float(state.get("last") or 0)
        if not force and (not slot or slot <= max(last, since)):
            return None
        work = work_of(data)
        sent = set(state.get("sent") or [])
        kind = "brief" if force or first else "new"
        start = last or (now - DAY / 2 if force else since)
        title, text, ids, quiet = message(kind, data, max(start, now - DAY), now, work)
        state["last"] = max(slot, last) if not force else max(now, last)
        state["sent"] = ids
        if not force and (quiet or (kind == "new" and not set(ids) - sent)):
            return None  # a quiet night, or no decision has come up since the last ping
        ok, why = send(cfg, title, text)
        row = {"at": round(now, 1), "title": title, "text": text, "ok": ok}
        if why:
            row["why"] = why
        state.setdefault("bundles", []).append(row)
        return row
    return edit(change, data)


def main():
    parser = argparse.ArgumentParser(description="Pings your phone: the morning brief, and decisions that wait on you.")
    parser.add_argument("--show", action="store_true", help="print what the brief would say now, and send nothing")
    parser.add_argument("--test", action="store_true", help="send a hello now, to check it reaches you")
    parser.add_argument("--now", action="store_true", help="send the brief now")
    args = parser.parse_args()
    data = claude_code.DATA
    cfg = settings(data)
    if args.show:
        title, text, _, _ = message("brief", data, time.time() - DAY / 2, time.time())
        print(f"{title}\n{text}")
        return
    if cfg is None:
        sys.exit('No pings are set. Add "pings" to data/company.json (docs/connect.md, "A morning brief, and pings on your phone").')
    if isinstance(cfg, str):
        sys.exit(cfg)
    if args.test:
        ok, why = send(cfg, "Arnheim: a test", "Arnheim can reach you here. Pings come at " + ", ".join("%02d:%02d" % t for t in cfg["at"]) + ".")
        print("Sent." if ok else f"Not sent: {why}.")
        sys.exit(0 if ok else 1)
    row = tick(data, force=args.now)
    if args.now or os.isatty(1):
        print("Nothing was due." if not row else ("Sent: " if row["ok"] else f"Not sent ({row.get('why')}): ") + row["title"])


if __name__ == "__main__":
    main()
