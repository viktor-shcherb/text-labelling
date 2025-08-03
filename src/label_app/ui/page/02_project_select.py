from pathlib import Path

import streamlit as st

from label_app.data.models import Project
from label_app.services.projects import discover_projects
from label_app.services.git import clone_or_pull
from label_app.services.git.config import APP_SLUG
from label_app.services.git.install_link import (
    get_owner_profile,
    build_install_link_for_many,
)
from label_app.ui.components.auth import sidebar_logout
from label_app.ui.components.version_selection import get_version_selection


# ---------------------------- helpers ----------------------------------------

def _access_help(meta: dict) -> str:
    """Short, user-facing explanation based on read/write flags."""
    read_ok = bool(meta.get("read_ok"))
    write_ok = bool(meta.get("write_ok"))
    owner = meta.get("owner", "")
    repo = meta.get("repo", "")
    if not read_ok:
        return (
            f"App cannot read **{owner}/{repo}**. "
            "Grant the app access to this repository."
        )
    if not write_ok:
        return (
            f"App has read-only access to **{owner}/{repo}**. "
            "Grant write access to enable saving annotations."
        )
    return (
        f"App has read and write access to **{owner}/{repo}**. "
        "You can revoke this access in GitHub settings."
    )


def _group_all_repos_by_owner(meta_by_slug: dict[str, dict]) -> dict[str, set[str]]:
    """
    Collect **all** mentioned repos per owner, regardless of access state.
    { owner_login: {repo, ...}, ... }
    """
    by_owner: dict[str, set[str]] = {}
    for meta in meta_by_slug.values():
        owner = meta.get("owner")
        repo = meta.get("repo")
        if not owner or not repo:
            continue
        by_owner.setdefault(owner, set()).add(repo)
    return by_owner


def _owners_needing_fix(meta_by_slug: dict[str, dict]) -> set[str]:
    """
    Owners for which **any** repo needs install or write permission.
    """
    owners: set[str] = set()
    for meta in meta_by_slug.values():
        owner = meta.get("owner")
        repo = meta.get("repo")
        if not owner or not repo:
            continue
        read_ok = bool(meta.get("read_ok"))
        write_ok = bool(meta.get("write_ok"))
        needs_install = not read_ok
        needs_write = read_ok and not write_ok
        if needs_install or needs_write:
            owners.add(owner)
    return owners


@st.cache_data(show_spinner=False)
def _owner_label(owner: str) -> str:
    """Pretty label for owner selector: 'Name (@login)' or '@login'."""
    prof = get_owner_profile(owner)  # cached
    name = (prof.get("name") or "").strip()
    login = prof.get("login") or owner
    return f"{name} (@{login})" if name else f"@{login}"


# ------------------------- project card --------------------------------------

@st.fragment()
def display_project(slug: str, versions: list[Project], meta: dict):
    """
    Render one project card with permission-aware UI.
    - Always shows owner/repo link to the directory and branch badge.
    - If no read -> only the link + small warning icon with tooltip.
    - If read but no write -> show project info; disable 'Select' with tooltip.
    """
    owner = meta["owner"]
    repo = meta["repo"]
    branch = meta.get("branch") or "default"
    repo_dir_url = meta["repo_dir_url"]
    read_ok = bool(meta["read_ok"])
    write_ok = bool(meta["write_ok"])
    can_select = read_ok and write_ok

    # Header line: repo link + branch
    header_md = f"**[{owner}/{repo}]({repo_dir_url})**  :gray-badge[branch: {branch}]"
    if not read_ok:
        header_md += " :red-badge[:material/error: not accessible]"
    elif not write_ok:
        header_md += " :orange-badge[:material/warning: read-only]"
    help_msg = _access_help(meta)

    with st.container(border=True):

        col_data, col_actions = st.columns([3, 1])
        with col_data:
            repo_info_placeholder = st.empty()
            content_placeholder = st.empty()
        with col_actions:
            selector_placeholder = st.empty()
            submit_placeholder = st.empty()

        with repo_info_placeholder:
            # Always show repo/branch info
            st.markdown(header_md, help=help_msg)

        project = None
        chosen_version = None
        if versions:
            version_names = sorted(p.version for p in versions)
            selected_version = st.session_state.version_selection.get(slug, version_names[-1])
            if selected_version not in version_names:
                selected_version = version_names[-1]

            selected_idx = version_names.index(selected_version)
            project = versions[selected_idx]

            with selector_placeholder:
                chosen_version = st.selectbox(
                    "Version",
                    version_names,
                    index=selected_idx,
                    key=f"ver_{slug}",
                )

            if chosen_version != selected_version:
                st.session_state.version_selection[slug] = chosen_version
                st.rerun(scope="fragment")

        def get_chosen_version():
            try:
                return next(p for p in versions if p.version == chosen_version)
            except StopIteration:
                return None

        with content_placeholder:
            if project is not None:
                with st.container():
                    is_latest = selected_idx == len(versions) - 1
                    st.markdown(
                        f"##### {project.name}"
                        + (" :red-badge[latest]" if is_latest else "")
                        + f" :blue-badge[{project.task_type}]"
                    )
                    if getattr(project, "description", None):
                        st.markdown(project.description)
            else:
                # Read OK but no versions discovered
                if read_ok:
                    st.info(
                        "No versions found in this project path. "
                        "Ensure the directory contains at least one folder with `project.yaml`."
                    )

            # Select button disabled when either read or write is missing
            is_current_selected = (
                "selected_project" in st.session_state
                and st.session_state.selected_project == get_chosen_version()
            )

        with submit_placeholder:
            disabled = False
            reason = None
            if not can_select:
                disabled = True
                reason = "Cannot select non-writable project"
            elif is_current_selected:
                disabled = True
                reason = "Cannot select already selected project"
            elif not versions:
                disabled = True
                reason = "No versions to select from"
            if st.button(
                "Select" if not is_current_selected else "Selected",
                key=f"btn_{slug}",
                disabled=disabled,
                help=reason,
                use_container_width=True,
                type="primary",
            ):
                st.session_state.selected_project = get_chosen_version()
                st.switch_page("page/03_annotate.py")


# ----------------------------- Page body -------------------------------------

header_col, refresh_col = st.columns([10, 1], vertical_alignment="bottom")
with header_col:
    st.header("Project Selection")
with refresh_col:
    if st.button("", icon=":material/refresh:", help="Refresh projects"):
        discover_projects.clear()
        clone_or_pull.clear()

access_holder = st.empty()
projects_holder = st.empty()

sidebar_logout()
img_path = Path(__file__).parent.with_name("static") / "icon_with_border.png"
st.logo(img_path, size="large")

# Expect discover_projects to return (projects, meta_by_slug)
projects, meta_by_slug = discover_projects()

# -------- Top panel: Fix access for entire owner installations ---------------
all_repos_by_owner = _group_all_repos_by_owner(meta_by_slug)
owners_needing_fix = _owners_needing_fix(meta_by_slug)

if owners_needing_fix:
    with access_holder:
        with st.container(border=True):
            st.subheader("Fix access")

            col_select, col_submit = st.columns([2, 1], gap="small", vertical_alignment="bottom")
            # Limit selector to owners that actually need changes
            with col_select:
                owners = sorted(owners_needing_fix, key=str.lower)
                labels = [_owner_label(o) for o in owners]
                idx = st.selectbox("Account", options=list(range(len(owners))), format_func=lambda i: labels[i])
                owner = owners[idx]

            # IMPORTANT: include **all** mentioned repos for this owner in the link,
            # not just the ones with issues, to avoid losing previously granted repos.
            repos = sorted(all_repos_by_owner.get(owner, []))

            # Build the bulk link (prefilled up to 100 repo IDs; GitHub’s limit)
            install_url = build_install_link_for_many(APP_SLUG, owner, repos)

            explanation_col, repo_list_col = st.columns([2, 1])

            with explanation_col:
                st.markdown(
                    "Grant the app access/write for this account so you can save annotations. "
                    "The link includes **all projects** listed for this account to avoid "
                    "dropping access to repositories that are already working."
                )

            with repo_list_col:
                # Explicit checklist of repositories to verify on the GitHub screen
                st.markdown("**Make sure the following repositories are selected:**")
                if len(repos) <= 20:
                    st.markdown("\n".join(f"- `{r}`" for r in repos))
                else:
                    first, rest = repos[:20], repos[20:]
                    st.markdown("\n".join(f"- `{r}`" for r in first))
                    with st.expander(f"Show {len(rest)} more"):
                        st.markdown("\n".join(f"- `{r}`" for r in rest))

            # CTA(s)
            with col_submit:
                cta = f"Grant access ({len(repos)} repo{'s' if len(repos)!=1 else ''})"
                st.link_button(cta, install_url, type="primary", use_container_width=True)

            with explanation_col:
                st.caption(
                    "Tip: Some private repositories may not appear preselected; check them manually on the next screen. "
                    "After completing the flow, click **Refresh** (top-right)."
                )

# -------- Version selection defaults (for readable projects with versions) ----

defaults = {
    slug: sorted(p.version for p in versions)[-1]
    for slug, versions in projects.items()
    if versions  # skip unreadable or empty
}
version_selection = get_version_selection() or defaults
st.session_state.version_selection = {**defaults, **version_selection}

# ------------------------- Projects listing ----------------------------------

with projects_holder:
    with st.container():
        for slug, versions in projects.items():
            meta = meta_by_slug.get(slug, {})
            display_project(slug, versions, meta)


# TODO: cookie sync for selection persist
