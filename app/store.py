"""Very simple session store: one JSON file per user session in data/sessions/.
Good enough for a hackathon demo; can be swapped for Supabase later."""
import json
import uuid
from datetime import datetime, timezone

from .config import SESSIONS_DIR


def _path(session_id: str):
    # Only allow plain hex ids, so nobody can read files outside the folder.
    if not session_id or not all(c in "0123456789abcdef" for c in session_id):
        raise KeyError("Invalid session id")
    return SESSIONS_DIR / f"{session_id}.json"


def create_session() -> dict:
    session = {
        "session_id": uuid.uuid4().hex,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "sources": [],
    }
    save_session(session)
    return session


def get_session(session_id: str) -> dict:
    path = _path(session_id)
    if not path.exists():
        raise KeyError("Session not found")
    return json.loads(path.read_text(encoding="utf-8"))


def save_session(session: dict) -> None:
    _path(session["session_id"]).write_text(
        json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def delete_session(session_id: str) -> bool:
    path = _path(session_id)
    if path.exists():
        path.unlink()
        return True
    return False
