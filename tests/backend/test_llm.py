import httpx
import openai
import pytest

from backend import llm
from backend.config import Settings


def use_settings(monkeypatch: pytest.MonkeyPatch, **values) -> None:
    settings = Settings(_env_file=None, **values)
    monkeypatch.setattr(llm, "get_settings", lambda: settings)


def client_returning(response: httpx.Response) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda request: response))


def test_missing_api_key_raises_actionable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    use_settings(monkeypatch, openai_api_key=None)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is not set"):
        llm.get_llm()


def test_model_and_key_come_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    use_settings(monkeypatch, openai_api_key="sk-env", openai_model="gpt-4o")

    model = llm.get_llm()

    assert model.model_name == "gpt-4o"
    assert model.openai_api_key.get_secret_value() == "sk-env"


def test_explicit_key_and_model_override_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    use_settings(monkeypatch, openai_api_key="sk-env", openai_model="gpt-4o")

    model = llm.get_llm(api_key="sk-typed", model="gpt-4o-mini")

    assert model.model_name == "gpt-4o-mini"
    assert model.openai_api_key.get_secret_value() == "sk-typed"


def test_explicit_key_works_without_any_configured_key(monkeypatch: pytest.MonkeyPatch) -> None:
    use_settings(monkeypatch, openai_api_key=None)
    assert llm.get_llm(api_key="sk-typed").openai_api_key.get_secret_value() == "sk-typed"


def test_verify_api_key_accepts_a_working_key(monkeypatch: pytest.MonkeyPatch) -> None:
    use_settings(monkeypatch, openai_api_key=None)
    ok = httpx.Response(200, json={"object": "list", "data": []})

    llm.verify_api_key("sk-good", http_client=client_returning(ok))


def test_verify_api_key_rejects_a_bad_key(monkeypatch: pytest.MonkeyPatch) -> None:
    use_settings(monkeypatch, openai_api_key=None)
    rejected = httpx.Response(
        401, json={"error": {"message": "Incorrect API key", "code": "invalid_api_key"}}
    )

    with pytest.raises(openai.AuthenticationError):
        llm.verify_api_key("sk-bad", http_client=client_returning(rejected))


def test_verify_api_key_falls_back_to_the_configured_key(monkeypatch: pytest.MonkeyPatch) -> None:
    use_settings(monkeypatch, openai_api_key="sk-env")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers["authorization"]
        return httpx.Response(200, json={"object": "list", "data": []})

    llm.verify_api_key(http_client=httpx.Client(transport=httpx.MockTransport(handler)))

    assert seen["authorization"] == "Bearer sk-env"
