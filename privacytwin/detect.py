"""Explainable three-signal detection.

For each column and each enabled rule:
    header    in {0, 1}   normalised column name matches a keyword
    value     in [0, 1]   share of sampled non-null values fully matching the rule pattern
    validator in [0, 1]   share of sampled non-null values passing the rule validator

score = weight * (Wh*header + Wv*value + Wc*validator), then adjusted by:
  * requires_header rules score 0 without a header match;
  * header-only evidence contradicted by values (value = validator = 0) is halved;
  * negative header keywords (order_id, sku ...) multiply by negative_penalty unless
    the rule's own header matched or a checksum validator passes >= 90%.
The best-scoring rule above its threshold sets the candidate class.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime

import regex

from .masking import fingerprint, mask_free_text, masked_examples, shape
from .rules import NOT_PERSONAL
from .validators import CHECKSUM_VALIDATORS, VALIDATORS, parse_date, strip_separators

MAX_VALUE_LEN = 400
REGEX_TIMEOUT = 0.05

VALIDATOR_LABELS = {
    "email": "email format check",
    "indian_mobile": "Indian mobile check (+91/0 prefix, starts 6-9)",
    "aadhaar": "Aadhaar Verhoeff checksum",
    "pan": "PAN structure check",
    "passport": "Indian passport structure check",
    "voter_id": "EPIC structure check",
    "driving_licence": "driving-licence state/RTO/year check",
    "gstin": "GSTIN checksum",
    "ifsc": "IFSC structure check",
    "bank_account": "bank-account length check",
    "card_number": "Luhn checksum",
    "upi_id": "UPI handle check",
    "pin_code": "PIN-code region check",
    "lat_long_pair": "coordinate range check",
    "latitude": "latitude range check",
    "longitude": "longitude range check",
    "ip_address": "IP address parser",
    "date_of_birth": "plausible birth-date check",
    "age": "age range check (1-120)",
    "gender": "gender vocabulary check",
    "address": "address token check",
    "indian_place": "Indian city/state list",
    "person_name": "common Indian name list",
}

PREFIX_SENSITIVE_RULES = {"voter_id", "passport_in", "pan", "driving_licence", "gstin"}


def constant_prefix_share(values: list[str]) -> float:
    """Share of values whose first three characters equal the most common alphabetic prefix."""
    prefixes = Counter(v[:3].upper() for v in values[:500] if len(v) >= 6 and v[:3].isalpha())
    if not prefixes or len(values) < 10:
        return 0.0
    return prefixes.most_common(1)[0][1] / min(len(values), 500)


QUASI_IDENTIFIER_RULES ={"date_of_birth": "dob", "age": "age", "gender": "gender", "pin_code": "pin", "place": "city"}
JOB_KEYWORDS = {"job", "title", "designation", "occupation", "profession", "role"}


# ---------------------------------------------------------------- headers

def normalise_header(name: str) -> tuple[str, list[str]]:
    s = regex.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(name))
    s = regex.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", s)
    s = regex.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").lower()
    tokens = [t for t in s.split("_") if t]
    # split digits from letters: addr1 -> addr, 1
    split: list[str] = []
    for t in tokens:
        split.extend(p for p in regex.split(r"(?<=[a-z])(?=\d)|(?<=\d)(?=[a-z])", t) if p)
    return "_".join(split), split


def keyword_hit(keywords: list[str], tokens: list[str]) -> str | None:
    joined = "".join(tokens)
    for kw in keywords:
        kt = [t for t in kw.split("_") if t]
        n = len(kt)
        if n and any(tokens[i:i + n] == kt for i in range(len(tokens) - n + 1)):
            return kw
        flat = "".join(kt)
        if len(flat) >= 5 and flat in joined:
            return kw
    return None


# ---------------------------------------------------------------- profile

_INT = re.compile(r"-?\d+")
_DEC = re.compile(r"-?\d+\.\d+")
_DATETIME = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?.*")


def infer_type(values: list[str]) -> str:
    if not values:
        return "empty"
    sample = values[:300]
    def share(pred):
        return sum(1 for v in sample if pred(v)) / len(sample)
    if share(lambda v: _INT.fullmatch(v) is not None) >= 0.95:
        return "integer"
    if share(lambda v: _DEC.fullmatch(v) is not None) >= 0.95:
        return "decimal"
    if share(lambda v: v.lower() in ("true", "false", "yes", "no", "0", "1", "y", "n")) >= 0.95:
        return "boolean"
    if share(lambda v: _DATETIME.fullmatch(v) is not None) >= 0.9:
        return "datetime"
    if share(lambda v: parse_date(v) is not None) >= 0.9:
        return "date"
    return "text"


def profile(raw: list, total_rows: int | None = None) -> dict:
    values = [str(v).strip()[:MAX_VALUE_LEN] for v in raw if v is not None and str(v).strip() != ""]
    n, size = len(values), len(raw)
    lengths = [len(v) for v in values]
    return {
        "sample_size": size,
        "non_null": n,
        "null_pct": round(100 * (size - n) / size, 1) if size else 0.0,
        "distinct_pct": round(100 * len(set(values)) / n, 1) if n else 0.0,
        "min_len": min(lengths, default=0),
        "max_len": max(lengths, default=0),
        "inferred_type": infer_type(values),
        "total_rows": total_rows if total_rows is not None else size,
    }


# ---------------------------------------------------------------- scoring

def _normalise(value: str, how: str) -> str:
    if how == "strip_separators":
        return strip_separators(value)
    if how == "upper":
        return value.strip().upper()
    return value.strip()


class _Pattern:
    """Default (reviewed) patterns run on the fast stdlib engine; user-edited patterns run
    on the `regex` engine with a per-call timeout to contain catastrophic backtracking."""

    def __init__(self, source: str, trusted: bool):
        self.trusted = trusted
        self.p = re.compile(source) if trusted else regex.compile(source)

    def fullmatch(self, s: str) -> bool:
        if self.trusted:
            return self.p.fullmatch(s) is not None
        return self.p.fullmatch(s, timeout=REGEX_TIMEOUT) is not None

    def finditer(self, s: str):
        return self.p.finditer(s) if self.trusted else self.p.finditer(s, timeout=REGEX_TIMEOUT)


def _trusted_patterns() -> set[str]:
    from .rules import default_ruleset
    return {r["value_regex"] for r in default_ruleset()["rules"]}


_TRUSTED: set[str] = set()


def _compiled(rule: dict, cache: dict):
    key = rule["value_regex"]
    if key not in cache:
        if not _TRUSTED:
            _TRUSTED.update(_trusted_patterns())
        cache[key] = _Pattern(key, key in _TRUSTED) if key else None
    return cache[key]


_DIGIT_SEP = re.compile(r"(?<=\d)[ \-.](?=\d)")


def value_signature(rule: dict) -> str:
    """Identifies everything that affects the value/validator signals of a rule."""
    return f"{rule['value_regex']}\x1f{rule['normalise']}\x1f{rule['validator']}\x1f{rule['embedded']}"


def header_signal(rule: dict, header_tokens: list[str]) -> tuple[float, str | None, str | None]:
    hit = keyword_hit(rule["header_keywords"], header_tokens)
    excluded = keyword_hit(rule["header_exclude"], header_tokens) if hit else None
    return (1.0 if hit and not excluded else 0.0), hit, excluded


def value_signals(rule: dict, values: list[str], cache: dict, counts: Counter | None = None) -> tuple[float, float, float, bool]:
    """Measure value, validator and embedded rates on the in-memory sample."""
    n = len(values)
    pattern = _compiled(rule, cache)
    validator = VALIDATORS.get(rule["validator"])
    matched = valid = 0
    timed_out = False
    if not n or pattern is None:
        return 0.0, 0.0, 0.0, False
    # measure each distinct value once, weighted by its count
    distinct = counts if counts is not None else Counter(values)
    for v, k in distinct.items():
        nv = _normalise(v, rule["normalise"])
        try:
            ok = pattern.fullmatch(nv)
        except TimeoutError:
            ok, timed_out = False, True
        if ok:
            matched += k
            if validator is None or validator(nv):
                valid += k
    value_rate, valid_rate = matched / n, valid / n
    embedded_rate = 0.0
    if rule["embedded"] and value_rate < 0.5:
        hits = 0
        key = "\x00embedded:" + rule["value_regex"]
        if key not in cache:
            # an embedded match must stand alone: not glued to other letters or digits
            cache[key] = _Pattern(r"(?<![A-Za-z0-9])(?:" + rule["value_regex"] + r")(?![A-Za-z0-9])", pattern.trusted)
        embedded = cache[key]
        for v, k in distinct.items():
            text = _DIGIT_SEP.sub("", v) if rule["normalise"] == "strip_separators" else v
            try:
                for m in embedded.finditer(text):
                    cand = _normalise(m.group(0), rule["normalise"])
                    if validator is None or validator(cand):
                        hits += k
                        break
            except TimeoutError:
                timed_out = True
        embedded_rate = hits / n
    return round(value_rate, 4), round(valid_rate, 4), round(embedded_rate, 4), timed_out


def combine(rule: dict, ruleset: dict, header_tokens: list[str], header: float, value_rate: float,
            valid_rate: float, embedded_rate: float, n: int, signals_enabled=(True, True, True)) -> tuple[float, list, list]:
    """Turn measured signals into a score. Shared by scans, impact preview and ablation."""
    w = ruleset["signal_weights"]
    use_h, use_v, use_c = signals_enabled
    h = header if use_h else 0.0
    v_sig = value_rate if use_v else 0.0
    c_sig = valid_rate if use_c else 0.0
    e_sig = embedded_rate if use_v else 0.0
    raw = w["header"] * h + w["value"] * v_sig + w["validator"] * c_sig
    notes: list[str] = []
    if e_sig >= 0.1 and e_sig > v_sig:
        emb = 0.8 * (w["header"] * h + (w["value"] + w["validator"]) * min(1.0, e_sig / 0.25))
        if emb > raw:
            raw = emb
            notes.append("embedded")
    if rule["requires_header"] and not h:
        raw = 0.0
        notes.append("requires_header")
    elif h and n and v_sig == 0 and c_sig == 0 and e_sig == 0 and (use_v or use_c):
        raw *= 0.5
        notes.append("values_contradict_header")
    negatives = [t for t in header_tokens if t in ruleset["negative_keywords"]]
    penalised: list[str] = []
    if negatives and not h and raw > 0:
        if not (rule["validator"] in CHECKSUM_VALIDATORS and valid_rate >= 0.9 and use_c):
            raw *= ruleset["negative_penalty"]
            penalised = negatives
    return round(rule["weight"] * raw, 4), notes, penalised


def score_rule(rule: dict, ruleset: dict, header_tokens: list[str], values: list[str], cache: dict,
               signals_enabled: tuple[bool, bool, bool] = (True, True, True), measured=None,
               counts: Counter | None = None) -> dict:
    header, hit, excluded = header_signal(rule, header_tokens)
    if measured is None:
        value_rate, valid_rate, embedded_rate, timed_out = value_signals(rule, values, cache, counts)
    else:
        value_rate, valid_rate, embedded_rate, timed_out = measured
    score, notes, penalised = combine(rule, ruleset, header_tokens, header, value_rate, valid_rate, embedded_rate,
                                      len(values), signals_enabled)
    return {
        "rule_id": rule["id"],
        "rule_name": rule["name"],
        "class": rule["class"],
        "score": score,
        "threshold": rule["threshold"],
        "signals": {"header": header, "value": value_rate, "validator": valid_rate, "embedded": embedded_rate},
        "header_keyword": hit if header else None,
        "header_excluded_by": excluded,
        "validator": rule["validator"],
        "negative_keywords": penalised,
        "notes": notes,
        "timed_out": timed_out,
    }


def band(score: float, ruleset: dict) -> str:
    if score >= ruleset["bands"]["high"]:
        return "HIGH"
    if score >= ruleset["bands"]["medium"]:
        return "MEDIUM"
    return "LOW"


def _pct(x: float) -> str:
    return f"{round(100 * x)}%"


def rationale(column: str, best: dict | None, n: int, sample_size: int) -> str:
    if best is None:
        return (f"No rule reached its threshold for '{column}' across {n:,} sampled non-null values. "
                "Raw values were not retained.")
    s = best["signals"]
    parts = []
    if s["header"]:
        parts.append(f"The header '{column}' matches the {best['rule_name']} rule (keyword '{best['header_keyword']}').")
    else:
        parts.append(f"The header '{column}' gives no hint; the evidence comes from values.")
    if "mixed" in best["notes"]:
        parts.append(f"The column mixes several identifier types: {best['mixed_parts']} of {n:,} sampled non-null values "
                     f"pass their validators, {_pct(s['validator'])} combined.")
    elif "embedded" in best["notes"]:
        parts.append(f"{_pct(s['embedded'])} of {n:,} sampled non-null values contain a "
                     f"{best['rule_name'].lower()} inside free text.")
    elif n:
        vlabel = VALIDATOR_LABELS.get(best["validator"], "validator")
        parts.append(f"{_pct(s['value'])} of {n:,} sampled non-null values match the pattern and "
                     f"{_pct(s['validator'])} pass the {vlabel}.")
    else:
        parts.append(f"All {sample_size:,} sampled values are empty, so only the header supports this.")
    if best["negative_keywords"]:
        parts.append(f"Score reduced because the name contains {', '.join(best['negative_keywords'])}.")
    parts.append(f"Confidence {best['score']:.2f} ({best['band']}).")
    parts.append("Raw values were not retained.")
    return " ".join(parts)


def classify_column(table: str, column: str, raw_values: list, ruleset: dict, salt: str,
                    total_rows: int | None = None, signals_enabled=(True, True, True),
                    cache: dict | None = None, measured: dict | None = None) -> dict:
    """Classify one column from an in-memory sample. Returns aggregates only.

    `measured` (optional, per column) memoises value signals per rule so ablation
    variants re-combine signals without re-measuring.
    """
    cache = {} if cache is None else cache
    prof = profile(raw_values, total_rows)
    values = [str(v).strip()[:MAX_VALUE_LEN] for v in raw_values if v is not None and str(v).strip() != ""]
    normalised, tokens = normalise_header(column)
    counts = Counter(values)
    scored = []
    for r in ruleset["rules"]:
        if not r["enabled"]:
            continue
        m = measured.get(r["id"]) if measured is not None else None
        if m is None:
            m = value_signals(r, values, cache, counts)
            if measured is not None:
                measured[r["id"]] = m
        scored.append(score_rule(r, ruleset, tokens, values, cache, signals_enabled, measured=m))
    prefix_share = constant_prefix_share(values)
    if prefix_share >= 0.8:
        # Values sharing one alphabetic prefix (ACC1234567, APT1234567) are system codes,
        # not government IDs, unless the header says otherwise.
        for s in scored:
            if s["rule_id"] in PREFIX_SENSITIVE_RULES and not s["signals"]["header"] and s["score"] > 0:
                s["score"] = round(s["score"] * ruleset["negative_penalty"], 4)
                s["notes"] = s["notes"] + ["constant_prefix"]
    best, scored = pick_best(scored, ruleset, prof)
    if best is None or best["score"] < ruleset["bands"]["medium"]:
        mixed = mixed_class_candidate(scored, ruleset)
        if mixed and (best is None or mixed["score"] > best["score"]):
            best = {**mixed, "band": band(mixed["score"], ruleset)}
    # Aggregate value signals for every rule (no raw values), so rule edits can be
    # re-scored later without re-reading the source.
    rule_signals = {
        s["rule_id"]: [s["signals"]["value"], s["signals"]["validator"], s["signals"]["embedded"],
                       _sig_hash(next(r for r in ruleset["rules"] if r["id"] == s["rule_id"]))]
        for s in scored if s["signals"]["value"] or s["signals"]["validator"] or s["signals"]["embedded"]
    }
    cls = best["class"] if best else NOT_PERSONAL
    rule_id = best["rule_id"] if best else None
    if best and "embedded" in best["notes"]:
        examples = list(dict.fromkeys(mask_free_text(v) for v in values if "[" in mask_free_text(v)))[:3]
    elif best:
        examples = masked_examples(values, rule_id)
    else:
        examples = list(dict.fromkeys(shape(v) for v in values))[:2]
    qi = QUASI_IDENTIFIER_RULES.get(rule_id or "")
    if not qi and set(tokens) & JOB_KEYWORDS and prof["inferred_type"] == "text":
        qi = "job"
    id_like = bool(set(tokens) & {"id", "no", "number", "key"}) and prof["distinct_pct"] >= 50
    fp = fingerprint(values, salt) if (best or id_like) else []
    alternatives = [
        {"rule_id": s["rule_id"], "class": s["class"], "score": s["score"]}
        for s in scored[1:4] if s["score"] > 0 and s["class"] != cls
    ]
    return {
        "table": table,
        "column": column,
        "normalised": normalised,
        "class": cls,
        "confidence": best["score"] if best else (round(scored[0]["score"], 4) if scored else 0.0),
        "band": best["band"] if best else "NONE",
        "rule_id": rule_id,
        "rule_name": best["rule_name"] if best else None,
        "signals": best["signals"] if best else (scored[0]["signals"] if scored else {"header": 0, "value": 0, "validator": 0, "embedded": 0}),
        "validator": best["validator"] if best else None,
        "header_keyword": best["header_keyword"] if best else None,
        "negative_keywords": best["negative_keywords"] if best else [],
        "notes": best["notes"] if best else [],
        "alternatives": alternatives,
        "masked_examples": examples,
        "rationale": rationale(column, best, len(values), prof["sample_size"]),
        "profile": prof,
        "quasi_identifier": qi,
        "id_like": id_like,
        "fingerprint": fp,
        "rule_signals": rule_signals,
        "constant_prefix": prefix_share >= 0.8,
    }


def _sig_hash(rule: dict) -> str:
    import hashlib
    return hashlib.sha256(value_signature(rule).encode()).hexdigest()[:12]


def pick_best(scored: list[dict], ruleset: dict, prof: dict) -> tuple[dict | None, list[dict]]:
    scored = sorted(scored, key=lambda r: (-r["score"], r["rule_id"]))
    # timestamps are never identity candidates without a header match
    if prof["inferred_type"] == "datetime":
        scored = [s if s["class"] != "IDENTITY" or s["signals"]["header"] else {**s, "score": 0.0} for s in scored]
        scored.sort(key=lambda r: (-r["score"], r["rule_id"]))
    best = scored[0] if scored and scored[0]["score"] > 0 and scored[0]["score"] >= scored[0]["threshold"] else None
    if best:
        best = {**best, "band": band(best["score"], ruleset)}
    return best, scored


MIXED_CLASSES = ("GOVERNMENT_ID", "FINANCIAL")


def mixed_class_candidate(scored: list[dict], ruleset: dict) -> dict | None:
    """One column holding several ID types (e.g. an 'ID proof number' with DL, voter ID and
    passport values). No single rule covers enough rows, but their validated shares add up.

    Only checksum/structure-validated shares count, the constant-prefix and negative-keyword
    penalties still apply, and at least two rules must each contribute >= 10%.
    """
    w = ruleset["signal_weights"]
    best = None
    for cls in MIXED_CLASSES:
        parts = [s for s in scored if s["class"] == cls and s["signals"]["validator"] >= 0.1
                 and "constant_prefix" not in s["notes"] and "requires_header" not in s["notes"]]
        if len(parts) < 2:
            continue
        v = min(1.0, sum(s["signals"]["value"] for s in parts))
        c = min(1.0, sum(s["signals"]["validator"] for s in parts))
        # a negative keyword (e.g. "id") is only overridden by near-complete validated coverage
        if c < (0.9 if any(s["negative_keywords"] for s in parts) else 0.8):
            continue
        header = max(s["signals"]["header"] for s in parts)
        score = round(0.9 * (w["header"] * header + w["value"] * v + w["validator"] * c), 4)
        if score >= 0.35 and (best is None or score > best["score"]):
            names = ", ".join(f"{s['rule_name']} {round(100 * s['signals']['validator'])}%" for s in sorted(parts, key=lambda s: -s["signals"]["validator"]))
            best = {"rule_id": f"mixed_{cls.lower()}", "rule_name": f"Mixed {cls.replace('_', ' ').lower()} types",
                    "class": cls, "score": score, "threshold": 0.35,
                    "signals": {"header": header, "value": round(v, 4), "validator": round(c, 4), "embedded": 0.0},
                    "header_keyword": None, "header_excluded_by": None, "validator": "multiple", "negative_keywords": [],
                    "notes": ["mixed"], "timed_out": False, "mixed_parts": names}
    return best


def rule_hashes(ruleset: dict) -> dict[str, str]:
    return {r["id"]: _sig_hash(r) for r in ruleset["rules"]}


def rescore(column: str, prof: dict, rule_signals: dict, ruleset: dict, scanned_hashes: dict[str, str],
            constant_prefix: bool = False) -> dict:
    """Re-score a stored column against a (possibly edited) rule set from aggregates only.

    `scanned_hashes` are the value-signal hashes of the rules used at scan time. A rule
    whose pattern, normaliser or validator changed (or a new rule) cannot be re-measured
    without the source: its value signals count as 0 and the result is flagged approximate.
    """
    _, tokens = normalise_header(column)
    approximate = False
    scored = []
    for r in ruleset["rules"]:
        if not r["enabled"]:
            continue
        stored = rule_signals.get(r["id"])
        if scanned_hashes.get(r["id"]) != _sig_hash(r):
            approximate = approximate or bool(r["value_regex"])
            stored = None
        measured = (stored[0], stored[1], stored[2], False) if stored else (0.0, 0.0, 0.0, False)
        s = score_rule(r, ruleset, tokens, [""] * prof.get("non_null", 0), {}, measured=measured)
        if constant_prefix and r["id"] in PREFIX_SENSITIVE_RULES and not s["signals"]["header"]:
            s["score"] = round(s["score"] * ruleset["negative_penalty"], 4)
        scored.append(s)
    best, _ = pick_best(scored, ruleset, prof)
    return {"class": best["class"] if best else NOT_PERSONAL, "confidence": best["score"] if best else 0.0,
            "band": best["band"] if best else "NONE", "rule_id": best["rule_id"] if best else None,
            "approximate": approximate}


# ---------------------------------------------------------------- table-level aggregates

def _qi_value(kind: str, v: str, generalise: bool) -> str:
    v = v.strip().lower()
    if not generalise:
        return v
    if kind == "dob":
        d = parse_date(v)
        return str(d.year // 5 * 5) if d else v
    if kind == "age":
        return str(int(v) // 5 * 5) if v.isdigit() else v
    if kind == "pin":
        return v[:3]
    return v


def k_anonymity(rows: list[dict], qi_columns: dict[str, str]) -> dict | None:
    """k-anonymity estimate on the in-memory sample; returns aggregates only."""
    if len(qi_columns) < 2 or not rows:
        return None
    out = {"quasi_identifiers": sorted(qi_columns), "sample_rows": len(rows)}
    for label, generalise in (("exact", False), ("generalised", True)):
        keys = Counter(
            tuple(_qi_value(kind, str(r.get(col) or ""), generalise) for col, kind in sorted(qi_columns.items()))
            for r in rows
        )
        unique_rows = sum(c for c in keys.values() if c == 1)
        out[label] = {
            "min_k": min(keys.values()),
            "unique_pct": round(100 * unique_rows / len(rows), 1),
            "groups": len(keys),
            "rows_k_lt_5_pct": round(100 * sum(c for c in keys.values() if c < 5) / len(rows), 1),
        }
    return out


RECORD_DATE_KEYWORDS = {"created", "signup", "registered", "joined", "opened", "onboarded", "date", "joining"}


def record_age_histogram(rows: list[dict], columns: list[str], today=None) -> dict | None:
    """Histogram of record ages (in days) from the first creation-like date column."""
    today = today or datetime.now().date()
    for col in columns:
        _, tokens = normalise_header(col)
        if not set(tokens) & RECORD_DATE_KEYWORDS or set(tokens) & {"birth", "dob", "expiry", "due"}:
            continue
        ages = []
        for r in rows:
            v = str(r.get(col) or "")[:10]
            d = parse_date(v)
            if d:
                ages.append(max(0, (today - d).days))
        if len(ages) >= max(10, len(rows) // 2):
            edges = [30, 90, 180, 365, 730, 1095, 1825, 2555, 3650, 10**6]
            hist = [0] * len(edges)
            for a in ages:
                for i, e in enumerate(edges):
                    if a <= e:
                        hist[i] += 1
                        break
            return {"column": col, "sampled": len(ages), "edges_days": edges, "counts": hist,
                    "oldest_days": max(ages), "median_days": sorted(ages)[len(ages) // 2]}
    return None
