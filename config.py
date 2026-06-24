import os

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_REALTIME_MODEL = os.environ.get("OPENAI_REALTIME_MODEL", "gpt-realtime-2")
OPENAI_EXTRACTION_MODEL = os.environ.get("OPENAI_EXTRACTION_MODEL", "gpt-4.1-mini")

PUBLIC_BASE_URL = os.environ.get(
    "PUBLIC_BASE_URL",
    "https://web-production-18008.up.railway.app",
).rstrip("/")

PUBLIC_WS_URL = os.environ.get(
    "PUBLIC_WS_URL",
    "wss://web-production-18008.up.railway.app",
).rstrip("/")