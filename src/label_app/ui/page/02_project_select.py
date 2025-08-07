from pathlib import Path

import streamlit as st

from label_app.services.github.branch_tracker import reset_trackers
from label_app.services.persistent_state.version_selection import get_version_selection, set_version_selection
from label_app.services.projects import discover_projects
from label_app.ui.components.access_fix import fill_access_holder
from label_app.ui.components.auth import sidebar_logout
from label_app.ui.components.project import display_project


# ----------------------------- Page body -------------------------------------

header_col, refresh_col = st.columns([10, 1], vertical_alignment="bottom")
access_holder = st.empty()
projects_holder = st.empty()

sidebar_logout()
img_path = Path(__file__).parent.with_name("static") / "icon_with_border.png"
st.logo(img_path, size="large")

projects, meta_by_slug = discover_projects()
tracker_keys = set((meta["repo_url"], meta["branch"]) for meta in meta_by_slug.values())

with header_col:
    st.header("Project Selection", anchor="project-selection")
with refresh_col:
    if st.button("", icon=":material/refresh:", help="Refresh projects"):
        reset_trackers(tracker_keys)

# -------- Top panel: Fix access for entire owner installations ---------------
fill_access_holder(access_holder, meta_by_slug)

# -------- Version selection defaults (for readable projects with versions) ----

defaults = {
    slug: sorted(p.version for p in versions)[-1]
    for slug, versions in projects.items()
    if versions  # skip unreadable or empty
}
version_selection = get_version_selection() or defaults
set_version_selection({**defaults, **version_selection})

# ------------------------- Projects listing ----------------------------------

with projects_holder:
    with st.container():
        for slug, versions in projects.items():
            meta = meta_by_slug.get(slug, {})
            with st.container(border=True):
                display_project(slug, versions, meta)
