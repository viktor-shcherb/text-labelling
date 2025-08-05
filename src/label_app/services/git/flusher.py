"""
flusher.py — background worker to auto-commit staged changes and push.

Responsibilities
----------------
- Periodically scan the local repo cache (CACHE_DIR) for repositories.
- For each repo:
  * Create a commit **only for staged changes** (never stages new files).
  * Push the current branch using a **GitHub App installation token**.  The
    work branch is pushed at least every ``PUSH_INTERVAL_SECONDS`` while it is
    ahead of its remote counterpart so that progress survives restarts.
  * Maintain a dedicated work branch and periodically squash-merge it into
    the target branch after a period of inactivity or after a maximum delay.

Threading & safety
------------------
- One background thread runs `flusher_loop`.
- Per-repo locks (`REPO_LOCKS`) prevent concurrent work on the same repo.
- Push state (`LAST_PUSH`) and merge timers are protected by `PENDING_LOCK`.

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

from .config import CACHE_DIR, BOT_NAME, BOT_EMAIL
from .ops import with_authed_remote, canonical_repo_url, owner_repo_from_url
from .auth import get_installation_token
from .errors import GitHubNotInstalledError, GitHubPermissionError

# Minimum delay between pushes of the work branch when local commits exist
PUSH_INTERVAL_SECONDS: int = 60
# How long to wait without new commits before squashing into the target branch
MERGE_IDLE_SECONDS: int = 3600  # 1 hour
# Always merge at least once this often if there are commits pending
MERGE_MAX_DELAY_SECONDS: int = 6 * 3600  # 6 hours
# Suffix used to create the work branch name
WORK_BRANCH_SUFFIX: str = "flush"
# How often the background worker scans the repo cache
CHECK_INTERVAL_SECONDS: int = 30  # 2 times a minute

# Per-repo lock to serialize work on a given checkout
REPO_LOCKS: dict[Path, threading.Lock] = defaultdict(threading.Lock)

# Push/merge state (protected by PENDING_LOCK)
LAST_PUSH: dict[Path, float] = {}
# Track per-repo target branch and merge timers
TARGET_BRANCH: dict[Path, str] = {}
LAST_COMMIT: dict[Path, float] = {}
LAST_MERGE: dict[Path, float] = {}
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
    author = Actor(BOT_NAME, BOT_EMAIL)
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


def ensure_work_branch(repo: Repo, repo_dir: Path) -> tuple[str, str] | None:
    """Ensure a dedicated work branch exists and is checked out.

    Returns a tuple of (target_branch, work_branch) or ``None`` if the repo is
    in a detached HEAD state.
    """
    try:
        current = repo.active_branch.name
    except (TypeError, AttributeError, GitCommandError):
        return None

    target = TARGET_BRANCH.get(repo_dir, current)
    TARGET_BRANCH[repo_dir] = target
    work = f"{target}-{WORK_BRANCH_SUFFIX}"

    branch_names = {b.name for b in repo.branches}
    if work not in branch_names:
        repo.git.checkout(target)
        repo.git.checkout("-b", work)
    elif current != work:
        repo.git.checkout(work)

    return target, work


def work_branch_has_commits(repo: Repo, target_branch: str, work_branch: str) -> bool:
    """True iff ``work_branch`` contains commits not in ``target_branch``."""
    try:
        count = int(repo.git.rev_list("--count", f"{target_branch}..{work_branch}"))
        return count > 0
    except GitCommandError:
        return False


def work_branch_ahead_of_remote(repo: Repo, work_branch: str) -> bool:
    """True iff ``work_branch`` has commits not present on ``origin``."""
    try:
        count = int(repo.git.rev_list("--count", f"origin/{work_branch}..{work_branch}"))
        return count > 0
    except GitCommandError:
        # If the remote branch does not exist yet treat it as ahead so that it
        # is pushed and created remotely.
        return True


def squash_merge_work_branch(repo: Repo, target: str, work: str) -> bool:
    """Rebase ``work`` onto ``target`` and squash-merge it into ``target``."""
    try:
        repo.git.fetch("origin", target, work, "--prune")
    except GitCommandError:
        pass

    # Rebase work branch onto the latest target
    try:
        repo.git.checkout(work)
        repo.git.rebase(f"origin/{target}")
    except GitCommandError:
        try:
            repo.git.rebase("--abort")
        except GitCommandError:
            pass
        return False

    if not push_current_branch_with_app(repo):
        return False

    # Squash-merge into the target branch
    repo.git.checkout(target)
    try:
        repo.git.merge("--squash", work)
    except GitCommandError:
        try:
            repo.git.reset("--merge")
        except GitCommandError:
            pass
        return False

    author = Actor(BOT_NAME, BOT_EMAIL)
    repo.index.commit("Auto-merge squashed commits", author=author, committer=author)

    if not push_current_branch_with_app(repo):
        return False

    # Reset work branch to the updated target branch
    try:
        repo.git.branch("-D", work)
    except GitCommandError:
        pass
    repo.git.checkout("-b", work)
    push_current_branch_with_app(repo)
    return True


def scan_and_flush_all() -> None:
    """
    Walk CACHE_DIR looking for repos to commit (staged only), push and merge.
    Layout: repos/<owner>/<repo>_<branch-or-default>

    Commits land on a dedicated work branch which is pushed periodically so
    that local progress is persisted between runs. The work branch is
    squash-merged into the target branch after ``MERGE_IDLE_SECONDS`` of
    inactivity or at least every ``MERGE_MAX_DELAY_SECONDS``.
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
                branches = ensure_work_branch(repo, repo_dir)
                if not branches:
                    continue
                target_branch, work_branch = branches

                # 1) Commit only staged changes
                created = commit_only_staged(repo)
                print(f"[flusher] Commit creation OK: {created}")

                # 2) Update push/merge state and decide whether to push/merge
                now = time.time()
                should_push = False
                should_merge = False

                with PENDING_LOCK:
                    if created:
                        LAST_COMMIT[repo_dir] = now

                    last_push = LAST_PUSH.get(repo_dir, 0)
                    if work_branch_ahead_of_remote(repo, work_branch) and (
                        now - last_push
                    ) >= PUSH_INTERVAL_SECONDS:
                        should_push = True

                    last_commit = LAST_COMMIT.get(repo_dir)
                    last_merge = LAST_MERGE.get(repo_dir, 0)
                    if last_commit and (now - last_commit) >= MERGE_IDLE_SECONDS:
                        should_merge = True
                    elif last_commit and (now - last_merge) >= MERGE_MAX_DELAY_SECONDS:
                        should_merge = True

                # 3) Push if the work branch is ahead and the interval elapsed
                if should_push:
                    ok = push_current_branch_with_app(repo)
                    if ok:
                        print(f"[flusher] Push OK: {repo_dir}")
                        with PENDING_LOCK:
                            LAST_PUSH[repo_dir] = now

                # 4) Merge work branch into target branch when appropriate
                if should_merge and work_branch_has_commits(repo, target_branch, work_branch):
                    ok = squash_merge_work_branch(repo, target_branch, work_branch)
                    if ok:
                        print(f"[flusher] Squash-merge OK: {repo_dir}")
                        with PENDING_LOCK:
                            LAST_MERGE[repo_dir] = now
                            LAST_COMMIT.pop(repo_dir, None)
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
    `CHECK_INTERVAL_SECONDS`, commits staged changes and pushes them.

    Returns:
        A `threading.Event` that can be set to request the worker to stop.
        (The Streamlit facade caches this, so a second call will be a no-op.)
    """
    stop = threading.Event()
    t = threading.Thread(target=flusher_loop, args=(stop,), name="repo-flusher", daemon=True)
    t.start()
    return stop
