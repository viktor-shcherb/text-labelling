import streamlit as st

from pathlib import Path
from typing import Dict

import yaml
from pydantic import BaseModel, EmailStr, Field


class AppSettings(BaseModel):
    """Strongly-typed application configuration."""

    admin_email: EmailStr = Field(..., description="Administrator contact email")
    public_keys: Dict[str, str] = Field(
        default_factory=dict,
        description="Mapping from username to their public key (SHA-256 of their private key)",
    )
    projects: Dict[str, str] = Field(
        default_factory=dict,
        description="Mapping from project slugs to project repositories",
    )

    class Config:
        frozen = True  # make instances hashable & read-only


APP_DIR: Path = Path("src/label_app")
DEFAULT_SETTINGS_PATH: Path = APP_DIR / "app_settings.yaml"


@st.cache_data(show_spinner=False, ttl="15m")
def get_settings(path: Path | str = DEFAULT_SETTINGS_PATH) -> AppSettings:
    """Return a cached :class:`AppSettings` instance loaded from *path*.

    Parameters
    ----------
    path:
        Path to the YAML file (defaults to ``src/label_app/app_settings.yaml``).
    """
    path = Path(path)
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Settings file not found at '{path}'. Create it or pass a custom path."
        ) from exc

    return AppSettings(**data)

