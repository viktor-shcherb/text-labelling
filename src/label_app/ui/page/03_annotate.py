from __future__ import annotations

import time
import streamlit as st

from label_app.data.models import ChatProject
from label_app.services.annotations import load_items, save_annotation
from label_app.ui.components.auth import current_user, sidebar_logout
from label_app.ui.components.chat_view import render_chat
from label_app.ui.components.nav_row import nav_row


if "selected_project" not in st.session_state:
    st.switch_page("page/02_project_select.py")

project: ChatProject = st.session_state.selected_project  # type: ignore
user = current_user()

items = load_items(project)
if not items:
    st.stop()

if "current_item_idx" not in st.session_state:
    st.session_state.current_item_idx = 0
if "labels" not in st.session_state:
    st.session_state.labels = [dict() for _ in items[0].messages]
if "dirty" not in st.session_state:
    st.session_state.dirty = False

current_idx = st.session_state.current_item_idx
item = items[current_idx]
labels = st.session_state.labels

# ----- periodic autosave -----
last_ts = st.session_state.get("last_save_ts", 0)
if st.session_state.dirty and time.time() - last_ts > 300:
    save_annotation(project, user, item, labels)
    st.session_state.dirty = False

st.header(f"Annotate – {project.name}")

new_labels = render_chat(
    item,
    labels,
    label_groups=project.label_groups,
    annotate_roles=project.chat_options.annotate_roles,
)

if new_labels != labels:
    st.session_state.labels = new_labels
    st.session_state.dirty = True


def on_save():
    save_annotation(project, user, item, st.session_state.labels)
    st.session_state.dirty = False


def on_prev():
    if st.session_state.current_item_idx > 0:
        st.session_state.current_item_idx -= 1
        new_item = items[st.session_state.current_item_idx]
        st.session_state.labels = [dict() for _ in new_item.messages]


def on_next():
    if st.session_state.current_item_idx < len(items) - 1:
        st.session_state.current_item_idx += 1
        new_item = items[st.session_state.current_item_idx]
        st.session_state.labels = [dict() for _ in new_item.messages]

nav_row(on_prev=on_prev, on_save=on_save, on_next=on_next)

sidebar_logout()
