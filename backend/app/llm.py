"""Groq chat completions. The caller shows this text as the answer."""

from __future__ import annotations

import re

import httpx

from app.config import Settings

_THINKING_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


class LlmService:
    def __init__(self, settings: Settings) -> None:
        if settings.groq_api_key:
            self.base_url = settings.groq_base_url.rstrip("/")
            self.api_key = settings.groq_api_key
            self.model = settings.groq_model
            self.provider = "groq"
        else:
            self.base_url = settings.openai_base_url.rstrip("/")
            self.api_key = settings.openai_api_key
            self.model = settings.openai_model
            self.provider = "openai"

    def complete(self, system: str, user: str, *, max_tokens: int = 2200) -> str | None:
        if not self.base_url or not self.api_key or not self.model:
            return None
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "temperature": 0.1,
                    "max_tokens": max_tokens,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
                timeout=45,
            )
            response.raise_for_status()
            message = response.json()["choices"][0]["message"]
            content = message.get("content") or ""
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
            return None
        if isinstance(content, list):
            parts: list[str] = []
            for part in content:
                if isinstance(part, dict):
                    parts.append(str(part.get("text") or ""))
                else:
                    parts.append(str(part))
            content = "".join(parts)
        if not isinstance(content, str):
            return None
        cleaned = _THINKING_RE.sub("", content).strip()
        return cleaned or None
