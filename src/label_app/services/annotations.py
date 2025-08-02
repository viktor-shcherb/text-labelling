from __future__ import annotations

import json
import time
from urllib.parse import urlparse

import streamlit as st
from git import Repo

from label_app.data.models import ChatItem, Project, User


@st.cache_data(show_spinner=False)
def load_items(project: Project) -> list[ChatItem]:
    """Load all chat items from the project's source directory."""
    src_dir = project.project_root / "source"
    jsonl_files = list(src_dir.glob("*.jsonl"))
    if not jsonl_files:
        st.error("No source .jsonl files found")
        return []
    path = jsonl_files[0]
    items: list[ChatItem] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            items.append(ChatItem(**data))
    return items


def _authed_remote_url(remote_url: str, token: str) -> str:
    parsed = urlparse(remote_url)
    return f"https://x-access-token:{token}@{parsed.netloc}{parsed.path}"


def save_annotation(project: Project, user: User, item: ChatItem, labels: list[dict[str, str]]) -> None:
    """Write annotation JSON and push commit to the project's source branch."""
    ann_dir = project.project_root / "annotation" / user.login
    ann_dir.mkdir(parents=True, exist_ok=True)
    ann_path = ann_dir / f"{item.id}.json"
    with ann_path.open("w", encoding="utf-8") as f:
        json.dump({"id": item.id, "labels": labels}, f, ensure_ascii=False, indent=2)

    repo = Repo(project.repo_path)
    repo.index.add([str(ann_path.relative_to(project.repo_path))])
    repo.index.commit(f"Add annotation for {item.id} by {user.login}")

    token = st.secrets.get("GITHUB_PAT")
    if token:
        remote = repo.remotes.origin
        orig_url = remote.url
        authed = _authed_remote_url(orig_url, token)
        remote.set_url(authed)
        remote.push(repo.active_branch.name)
        remote.set_url(orig_url)
    else:
        st.warning("GITHUB_PAT not set; skipping push")

    # update timestamp for autosave logic
    st.session_state.last_save_ts = time.time()
