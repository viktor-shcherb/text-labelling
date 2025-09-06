import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from enum import IntEnum
from pathlib import Path
from typing import Iterable, Literal

from git import GitCommandError, Repo, GitError, Actor

from .auth import get_installation_token
from .config import BOT_NAME, BOT_EMAIL
from .errors import GitHubNotInstalledError, GitHubPermissionError
from .ops import clone, sync_with_remote, authed_remote, count_commits_between, bot_identity_env
from .repo_fs import repo_dest
from .urls import canonical_repo_url, owner_repo_from_url

from label_app.utils.lock import lock

# limit accesses to remote
POLL_TIMEOUT = 5
PULL_TIMEOUT = 15 * 60
PUSH_TIMEOUT = 5 * 60
AUTO_COMMIT_TIMEOUT = 5 * 60
TOKEN_REFRESH_TIMEOUT = 15 * 60
MERGE_SQUASHED_AFTER_INACTIVE = 1 * 60 * 60
MAX_CONCURRENCY = 10


class RepoStatus(IntEnum):
    INACCESSIBLE = 1
    READ_ONLY = 2
    OK = 3


REPO_LOCKS: dict[Path, threading.RLock] = defaultdict(threading.RLock)


class BranchTracker:
    def __init__(self, repo_url: str, branch: str) -> None:
        self.url = canonical_repo_url(repo_url)

        owner, repo_name = owner_repo_from_url(self.url)
        self.owner = owner
        self.repo_name = repo_name
        self.tracking_branch = branch
        self.staging_branch = f"{branch}-staging"
        self.branch_names: dict[Literal["tracking", "staging"], str] = {
            "tracking": self.tracking_branch, "staging": self.staging_branch
        }

        self._repo = None
        self.path = repo_dest(repo_url, branch)  # unique per (repo, branch) combo
        self.logging_prefix = f"[tracker-{self.path.name}]"

        # WARNING: do not grab repo lock before releasing time lock
        self._time_lock = threading.RLock()
        self._last_push_time: dict[Literal["tracking", "staging"], float | None] = {"tracking": None, "staging": None}
        self._last_pull_time = None
        self._last_merge_time = None
        self._last_token_refresh_time = None
        self._last_auto_commit_time = None

        self._token = None
        self._repo_status = None
        self._is_private = False
        self._monitor_thread = None
        self.reset()

        print(f"{self.logging_prefix} Initialized")

    @property
    def repo(self) -> Repo | None:
        if self.is_initialized() and self._repo is None:
            self._repo = Repo(self.path)
        return self._repo

    @property
    def last_merge_time(self) -> float | None:
        return self._last_pull_time

    @property
    def last_pull_time(self) -> float | None:
        return self._last_pull_time

    @property
    def repo_status(self) -> RepoStatus | None:
        return self._repo_status

    @property
    def is_private(self) -> bool:
        return self._is_private

    @property
    def repo_lock(self) -> threading.RLock:
        return REPO_LOCKS[self.path]

    def is_initialized(self) -> bool:
        return (self.path / ".git").exists()

    def _init(self):
        """IMPORTANT: not thread-safe. Make sure to lock self.repo_lock"""

        if self.is_initialized():
            return

        print(f"{self.logging_prefix} Initializing the local branches")

        if not self._is_private:
            try:
                clone(self.url, self.path)
                print(f"{self.logging_prefix} Successful anon clone of the branch")
            except GitCommandError:
                self._is_private = True

        if self._is_private:
            self.refresh_token()
            if self._token is not None:
                clone(self.url, self.path, token=self._token)
                print(f"{self.logging_prefix} Successful authed clone of the branch")
            else:
                print(f"{self.logging_prefix} Token acquisition failed")

    def _update(self):
        """IMPORTANT: not thread-safe. Make sure to lock self.repo_lock"""

        if not self.is_initialized():
            raise RuntimeError(f"Call _init before calling _update")

        print(f"{self.logging_prefix} Updating the local branches")
        # Existing checkout: try anonymous fetch/pull first
        if not self._is_private:
            try:
                sync_with_remote(self.repo, branches=[self.tracking_branch, self.staging_branch])
                print(f"{self.logging_prefix} Successful anon branch pull")
            except GitCommandError as e:
                print(f"{self.logging_prefix} Failed to sync: {e}")
                self._is_private = True

        if self._is_private:
            self.refresh_token()
            if self._token is not None:
                sync_with_remote(self.repo, branches=[self.tracking_branch, self.staging_branch], token=self._token)
                print(f"{self.logging_prefix} Successful authenticated branch pull")
            else:
                print(f"{self.logging_prefix} Token acquisition failed")

    def pull_remote(self, *, force: bool = False) -> None:
        with self._time_lock:
            time_since_last_pull = float("inf")
            if self._last_pull_time is not None:
                time_since_last_pull = time.time() - self._last_pull_time
            wait_time = max(0.0, PULL_TIMEOUT - time_since_last_pull)

            if not force:
                if wait_time > 0:
                    return

                if self._repo_status is RepoStatus.INACCESSIBLE:
                    return

            self._last_pull_time = time.time()

        with self.repo_lock:
            try:
                if self.is_initialized():
                    self._update()
                else:
                    self._init()

                # clone or pull is successful, repo exists on disk and ready for tracking changes
                if self.is_initialized():
                    self.ensure_staging_branch()
            except (GitError, OSError) as e:
                print(f"{self.logging_prefix} Error during remote sync: {e}")

    def reset(self):
        self._token = None
        self._repo_status = None
        self._is_private = False  # assume public

        print(f"{self.logging_prefix} Resetting")

        try:
            # this will determine the current repo status
            self.refresh_token(force=True)
            self.pull_remote(force=True)
        except (GitError, OSError) as e:
            print(f"{self.logging_prefix} Error during reset: {e}")

        if self._monitor_thread is None or not self._monitor_thread.is_alive():
            self._monitor_thread = threading.Thread(
                target=self.monitor_branches,
                daemon=True,
            )
            self._monitor_thread.start()

    def refresh_token(self, force: bool = False) -> None:
        with self._time_lock:
            time_since_last_refresh = float("inf")
            if self._last_token_refresh_time is not None:
                time_since_last_refresh = time.time() - self._last_token_refresh_time
            wait_time = max(0.0, TOKEN_REFRESH_TIMEOUT - time_since_last_refresh)

            if not force and wait_time > 0.0:
                return

            self._last_token_refresh_time = time.time()

        try:
            self._token = get_installation_token(self.owner, self.repo_name, require_write=True)
            self._repo_status = RepoStatus.OK
        except GitHubNotInstalledError:
            self._token = None
            self._repo_status = RepoStatus.INACCESSIBLE
        except GitHubPermissionError:
            self._token = None
            self._repo_status = RepoStatus.READ_ONLY

        print(f"{self.logging_prefix} Token refresh")

    def ensure_staging_branch(self):
        """
        Ensure that `self.staging_branch` is checked out locally, branching off `self.tracked_branch`.
        If the tracked branch does not exist locally, raises a GitCommandError.
        If the staging branch already exists locally, simply switches to it.
        Otherwise, creates a new local staging branch at the tip of the tracked branch.
        """
        if not self.is_initialized():
            raise RuntimeError(f"{self.logging_prefix} Call _init before calling _ensure_staging_branch")

        with self.repo_lock:
            # Ensure tracked branch exists locally
            if self.tracking_branch not in self.repo.heads:
                raise GitCommandError(f"Branch '{self.tracking_branch}' not found locally", 128)

            # If staging branch exists, switch to it
            if self.staging_branch in self.repo.heads:
                self.repo.git.checkout(self.staging_branch)
                return

            remote_staging = getattr(self.repo.remotes.origin.refs, self.staging_branch, None)
            if remote_staging is not None:
                # use the remote version
                self.repo.create_head(self.staging_branch, remote_staging)
            else:
                # everything failed: use tracking branch to create a new branch
                self.repo.create_head(self.staging_branch, self.tracking_branch)
            self.repo.git.checkout(self.staging_branch)

            # Push it to the remote, so it exists in the future
            self.push_branch("staging", force=True)

    def push_branch(self, branch: Literal["tracking", "staging"], *, force: bool = False) -> None:
        with self._time_lock:
            time_since_last_push = float("inf")
            if self._last_push_time[branch] is not None:
                time_since_last_push = time.time() - self._last_push_time[branch]
            wait_time = max(0.0, PUSH_TIMEOUT - time_since_last_push)

            if not force and wait_time > 0.0:
                return

            self._last_push_time[branch] = time.time()

        branch_name = self.branch_names[branch]
        print(f"{self.logging_prefix} Pushing {branch_name}")

        self.refresh_token(force=self._token is None)  # force refresh if there is no access
        if self._token is None:
            print(f"{self.logging_prefix} Cannot push branch {branch_name} without write access")
            return

        with self.repo_lock:
            try:
                with authed_remote(self.repo, token=self._token) as origin:
                    # always force-push staging
                    origin.push(refspec=f"{branch_name}:{branch_name}", force=(branch == "staging"))
            except (GitError, OSError) as e:
                print(f"{self.logging_prefix} Failed to push branch {branch_name}: {e}")

    def sync_with_staging_branch(self):
        """
        1. Fetches fresh branches (force pull on tracked branch).
        2. Rebases staging branch onto tracked branch, resolving conflicts by prioritizing tracked branch.
        3. Squash-merges staging into tracked branch (creating a single commit).
        4. Pushes tracked branch to remote.
        5. Resets staging branch to match tracked branch exactly.
        """
        self.refresh_token(force=self._token is None)  # force refresh if there is no access
        if self._token is None:
            print(f"{self.logging_prefix} Cannot sync staging branch without write access")
            return

        if not self.is_initialized():
            print(f"{self.logging_prefix} Cannot sync staging branch on non-initialized repo")
            return

        with self.repo_lock:  # freeze the repo for the duration of the pull-push cycle
            # 1) Update from remote
            self.pull_remote(force=True)

            # Ensure both branches exist locally
            if self.tracking_branch not in self.repo.heads:
                raise GitCommandError(f"Branch '{self.tracking_branch}' not found locally", 128)
            if self.staging_branch not in self.repo.heads:
                raise GitCommandError(f"Staging branch '{self.staging_branch}' not found locally", 128)

            # 2) Rebase staging onto tracked (tracked priority on conflict)
            self.repo.git.checkout(self.staging_branch)
            try:
                with bot_identity_env(self.repo, BOT_NAME, BOT_EMAIL):
                    self.repo.git.rebase(
                        self.tracking_branch,
                        "-s", "recursive",
                        "-X", "theirs"
                    )
            except GitCommandError:
                self.repo.git.rebase("--abort")
                raise

            # 3) Squash-merge staging into tracked
            self.repo.git.checkout(self.tracking_branch)
            # Prepare squash, but don't commit automatically
            self.repo.git.merge(self.staging_branch, "--squash")
            # Commit with a message
            author = Actor(BOT_NAME, BOT_EMAIL)
            self.repo.index.commit(
                f"Squash merge {self.staging_branch} into {self.tracking_branch}",
                author=author, committer=author
            )

            # 4) push asap before the remote diverged
            self.push_branch("tracking", force=True)

            # 5) Reset staging to tracked (hard update)
            self.repo.git.checkout(self.staging_branch)
            self.repo.git.reset("--hard", self.tracking_branch)
            self.push_branch("staging", force=True)

    def auto_commit(self, force: bool = False) -> None:
        with self._time_lock:
            time_since_last_commit = float("inf")
            if self._last_auto_commit_time is not None:
                time_since_last_commit = time.time() - self._last_auto_commit_time
            wait_time = max(0.0, AUTO_COMMIT_TIMEOUT - time_since_last_commit)

            if not force and wait_time > 0.0:
                return

            self._last_auto_commit_time = time.time()

        if not self.is_initialized():
            print(f"{self.logging_prefix} Cannot auto-commit on non-initialized repo")
            return

        with self.repo_lock:
            # ensure we're on staging
            self.ensure_staging_branch()

            # detect staged changes (including new files)
            staged = self.repo.index.diff("HEAD")
            untracked = self.repo.untracked_files
            if staged or untracked:
                # add everything, commit with bot identity
                self.repo.git.add("--all")
                author = Actor(BOT_NAME, BOT_EMAIL)
                self.repo.index.commit(
                    "Auto-commit staged changes",
                    author=author,
                    committer=author
                )
                print(f"{self.logging_prefix} Auto-committed staging changes")

    def monitor_branches(self) -> None:
        branches: list[Literal["tracking", "staging"]] = ["tracking", "staging"]
        while True:
            time.sleep(POLL_TIMEOUT)
            if not self.is_initialized() or self._repo_status is not RepoStatus.OK:
                # periodically poll the remote until access issues are resolved and it is cloned
                self.pull_remote()
                continue

            # determine if any of the branches need push
            push_needed: dict[Literal["tracking", "staging"], bool] = {"tracking": False, "staging": False}
            for branch in branches:
                with self._time_lock:
                    time_since_last_push = float("inf")
                    if self._last_push_time[branch] is not None:
                        time_since_last_push = time.time() - self._last_push_time[branch]

                    push_needed[branch] = (time_since_last_push > PUSH_TIMEOUT)

            with self.repo_lock:  # freeze the repo for the duration of the pull-push cycle
                # auto-commit any staged changes on staging (no more than once per AUTO_COMMIT_TIMEOUT)
                self.auto_commit()

                for branch in branches:
                    local = self.branch_names[branch]
                    remote = f"origin/{local}"

                    # if remote ref doesn't exist, assume all local commits are unpushed
                    if remote not in self.repo.refs:
                        push_needed[branch] &= True
                        continue

                    commits_not_in_remote, _ = count_commits_between(self.repo, local, remote)
                    push_needed[branch] &= (commits_not_in_remote > 0)

                # If staging branch has been inactive AND has commits not on tracking, do the sync
                # i.e. squash-merge staging into tracking and push both
                staging_head = self.repo.heads[self.staging_branch].commit.committed_date
                time_since_last_commit = time.time() - staging_head
                if time_since_last_commit > MERGE_SQUASHED_AFTER_INACTIVE:
                    _, only_staging = count_commits_between(self.repo, self.tracking_branch, self.staging_branch)
                    if only_staging > 0:
                        print(f"{self.logging_prefix} Long period of inactivity with pending staging commits — syncing")
                        try:
                            self.sync_with_staging_branch()
                            # clear push flags so we don't double-push
                            push_needed = dict.fromkeys(branches, False)
                        except Exception as e:
                            print(f"{self.logging_prefix} staging branch sync failed: {e}")

                # force if we are going to push anything, otherwise just check the timeout
                self.pull_remote(force=any(push_needed.values()))

                for branch, do_push in push_needed.items():
                    if do_push:
                        self.push_branch(branch)


REPO_PATH_TO_TRACKER: dict[Path, BranchTracker] = {}
TRACKERS: dict[(str, str), BranchTracker] = {}
TRACKER_ACCESS_LOCK = threading.Lock()


def _ensure_tracker(url_and_branch: tuple[str, str]):
    """WARNING: not thread-safe. Make sure the TRACKER_ACCESS_LOCK is locked"""
    if url_and_branch in TRACKERS:
        return

    url, branch = url_and_branch
    tracker = BranchTracker(repo_url=url, branch=branch)
    TRACKERS[url_and_branch] = tracker
    REPO_PATH_TO_TRACKER[tracker.path] = tracker


@lock(TRACKER_ACCESS_LOCK)
def get_branch_tracker(repo_url: str, branch: str) -> BranchTracker:
    repo_url = canonical_repo_url(repo_url)
    key = (repo_url, branch)
    _ensure_tracker(key)
    return TRACKERS[key]


@lock(TRACKER_ACCESS_LOCK)
def get_responsible_tracker(absolute_path: str | Path) -> BranchTracker:
    if not absolute_path.is_absolute():
        raise ValueError(f"Passed in path {absolute_path} is not absolute")

    if absolute_path in REPO_PATH_TO_TRACKER:
        return REPO_PATH_TO_TRACKER[absolute_path]

    for potential_path in REPO_PATH_TO_TRACKER:
        if absolute_path.is_relative_to(potential_path):
            return REPO_PATH_TO_TRACKER[potential_path]

    raise RuntimeError(f"No existing tracker found for {absolute_path}. "
                       f"Please use `ensure_trackers` to ensure all repository trackers exist")


@lock(TRACKER_ACCESS_LOCK)
def ensure_trackers(url_and_branch: Iterable[tuple[str, str]]):
    canonical_keys = [(canonical_repo_url(url), branch) for url, branch in url_and_branch]
    non_ensured = [key for key in canonical_keys if key not in TRACKERS]
    if not len(non_ensured):
        return

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENCY) as executor:
        executor.map(_ensure_tracker, non_ensured)


def _reset_tracker(url_and_branch: tuple[str, str]):
    if url_and_branch not in TRACKERS:
        return
    TRACKERS[url_and_branch].reset()


@lock(TRACKER_ACCESS_LOCK)
def reset_trackers(url_and_branch: Iterable[tuple[str, str]]):
    canonical_keys = [(canonical_repo_url(url), branch) for url, branch in url_and_branch]
    not_initialized = [key for key in canonical_keys if key not in TRACKERS]
    if len(not_initialized):
        print(f"[reset_trackers] Some of the requested trackers are not initialized: {not_initialized}")

    initialized = [key for key in canonical_keys if key in TRACKERS]
    if not len(initialized):
        return

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENCY) as executor:
        executor.map(_reset_tracker, initialized)
