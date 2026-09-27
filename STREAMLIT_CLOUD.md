# Streamlit Community Cloud deployment

1. Open https://share.streamlit.io/ and sign in with GitHub.
2. Select repository `mg1755632-boop/myanmar-recap-video`.
3. Select branch `main` and main file `app.py`.
4. Deploy the app.
5. Open **Settings → Secrets** and add:

```toml
GEMINI_API_KEY = "your-gemini-api-key"
GEMINI_MODEL = "gemini-3.8-flash"
```

The app uses `packages.txt` to install FFmpeg. Keep the Gemini key in Secrets; do not put it in GitHub or `.env.example`.
