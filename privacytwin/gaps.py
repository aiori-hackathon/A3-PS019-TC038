"""Metadata declarations, gap engine and labelled suggestions."""
from __future__ import annotations

import re

METADATA_FIELDS = ("purpose", "retention", "owner", "legal_basis", "system_of_record")
FIELD_LABELS = {"purpose": "Purpose", "retention": "Retention", "owner": "Owner", "legal_basis": "Legal basis (declared)",
                "system_of_record": "System of record"}
SEVERITY_ORDER = {"High": 3, "Medium": 2, "Low": 1}
GAP_RULES = {
    "purpose": ("High", "No purpose declared"),
    "retention": ("High", "No retention period declared"),
    "owner": ("Medium", "No owner declared"),
    "legal_basis": ("Medium", "No legal basis declared"),
}

_UNITS = {"d": 1, "day": 1, "days": 1, "w": 7, "week": 7, "weeks": 7, "m": 30, "mo": 30, "month": 30, "months": 30,
          "y": 365, "yr": 365, "yrs": 365, "year": 365, "years": 365}


def parse_retention(text: str) -> int | None:
    """'7 years' -> 2555; '90 days' -> 90; '18 months' -> 540. Returns None when not understood."""
    if not text:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)\s*([a-zA-Z]+)", text.strip())
    if not m:
        return None
    unit = _UNITS.get(m.group(2).lower())
    if unit is None:
        return None
    return int(round(float(m.group(1)) * unit))


def table_target(source_id: str, table: str) -> str:
    return f"table:{source_id}/{table}"


def column_target(column_key: str) -> str:
    return f"col:{column_key}"


def effective(meta_by_target: dict[str, dict], source_id: str, table: str, column_key: str) -> dict:
    """Column declarations override table declarations, field by field."""
    col = meta_by_target.get(column_target(column_key), {})
    tab = meta_by_target.get(table_target(source_id, table), {})
    out = {}
    for f in METADATA_FIELDS:
        if col.get(f):
            out[f] = {"value": col[f], "origin": "column"}
        elif tab.get(f):
            out[f] = {"value": tab[f], "origin": "table"}
        else:
            out[f] = {"value": "", "origin": None}
    out["retention_days"] = parse_retention(out["retention"]["value"])
    return out


def gaps_for(meta: dict, max_retention_days: int) -> list[dict]:
    gaps = []
    for field, (severity, text) in GAP_RULES.items():
        if not meta[field]["value"]:
            gaps.append({"field": field, "severity": severity, "message": text})
    if meta["retention"]["value"] and meta["retention_days"] is None:
        gaps.append({"field": "retention", "severity": "High",
                     "message": f"Retention '{meta['retention']['value']}' could not be read as a duration"})
    elif meta["retention_days"] and meta["retention_days"] > max_retention_days:
        gaps.append({"field": "retention", "severity": "Low",
                     "message": f"Declared retention ({meta['retention']['value']}) is longer than the workspace "
                                f"maximum of {max_retention_days // 365} years (for review)"})
    return gaps


def is_documented(meta: dict) -> bool:
    return all(meta[f]["value"] for f in ("purpose", "retention", "owner", "legal_basis")) and meta["retention_days"] is not None


# ---------------------------------------------------------------- suggestions

TABLE_HINTS = [
    (r"visitor|gate|guest|entry_pass", "Visitor & site security", "Security officer", "1 year"),
    (r"personnel|officer|scientist|service_record", "Personnel administration", "Administration (HR)", "Service period + 7 years"),
    (r"vendor|supplier|procure|purchase|tender", "Vendor management & procurement", "Materials management", "8 years"),
    (r"ta_da|claim|travel|tour", "Travel & reimbursement claims", "Accounts section", "8 years"),
    (r"access_log|badge|swipe|biometric", "Physical access control", "Security officer", "1 year"),
    (r"payment|billing|invoice|txn|transaction|card", "Billing & payments", "Finance team", "8 years"),
    (r"kyc|verification|identity|onboard", "Customer identity verification (KYC)", "Compliance team", "5 years"),
    (r"support|ticket|helpdesk|complaint", "Customer support", "Customer support team", "2 years"),
    (r"marketing|lead|campaign|newsletter|prospect", "Marketing outreach", "Marketing team", "1 year"),
    (r"employee|staff|hr|payroll|salary", "Employment administration", "HR team", "7 years"),
    (r"customer|user|account|member|client|profile", "Account management", "Customer operations", "3 years"),
    (r"order|shipment|delivery|cart", "Order fulfilment", "Operations team", "3 years"),
    (r"log|audit|session|login|access", "Security & audit logging", "Security team", "1 year"),
    (r"loan|credit|emi|underwriting", "Credit assessment", "Risk team", "8 years"),
]


def suggest(table: str, source_name: str) -> dict:
    """Labelled suggestions. Never stored until a person accepts them. No legal-basis suggestions."""
    name = table.lower()
    for pattern, purpose, owner, retention in TABLE_HINTS:
        if re.search(pattern, name):
            return {
                "purpose": purpose,
                "owner": owner,
                "retention": retention,
                "system_of_record": source_name,
                "basis": f"Table name '{table}' resembles '{pattern.split('|')[0]}' tables. Confirm with the data owner.",
            }
    return {"system_of_record": source_name, "basis": "Only the system of record could be inferred from the source name."}
