"""Pembuat objek LLM + helper structured output.

MODEL_NAME di .env berformat "<provider>:<nama-model>", contoh:
  openrouter:openai/gpt-4o-mini | openai:gpt-4o-mini | anthropic:claude-haiku-4-5 | offline

Kalau provider tidak dikenal / API key kosong / MODEL_NAME=offline -> get_llm() mengembalikan None
dan semua agent memakai fallback aturan + template (mode offline).
"""

import os
from functools import lru_cache

from langchain.chat_models import init_chat_model
from langchain_openai import ChatOpenAI

import config

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
_KEY_BY_PROVIDER = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "openrouter": "OPENROUTER_API_KEY"}
_status = {"mode": "offline", "reason": ""}


@lru_cache(maxsize=1)
def get_llm():
    name = config.MODEL_NAME
    if name.lower() in ("", "offline", "none"):
        _status.update(mode="offline", reason="MODEL_NAME=offline")
        return None
    provider, _, model = name.partition(":")
    provider = provider.lower()
    if provider not in _KEY_BY_PROVIDER or not model:
        _status.update(mode="offline", reason=f"provider '{provider}' tidak dikenal")
        return None
    key = os.getenv(_KEY_BY_PROVIDER[provider], "").strip()
    if not key:
        _status.update(mode="offline", reason=f"{_KEY_BY_PROVIDER[provider]} kosong")
        return None
    common = dict(temperature=config.LLM_TEMPERATURE, max_tokens=config.LLM_MAX_TOKENS, timeout=90, max_retries=2)
    if provider == "openrouter":
        llm = ChatOpenAI(model=model, base_url=OPENROUTER_BASE_URL, api_key=key, **common)
    else:
        llm = init_chat_model(model, model_provider=provider, **common)
    _status.update(mode="llm", reason=name)
    return llm


def llm_status() -> str:
    get_llm()
    return _status["reason"] if _status["mode"] == "llm" else f"offline ({_status['reason']})"


def is_online() -> bool:
    return get_llm() is not None


def structured(schema, system: str, user: str):
    """Panggil LLM dengan structured output. Return (objek | None, pesan_error | None)."""
    llm = get_llm()
    if llm is None:
        return None, "offline"
    try:
        kwargs = {"method": "function_calling"} if isinstance(llm, ChatOpenAI) else {}
        out = llm.with_structured_output(schema, **kwargs).invoke([("system", system), ("human", user)])
        if out is None:
            return None, "LLM tidak mengembalikan output terstruktur"
        return out, None
    except Exception as e:  # jaringan, rate limit, parse error -> fallback
        return None, f"{type(e).__name__}: {str(e)[:200]}"
