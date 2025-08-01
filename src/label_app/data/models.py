from __future__ import annotations

from pathlib import Path
from typing import Annotated, Dict, List, Literal, Union

from pydantic import BaseModel, Field


class User(BaseModel):
    login: str


class LabelGroup(BaseModel):
    single_choice: bool = False
    labels: List[str]


class ProjectBase(BaseModel):
    # ── from project.yaml ───────────────────
    name: str
    description: str | None = None
    task_type: str                           # discriminator

    # ── derived from repository ────────────
    version: str
    slug: str
    repo_url: str
    repo_path: Path
    project_root: Path

    model_config = dict(extra="forbid")      # help catch typos


# Chat ────────────────────────────────────

class ChatOptions(BaseModel):
    annotate_roles: List[str] = Field(default_factory=list, description="Roles to tag")


class ChatProject(ProjectBase):
    task_type: Literal["chat"] = "chat"
    chat_options: ChatOptions = Field(default_factory=ChatOptions)
    label_groups: Dict[str, LabelGroup]


# ──────────────────────────────────────────

# Polymorphic union – Pydantic picks the right subclass by task_type
Project = Annotated[
    Union[ChatProject],                     # , ImageProject, …
    Field(discriminator="task_type"),
]


# ────────────────────────────────────────────────────────────────
# Factory helper for callers that already have repo metadata
# ────────────────────────────────────────────────────────────────
def make_project(
    yaml_data: dict,
    *,
    slug: str,
    version: str,
    repo_url: str,
    repo_path: Path,
    project_root: Path,
) -> Project:
    """
    Combine YAML + repo context and return the *right* Project subclass.
    Raises `pydantic.ValidationError` if the YAML doesn't match a model.
    """
    merged = {
        **yaml_data,
        "slug": slug,
        "version": version,
        "repo_url": repo_url,
        "repo_path": repo_path,
        "project_root": project_root,
    }
    return Project.model_validate(merged)   # discriminator magic
