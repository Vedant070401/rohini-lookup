# server.py — FastAPI backend for Rohini lookup with password gate

import os, re, unicodedata, hashlib, hmac
from typing import List, Dict, Any

import pandas as pd
from fastapi import FastAPI, Query, HTTPException, Request, Depends, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

# ------------ CONFIG ------------

DATA_PATH = os.environ.get("DATA_PATH", "data.csv")
FORCE_NAME_COL = os.environ.get("NAME_COL")  # optional override

# 🔐 password protection (change these!)
APP_PASSWORD = os.environ.get("APP_PASSWORD", "change_me_123")  # TODO: set real password
AUTH_COOKIE_NAME = "rohini_auth"
AUTH_SALT = os.environ.get("AUTH_SALT", "rohini-secret-salt")   # can change in prod

PREFERRED_NAME_COLUMNS = [
    "full name", "fullname",
    "full_name", "name_full", "name",
    "नाम", "नाव", "नाम_हिंदी", "Name", "Full Name", "Full_Name"
]

DISPLAY_COLS_PREFERENCE = [
    # you can align these to your CSV columns if you want display order
    "Serial No.",
    "Voter ID",
    "Full Name (Marathi)",
    "Full Name (English)",
    "Relative's Name (Marathi)",
    "Relative's Name (English)",
    "Relationship",
    "Age",
    "Gender",
    "House No.",
    "Electoral Roll Ref",
]

# ------------ APP SETUP ------------

app = FastAPI(title="Rohini Lookup")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

# ------------ CSV / SEARCH HELPERS ------------

def _read_csv_with_fallbacks(path: str) -> pd.DataFrame:
    encs = ["utf-8", "utf-8-sig", "utf-16", "utf-16le", "utf-16be", "cp1252", "latin1"]
    last = None
    for enc in encs:
        try:
            return pd.read_csv(path, dtype=str, encoding=enc, na_filter=False)
        except Exception as e:
            last = e
    raise last

def strip_marks(text: str) -> str:
    if not isinstance(text, str):
        text = "" if text is None else str(text)
    norm = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in norm if unicodedata.category(ch) != "Mn").lower().strip()

def _is_probably_epic(series: pd.Series) -> bool:
    s = series.astype(str)
    pat = re.compile(r"^[A-Z]{2,4}[0-9]{5,8}$")
    match_rate = s.str.fullmatch(pat).mean()

    def digit_ratio(x: str) -> float:
        x = (x or "").strip()
        return 0.0 if not x else sum(ch.isdigit() for ch in x) / max(1, len(x))

    sample = s.sample(min(len(s), 300), random_state=0)
    digit_rate = sample.apply(digit_ratio).mean()
    return (match_rate >= 0.5) or (digit_rate >= 0.5)

def _alpha_ratio(x: str) -> float:
    x = "" if x is None else str(x)
    n = len(x)
    return 0.0 if n == 0 else sum(ch.isalpha() for ch in x) / n

def pick_name_column(df: pd.DataFrame) -> str:
    # honor explicit env override if present
    if FORCE_NAME_COL and FORCE_NAME_COL in df.columns:
        return FORCE_NAME_COL

    lower_map = {c.lower(): c for c in df.columns}
    for cand in PREFERRED_NAME_COLUMNS:
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]

    # fallback heuristic: texty & not EPIC-like
    best, best_score = None, -1.0
    for c in df.columns:
        ser = df[c].astype(str)
        if _is_probably_epic(ser):
            continue
        score = ser.sample(min(len(ser), 300), random_state=1).apply(_alpha_ratio).mean()
        if score > best_score:
            best, best_score = c, score
    return best or df.columns[0]

def build_display_cols(df: pd.DataFrame, name_col: str) -> List[str]:
    cols: List[str] = []
    # prefer name column first
    if name_col not in cols:
        cols.append(name_col)
    # then follow your preference list
    for c in DISPLAY_COLS_PREFERENCE:
        if c in df.columns and c not in cols:
            cols.append(c)
    # then everything else (except internal columns)
    for c in df.columns:
        if c not in cols and not str(c).startswith("_"):
            cols.append(c)
    return cols

# -------- Load data on startup --------
DF: pd.DataFrame = None
NAME_COL: str = ""
DISPLAY_COLS: List[str] = []

def load_dataset():
    global DF, NAME_COL, DISPLAY_COLS
    if not os.path.exists(DATA_PATH):
        raise FileNotFoundError(f"Backend data.csv not found at {DATA_PATH}")

    df = _read_csv_with_fallbacks(DATA_PATH)

    # ---- choose name column explicitly for your schema ----
    if "Full Name (English)" in df.columns:
        name_col = "Full Name (English)"
    elif "Full Name (Marathi)" in df.columns:
        name_col = "Full Name (Marathi)"
    elif "Full Name" in df.columns:
        name_col = "Full Name"
    else:
        name_col = pick_name_column(df)

    # normalize values for search
    df[name_col] = df[name_col].astype(str)
    df["_name_key"] = df[name_col].str.strip().str.lower()
    df["_name_norm"] = df[name_col].map(strip_marks)

    DF = df
    NAME_COL = name_col
    DISPLAY_COLS = build_display_cols(DF, NAME_COL)
    print(f"[INFO] Loaded {len(DF)} rows; name column = {NAME_COL}")

# ------------ AUTH HELPERS ------------

def _make_token() -> str:
    """Create a simple signed token based on password + salt."""
    msg = APP_PASSWORD.encode("utf-8")
    key = AUTH_SALT.encode("utf-8")
    return hmac.new(key, msg, hashlib.sha256).hexdigest()

def _is_authenticated(request: Request) -> bool:
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if not token:
        return False
    return token == _make_token()

def require_auth(request: Request):
    """Dependency for API routes."""
    if not _is_authenticated(request):
        raise HTTPException(status_code=401, detail="Not authenticated")

# ------------ APP LIFECYCLE ------------

@app.on_event("startup")
def _on_startup():
    load_dataset()

# ------------ LOGIN PAGES ------------

LOGIN_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>Rohini Lookup • Login</title>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <style>
    :root{
      --saffron-1:#ff6a00;
      --saffron-2:#ff8f1b;
      --bg:#fff4e6;
      --card:#ffffff;
      --border:#ffd0a3;
    }
    *{box-sizing:border-box;}
    body{
      margin:0; min-height:100vh;
      display:flex; align-items:center; justify-content:center;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background:linear-gradient(135deg,var(--saffron-1),var(--saffron-2));
    }
    .card{
      width:100%; max-width:380px;
      background:var(--card);
      border-radius:18px;
      padding:24px 22px 22px;
      box-shadow:0 16px 40px rgba(0,0,0,0.18);
      border:1px solid var(--border);
    }
    h1{
      margin:0 0 8px;
      font-size:22px; font-weight:800;
      color:#7a3200;
    }
    p{
      margin:0 0 18px;
      font-size:13px;
      color:#5b6778;
    }
    label{
      display:block;
      font-size:12px;
      margin-bottom:6px;
      color:#7a3200;
      font-weight:600;
    }
    input[type=password]{
      width:100%;
      padding:10px 12px;
      border-radius:12px;
      border:1.5px solid var(--border);
      font-size:14px;
      outline:none;
    }
    input[type=password]:focus{
      border-color:#ff9b3f;
      box-shadow:0 0 0 2px rgba(255,155,63,0.3);
    }
    button{
      width:100%; margin-top:14px;
      border-radius:999px;
      border:none;
      padding:10px 14px;
      background:linear-gradient(135deg,#ff7a1a,#ffb347);
      color:#fff;
      font-size:14px; font-weight:700;
      cursor:pointer;
      box-shadow:0 10px 24px rgba(0,0,0,0.18);
    }
    .error{
      margin-top:10px;
      font-size:12px;
      color:#b00020;
    }
    .tag{
      margin-top:12px;
      font-size:11px;
      color:#9a5200;
      opacity:.8;
      text-align:center;
    }
  </style>
</head>
<body>
  <form class="card" method="post" action="/login">
    <h1>Rohini Lookup</h1>
    <p>Enter the access password to view the voter lookup dashboard.</p>
    <label for="password">Access Password</label>
    <input id="password" name="password" type="password" required autocomplete="current-password"/>
    <button type="submit">Enter</button>
    {error_block}
    <div class="tag">Authorized users only</div>
  </form>
</body>
</html>
"""

@app.get("/login", include_in_schema=False)
async def login_page(request: Request):
    # already logged in? go straight to app
    if _is_authenticated(request):
        return RedirectResponse(url="/", status_code=302)
    html = LOGIN_HTML.replace("{error_block}", "")
    return HTMLResponse(html)

@app.post("/login", include_in_schema=False)
async def login_post(password: str = Form(...)):
    if password != APP_PASSWORD:
        error_html = '<div class="error">Incorrect password. Try again.</div>'
        html = LOGIN_HTML.replace("{error_block}", error_html)
        return HTMLResponse(html, status_code=401)

    # success → set auth cookie and redirect
    token = _make_token()
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        AUTH_COOKIE_NAME,
        token,
        httponly=True,
        max_age=7 * 24 * 60 * 60,  # 7 days
        secure=False,              # set True if you use HTTPS
        samesite="lax",
    )
    return response

@app.get("/logout", include_in_schema=False)
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(AUTH_COOKIE_NAME)
    return response

# ------------ ROOT UI (PROTECTED) ------------

@app.get("/", include_in_schema=False)
async def index(request: Request):
    if not _is_authenticated(request):
        return RedirectResponse(url="/login", status_code=302)
    return FileResponse("static/index.html")

# ------------ APIs (ALL PROTECTED) ------------

@app.get("/api/meta")
async def meta(request: Request, _: None = Depends(require_auth)):
    return {
        "name_col": NAME_COL,
        "columns": [c for c in DF.columns if not c.startswith("_")],
        "total_rows": len(DF),
    }

@app.get("/api/suggest")
async def suggest(
    request: Request,
    q: str = "",
    limit: int = 100,
    _: None = Depends(require_auth),
):
    query = strip_marks(q or "")
    if not query:
        names = DF[NAME_COL].astype(str).str.strip()
        names = names[names.ne("")].drop_duplicates().head(limit).tolist()
        return {"options": names}
    mask = DF["_name_norm"].str.contains(query, na=False)
    names = (
        DF.loc[mask, NAME_COL]
        .astype(str)
        .str.strip()
        .drop_duplicates()
        .head(limit)
        .tolist()
    )
    return {"options": names}

@app.get("/api/lookup")
async def lookup(
    request: Request,
    name: str,
    _: None = Depends(require_auth),
):
    nm = (name or "").strip()
    if not nm:
        raise HTTPException(400, "Missing name")
    key = nm.lower()
    exact = DF[DF["_name_key"] == key]
    if exact.empty:
        exact = DF[
            DF[NAME_COL]
            .astype(str)
            .str.strip()
            .str.lower()
            .str.contains(key, na=False)
        ]
    rows = [
        {k: v for k, v in row.items() if not str(k).startswith("_")}
        for _, row in exact.iterrows()
    ]
    return {"count": len(rows), "rows": rows}

@app.post("/api/reload")
async def reload_ds(request: Request, _: None = Depends(require_auth)):
    load_dataset()
    return {"ok": True, "name_col": NAME_COL, "total_rows": len(DF)}
