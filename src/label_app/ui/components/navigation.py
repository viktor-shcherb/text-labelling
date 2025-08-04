import streamlit as st
from streamlit.runtime.scriptrunner_utils.script_run_context import get_script_run_ctx
from streamlit.source_util import PageInfo

from label_app.services.persistent_state.project import is_project_selected
from label_app.ui.components.auth import is_logged_in


def get_login_page(*, default: bool = False):
    return st.Page(
        "page/01_login.py",
        title="Login",
        url_path="login",
        default=default
    )


def get_project_selection_page(*, default: bool = False):
    return st.Page(
        "page/02_project_select.py",
        title="Projects",
        icon=":material/folder_open:",
        url_path="projects",
        default=default
    )


def get_instructions_page(*, default: bool = False):
    return st.Page(
        "page/03_instructions.py",
        title="Instructions",
        icon=":material/menu_book:",
        url_path="instructions",
        default=default
    )


def get_annotations_page(*, default: bool = False):
    return st.Page(
        "page/04_annotate.py",
        title="Annotate",
        icon=":material/edit:",
        url_path="annotations",
        default=default
    )


def get_active_pages() -> list[st.Page]:
    if not is_logged_in():
        # only allow login page
        return [
            get_login_page(default=True),
        ]
    elif not is_project_selected():
        # only allow project selection page
        return [
            get_project_selection_page(default=True),
        ]

    return [
        get_project_selection_page(),
        get_instructions_page(default=True),
        get_annotations_page(),
    ]


def update_navigation():
    get_script_run_ctx().pages_manager.set_pages({
    page._script_hash: PageInfo( # noqa
        script_path=str(page._page), # noqa
        page_script_hash=page._script_hash, # noqa
        icon=page.icon,
        page_name=page.title,
        url_pathname=page.url_path
    ) for page in get_active_pages()})


def setup_navigation() -> st.navigation:
    sidebar = is_logged_in()
    return st.navigation(get_active_pages(), position="hidden" if not sidebar else "sidebar", expanded=sidebar)
