"""
errors.py — custom exceptions used across the git service.

These exceptions are intentionally small and specific so callers can handle
permission/install problems distinctly from generic network or git errors.

Public API:
- GitHubNotInstalledError
- GitHubPermissionError
"""

from __future__ import annotations


class GitHubAppError(RuntimeError):
    """
    Base class for GitHub App–related errors in this package.

    Subclassing RuntimeError keeps behavior consistent with existing code that
    may already be catching RuntimeError broadly, while allowing you to catch
    all app-specific issues via `GitHubAppError` if desired.
    """


class GitHubNotInstalledError(GitHubAppError):
    """The GitHub App is not installed for this repository (or this repo was not granted to the installation)."""


class GitHubPermissionError(GitHubAppError):
    """The GitHub App lacks the required permission (e.g., `contents: write`) for this repository."""


__all__ = [
    "GitHubAppError",
    "GitHubNotInstalledError",
    "GitHubPermissionError",
]
