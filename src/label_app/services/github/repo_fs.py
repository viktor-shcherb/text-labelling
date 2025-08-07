"""
repo_fs.py — local filesystem layout for cached git repositories.

Responsibilities
----------------
- Convert a repository URL (+ optional branch) into a deterministic on-disk
  destination under `CACHE_DIR`.
- Ensure the destination directory exists.

Design
------
We store checkouts under:
    <CACHE_DIR>/<owner>/<repo>_<branch-suffix>

Where `<branch-suffix>` is:
- `"default"` when `branch is None` (meaning the server's default branch), or
- the branch name with path separators sanitized (e.g., `feature/foo` → `feature__foo`).

Sanitization prevents accidental nested directories and OS-invalid filenames.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

from .config import CACHE_DIR
from .urls import parse_github_url


# Characters allowed in a single path segment on most platforms.
# We normalize everything else to underscore. We also collapse consecutive
# slashes/backslashes to a double underscore to preserve some visual structure.
_ALLOWED_SEGMENT_RE = re.compile(r"[^A-Za-z0-9._-]")


def _sanitize_branch_suffix(branch: str | None) -> str:
    """
    Sanitize the branch name for use in a single path segment.

    - None -> "default"
    - Replace any '/' or '\' runs with '__'
    - Replace other disallowed characters with '_'
    - Avoid leading dot to prevent hidden directories
    """
    if not branch:
        return "default"
    # First, collapse path separators, so we don't create nested dirs
    s = re.sub(r"[\\/]+", "__", branch)
    # Replace remaining disallowed chars
    s = _ALLOWED_SEGMENT_RE.sub("_", s)
    # Avoid leading dot
    if s.startswith("."):
        s = "_" + s.lstrip(".")
    # Guard against empty after sanitization
    return s or "default"


def repo_dest(url: str, branch: str | None) -> Path:
    """
    Compute the destination directory for a repo checkout.

    Args:
        url: Any supported GitHub repo URL (HTTPS/SSH, with or without .git).
        branch: Optional branch name. When None, indicates the remote's default branch.

    Returns:
        Path to the local work tree directory. The directory is created if needed.

    Raises:
        ValueError: if the URL cannot be parsed as a GitHub repository.
    """
    canon, _, _ = parse_github_url(url)
    p = urlparse(canon)
    owner, repo_git = p.path.strip("/").split("/")[-2:]
    repo = repo_git[:-4] if repo_git.endswith(".git") else repo_git

    suffix = _sanitize_branch_suffix(branch)
    dest = CACHE_DIR / owner / f"{repo}_{suffix}"
    dest.mkdir(parents=True, exist_ok=True)
    return dest
