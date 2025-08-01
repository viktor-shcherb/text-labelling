from pathlib import Path

from pydantic import BaseModel


class User(BaseModel):
    login: str


class Project(BaseModel):
    """Metadata for a single project version."""

    slug: str
    version: str
    name: str
    description: str | None = None
    repo_url: str
    repo_path: Path
    project_root: Path
