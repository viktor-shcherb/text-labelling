# Text Labelling App

<img width="2043" height="738" alt="banner_text_labelling (1)" src="https://github.com/user-attachments/assets/74556a50-e609-4186-b31e-bd149b1e940a" />

A collaborative annotation tool designed for easy deployment and customization. It provides out-of-the-box support for real-time multi-user labeling, project versioning, and seamless persistance to GitHub without additional infrastructure.

**Key Features:**

* **Collaborative Annotation:** Multiple contributors can label data concurrently with real‑time updates.
* **Flexible Data Model:** Built with Pydantic for custom project, item, and annotation schemas.
* **Versioned Projects:** Track iterations and changes across project versions.
* **GitHub Integration:** Store source data and annotations directly in your repository for auditability.
* **Extensible UI:** Plug in your own rendering logic and controls without touching core code.

**Potential Limitations:**

* **Auth0 Authentication Only:** Requires an Auth0 tenant (OAuth2/OpenID Connect).
* **GitHub Storage Constraints:** Best suited for datasets within GitHub’s size limits (see [GitHub Community discussion](https://github.com/orgs/community/discussions/120943#discussioncomment-9209743)).
* **Single-Instance Assumption:** Running multiple instances of the app on the same project/version may overwrite each other’s changes and corrupt the repository.

---

# Deployment

Deploying the Text Labelling App is straightforward but requires initial setup for Auth0 and GitHub integrations. You can run the app locally for development or deploy to Streamlit Cloud for production.

**Prerequisites**

* Python 3.8+
* `pip` package manager
* Auth0 tenant (free tier available)
* GitHub account with permission to create Apps

## 1. Auth0 Integration

1. **Create an Auth0 Application**

   * In the Auth0 dashboard, add a new "Web Application".
   * Under **Settings → Application URIs**, configure:

     * **Allowed Callback URLs:** `https://<your-domain>/oauth2callback`
     * **Allowed Logout URLs:** Your app origin.
2. **Configure Secrets**
   In your project’s `secrets.toml`, add:

   ```toml
   [auth]
   redirect_uri = "https://<your-domain>/oauth2callback"
   cookie_secret = "<random SHA‑256 or longer string>"

   [auth.auth0]
   client_id = "<Auth0 Client ID>"
   client_secret = "<Auth0 Client Secret>"
   server_metadata_url = "https://<your-tenant>.<region>.auth0.com/.well-known/openid-configuration"
   ```

## 2. GitHub Integration

1. **Create a GitHub App**

   * Go to **Settings → Developer settings → GitHub Apps** and click **New GitHub App**.
   * Grant **Permissions**: `Repository contents: Read & write`.
2. **Generate Credentials**

   * In your GitHub App settings, generate a **Private Key** (.pem file).
   * Note the **Client ID**, **Client Secret**, and **App ID**.
   * Record your App’s **slug** (last segment of the public URL, e.g., `text-labelling-app`).
   * To find your **commit\_sign\_id**, query `https://api.github.com/users/<your-app-slug>[bot]` and look for the `id` field.
3. **Configure Secrets**
   Add your GitHub App credentials to `secrets.toml` under the `[github_app]` section:

   ```toml
   [github_app]
   slug = "<your-app-slug>"                # e.g., text-labelling-app
   client_id = "<GitHub App Client ID>"
   commit_sign_id = "<GitHub App numeric ID>"
   private_key_pem = '''
   -----BEGIN RSA PRIVATE KEY-----
   <YOUR PRIVATE KEY>
   -----END RSA PRIVATE KEY-----
   '''
   ```

## 3. Running Locally&#x20;

```bash
pip install -r requirements.txt
streamlit run src/label_app/ui/main.py
```

* Open `http://localhost:8501` in your browser.
* Ensure `secrets.toml` resides in `.streamlit` folder.

## 4. Streamlit Cloud Deployment

1. Fork this repository to your GitHub account.
2. On Streamlit Cloud, select **New app** and connect your fork.
3. In the app settings, add the same secrets under **Advanced settings**:

   * **auth.redirect\_uri**, **auth.cookie\_secret**
   * **auth.auth0.client\_id**, **client\_secret**, **server\_metadata\_url**
   * **github\_app.slug**, **client\_id**, **commit\_sign\_id**, **private\_key\_pem**
4. Deploy and share the live URL with your team.

---

# Tailoring the App

Adapt the core app to your specific labeling tasks by extending the data model and UI. You won’t need to alter any deployment or infrastructure code.

## 1. Data Model

All data classes live in `src/label_app/data/models.py`. Three abstract Pydantic bases define your project structure:

* **ProjectBase**: Project-wide settings (instructions, label schema). Serialized as `project.yaml` at each version root.
* **ItemBase**: Represents one data point (text snippet, image URL, dialog turn, etc.).
* **AnnotationBase**: Annotation schema for each item.

**Steps to Extend:**

1. **Subclass Templates**

   ```python
   class YourProject(ProjectBase): ...
   class YourItem(ItemBase): ...
   class YourAnnotation(AnnotationBase): ...
   ```
2. **Register in Union**
   Update the discriminated union so Pydantic knows your type:

   ```python
   Project = Annotated[
       Union[ChatProject, YourProject],
       Field(discriminator="task_type"),
   ]
   ```
3. **Version Config**

   * Place `project.yaml` at `<project>/<version>/project.yaml` following your `YourProject` schema.
   * Organize source files under `<project>/<version>/source/` as `.jsonl` chunks (100–1000 lines each).

## 2. UI Customization

The renderer for item and annotation views lives in `src/label_app/ui/components/annotation_view.py`. You can hook into this without changing core app logic.

**Steps to Customize:**

1. **Locate Render Method**

   ```python
   @singledispatch
   def render(project: Project, annotation: _AnnotationType) -> _AnnotationType:
       raise TypeError(f"No renderer registered for {type(project).__name__}")
   ```
2. **Override Renderer**

   ```python
   @render.register
   def _your_render(project: YourProject, annotation: YourAnnotation) -> YourAnnotation: ...
   ```
3. **Add Custom Controls**

   * Use `st.selectbox`, `st.slider`, `st.checkbox`, etc., to capture annotations.
   * Leverage Streamlit layout (`st.columns`, `st.expander`) for better UX.
4. **Validate & Iterate**

   * Restart the app locally (`streamlit run ...`).
   * Test with your `.jsonl` dataset and ensure annotations save correctly.

---

# Projects

List your labeling projects in `src/label_app/app_settings.yaml` to make them appear in the UI. You can register multiple projects:

```yaml
projects:
    ner: "https://github.com/your-org/ner-repo/data"
    image: "https://github.com/your-org/img-classifier/dataset"
```

## Project Versions

Each version of a project lives in its own subdirectory. For example:

```
ner-project/
├── v1.0/
│   ├── project.yaml       # Pydantic config for v1.0
│   └── source/
│       └── data_part1.jsonl
│       └── data_part2.jsonl
└── v2.0/
    ├── project.yaml       # Updated config for v2.0
    └── source/
        └── all_data.jsonl
```

* **Immutable Versions:** Once data files and `project.yaml` are committed, treat them as read-only. Create a new version directory for any changes.
* **project.yaml:** Must match your `ProjectBase` schema exactly.
* **Source Tree:** The `source/` directory can contain nested subdirectories; only leaf files should be `.jsonl`. Each line in these JSONL files must represent a serialized Pydantic `YourItem`  model.
* **Chunking:** For performance, keep each `.jsonl` file between 100–1000 lines.

## Annotations Storage

When contributors annotate, their results are saved back into the repository under:

```
<project>/<version>/annotation/<contributor>/source/.../*.jsonl
```

* The `annotation/` tree mirrors the `source/` layout, ensuring your commit history remains clear.
* Multiple contributors can work in parallel without merge conflicts.

---

## Potential Welcomed Contributions

* **New Authentication Backends**

  * Support additional OAuth/OIDC providers (e.g., GitHub OAuth, Google).
  * Implement a plugin architecture for custom authentication modules.

* **Alternative Storage Layers**

  * Add optional back-ends for data and annotation storage (e.g., AWS S3, Google Cloud Storage, SQL/NoSQL databases).
  * Integrate Hugging Face Datasets as a storage and loading option, enabling seamless access to public and private HF repositories.

* **Automated Testing & CI/CD**

  * Include unit and integration tests with pytest covering core components.
  * Provide GitHub Actions workflows for linting, testing, and automated deployment of documentation or Docker images.

* **Interactive Analytics Page**

  * Add a dedicated page within the app for visualizing annotation metrics such as annotator throughput, label distributions, and inter-annotator agreement.
  * Use interactive plotting libraries (Plotly, Recharts, or Streamlit charts) for real-time analytics.

* **Built-in Project Types & Templates**

  * Add additional out-of-the-box project implementations (beyond the current chat labeling).
