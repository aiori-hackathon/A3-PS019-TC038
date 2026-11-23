"""Masking and keyed fingerprints. Nothing in this module returns a raw value."""
from __future__ import annotations

import hashlib
import hmac
import os
import re

from . import validators as _validators
from .validators import strip_separators

_UPI_SHAPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-_]{1,255}@[A-Za-z]{2,64}$")
_EMBEDDED = re.compile(r"(?P<email>[^@\s]+@[^@\s]+\.[A-Za-z]{2,24})|(?P<phone>(?:\+?91[\s-]?|0)?[6-9]\d{4}[\s-]?\d{5})")


def mask_free_text(value: str) -> str:
    """Free text: embedded identifiers become [email]/[phone]; everything else is shape-masked."""
    v = value[:120]
    out, pos = [], 0
    for m in _EMBEDDED.finditer(v):
        out.append(_shape_plain(v[pos:m.start()]))
        out.append("[email]" if m.group("email") else "[phone]")
        pos = m.end()
    out.append(_shape_plain(v[pos:]))
    return "".join(out) + ("…" if len(value) > 120 else "")


def _shape_plain(v: str) -> str:
    v = re.sub(r"[A-Z]", "A", v)
    v = re.sub(r"[a-z]", "a", v)
    v = re.sub(r"[0-9]", "9", v)
    return re.sub(r"[^\x00-\x7f]", "*", v)

_PEPPER = os.environ.get("PRIVACYTWIN_FINGERPRINT_PEPPER", "privacytwin-local-pepper").encode()


def _keep_last(value: str, keep: int, fill: str = "X") -> str:
    digits = strip_separators(value)
    if len(digits) <= keep:
        return fill * len(digits)
    return fill * (len(digits) - keep) + digits[-keep:]


def _group4(masked: str) -> str:
    return "-".join(masked[i:i + 4] for i in range(0, len(masked), 4))


def shape(value: str) -> str:
    """Letters -> a/A, digits -> 9. Keeps the format, drops the content."""
    out = re.sub(r"[A-Z]", "A", value[:24])
    out = re.sub(r"[a-z]", "a", out)
    out = re.sub(r"[0-9]", "9", out)
    out = re.sub(r"[^\x00-\x7f]", "*", out)
    return out + ("…" if len(value) > 24 else "")


def mask(value: str, rule_id: str | None) -> str:
    """Return a masked example. Unknown or non-personal columns get a shape mask."""
    v = str(value).strip()
    if not v:
        return ""
    if rule_id == "email":
        if not _validators.email(v):
            return shape(v)
        local, _, domain = v.partition("@")
        return f"{local[:2]}****@{domain}"
    if rule_id == "upi_id":
        if not _UPI_SHAPE.match(v):
            return shape(v)
        local, _, handle = v.partition("@")
        return f"{local[:2]}****@{handle}"
    if rule_id == "mobile_in":
        return "+91-XXXXXX" + strip_separators(v)[-4:]
    if rule_id in ("aadhaar", "card_number"):
        return _group4(_keep_last(v, 4))
    if rule_id == "bank_account":
        return _keep_last(v, 4)
    if rule_id in ("pan", "passport_in", "voter_id", "driving_licence", "gstin"):
        s = strip_separators(v).upper()
        return "X" * (len(s) - 4) + s[-4:]
    if rule_id == "ifsc":
        s = v.upper()
        return s[:4] + "0XXXXXX"
    if rule_id == "pin_code":
        return strip_separators(v)[:2] + "XXXX"
    if rule_id in ("latitude", "longitude"):
        return re.sub(r"(\.\d)\d+", r"\1**", v)
    if rule_id == "geo_pair":
        return re.sub(r"(\.\d)\d+", r"\1**", v)
    if rule_id == "ip_address":
        if "." in v:
            parts = v.split(".")
            return ".".join(parts[:2] + ["x", "x"])
        return v.split(":")[0] + ":xxxx:…"
    if rule_id == "date_of_birth":
        m = re.search(r"(19|20)\d{2}", v)
        return f"XX-XX-{m.group(0)}" if m else "XX-XX-XXXX"
    if rule_id == "age":
        return "XX"
    if rule_id == "gender":
        return v[:1].upper() + "***"
    if rule_id == "person_name":
        return " ".join(t[:1].upper() + "***" for t in v.split()[:3])
    if rule_id == "place":
        return v[:2] + "****"
    if rule_id == "address":
        return f"[address, {len(v)} chars]"
    return shape(v)


def masked_examples(values: list[str], rule_id: str | None, limit: int = 3) -> list[str]:
    seen: list[str] = []
    for v in values:
        m = mask(v, rule_id)
        if m and m not in seen:
            seen.append(m)
        if len(seen) >= limit:
            break
    return seen


def _hmac(salt: str, value: str) -> int:
    return int.from_bytes(hmac.new(_PEPPER + salt.encode(), value.encode(), hashlib.sha256).digest()[:4], "big")


def fingerprint(values: list[str], salt: str, k: int = 32) -> list[int]:
    """Bottom-k MinHash of keyed 32-bit hashes of normalised values.

    Only k truncated keyed hashes are kept per column, enough to estimate overlap
    between columns (lineage) but not to enumerate the values.
    """
    normalised = {re.sub(r"\s+", "", v.lower()) for v in values if v}
    return sorted({_hmac(salt, v) for v in normalised})[:k]


def overlap(a: list[int], b: list[int], k: int = 32) -> float:
    """Estimated Jaccard similarity from two bottom-k sketches."""
    if not a or not b:
        return 0.0
    union = sorted(set(a) | set(b))[:k]
    sa, sb = set(a), set(b)
    both = sum(1 for h in union if h in sa and h in sb)
    return round(both / len(union), 3)


# ------------------------------------------------------------ masking preview

def apply_strategy(value: str, strategy: str, rule_id: str | None, salt: str) -> str:
    if strategy == "partial":
        return mask(value, rule_id)
    if strategy == "hash":
        return hmac.new(_PEPPER + salt.encode(), value.encode(), hashlib.sha256).hexdigest()[:16]
    if strategy == "tokenise":
        digest = hmac.new(_PEPPER + salt.encode() + b"tok", value.encode(), hashlib.sha256).hexdigest()
        return "TKN_" + digest[:10].upper()
    if strategy == "redact":
        return "[REDACTED]"
    return value


# Illustrative synthetic examples per rule for the masking preview. These are
# invented values, not taken from any scan.
SYNTHETIC_EXAMPLES = {
    "email": "ravi.kumar@example.in",
    "mobile_in": "+91 98765 43210",
    "aadhaar": "2345 6789 0124",
    "pan": "ABCPK1234F",
    "passport_in": "K1234567",
    "voter_id": "XYZ1234567",
    "driving_licence": "MH12 20150012345",
    "gstin": "27ABCPK1234F1Z5",
    "ifsc": "HDFC0001234",
    "bank_account": "50100012345678",
    "card_number": "4111 1111 1111 1111",
    "upi_id": "ravi.k@okaxis",
    "pin_code": "560034",
    "address": "Flat 12, 4th Cross, Indiranagar, Bengaluru",
    "place": "Bengaluru",
    "geo_pair": "12.9716, 77.5946",
    "latitude": "12.9716",
    "longitude": "77.5946",
    "ip_address": "203.0.113.42",
    "date_of_birth": "1990-04-17",
    "age": "34",
    "gender": "Female",
    "person_name": "Ravi Kumar",
}
