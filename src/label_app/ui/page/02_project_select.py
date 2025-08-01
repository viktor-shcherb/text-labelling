import streamlit as st

from label_app.config.settings import get_settings
from label_app.services.projects import discover_projects
from label_app.ui.components.auth import require_login, sidebar_logout

require_login()

st.header("Project Selection")

sidebar_logout()
search = st.sidebar.text_input("Search")

projects = discover_projects(get_settings())

with st.scrollable_container():
    for slug, versions in projects.items():
        version_names = sorted(p.version for p in versions)
        default_idx = len(version_names) - 1

        meta = versions[default_idx]
        if search and search.lower() not in meta.name.lower():
            continue

        with st.container():
            st.markdown(f"### {meta.name}")
            if meta.description:
                st.markdown(meta.description)

            chosen_version = st.selectbox(
                "Version",
                version_names,
                index=default_idx,
                key=f"ver_{slug}",
            )

            if st.button("Select", key=f"btn_{slug}"):
                selected = next(p for p in versions if p.version == chosen_version)
                st.session_state.selected_project = selected
                st.switch_page("page/03_annotate.py")
