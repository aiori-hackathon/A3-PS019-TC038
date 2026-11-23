"""Rule-set loading, validation, versioning and import/export."""
from __future__ import annotations

import copy
import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from .validators import VALIDATORS

CLASSES = ["IDENTITY", "CONTACT", "GOVERNMENT_ID", "FINANCIAL", "LOCATION"]
NOT_PERSONAL = "NOT_PERSONAL"
ALL_CLASSES = CLASSES + [NOT_PERSONAL]

# Sensitivity of each class, used to rank the review queue and the posture score.
CLASS_SENSITIVITY = {"GOVERNMENT_ID": 1.0, "FINANCIAL": 0.9, "IDENTITY": 0.7, "CONTACT": 0.6, "LOCATION": 0.5, NOT_PERSONAL: 0.0}

NORMALISERS = ("none", "strip_separators", "upper")
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
RULE_ID = re.compile(r"^[a-z][a-z0-9_]{0,48}$")
DEFAULT_PATH = Path(__file__).with_name("default_rules.yaml")

RULE_DEFAULTS = {
    "header_exclude": [],
    "normalise": "none",
    "validator": "",
    "threshold": 0.35,
    "weight": 1.0,
    "requires_header": False,
    "embedded": False,
    "enabled": True,
}


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256(value: Any) -> str:
    data = value if isinstance(value, (bytes, bytearray)) else canonical(value).encode()
    return hashlib.sha256(data).hexdigest()


def _keywords(value: Any, field: str, rule_id: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(k, str) or not k.strip() or len(k) > 60 for k in value):
        raise ValueError(f"Rule {rule_id}: {field} must be a list of short keywords")
    if len(value) > 80:
        raise ValueError(f"Rule {rule_id}: at most 80 {field}")
    return [k.strip().lower() for k in value]


def validate_rule(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("Each rule must be an object")
    rule = {**RULE_DEFAULTS, **raw}
    allowed = set(RULE_DEFAULTS) | {"id", "name", "class", "header_keywords", "value_regex"}
    unknown = set(rule) - allowed
    if unknown:
        raise ValueError(f"Unknown rule properties: {', '.join(sorted(unknown))}")
    rid = rule.get("id")
    if not isinstance(rid, str) or not RULE_ID.match(rid):
        raise ValueError("Rule IDs must be lowercase identifiers (letters, digits, underscores)")
    if not isinstance(rule.get("name"), str) or not 1 <= len(rule["name"]) <= 80:
        raise ValueError(f"Rule {rid}: name must be 1-80 characters")
    if rule.get("class") not in CLASSES:
        raise ValueError(f"Rule {rid}: class must be one of {', '.join(CLASSES)}")
    rule["header_keywords"] = _keywords(rule.get("header_keywords", []), "header_keywords", rid)
    rule["header_exclude"] = _keywords(rule["header_exclude"], "header_exclude", rid)
    regex = rule.get("value_regex", "")
    if not isinstance(regex, str) or len(regex) > 300:
        raise ValueError(f"Rule {rid}: value_regex must be text up to 300 characters")
    try:
        re.compile(regex)
    except re.error as exc:
        raise ValueError(f"Rule {rid}: invalid value_regex ({exc})") from exc
    if not regex and not rule["header_keywords"]:
        raise ValueError(f"Rule {rid}: needs header keywords or a value pattern")
    if rule["validator"] and rule["validator"] not in VALIDATORS:
        raise ValueError(f"Rule {rid}: unknown validator '{rule['validator']}'")
    if rule["normalise"] not in NORMALISERS:
        raise ValueError(f"Rule {rid}: normalise must be one of {', '.join(NORMALISERS)}")
    for key, lo, hi in (("threshold", 0.05, 1.0), ("weight", 0.05, 1.0)):
        if type(rule[key]) not in (int, float) or not lo <= rule[key] <= hi:
            raise ValueError(f"Rule {rid}: {key} must be between {lo} and {hi}")
        rule[key] = float(rule[key])
    for key in ("requires_header", "embedded", "enabled"):
        if type(rule[key]) is not bool:
            raise ValueError(f"Rule {rid}: {key} must be true or false")
    return {k: rule[k] for k in sorted(allowed)}


def validate_ruleset(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("A rule set must be an object")
    allowed = {"name", "version", "signal_weights", "bands", "negative_penalty", "negative_keywords", "rules"}
    unknown = set(raw) - allowed
    if unknown:
        raise ValueError(f"Unknown rule-set properties: {', '.join(sorted(unknown))}")
    name = raw.get("name", "Custom rules")
    version = str(raw.get("version", "1.0.0"))
    if not SEMVER.match(version):
        raise ValueError("Rule-set version must be semantic (for example 1.2.0)")
    weights = raw.get("signal_weights", {})
    if set(weights) != {"header", "value", "validator"} or any(type(v) not in (int, float) or not 0 <= v <= 1 for v in weights.values()):
        raise ValueError("signal_weights needs header, value and validator between 0 and 1")
    if abs(sum(weights.values()) - 1) > 1e-6:
        raise ValueError("signal_weights must add up to 1")
    bands = raw.get("bands", {})
    if set(bands) != {"high", "medium"} or not 0 < bands["medium"] < bands["high"] <= 1:
        raise ValueError("bands needs medium < high, both between 0 and 1")
    penalty = raw.get("negative_penalty", 0.4)
    if type(penalty) not in (int, float) or not 0 <= penalty <= 1:
        raise ValueError("negative_penalty must be between 0 and 1")
    rules = raw.get("rules")
    if not isinstance(rules, list) or not 1 <= len(rules) <= 100:
        raise ValueError("A rule set needs 1-100 rules")
    cleaned = [validate_rule(r) for r in rules]
    ids = [r["id"] for r in cleaned]
    if len(set(ids)) != len(ids):
        raise ValueError("Rule IDs must be unique")
    return {
        "name": str(name)[:80],
        "version": version,
        "signal_weights": {k: float(v) for k, v in weights.items()},
        "bands": {k: float(v) for k, v in bands.items()},
        "negative_penalty": float(penalty),
        "negative_keywords": _keywords(raw.get("negative_keywords", []), "negative_keywords", "set"),
        "rules": cleaned,
    }


def content_hash(ruleset: dict) -> str:
    """Hash of everything that affects detection (name and version excluded)."""
    body = {k: v for k, v in ruleset.items() if k not in ("name", "version")}
    return sha256(body)


@lru_cache(maxsize=1)
def _default() -> dict:
    return validate_ruleset(yaml.safe_load(DEFAULT_PATH.read_text(encoding="utf-8")))


def default_ruleset() -> dict:
    return copy.deepcopy(_default())


def bump(version: str, part: str = "minor") -> str:
    major, minor, patch = (int(x) for x in version.split("."))
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    return f"{major}.{minor + 1}.0"


def parse_import(text: str) -> dict:
    """Accept YAML or JSON (JSON is valid YAML)."""
    if len(text) > 500_000:
        raise ValueError("Rule file is too large (limit 500 KB)")
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError(f"Could not parse rule file: {exc}") from exc
    return validate_ruleset(data)


def export(ruleset: dict, fmt: str = "yaml") -> str:
    if fmt == "json":
        return json.dumps(ruleset, indent=2, ensure_ascii=False)
    return yaml.safe_dump(ruleset, sort_keys=False, allow_unicode=True)
