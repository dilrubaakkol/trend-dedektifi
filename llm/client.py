"""LLM sağlayıcı istemcileri. Anahtar YALNIZCA ortam değişkeninden okunur; koda/repoya yazılmaz.

Ortam değişkenleri:
  LLM_PROVIDER = anthropic | openai | none   (boş bırakılırsa LLM kullanılmaz, şablon devrede)
  LLM_MODEL    = model adı (sağlayıcının belgesinden)
  LLM_API_KEY  = API anahtarı
  LLM_BASE_URL = (yalnız openai) OpenAI uyumlu uç nokta; Groq, Gemini'nin OpenAI uyumlu ucu,
                 yerel Ollama (http://localhost:11434/v1) gibi servisler de bu yolla bağlanır.
Streamlit'te bunlar st.secrets'tan os.environ'a aktarılabilir.
"""
from __future__ import annotations

import os
from typing import Protocol

import requests

TIMEOUT_S = 60


class LLMClient(Protocol):
    def complete(self, system: str, user: str) -> str: ...


class AnthropicClient:
    """Anthropic Messages API."""

    def __init__(self, model: str, api_key: str):
        self.model, self.api_key = model, api_key

    def complete(self, system: str, user: str) -> str:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": self.model, "max_tokens": 1200, "system": system,
                  "messages": [{"role": "user", "content": user}]},
            timeout=TIMEOUT_S)
        r.raise_for_status()
        return "".join(b.get("text", "") for b in r.json()["content"])


class OpenAICompatClient:
    """OpenAI Chat Completions biçimindeki herhangi bir servis."""

    def __init__(self, model: str, api_key: str, base_url: str):
        self.model, self.api_key, self.base_url = model, api_key, base_url.rstrip("/")

    def complete(self, system: str, user: str) -> str:
        r = requests.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "temperature": 0.2,
                  "messages": [{"role": "system", "content": system},
                               {"role": "user", "content": user}]},
            timeout=TIMEOUT_S)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


def get_client() -> LLMClient | None:
    """Ortam değişkenlerinden istemci kurar; ayar yoksa None (şablon açıklayıcı çalışır)."""
    provider = os.environ.get("LLM_PROVIDER", "none").strip().lower()
    if provider in ("", "none"):
        return None
    model, key = os.environ.get("LLM_MODEL"), os.environ.get("LLM_API_KEY")
    if not model or not key:
        raise RuntimeError("LLM_MODEL ve LLM_API_KEY ortam değişkenleri gerekli.")
    if provider == "anthropic":
        return AnthropicClient(model, key)
    if provider == "openai":
        return OpenAICompatClient(model, key, os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1"))
    raise RuntimeError(f"Bilinmeyen LLM_PROVIDER: {provider}")
