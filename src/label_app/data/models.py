from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal, Union, Type, Mapping

from pydantic import BaseModel, Field, EmailStr


class User(BaseModel):
    email: EmailStr

    model_config = dict(extra="forbid", frozen=True)  # help catch typos


class LabelGroup(BaseModel):
    title: str = None
    single_choice: bool = False
    labels: list[str]

    model_config = dict(extra="forbid", frozen=True)  # help catch typos


class ProjectBase(BaseModel):
    # ── from project.yaml ───────────────────
    name: str
    description: str | None = None
    task_type: str  # discriminator
    instructions: str | None = None

    # ── derived from repository ────────────
    version: str
    slug: str
    repo_url: str
    repo_path: Path
    project_root: Path

    model_config = dict(extra="forbid", frozen=True)  # help catch typos

    @classmethod
    def item_model(cls) -> Type[ItemBase]:
        """Each concrete Project must return its dataset item model."""
        raise NotImplementedError

    @classmethod
    def annotation_model(cls) -> Type[AnnotationBase]:
        raise NotImplementedError


class ItemBase(BaseModel):
    # ── derived from JSONL file ────────────
    # these are not saved on serialization
    key: Path = Field(exclude=True, default=None)  # relative to project root
    idx: int = Field(exclude=True, default=None)
    # important for subclasses: always allow empty class instantiation (every new field has to have default)

    @classmethod
    def empty(cls, key: Path, idx: int) -> ItemBase:
        return cls(key=key, idx=idx)


class AnnotationBase(BaseModel):
    # ── derived from item ────────────
    # these are not saved on serialization
    item: ItemBase = Field(exclude=True, default=None)  # relative to project root
    # important for subclasses: always allow empty class instantiation (every new field has to have default)

    @classmethod
    def empty_for(cls, item: ItemBase) -> AnnotationBase:
        return cls(item=item)


# Chat ────────────────────────────────────

class ChatOptions(BaseModel):
    annotate_roles: tuple[str] = Field(default_factory=tuple, description="Roles to tag")

    model_config = dict(extra="forbid", frozen=True)  # help catch typos


class ChatProject(ProjectBase):
    task_type: Literal["chat"] = "chat"
    chat_options: ChatOptions = Field(default_factory=ChatOptions)
    label_groups: Mapping[str, LabelGroup]  # name to possible labels

    model_config = dict(extra="forbid", frozen=True)  # help catch typos

    @classmethod
    def item_model(cls) -> Type[ItemBase]:
        return ChatItem

    @classmethod
    def annotation_model(cls) -> Type[AnnotationBase]:
        return ChatAnnotation

    def __hash__(self) -> int:
        return hash((self.version, self.slug))


# ── Chat dataset ──────────────────────────────────────────
class Message(BaseModel):
    role: str
    content: str


class ChatItem(ItemBase):
    messages: list[Message] = Field(default_factory=list)
    model_config = dict(extra="forbid")


class ChatAnnotation(AnnotationBase):
    # label group selection per message
    labels: list[dict[str, list[str]]] = Field(default_factory=list)  # name to selected labels

    @classmethod
    def empty_for(cls, item: ChatItem) -> ChatAnnotation:
        return cls(item=item, labels=[{} for _ in item.messages])


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
