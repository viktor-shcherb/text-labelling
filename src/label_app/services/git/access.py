"""
Access helpers: determine effective read/write capabilities for a repository and
produce a prefilled GitHub App installation URL.

Public API:
- github_app_install_url(owner, repo) -> str
- check_repo_access(owner, repo) -> RepoAccess
"""

from __future__ import annotations

from typing import TypedDict

import requests

from .auth import get_installation_token
from .errors import GitHubNotInstalledError, GitHubPermissionError
from .config import GH_API, USER_AGENT


class RepoAccess(TypedDict):
    """Structured result for `check_repo_access`."""
    read_ok: bool
    write_ok: bool


def _headers_public() -> dict:
    """Headers for unauthenticated GitHub REST calls."""
    return {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": USER_AGENT,
    }


def _is_repo_public(owner: str, repo: str) -> bool:
    """
    Return True if the repository is public (readable without app installation).

    We call GET /repos/{owner}/{repo} *without* authentication:
      - 200 + {"private": false}  -> public
      - 200 + {"private": true}   -> private (not public)
      - 404 or other errors       -> treat as not public
    """
    try:
        r = requests.get(f"{GH_API}/repos/{owner}/{repo}", headers=_headers_public(), timeout=10)
        if r.status_code == 200:
            data = r.json()
            return not bool(data.get("private", True))
        # 404 (not found / no access) → not public
        return False
    except requests.RequestException:
        # Network issue → err on the side of “not public”
        return False


def check_repo_access(owner: str, repo: str) -> RepoAccess:
    """
    Check this app's access to `owner/repo`.

    Returns:
        {
            'read_ok':  True iff the repo is effectively readable by the app/page:
                        - app installed (any level), or
                        - repo is PUBLIC (anonymous read),
            'write_ok': True iff the app has `contents: write` on this repo,
            'install_url': link to open GitHub’s install/consent screen prefilled
        }

    Strategy (at most one token mint in the common case):
      1) Try to mint a token with `require_write=True`.
         - Success → read_ok=True, write_ok=True.
         - GitHubPermissionError → installed but read-only → read_ok=True, write_ok=False.
         - GitHubNotInstalledError → app not installed:
             * If repo is PUBLIC (unauthenticated GET /repos says private==false) →
               read_ok=True, write_ok=False.
             * Else → read_ok=False, write_ok=False.

    Notes:
    - This function does not swallow unexpected HTTP/network errors from the token
      mint path; callers may handle them if desired.
    """

    try:
        # Attempt to mint a write-capable token (implies read access as well)
        _ = get_installation_token(owner, repo, require_write=True)
        return {"read_ok": True, "write_ok": True}
    except GitHubPermissionError:
        # App is installed and can read, but lacks contents:write
        return {"read_ok": True, "write_ok": False}
    except GitHubNotInstalledError:
        # App not installed (or not granted). Public repos are still readable anonymously.
        if _is_repo_public(owner, repo):
            return {"read_ok": True, "write_ok": False}
        return {"read_ok": False, "write_ok": False}
