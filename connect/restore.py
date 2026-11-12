#!/usr/bin/env python3
"""Restore points: a project's files as they were just before an agent changed them, so you can go back
(docs/connect.md, "Restore points").

The hook (connect/claude_code.py) takes one before the first file an agent changes after each message
you send it, and before any command that deletes or overwrites files in bulk (rm -r, git reset --hard,
git clean and the like). Each is a git commit of every file in the project's folder that git doesn't
ignore, saved under refs/arnheim/restore/: your branch, what you have staged and your files are left as
they are, and `git log` shows nothing new unless you ask for --all. The last 40 are kept; older ones
are let go, and git tidies them away in its own time.

Going back (from the building, with control on: connect/control.py) puts the files as they were at that
point: the ones changed since are put back, the ones deleted since come back, and the ones made since
are left where they are, and listed. It takes a restore point of how things are first, so going back can
be undone too. It refuses while an agent is at work on that floor.

Nothing here runs a command built from what an agent did: every git call is a fixed list of arguments,
and the only things that come from outside are a commit this file made and the paths git itself lists.
Standard library only. A folder that isn't in git gets no restore points.
"""
import json
import os
import re
import subprocess
import tempfile
import time

HERE = os.path.dirname(os.path.realpath(__file__))
DATA = os.environ.get("ARNHEIM_DATA") or os.path.join(os.path.dirname(HERE), "data")
REF = "refs/arnheim/restore/"
KEEP = 40  # restore points kept, across the company
POINT = re.compile(r"^rp-[0-9a-f]{12}$")
COMMIT = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")  # sha-1, or sha-256
WAIT = 20  # seconds a git call may take at most: past that, no restore point, and the agent goes on
# Commands that delete or overwrite many files at once: a restore point first, every time.
RISKY = re.compile(
    r"(?:^|[\s;&|(`])(?:"
    r"rm\s+(?:-[a-zA-Z]*[rR]|--recursive)"            # rm -r, rm -rf, rm -fr
    r"|git\s+(?:reset\s+(?:\S+\s+)*--hard"             # git reset --hard
    r"|clean\s+(?:\S+\s+)*-[a-zA-Z]*f"                 # git clean -f, -fd, -xdf
    r"|checkout\s+(?:\S+\s+)*(?:--\s|\.(?:\s|$))"      # git checkout -- file, git checkout .
    r"|restore\s|stash(?:\s|$)|switch\s+(?:\S+\s+)*(?:-f|--force|--discard-changes))"
    r"|find\s.*\s-delete\b"
    r"|truncate\s"
    r")")
GIT_ENV = {  # who the restore points' commits are by: never the person's own name
    "GIT_AUTHOR_NAME": "Arnheim restore point", "GIT_AUTHOR_EMAIL": "restore@arnheim.invalid",
    "GIT_COMMITTER_NAME": "Arnheim restore point", "GIT_COMMITTER_EMAIL": "restore@arnheim.invalid",
    "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0",
}


class Lock:
    """One writer at a time: hooks for several conversations run at once."""

    def __init__(self, path):
        self.path = path

    def __enter__(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.handle = open(self.path, "a")
        try:
            import fcntl
            fcntl.flock(self.handle, fcntl.LOCK_EX)
        except ImportError:  # Windows has no flock; a clash there costs one restore point's record at most
            pass
        return self

    def __exit__(self, *_):
        self.handle.close()


def git(repo, *args, env=None, data=False):
    """Runs git in repo with fixed arguments: its output as text (bytes with data=True), or None if it failed."""
    try:
        done = subprocess.run(["git", "-C", repo, *args], capture_output=True, stdin=subprocess.DEVNULL, timeout=WAIT,
                              env={**os.environ, **GIT_ENV, **(env or {})})
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    return done.stdout if data else done.stdout.decode("utf-8", "replace").strip()


def top(folder):
    """The top folder of the git repository folder is in, or None if it isn't in one."""
    folder = os.path.realpath(os.path.expanduser(str(folder or "")))
    if not os.path.isdir(folder):
        return None
    found = git(folder, "rev-parse", "--show-toplevel")
    return os.path.realpath(found) if found else None


def folders_of(project, data=DATA):
    """The folders of the floor whose project (or label) this is, as data/company.json gives them."""
    try:
        with open(os.path.join(data, "company.json"), encoding="utf-8-sig") as handle:
            company = json.load(handle)
    except (OSError, ValueError):
        return []
    for floor in company.get("floors") or [] if isinstance(company, dict) else []:
        if isinstance(floor, dict) and project and str(floor.get("project") or floor.get("label") or "") == project:
            folders = floor.get("folders") or ([floor["folder"]] if floor.get("folder") else [])
            return [os.path.realpath(os.path.expanduser(str(f))) for f in folders if f] if isinstance(folders, list) else []
    return []


def where(repo, project, data=DATA):
    """The repository as a path from its floor's folder ("." when they are the same), so the feed never
    holds this computer's own folders; None if it isn't near any of them."""
    for folder in folders_of(project, data):
        rel = os.path.relpath(repo, folder)
        if rel == "." or not rel.startswith("..") or folder.startswith(repo.rstrip(os.sep) + os.sep):
            return rel
    return None


def found_repo(point, data=DATA):
    """The repository a restore point was taken in, from its floor's folders, or None."""
    rel = point.get("repo")
    if not isinstance(rel, str) or os.path.isabs(rel):
        return None
    for folder in folders_of(point.get("project"), data):
        repo = top(os.path.join(folder, rel))
        if repo and os.path.realpath(os.path.join(folder, rel)) == repo:
            return repo
    return None


def feed_path(data=DATA):
    return os.path.join(data, "feeds", "restore.json")


def read_points(data=DATA):
    try:
        with open(feed_path(data), encoding="utf-8") as handle:
            rows = json.load(handle).get("restore")
    except (OSError, ValueError, AttributeError):
        return []
    return [row for row in rows if isinstance(row, dict) and POINT.match(str(row.get("id") or ""))] if isinstance(rows, list) else []


def snapshot(repo, message):
    """Every file git doesn't ignore, as a commit on top of HEAD, made through an index of its own so the
    real one is untouched: (commit, how many files differ from HEAD), or None."""
    gitdir = git(repo, "rev-parse", "--absolute-git-dir")
    index = git(repo, "rev-parse", "--git-path", "index")
    if not gitdir or not index:
        return None
    index = os.path.join(repo, index)  # as given from the repository's top, unless it is absolute already
    handle, temp = tempfile.mkstemp(prefix="arnheim-restore-", dir=gitdir)
    try:
        with os.fdopen(handle, "wb") as out:
            try:
                with open(index, "rb") as real:  # git's own record of what it has seen, so only changed files are read again
                    out.write(real.read())
            except OSError:
                pass  # a repository with nothing added yet
        env = {"GIT_INDEX_FILE": temp}
        if git(repo, "add", "-A", "--", ".", env=env) is None:
            return None
        tree = git(repo, "write-tree", env=env)
    finally:
        try:
            os.remove(temp)
        except OSError:
            pass
    if not tree:
        return None
    head = git(repo, "rev-parse", "-q", "--verify", "HEAD^{commit}")
    commit = git(repo, "commit-tree", tree, *(["-p", head] if head else []), "-m", message)
    if not commit or not COMMIT.match(commit):
        return None
    changed = git(repo, "diff", "--name-only", "-z", head, tree, data=True) if head else git(repo, "ls-tree", "-r", "--name-only", "-z", tree, data=True)
    return commit, len([p for p in (changed or b"").split(b"\0") if p])


def take(folder, why, key="", project="", title="", by="agent", data=DATA, now=None):
    """A restore point of the repository folder is in, kept in data/feeds/restore.json: the point, or None
    (not in git, git missing or too slow, or the folder near no floor of the company)."""
    now = now or time.time()
    repo = top(folder)
    if not repo:
        return None
    rel = where(repo, project, data)
    if rel is None:
        return None
    made = snapshot(repo, f"Arnheim restore point: {why}")
    if not made:
        return None
    commit, files = made
    stamp = str(int(now * 1000))
    if git(repo, "update-ref", REF + stamp, commit) is None:
        return None
    point = {"id": "rp-" + commit[:12], "ref": stamp, "commit": commit, "repo": rel, "project": project, "key": key,
             "title": " ".join(str(title or "").split())[:80], "why": " ".join(str(why or "").split())[:160], "by": by,
             "at": round(now, 1), "files": files}
    path = feed_path(data)
    with Lock(path + ".lock"):
        rows = [row for row in read_points(data) if row.get("id") != point["id"]] + [point]
        rows.sort(key=lambda row: row.get("at") or 0)
        dropped, rows = rows[:-KEEP], rows[-KEEP:]
        part = f"{path}.{os.getpid()}.part"
        with open(part, "w", encoding="utf-8") as handle:
            json.dump({"about": "Restore points: the files as they were before an agent changed them (docs/connect.md, "
                                "\"Restore points\"). Kept by connect/restore.py. Safe to delete: the points are then forgotten.",
                       "restore": rows}, handle, ensure_ascii=False, indent=1)
        os.replace(part, path)
    for old in dropped:  # let go of the oldest: git tidies their files away in its own time
        repo_of = found_repo(old, data)
        if repo_of and re.match(r"^\d{1,16}$", str(old.get("ref") or "")):
            git(repo_of, "update-ref", "-d", REF + old["ref"])
    return point


def risky(command):
    """Whether a shell command deletes or overwrites files in bulk."""
    return bool(RISKY.search(" " + str(command or "")))


def names(raw):
    return [p.decode("utf-8", "replace") for p in (raw or b"").split(b"\0") if p]


def go_back(point, data=DATA, now=None):
    """Puts the files as they were at a restore point. A restore point of how they are now is taken first.
    Gives {"kept": that point's id or None, "left": files made since, which stay, "more": how many more},
    or raises ValueError with why it can't."""
    commit = str(point.get("commit") or "")
    if not COMMIT.match(commit):
        raise ValueError("That restore point can't be read.")
    repo = found_repo(point, data)
    if not repo:
        raise ValueError("Its project's folder isn't where it was, so it can't go back.")
    if git(repo, "cat-file", "-e", commit + "^{commit}") is None:
        raise ValueError("That restore point has gone from its project's git.")
    clock = time.strftime("%H:%M", time.localtime(point.get("at") or 0))
    kept = take(repo, f"before going back to {clock}", key="", project=point.get("project") or "", title="You, from the building",
                by="you", data=data, now=now)
    if git(repo, "restore", f"--source={commit}", "--worktree", "--", ".") is None:
        raise ValueError("Git couldn't put the files back. Nothing was changed by Arnheim; look in the project's folder.")
    then = set(names(git(repo, "ls-tree", "-r", "--name-only", "-z", commit, data=True)))
    made = [p for p in names(git(repo, "ls-files", "--others", "--exclude-standard", "-z", data=True)) if p not in then]
    return {"kept": kept and kept["id"], "left": made[:10], "more": max(0, len(made) - 10)}
