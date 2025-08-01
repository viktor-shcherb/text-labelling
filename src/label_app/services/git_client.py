from __future__ import annotations

from pathlib import Path
from platformdirs import user_cache_dir
from urllib.parse import urlparse

import streamlit as st
from git import Repo


APP = "label_app"
CACHE_DIR = Path(user_cache_dir(APP)) / "repos"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _repo_dest(url: str, branch: str | None) -> Path:
    parts = urlparse(url)
    owner, repo = Path(parts.path).with_suffix("").parts[1:3]   # strip .git
    suffix = branch or "default"
    dest = CACHE_DIR / owner / f"{repo}_{suffix}"
    dest.mkdir(parents=True, exist_ok=True)
    return dest


@st.cache_resource(show_spinner=False)
def clone_or_pull(url: str, branch: str | None = None) -> Path:
    """
    Ensure *url*@*branch* is available locally and up to date.
    Returns the repo root Path.

    Raises GitCommandError.

    NB: callers should still `repo.git.checkout(branch)` if they need to
    hop around after the clone, but for read-only operations the work-tree
    is already on the correct branch.
    """
    dest = _repo_dest(url, branch)
    if (dest / ".git").exists():
        repo = Repo(dest)
        # fetch + fast-forward the target branch
        repo.remotes.origin.fetch(prune=True)
        if branch:
            repo.git.checkout(branch)
        repo.git.pull("--ff-only")
    else:
        Repo.clone_from(url, dest, branch=branch or None)

    return dest
