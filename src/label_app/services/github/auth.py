"""
auth.py — GitHub App authentication & installation token management.

Responsibilities
----------------
- Create short-lived **App JWTs** (RS256) from your App ID + private key.
- Mint **installation access tokens** for a specific repository’s installation.
- Maintain an in-process, thread-safe cache of installation tokens, including
  their **permissions** and **expiry**, so callers avoid unnecessary API calls.

Public API
----------
- get_installation_id_for_repo(owner, repo) -> int
- get_installation_token(owner, repo, *, require_write: bool = False) -> str

Design notes
------------
- We fetch the installation id using `GET /repos/{owner}/{repo}/installation`.
  GitHub returns **404** when the app is not installed or not granted access
  to that specific repository.

- Tokens are cached **per installation id** until within 5 minutes of expiry.
  The cache stores the token string, expiry, and the permission map returned by
  GitHub. The cache is guarded by a lock for thread safety.

- `_get_cached_installation_token(..., require_write=True)` only returns a
  cached token if it is still valid **and** the cached permission includes
  `contents: write`. This lets `get_installation_token(..., require_write=True)`
  return the cached token immediately without re-minting.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any

import jwt
import requests

from .config import CLIENT_ID, APP_PRIVATE_KEY, USER_AGENT, GH_API
from .errors import GitHubNotInstalledError, GitHubPermissionError

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

# HTTP timeouts (seconds)
_REQUEST_TIMEOUT = 15
# Clock skew applied to JWT "iat"
_JWT_IAT_SKEW_SECONDS = 30
# JWT lifetime (must be <= 10 minutes)
_JWT_LIFETIME_SECONDS = 8 * 60
# How soon before expiry we consider a token "stale" and force a refresh
_TOKEN_REFRESH_SLOP_SECONDS = 300  # 5 minutes

# --------------------------------------------------------------------------- #
# In-memory token cache (installation_id -> token bundle)
# --------------------------------------------------------------------------- #

_token_cache: dict[int, dict[str, Any]] = {}  # {"token", "expires_at", "permissions"}
_token_cache_lock = threading.Lock()


def _now_ts() -> int:
    """Current epoch seconds."""
    return int(time.time())


def _iso8601_to_ts(s: str) -> int:
    """
    Parse timestamps like '2024-01-01T12:00:00Z' into epoch seconds.
    GitHub returns `expires_at` in this Zulu ISO 8601 format.
    """
    return int(datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp())


def _make_app_jwt() -> str:
    """
    Create a signed JWT to authenticate as the GitHub App itself.
    Valid for < 10 minutes as required by GitHub.
    """
    now = _now_ts()
    payload = {
        "iat": now - _JWT_IAT_SKEW_SECONDS,
        "exp": now + _JWT_LIFETIME_SECONDS,
        "iss": CLIENT_ID,
    }
    return jwt.encode(payload, APP_PRIVATE_KEY, algorithm="RS256")


def _headers_common() -> dict:
    """Headers recommended by GitHub for REST API calls."""
    return {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": USER_AGENT,
    }


def _headers_as_app() -> dict:
    """Auth headers for requests made as the App (using the App JWT)."""
    return {"Authorization": f"Bearer {_make_app_jwt()}", **_headers_common()}


def _create_installation_token(installation_id: int, repositories: list[str] | None = None) -> dict:
    """
    POST /app/installations/{id}/access_tokens

    Optionally scope to specific repositories when the installation is set to
    “Only selected repositories.” Returns a JSON object that includes:
      - token (str)
      - expires_at (ISO8601)
      - permissions (mapping like {'contents': 'read'|'write', ...})
      - repository_selection, repositories (when scoped)
    """
    url = f"{GH_API}/app/installations/{installation_id}/access_tokens"
    payload: dict[str, Any] = {}
    if repositories:
        payload["repositories"] = repositories

    r = requests.post(url, headers=_headers_as_app(), json=payload, timeout=_REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.json()


def _get_cached_installation_token(installation_id: int, *, require_write: bool = False) -> str | None:
    """
    Return a cached token if it exists, isn’t near expiry, and (if requested)
    carries `contents: write` permission.
    """
    with _token_cache_lock:
        entry = _token_cache.get(installation_id)

    if not entry:
        return None

    # Check required permissions
    permissions = (entry.get("permissions") or {})
    if require_write and permissions.get("contents") != "write":
        return None

    # Refresh if < slop window left
    if _now_ts() > _iso8601_to_ts(entry["expires_at"]) - _TOKEN_REFRESH_SLOP_SECONDS:
        return None

    return entry["token"]


def get_installation_id_for_repo(owner: str, repo: str) -> int:
    """
    Return the installation id that covers this specific repository.

    GitHub returns:
      - 200 with the installation record if the app is installed AND granted access
      - 404 if the app is not installed or not granted this repository

    Raises:
        GitHubNotInstalledError: when 404 from GitHub (not installed/not granted).
        HTTPError: for other HTTP errors (401/403/5xx).
    """
    url = f"{GH_API}/repos/{owner}/{repo}/installation"
    r = requests.get(url, headers=_headers_as_app(), timeout=_REQUEST_TIMEOUT)
    if r.status_code == 200:
        return int(r.json()["id"])
    if r.status_code == 404:
        # GitHub deliberately returns 404 when the app doesn't have access
        raise GitHubNotInstalledError(
            f"GitHub App is not installed or not granted access to {owner}/{repo}."
        )
    # Bubble up other issues (401/403/5xx)
    r.raise_for_status()
    # Should be unreachable if raise_for_status() did its job
    raise RuntimeError("Unexpected response while fetching installation id")


def get_installation_token(owner: str, repo: str, *, require_write: bool = False) -> str:
    """
    Return a valid **installation access token** for `owner/repo`.

    Args:
        owner: GitHub login of the user or org.
        repo: Repository name.
        require_write: If True, ensure the token has `contents: write` permission.
                       If the app lacks write permission, raise GitHubPermissionError.

    Returns:
        The bearer token string usable for REST and Git over HTTPS
        (with username `x-access-token`).

    Raises:
        GitHubNotInstalledError: the app is not installed or not granted this repo.
        GitHubPermissionError: write required but the app only has read.
        HTTPError: for network/HTTP errors while calling GitHub.

    Behavior:
        - Uses a thread-safe in-memory cache keyed by installation id.
        - Re-mints tokens when the cached token is missing, lacks required
          permission (for `require_write=True`), or is near expiry.
    """
    installation_id = get_installation_id_for_repo(owner, repo)

    # First, try to serve from cache. This already honors `require_write`.
    cached = _get_cached_installation_token(installation_id, require_write=require_write)
    if cached:
        return cached

    # Otherwise mint a fresh token and update cache
    tok = _create_installation_token(installation_id)
    permissions = (tok.get("permissions") or {})

    with _token_cache_lock:
        _token_cache[installation_id] = {
            "token": tok["token"],
            "permissions": permissions,
            "expires_at": tok["expires_at"],
        }

    if require_write and permissions.get("contents") != "write":
        # Token minted but app lacks write; signal to caller
        raise GitHubPermissionError(
            f"GitHub App does not have 'contents: write' permission on {owner}/{repo}."
        )

    return tok["token"]
