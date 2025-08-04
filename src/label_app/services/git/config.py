"""
config.py — central configuration and process-wide constants.

This module is intentionally small and import-safe. It:

- Defines the on-disk **cache directory** used for local git checkouts.
- Holds constants for the GitHub REST API base URL and HTTP **User-Agent**.
- Reads the GitHub App credentials (**App ID**, **private key PEM**, **App slug**)
  from `st.secrets["github_app"]` exactly once at import time so that other
  modules (including background threads) don’t need to touch Streamlit APIs.

Expected `st.secrets` structure:

```toml
[github_app]
app_id = "123456"
private_key_pem = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
slug = "your-app-slug"
```

If any of these are missing, this module raises a **RuntimeError** with a clear
message at import time.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st
from platformdirs import user_cache_dir

# --------------------------------------------------------------------------- #
# App identity and cache locations
# --------------------------------------------------------------------------- #

APP: str = "label_app"

# Base directory where local git clones are stored:
#   <user_cache_dir(APP)>/repos
CACHE_DIR: Path = Path(user_cache_dir(APP)) / "repos"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------- #
# GitHub API settings
# --------------------------------------------------------------------------- #

# REST API base
GH_API: str = "https://api.github.com"

# HTTP User-Agent sent on all GitHub requests (recommended by GitHub)
USER_AGENT: str = f"{APP}-github-app/1.0"


# --------------------------------------------------------------------------- #
# GitHub App credentials (read once from Streamlit secrets)
# --------------------------------------------------------------------------- #

def _require_github_app_secrets() -> dict:
    """
    Load and validate the `[github_app]` section from st.secrets.

    Raises:
        RuntimeError: if the section or any required key is missing.
    """
    try:
        app_secrets = st.secrets["github_app"]
    except Exception as exc:  # KeyError or Secrets backend issues
        raise RuntimeError(
            "Missing [github_app] section in Streamlit secrets. "
            "Please define github_app.app_id, github_app.private_key_pem, and github_app.slug."
        ) from exc

    missing = [k for k in ("app_id", "private_key_pem", "slug", "commit_sign_id") if k not in app_secrets]
    if missing:
        raise RuntimeError(
            "Missing required keys in [github_app] secrets: "
            + ", ".join(missing)
        )
    return app_secrets


_app = _require_github_app_secrets()

# Note: coerce APP_ID to str because TOML/YAML may parse numeric ids as ints.
APP_ID: str = str(_app["app_id"])
APP_PRIVATE_KEY: str = _app["private_key_pem"]
APP_SLUG: str = _app["slug"]
BOT_SIGN_ID: str = _app["commit_sign_id"]

BOT_NAME = f"{APP_SLUG}[bot]"
BOT_EMAIL = f"{BOT_SIGN_ID}+{BOT_NAME}@users.noreply.github.com"

__all__ = [
    "APP",
    "CACHE_DIR",
    "GH_API",
    "USER_AGENT",
    "APP_ID",
    "APP_PRIVATE_KEY",
    "APP_SLUG",
]
