import sqlite3
import tempfile
from pathlib import Path

import pytest

from privacytwin import ingest
from privacytwin.gaps import effective, gaps_for, is_documented, parse_retention, suggest
from privacytwin.rules import bump, content_hash, default_ruleset, export, parse_import, validate_rule, validate_ruleset


# ------------------------------------------------------------------ ingest

def test_csv_encoding_fallback_and_delimiter():
    data = "naam;city\nJosé Iyer;Pune\nAna Rao;Delhi\n".encode("latin-1")
    r = ingest.read_csv(data, "x.csv", 1000, "head")
    assert r.delimiter == ";" and r.encoding in ("cp1252", "latin-1")
    assert r.tables[0].rows[0][0] == "José Iyer"
    assert any("not valid UTF-8" in n for n in r.notes)


def test_csv_bom_tabs_duplicates_and_ragged_rows():
    data = "﻿email\temail\t\nA@b.co\tx\ny\n".encode("utf-8")
    r = ingest.read_csv(data, "t.tsv", 1000, "head")
    assert r.tables[0].headers == ["email", "email_2", "column_3"]
    assert r.tables[0].rows[1] == ["y", "", ""]
    assert any("Duplicate header" in n for n in r.notes) and any("padded" in n for n in r.notes)


def test_csv_limits_and_bad_inputs():
    with pytest.raises(ValueError, match="20 MB"):
        ingest.read_csv(b"a\n" + b"x\n" * (11 * 1024 * 1024), "big.csv", 1000, "head")
    with pytest.raises(ValueError, match="empty"):
        ingest.read_csv(b"  \n", "e.csv", 1000, "head")
    with pytest.raises(ValueError):
        ingest.detect_kind("x.exe", b"MZ")
    with pytest.raises(ValueError, match="not a SQLite"):
        ingest.detect_kind("x.db", b"hello")
    with pytest.raises(ValueError):
        ingest.check_options(123, "head")


@pytest.mark.parametrize("strategy", ingest.STRATEGIES)
def test_sampling_strategies_are_bounded(strategy):
    rows = [[i] for i in range(5000)]
    s = ingest.sample_rows(rows, 500, strategy)
    assert len(s) == 500
    if strategy == "stratified":
        assert min(r[0] for r in s) < 500 and max(r[0] for r in s) > 4500


def _sqlite_bytes() -> bytes:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.sqlite"
        c = sqlite3.connect(p)
        c.execute('CREATE TABLE "we""ird" (email TEXT, n INT)')
        c.executemany('INSERT INTO "we""ird" VALUES(?,?)', [(f"u{i}@x.com", i) for i in range(50)])
        c.commit()
        c.close()
        return p.read_bytes()


def test_sqlite_read_only_self_test_and_quoting():
    before = set(Path(tempfile.gettempdir()).glob("pt-*.sqlite"))
    r = ingest.read_sqlite_bytes(_sqlite_bytes(), 1000, "head")
    assert r.read_only_verified and "refused" in r.read_only_detail
    assert r.tables[0].name == 'we"ird' and r.tables[0].total_rows == 50
    assert r.transient_copy and set(Path(tempfile.gettempdir()).glob("pt-*.sqlite")) == before


def test_sqlite_selftest_detects_writable_connection():
    c = sqlite3.connect(":memory:", isolation_level=None)
    ok, detail = ingest.sqlite_readonly_selftest(c)
    assert not ok and "not refused" in detail


# ------------------------------------------------------------------ rules

def test_default_rules_valid_and_hash_stable():
    rs = default_ruleset()
    assert content_hash(rs) == content_hash(default_ruleset())
    assert content_hash(rs) != content_hash({**rs, "negative_penalty": 0.5})
    assert content_hash(rs) == content_hash({**rs, "version": "9.9.9"})


def test_rule_validation_errors():
    with pytest.raises(ValueError, match="class"):
        validate_rule({"id": "x", "name": "X", "class": "SECRET", "header_keywords": ["a"]})
    with pytest.raises(ValueError, match="value_regex"):
        validate_rule({"id": "x", "name": "X", "class": "CONTACT", "value_regex": "("})
    with pytest.raises(ValueError, match="validator"):
        validate_rule({"id": "x", "name": "X", "class": "CONTACT", "header_keywords": ["a"], "validator": "nope"})
    with pytest.raises(ValueError, match="add up"):
        validate_ruleset({**default_ruleset(), "signal_weights": {"header": 0.5, "value": 0.5, "validator": 0.5}})


def test_import_export_roundtrip_yaml_and_json():
    rs = default_ruleset()
    assert parse_import(export(rs, "yaml")) == rs
    assert parse_import(export(rs, "json")) == rs
    with pytest.raises(ValueError):
        parse_import("rules: [unclosed")


def test_semver_bump():
    assert bump("1.2.3") == "1.3.0" and bump("1.2.3", "major") == "2.0.0" and bump("1.2.3", "patch") == "1.2.4"


# ------------------------------------------------------------------ gaps

def test_parse_retention():
    assert parse_retention("7 years") == 2555
    assert parse_retention("90 days") == 90
    assert parse_retention("18 months") == 540
    assert parse_retention("forever") is None and parse_retention("") is None


def test_gap_engine_severities():
    meta = effective({}, "s", "t", "s/t/c")
    sev = {g["field"]: g["severity"] for g in gaps_for(meta, 3650)}
    assert sev == {"purpose": "High", "retention": "High", "owner": "Medium", "legal_basis": "Medium"}
    full = effective({"table:s/t": {"purpose": "p", "retention": "20 years", "owner": "o", "legal_basis": "l"}}, "s", "t", "s/t/c")
    gaps = gaps_for(full, 3650)
    assert [g["severity"] for g in gaps] == ["Low"] and "for review" in gaps[0]["message"]
    assert is_documented(full)


def test_column_overrides_table_field_by_field():
    meta = {"table:s/t": {"purpose": "Table purpose", "owner": "Team"}, "col:s/t/c": {"purpose": "Column purpose"}}
    e = effective(meta, "s", "t", "s/t/c")
    assert e["purpose"] == {"value": "Column purpose", "origin": "column"}
    assert e["owner"] == {"value": "Team", "origin": "table"}


def test_unreadable_retention_is_a_high_gap():
    e = effective({"table:s/t": {"retention": "as long as needed"}}, "s", "t", "s/t/c")
    assert any(g["severity"] == "High" and "could not be read" in g["message"] for g in gaps_for(e, 3650))


def test_suggestions_never_include_legal_basis():
    for table in ("payments", "kyc_documents", "employees", "random_table"):
        assert "legal_basis" not in suggest(table, "src")
    assert suggest("payments", "src")["purpose"] == "Billing & payments"
