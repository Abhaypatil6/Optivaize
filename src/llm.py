from __future__ import annotations

import json
import os
import re
from typing import Any, Literal

from dotenv import load_dotenv

load_dotenv()

Provider = Literal["groq", "gemini"]

DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"


def use_mock_llm() -> bool:
    return os.getenv("MOCK_LLM", "0").strip().lower() in ("1", "true", "yes")


def get_provider() -> Provider:
    name = os.getenv("LLM_PROVIDER", "groq").strip().lower()
    if name not in ("groq", "gemini"):
        raise ValueError(f"LLM_PROVIDER must be 'groq' or 'gemini', got: {name}")
    return name  # type: ignore[return-value]


def get_model() -> str:
    provider = get_provider()
    if provider == "groq":
        return os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL)
    return os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)


def _groq_chat(messages: list[dict], temperature: float, json_mode: bool) -> str:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY missing in .env (or set MOCK_LLM=1)")

    import httpx

    body: dict[str, Any] = {
        "model": get_model(),
        "messages": messages,
        "temperature": temperature,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    resp = httpx.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=60.0,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Groq API error {resp.status_code}: {resp.text[:500]}")
    data = resp.json()
    return (data["choices"][0]["message"]["content"] or "").strip()


def _gemini_chat(messages: list[dict], temperature: float, json_mode: bool) -> str:
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY missing in .env (or set MOCK_LLM=1)")

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    system_parts = [m["content"] for m in messages if m["role"] == "system"]
    user_parts = [m["content"] for m in messages if m["role"] == "user"]
    prompt = ""
    if system_parts:
        prompt += system_parts[0] + "\n\n"
    prompt += user_parts[-1] if user_parts else ""

    config = types.GenerateContentConfig(
        temperature=temperature,
        response_mime_type="application/json" if json_mode else "text/plain",
    )
    response = client.models.generate_content(
        model=get_model(),
        contents=prompt,
        config=config,
    )
    return (response.text or "").strip()


def _llm_complete(system: str, user: str, temperature: float, json_mode: bool) -> str:
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    if get_provider() == "groq":
        return _groq_chat(messages, temperature, json_mode)
    return _gemini_chat(messages, temperature, json_mode)


def _parse_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


def chat_json(system: str, user: str, mock_response: dict | None = None) -> dict[str, Any]:
    if use_mock_llm():
        if mock_response is None:
            raise ValueError("mock_response required when MOCK_LLM=1")
        return mock_response

    content = _llm_complete(system, user, temperature=0.2, json_mode=True)
    return _parse_json(content)


def chat_text(system: str, user: str, mock_text: str | None = None) -> str:
    if use_mock_llm():
        return mock_text or ""

    return _llm_complete(system, user, temperature=0.3, json_mode=False)


def extract_order_ids(text: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"ORD-\d{4}", text, flags=re.IGNORECASE)))
