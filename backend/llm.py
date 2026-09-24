import httpx
import openai
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from backend.config import get_settings


def _resolve_key(api_key: str | None) -> SecretStr:
    key = SecretStr(api_key) if api_key else get_settings().openai_api_key
    if key is None:
        raise RuntimeError("OPENAI_API_KEY is not set. Copy .env.example to .env and add your key.")
    return key


def get_llm(api_key: str | None = None, model: str | None = None) -> ChatOpenAI:
    return ChatOpenAI(
        model=model or get_settings().openai_model,
        api_key=_resolve_key(api_key),
        temperature=0,
    )


def verify_api_key(api_key: str | None = None, http_client: httpx.Client | None = None) -> None:
    client = openai.OpenAI(
        api_key=_resolve_key(api_key).get_secret_value(), max_retries=0, http_client=http_client
    )
    client.models.list()
