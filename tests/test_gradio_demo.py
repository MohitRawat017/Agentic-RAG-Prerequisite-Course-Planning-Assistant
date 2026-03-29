from pathlib import Path

from src.planning.gradio_app import _run_graph
from src.planning.history_store import (
    append_message,
    chat_messages,
    clear_session,
    create_session,
    get_session,
    latest_artifacts,
    load_history,
)


def test_history_store_persists_messages(tmp_path: Path) -> None:
    history_path = tmp_path / "history.json"
    session_id, _ = create_session(path=history_path)
    append_message(session_id, "user", "Can I take COMP2145?", path=history_path)
    append_message(
        session_id,
        "assistant",
        "Answer / Plan:\nYou should take COMP1140.",
        artifacts={"plan": {"recommended_courses": ["COMP1140"]}},
        path=history_path,
    )

    history = load_history(history_path)
    session = get_session(history, session_id)

    assert session is not None
    assert len(session["messages"]) == 2
    assert chat_messages(session)[0]["content"] == "Can I take COMP2145?"
    assert latest_artifacts(session)["plan"]["recommended_courses"] == ["COMP1140"]


def test_clear_session_keeps_session_and_removes_messages(tmp_path: Path) -> None:
    history_path = tmp_path / "history.json"
    session_id, _ = create_session(path=history_path)
    append_message(session_id, "user", "Hello", path=history_path)

    history = clear_session(session_id, path=history_path)
    session = get_session(history, session_id)

    assert session is not None
    assert session["messages"] == []


def test_gradio_backend_matches_expected_semester_plan_shape() -> None:
    result = _run_graph(
        "I have completed COMP1120 and COMP1130. I want to plan my next semester with a maximum of 8 credits."
    )

    assert result["plan"]["recommended_courses"] == ["COMP1140", "COMP1200"]
    assert result["response_text"].startswith("Answer / Plan:")


def test_gradio_backend_greeting_returns_friendly_response() -> None:
    result = _run_graph("hii")

    assert result["plan"]["recommended_courses"] == []
    assert "Hello! How can I help you with your course planning today?" in result["response_text"]
    assert "\nCitations:\nNone" in result["response_text"]
