"""ArriveAssist: a Streamlit frontend for an n8n settlement-assistant chatbot."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import requests
import streamlit as st


APP_NAME = "ArriveAssist ðŸ"
TAGLINE = "New to Canada? I am here to help."
DEFAULT_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "")
REQUEST_TIMEOUT_SECONDS = 45
RESPONSE_FIELDS = ("output", "text", "response", "message")


st.set_page_config(
    page_title="ArriveAssist",
    page_icon="ðŸ",
    layout="wide",
    initial_sidebar_state="expanded",
)


st.markdown(
    """
    <style>
    :root {
        --arrive-red: #c9363e;
        --arrive-red-dark: #9f222a;
        --arrive-cream: #fffaf3;
        --arrive-ink: #20302b;
        --arrive-green: #287052;
    }
    .stApp {
        background: linear-gradient(145deg, #fffaf3 0%, #ffffff 55%, #f3faf6 100%);
        color: var(--arrive-ink);
    }
    .block-container { max-width: 1100px; padding-top: 2rem; }
    h1, h2, h3 { letter-spacing: -0.025em; }
    .hero { text-align: center; padding: 3.8rem 1rem 2.2rem; }
    .hero h1 { font-size: clamp(2.8rem, 7vw, 5rem); margin: 0; color: var(--arrive-ink); }
    .hero p { font-size: 1.35rem; color: #5b6863; margin-top: .65rem; }
    .info-card {
        height: 100%; padding: 1.55rem 1.7rem; border-radius: 18px;
        border: 1px solid rgba(32, 48, 43, .10); background: rgba(255,255,255,.88);
        box-shadow: 0 12px 35px rgba(32,48,43,.07);
    }
    .info-card h3 { margin-top: 0; }
    .can-card { border-top: 5px solid var(--arrive-green); }
    .cant-card { border-top: 5px solid var(--arrive-red); }
    .info-card li { margin-bottom: .55rem; line-height: 1.45; }
    .safety-note {
        margin: 1.35rem 0; padding: 1rem 1.2rem; border-radius: 12px;
        background: #fff4d9; border-left: 4px solid #d99b22; color: #604815;
    }
    div.stButton > button[kind="primary"] {
        background: var(--arrive-red); border-color: var(--arrive-red);
        border-radius: 999px; font-weight: 700; min-height: 3rem;
    }
    div.stButton > button[kind="primary"]:hover {
        background: var(--arrive-red-dark); border-color: var(--arrive-red-dark);
    }
    [data-testid="stSidebar"] { border-right: 1px solid rgba(32,48,43,.10); }
    .chat-heading { padding-bottom: .8rem; border-bottom: 1px solid rgba(32,48,43,.10); }
    .chat-heading h1 { margin-bottom: .15rem; }
    .chat-heading p { color: #65716d; margin: 0; }
    .empty-chat {
        text-align: center; margin: 5rem auto 2rem; max-width: 560px; padding: 2rem;
        border: 1px dashed rgba(32,48,43,.25); border-radius: 20px; color: #60706a;
    }
    @media (max-width: 700px) {
        .hero { padding-top: 2rem; }
        .block-container { padding-top: 1rem; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_thread() -> dict[str, Any]:
    now = utc_now()
    return {
        "id": str(uuid4()),
        "label": "New conversation",
        "messages": [],
        "session_id": None,
        "created_at": now,
        "updated_at": now,
    }


def initialize_state() -> None:
    st.session_state.setdefault("screen", "landing")
    st.session_state.setdefault("threads", [])
    st.session_state.setdefault("active_thread_id", None)
    # Keep the saved setting separate from its widget key. Widget state may be
    # removed by Streamlit when a conditionally rendered widget disappears.
    legacy_url = st.session_state.get("webhook_url", DEFAULT_WEBHOOK_URL)
    st.session_state.setdefault("configured_webhook_url", legacy_url)
    st.session_state.setdefault("webhook_url_input", legacy_url)


def active_thread() -> dict[str, Any] | None:
    active_id = st.session_state.active_thread_id
    return next(
        (thread for thread in st.session_state.threads if thread["id"] == active_id),
        None,
    )


def create_and_activate_thread() -> dict[str, Any]:
    thread = new_thread()
    st.session_state.threads.append(thread)
    st.session_state.active_thread_id = thread["id"]
    return thread


def ensure_active_thread() -> dict[str, Any]:
    return active_thread() or create_and_activate_thread()


def make_thread_label(message: str, max_length: int = 34) -> str:
    compact = " ".join(message.split())
    return compact if len(compact) <= max_length else f"{compact[: max_length - 1].rstrip()}â€¦"


def find_response_value(payload: Any) -> tuple[str | None, str | None]:
    """Extract the first supported answer field and an optional n8n session ID."""
    if isinstance(payload, list) and payload:
        payload = payload[0]

    if not isinstance(payload, dict):
        return (str(payload) if payload not in (None, "") else None), None

    session_id = payload.get("sessionId") or payload.get("session_id")
    for field in RESPONSE_FIELDS:
        value = payload.get(field)
        if value not in (None, ""):
            if isinstance(value, (dict, list)):
                return str(value), str(session_id) if session_id else None
            return str(value), str(session_id) if session_id else None
    return None, str(session_id) if session_id else None


def http_error_message(exc: requests.exceptions.HTTPError) -> str:
    """Return useful n8n error details without exposing the configured URL."""
    response = exc.response
    if response is None:
        return "The webhook returned an HTTP error without a response."

    detail = " ".join(response.text.strip().split())[:500]
    message = f"The webhook returned HTTP {response.status_code}."
    if detail:
        message += f" n8n said: {detail}"
    if response.status_code == 404:
        message += (
            " If this is an n8n test URL, click â€˜Listen for test eventâ€™ in n8n first; "
            "otherwise activate the workflow and use its production URL."
        )
    return message


def ask_webhook(message: str, thread: dict[str, Any]) -> tuple[str, str | None]:
    url = st.session_state.configured_webhook_url.strip()
    if not url:
        raise ValueError(
            "The n8n webhook URL is not configured. Add it under Webhook settings in the sidebar."
        )

    body = {"chatInput": message}
    if thread.get("session_id"):
        body["sessionId"] = thread["session_id"]

    response = requests.post(url, json=body, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    try:
        payload = response.json()
    except requests.exceptions.JSONDecodeError as exc:
        raise ValueError("The webhook returned a response that was not valid JSON.") from exc

    answer, session_id = find_response_value(payload)
    if not answer:
        raise ValueError(
            "The webhook response did not contain output, text, response, or message."
        )
    return answer, session_id


def show_landing_page() -> None:
    st.markdown(
        f'<section class="hero"><h1>{APP_NAME}</h1><p>{TAGLINE}</p></section>',
        unsafe_allow_html=True,
    )
    st.markdown("## How I can help")
    can_col, cant_col = st.columns(2, gap="large")

    with can_col:
        st.markdown(
            """
            <div class="info-card can-card">
              <h3>âœ… What I can help with</h3>
              <ul>
                <li><strong>Canadian citizenship</strong> â€” eligibility and the application process</li>
                <li><strong>OHIP</strong> (Ontario health coverage) â€” eligibility, required documents, and how to apply</li>
                <li><strong>SIN</strong> (Social Insurance Number) â€” applications, required documents, and fraud protection</li>
                <li>Questions that touch more than one of these topics at once</li>
              </ul>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with cant_col:
        st.markdown(
            """
            <div class="info-card cant-card">
              <h3>ðŸš« What I can't help with</h3>
              <ul>
                <li>Driver's licence exchanges</li>
                <li>Opening a bank account</li>
                <li>Student visas or study permits</li>
                <li>Filing income taxes</li>
                <li>Job searching or employment help</li>
                <li>Work visa travel or re-entry rules</li>
                <li>Permanent residency applications</li>
                <li>Health coverage outside Ontario</li>
              </ul>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(
        """
        <div class="safety-note"><strong>Please note:</strong> Always confirm important
        details on the official government website before acting on them.</div>
        """,
        unsafe_allow_html=True,
    )
    _, button_col, _ = st.columns([1, 1.2, 1])
    with button_col:
        if st.button("Let's Chat", type="primary", width="stretch"):
            ensure_active_thread()
            st.session_state.screen = "chat"
            st.rerun()


def show_chat_sidebar() -> None:
    with st.sidebar:
        st.markdown(f"## {APP_NAME}")
        if st.button("â† Back to home", width="stretch"):
            st.session_state.screen = "landing"
            st.rerun()

        if st.button("âž• New Chat", type="primary", width="stretch"):
            create_and_activate_thread()
            st.rerun()

        st.markdown("### Chat history")
        threads = sorted(
            st.session_state.threads,
            key=lambda item: item.get("updated_at", item["created_at"]),
            reverse=True,
        )
        for thread in threads:
            is_active = thread["id"] == st.session_state.active_thread_id
            label = f"â— {thread['label']}" if is_active else thread["label"]
            if st.button(label, key=f"thread_{thread['id']}", width="stretch"):
                st.session_state.active_thread_id = thread["id"]
                st.rerun()

        st.divider()
        configured = bool(st.session_state.configured_webhook_url.strip())
        with st.expander("Webhook settings", expanded=not configured):
            with st.form("webhook_settings_form"):
                st.text_input(
                    "n8n webhook URL",
                    key="webhook_url_input",
                    placeholder="https://your-n8n-host/webhook/...",
                    type="password",
                    persist_state="session",
                    help="You can also set the N8N_WEBHOOK_URL environment variable.",
                )
                save_webhook = st.form_submit_button("Save webhook", width="stretch")

            if save_webhook:
                candidate = st.session_state.webhook_url_input.strip()
                if candidate and not candidate.lower().startswith(("http://", "https://")):
                    st.error("Enter a complete webhook URL beginning with http:// or https://.")
                elif not candidate:
                    st.error("Enter a webhook URL before saving.")
                else:
                    st.session_state.configured_webhook_url = candidate
                    st.success("Webhook saved for this session.")

            if st.session_state.configured_webhook_url.strip():
                st.success("Webhook is configured.", icon="âœ…")
            else:
                st.warning("Webhook is not configured.", icon="âš ï¸")
            st.caption("The URL is kept only in this browser session unless supplied as an environment variable.")


def show_chat_page() -> None:
    thread = ensure_active_thread()
    show_chat_sidebar()

    st.markdown(
        f'<div class="chat-heading"><h1>{APP_NAME}</h1><p>{TAGLINE}</p></div>',
        unsafe_allow_html=True,
    )

    if not thread["messages"]:
        st.markdown(
            """
            <div class="empty-chat">
              <h3>How can I help you settle in?</h3>
              <p>Ask me about Canadian citizenship, OHIP, or your Social Insurance Number.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    for message in thread["messages"]:
        avatar = "ðŸ" if message["role"] == "assistant" else "ðŸ‘¤"
        with st.chat_message(message["role"], avatar=avatar):
            st.markdown(message["content"])

    prompt = st.chat_input(
        "Ask about citizenship, OHIP, or SINâ€¦",
        submit_mode="disable",
    )
    if not prompt:
        return

    user_message = {"role": "user", "content": prompt}
    thread["messages"].append(user_message)
    if len(thread["messages"]) == 1:
        thread["label"] = make_thread_label(prompt)
    thread["updated_at"] = utc_now()

    with st.chat_message("user", avatar="ðŸ‘¤"):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar="ðŸ"):
        with st.spinner("ArriveAssist is finding an answerâ€¦"):
            try:
                answer, session_id = ask_webhook(prompt, thread)
                if session_id:
                    thread["session_id"] = session_id
            except requests.exceptions.Timeout:
                answer = (
                    f"The webhook did not respond within {REQUEST_TIMEOUT_SECONDS} seconds. "
                    "Check that the n8n workflow is active and try again."
                )
            except requests.exceptions.HTTPError as exc:
                answer = http_error_message(exc)
            except requests.exceptions.SSLError:
                answer = (
                    "The webhook's HTTPS certificate could not be verified. "
                    "Check the n8n domain and its TLS certificate."
                )
            except requests.exceptions.ConnectionError:
                answer = (
                    "A connection to the webhook could not be established. Check that the "
                    "domain is reachable, n8n is running, and the URL uses the correct port."
                )
            except requests.exceptions.RequestException as exc:
                answer = f"The webhook request failed ({type(exc).__name__}). Please try again."
            except ValueError as exc:
                answer = str(exc)
            except Exception:
                answer = "Something unexpected went wrong while contacting the assistant. Please try again."
            st.markdown(answer)

    thread["messages"].append({"role": "assistant", "content": answer})
    thread["updated_at"] = utc_now()


initialize_state()
if st.session_state.screen == "chat":
    show_chat_page()
else:
    show_landing_page()

