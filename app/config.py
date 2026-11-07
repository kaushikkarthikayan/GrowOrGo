"""Settings loaded from the .env file. Every value has a safe default."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
SESSIONS_DIR = DATA_DIR / "sessions"
UPLOADS_DIR = DATA_DIR / "uploads"
for _d in (SESSIONS_DIR, UPLOADS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# Windows default install path for Tesseract OCR; leave blank on Mac/Linux.
TESSERACT_CMD = os.getenv("TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

MAX_FILE_MB = int(os.getenv("MAX_FILE_MB", "10"))
