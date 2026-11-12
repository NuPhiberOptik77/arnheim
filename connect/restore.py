#!/usr/bin/env python3
"""Restore points: a floor's files as they were just before an agent changed them, so you can go back
(docs/connect.md, "Restore points").

The hook (connect/claude_code.py) takes one before the first file an agent changes after each message
you send it, and before any command that deletes or overwrites files in bulk (rm -r, git reset --hard,
git clean and the like). Each is a git commit of the files in the floor's folder that git doesn't ignore,
saved under refs/arnheim/restore/ in the project's repository: your branch, what you have staged and
your files are left as they are, and `git log` shows nothing new unless you ask for --all. Files that look
like keys, passwords or tokens (SECRETS) are never saved in one. The last 40 are kept; older ones are let
go, and git tidies them away in its own time.

Going back (from the building, with control on: connect/control.py) puts every file the point holds as it
was then: the ones changed since are put back and the ones deleted since come back. Files that weren't
there then, made or added since, are left where they are, and listed. It takes a restore point of how
things are first, so going back can be undone too. It refuses while an agent on that folder is at work
or waiting on you.

Saving keeps an index of its own for each floor, so after the first, only files that changed are read
again. A folder too big to save within WAIT seconds gets no restore points for SLOW_FOR, so it doesn't
hold its agents up each time; keep big folders in .gitignore.

Nothing here runs a command built from what an agent did: every git call is a fixed list of arguments,
and the only things that come from outside are a commit this file made and paths git itself lists, passed
as literal paths. Standard library only. A folder that isn't in git gets no restore points.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import time

HERE = os.path.dirname(os.path.realpath(__file__))
DATA = os.environ.get("ARNHEIM_DATA") or os.path.join(os.path.dirname(HERE), "data")
REF = "refs/arnheim/restore/"
KEEP = 40  # restore points kept, across the company
POINT = re.compile(r"^rp-[0-9a-f]{12}$")
COMMIT = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")  # sha-1, or sha-256
WAIT = 20  # seconds a git call may take at most: past that, no restore point, and the agent goes on
SLOW_FOR = 6 * 3600  # seconds a folder too big to save in time goes without restore points
# Commands that delete or overwrite many files at once: a restore point first, every time.
_PATH = r"(?:\S*/)?"  # rm, or /bin/rm
_GIT = r"git\s+(?:(?:-C|-c|--git-dir|--work-tree)\s+\S+\s+|--?[\w-]+(?:=\S+)?\s+)*"  # git, with its own options first
RISKY = re.compile(
    r"(?:^|[\s;&|(`])(?:"
    + _PATH + r"rm\s+(?:-\S+\s+)*(?:-[a-zA-Z]*[rR][a-zA-Z]*|--recursive)\b"  # rm -r, -rf, -f -r, -v -rf
    + r"|" + _GIT + r"(?:reset\s+(?:\S+\s+)*--hard"                          # git reset --hard
    + r"|clean\s+(?:\S+\s+)*-[a-zA-Z]*f"                                       # git clean -f, -fd, -xdf
    + r"|checkout\s+(?:\S+\s+)*(?:--\s|\.(?:\s|$)|-f\b|--force\b)"            # git checkout -- file, git checkout .
    + r"|restore\s+(?!(?:--staged|-S)\s+[^-\s])"                               # git restore, but not --staged alone
    + r"|stash(?:\s+(?:push|save|-\S+))*(?:\s*$|\s*[;&|)])"                    # git stash, push or save: not list, show
    + r"|switch\s+(?:\S+\s+)*(?:-f|--force|--discard-changes))"
    + r"|find\s.*\s-delete\b"
    + r"|rsync\s.*--delete"
    + r"|truncate\s"
    + r")")
# Never saved in a restore point, so never in the project's git unless it is there already: files that hold keys,
# passwords or tokens by their kind or name. Going back leaves them as they are.
SECRETS = (".env", ".env.*", "*.env", "*.pem", "*.key", "*.p8", "*.p12", "*.pfx", "*.keystore", "*.jks", "*.kdbx", "*.ovpn", "*.ppk",
           "id_rsa*", "id_dsa*", "id_ecdsa*", "id_ed25519*", ".netrc", ".npmrc", ".pypirc", ".pgpass", ".git-credentials",
           "credentials", "credentials.*", "*-credentials.*", "*_credentials.*", "secrets.*", "*.secret", "*.secrets",
           "client_secret*", "service-account*.json", "*service_account*.json", ".ssh/**", ".aws/**", ".gnupg/**")
NOT_SECRETS = [f":(top,exclude,glob,icase)**/{p}" for p in SECRETS]
GIT_ENV = {  # who the restore points' commits are by: never the person's own name
    "GIT_AUTHOR_NAME": "Arnheim restore point", "GIT_AUTHOR_EMAIL": "restore@arnheim.invalid",
    "GIT_COMMITTER_NAME": "Arnheim restore point", "GIT_COMMITTER_EMAIL": "restore@arnheim.invalid",
    "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0",
}


class Lock:
    """One at a time: hooks for several conversations run at once."""

    def __init__(self, path):
        self.path = path

    def __enter__(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.handle = open(self.path, "a")
        try:
            import fcntl
            fcntl.flock(self.handle, fcntl.LOCK_EX)
        except ImportError:  # Windows has no flock; a clash there costs one restore point at most
            pass
        return self

    def __exit__(self, *_):
        self.handle.close()


class TooSlow(Exception):
    pass


def git(repo, *args, env=None, data=False, given=None):
    """Runs git in repo with fixed arguments: its output as text (bytes with data=True), or None if it failed.
    Raises TooSlow past WAIT seconds."""
    try:
        done = subprocess.run(["git", "-C", repo, *args], capture_output=True, input=given, stdin=None if given is not None else subprocess.DEVNULL,
                              timeout=WAIT, env={**os.environ, **GIT_ENV, **(env or {})})
    except subprocess.TimeoutExpired as error:
        raise TooSlow() from error
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
    try:
        found = git(folder, "rev-parse", "--show-toplevel")
    except TooSlow:
        return None
    return os.path.realpath(found) if found else None


def inside(path, folder):
    return path == folder or path.startswith(folder.rstrip(os.sep) + os.sep)


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


def placed(folder, project, data=DATA):
    """Where a restore point of folder goes: (repository, the floor's folder holding folder, what of the repository it
    covers: "." or the floor's folder inside it), or None if folder isn't in git or in any of the floor's folders."""
    here = os.path.realpath(os.path.expanduser(str(folder or "")))
    floor = max((f for f in folders_of(project, data) if inside(here, f)), key=len, default=None)
    repo = top(here)
    if not floor or not repo:
        return None
    if inside(floor, repo):
        return repo, floor, os.path.relpath(floor, repo)  # the floor's folder, inside a bigger repository
    return (repo, floor, ".") if inside(repo, floor) else None


def scope_spec(scope):
    return ":(top)" if scope == "." else f":(top,literal){scope}"


def found_repo(point, data=DATA):
    """The repository a restore point was taken in, from its floor's folders, or None: only one that holds the
    floor's folder or is inside it."""
    rel = point.get("repo")
    if not isinstance(rel, str) or os.path.isabs(rel):
        return None
    for folder in folders_of(point.get("project"), data):
        want = os.path.realpath(os.path.join(folder, rel))
        if not (inside(want, folder) or inside(folder, want)):
            continue
        repo = top(want)
        if repo and repo == want:
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


def snapshot(repo, scope, message):
    """The files of scope that git doesn't ignore, secrets left out, as a commit on top of HEAD: (commit, how many
    files of scope differ from HEAD), or None. Made through an index of Arnheim's own for that scope, so the real
    one is untouched and, after the first time, only changed files are read again. Raises TooSlow."""
    gitdir = git(repo, "rev-parse", "--absolute-git-dir")
    if not gitdir:
        return None
    head = git(repo, "rev-parse", "-q", "--verify", "HEAD^{commit}")
    mine = os.path.join(gitdir, "arnheim-restore", hashlib.sha1(scope.encode()).hexdigest()[:12])
    os.makedirs(mine, exist_ok=True)
    index = os.path.join(mine, "index")
    env = {"GIT_INDEX_FILE": index}
    with Lock(os.path.join(mine, "lock")):
        try:
            if os.path.exists(index + ".lock"):  # one stopped mid-way, under this same lock: it left its lock behind
                os.remove(index + ".lock")
            real = os.path.join(repo, git(repo, "rev-parse", "--git-path", "index") or ".git/index")
            if not os.path.isfile(index) and os.path.isfile(real):  # the first time: from the real index, so git knows its files
                shutil.copyfile(real, index)
            # A file this index holds that git now ignores and the real index doesn't track: let it go.
            ignored = names(git(repo, "ls-files", "-z", "--cached", "--ignored", "--exclude-standard", "--", scope_spec(scope), env=env, data=True))
            if ignored:
                tracked = set(names(git(repo, "ls-files", "-z", "--cached", "--", scope_spec(scope), data=True)))
                drop = [p for p in ignored if p not in tracked]
                if drop:
                    git(repo, "rm", "-r", "--cached", "-q", "--ignore-unmatch", "--pathspec-from-file=-", "--pathspec-file-nul",
                        env={**env, "GIT_LITERAL_PATHSPECS": "1"}, given=b"\0".join(p.encode("utf-8", "surrogateescape") for p in drop))
            if git(repo, "add", "-A", "--", scope_spec(scope), *NOT_SECRETS, env=env) is None:
                return None
            tree = git(repo, "write-tree", env=env)
        except TooSlow:
            if os.path.exists(index + ".lock"):  # git was stopped mid-way: it leaves its lock
                os.remove(index + ".lock")
            raise
    if not tree:
        return None
    commit = git(repo, "commit-tree", tree, *(["-p", head] if head else []), "-m", message)
    if not commit or not COMMIT.match(commit):
        return None
    where = [] if scope == "." else ["--", scope]
    changed = (git(repo, "diff", "--name-only", "-z", head, tree, *where, data=True) if head
               else git(repo, "ls-tree", "-r", "--name-only", "-z", "--full-tree", tree, *where, data=True))
    return commit, len([p for p in (changed or b"").split(b"\0") if p])


def slow_mark(repo):
    gitdir = git(repo, "rev-parse", "--absolute-git-dir")
    return os.path.join(gitdir, "arnheim-restore", "slow") if gitdir else None


def take(folder, why, key="", project="", title="", by="agent", data=DATA, now=None):
    """A restore point of the floor's folder that holds folder, kept in data/feeds/restore.json: the point, or None
    (not in git, git missing, too slow lately, or the folder in none of the floor's folders)."""
    now = now or time.time()
    where = placed(folder, project, data)
    if not where:
        return None
    repo, floor, scope = where
    mark = slow_mark(repo)
    try:
        if mark and now - os.path.getmtime(mark) < SLOW_FOR:
            return None  # too big to save in time, lately: the agent isn't held up again
    except OSError:
        pass
    try:
        made = snapshot(repo, scope, f"Arnheim restore point: {why}")
    except TooSlow:
        if mark:
            with open(mark, "w", encoding="utf-8") as handle:
                handle.write(f"No restore points until {time.ctime(now + SLOW_FOR)}: saving took over {WAIT} seconds.\n")
        return None
    if not made:
        return None
    commit, files = made
    point = {"id": "rp-" + commit[:12], "commit": commit, "repo": os.path.relpath(repo, floor), "scope": scope, "project": project,
             "key": key, "title": " ".join(str(title or "").split())[:80], "why": " ".join(str(why or "").split())[:160], "by": by,
             "at": round(now, 1), "files": files}
    path = feed_path(data)
    with Lock(path + ".lock"):  # the refs too, so one hook never lets go of another's new point
        rows = [row for row in read_points(data) if row.get("id") != point["id"]] + [point]
        rows.sort(key=lambda row: row.get("at") or 0)
        rows = rows[-KEEP:]
        try:
            git(repo, "update-ref", REF + commit, commit)
            part = f"{path}.{os.getpid()}.part"
            with open(part, "w", encoding="utf-8") as handle:
                json.dump({"about": "Restore points: the files as they were before an agent changed them (docs/connect.md, "
                                    "\"Restore points\"). Kept by connect/restore.py. Safe to delete: the points are then forgotten.",
                           "restore": rows}, handle, ensure_ascii=False, indent=1)
            os.replace(part, path)
            kept = {row.get("commit") for row in rows}
            # Let go of this repository's points that aren't kept: older ones, and any from a floor since renamed
            # or moved, or from before restore.json was deleted. git tidies their files away in its own time.
            for line in (git(repo, "for-each-ref", "--format=%(refname) %(objectname)", REF) or "").splitlines():
                name, _, target = line.partition(" ")
                if target not in kept and name.startswith(REF):
                    git(repo, "update-ref", "-d", name)
        except TooSlow:
            return None
    return point


def risky(command):
    """Whether a shell command deletes or overwrites files in bulk."""
    return bool(RISKY.search(" " + str(command or "")))


def names(raw):
    return [p.decode("utf-8", "surrogateescape") for p in (raw or b"").split(b"\0") if p]


def scope_dir(point, data=DATA):
    """The folder a restore point covers, or None."""
    repo = found_repo(point, data)
    scope = point.get("scope") or "."
    if not repo or not isinstance(scope, str) or os.path.isabs(scope) or ".." in scope.split("/"):
        return None
    return os.path.realpath(os.path.join(repo, scope))


def busy(point, conversations, asking=(), data=DATA):
    """The projects whose agents, at work or waiting on you mid-turn, share a folder with the point's: going back
    waits for them. asking: conversation keys with a permission request waiting."""
    covered = scope_dir(point, data)
    out = []
    for c in conversations:
        if not isinstance(c, dict) or not (c.get("working") or (c.get("says") or {}).get("needs") or c.get("id") in asking):
            continue
        project = c.get("project")
        if project == point.get("project") or (covered and any(inside(f, covered) or inside(covered, f) for f in folders_of(project, data))):
            if project not in out:
                out.append(project)
    return out


def go_back(point, data=DATA, now=None):
    """Puts every file the restore point holds as it was then; files it doesn't hold are left. A restore point of
    how things are now is taken first. Gives {"kept": that point's id or None, "left": files that weren't there then
    and stay, "more": how many more}, or raises ValueError with why it can't."""
    commit = str(point.get("commit") or "")
    if not COMMIT.match(commit):
        raise ValueError("That restore point can't be read.")
    repo = found_repo(point, data)
    covered = scope_dir(point, data)
    if not repo or not covered or not os.path.isdir(covered):
        raise ValueError("Its project's folder isn't where it was, so it can't go back.")
    scope = os.path.relpath(covered, repo)
    try:
        if git(repo, "cat-file", "-e", commit + "^{commit}") is None:
            raise ValueError("That restore point has gone from its project's git.")
        clock = time.strftime("%H:%M", time.localtime(point.get("at") or 0))
        kept = take(covered, f"before going back to {clock}", key="", project=point.get("project") or "", title="You, from the building",
                    by="you", data=data, now=now)
        where = [] if scope == "." else ["--", scope]
        held = names(git(repo, "ls-tree", "-r", "--name-only", "-z", "--full-tree", commit, *where, data=True))
        if held and git(repo, "restore", f"--source={commit}", "--worktree", "--pathspec-from-file=-", "--pathspec-file-nul",
                        env={"GIT_LITERAL_PATHSPECS": "1"}, given=b"\0".join(p.encode("utf-8", "surrogateescape") for p in held)) is None:
            raise ValueError("Git couldn't put the files back. Look in the project's folder: how they were a moment ago is a restore point too.")
        then = set(held)
        now_there = names(git(repo, "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", scope_spec(scope), *NOT_SECRETS, data=True))
        made = [p for p in now_there if p not in then and os.path.lexists(os.path.join(repo, p))]
    except TooSlow:
        raise ValueError(f"Git took over {WAIT} seconds, so it stopped. Look in the project's folder: how it was a moment ago is a restore point too.")
    return {"kept": kept and kept["id"], "left": made[:10], "more": max(0, len(made) - 10)}
