#!/usr/bin/env python3
"""Arnheim's git and GitHub connector: each floor's unsaved changes and open pull requests.

  python3 connect/projects.py               look once
  python3 connect/projects.py --every 60    look every minute, until Ctrl-C
  python3 connect/projects.py --no-github   leave out pull requests

For every floor with a "folder" in data/company.json, it asks git how many files have changes not
yet committed (a crate in the floor's Code room) and, if GitHub's `gh` command is installed and
signed in, which pull requests are open (books on its shelves). It writes data/feeds/projects.json,
which the page reads every few seconds (docs/connect.md). It only reads: it never changes a
repository. Standard library only; git, and gh if you want pull requests.
"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.realpath(__file__))
DATA = os.environ.get("ARNHEIM_DATA") or os.path.join(os.path.dirname(HERE), "data")
FEED = os.path.join(DATA, "feeds", "projects.json")


def run(args, folder, timeout=20):
    """A command's output, or None if it isn't there or fails. Fixed arguments, no shell."""
    try:
        done = subprocess.run(args, cwd=folder, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout if done.returncode == 0 else None


def floors():
    """(floor id, project, folder) for every floor that names a folder."""
    with open(os.path.join(DATA, "company.json"), encoding="utf-8-sig") as handle:
        company = json.load(handle)
    out = []
    for floor in company.get("floors") or []:
        if not isinstance(floor, dict):
            continue
        folders = floor.get("folders") or ([floor["folder"]] if floor.get("folder") else [])
        for folder in folders if isinstance(folders, list) else []:
            out.append((str(floor.get("id")), floor.get("project") or floor.get("label"), os.path.expanduser(str(folder))))
    return out


def look(github=True):
    copies, prs, notes = [], [], []
    found = floors()
    if not found:
        notes.append("no floor names a folder yet: add \"folder\" to a floor in data/company.json (docs/connect.md)")
    for floor_id, project, folder in found:
        name = os.path.basename(os.path.normpath(folder)) or folder
        if not os.path.isdir(folder):
            notes.append(f"{name}: the folder isn't there")
            continue
        status = run(["git", "status", "--porcelain", "--", "."], folder)  # this folder's changes only
        if status is None:
            notes.append(f"{name}: not a git repository")
            continue
        changes = len([row for row in status.splitlines() if row.strip()])
        branch = (run(["git", "branch", "--show-current"], folder) or "").strip()
        if changes:
            copies.append({"id": f"git-{floor_id}-{name}", "project": project, "name": f"{name} on {branch}" if branch else name, "changes": changes})
        if github:
            listed = run(["gh", "pr", "list", "--json", "number,title,isDraft", "--limit", "30"], folder)
            if listed is None:
                notes.append(f"{name}: no pull requests (gh is missing, signed out, or the repository isn't on GitHub)")
                continue
            try:
                listed = json.loads(listed or "[]")
            except ValueError:
                listed = []
            for pr in listed if isinstance(listed, list) else []:
                if isinstance(pr, dict) and "number" in pr:
                    prs.append({"number": pr["number"], "project": project, "title": str(pr.get("title") or ""), "draft": bool(pr.get("isDraft"))})
    return {"copies": copies, "pullRequests": prs}, notes


def write(feed):
    os.makedirs(os.path.dirname(FEED), exist_ok=True)
    out = {"about": "Kept up to date by connect/projects.py, from git and GitHub (docs/connect.md). Safe to delete.", **feed}
    part = f"{FEED}.{os.getpid()}.part"
    with open(part, "w", encoding="utf-8") as handle:
        json.dump(out, handle, ensure_ascii=False, indent=1)
    os.replace(part, FEED)  # whole, so the page never reads half a file


def main():
    parser = argparse.ArgumentParser(description="Shows each floor's unsaved changes and open pull requests in Arnheim.")
    parser.add_argument("--every", type=float, metavar="SECONDS", help="look again every so many seconds, until Ctrl-C")
    parser.add_argument("--no-github", action="store_true", help="leave out pull requests")
    args = parser.parse_args()
    if not os.path.isfile(os.path.join(DATA, "company.json")):
        sys.exit("There is no data/company.json yet. Make your company first (README, \"Make it yours\").")
    said = set()
    try:
        while True:
            try:
                feed, notes = look(github=not args.no_github)
            except (OSError, ValueError) as error:
                print(f"data/company.json can't be read: {error}", file=sys.stderr)
                feed, notes = None, []
            if feed is not None:
                write(feed)
                print(f"{time.strftime('%H:%M:%S')} {len(feed['copies'])} with unsaved changes, {len(feed['pullRequests'])} open pull requests", flush=True)
            for note in notes:
                if note not in said:
                    said.add(note)
                    print(f"  {note}", flush=True)
            if not args.every:
                break
            time.sleep(max(5.0, args.every))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
