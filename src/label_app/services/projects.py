from __future__ import annotations

import yaml
import streamlit as st

from label_app.config.settings import get_settings
from label_app.data.models import Project, make_project
from label_app.services.github import (
    parse_github_url,
    owner_repo_from_url,
    github_web_dir_url,
    ensure_trackers, get_branch_tracker,
)
from label_app.services.github.branch_tracker import RepoStatus


@st.cache_resource(show_spinner=False, ttl="15m")
def discover_projects() -> tuple[dict[str, list[Project]], dict[str, dict]]:
    """
    Clone repos listed in *settings* (when readable) and return:
        (discovered_projects, meta_by_slug)

    `discovered_projects[slug]` is a list of Project objects (may be empty).

    `meta_by_slug[slug]` contains UI-facing metadata **always** present,
    even when the repo isn’t readable, so the page can render a card and
    an access prompt:

        {
            'owner': str,
            'repo': str,
            'branch': str | None,
            'subdir': str,
            'repo_url': str,
            'repo_dir_url': str,   # link to directory in GitHub UI
            'read_ok': bool,
            'write_ok': bool,
            'needs_install': bool, # derived: True iff not read_ok
            'needs_write': bool,   # derived: True iff read_ok and not write_ok
            'versions_comment': str | None,  # if not None, explains why versions are empty
        }
    """
    def get_basic_meta(url: str) -> dict:
        repo_url, branch, subdir = parse_github_url(url)
        owner, repo = owner_repo_from_url(repo_url)
        return {
            "owner": owner,
            "repo": repo,
            "branch": branch,
            "subdir": subdir or "",
            "repo_url": repo_url,
            "repo_dir_url": github_web_dir_url(repo_url, branch, subdir or "")
        }

    settings = get_settings()
    discovered: dict[str, list[Project]] = {}
    meta_by_slug: dict[str, dict] = {
        slug: get_basic_meta(raw_url)
        for slug, raw_url in settings.projects.items()
    }

    ensure_trackers(
        (meta["repo_url"], meta["branch"])
        for meta in meta_by_slug.values()
    )  # this will clone the repos if needed

    for slug, meta in meta_by_slug.items():
        try:
            tracker = get_branch_tracker(meta["repo_url"], meta["branch"])

            # populate access-related meta
            read_ok = tracker.repo_status is not None and (tracker.repo_status >= RepoStatus.READ_ONLY)
            write_ok = tracker.repo_status is not None and (tracker.repo_status >= RepoStatus.OK)
            needs_install = not read_ok
            needs_write = read_ok and not write_ok

            meta_by_slug[slug].update({
                "read_ok": read_ok,
                "write_ok": write_ok,
                "needs_install": needs_install,
                "needs_write": needs_write,
            })

            # If unreadable, don't discover versions
            if not read_ok:
                meta_by_slug[slug]["versions_comment"] = "Cannot discover versions without read permissions"
                discovered[slug] = []
                continue

            # Readable: clone or update happened on tracker initialization
            subdir = meta["subdir"]
            base = tracker.path / subdir if subdir else tracker.path
            if not base.exists():
                meta_by_slug[slug]["versions_comment"] = f"No versions found for [project]({meta['repo_dir_url']})"
                discovered[slug] = []
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
                        repo_url=tracker.url,
                        repo_path=tracker.path,
                        project_root=version_dir,
                    )
                )

            meta_by_slug[slug]["versions_comment"] = None
            discovered[slug] = versions

        except Exception as exc:
            # Surface to user but keep going
            meta_by_slug[slug]["versions_comment"] = f"Unexpected error happened while trying to load the project!"
            print(f"[discover_projects] {exc}")

            meta_by_slug[slug].update({
                "read_ok": False,
                "write_ok": False,
                "needs_install": True,
                "needs_write": False,
            })

            discovered[slug] = []

    return discovered, meta_by_slug
