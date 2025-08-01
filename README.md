# text-labelling

Streamlit-powered collaborative text-labeling tool with Git-backed projects, versioned YAML configs, and pluggable task UIs.

## Running locally

```bash
pip install -r requirements.txt
PYTHONPATH=src streamlit run src/label_app/ui/main.py
```

## `secrets.toml` example

Create `.streamlit/secrets.toml` in the project root with your hashed login keys and OAuth credentials:

```toml
AUTH_SECRET = "your-jwt-signing-secret"

[oauth.github]
client_id = "gh-client-id"
client_secret = "gh-client-secret"
redirect_uri = "http://localhost:8501"

[oauth.google]
client_id = "google-client-id"
client_secret = "google-client-secret"
redirect_uri = "http://localhost:8501"
```
