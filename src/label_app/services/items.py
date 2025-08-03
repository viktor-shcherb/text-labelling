import functools
from collections import defaultdict
from pathlib import Path
from typing import TypeVar

from pydantic import TypeAdapter, ValidationError

from label_app.data.models import Project, ItemBase


MAX_ERRS_TO_SHOW = 5


@functools.lru_cache()
def load_items_by_file(project: Project) -> dict[Path, list[ItemBase]]:
    items = load_items(project)
    result = defaultdict(list)
    for item in items:
        result[item.key].append(item)
    return result


_ItemType = TypeVar("_ItemType", bound=ItemBase)


@functools.lru_cache(maxsize=1024)
def load_file_items(item_type: _ItemType, rel_path: Path, project_root: Path) -> list[_ItemType]:
    adapter = TypeAdapter(item_type)
    path = project_root.joinpath(rel_path)
    items = []

    with path.open("rb") as f:
        for lineno, raw in enumerate(f):
            # Trim whitespace once, then handle blank/comment lines
            raw = raw.strip()
            if not raw:
                continue

            # skip comments
            if raw.startswith(b"#") or raw.startswith(b"//"):
                continue

            try:
                item: _ItemType = adapter.validate_json(raw)
                # attach derived (non-serialized) metadata
                item.key = rel_path
                item.idx = lineno
                items.append(item)
            except ValidationError as e:
                print(f"[load_file_items] {path}:{lineno}: {e}")

    return items


@functools.lru_cache()
def load_items(project: Project) -> list[ItemBase]:
    """
    Load and validate dataset items for the given project from source/*.jsonl.
    Uses the project's item model (no item_type in rows).
    Attaches .key (Path relative to project root) and .idx (line number).
    """
    src_dir: Path = project.project_root / "source"
    jsonl_files = sorted(src_dir.glob("*.jsonl"))

    if not jsonl_files:
        return []

    item_model = project.item_model()
    items: list[ItemBase] = []

    for path in jsonl_files:
        rel_key = path.relative_to(project.project_root)  # path stored on each item
        items.extend(load_file_items(item_model, rel_key, project.project_root))
    return items
