from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import streamlit as st
from git import Repo

CACHE_DIR = Path.home() / ".cache" / "label_app" / "repos"


def _repo_dest(url: str) -> Path:
    """Return the filesystem path for the given Git *url*."""
    parts = urlparse(url)
    owner, repo = Path(parts.path).parts[1:3]
    dest = CACHE_DIR / owner / repo.replace('.git', '')
    dest.parent.mkdir(parents=True, exist_ok=True)
    return dest


@st.cache_resource()
def clone_or_pull(url: str) -> Path:
    """Clone *url* into the cache or pull the latest changes."""
    dest = _repo_dest(url)
    if dest.exists() and (dest / ".git").exists():
        repo = Repo(dest)
        repo.remotes.origin.pull()
    else:
        Repo.clone_from(url, dest)
    return dest
