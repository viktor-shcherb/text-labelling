import json
import re
from pathlib import Path
from typing import Any

import streamlit as st
from platformdirs import user_cache_dir

from label_app.ui.components.auth import is_logged_in, current_user

APP = "label_app"

# Base directory where local git clones are stored:
#   <user_cache_dir(APP)>/repos
CACHE_DIR: Path = Path(user_cache_dir(APP)) / "states"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


@st.cache_data()
def get_user_file(user: str) -> Path:
    safe_user = re.sub(r"[^a-zA-Z0-9._-]", "_", user)
    return CACHE_DIR / f"{safe_user}.json"


@st.cache_data()
def get_state(user: str) -> dict[str, Any]:
    user_file = get_user_file(user)
    if not user_file.exists():
        return {}

    with user_file.open() as f:
        data = json.load(f)

    return data


def save_state(user: str, state: dict[str, Any]) -> None:
    user_file = get_user_file(user)
    with user_file.open("w") as f:
        json.dump(state, f)


def get_value(user: str, key: str) -> Any | None:
    return get_state(user).get(key, None)


def set_value(user: str, key: str, value: Any) -> None:
    state = get_state(user)
    if value != state.get(key, None):
        state[key] = value
        invalidate_cache()
        save_state(user, state)


def set_values(user: str, values: dict[str, Any]) -> None:
    state = get_state(user)
    any_change = False
    for key, value in values.items():
        if value != state.get(key, None):
            any_change = True
            break

    if not any_change:
        return

    state.update(values)
    invalidate_cache()
    save_state(user, state)


def invalidate_cache() -> None:
    get_state.clear()


def session_state_sync(user: str, key: str) -> None:
    if key in st.session_state:
        # session state is a ground truth
        set_value(user, key, st.session_state[key])
    else:
        value = get_value(user, key)
        if value is not None:
            st.session_state[key] = value


def get_authenticated_user() -> str:
    if not is_logged_in():
        raise RuntimeError("Unauthenticated")

    return current_user().email
