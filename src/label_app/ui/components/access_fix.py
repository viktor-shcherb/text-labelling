import streamlit as st

from label_app.services.git.config import APP_SLUG
from label_app.services.git.install_link import get_owner_profile, build_install_link_for_many


def _group_all_repos_by_owner(meta_by_slug: dict[str, dict]) -> dict[str, set[str]]:
    """
    Collect **all** mentioned repos per owner, regardless of access state.
    { owner_login: {repo, ...}, ... }
    """
    by_owner: dict[str, set[str]] = {}
    for meta in meta_by_slug.values():
        owner = meta.get("owner")
        repo = meta.get("repo")
        if not owner or not repo:
            continue
        by_owner.setdefault(owner, set()).add(repo)
    return by_owner


def _owners_needing_fix(meta_by_slug: dict[str, dict]) -> set[str]:
    """
    Owners for which **any** repo needs install or write permission.
    """
    owners: set[str] = set()
    for meta in meta_by_slug.values():
        owner = meta.get("owner")
        repo = meta.get("repo")
        if not owner or not repo:
            continue
        read_ok = bool(meta.get("read_ok"))
        write_ok = bool(meta.get("write_ok"))
        needs_install = not read_ok
        needs_write = read_ok and not write_ok
        if needs_install or needs_write:
            owners.add(owner)
    return owners


@st.cache_data(show_spinner=False)
def _owner_label(owner: str) -> str:
    """Pretty label for owner selector: 'Name (@login)' or '@login'."""
    prof = get_owner_profile(owner)  # cached
    name = (prof.get("name") or "").strip()
    login = prof.get("login") or owner
    return f"{name} (@{login})" if name else f"@{login}"


def fill_access_holder(access_holder: st.empty, meta_by_slug: dict):
    all_repos_by_owner = _group_all_repos_by_owner(meta_by_slug)
    owners_needing_fix = _owners_needing_fix(meta_by_slug)

    if owners_needing_fix:
        with access_holder:
            with st.container(border=True):
                st.subheader("Fix access")

                col_select, col_submit = st.columns([2, 1], gap="small", vertical_alignment="bottom")
                # Limit selector to owners that actually need changes
                with col_select:
                    owners = sorted(owners_needing_fix, key=str.lower)
                    labels = [_owner_label(o) for o in owners]
                    idx = st.selectbox("Account", options=list(range(len(owners))), format_func=lambda i: labels[i])
                    owner = owners[idx]

                # IMPORTANT: include **all** mentioned repos for this owner in the link,
                # not just the ones with issues, to avoid losing previously granted repos.
                repos = sorted(all_repos_by_owner.get(owner, []))

                # Build the bulk link (prefilled up to 100 repo IDs; GitHub’s limit)
                install_url = build_install_link_for_many(APP_SLUG, owner, repos)

                explanation_col, repo_list_col = st.columns([2, 1])

                with explanation_col:
                    st.markdown(
                        "Grant the app access/write for this account so you can save annotations. "
                        "The link includes **all projects** listed for this account to avoid "
                        "dropping access to repositories that are already working."
                    )

                with repo_list_col:
                    # Explicit checklist of repositories to verify on the GitHub screen
                    st.markdown("**Make sure the following repositories are selected:**")
                    if len(repos) <= 20:
                        st.markdown("\n".join(f"- `{r}`" for r in repos))
                    else:
                        first, rest = repos[:20], repos[20:]
                        st.markdown("\n".join(f"- `{r}`" for r in first))
                        with st.expander(f"Show {len(rest)} more"):
                            st.markdown("\n".join(f"- `{r}`" for r in rest))

                # CTA(s)
                with col_submit:
                    cta = f"Grant access ({len(repos)} repo{'s' if len(repos)!=1 else ''})"
                    st.link_button(cta, install_url, type="primary", use_container_width=True)

                with explanation_col:
                    st.caption(
                        "Tip: Some private repositories may not appear preselected; "
                        "check them manually on the next screen. "
                        "After completing the flow, click **Refresh** (top-right)."
                    )
