# OneFile · 一人档 (Streamlit MVP)

Single-file entrypoint with modular internals for creating and maintaining structured OPC project archives.

## Entrypoint
- `app.py`

## Local run
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Secrets
Set keys in **Streamlit Cloud**: App → Settings → Secrets.

Required (any one works):
- `DASHSCOPE_API_KEY`
- `QWEN_API_KEY`
- `OPENAI_API_KEY`

Optional:
- `ONEFILE_BASE_URL` (e.g. `https://your-app-name.streamlit.app`) to generate absolute share links.

Local template:
- `.streamlit/secrets.toml.example`

## Deploy to Streamlit Community Cloud
1. Push this repo to GitHub.
2. In Streamlit Community Cloud, create app from this repo.
3. Set **Main file path** to `app.py`.
4. Add secrets in app settings.
5. Deploy and share the generated `*.streamlit.app` URL.

## Persistence note
Project data is stored in `data/projects.json` (local file storage).
On Streamlit Community Cloud, filesystem storage can be ephemeral across restarts/redeploys.
This means data may reset unless you later connect an external persistent database.
