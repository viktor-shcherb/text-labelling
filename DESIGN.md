# Collaborative Text‑Labelling App – Design Document

## 1. Purpose & Scope

A web‑based tool that lets multiple annotators log in with GitHub, Google, or a pre‑shared key, pick a *project* that lives in a GitHub repo, and label small chat transcripts (JSONL). Each annotator’s work is written back to the same repo in a predictable folder layout so that project owners can track progress in Git.

---

## 2. Architecture at a Glance

```
┌─────────┐        ┌────────────────┐        ┌──────────────────┐
│ Browser │─HTTP──▶│ Streamlit UI   │──RPC──▶│ Domain Services  │
└─────────┘        │  (src/ui)      │        │  (src/services)  │
                   └────────▲───────┘        └────────┬─────────┘
                            │                         │
     st.session_state +     │                         ▼
   cached resources (Redis) │                  Git / GitHub API
                            │                         │
                            ▼                         ▼
                         Data Access  ◀──────────▶  Project Repos
                         (src/data)                 (local cache)
```

* **Frontend** – Streamlit pages/components only; no business logic.
* **Domain Services** – pure‑Python modules that talk to Git, validate YAML, merge annotations, etc.
* **Data Layer** – thin wrappers over GitPython + file I/O; optionally Redis for per‑session caching.

---

## 3. Tech Stack

| Concern          | Choice                              | Rationale                     |
| ---------------- | ----------------------------------- | ----------------------------- |
| UI               | Streamlit ≥ 1.35                    | Fast to prototype, multipage. |
| Auth (OAuth)     | Authlib + GitHub / Google endpoints | Works inside Streamlit.       |
| Auth (key)       | SHA‑256 keys stored in secrets      | Simple, no external dep.      |
| Git interactions | GitPython (fallback: dulwich)       | Pure‑Python, no CLI needed.   |
| YAML → objects   | `pydantic` models                   | Validation & docs.            |
| Tests            | pytest + streamlit.testing          | Component/unit isolation.     |
| Container        | Docker + `streamlit run …`          | Identical local/prod runtime. |

---

## 4. Repository Layout

```text
my_label_app/
├─ src/
│  └─ label_app/
│     ├─ ui/                  # Streamlit only
│     │  ├─ main.py           # entry point
│     │  ├─ pages/
│     │  │   ├─ 01_login.py
│     │  │   ├─ 02_project_select.py
│     │  │   └─ 03_annotate.py
│     │  └─ components/
│     │      ├─ chat_view.py
│     │      └─ label_pills.py
│     ├─ services/           # domain logic, no st.* imports
│     │  ├─ auth.py          # OAuth + key verification
│     │  ├─ projects.py      # discover + validate projects
│     │  ├─ annotations.py   # read/write user annotations
│     │  └─ git_client.py    # thin GitPython wrapper
│     ├─ data/
│     │  ├─ models.py        # Pydantic models (Project, Item, …)
│     │  └─ storage.py       # repo cache, optional Redis
│     ├─ config/
│     │  ├─ settings.py      # BaseSettings → env, .streamlit
│     │  └─ state_keys.py    # centralised session_state keys
│     ├─ utils/
│     └─ tests/              # mirrors package layout
├─ .streamlit/
│  ├─ config.toml
│  └─ secrets.toml           # hashed keys & OAuth creds
├─ pyproject.toml            # poetry / hatch
└─ README.md
```

---

### 4.1 UI Pages & Layout

**Global layout conventions**

* **Sidebar (********`st.sidebar`****\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*)** – persistent navigation: project & version selectors (after login), help links, and a logout button.
* **Header row** – page title via `st.header`, optionally a progress badge.
* **Main pane** – task‑specific content rendered by a `*_view` component.
* **Action bar** – sticky container at the bottom with **Save  · Prev  · Next**; implemented once in `ui/components/nav_row.py` and reused.
* **Icons** – prefer Google Material icons over emoji in page and button chrome.

| Page file              | Route label        | Purpose                                                                                                                                                                                                        | Main widgets                                                                                  | Sidebar widgets            |
| ---------------------- | ------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- | -------------------------- |
| `01_login.py`          | **Login**          | Authenticate user via GitHub, Google, or access‑key.                                                                                                                                                           | `st.button` (OAuth), `st.text_input` inside `st.form` (key). Redirects on success.            | –                          |
| `02_project_select.py` | **Project Select** | Scrollable list of **ProjectCard** containers—each shows project title, short description, a **Version** `st.selectbox` (default = last lexicographic), and a **Select** button that loads the chosen version. | Search/filter field, logout                                                                   |                            |
| `03_annotate.py`       | **Annotate**       | Show a single *Item* and collect an *ItemAnnotation*.                                                                                                                                                          | Dynamic `render_item()` from `ui/components/<task_type>_view.py`; progress meter; action bar. | Label legend, project meta |

**ProjectCard layout**

* Render inside `st.container` placed in a `st.scrollable_container()` so a long list doesn’t stretch the page.
* Components inside each card:

  1. `st.markdown(f"### {project.name}")` – project title.
  2. `st.markdown(project.short_description)` – one‑paragraph snippet pulled from `project.yaml`.
  3. `st.selectbox("Version", versions, index=len(versions)-1)` – defaults to the last *lexicographically* sorted version.
  4. `st.button("Select", key=project_slug)` – loads `03_annotate` with `session_state.selected_project` set.

**Adding new task types**

Create `ui/components/<task_type>_view.py`:

```python
from label_app.data.models import Item, ItemAnnotation, Project

def render_item(item: Item, project: Project) -> ItemAnnotation:
    """Render UI and return the annotation model."""
```

`03_annotate.py` dispatches on `project.task_type` to that renderer.

---

## 5. Key Modules & Responsibilities & Responsibilities

### 5.1 `services.auth`

```python
class AuthService:
    def get_authorize_url(provider: Literal["github", "google"]) -> str: ...
    def login_with_oauth(provider: Literal["github", "google"], code: str) -> User: ...
    def login_with_key(key: str) -> User: ...  # constant‑time compare
```

* **Security note** – keys are pre‑hashed with SHA‑256 and stored in `.streamlit/secrets.toml` as `KEY_SHA256 -> user_login` entries. No plain keys on disk.
* OAuth client IDs and secrets are also stored under `[oauth]` sections in `secrets.toml`.
* The login screen is presented in a modal via `require_login()`; all pages call this helper so navigation is blocked until authentication succeeds. The access-key form hints to contact the admin using `Settings.admin_email`.

### 5.2 `services.projects`

* Clone/pull each *project repo* into `~/.cache/label_app/repos/<org>/<repo>`.
* **Discover versions**: every top‑level directory name (e.g. `v1`, `2025‑07‑release`) is treated as a version. A dropdown in the Project‑Select page lets the annotator pick which version they want.
* Parse **`<version>/project.yaml`** (see §6) → `Project` model.
* Expose the version’s *source* tree and compute the per‑user annotation path: `<version>/annotation/<login>/…`.
* Provide helpers `list_versions(repo) -> list[str]` and `get_current(project, version)` that downstream UI can call.

### 5.3 `services.annotations`

* `load_item(project: Project, rel_path: str) -> Item`  (pulls the raw content line from the source JSONL).

* `save_annotation(user: User, item_id: str, annotation: ItemAnnotation)`  (writes JSON with annotation only—**not** the original content) under `<version>/annotation/<login>/<rel_path>`.

* Auto‑commit & push on save. Save on button click and each 5 minutes if there are any unsaved changes. Commits go to the project's source branch; per‑user directories keep work isolated.

* **Schema separation**: `Item` holds immutable source content; `ItemAnnotation` holds user metadata (`labels`, `free_text`, etc.). The two share a stable `id` key so they can be joined downstream.
  `services.annotations`

* `load_item(project: Project, rel_path: str) -> ChatItem`  (pulls JSONL line).

* `save_annotation(user: User, item: ChatItem, labels: dict[str, str])`  (writes JSONL with `{"id":…, "labels":…}`) under `annotation/<login>/<rel_path>`.

* Auto‑commit & push on save (configurable). Commits land on the same branch as the project's source.

### 5.4 `ui.pages.03_annotate`

* Reads session state `current_item_idx`, `dirty`, `labels`.
* ChatList component renders messages; below each message LabelPills renders allowed labels.
* Buttons: **Save**, **Prev**, **Next**. Save flushes via `annotations.save_annotation`; on change sets `dirty=True`.
* Streamlit `on_event("page_unload")` (experimental) pops a modal if `dirty`.

---

### 5.5 Data Models & Class Hierarchy

`src/label_app/data/models.py`

```python
from pydantic import BaseModel
import abc

class Item(BaseModel, abc.ABC):
    """Immutable source unit that every annotator sees."""
    id: str              # stable across versions

class ItemAnnotation(BaseModel, abc.ABC):
    """User‑generated data that refers to an Item by id."""
    id: str              # item id
    annotator: str       # login / handle
```

Every **task type** contributes concrete subclasses that extend the two base classes and add fields relevant to that data shape.  The UI renderer for a task imports these subclasses exclusively—so adding a new task means:

1. Add `MyItem` & `MyItemAnnotation` to `models.py`.
2. Implement `render_item()` in a new `components/<task_type>_view.py`.
3. Include the task‑specific options block in `project.yaml`.

#### Chat task subclasses (current implementation)

```python
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatItem(Item):
    messages: list[ChatMessage]

class ChatAnnotation(ItemAnnotation):
    labels: list[dict[str, str]]  # label_group -> chosen label for each message
```

---

## 6. Project Directory Layout & YAML Schema

### 6.1 Directory Layout

```
<repo_root>/
└─ <version>/               # e.g. v1, v2, 2025‑07‑release
   ├─ project.yaml          # task definition for THAT version
   ├─ source/               # arbitrary sub‑tree of *.jsonl, images, etc.
   └─ annotation/           # created by the app on first save
      └─ <login>/           # one folder per annotator
         └─ … (mirrors source tree) …
```

Only **annotation files** live under `annotation/<login>`; source data is *never* copied there.

### 6.2 YAML Schema (`<version>/project.yaml`)

```yaml
# required
name: "Support Chat Triage"
task_type: chat            # one of: chat, classification, span, image_tagging, …

# optional: UI + label specs
label_groups:
  sentiment:
    single_choice: true
    labels: [positive, neutral, negative]
  actionability:
    single_choice: true
    labels: [action_required, ignore]

chat_options:
  annotate_roles: [user, assistant]
```

Key points:

* **`task_type`** drives the UI: each value matches a component module in `ui/components/*_view.py` implementing `render_item()` and returning that task’s `ItemAnnotation` subclass.
* Unknown keys fail schema validation so typos are caught early.

### 6.3 Chat Task Type – Data Model & Annotation Screen

| Aspect               | Design                                                                                                                                                                                                                                                                                              |
| -------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Source model**     | `ChatItem` (see §5.5): list of `ChatMessage` objects.                                                                                                                                                                                                                                               |
| **Annotation model** | `ChatAnnotation`: per‑message or per‑dialog label map.                                                                                                                                                                                                                                              |
| **Screen layout**    | Vertically scrollable chat  column (`ChatView` component). Under each message, `LabelPills` renders the label groups that apply to that role. Long messages are "shortened": only the first 200 and the last 100 characters are shown. The option to view the full message is provided to the user  |
| **Controls**         | Sticky action bar with **Prev / Next / Save** ; dirty‑state warning on unload.                                                                                                                                                                                                                      |
| **State keys**       | `current_item_idx`, `labels` (`dict[str,str]`), `dirty`.                                                                                                                                                                                                                                            |
| **Save behaviour**   | Writes `ChatAnnotation` JSON under `<version>/annotation/<login>/<rel_path>`; commits to the project's source branch.                                                                                                                                                                             |
|                      |                                                                                                                                                                                                                                                                                                     |

---

## 7. Streamlit State & Caching. Streamlit State & Caching

| Key                | Type                  | Lifetime                |
| ------------------ | --------------------- | ----------------------- |
| `user`             | `User`                | browser session         |
| `selected_project` | `Project`             | until logout            |
| `item_cache`       | `dict[int, ChatItem]` | LRU via `st.cache_data` |
| `dirty`            | `bool`                | page session            |
| `labels`           | `dict`                | page session            |

Heavy resources (Git repo object) go through `st.cache_resource` so multiple users share one in‑memory object.

---

## 8. Deployment & Ops (Streamlit Community Cloud)

| Checklist                          | Notes                                                                                                                                                                               |
| ---------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Dependencies**                   | List every Python package in `requirements.txt` **or** under `[project.dependencies]` in `pyproject.toml`. Streamlit Cloud installs only from these files.                          |
| **Secrets**                        | Add hashed keys, OAuth client IDs/secrets, and a GitHub Personal Access Token (PAT) with `repo` scope as **Secrets** in the Cloud UI; read them with `st.secrets["…"]`.             |
| **OAuth redirect**                 | Register `https://share.streamlit.io/<user>/<repo>/main` (or the branch path) as an *authorized redirect URI* in GitHub / Google developer consoles.                                |
| **Git push**                       | Compose an HTTPS remote like `https://x-access-token:${GITHUB_PAT}@github.com/{org}/{repo}.git` and set `git config user.email` / `git config user.name` at runtime before pushing. |
| **Caching**                        |  `st.cache_data` and `st.cache_resource` are plenty because a Cloud app runs in a single Python process.                                                                            |
| **Repo cache**                     | Clone repos to `/app/.cache/label_app/repos`. The directory survives app restarts but is wiped on redeploy.                                                                         |
| **File watcher**                   | Prevent *Too many files open* warnings by adding `fileWatcherType = "none"` to `.streamlit/config.toml`                                                                             |
| **System packages**                | If you ever need non‑Python libs, create an `apt-packages` file; Streamlit Cloud installs them automatically.                                                                       |

## 9. Testing Strategy&#x20;

| Layer           | Tooling               | What to test                              |
| --------------- | --------------------- | ----------------------------------------- |
| Domain services | pytest + fixtures     | Git repo ops, YAML validation, save logic |
| UI components   | streamlit.testing     | Label selection, dirty‑state warnings     |
| Integration     | Playwright / Selenium | Login → annotate → commit happy path      |
