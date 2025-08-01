from __future__ import annotations

from pathlib import Path

import yaml
import streamlit as st

from label_app.config.settings import AppSettings, get_settings
from label_app.data.models import Project
from label_app.services.git_client import clone_or_pull


@st.cache_data()
def parse_repo_url(raw_url: str) -> tuple[str, str]:
    """Return ``(repo_url, subdir)`` for a GitHub tree URL."""
    if "/tree/" in raw_url:
        repo_part, sub_path = raw_url.split("/tree/", 1)
        repo_url = repo_part + ".git" if not repo_part.endswith(".git") else repo_part
        parts = sub_path.split("/", 1)
        subdir = parts[1] if len(parts) > 1 else ""
    else:
        repo_url = raw_url if raw_url.endswith(".git") else raw_url + ".git"
        subdir = ""
    return repo_url, subdir


@st.cache_data()
def discover_projects(settings: AppSettings | None = None) -> dict[str, list[Project]]:
    """Clone repos listed in *settings* and return discovered projects."""
    settings = settings or get_settings()
    result: dict[str, list[Project]] = {}

    for slug, raw_url in settings.projects.items():
        repo_url, subdir = parse_repo_url(raw_url)
        repo_path = clone_or_pull(repo_url)
        base = repo_path / subdir if subdir else repo_path
        versions: list[Project] = []
        for version_dir in sorted(base.iterdir()):
            yaml_path = version_dir / "project.yaml"
            if not yaml_path.exists():
                continue
            with yaml_path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            versions.append(
                Project(
                    slug=slug,
                    version=version_dir.name,
                    name=data.get("name", slug),
                    description=data.get("description"),
                    repo_url=repo_url,
                    repo_path=repo_path,
                    project_root=version_dir,
                )
            )
        if versions:
            result[slug] = versions
    return result
