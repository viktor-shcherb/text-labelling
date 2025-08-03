"""
flusher.py — background worker to auto-commit staged changes and push (debounced)

Responsibilities
----------------
- Periodically scan the local repo cache (CACHE_DIR) for repositories.
- For each repo:
  * Create a commit **only for staged changes** (never stages new files).
  * Debounce pushes: once a new local commit is observed, wait at least
    `DEBOUNCE_SECONDS` before pushing to batch frequent small updates.
  * Push using a **GitHub App installation token** (write required).

Threading & safety
------------------
- One background thread runs `flusher_loop`.
- Per-repo locks (`REPO_LOCKS`) prevent concurrent work on the same repo.
- Debounce state (`PENDING_SINCE`, `LAST_PUSH`) is protected by `PENDING_LOCK`.

Notes
-----
- The worker only pushes when write access exists; otherwise it logs a warning
  once per repo and skips it thereafter.
- Detached HEADs are skipped (nothing to push).
- Remote credentials are injected temporarily via the context manager in `ops`.

Public API
----------
- start_repo_flusher_core() -> threading.Event
- scan_and_flush_all() -> None  (primarily for tests/manual runs)
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from pathlib import Path

from git import Repo, GitCommandError, Actor

from .config import CACHE_DIR
from .ops import with_authed_remote, canonical_repo_url, owner_repo_from_url
from .auth import get_installation_token
from .errors import GitHubNotInstalledError, GitHubPermissionError

# How long to accumulate new local commits before attempting a push
DEBOUNCE_SECONDS: int = 300  # 5 minutes
# How often the background worker scans the repo cache
CHECK_INTERVAL_SECONDS: int = 30  # 2 times a minute

# Per-repo lock to serialize work on a given checkout
REPO_LOCKS: dict[Path, threading.Lock] = defaultdict(threading.Lock)

# Debounce state (protected by PENDING_LOCK)
PENDING_SINCE: dict[Path, float] = {}
LAST_PUSH: dict[Path, float] = {}
PENDING_LOCK = threading.Lock()

# Warn-once registry for permission/install failures
WARNED_PERM_DENIED: set[Path] = set()


def has_staged_changes(repo: Repo) -> bool:
    """
    True iff there are staged changes ready to commit (ignores unstaged/untracked).
    """
    try:
        if repo.head.is_valid():
            # Only index vs HEAD; do not consider working tree or untracked
            return repo.is_dirty(index=True, working_tree=False, untracked_files=False)
        # No commits yet: any index entry counts as staged
        return len(repo.index.entries) > 0
    except Exception:
        return False


def commit_only_staged(repo: Repo) -> bool:
    """
    Commit only the staged changes. Return True iff a commit was created.
    """
    if not has_staged_changes(repo):
        return False
    author = Actor("label-app[bot]", "label-app[bot]@users.noreply.github.com")
    repo.index.commit("Auto-commit (staged changes)", author=author, committer=author)
    return True


def push_current_branch_with_app(repo: Repo) -> bool:
    """
    Fetch + rebase then push current branch using a GitHub App token.
    Returns True iff push appears successful (no exception).
    """
    origin = repo.remotes.origin
    base_https = canonical_repo_url(origin.url)
    owner, repo_name = owner_repo_from_url(base_https)
    token = get_installation_token(owner, repo_name, require_write=True)

    try:
        branch = repo.active_branch.name
    except (TypeError, AttributeError, GitCommandError):
        return False  # detached; nothing to push

    try:
        with with_authed_remote(repo, token) as authed_origin:
            # Narrow network traffic to the active branch when possible
            try:
                repo.git.fetch("origin", branch, "--prune")
            except GitCommandError:
                # Remote branch may not exist yet; continue
                pass

            # Rebase onto remote branch if it exists; abort on conflicts
            try:
                repo.git.rebase(f"origin/{branch}")
            except GitCommandError:
                try:
                    repo.git.rebase("--abort")
                except GitCommandError:
                    pass

            # Push; if upstream not set, set it
            try:
                authed_origin.push()
            except GitCommandError:
                authed_origin.push(refspec=f"{branch}:{branch}", set_upstream=True)

        return True
    except GitCommandError:
        return False


def scan_and_flush_all() -> None:
    """
    Walk CACHE_DIR looking for repos to commit (staged only) and (debounced) push.
    Layout: repos/<owner>/<repo>_<branch-or-default>

    Debounce: after we first see a new local commit in a repo, wait at least
    DEBOUNCE_SECONDS before pushing. This batches frequent small commits.
    """
    for owner_dir in CACHE_DIR.iterdir():
        if not owner_dir.is_dir():
            continue

        for repo_dir in owner_dir.iterdir():
            print(f"[flusher] Inspecting {repo_dir}")
            if not (repo_dir / ".git").exists():
                continue

            lock = REPO_LOCKS[repo_dir.resolve()]
            if not lock.acquire(blocking=False):
                # Another thread is working on this repo
                continue

            try:
                repo = Repo(repo_dir)

                # 1) Commit only staged changes
                created = commit_only_staged(repo)
                print(f"[flusher] Commit creation OK: {created}")

                # 2) Update debounce state and decide whether to push
                now = time.time()
                should_push = False

                with PENDING_LOCK:
                    if created and repo_dir not in PENDING_SINCE:
                        # First time we noticed a new local commit for this repo
                        PENDING_SINCE[repo_dir] = now

                    pending_since = PENDING_SINCE.get(repo_dir)
                    if pending_since is not None and (now - pending_since) >= DEBOUNCE_SECONDS:
                        should_push = True

                # 3) Push if the debounce window elapsed
                if should_push:
                    ok = push_current_branch_with_app(repo)
                    if ok:
                        print(f"[flusher] Push OK: {repo_dir}]")
                        with PENDING_LOCK:
                            PENDING_SINCE.pop(repo_dir, None)
                            LAST_PUSH[repo_dir] = now

            except (GitHubNotInstalledError, GitHubPermissionError) as e:
                if repo_dir not in WARNED_PERM_DENIED:
                    print(f"[flusher] {repo_dir}: {e}", flush=True)
                    WARNED_PERM_DENIED.add(repo_dir)
            except Exception as e:
                print(f"[flusher] {repo_dir}: {e}", flush=True)
            finally:
                lock.release()


def flusher_loop(stop_event: threading.Event) -> None:
    """
    Main loop: periodically scan for repos to flush until `stop_event` is set.
    """
    while not stop_event.is_set():
        print(f"[flusher] Tick")
        scan_and_flush_all()
        stop_event.wait(CHECK_INTERVAL_SECONDS)

    print(f"[flusher] Exit")


def start_repo_flusher_core() -> threading.Event:
    """
    Start a single background thread per app process that, every
    `CHECK_INTERVAL_SECONDS`, commits staged changes and (debounced) pushes them.

    Returns:
        A `threading.Event` that can be set to request the worker to stop.
        (The Streamlit facade caches this, so a second call will be a no-op.)
    """
    stop = threading.Event()
    t = threading.Thread(target=flusher_loop, args=(stop,), name="repo-flusher", daemon=True)
    t.start()
    return stop
