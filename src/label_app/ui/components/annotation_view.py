from __future__ import annotations

import bisect
import re
from functools import singledispatch
from typing import TypeVar, overload, Any

import streamlit as st

from label_app.data.models import AnnotationBase, ChatAnnotation, Project, ChatProject, LabelGroup

LINES_LIMIT = 5
CHAR_LIMIT = 300
PREVIEW_CHARS = 200
PREVIEW_LINES = 5


_AnnotationType = TypeVar("_AnnotationType", bound=AnnotationBase)


@overload
def render(project: ChatProject, annotation: ChatAnnotation) -> ChatAnnotation: ...


@singledispatch
def render(project: Project, annotation: _AnnotationType) -> _AnnotationType:
    raise TypeError(f"No renderer registered for {type(project).__name__}")


def _split_at_nearest_markdown_safe(s: str, limit: int = 200, lines_limit: int = 5):
    """
    Split markdown-aware at the nearest safe boundary to:
      • `limit` characters, and
      • `lines_limit` lines in the preview.
    """
    n = len(s)
    if n == 0:
        return "", ""

    # Clamp character limit
    limit = min(limit, max(0, n - 1))

    # 1) Identify “atomic” markdown spans we never want to cut inside
    patterns = [
        r'```[\s\S]*?```',    # fenced code blocks
        r'`[^`]*`',           # inline code spans
        r'!\[.*?\]\(.*?\)',   # images
        r'\[.*?\]\(.*?\)',    # links
    ]
    spans = []
    for pat in patterns:
        for m in re.finditer(pat, s):
            spans.append((m.start(), m.end()))
    spans.sort()

    def in_span(pos: int) -> bool:
        """Return True if `pos` is inside any protected span."""
        for st, ed in spans:
            if st <= pos < ed:
                return True
            if pos < st:
                break
        return False

    # 2) Build a sorted list of “safe” cut points:
    #    • Whitespace outside any protected span
    #    • Exact start/end of each protected span
    whitespace_pts = [
        i for i, ch in enumerate(s)
        if ch.isspace() and not in_span(i)
    ]
    elem_pts = [p for span in spans for p in span]
    pts = sorted(set(whitespace_pts + elem_pts))
    if not pts:
        pts = [limit]

    # 3) Helper to pick the safe cut nearest `target`,
    #    and bump it to include any contested element fully.
    def find_cut(target: int) -> int:
        idx = bisect.bisect_left(pts, target)
        candidates = []
        if idx < len(pts):
            candidates.append(pts[idx])
        if idx > 0:
            candidates.append(pts[idx - 1])
        cut = min(candidates, key=lambda x: abs(x - target))
        # If cut is inside a protected span, push it to the span’s start
        for st, ed in spans:
            if st <= cut < ed:
                cut = st
                break
        return cut

    # 4) First pass: cut by character limit
    cut = find_cut(limit)

    # 5) Enforce lines_limit: if preview has more lines than allowed,
    #    recalculate `cut` at the boundary of the Nth newline.
    if lines_limit > 0:
        newline_positions = [i for i, ch in enumerate(s) if ch == "\n"]
        if len(newline_positions) >= lines_limit:
            # Position of the end of the lines_limit'th line
            line_target = newline_positions[lines_limit - 1]
            cut = find_cut(line_target)

    # 6) Build preview/expanded halves
    preview = s[:cut].rstrip() + "\n  ..."
    expanded = s[cut:].lstrip()

    # 7) If preview ballooned to >200% of `limit`, retry at half limit once
    if len(preview) > 2 * limit:
        half = limit // 2
        cut2 = find_cut(half)
        preview2 = s[:cut2].rstrip() + "\n  ..."
        if len(preview2) <= 2 * half:
            preview = preview2
            expanded = s[cut2:].lstrip()

    return preview, expanded


def _fix_annotation(annotation: ChatAnnotation):
    missing = len(annotation.item.conversation) - len(annotation.labels)
    if missing > 0:
        print(f"[render_chat] malformed annotation {annotation.item.key}:{annotation.item.idx}: "
              f"not enough labels, {missing} missing")
        annotation.labels.extend([{} for _ in range(missing)])
    if missing < 0:
        print(f"[render_chat] malformed annotation {annotation.item.key}:{annotation.item.idx}: "
              f"too many labels, {-missing} extra")
        annotation.labels = annotation.labels[:missing]


@render.register
@st.fragment()
def _render_chat(project: ChatProject, annotation: ChatAnnotation) -> ChatAnnotation:
    """Display chat messages with annotation controls.

    Returns the updated annotation.
    """
    _fix_annotation(annotation)
    for idx, msg in enumerate(annotation.item.conversation):
        with st.container(border=True, key=f"container-msg-{idx}"):
            st.markdown(f"**{msg.role}**")
            content = msg.content

            line_count = content.count("\n") + 1

            if len(content) > CHAR_LIMIT or line_count > LINES_LIMIT:
                preview, expanded = _split_at_nearest_markdown_safe(
                    content,
                    limit=PREVIEW_CHARS,
                    lines_limit=PREVIEW_LINES
                )
                with st.expander(preview):
                    st.markdown(expanded)
            else:
                with st.container(border=True):
                    st.markdown(content)

            if msg.role in project.chat_options.annotate_roles:
                cols = st.columns([1] * len(project.label_groups), gap="large")

                def handle_label_change(id_, slug):
                    def callback():
                        new_val = st.session_state[f"{id_}_{slug}"]
                        if new_val is not None:
                            annotation.labels[id_][slug] = new_val if isinstance(new_val, list) else [new_val]

                    return callback

                for (group_slug, group), col in zip(project.label_groups.items(), cols):
                    group: LabelGroup
                    current = annotation.labels[idx].get(group_slug)
                    with col:
                        st.pills(
                            group.title or group_slug, group.labels,
                            selection_mode="single" if group.single_choice else "multi",
                            key=f"{idx}_{group_slug}",
                            on_change=handle_label_change(idx, group_slug),
                            default=current if current is not None else [],
                            width="content"
                        )
    return annotation
