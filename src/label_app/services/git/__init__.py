"""
Streamlit-facing facade for the git service.

This module re-exports the public API from the internal submodules and applies
Streamlit caching where it benefits the UI:

- `clone_or_pull(...)` is cached as a **resource** so repeated reads across
  reruns/sessions reuse the same local checkout and network connections. It
  may use **anonymous Git** for public repositories or a **GitHub App token**
  for private repositories, depending on what’s needed.

- `start_repo_flusher()` is cached as a **resource** to ensure the background
  worker (debounced commit/push loop) starts **exactly once per process**.

Anything imported from here should be safe to use directly in Streamlit pages
and fragments. The core implementations live in sibling modules and are kept
free of Streamlit dependencies for easier testing.
"""

from __future__ import annotations

from pathlib import Path
import threading

import streamlit as st

# Public API re-exports (implementation lives in the submodules)
from .urls import (
    parse_github_url,
    canonical_repo_url,
    owner_repo_from_url,
    github_web_dir_url,
)
from .ops import clone_or_pull_core
from .access import check_repo_access, RepoAccess
from .flusher import start_repo_flusher_core


# -----------------------------------------------------------------------------
# Facade functions with Streamlit caching (UI-facing)
# -----------------------------------------------------------------------------

@st.cache_resource(show_spinner=False, ttl="15m")
def clone_or_pull(url: str, branch: str | None = None) -> Path:
    """
    Ensure `url@branch` exists locally and is up-to-date; return the repo root.

    This is a thin wrapper over `clone_or_pull_core` that adds Streamlit's
    resource caching. The cache key is derived from the function's arguments,
    so different repo/branch pairs maintain distinct worktrees.
    """
    return clone_or_pull_core(url, branch)


@st.cache_resource(show_spinner=False)
def start_repo_flusher() -> threading.Event:
    """
    Start the background flusher thread once per process and return its stop event.

    The flusher periodically scans cached repos, commits **staged** changes only,
    and (debounced) pushes them using a GitHub App token.
    """
    return start_repo_flusher_core()


# Backwards-compat short names re-exported:
__all__ = [
    "parse_github_url",
    "canonical_repo_url",
    "owner_repo_from_url",
    "github_web_dir_url",
    "clone_or_pull",
    "check_repo_access",
    "start_repo_flusher",
    "RepoAccess",
]

# -----------------------------------------------------------------------------
# Autostart the flusher for convenience.
# Importing this module from any Streamlit page will ensure the worker is
# running. Because `start_repo_flusher` is a @cache_resource, this will only
# start the thread once per process (and no-op on subsequent imports).
# -----------------------------------------------------------------------------
_ = start_repo_flusher()
