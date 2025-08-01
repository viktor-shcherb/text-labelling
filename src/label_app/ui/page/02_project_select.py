import streamlit as st

from label_app.data.models import Project
from label_app.services.projects import discover_projects
from label_app.services.git_client import clone_or_pull
from label_app.ui.components.auth import sidebar_logout
from label_app.ui.components.version_selection import get_version_selection


@st.fragment()
def display_project(slug: str, versions: list[Project]):
    selected_version = st.session_state.version_selection[slug]
    version_names = sorted(p.version for p in versions)
    selected_idx = version_names.index(selected_version)

    project = versions[selected_idx]

    with st.container(border=True):
        col_data, col_actions = st.columns([3, 1])
        with col_data:
            is_latest = selected_idx == len(versions) - 1
            st.markdown(f"##### {project.name}"
                        + (" :red-badge[latest]" if is_latest else "")
                        + f" :blue-badge[{project.task_type}]"
        )
            if project.description:
                st.markdown(project.description)

        with col_actions:
            chosen_version = st.selectbox(
                "Version",
                version_names,
                index=selected_idx,
                key=f"ver_{slug}",
            )
            chosen_idx = version_names.index(chosen_version)
            if chosen_idx != selected_idx:
                # selected version changed, need to redraw
                st.session_state.version_selection[slug] = chosen_version
                st.rerun(scope="fragment")

            selected_project = next(p for p in versions if p.version == chosen_version)
            is_current_selected = "selected_project" in st.session_state \
                                  and (st.session_state.selected_project == selected_project)

            if st.button(
                "Select" if not is_current_selected else "Selected",
                key=f"btn_{slug}",
                disabled=is_current_selected,
                use_container_width=True,
                type="primary"
            ):
                st.session_state.selected_project = selected_project
                st.switch_page("page/03_annotate.py")


header_col, refresh_col = st.columns([10, 1], vertical_alignment="bottom")
with header_col:
    st.header("Project Selection")
with refresh_col:
    if st.button("", icon=":material/refresh:", help="Refresh projects"):
        discover_projects.clear()
        clone_or_pull.clear()

projects_holder = st.empty()

sidebar_logout()

projects = discover_projects()

version_selection = get_version_selection() or {
    slug: sorted(p.version for p in versions)[len(versions) - 1]
    for slug, versions in projects.items()
}
st.session_state.version_selection = version_selection

with projects_holder:
    with st.container():
        for slug, versions in projects.items():
            display_project(slug, versions)
