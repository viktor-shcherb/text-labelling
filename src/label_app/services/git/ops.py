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

from pathlib import Path
from urllib.parse import urlparse, urlunparse

from git import Repo, GitCommandError

from .urls import canonical_repo_url, owner_repo_from_url
from .repo_fs import repo_dest
from .auth import get_installation_token
from .errors import GitHubNotInstalledError


# --------------------------------------------------------------------------- #
# Helpers to manage HTTPS remotes
# --------------------------------------------------------------------------- #

def authed_https_for_app(base_https_url: str, token: str) -> str:
    """
    Return an HTTPS remote URL that includes GitHub App credentials:

        https://x-access-token:<token>@github.com/<owner>/<repo>.git
    """
    p = urlparse(base_https_url)
    assert p.scheme == "https"
    netloc = f"x-access-token:{token}@{p.netloc}"
    return urlunparse(p._replace(netloc=netloc))


def with_authed_remote(repo: Repo, token: str):
    """
    Temporarily set `origin` to an authed URL using the GitHub App token.

    The original (clean) URL is restored on exit, even if an exception occurs.
    """
    class _Ctx:
        def __enter__(self_inner):
            origin = repo.remotes.origin
            self_inner._prev_url = origin.url
            clean = canonical_repo_url(origin.url)
            origin.set_url(authed_https_for_app(clean, token))
            return origin

        def __exit__(self_inner, exc_type, exc, tb):
            try:
                repo.remotes.origin.set_url(self_inner._prev_url)
            except Exception:
                # As a fallback, reset to canonical clean https
                try:
                    repo.remotes.origin.set_url(canonical_repo_url(repo.remotes.origin.url))
                except Exception:
                    pass
            return False
    return _Ctx()


# --------------------------------------------------------------------------- #
# Internal helpers: anonymous vs authed network operations
# --------------------------------------------------------------------------- #

def _ff_pull(repo: Repo, branch: str | None) -> None:
    """
    Attempt a fast-forward pull. If the local branch is not tracking, try
    specifying the remote and branch explicitly. Raises GitCommandError if all
    strategies fail.
    """
    try:
        # Works when the current branch has an upstream configured
        repo.git.pull("--ff-only")
        return
    except GitCommandError:
        if branch:
            # Fallback when upstream isn't configured
            repo.git.pull("origin", branch, "--ff-only")
            return
        # No branch hint; re-raise the original error
        raise


def _anon_fetch_checkout_pull(repo: Repo, branch: str | None) -> None:
    """
    Try to fetch/checkout/pull without credentials.
    Raises GitCommandError on failure (to allow authed fallback).
    """
    # Ensure the origin URL is canonical https without creds
    try:
        repo.remotes.origin.set_url(canonical_repo_url(repo.remotes.origin.url))
    except Exception:
        pass

    if branch:
        repo.git.fetch("origin", branch, "--prune")
        repo.git.checkout(branch)
    else:
        repo.remotes.origin.fetch(prune=True)

    _ff_pull(repo, branch)


def _authed_fetch_checkout_pull(repo: Repo, branch: str | None, token: str) -> None:
    """
    Same as _anon_fetch_checkout_pull but using a temporary authed remote.
    """
    with with_authed_remote(repo, token) as origin:
        if branch:
            repo.git.fetch("origin", branch, "--prune")
            repo.git.checkout(branch)
        else:
            origin.fetch(prune=True)

        _ff_pull(repo, branch)


def _anon_clone(base_https: str, dest: Path, branch: str | None) -> None:
    """
    Clone without credentials; raises GitCommandError on failure.
    """
    Repo.clone_from(base_https, dest, branch=branch or None)


def _authed_clone(base_https: str, dest: Path, branch: str | None, token: str) -> None:
    """
    Clone using a temporary authed URL, then immediately reset the remote
    back to the clean https URL to avoid storing credentials in .git/config.
    """
    authed = authed_https_for_app(base_https, token)
    Repo.clone_from(authed, dest, branch=branch or None)
    repo = Repo(dest)
    repo.remotes.origin.set_url(base_https)


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #

def clone_or_pull_core(url: str, branch: str | None = None) -> Path:
    """
    Ensure `url@branch` is available locally and up to date; return the repo root.

    Strategy:
    1) Prefer **anonymous** Git operations (public repos succeed without tokens).
    2) If anonymous operations fail, fall back to **GitHub App–authenticated**
       operations by minting an installation token for `owner/repo`.
       - If the app is not installed for a private repo, a clear error is raised.

    Raises:
        GitCommandError
            When both anonymous and authenticated attempts fail.
        GitHubNotInstalledError
            For private repos where the app isn’t installed (fallback not possible).
        requests.HTTPError
            If token minting fails for other reasons.

    Note:
        Callers that need to hop across branches can still run
        `repo.git.checkout(branch)` after calling this function; for the common
        read-only case the work-tree is already on the correct branch.
    """
    dest = repo_dest(url, branch)
    base_https = canonical_repo_url(url)
    owner, repo_name = owner_repo_from_url(url)

    if (dest / ".git").exists():
        # Existing checkout: try anonymous fetch/pull first
        repo = Repo(dest)

        # Normalize remote to canonical https (without creds)
        try:
            repo.remotes.origin.set_url(canonical_repo_url(repo.remotes.origin.url))
        except Exception:
            pass

        try:
            _anon_fetch_checkout_pull(repo, branch)
            return dest
        except GitCommandError:
            # Anonymous path failed; try authenticated fallback
            try:
                token = get_installation_token(owner, repo_name)
            except GitHubNotInstalledError:
                # Likely a private repo without installation: surface clearly
                raise
            _authed_fetch_checkout_pull(repo, branch, token)
            return dest
    else:
        # No checkout yet: try anonymous clone first
        try:
            _anon_clone(base_https, dest, branch)
            return dest
        except GitCommandError:
            # Anonymous clone failed; try authenticated fallback
            try:
                token = get_installation_token(owner, repo_name)
            except GitHubNotInstalledError:
                # Private repo without installation: surface clearly
                raise
            _authed_clone(base_https, dest, branch, token)
            return dest
