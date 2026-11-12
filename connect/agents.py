#!/usr/bin/env python3
"""Any agent in the building, not just Claude Code (docs/connect.md, "Any agent").

A command any coding agent, script or tool can run, to show a conversation of its own on the floor
whose folder it works in: at work, asking you something, or finished. It keeps data/feeds/agents.json,
which the building reads like the Claude Code feed, so these sit in the same Conversations rooms,
the same list of what waits on you, and the same replay of the day.

    python3 connect/agents.py --agent Codex --session 42 --cwd ~/code/lantern --state working --says "Fixing the login"
    python3 connect/agents.py --agent Codex --session 42 --cwd ~/code/lantern --state asking --says "Which font?"
    python3 connect/agents.py --agent Codex --session 42 --cwd ~/code/lantern --state finished --says "Fixed it."
    python3 connect/agents.py --agent Codex --session 42 --cwd ~/code/lantern --state ended

--title names the conversation (its first message, say). connect/codex.py uses this for OpenAI's
Codex CLI. Nothing here can answer or start an agent: that needs the agent's own way in, which only
Claude Code has today. Standard library only.
"""
import argparse
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import claude_code  # noqa: E402  (beside this file: floors, the feed's writer and the day's history)

FEED = os.path.join(claude_code.DATA, "feeds", "agents.json")
ABOUT = "Kept up to date by connect/agents.py, for agents other than Claude Code (docs/connect.md). Safe to delete."
STATES = ("working", "asking", "finished", "ended")


def key_of(agent, session):
    clean = lambda text, most: re.sub(r"[^A-Za-z0-9]", "", str(text or ""))[:most].lower()
    return f"ag-{clean(agent, 10) or 'agent'}-{clean(session, 16) or 'one'}"


def report(agent, session, cwd, state, says="", title=None):
    """Shows the agent's conversation as `state`. Gives back its key, or None when its folder is no
    floor's and the building doesn't know it already."""
    if state not in STATES:
        raise ValueError(f"state is one of {', '.join(STATES)}")
    agent = claude_code.line(agent or "An agent", 30)
    key = key_of(agent, session)
    project = claude_code.project_for(cwd)
    said = claude_code.sentences(says) if says else ""
    now = time.time()
    found = {}

    def edit(feed):
        talks = [c for c in feed.get("conversations") or [] if isinstance(c, dict) and now - float(c.get("at") or 0) <= claude_code.KEEP]
        tasks = [t for t in feed.get("tasks") or [] if isinstance(t, dict) and t.get("session") in {c.get("id") for c in talks}]
        talk = next((c for c in talks if c.get("id") == key), None)
        where = project or (talk or {}).get("project")
        if not where:
            return None  # not this company's work
        ask = f"{key}-ask"
        tasks = [t for t in tasks if t.get("id") != ask]
        if state == "ended":
            if talk:
                claude_code.add_moment(talk, where, "left", "The conversation ended.")
            found["key"] = key
            return [c for c in talks if c.get("id") != key], [t for t in tasks if t.get("session") != key]
        if talk is None:
            talk = {"id": key, "agent": agent, "title": claude_code.line(title or said or f"{agent} at work", 70)}
            talks.append(talk)
        elif title:
            talk["title"] = claude_code.line(title, 70)
        talk.update(project=where, agent=agent, at=now)
        if state == "working":
            talk.update(working=True, check=False, says={"now": said or "I'm working on it."})
        elif state == "asking":
            talk.update(working=False, check=True, says={"now": said, "needs": said or f"{agent} is waiting for you."})
            tasks.append({"id": ask, "session": key, "project": where, "status": "needs_you",
                          "title": claude_code.line(f"{talk['title']}: {said or 'waiting for you'}", 120), "note": said})
        else:
            talk.update(working=False, check=True, stopped=now, says={"now": said or "I've finished for now.", "next": "It's your turn now."})
        claude_code.add_moment(talk, where, {"working": "working", "asking": "asked", "finished": "finished"}[state],
                               said or talk["says"].get("needs") or talk["says"]["now"])
        found["key"] = key
        return talks, tasks

    claude_code.edit_feed(edit, FEED, ABOUT)
    return found.get("key")


def main():
    parser = argparse.ArgumentParser(description="Shows any agent's conversation in the building (docs/connect.md, \"Any agent\").")
    parser.add_argument("--agent", required=True, help="the agent's name, such as Codex")
    parser.add_argument("--session", required=True, help="the conversation's own id, the same each time")
    parser.add_argument("--cwd", default=os.getcwd(), help="the folder it works in (here, if left out)")
    parser.add_argument("--state", required=True, choices=STATES)
    parser.add_argument("--says", default="", help="what it said or asks, in a sentence or two")
    parser.add_argument("--title", help="what the conversation is about")
    args = parser.parse_args()
    try:
        key = report(args.agent, args.session, args.cwd, args.state, args.says, args.title)
    except Exception as error:  # an agent's own work never waits on the building
        claude_code.note(error)
        return
    if key is None:
        print("That folder isn't one of the building's floors, so nothing was shown. Give a floor that folder in data/company.json.", file=sys.stderr)


if __name__ == "__main__":
    main()
