import streamlit as st

from label_app.data.models import Project
from label_app.services.persistent_state.project import is_project_selected, get_project_selection, select_project
from label_app.services.persistent_state.version_selection import select_version, get_version_selection
from label_app.ui.components.navigation import update_navigation


def _on_version_change(slug: str, state_key: str):
    # Persist the newly chosen value to your cookie/store
    select_version(slug, st.session_state[state_key])


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


# ------------------------- project card --------------------------------------

@st.fragment()
def display_project(slug: str, versions: list[Project], meta: dict):
    owner = meta["owner"]; repo = meta["repo"]
    branch = meta.get("branch") or "default"
    repo_dir_url = meta["repo_dir_url"]
    read_ok = bool(meta["read_ok"]); write_ok = bool(meta["write_ok"])
    can_select = read_ok and write_ok

    header_md = f"**[{owner}/{repo}]({repo_dir_url})**  :gray-badge[branch: {branch}]"
    if not read_ok:
        header_md += " :red-badge[:material/error: not accessible]"
    elif not write_ok:
        header_md += " :orange-badge[:material/warning: read-only]"
    help_msg = _access_help(meta)

    version_selection = get_version_selection()

    col_data, col_actions = st.columns([3, 1])
    with col_data:
        repo_info_placeholder = st.empty()
        content_placeholder = st.empty()
    with col_actions:
        selector_placeholder = st.empty()
        submit_placeholder = st.empty()

    repo_info_placeholder.markdown(header_md, help=help_msg)

    project = None
    chosen_version = None
    selected_idx = None

    if versions:
        version_names = sorted(p.version for p in versions)
        persisted = version_selection.get(slug, version_names[-1])
        if persisted not in version_names:
            persisted = version_names[-1]

        with selector_placeholder:
            state_key = f"ver_{slug}"

            # Ensure session state is initialized once (avoids index-jumps/jitter on first render)
            if state_key not in st.session_state:
                st.session_state[state_key] = persisted

            # Use on_change to update your cookie when the value changes
            st.selectbox(
                "Version",
                version_names,
                key=state_key,
                index=version_names.index(st.session_state[state_key]),
                on_change=_on_version_change,
                args=(slug, state_key),
            )

        chosen_version = st.session_state[state_key]

        # Drive UI from the chosen value in the same pass
        selected_idx = version_names.index(chosen_version)
        project = next((p for p in versions if p.version == chosen_version), None)

    if project is not None:
        is_latest = selected_idx == len(versions) - 1
        latest_badge = " :red-badge[latest]" if is_latest else ""
        task_type_badge = f" :blue-badge[{project.task_type}]"
        description = project.description or "No description available"
        content_placeholder.markdown(
            f"##### {project.name}{latest_badge}{task_type_badge}\n{description}"
        )
    else:
        if read_ok:
            content_placeholder.info(
                "No versions found in this project path. "
                "Ensure the directory contains at least one folder with `project.yaml`."
            )

    def get_chosen_version():
        return next((p for p in versions if p.version == chosen_version), None)

    is_current_selected = (is_project_selected() and (get_project_selection() == get_chosen_version()))

    with submit_placeholder:
        disabled = False
        reason = None
        if not can_select:
            disabled, reason = True, "Cannot select non-writable project"
        elif is_current_selected:
            disabled, reason = True, "Cannot select already selected project"
        elif not versions:
            disabled, reason = True, "No versions to select from"

        if st.button(
            "Select" if not is_current_selected else "Selected",
            key=f"btn_{slug}",
            disabled=disabled,
            help=reason,
            use_container_width=True,
            type="primary",
        ):
            none_selected = not is_project_selected()
            select_project(get_chosen_version())
            if none_selected:
                update_navigation()
            st.switch_page("page/03_instructions.py")
