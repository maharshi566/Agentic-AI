import streamlit as st

from backend import service
from backend.service import AgentState

API_KEY = "api_key"
MODEL = "model"
MODEL_CHOICES = ("gpt-4o-mini", "gpt-4o")
KEY_HINT = "Update it on the Settings page."


def session_api_key() -> str | None:
    return st.session_state.get(API_KEY) or None


def selected_model() -> str:
    return st.session_state.get(MODEL) or service.default_model()


def key_source() -> str | None:
    if session_api_key():
        return "entered on the Settings page"
    if service.environment_key_configured():
        return "the OPENAI_API_KEY environment setting"
    return None


def api_key_available() -> bool:
    return key_source() is not None


def ask(question: str) -> AgentState:
    return service.ask(question, api_key=session_api_key(), model=selected_model())
