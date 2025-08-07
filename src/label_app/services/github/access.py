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
