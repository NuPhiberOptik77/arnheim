#!/usr/bin/env python3
"""OpenAI's Codex CLI in the building (docs/connect.md, "Any agent").

Codex runs a program of your choosing when it finishes a turn: its `notify` setting, in
~/.codex/config.toml:

    notify = ["python3", "/path/to/arnheim/connect/codex.py"]

It hands that program what happened as one JSON argument. This shows the conversation on the floor
whose folder Codex works in, finished and waiting for your next step, through connect/agents.py.
Codex says nothing while it works, so the building only sees it when a turn ends. It prints nothing
and never troubles Codex. Standard library only.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import agents  # noqa: E402  (beside this file)
import claude_code  # noqa: E402


def heard(given):
    """Shows one notification from Codex. Gives back the conversation's key, or None."""
    if not isinstance(given, dict) or given.get("type") != "agent-turn-complete":
        return None
    session = given.get("thread-id") or given.get("session-id") or given.get("turn-id")
    if not session:
        return None
    asked = given.get("input-messages")
    first = asked[0] if isinstance(asked, list) and asked and isinstance(asked[0], str) else None
    return agents.report("Codex", session, given.get("cwd") or os.getcwd(), "finished",
                         str(given.get("last-assistant-message") or ""), title=first)


def main():
    try:
        heard(json.loads(sys.argv[1]) if len(sys.argv) > 1 else None)
    except Exception as error:  # never trouble Codex: note it and carry on
        claude_code.note(error)


if __name__ == "__main__":
    main()
