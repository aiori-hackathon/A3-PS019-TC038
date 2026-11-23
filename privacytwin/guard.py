"""Prompt guardrails for the AI chat (Ask AI / assistant).

* Length: questions are limited to MAX_QUESTION_CHARS after normalisation.
* Normalisation: control characters removed, whitespace collapsed.
* Injection / exfiltration: prompts that try to override instructions, reveal the system
  prompt or extract raw values are answered by a fixed safe reply and never reach the LLM.
* Rate limit: per workspace, CHAT_LIMIT questions per CHAT_WINDOW seconds.
"""
from __future__ import annotations

import re
import time
import unicodedata
from collections import defaultdict, deque

MAX_QUESTION_CHARS = 300
MIN_QUESTION_CHARS = 3
CHAT_LIMIT = 30
CHAT_WINDOW = 300

_BLOCKED = [
    (r"\b(ignore|disregard|forget|override)\b.{0,40}\b(previous|above|prior|earlier|all|system)\b.{0,20}\b(instruction|prompt|rule|message)s?",
     "instruction override"),
    (r"\b(system|developer|hidden)\s+prompt\b|\byour (instructions|rules|prompt)\b", "system prompt request"),
    (r"\b(act|pretend|behave|roleplay|role-play)\s+(as|to be|like)\b|\byou are now\b|\bjailbreak\b|\bDAN\b|\bdo anything now\b|\bunrestricted\b|\bdeveloper mode\b",
     "role override"),
    (r"\b(show|list|give|print|reveal|dump|export|display|send|tell me|unmask|decode|reconstruct)\b.{0,30}\b(raw|unmasked|full|actual|real|original|complete|plain)\s+(values?|data|records?|numbers?|aadhaar|pan|emails?|phones?|rows?)\b",
     "raw data request"),
    (r"\b(show|list|give|print|reveal|dump|export|display|send|tell me)\b.{0,30}\b(aadhaar|pan|passport|card|account|mobile|phone)\s*(numbers?|nos?\.?|values?)\b",
     "identifier extraction"),
    (r"\b(api[_ ]?key|groq|secret|password|token|credential)s?\b.{0,20}\b(show|print|reveal|what|give)\b|\b(show|print|reveal|give)\b.{0,20}\b(api[_ ]?key|secret|password|token|credential)s?\b",
     "secret request"),
    (r"<\s*script|\{\{.*\}\}|\bselect\b.+\bfrom\b|\bdrop\s+table\b", "code / query injection"),
]
_COMPILED = [(re.compile(p, re.I | re.S), why) for p, why in _BLOCKED]

SAFE_REPLY = ("I can't help with that request. I answer questions about where personal data lives, why fields were "
              "flagged, gaps, changes and risk, using workspace metadata only. Raw values are never stored, so they "
              "cannot be shown. Try one of the suggested questions.")


class GuardError(ValueError):
    pass


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = "".join(ch for ch in text if unicodedata.category(ch)[0] != "C" or ch in "\n\t")
    return re.sub(r"\s+", " ", text).strip()


def check(question: str) -> tuple[str, str | None]:
    """Returns (clean question, reason it is blocked or None). Raises GuardError on length."""
    q = normalise(question)
    if len(q) < MIN_QUESTION_CHARS:
        raise GuardError("Type a question of at least 3 characters.")
    if len(q) > MAX_QUESTION_CHARS:
        raise GuardError(f"Questions are limited to {MAX_QUESTION_CHARS} characters (yours has {len(q)}). Please shorten it.")
    for pattern, why in _COMPILED:
        if pattern.search(q):
            # "list the tables/columns with Aadhaar numbers" asks about metadata, which is fine
            if why in ("identifier extraction", "raw data request") and _METADATA_Q.search(q):
                continue
            return q, why
    return q, None


_METADATA_Q = re.compile(r"\b(tables?|columns?|fields?|sources?|where|which|how many|count)\b", re.I)


class ChatLimiter:
    def __init__(self, limit: int = CHAT_LIMIT, window: int = CHAT_WINDOW):
        self.limit, self.window = limit, window
        self.hits: dict[str, deque] = defaultdict(deque)

    def allow(self, ws: str) -> bool:
        now = time.monotonic()
        q = self.hits[ws]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        return True
