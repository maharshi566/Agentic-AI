import sqlite3

import httpx
import openai
import pytest
from langchain_openai.chat_models.base import OpenAIRefusalError

from backend.errors import EXPECTED_ERRORS, describe_error

REQUEST = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")


def auth_error() -> openai.AuthenticationError:
    return openai.AuthenticationError(
        "bad key", response=httpx.Response(401, request=REQUEST), body=None
    )


def test_authentication_errors_carry_the_caller_supplied_hint() -> None:
    assert describe_error(auth_error()) == "OpenAI rejected the API key. Check OPENAI_API_KEY."
    assert describe_error(auth_error(), key_hint="Fix it in Settings.") == (
        "OpenAI rejected the API key. Fix it in Settings."
    )


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (openai.APIConnectionError(request=REQUEST), "OpenAI request failed: Connection error."),
        (OpenAIRefusalError("declined"), "OpenAI request failed: declined"),
        (sqlite3.OperationalError("locked"), "Database error: locked"),
        (RuntimeError("no key"), "no key"),
        (FileNotFoundError("missing"), "missing"),
    ],
)
def test_other_expected_errors_are_summarised(error: Exception, message: str) -> None:
    assert describe_error(error) == message
    assert isinstance(error, EXPECTED_ERRORS)


def test_unexpected_errors_are_not_in_the_expected_set() -> None:
    assert not isinstance(ZeroDivisionError(), EXPECTED_ERRORS)
