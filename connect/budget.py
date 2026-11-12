"""A budget per floor, with a brake (docs/connect.md, "A budget per floor").

What each Claude Code conversation spends, counted from its own transcript as the hook runs
(connect/claude_code.py): the new tokens of each reply, that is what Claude read fresh, wrote to its
cache, and wrote back. Re-reading its cache is left out: that is the same context again. A reply is
logged once for each of its parts, so each is counted once, by its id, on the day it was written.

A floor in data/company.json can give its agents a budget for a day, in new tokens ("budget":
2000000), or the company can give every floor one. When a floor's agents pass it, the hook stops the
one at work at its next step, once, and asks you whether they may go on ("Let them go on" in the
building gives them as much again, for today). Standard library only.
"""
import datetime
import json
import os

COUNTED = ("input_tokens", "cache_creation_input_tokens", "output_tokens")
FIRST_READ = 64 * 1024 * 1024  # a transcript met for the first time is read from at most this far back


def local_day(stamp=None):
    """The day on this computer's clock, as 2026-11-12: now, or when an ISO time was."""
    if stamp:
        try:
            return datetime.datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d")
        except ValueError:
            pass
    return datetime.datetime.now().strftime("%Y-%m-%d")


def new_tokens(path, read):
    """New tokens in a transcript since it was last read: ({day: tokens}, where it has been read to).
    `read` is what this gave back last time ({"path", "at", "last"}), or {}."""
    read = read if isinstance(read, dict) and read.get("path") == path else {}
    try:
        size = os.path.getsize(path)
    except (OSError, TypeError, ValueError):
        return {}, read
    start = read.get("at") if isinstance(read.get("at"), int) else 0
    last = read.get("last")
    if start > size:  # a new file under the old name
        start, last = 0, None
    if not start and size > FIRST_READ:
        start = size - FIRST_READ
    spent = {}
    with open(path, "rb") as handle:
        handle.seek(start)
        if start and not read:
            start += len(handle.readline())  # from the start of a whole line
        for raw in handle:
            if not raw.endswith(b"\n"):
                break  # still being written: read it next time
            start += len(raw)
            if b'"usage"' not in raw:
                continue
            try:
                row = json.loads(raw)
            except ValueError:
                continue
            message = row.get("message") if isinstance(row, dict) and row.get("type") == "assistant" else None
            if not isinstance(message, dict) or not isinstance(message.get("usage"), dict):
                continue
            if message.get("id") and message["id"] == last:
                continue  # another part of the reply just counted
            last = message.get("id")
            n = 0
            for key in COUNTED:
                try:
                    n += max(0, int(message["usage"].get(key) or 0))
                except (TypeError, ValueError):
                    pass
            day = local_day(row.get("timestamp"))
            spent[day] = spent.get(day, 0) + n
    return spent, {"path": path, "at": start, "last": last}


def budget_of(company, project):
    """A floor's budget for a day in new tokens, or the company's for every floor, or None."""
    floors = company.get("floors") if isinstance(company, dict) else None
    floor = next((f for f in floors or [] if isinstance(f, dict) and str(f.get("project") or f.get("label") or "") == project), None)
    for given in ((floor or {}).get("budget"), company.get("budget") if isinstance(company, dict) else None):
        if isinstance(given, (int, float)) and not isinstance(given, bool) and given > 0:
            return int(given)
    return None


def spent_today(talks, project, day, ended=None):
    """What a floor's conversations have spent on `day`, with what those that left the feed today spent
    (`ended`, the feed's, from leave())."""
    total = 0
    for c in talks:
        spent = c.get("spent") if isinstance(c, dict) and c.get("project") == project else None
        if isinstance(spent, dict) and spent.get("day") == day and isinstance(spent.get("tokens"), int):
            total += spent["tokens"]
    if isinstance(ended, dict) and ended.get("day") == day and isinstance(ended.get("talks"), dict):
        for t in ended["talks"].values():
            if isinstance(t, dict) and t.get("project") == project and isinstance(t.get("tokens"), int):
                total += t["tokens"]
    return total


def leave(feed, talks, day):
    """Conversations leaving the feed (ended, or not heard from for long): what each spent today, and how
    far its transcript was read, kept in the feed's "ended" for the day, so the floor's total still counts
    them and one that comes back carries on from there (come_back)."""
    ended = feed.get("ended") if isinstance(feed.get("ended"), dict) and feed["ended"].get("day") == day else {}
    kept = dict(ended["talks"]) if isinstance(ended.get("talks"), dict) else {}
    for c in talks:
        spent = c.get("spent") if isinstance(c.get("spent"), dict) else {}
        tokens = spent.get("tokens") if spent.get("day") == day and isinstance(spent.get("tokens"), int) else 0
        if c.get("id") and tokens > 0:
            kept[c["id"]] = {"project": c.get("project"), "tokens": tokens, "read": c.get("read")}
    feed["ended"] = {"day": day, "talks": kept}


def come_back(feed, key, day):
    """A conversation back in the feed today: what it had spent and read when it left, or None."""
    ended = feed.get("ended") if isinstance(feed.get("ended"), dict) and feed["ended"].get("day") == day else None
    talks = ended.get("talks") if ended and isinstance(ended.get("talks"), dict) else {}
    back = talks.pop(key, None)
    return back if isinstance(back, dict) else None


def tokens(n):
    """1,200,000 as 1.2 million, for people."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}".rstrip("0").rstrip(".") + " million"
    if n >= 1000:
        return f"{round(n / 1000)} thousand"
    return str(n)
