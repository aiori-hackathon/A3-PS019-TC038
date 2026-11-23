import io
import json
import zipfile

from privacytwin.store import GENESIS, verify_chain


def _entries(n=4):
    from privacytwin.store import audit_hash
    prev, out = GENESIS, []
    for i in range(1, n + 1):
        body = {"seq": i, "ts": f"2026-01-0{i}T00:00:00+00:00", "actor": "a", "action": "review.confirmed",
                "target": f"PT-0000{i}", "payload": {"note": "x"}}
        h = audit_hash(prev, body)
        out.append(body | {"prev_hash": prev, "hash": h})
        prev = h
    return out


def test_chain_verifies():
    r = verify_chain(_entries())
    assert r["ok"] and r["entries"] == 4


def test_chain_detects_edit_deletion_and_reorder():
    edited = _entries()
    edited[1]["payload"]["note"] = "changed"
    assert verify_chain(edited) == {**verify_chain(edited), "ok": False, "broken_at": 2}
    deleted = _entries()
    del deleted[1]
    r = verify_chain(deleted)
    assert not r["ok"] and r["broken_at"] == 3
    swapped = _entries()
    swapped[0], swapped[1] = swapped[1], swapped[0]
    assert not verify_chain(swapped)["ok"]


def test_api_audit_chain_detects_database_tampering(client, app):
    client.scan_csv("people.csv", b"email,mobile\na.b@example.com,9876543210\nc.d@example.com,9123456780\n")
    keys = [r["key"] for r in client.get("/api/inventory").json()["rows"]]
    client.post("/api/reviews", json={"keys": keys[:1], "status": "confirmed"})
    client.post("/api/reviews", json={"keys": keys[1:], "status": "rejected", "note": "test data"})
    r = client.get("/api/audit/verify").json()
    assert r["ok"] and r["entries"] == 3
    store = app.state.twin.store
    with store.connect() as c:
        c.execute("DROP TRIGGER audit_no_update")
        c.execute("UPDATE audit SET payload='{\"note\":\"forged\"}' WHERE seq=2")
    bad = client.get("/api/audit/verify").json()
    assert not bad["ok"] and bad["broken_at"] == 2 and bad["reason"] == "entry content does not match its hash"


def test_audit_log_is_append_only(demo, demo_app):
    import sqlite3
    import pytest
    store = demo_app.state.twin.store
    with store.connect() as c, pytest.raises(sqlite3.DatabaseError):
        c.execute("UPDATE audit SET actor='x'")


def test_evidence_pack_roundtrip_and_tamper(demo):
    r = demo.post("/api/evidence")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    pack = r.content
    z = zipfile.ZipFile(io.BytesIO(pack))
    names = set(z.namelist())
    for required in ("inventory.csv", "inventory.json", "gaps.csv", "reviews.json", "audit_chain.json", "evaluation.json",
                     "ruleset.yaml", "data_handling_receipts.json", "scan_diff.json", "summary.html", "manifest.json"):
        assert required in names
    manifest = json.loads(z.read("manifest.json"))
    assert manifest["disclaimer"] == "Technical evidence for human review. Not a legal determination."
    assert "Not a legal determination" in z.read("summary.html").decode()
    ok = demo.post("/api/evidence/verify", files={"file": ("p.zip", pack, "application/zip")}).json()
    assert ok["ok"] and ok["anchored_in_this_workspace"] and all(f["ok"] for f in ok["files"])

    def rebuild(change):
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as w:
            for n in z.namelist():
                data = z.read(n)
                res = change(n, data)
                if res is not None:
                    w.writestr(n, res)
            if change("__extra__", b"") is not None:
                w.writestr("extra.txt", b"surprise")
        return out.getvalue()

    tampered = rebuild(lambda n, d: d.replace(b"CONTACT", b"CONTACX") if n == "inventory.csv" else (None if n == "__extra__" else d))
    bad = demo.post("/api/evidence/verify", files={"file": ("p.zip", tampered, "application/zip")}).json()
    assert not bad["ok"]
    assert [f["path"] for f in bad["files"] if not f["ok"]] == ["inventory.csv"]
    missing = rebuild(lambda n, d: None if n in ("gaps.csv", "__extra__") else d)
    r2 = demo.post("/api/evidence/verify", files={"file": ("p.zip", missing, "application/zip")}).json()
    assert any(f["path"] == "gaps.csv" and f["reason"] == "missing from the pack" for f in r2["files"])
    extra = rebuild(lambda n, d: b"" if n == "__extra__" else d)
    r3 = demo.post("/api/evidence/verify", files={"file": ("p.zip", extra, "application/zip")}).json()
    assert not r3["ok"] and any(f["path"] == "extra.txt" for f in r3["files"])
    assert demo.post("/api/evidence/verify", files={"file": ("p.zip", b"nope", "application/zip")}).status_code == 400


def test_csv_exports_neutralise_formulas():
    from privacytwin.evidence import _safe_cell
    assert _safe_cell("=1+1") == "'=1+1" and _safe_cell("+91-XXXX") == "'+91-XXXX" and _safe_cell("ok") == "ok"
