"""
install_link.py — build prefilled GitHub App install/consent links.

This module constructs URLs that open GitHub’s **Install App** (or **Update
permissions**) screen with:
- the **target account** preselected (`suggested_target_id`), and
- optionally, one or more **repositories** preselected (`repository_ids[]`).

Public API
----------
- build_install_link_for_repo(app_slug: str, owner: str, repo: str) -> str
- build_install_link_for_many(app_slug: str, owner: str, repos: list[str]) -> str
- get_owner_profile(owner: str) -> dict   # id/login/name/type (cached)

Notes
-----
- `suggested_target_id` is **required** for the prefilled screen.
- You may include up to **100** `repository_ids[]` values per link. If some
  repo IDs can’t be resolved (e.g., private repo without visibility), they’re
  simply omitted; the user can select them on GitHub manually.
- All functions are **process-local cached** via `functools.lru_cache`.
  No Streamlit dependency.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional, Dict, List
from urllib.parse import urlencode

import requests

from .config import GH_API, USER_AGENT


# --------------------------------------------------------------------------- #
# HTTP utilities
# --------------------------------------------------------------------------- #

def _headers_common() -> dict:
    """Headers for unauthenticated GitHub REST calls."""
    return {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": f"{USER_AGENT} install-link",
    }


# --------------------------------------------------------------------------- #
# Owner & repository lookups (cached)
# --------------------------------------------------------------------------- #

@lru_cache(maxsize=1024)
def get_owner_profile(owner: str) -> Dict[str, Optional[str | int]]:
    """
    Return owner profile metadata suitable for building prefilled links.

    Result (keys):
      - id:   numeric account id (int) or None if not found
      - login: login/handle string
      - name: display name (may be None)
      - type: "User" or "Organization" (may be None if unknown)

    We call GET /users/{owner} (works for both users and orgs).
    """
    try:
        r = requests.get(f"{GH_API}/users/{owner}", headers=_headers_common(), timeout=10)
        if r.status_code == 200:
            data = r.json()
            return {
                "id": int(data.get("id")) if data.get("id") is not None else None,
                "login": data.get("login"),
                "name": data.get("name"),
                "type": data.get("type"),
            }
    except requests.RequestException:
        pass
    # Fallback empty profile
    return {"id": None, "login": owner, "name": None, "type": None}


@lru_cache(maxsize=4096)
def _get_repo_id(owner: str, repo: str) -> Optional[int]:
    """
    Return repository id if it can be resolved anonymously; otherwise None.

    Uses GET /repos/{owner}/{repo}. For private repos without visibility this
    will return None, which is fine — the install screen will still open with
    the owner preselected and the user can pick repos there.
    """
    try:
        r = requests.get(f"{GH_API}/repos/{owner}/{repo}", headers=_headers_common(), timeout=10)
        if r.status_code == 200:
            return int(r.json()["id"])
    except requests.RequestException:
        pass
    return None


# --------------------------------------------------------------------------- #
# Link builders
# --------------------------------------------------------------------------- #

def build_install_link_for_repo(app_slug: str, owner: str, repo: str) -> str:
    """
    Prefilled consent URL for a single repository; falls back to owner-only
    selection if the repo id is unknown (e.g., private repo without visibility).

    Example
    -------
    >>> build_install_link_for_repo("my-app", "acme", "tools")
    'https://github.com/apps/my-app/installations/new/permissions?suggested_target_id=123&repository_ids[]=456'
    """
    owner_profile = get_owner_profile(owner)
    owner_id = owner_profile["id"]

    base = f"https://github.com/apps/{app_slug}/installations/new/permissions"
    if not owner_id:
        # Hard fallback: plain install page (user will choose the account)
        return f"https://github.com/apps/{app_slug}/installations/new"

    params: List[tuple[str, str]] = [("suggested_target_id", str(owner_id))]
    repo_id = _get_repo_id(owner, repo)
    if repo_id:
        params.append(("repository_ids[]", str(repo_id)))

    return f"{base}?{urlencode(params)}"


def build_install_link_for_many(app_slug: str, owner: str, repos: list[str]) -> str:
    """
    Prefilled consent URL for **many** repositories under the same owner.

    - Preselects the owner via `suggested_target_id`.
    - Adds up to **100** `repository_ids[]` (GitHub’s documented limit).
      Any repos without resolvable IDs (e.g., private) are omitted and can
      be selected manually on the GitHub screen.

    If the owner id cannot be resolved, falls back to the generic install page.

    Example
    -------
    >>> build_install_link_for_many(\"my-app\", \"acme\", [\"tools\", \"widgets\"])
    'https://github.com/apps/my-app/installations/new/permissions?suggested_target_id=123&repository_ids[]=456&repository_ids[]=789'
    """
    # Normalize and de-duplicate in order of appearance
    unique_repos: List[str] = sorted(set(repos))

    owner_profile = get_owner_profile(owner)
    owner_id = owner_profile["id"]

    base = f"https://github.com/apps/{app_slug}/installations/new/permissions"
    if not owner_id:
        return f"https://github.com/apps/{app_slug}/installations/new"

    params: List[tuple[str, str]] = [("suggested_target_id", str(owner_id))]

    # Resolve as many repo IDs as we can (up to 100)
    count = 0
    for repo in unique_repos:
        if count >= 100:
            break
        rid = _get_repo_id(owner, repo)
        if rid:
            params.append(("repository_ids[]", str(rid)))
            count += 1

    return f"{base}?{urlencode(params)}"


__all__ = [
    "build_install_link_for_repo",
    "build_install_link_for_many",
    "get_owner_profile",
]
