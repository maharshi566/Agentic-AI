import sqlite3

import openai
from langchain_openai.chat_models.base import OpenAIRefusalError
from pydantic import ValidationError

EXPECTED_ERRORS = (
    RuntimeError,
    FileNotFoundError,
    openai.OpenAIError,
    OpenAIRefusalError,
    ValidationError,
    sqlite3.Error,
)


def describe_error(exc: Exception, key_hint: str = "Check OPENAI_API_KEY.") -> str:
    if isinstance(exc, openai.AuthenticationError):
        return f"OpenAI rejected the API key. {key_hint}"
    if isinstance(exc, openai.OpenAIError | OpenAIRefusalError):
        return f"OpenAI request failed: {exc}"
    if isinstance(exc, ValidationError):
        return "The planner returned a plan that failed validation."
    if isinstance(exc, sqlite3.Error):
        return f"Database error: {exc}"
    return str(exc)
