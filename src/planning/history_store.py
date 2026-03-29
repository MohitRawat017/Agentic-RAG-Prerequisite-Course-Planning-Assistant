from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.planning.constants import DEFAULT_GRADIO_HISTORY_FILE


def load_history(path: Path = DEFAULT_GRADIO_HISTORY_FILE) -> dict:
    if not path.exists():
        return {"sessions": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save_history(history: dict, path: Path = DEFAULT_GRADIO_HISTORY_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")


def create_session(title: str | None = None, path: Path = DEFAULT_GRADIO_HISTORY_FILE) -> tuple[str, dict]:
    history = load_history(path)
    now = _utc_now()
    session_id = str(uuid.uuid4())
    history["sessions"].insert(
        0,
        {
            "session_id": session_id,
            "title": title or "New chat",
            "created_at": now,
            "updated_at": now,
            "messages": [],
        },
    )
    save_history(history, path)
    return session_id, history


def append_message(
    session_id: str,
    role: str,
    content: str,
    artifacts: dict | None = None,
    path: Path = DEFAULT_GRADIO_HISTORY_FILE,
) -> dict:
    history = load_history(path)
    session = _find_or_create_session(history, session_id)
    session["messages"].append(
        {
            "role": role,
            "content": content,
            "artifacts": artifacts,
            "timestamp": _utc_now(),
        }
    )
    session["updated_at"] = _utc_now()
    if role == "user" and len(session["messages"]) == 1:
        session["title"] = _title_from_message(content)
    history["sessions"] = _sort_sessions(history["sessions"])
    save_history(history, path)
    return history


def clear_session(session_id: str, path: Path = DEFAULT_GRADIO_HISTORY_FILE) -> dict:
    history = load_history(path)
    session = _find_or_create_session(history, session_id)
    session["messages"] = []
    session["updated_at"] = _utc_now()
    history["sessions"] = _sort_sessions(history["sessions"])
    save_history(history, path)
    return history


def get_session(history: dict, session_id: str) -> dict | None:
    for session in history.get("sessions", []):
        if session["session_id"] == session_id:
            return session
    return None


def session_choices(history: dict) -> list[tuple[str, str]]:
    return [
        (_session_label(session), session["session_id"])
        for session in _sort_sessions(history.get("sessions", []))
    ]


def chat_messages(session: dict | None) -> list[dict]:
    if session is None:
        return []
    return [{"role": message["role"], "content": message["content"]} for message in session.get("messages", [])]


def latest_artifacts(session: dict | None) -> dict:
    if session is None:
        return {}
    for message in reversed(session.get("messages", [])):
        artifacts = message.get("artifacts")
        if artifacts:
            return artifacts
    return {}


def _find_or_create_session(history: dict, session_id: str) -> dict:
    session = get_session(history, session_id)
    if session is not None:
        return session
    now = _utc_now()
    session = {
        "session_id": session_id,
        "title": "New chat",
        "created_at": now,
        "updated_at": now,
        "messages": [],
    }
    history.setdefault("sessions", []).insert(0, session)
    return session


def _sort_sessions(sessions: list[dict]) -> list[dict]:
    return sorted(sessions, key=lambda item: item.get("updated_at", ""), reverse=True)


def _session_label(session: dict) -> str:
    return f"{session.get('title', 'New chat')} [{session['session_id'][:8]}]"


def _title_from_message(content: str) -> str:
    cleaned = " ".join(content.strip().split())
    return cleaned[:48] + ("..." if len(cleaned) > 48 else "")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
