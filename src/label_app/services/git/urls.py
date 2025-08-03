"""
urls.py — parsing and canonicalization of GitHub repository URLs.

Responsibilities
----------------
- Parse a variety of GitHub URL shapes (HTTPS with/without creds, scp-like SSH)
  into a **canonical repo URL** and optional branch/subdirectory.
- Provide helpers to extract `(owner, repo)` and to build GitHub Web links.

Supported inputs
----------------
- HTTPS:
    https://github.com/<owner>/<repo>(.git)?
    https://user:pass@github.com/<owner>/<repo>.git
    https://github.com/<owner>/<repo>/tree/<branch>[/<subdir...>]
- scp-like SSH:
    git@github.com:<owner>/<repo>(.git)

Outputs
-------
- `repo_url`: always `https://github.com/<owner>/<repo>.git` (no credentials)
- `branch`:   `str | None` (None means the server’s default branch)
- `subdir`:   `str` ('' when no subpath)

Notes
-----
- Query strings and fragments are ignored.
- Branch and subdir are **URL-decoded** (e.g., `%2F` becomes `/`).
- We only support `github.com` (and `www.github.com`) here. Enterprise hosts
  are out of scope by design.
"""

from __future__ import annotations

from urllib.parse import urlparse, unquote
from typing import Tuple


def parse_github_url(raw_url: str) -> Tuple[str, str | None, str]:
    """
    Canonicalize a GitHub URL and return (repo_url, branch, subdir).

    • repo_url -> always 'https://github.com/<owner>/<repo>.git' (no creds)
    • branch   -> branch name or None (means default branch)
    • subdir   -> path inside the repo, '' if none

    Examples
    --------
    >>> parse_github_url("https://github.com/acme/tools")
    ('https://github.com/acme/tools.git', None, '')

    >>> parse_github_url("git@github.com:acme/tools.git")
    ('https://github.com/acme/tools.git', None, '')

    >>> parse_github_url("https://github.com/acme/tools/tree/feat-x/dir/a%20b")
    ('https://github.com/acme/tools.git', 'feat-x', 'dir/a b')
    """
    s = raw_url.strip()

    # Handle scp-like SSH: git@github.com:owner/repo(.git)
    if s.startswith("git@github.com:"):
        # Convert to an https-looking string so urlparse can do the rest
        s = "https://github.com/" + s.split(":", 1)[1]

    parsed = urlparse(s)

    # Host must be github.com (normalize and strip any userinfo in netloc)
    host = parsed.netloc.lower()
    if "@" in host:
        host = host.split("@", 1)[1]  # drop user:pass@
    if host not in ("github.com", "www.github.com"):
        raise ValueError(f"Failed to parse project source: {raw_url}. Only GitHub URLs are supported.")

    # Drop trailing slash & ignore query/fragment entirely for canon
    path = parsed.path.rstrip("/")

    # Extract owner/repo and optional /tree/<branch>/<subdir>
    branch: str | None = None
    subdir = ""

    if "/tree/" in path:
        repo_part, tree_part = path.split("/tree/", 1)
        owner_repo = repo_part.lstrip("/")
        # tree_part = "<branch>" or "<branch>/<subdir...>"
        first, *rest = tree_part.split("/", 1)
        branch = unquote(first) if first else None
        subdir = unquote(rest[0]) if rest else ""
    else:
        owner_repo = path.lstrip("/")

    # owner_repo should be "<owner>/<repo[.git]>"
    parts = [p for p in owner_repo.split("/") if p]
    if len(parts) < 2:
        raise ValueError(f"Invalid GitHub repo path in URL: {raw_url}")

    owner, repo = parts[0], parts[1]
    # Strip only a trailing ".git" (don't remove other dots in the repo name)
    if repo.endswith(".git"):
        repo = repo[:-4]

    repo_url = f"https://github.com/{owner}/{repo}.git"
    return repo_url, branch, subdir


def canonical_repo_url(url: str) -> str:
    """Return only the canonical HTTPS repo URL for a given GitHub URL."""
    repo_url, _, _ = parse_github_url(url)
    return repo_url


def owner_repo_from_url(raw_url: str) -> Tuple[str, str]:
    """
    Extract (owner, repo) from any supported GitHub URL.

    Examples
    --------
    >>> owner_repo_from_url("https://github.com/acme/tools.git")
    ('acme', 'tools')
    """
    repo_url, _, _ = parse_github_url(raw_url)
    p = urlparse(repo_url)
    owner, repo_git = p.path.strip("/").split("/")[-2:]
    repo = repo_git[:-4] if repo_git.endswith(".git") else repo_git
    return owner, repo


def github_web_dir_url(repo_url: str, branch: str | None, subdir: str) -> str:
    """
    Build a link to the directory in GitHub’s web UI.

    If `branch is None`, we use `HEAD` so that GitHub resolves to the current
    default branch at view time.

    Examples
    --------
    >>> github_web_dir_url('https://github.com/acme/tools.git', None, '')
    'https://github.com/acme/tools/tree/HEAD'
    """
    owner, repo = owner_repo_from_url(repo_url)
    ref = branch if branch else "HEAD"
    path = (subdir or "").strip("/")
    suffix = f"/{path}" if path else ""
    return f"https://github.com/{owner}/{repo}/tree/{ref}{suffix}"


__all__ = [
    "parse_github_url",
    "canonical_repo_url",
    "owner_repo_from_url",
    "github_web_dir_url",
]
