from __future__ import annotations

import yaml
import streamlit as st

from label_app.config.settings import get_settings
from label_app.data.models import Project, make_project
from label_app.services.git import (
    clone_or_pull,
    parse_github_url,
    owner_repo_from_url,
    check_repo_access,
    github_web_dir_url,
)


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
            'repo_dir_url': str,   # link to directory in GitHub UI
            'read_ok': bool,
            'write_ok': bool,
            'needs_install': bool, # derived: True iff not read_ok
            'needs_write': bool,   # derived: True iff read_ok and not write_ok
        }
    """
    settings = get_settings()
    discovered: dict[str, list[Project]] = {}
    meta_by_slug: dict[str, dict] = {}

    for slug, raw_url in settings.projects.items():
        try:
            # Parse URL → canonical repo URL + optional branch + optional subdir
            repo_url, branch, subdir = parse_github_url(raw_url)
            owner, repo = owner_repo_from_url(repo_url)
            access = check_repo_access(owner, repo)  # read/write booleans
            repo_dir_url = github_web_dir_url(repo_url, branch, subdir or "")

            read_ok = bool(access["read_ok"])
            write_ok = bool(access["write_ok"])
            needs_install = not read_ok
            needs_write = read_ok and not write_ok

            # Save meta (always) so UI can render cards even when unreadable
            meta_by_slug[slug] = {
                "owner": owner,
                "repo": repo,
                "branch": branch,
                "subdir": subdir or "",
                "repo_dir_url": repo_dir_url,
                "read_ok": read_ok,
                "write_ok": write_ok,
                "needs_install": needs_install,
                "needs_write": needs_write,
            }

            # If unreadable, don't attempt to clone; show a card with a prompt
            if not read_ok:
                discovered[slug] = []
                continue

            # Readable: clone or update (clone_or_pull handles anon vs authed)
            repo_path = clone_or_pull(repo_url, branch)
            base = repo_path / subdir if subdir else repo_path
            if not base.exists():
                st.error(
                    f"Path '{subdir or '.'}' not found in "
                    f"{repo_url}@{branch or 'default'}"
                )
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
                        repo_url=repo_url,
                        repo_path=repo_path,
                        project_root=version_dir,
                    )
                )

            discovered[slug] = versions

        except Exception as exc:
            # Surface to user but keep going
            st.error(f"Could not load project from {raw_url}: {exc}")

            # Best-effort meta so the UI can still render a prompt card if parsing worked
            try:
                repo_url, branch, subdir = parse_github_url(raw_url)
                owner, repo = owner_repo_from_url(repo_url)
                meta_by_slug[slug] = {
                    "owner": owner,
                    "repo": repo,
                    "branch": branch,
                    "subdir": subdir or "",
                    "repo_dir_url": github_web_dir_url(repo_url, branch, subdir or ""),
                    "read_ok": False,
                    "write_ok": False,
                    "needs_install": True,
                    "needs_write": False,
                }
            except Exception:
                # If even parsing fails, we skip meta for this slug
                pass

            discovered.setdefault(slug, [])

    return discovered, meta_by_slug
