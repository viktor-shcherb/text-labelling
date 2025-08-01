from __future__ import annotations

from urllib.parse import urlparse

import yaml
import streamlit as st

from label_app.config.settings import get_settings
from label_app.data.models import Project, make_project
from label_app.services.git_client import clone_or_pull


@st.cache_data(show_spinner=False)
def parse_repo_url(raw_url: str) -> tuple[str, str | None, str]:
    """
    Canonicalise a GitHub URL and return **(repo_url, branch, subdir)**.

    ▸ *repo_url* → always https://github.com/<owner>/<repo>.git
    ▸ *branch*   → branch name or None (means: default branch)
    ▸ *subdir*   → path inside the repo, may be ''
    """
    parsed = urlparse(raw_url.strip())
    if parsed.netloc.lower() != "github.com":
        st.error(f"Failed to parse project source: {raw_url}. Only GitHub URLs are supported.")
        raise ValueError("Non-GitHub URL")

    path = parsed.path.rstrip("/")
    if "/tree/" in path:
        repo_part, tree_part = path.split("/tree/", 1)
        owner_repo = repo_part.lstrip("/")
        branch, *rest = tree_part.split("/", 1)
        subdir = rest[0] if rest else ""
    else:                           # plain repo URL → no branch, no sub-path
        owner_repo = path.lstrip("/")
        branch, subdir = None, ""

    repo_url = f"https://github.com/{owner_repo}"
    if not repo_url.endswith(".git"):
        repo_url += ".git"

    return repo_url, branch, subdir


@st.cache_data(show_spinner=False)
def discover_projects() -> dict[str, list[Project]]:
    """Clone repos listed in *settings* and return discovered projects."""
    settings = get_settings()
    discovered: dict[str, list[Project]] = {}

    for slug, raw_url in settings.projects.items():
        try:
            repo_url, branch, subdir = parse_repo_url(raw_url)
            repo_path = clone_or_pull(repo_url, branch)
            base = repo_path / subdir if subdir else repo_path
            if not base.exists():
                st.error(
                    f"Path '{subdir or '.'}' not found in "
                    f"{repo_url}@{branch or 'default'}"
                )
                continue

            versions: list[Project] = []
            for version_dir in sorted(p for p in base.iterdir() if p.is_dir()):
                yaml_path = version_dir / "project.yaml"
                if not yaml_path.is_file():
                    continue
                with yaml_path.open(encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                versions.append(
                    make_project(
                        yaml_data=data,
                        slug=slug,
                        version=version_dir.name,
                        repo_url=repo_url,
                        repo_path=repo_path,
                        project_root=version_dir,
                    )
                )
            if versions:
                discovered[slug] = versions
        except Exception as exc:
            # Any unexpected error for this repo -> show user & keep going
            st.error(f"Could not load project from {raw_url}: {exc}")

    return discovered
