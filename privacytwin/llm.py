"""Optional LLM layer (Groq by default, any OpenAI-compatible endpoint works).

Configuration, first match wins:
  PRIVACYTWIN_LLM_DISABLE=1          -> off (used by the test suite)
  GROQ_API_KEY or data/groq-key.txt  -> Groq, model GROQ_MODEL (default llama-3.3-70b-versatile)
  PRIVACYTWIN_LLM_URL (+ _MODEL, _KEY) -> any OpenAI-compatible chat endpoint

Only workspace metadata is ever sent (table/column names, classes, signal scores,
gap fields, rule IDs). Raw values and masked examples are never sent.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import DISCLAIMER

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
KEY_FILE = Path(__file__).resolve().parents[1] / "data" / "groq-key.txt"
SYSTEM = ("You are PrivacyTwin's AI analyst. You help privacy teams understand where personal data lives. "
          "Use ONLY the JSON metadata provided; never invent tables, columns or numbers. Be concise and specific; "
          "cite PT-IDs and table.column names. Never make legal determinations and never use the words "
          "'compliant', 'violation' or 'illegal'. " + DISCLAIMER)

_cache: dict[str, str] = {}
MAX_RETRY_WAIT = float(os.environ.get("PRIVACYTWIN_LLM_MAX_WAIT", "20"))


def _retry_after(exc: urllib.error.HTTPError) -> float | None:
    """Seconds to wait from a 429: Retry-After header, else 'try again in 4.14s' in the body."""
    try:
        header = exc.headers.get("retry-after") if exc.headers else None
        if header:
            return float(header)
        m = re.search(r"try again in ([\d.]+)s", exc.read().decode("utf-8", "replace"))
        return float(m.group(1)) if m else None
    except (ValueError, OSError):
        return None
_resolved: dict[str, str] = {}
PREFERRED = ["openai/gpt-oss-120b", "qwen/qwen3.8-27b", "openai/gpt-oss-20b", "llama-3.3-70b-versatile"]


def _pick_groq_model(key: str) -> str | None:
    """If the configured model was retired, pick the best available one from the key's model list."""
    try:
        req = urllib.request.Request("https://api.groq.com/openai/v1/models", headers={"Authorization": f"Bearer {key}", "User-Agent": "PrivacyTwin/3"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            ids = {m["id"] for m in json.loads(resp.read())["data"]}
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError, OSError):
        return None
    return next((m for m in PREFERRED if m in ids), None)


def config() -> dict | None:
    if os.environ.get("PRIVACYTWIN_LLM_DISABLE") == "1":
        return None
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if not key and KEY_FILE.exists():
        key = KEY_FILE.read_text(encoding="utf-8").strip()
    if key:
        return {"provider": "Groq", "url": GROQ_URL, "model": os.environ.get("GROQ_MODEL") or _resolved.get("groq", PREFERRED[0]), "key": key}
    url = os.environ.get("PRIVACYTWIN_LLM_URL")
    if url:
        return {"provider": "Custom", "url": url, "model": os.environ.get("PRIVACYTWIN_LLM_MODEL", "local"),
                "key": os.environ.get("PRIVACYTWIN_LLM_KEY", "")}
    return None


def status() -> dict:
    c = config()
    return {"enabled": bool(c), "provider": c["provider"] if c else None, "model": c["model"] if c else None,
            "endpoint": re.sub(r"//[^/@]+@", "//***@", c["url"]) if c else None,
            "sends": "Table and column names, candidate classes, signal scores and gap fields. Never raw or masked values."}


def chat(user: str, max_tokens: int = 450, cache: bool = True) -> str | None:
    """One chat completion. Returns None on any failure so callers fall back to offline answers."""
    c = config()
    if not c:
        return None
    ck = hashlib.sha256((c["model"] + user).encode()).hexdigest()
    if cache and ck in _cache:
        return _cache[ck]
    headers = {"Content-Type": "application/json", "User-Agent": "PrivacyTwin/3"}
    if c["key"]:
        headers["Authorization"] = f"Bearer {c['key']}"

    def call(model: str) -> str:
        payload = {"model": model, "temperature": 0.2, "max_tokens": max_tokens + 1200,
                   "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user[:24000]}]}
        if "gpt-oss" in model:
            payload["reasoning_effort"] = "low"  # reasoning models: keep latency low
        body = json.dumps(payload).encode()
        for attempt in (1, 2):
            try:
                with urllib.request.urlopen(urllib.request.Request(c["url"], body, headers), timeout=30) as resp:
                    return json.loads(resp.read())["choices"][0]["message"]["content"].strip()
            except urllib.error.HTTPError as exc:
                # Free tiers cap tokens per minute; the provider says how long to wait. Retry once.
                wait = _retry_after(exc)
                if exc.code != 429 or attempt == 2 or wait is None or wait > MAX_RETRY_WAIT:
                    raise
                time.sleep(wait + 0.25)
        raise RuntimeError("unreachable")

    try:
        try:
            text = call(c["model"])
        except urllib.error.HTTPError as exc:
            if exc.code != 404 or c["provider"] != "Groq" or os.environ.get("GROQ_MODEL"):
                raise
            model = _pick_groq_model(c["key"])
            if not model:
                return None
            _resolved["groq"] = model
            text = call(model)
    except (urllib.error.URLError, TimeoutError, KeyError, IndexError, ValueError, OSError):
        return None
    if not text:
        return None
    text = text.translate({0x2011: "-", 0x2010: "-", 0x2013: "-", 0x202F: " ", 0x00A0: " "})
    text = re.sub(r"\b(compliant|violation|illegal)\b", "flagged", text, flags=re.I)
    if cache:
        _cache[ck] = text
    return text


def finding_context(r: dict) -> dict:
    """Metadata for one finding. Deliberately excludes masked examples and raw values."""
    return {"pt_id": r["pt_id"], "table": r["table"], "column": r["column"], "class": r["class"],
            "confidence": r["confidence"], "band": r["band"], "rule": r["rule_id"], "signals": r["signals"],
            "status": r["status"], "gaps": [g["field"] for g in r["gaps"]], "quasi_identifier": r["quasi_identifier"],
            "profile": {k: r["profile"][k] for k in ("inferred_type", "null_pct", "distinct_pct", "total_rows")}}
