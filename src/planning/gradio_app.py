from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import gradio as gr

from src.graph.graph import build_planning_graph
from src.graph.state import GraphState
from src.planning.constants import (
    DEFAULT_COURSE_FILE,
    DEFAULT_GRADIO_HISTORY_FILE,
    DEFAULT_POLICY_FILE,
    DEFAULT_PROGRAM_FILE,
)
from src.planning.history_store import (
    append_message,
    chat_messages,
    clear_session,
    create_session,
    get_session,
    latest_artifacts,
    load_history,
    session_choices,
)


@lru_cache(maxsize=1)
def _graph():
    return build_planning_graph()


def build_app() -> gr.Blocks:
    history = load_history(DEFAULT_GRADIO_HISTORY_FILE)
    if not history.get("sessions"):
        session_id, history = create_session(path=DEFAULT_GRADIO_HISTORY_FILE)
    else:
        session_id = history["sessions"][0]["session_id"]

    with gr.Blocks(title="Course Planning Assistant Demo") as demo:
        gr.Markdown("## Course Planning Assistant")
        gr.Markdown("Chat with the LangGraph-backed planner and inspect the latest grounded plan artifacts.")

        history_state = gr.State(history)
        session_state = gr.State(session_id)

        with gr.Row():
            session_dropdown = gr.Dropdown(
                choices=session_choices(history),
                value=session_id,
                label="Conversation",
                interactive=True,
            )
            new_chat_button = gr.Button("New Chat", variant="primary")
            clear_chat_button = gr.Button("Clear Current Chat")

        chatbot = gr.Chatbot(label="Conversation", height=520)
        message_box = gr.Textbox(label="Your message", placeholder="Ask about eligibility or planning...", lines=3)
        send_button = gr.Button("Send", variant="primary")

        with gr.Accordion("Debug Panel", open=False):
            plan_json = gr.Code(label="Latest Plan JSON", language="json")
            verification_json = gr.Code(label="Verification", language="json")
            citations_json = gr.Code(label="Retrieved Chunk Metadata", language="json")

        demo.load(
            _load_session_view,
            inputs=[history_state, session_state],
            outputs=[chatbot, plan_json, verification_json, citations_json, session_dropdown],
        )

        send_button.click(
            _handle_message,
            inputs=[message_box, history_state, session_state],
            outputs=[message_box, history_state, session_state, chatbot, plan_json, verification_json, citations_json, session_dropdown],
        )
        message_box.submit(
            _handle_message,
            inputs=[message_box, history_state, session_state],
            outputs=[message_box, history_state, session_state, chatbot, plan_json, verification_json, citations_json, session_dropdown],
        )
        new_chat_button.click(
            _new_chat,
            inputs=[history_state],
            outputs=[history_state, session_state, chatbot, plan_json, verification_json, citations_json, session_dropdown],
        )
        clear_chat_button.click(
            _clear_chat,
            inputs=[history_state, session_state],
            outputs=[history_state, chatbot, plan_json, verification_json, citations_json, session_dropdown],
        )
        session_dropdown.change(
            _switch_session,
            inputs=[history_state, session_dropdown],
            outputs=[session_state, chatbot, plan_json, verification_json, citations_json, session_dropdown],
        )

    return demo


def launch() -> None:
    build_app().launch()


def _handle_message(message: str, history: dict, session_id: str):
    if not message.strip():
        session = get_session(history, session_id)
        artifacts = latest_artifacts(session)
        return (
            "",
            history,
            session_id,
            chat_messages(session),
            _pretty_json(artifacts.get("plan")),
            _pretty_json(artifacts.get("verification")),
            _pretty_json(artifacts.get("retrieved_chunks")),
            gr.update(choices=session_choices(history), value=session_id),
        )

    history = append_message(session_id, "user", message.strip(), path=DEFAULT_GRADIO_HISTORY_FILE)
    result = _run_graph(message.strip())
    artifacts = {
        "plan": result["plan"],
        "verification": result.get("verification", {}),
        "retrieved_chunks": _chunk_metadata(result.get("retrieved_chunks", [])),
    }
    history = append_message(
        session_id,
        "assistant",
        result["response_text"],
        artifacts=artifacts,
        path=DEFAULT_GRADIO_HISTORY_FILE,
    )
    session = get_session(history, session_id)
    return (
        "",
        history,
        session_id,
        chat_messages(session),
        _pretty_json(artifacts["plan"]),
        _pretty_json(artifacts["verification"]),
        _pretty_json(artifacts["retrieved_chunks"]),
        gr.update(choices=session_choices(history), value=session_id),
    )


def _new_chat(history: dict):
    session_id, history = create_session(path=DEFAULT_GRADIO_HISTORY_FILE)
    session = get_session(history, session_id)
    return (
        history,
        session_id,
        chat_messages(session),
        _pretty_json({}),
        _pretty_json({}),
        _pretty_json([]),
        gr.update(choices=session_choices(history), value=session_id),
    )


def _clear_chat(history: dict, session_id: str):
    history = clear_session(session_id, path=DEFAULT_GRADIO_HISTORY_FILE)
    session = get_session(history, session_id)
    return (
        history,
        chat_messages(session),
        _pretty_json({}),
        _pretty_json({}),
        _pretty_json([]),
        gr.update(choices=session_choices(history), value=session_id),
    )


def _switch_session(history: dict, session_id: str):
    session = get_session(history, session_id)
    artifacts = latest_artifacts(session)
    return (
        session_id,
        chat_messages(session),
        _pretty_json(artifacts.get("plan")),
        _pretty_json(artifacts.get("verification")),
        _pretty_json(artifacts.get("retrieved_chunks")),
        gr.update(choices=session_choices(history), value=session_id),
    )


def _load_session_view(history: dict, session_id: str):
    session = get_session(history, session_id)
    artifacts = latest_artifacts(session)
    return (
        chat_messages(session),
        _pretty_json(artifacts.get("plan")),
        _pretty_json(artifacts.get("verification")),
        _pretty_json(artifacts.get("retrieved_chunks")),
        gr.update(choices=session_choices(history), value=session_id),
    )


def _run_graph(query: str) -> dict:
    return _graph().invoke(
        GraphState(
            query=query,
            courses_path=DEFAULT_COURSE_FILE,
            program_path=DEFAULT_PROGRAM_FILE,
            policies_path=DEFAULT_POLICY_FILE,
            output_path=None,
            rebuild_index=False,
            print_explanation=True,
        )
    )


def _chunk_metadata(retrieved_chunks: list[dict]) -> list[dict]:
    return [dict(item.get("metadata", {})) for item in retrieved_chunks]


def _pretty_json(value) -> str:
    if value is None:
        value = {}
    return json.dumps(value, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    launch()
