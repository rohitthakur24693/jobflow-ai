import os
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent
UPLOADS_DIR = BASE_DIR / "uploads"
DRAFTS_DIR = BASE_DIR / "drafts"
CREDENTIALS_DIR = BASE_DIR / "credentials"
TOKENS_DIR = BASE_DIR / "tokens"
SAMPLE_DATA_DIR = BASE_DIR / "sample_data"
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = BASE_DIR / "data"

for folder in [UPLOADS_DIR, DRAFTS_DIR, CREDENTIALS_DIR, TOKENS_DIR, SAMPLE_DATA_DIR, STATIC_DIR, DATA_DIR]:
    folder.mkdir(parents=True, exist_ok=True)

TRACKER_FILE = DATA_DIR / "tracker.json"
SCHEDULER_FILE = DATA_DIR / "scheduler_config.json"

# Google / Gmail Settings
GMAIL_CREDENTIALS_FILE = CREDENTIALS_DIR / "client_secret.json"
GMAIL_TOKEN_FILE = TOKENS_DIR / "gmail_token.json"
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile"
]

# AI Engine / Gemini
# Checks GEMINI_API_KEY from environment or user settings file
SETTINGS_FILE = BASE_DIR / "settings.json"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"

def get_gemini_api_key() -> str:
    # 1. Environment variable
    env_key = os.environ.get("GEMINI_API_KEY", "")
    if env_key:
        return env_key.strip()
    # 2. Settings JSON file
    if SETTINGS_FILE.exists():
        try:
            import json
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("gemini_api_key", "").strip()
        except Exception:
            pass
    return ""

def set_gemini_api_key(key: str):
    import json
    data = {}
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass
    data["gemini_api_key"] = key.strip()
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

SERVER_HOST = os.environ.get("HOST", "0.0.0.0")
SERVER_PORT = int(os.environ.get("PORT", 8000))

# Authentication & Security
AUTH_SECRET_KEY = os.environ.get("AUTH_SECRET_KEY", "jobflow-secure-jwt-key-2026-isolated-tenant")
AUTH_ALGORITHM = "HS256"
AUTH_TOKEN_EXPIRE_DAYS = 7
