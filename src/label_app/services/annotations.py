import json
import os
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Type, TypeVar

import streamlit as st
from git import Repo
from pydantic import TypeAdapter, ValidationError

from label_app.data.models import Project, User, ItemBase, AnnotationBase
from label_app.services.items import load_items_by_file

MAX_ERRS_TO_SHOW = 5


def _annotation_path_for_key(root: Path, email: str, key: Path) -> Path:
    """
    Map a dataset key (relative to project root) to the per-user annotation JSON file.
    E.g. key='source/train.jsonl' -> 'annotation/<email>/source/train.jsonl'
    """
    safe_email = re.sub(r"[^a-zA-Z0-9._-]", "_", email)
    target = (root / "annotation" / safe_email / key)
    return target.with_suffix(".jsonl")


def _atomic_write_lines(path: Path, lines: Iterable[str]) -> None:
    """Atomically write text lines (newline-terminated) to a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8", newline="\n") as f:
            for line in lines:
                # Avoid double newlines if caller passed '\n' already
                if line.endswith("\n"):
                    f.write(line)
                else:
                    f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        # best-effort durability for the directory entry
        try:
            dir_fd = os.open(str(path.parent), os.O_DIRECTORY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except Exception:
            pass
    except Exception:
        try:
            tmp.unlink()
        except Exception:
            pass
        raise


def _to_json(annotation: AnnotationBase) -> str:
    return json.dumps(annotation.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))


def read_annotations(annot_cls: Type[AnnotationBase], path: Path, items: list[ItemBase]) -> list[str]:
    """Read annotations as raw lines; strip newline terminators, keep content as-is."""
    if not path.exists():
        # create filler
        return [_to_json(annot_cls.empty_for(item)) for item in items]
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return [ln.rstrip("\r\n") for ln in f]


_AnnotationType = TypeVar("_AnnotationType", bound=AnnotationBase)


def load_file_annotations(
        annot_cls: Type[_AnnotationType],
        user: User, rel_path: Path, project_root: Path,
        items: list[ItemBase]
) -> list[_AnnotationType]:

    path = _annotation_path_for_key(project_root, user.email, rel_path)
    if not path.exists():
        # create filler
        return [annot_cls.empty_for(item) for item in items]

    adapter = TypeAdapter(annot_cls)
    annotations = []

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
                annotation: _AnnotationType = adapter.validate_json(raw)
                # attach derived (non-serialized) metadata
                annotation.item = items[lineno]
                annotations.append(annotation)
            except ValidationError as e:
                print(f"[load_file_annotations] {path}:{lineno}: {e}")

    return annotations


def save_annotations(project: Project, user: User, annotations: Iterable[AnnotationBase]) -> None:
    """
    Persist annotations to disk and **stage** modified files only.

    This function no longer creates commits or pushes; the background flusher
    is responsible for batching commits (staged-only) and pushing to GitHub.
    """
    items = load_items_by_file(project)  # cached so cheap
    repo = Repo(project.repo_path)
    worktree = Path(repo.working_tree_dir).resolve()

    # --- 0) Verify types and group by key --------------------------------------
    annot_cls: Type[AnnotationBase] = project.annotation_model()

    grouped: dict[Path, list[AnnotationBase]] = defaultdict(list)
    max_idx_by_key: dict[Path, int] = defaultdict(int)

    for ann in annotations:
        if not isinstance(ann, annot_cls):
            raise TypeError(
                f"Annotation type mismatch: expected {annot_cls.__name__}, got {type(ann).__name__}"
            )
        # Validate that key is relative to project root (and safe)
        try:
            rel_key = Path(ann.item.key)  # should already be relative
            # Resolve a *candidate* on disk and ensure it stays inside the repo when rooted
            (worktree / rel_key).resolve().relative_to(worktree)
        except Exception:
            raise ValueError(f"Annotation key must be a path relative to project root: {ann.item.key!r}")

        if ann.item.idx < 0:
            raise ValueError(f"Annotation idx must be >= 0; "
                             f"got {ann.item.idx} for key {rel_key}")

        local_items = items[rel_key]
        if ann.item.idx >= len(local_items):
            raise ValueError(f"Annotation idx exceeds number of items; "
                             f"got {ann.item.idx} for #items = {len(local_items)} for key {rel_key}")

        grouped[rel_key].append(ann)
        if ann.item.idx > max_idx_by_key[rel_key]:
            max_idx_by_key[rel_key] = ann.item.idx

    if not grouped:
        st.info("No annotations to save.")
        return

    # --- For each key: read raw lines, apply diffs, write+stage only if changed --
    staged_paths: list[str] = []
    files_updated = 0
    rows_written_total = 0

    for key, new_anns in grouped.items():
        local_items = items[key]

        ann_path = _annotation_path_for_key(worktree, user.email, key).resolve()
        ann_path.relative_to(worktree)  # safety: must stay inside repo

        # 1) Read existing JSONL as raw lines (or filler if missing)
        lines = read_annotations(annot_cls, ann_path, items=local_items)
        if len(lines) != len(local_items):
            raise ValueError(f"Broken file at {key}: Number of read annotations does not match number of items")

        # 2) Apply only effective changes
        changed = False
        for ann in new_anns:
            pos = ann.item.idx
            new_line = _to_json(ann)
            if lines[pos] != new_line:
                lines[pos] = new_line
                changed = True

        if not changed:
            # Nothing to write or stage for this file
            continue

        # 3) Persist atomically
        _atomic_write_lines(ann_path, lines)

        # 4) Stage the updated file
        rel = str(ann_path.relative_to(worktree))
        repo.index.add([rel])
        staged_paths.append(rel)
        files_updated += 1
        rows_written_total += len(lines)

    if not staged_paths:
        st.info("No changes to stage.")
        return

    st.success(
        f"Staged {files_updated} file{'s' if files_updated != 1 else ''} "
        f"({rows_written_total} rows total). "
        "Changes will be auto-committed and pushed by the background flusher."
    )
    st.session_state.last_save_ts = time.time()
