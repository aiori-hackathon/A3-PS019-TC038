"""Acceptance test: no raw personal value is persisted in the database or any export.

Scans the demo company and an uploaded CSV/SQLite with known synthetic values, then
searches the SQLite file (after a WAL checkpoint), the evidence pack contents, the
workspace export, CSV/JSON views and the evaluation export for any raw value.
"""
import io
import json
import sqlite3
import zipfile

from privacytwin.demo import _tables
from privacytwin.synth import Gen
from tests.conftest import Client

PERSONAL_COLUMNS = {
    "customers": ["full_name", "email", "mobile", "dob", "pan", "address", "pincode"],
    "kyc_documents": ["pan_number", "passport_no", "voter_id", "verified_by", "dl_number"],
    "payments": ["card_number", "bank_account", "upi_id"],
    "support_tickets": ["message", "agent_name", "aadhaar_no"],
    "marketing_leads": ["lead_name", "email", "whatsapp_no"],
    "employees": ["emp_name", "work_email", "mobile", "salary_account", "home_address", "pin_code"],
}


def _raw_values() -> set[str]:
    raw = set()
    for version in (1, 2, 3):
        for table, (headers, rows) in _tables(version).items():
            for col in PERSONAL_COLUMNS.get(table, []):
                if col not in headers:
                    continue
                i = headers.index(col)
                for r in rows:
                    v = str(r[i]).strip()
                    if len(v) >= 6:
                        raw.add(v)
                        digits = "".join(ch for ch in v if ch.isdigit())
                        if len(digits) >= 9 and not any(ch.isalpha() for ch in v):
                            raw.add(digits)
    return raw


def _upload_values():
    g = Gen(99)
    rows = [(g.name(), g.email(), g.mobile("plain"), g.aadhaar(), g.card(spaced=False), g.address()) for _ in range(60)]
    csv_bytes = ("name,email,mobile,aadhaar,card,address\n" + "\n".join(",".join(f'"{x}"' for x in r) for r in rows)).encode()
    return csv_bytes, {v for r in rows for v in r}


def _assert_clean(blob: str, raw: set[str], where: str):
    """Text values are searched as substrings. Purely numeric values (PIN codes, phone and
    account numbers) are matched at digit boundaries, so a 6-digit PIN is not reported
    inside an unrelated 10-digit hash integer."""
    import re
    digits = {m.group(0) for m in re.finditer(r"\d{6,19}", blob)}
    leaks = [v for v in raw if (v in digits) if v.isdigit()] + [v for v in raw if not v.isdigit() and v in blob]
    assert not leaks, f"{len(leaks)} raw values found in {where}, e.g. {sorted(leaks)[:3]}"


def test_no_raw_values_anywhere(tmp_path):
    from privacytwin.api import create_app
    db = tmp_path / "pt.sqlite3"
    app = create_app(str(db))
    c = Client(app, "r" * 40)
    assert c.post("/api/demo", json={}).json()["loaded"]
    csv_bytes, upload_raw = _upload_values()
    c.scan_csv("upload.csv", csv_bytes)
    raw = _raw_values() | upload_raw
    assert len(raw) > 2000

    exports = {
        "evidence pack": None,
        "workspace export": c.get("/api/workspace/export").text,
        "inventory API": c.get("/api/inventory").text,
        "review queue API": c.get("/api/review-queue").text,
        "overview API": c.get("/api/overview").text,
        "timeline API": c.get("/api/timeline").text,
        "lineage API": c.get("/api/lineage").text,
        "audit API": c.get("/api/audit").text,
        "sources API": c.get("/api/sources").text,
        "metadata API": c.get("/api/metadata").text,
        "evaluation export": c.get("/api/evaluation/export", params={"format": "csv"}).text,
    }
    pack = c.post("/api/evidence").content
    with zipfile.ZipFile(io.BytesIO(pack)) as z:
        exports["evidence pack"] = "\n".join(z.read(n).decode("utf-8", "replace") for n in z.namelist())
    for where, blob in exports.items():
        _assert_clean(blob, raw, where)

    with sqlite3.connect(db) as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        dump = "\n".join(conn.iterdump())
    _assert_clean(dump, raw, "application database")
    for f in tmp_path.iterdir():
        if f.is_file():
            _assert_clean(f.read_bytes().decode("latin-1"), raw, f"file {f.name}")


def test_finding_detail_has_masked_examples_only(demo):
    rows = demo.get("/api/inventory").json()["rows"]
    email = next(r for r in rows if r["table"] == "customers" and r["column"] == "email")
    detail = demo.get(f"/api/findings/{email['pt_id']}").json()
    assert all("****@" in e for e in detail["finding"]["masked_examples"])
    assert "fingerprint" not in json.dumps(detail) and "rule_signals" not in json.dumps(detail)
