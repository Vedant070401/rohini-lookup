# Name Lookup — Gradio Web App

Search your voter/registry CSV by **name** and view full details. Works great for ~300 rows (and more).

## Run locally
```bash
pip install -r requirements.txt
python app.py
```
Open the URL shown (e.g., http://127.0.0.1:7860).

## Use your own CSV
- Put your file at `data.csv` (UTF-8 encoded), or upload via the UI.
- The app auto-detects the **name** column from common variants (`name`, `name_full`, `नाम`, etc.).

## Deploy to the web
- **Hugging Face Spaces** (Python template): push these files to a new Space.
- Or run on your own server (Gunicorn/Uvicorn) and reverse-proxy with Nginx.
