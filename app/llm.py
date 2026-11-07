"""One small wrapper for whichever AI the team uses.
Set LLM_PROVIDER in .env to: gemini, claude, openai or demo.
If it is left as "auto", the first provider with a key is used; with no key we run in demo mode
(rule-based, no AI), so the backend always works.

Uses plain HTTP calls, so no extra SDK needs installing."""
import json
import os
import re

import httpx

TIMEOUT = 90


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def provider() -> str:
    p = _env("LLM_PROVIDER", "auto").lower()
    if p != "auto":
        return p
    if _env("GEMINI_API_KEY"):
        return "gemini"
    if _env("ANTHROPIC_API_KEY"):
        return "claude"
    if _env("OPENAI_API_KEY"):
        return "openai"
    return "demo"


class LLMError(Exception):
    pass


def _parse_json(text: str) -> dict:
    text = text.strip()
    # Strip ```json fences if the model added them
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            return json.loads(m.group(0))
        raise LLMError("The AI did not return valid JSON")


# Google renames and retires Gemini models often. We try the one in .env first,
# then these free-tier models in order, and remember whichever works.
GEMINI_FALLBACKS = ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-2.5-flash"]
_gemini_working_model = None


def _gemini(system: str, user: str) -> str:
    global _gemini_working_model
    key = _env("GEMINI_API_KEY")
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
    }
    models = [_gemini_working_model] if _gemini_working_model else []
    models += [m for m in [_env("GEMINI_MODEL")] + GEMINI_FALLBACKS if m and m not in models]
    last = ""
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        r = httpx.post(url, headers={"x-goog-api-key": key}, json=body, timeout=TIMEOUT)
        if r.status_code == 200:
            _gemini_working_model = model
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        last = f"Gemini error {r.status_code} on {model}: {r.text[:200]}"
        # 404 = model retired/renamed; 429 with limit 0 = not on free tier. Try the next one.
        if r.status_code not in (404, 400, 429):
            break
    raise LLMError(last)


def check() -> dict:
    """Tiny test call so you can confirm your key works (used by /health/check)."""
    p = provider()
    if p == "demo":
        return {"ok": False, "provider": "demo", "message": "No AI key set - running in demo mode."}
    try:
        out = ask_json('Reply with JSON {"ok": true}', "ping")
        model = _gemini_working_model if p == "gemini" else _env(f"{'CLAUDE' if p == 'claude' else 'OPENAI'}_MODEL")
        return {"ok": bool(out.get("ok", True)), "provider": p, "model": model, "message": "AI key works."}
    except LLMError as e:
        return {"ok": False, "provider": p, "message": str(e)}


def _claude(system: str, user: str) -> str:
    key = _env("ANTHROPIC_API_KEY")
    model = _env("CLAUDE_MODEL", "claude-haiku-5-5")
    r = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={
            "model": model,
            "max_tokens": 4096,
            "temperature": 0.2,
            "system": system + "\nRespond with JSON only.",
            "messages": [{"role": "user", "content": user}],
        },
        timeout=TIMEOUT,
    )
    if r.status_code != 200:
        raise LLMError(f"Claude error {r.status_code}: {r.text[:300]}")
    return "".join(b.get("text", "") for b in r.json()["content"])


def _openai(system: str, user: str) -> str:
    key = _env("OPENAI_API_KEY")
    model = _env("OPENAI_MODEL", "gpt-4o-mini")
    r = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": model,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        },
        timeout=TIMEOUT,
    )
    if r.status_code != 200:
        raise LLMError(f"OpenAI error {r.status_code}: {r.text[:300]}")
    return r.json()["choices"][0]["message"]["content"]


def ask_json(system: str, user: str) -> dict:
    """Send a prompt, get a dict back. Raises LLMError if no AI is configured or the call fails."""
    p = provider()
    if p == "demo":
        raise LLMError("Demo mode: no AI key configured")
    fn = {"gemini": _gemini, "claude": _claude, "openai": _openai}.get(p)
    if not fn:
        raise LLMError(f"Unknown LLM_PROVIDER '{p}'. Use gemini, claude, openai or demo.")
    try:
        return _parse_json(fn(system, user))
    except LLMError:
        raise
    except Exception as e:
        raise LLMError(f"{p} call failed: {e}")
