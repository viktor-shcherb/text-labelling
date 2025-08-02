# Text Labelling App

<img width="2043" height="738" alt="banner_text_labelling (1)" src="https://github.com/user-attachments/assets/74556a50-e609-4186-b31e-bd149b1e940a" />

Streamlit-powered collaborative text-labeling tool with Git-backed projects, versioned YAML configs, and pluggable task UIs.

## Running locally

```bash
pip install -r requirements.txt
PYTHONPATH=src streamlit run src/label_app/ui/main.py
```

## `secrets.toml` example

Create `.streamlit/secrets.toml` in the project root with your hashed login keys and OAuth credentials. Set `REDIRECT_URI` to your current deployment.

```toml
AUTH_SECRET = "your-jwt-signing-secret"
REDIRECT_URI = "http://localhost:8501"

[oauth.github]
client_id = "gh-client-id"
client_secret = "gh-client-secret"

[oauth.google]
client_id = "google-client-id"
client_secret = "google-client-secret"
```
