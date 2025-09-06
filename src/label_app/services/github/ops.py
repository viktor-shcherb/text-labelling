"""
ops.py — Git operations (auth-optional clone/fetch/pull)

Core Git functions with **no Streamlit dependencies**. The workflow prefers
**anonymous** Git (good for public repos) and falls back to a **GitHub App**
installation token only when anonymous access fails (e.g., private repos).

Public API:
- authed_https_for_app(base_https_url, token) -> str
- with_authed_remote(repo, token) -> context manager
- clone_or_pull_core(url, branch=None) -> Path
"""

from __future__ import annotations

from contextlib import contextmanager
from functools import partial
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse, urlunparse

from git import Repo, GitCommandError, Remote

from .urls import canonical_repo_url


@contextmanager
def bot_identity_env(repo, name, email):
    with repo.git.custom_environment(
        GIT_AUTHOR_NAME=name,
        GIT_AUTHOR_EMAIL=email,
        GIT_COMMITTER_NAME=name,
        GIT_COMMITTER_EMAIL=email,
    ):
        yield


def authed_https_for_app(base_https_url: str, token: str) -> str:
    """
    Return an HTTPS remote URL that includes GitHub App credentials:

        https://x-access-token:<token>@github.com/<owner>/<repo>.git
    """
    p = urlparse(base_https_url)
    assert p.scheme == "https"
    netloc = f"x-access-token:{token}@{p.netloc}"
    return urlunparse(p._replace(netloc=netloc))  # noqa


def authed_remote(repo: Repo, *, token: str):
    """
    Temporarily set `origin` to an authed URL using the GitHub App token.

    The original (clean) URL is restored on exit, even if an exception occurs.
    """
    class _Ctx:
        def __enter__(self) -> Remote:
            origin: Remote = repo.remotes.origin
            self._prev_url = origin.url
            clean = canonical_repo_url(origin.url)
            origin.set_url(authed_https_for_app(clean, token))
            return origin

        def __exit__(self, exc_type, exc, tb):
            try:
                repo.remotes.origin.set_url(self._prev_url)
            except Exception:
                # As a fallback, reset to canonical clean https
                try:
                    repo.remotes.origin.set_url(canonical_repo_url(repo.remotes.origin.url))
                except Exception:
                    pass
            return False
    return _Ctx()


def clean_remote(repo: Repo):
    """
    Temporarily set `origin` to the canonical HTTPS URL without embedded credentials.

    - On entering, stores the current remote URL (which may include credentials).
    - Updates `origin` to the cleaned URL returned by `canonical_repo_url`.
    - On exit (normal or exception), restores the original URL.

    Returns:
        A context manager that yields the `origin` remote.

    Example:
        with with_clean_remote(repo) as origin:
            # origin.url is now the cleaned HTTPS URL
            origin.fetch()
    """
    class _Ctx:
        def __enter__(self) -> Remote:
            origin: Remote = repo.remotes.origin
            self._prev_url = origin.url
            clean_url = canonical_repo_url(self._prev_url)
            origin.set_url(clean_url)
            return origin

        def __exit__(self, exc_type, exc, tb):
            try:
                repo.remotes.origin.set_url(self._prev_url)
            except Exception:
                # Fallback: ensure remote is set to canonical clean URL
                try:
                    repo.remotes.origin.set_url(canonical_repo_url(repo.remotes.origin.url))
                except Exception:
                    pass
            return False

    return _Ctx()


def sync_with_remote(
    repo: Repo,
    branches: Iterable[str],
    *,
    token: str | None = None
) -> None:
    """
    For each branch in `branches`:
      1. Try `git fetch origin <branch>` (no prune).
      2. If it succeeded, branch exists remotely:
         - checkout (or create-and-track) local branch
         - rebase onto origin/<branch> with “ours” strategy
      3. If fetch failed with “Couldn't find remote ref”:
         - simply create a new local branch off HEAD

    Raises:
        GitCommandError:
            - When `origin.fetch(branch)` fails for reasons other than a missing remote ref.
            - When `repo.git.checkout(...)` or `repo.git.rebase(...)` encounters Git errors.
        GitCommandNotFound:
            If the underlying `git` executable is not found in the system PATH.
        OSError:
            For low-level I/O or filesystem errors (e.g., permission denied, broken pipe).
    """
    remote_manager = clean_remote if token is None else partial(authed_remote, token=token)

    with remote_manager(repo) as origin:
        for branch in branches:
            # 1) detect remote existence
            try:
                origin.fetch(branch)
                exists_on_remote = True
            except GitCommandError as e:
                if "Couldn't find remote ref" in str(e):
                    exists_on_remote = False
                else:
                    raise

            # 2) checkout or create
            if branch in repo.heads:
                repo.git.checkout(branch)
            else:
                if exists_on_remote:
                    # create & track origin/branch
                    repo.git.checkout("-b", branch, f"{origin.name}/{branch}")
                else:
                    # brand-new local branch
                    repo.git.checkout("-b", branch)

            # 3) rebase only if it came from the remote
            if exists_on_remote:
                try:
                    repo.git.rebase(
                        f"{origin.name}/{branch}",
                        "-s", "recursive",
                        "-X", "ours"
                    )
                except GitCommandError as rebase_err:
                    try:
                        repo.git.rebase("--abort")
                    except GitCommandError:
                        # nothing to abort (safe to ignore)
                        pass
                    raise rebase_err  # bubble up the original error


def clone(base_https: str, dest: Path, *, token: str | None = None) -> None:
    """
    Clone a repository using an optionally authenticated URL, then reset the origin remote URL
    to the clean HTTP URL to avoid storing credentials in `.git/config`.

    Uses a temporary URL embedding the provided `token` for authentication, then
    restores the remote.

    Raises:
        GitCommandError: If the `git clone` command fails with a non-zero exit status.
            ([gitpython.readthedocs.io](https://gitpython.readthedocs.io/en/3.1.14/reference.html))
        GitCommandNotFound: If the `git` executable cannot be found in the system PATH.
            ([gitpython.readthedocs.io](https://gitpython.readthedocs.io/en/3.1.14/reference.html))
        OSError: On filesystem or subprocess failures (e.g., permission issues, execution failures).
            ([docs.python.org](https://docs.python.org/3/library/subprocess.html))
        InvalidGitRepositoryError: If the cloned directory is invalid when opening with `Repo(dest)`.
            ([gitpython.readthedocs.io](https://gitpython.readthedocs.io/en/3.1.14/reference.html))
        NoSuchPathError: If the destination path is invalid when instantiating `Repo(dest)`.
            ([gitpython.readthedocs.io](https://gitpython.readthedocs.io/en/3.1.14/reference.html))
    """
    url = base_https
    if token is not None:
        url = authed_https_for_app(base_https, token)

    Repo.clone_from(url, dest)
    repo = Repo(dest)
    repo.remotes.origin.set_url(base_https)


def count_commits_between(repo: Repo, ref_a: str, ref_b: str) -> tuple[int, int]:
    """
    Return a tuple (ahead, behind) where
      - ahead  = number of commits in ref_a that are not in ref_b
      - behind = number of commits in ref_b that are not in ref_a
    """
    ahead = int(repo.git.rev_list("--count", f"{ref_b}..{ref_a}"))
    behind = int(repo.git.rev_list("--count", f"{ref_a}..{ref_b}"))
    return ahead, behind
