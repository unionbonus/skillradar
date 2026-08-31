"""OpenAI-compatible and Anthropic chat completion. Secrets never logged."""

from __future__ import annotations

import logging
import os
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import LLMConfig
from app.security import decrypt_secret

logger = logging.getLogger("skillradar")


class LLMError(Exception):
    pass


def resolve_llm_config(db: Session, user_id: UUID | None, config_id: UUID | None = None) -> LLMConfig | None:
    if config_id is not None:
        row = db.get(LLMConfig, config_id)
        if row is None:
            raise LLMError("llm config not found")
        if user_id is not None and row.user_id is not None and row.user_id != user_id:
            raise LLMError("llm config not found")
        return row
    if user_id is not None:
        from sqlalchemy import select

        row = db.scalar(
            select(LLMConfig).where(LLMConfig.user_id == user_id, LLMConfig.is_default.is_(True))
        )
        if row is not None:
            return row
        row = db.scalar(select(LLMConfig).where(LLMConfig.user_id == user_id))
        if row is not None:
            return row
    return None


def complete(
    prompt: str,
    system: str = "You are SkillRadar analyst. Reply with valid JSON only.",
    llm_config: LLMConfig | None = None,
    timeout: float = 45.0,
) -> str:
    settings = get_settings()
    provider = "openai"
    api_key = settings.llm_api_key
    base_url = settings.llm_base_url.rstrip("/")
    model = settings.llm_model
    temperature = 0.2
    max_tokens = 4096
    if llm_config is not None:
        provider = (llm_config.provider or "openai").lower()
        if llm_config.api_key_encrypted:
            api_key = decrypt_secret(llm_config.api_key_encrypted)
        if llm_config.base_url:
            base_url = llm_config.base_url.rstrip("/")
        if llm_config.model_name:
            model = llm_config.model_name
        temperature = float(llm_config.temperature or 0.2)
        max_tokens = int(llm_config.max_tokens or 4096)
    if not api_key:
        raise LLMError("LLM API key not configured")
    if os.environ.get("SKILLRADAR_OFFLINE") == "1":
        raise LLMError("offline mode")
    try:
        if provider == "anthropic":
            return _anthropic(api_key, base_url, model, system, prompt, temperature, max_tokens, timeout)
        return _openai_compat(api_key, base_url, model, system, prompt, temperature, max_tokens, timeout)
    except httpx.HTTPError as exc:
        raise LLMError(f"LLM request failed: {exc}") from exc
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise LLMError(f"LLM response malformed: {exc}") from exc


def ping(llm_config: LLMConfig | None = None) -> str:
    return complete("Reply with the single word pong.", system="You are a connection probe.", llm_config=llm_config, timeout=20.0)


def _openai_compat(
    api_key: str,
    base_url: str,
    model: str,
    system: str,
    prompt: str,
    temperature: float,
    max_tokens: int,
    timeout: float,
) -> str:
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()
    content = data["choices"][0]["message"]["content"]
    if not isinstance(content, str) or not content.strip():
        raise LLMError("empty LLM content")
    return content


def _anthropic(
    api_key: str,
    base_url: str,
    model: str,
    system: str,
    prompt: str,
    temperature: float,
    max_tokens: int,
    timeout: float,
) -> str:
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        url = root + "/messages"
    else:
        url = root + "/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
    }
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()
    parts = data.get("content") or []
    text = "".join(p.get("text") or "" for p in parts if isinstance(p, dict))
    if not text.strip():
        raise LLMError("empty LLM content")
    return text
