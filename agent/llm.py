"""
Unified LLM client — supports Groq and Google Gemini.

Both providers are completely FREE (no credit card needed):
  • groq   — Groq Cloud   (llama-3.3-70b-versatile)  → console.groq.com
  • gemini — Google AI    (gemini-2.5-flash)           → aistudio.google.com

Default provider: groq  (higher rate limits, very fast)

Set LLM_PROVIDER in your .env to switch providers:
    LLM_PROVIDER=groq      # default
    LLM_PROVIDER=gemini    # fallback

Both use the OpenAI-compatible REST API, so a single client handles both.
"""
from __future__ import annotations

import logging
import os
import time
import re
from typing import Any

# pyrefly: ignore [missing-import]
import openai
# pyrefly: ignore [missing-import]
from openai import OpenAI

logger = logging.getLogger(__name__)

# ── Provider configurations ───────────────────────────────────────────────────

_PROVIDERS: dict[str, dict[str, Any]] = {
    "groq": {
        "env_key":  "GROQ_API_KEY",
        "base_url": "https://api.groq.com/openai/v1",
        "model":    "llama-3.3-70b-versatile",   # Llama 3.3 70B — free tier
        "note":     "Free at https://console.groq.com — no credit card needed",
    },
    "gemini": {
        "env_key":  "GEMINI_API_KEY",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "model":    "gemini-2.5-flash",           # Gemini 3.5 Flash — free tier
        "note":     "Free at https://aistudio.google.com/apikey — no credit card needed",
    },
}

_client: OpenAI | None = None
_provider: str = ""
_model: str = ""


def _init() -> None:
    """Lazily initialise the OpenAI-compatible client on first call."""
    global _client, _provider, _model

    if _client is not None:
        return

    _provider = os.getenv("LLM_PROVIDER", "groq").strip().lower()

    if _provider not in _PROVIDERS:
        raise ValueError(
            f"Unknown LLM_PROVIDER='{_provider}'. "
            f"Supported providers: groq, gemini\n"
            f"  Set LLM_PROVIDER=groq or LLM_PROVIDER=gemini in your .env"
        )

    cfg = _PROVIDERS[_provider]

    # Honour LLM_MODEL override; fall back to provider default when blank/unset
    _model = (os.getenv("LLM_MODEL") or "").strip() or cfg["model"]

    env_key = cfg["env_key"]
    api_key = os.environ.get(env_key, "").strip()

    if not api_key or api_key.startswith("your-") or api_key.endswith("-here"):
        raise RuntimeError(
            f"\n❌  {env_key} is not set or still has a placeholder value.\n"
            f"   {cfg['note']}\n"
            f"   Open your .env file and set: {env_key}=your-real-key-here"
        )

    _client = OpenAI(api_key=api_key, base_url=cfg["base_url"])
    logger.info("[LLM] Provider: %s  Model: %s", _provider, _model)


def chat(system: str, user: str, max_tokens: int = 1024) -> str:
    """
    Send a system + user message to the configured LLM provider.
    Returns the assistant's response text (stripped).

    Includes self-healing rate limit retry handling for free tiers.
    """
    _init()

    max_retries = 5
    base_delay = 5.0

    for attempt in range(1, max_retries + 1):
        try:
            resp = _client.chat.completions.create(
                model=_model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user},
                ],
            )
            return resp.choices[0].message.content.strip()
        except openai.RateLimitError as exc:
            logger.warning("[LLM] Rate limit hit (attempt %d/%d). Details: %s", attempt, max_retries, exc)
            if attempt == max_retries:
                raise exc
            
            # Try to parse retry delay from the error message
            delay = base_delay
            msg = str(exc)
            # e.g., "try again in 5m4.992s" or "retry in 7s" or similar
            match_s = re.search(r"try again in (\d+(?:\.\d+)?)s", msg)
            if not match_s:
                match_s = re.search(r"retry in (\d+(?:\.\d+)?)s", msg)
            
            match_m = re.search(r"try again in (\d+)m(\d+(?:\.\d+)?)s", msg)
            
            if match_m:
                minutes = int(match_m.group(1))
                seconds = float(match_m.group(2))
                delay = minutes * 60 + seconds + 2.0
            elif match_s:
                delay = float(match_s.group(1)) + 2.0
            else:
                # Exponential backoff
                delay = base_delay * (2 ** (attempt - 1))
            
            logger.warning("[LLM] Sleeping for %.2f seconds before retrying...", delay)
            time.sleep(delay)
        except Exception as exc:
            # Handle general errors that might be rate limits but under different names or formats
            if "rate limit" in str(exc).lower() or "429" in str(exc) or "quota" in str(exc).lower() or "exhausted" in str(exc).lower():
                logger.warning("[LLM] General rate limit/quota exception (attempt %d/%d): %s", attempt, max_retries, exc)
                if attempt == max_retries:
                    raise exc
                
                # Check if retry delay is inside string (like "Please retry in 7.34s")
                delay = base_delay
                msg = str(exc)
                match_retry = re.search(r"[Rr]etry in (\d+(?:\.\d+)?)s", msg)
                if match_retry:
                    delay = float(match_retry.group(1)) + 2.0
                else:
                    delay = base_delay * (2 ** (attempt - 1))
                    
                logger.warning("[LLM] Sleeping for %.2f seconds before retrying...", delay)
                time.sleep(delay)
            else:
                raise exc


def get_provider_name() -> str:
    """Return the active provider name (initialises lazily if not yet called)."""
    return _provider or os.getenv("LLM_PROVIDER", "groq").strip().lower()


def get_model_name() -> str:
    """Return the active model name (initialises lazily if not yet called)."""
    if _model:
        return _model
    provider = os.getenv("LLM_PROVIDER", "groq").strip().lower()
    return _PROVIDERS.get(provider, {}).get("model", "unknown")
