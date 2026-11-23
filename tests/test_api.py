import json

from tests.conftest import ORIGIN, Client

PEOPLE = (b"customer_name,email,mobile_no,order_id,city\n"
          b"Rahul Sharma,rahul.s@example.com,9876543210,6123456789,Pune\n"
          b"Priya Iyer,priya.i@example.com,+91 91234 56780,7123456789,Mumbai\n"
          b"Amit Patel,amit.p@example.com,09812345678,8123456789,Delhi\n") * 5


def test_health_and_security_headers(client):
    r = client.c.get("/health")
    assert r.json()["status"] == "ok"
    r = client.get("/api/overview")
    for h in ("content-security-policy", "x-content-type-options", "referrer-policy", "x-frame-options"):
        assert h in r.headers
    assert r.headers["x-content-type-options"] == "nosniff"


def test_workspace_key_required_and_validated(app):
    from fastapi.testclient import TestClient
    c = TestClient(app)
    assert c.get("/api/overview").status_code == 401
    assert c.get("/api/overview", headers={"X-Workspace-Key": "short"}).status_code == 401


def test_csrf_and_origin_enforced(app):
    c = Client(app, "b" * 40)
    no_token = {k: v for k, v in c.h.items() if k != "X-CSRF-Token"}
    r = c.c.post("/api/reviews", headers=no_token, json={"keys": ["x"], "status": "confirmed"})
    assert r.status_code == 403 and r.json()["code"] == "csrf"
    evil = {**c.h, "Origin": "https://evil.example"}
    assert c.c.get("/api/overview", headers=evil).status_code == 403
    other_ws = {**c.h, "X-Workspace-Key": "c" * 40}
    assert c.c.post("/api/reviews", headers=other_ws, json={"keys": ["x"], "status": "confirmed"}).status_code == 403


def test_cors_locked_to_frontend(app):
    from fastapi.testclient import TestClient
    c = TestClient(app)
    ok = c.options("/api/overview", headers={"Origin": ORIGIN, "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == ORIGIN
    bad = c.options("/api/overview", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert bad.headers.get("access-control-allow-origin") is None


def test_streaming_scan_and_inventory(client):
    events = client.scan_csv("people.csv", PEOPLE)
    kinds = [e["type"] for e in events]
    assert kinds[0] == "reading" and kinds[1] == "start" and kinds[-1] == "done"
    assert sum(1 for e in events if e["type"] == "column") == 5
    done = events[-1]
    assert done["receipt"]["raw_values_persisted"] is False and done["receipt"]["processed_in_memory"]
    rows = {r["column"]: r for r in client.get("/api/inventory").json()["rows"]}
    assert rows["email"]["class"] == "CONTACT" and rows["order_id"]["class"] == "NOT_PERSONAL"
    assert rows["email"]["pt_id"].startswith("PT-") and rows["email"]["status"] == "candidate"
    assert rows["email"]["rationale"].endswith("Raw values were not retained.")


def test_rescan_keeps_stable_ids_and_builds_history(client):
    client.scan_csv("people.csv", PEOPLE)
    first = {r["column"]: r["pt_id"] for r in client.get("/api/inventory").json()["rows"]}
    client.scan_csv("people.csv", PEOPLE.replace(b",city", b",city,aadhaar_no").replace(b"Pune\n", b"Pune,234567890124\n"))
    rows = {r["column"]: r for r in client.get("/api/inventory").json()["rows"]}
    assert all(rows[c]["pt_id"] == first[c] for c in first)
    tl = client.get("/api/timeline").json()
    assert [s["seq"] for s in tl["scans"]] == [1, 2]
    diff = client.get("/api/diff", params={"a": 1, "b": 2}).json()
    assert any(n["column"] == "aadhaar_no" for n in diff["new"])
    detail = client.get(f"/api/findings/{rows['email']['pt_id']}").json()
    assert len(detail["history"]) == 2


def test_workspaces_are_isolated(app):
    a, b = Client(app, "e" * 40), Client(app, "f" * 40)
    a.scan_csv("people.csv", PEOPLE)
    assert len(a.get("/api/inventory").json()["rows"]) == 5
    assert b.get("/api/inventory").json()["rows"] == []
    key = a.get("/api/inventory").json()["rows"][0]["key"]
    assert b.post("/api/reviews", json={"keys": [key], "status": "confirmed"}).status_code == 404


def test_review_rules_and_undo(client):
    client.scan_csv("people.csv", PEOPLE)
    rows = client.get("/api/review-queue").json()["rows"]
    key = rows[0]["key"]
    assert client.post("/api/reviews", json={"keys": [key], "status": "rejected"}).status_code == 400
    assert client.post("/api/reviews", json={"keys": [key], "status": "confirmed", "class_override": "IDENTITY"}).status_code == 400
    r = client.post("/api/reviews", json={"keys": [key], "status": "rejected", "note": "Test fixture"}).json()
    assert r["previous"][0]["status"] == "candidate"
    assert client.get("/api/review-queue").json()["rows"][-1]["status"] == "rejected"
    client.post("/api/reviews/undo", json={"previous": r["previous"]})
    assert next(x for x in client.get("/api/inventory").json()["rows"] if x["key"] == key)["status"] == "candidate"
    bulk = [x["key"] for x in rows]
    assert client.post("/api/reviews", json={"keys": bulk, "status": "confirmed"}).json()["updated"] == len(bulk)
    assert client.get("/api/evaluation").json()["human"]["reviewed"] == len(bulk)


def test_metadata_gaps_bulk_undo_and_import(client):
    client.scan_csv("people.csv", PEOPLE)
    meta = client.get("/api/metadata").json()
    assert meta["coverage"]["documented"] == 0
    target = meta["tables"][0]["target"]
    assert meta["tables"][0]["suggestion"].get("system_of_record") == "people.csv"
    assert "legal_basis" not in meta["tables"][0]["suggestion"]
    r = client.post("/api/metadata", json={"targets": [target], "values": {"purpose": "Orders", "retention": "2 years",
                                                                            "owner": "Ops", "legal_basis": "Contract (declared)"}}).json()
    assert client.get("/api/metadata").json()["coverage"]["pct"] == 100
    client.post("/api/metadata/undo", json={"previous": r["previous"]})
    assert client.get("/api/metadata").json()["coverage"]["documented"] == 0
    csv_body = b"table,column,purpose,retention,owner\npeople,email,Receipts,1 year,Support\nmissing,,x,,\n"
    imp = client.post("/api/metadata/import", files={"file": ("m.csv", csv_body, "text/csv")}).json()
    assert imp["applied"] == 1 and imp["skipped"][0]["reason"].startswith("Table")
    assert client.get("/api/metadata/template").text.startswith("source,table,column")
    assert "metadata:" in client.get("/api/metadata/template", params={"format": "yaml"}).text


def test_rules_versioning_impact_and_test(client):
    client.scan_csv("people.csv", PEOPLE)
    rules = client.get("/api/rules").json()
    rs = rules["active"]
    assert rs["version"] == "1.0.0" and len(rules["versions"]) == 1
    edited = json.loads(json.dumps(rs))
    edited.pop("hash")
    for r in edited["rules"]:
        if r["id"] == "email":
            r["enabled"] = False
    impact = client.post("/api/rules/impact", json={"ruleset": edited}).json()
    assert impact["summary"]["no_longer_personal"] >= 1
    saved = client.post("/api/rules", json={"ruleset": edited, "note": "disable email"}).json()
    assert saved["version"] == "1.1.0"
    assert client.post("/api/rules", json={"ruleset": edited}).status_code == 400  # identical
    events = client.scan_csv("people.csv", PEOPLE)
    assert events[-1]["receipt"]["ruleset_version"] == "1.1.0"
    client.post("/api/rules/activate", json={"version": "1.0.0"})
    assert client.get("/api/rules").json()["active"]["version"] == "1.0.0"
    test = client.post("/api/rules/test", json={"rule": next(r for r in rs["rules"] if r["id"] == "aadhaar"), "header": "uid",
                                                "samples": ["234567890124", "123456789012", "hello"]}).json()
    assert [s["matches"] for s in test["samples"]] == [True, False, False]
    assert test["samples"][0]["valid"] and "234567890124" not in json.dumps(test)
    assert test["header"]["matched"]
    yaml_text = client.get("/api/rules/export").text
    assert client.post("/api/rules/import", files={"file": ("r.yaml", yaml_text.encode(), "text/yaml")}).status_code == 200


def test_demo_features(demo):
    o = demo.get("/api/overview").json()
    assert o["kpis"]["sources"] == 1 and o["kpis"]["candidates"] > 25 and o["posture"]["score"] is not None
    assert o["next_action"]["action"] in ("review", "metadata")
    assert any("aadhaar_no" in d["message"] and "no declared purpose" in d["message"] for d in o["drift"])
    lin = demo.get("/api/lineage").json()
    assert lin["edges"] and "Raw values are never compared" in lin["method"]
    target = lin["nodes"][0]["id"]
    blast = demo.get("/api/blast", params={"target": target}).json()
    assert blast["records"] > 0 and "Simulation" in blast["label"]
    reid = demo.get("/api/reid").json()
    assert any(t["kanon"] for t in reid["tables"])
    ret = demo.post("/api/retention", json={}).json()
    assert ret["never_cleaned"] and "What-if" in ret["label"]
    assert demo.post("/api/retention", json={"assume": {target: 0}}).status_code == 400
    ev = demo.get("/api/evaluation").json()
    assert ev["benchmark"]["macro"]["f1"] >= 0.9
    ans = demo.post("/api/assistant", json={"question": "Which tables have Aadhaar with no retention?"}).json()
    assert "support_tickets" in ans["answer"]
    why = demo.post("/api/assistant", json={"question": "Why was customers.mobile flagged?"}).json()
    assert "CONTACT" in why["answer"]
    pt = o["top_tables"][0]
    assert pt["risk"] > 0
    prev = demo.post("/api/mask/preview", json={"pt_id": "PT-00003", "strategy": "tokenise"}).json()
    assert prev["result"].startswith("TKN_")


def test_labels_run_on_my_data(client):
    client.scan_csv("people.csv", PEOPLE)
    rows = client.get("/api/inventory").json()["rows"]
    for r in rows:
        truth = "NOT_PERSONAL" if r["column"] == "order_id" else r["detected_class"]
        res = client.post("/api/labels", json={"key": r["key"], "true_class": truth}).json()
    assert res["labelled"] == 5 and res["metrics"]["accuracy"] == 1.0


def test_masked_csv_download(client):
    r = client.post("/api/mask/csv", files={"file": ("people.csv", PEOPLE, "text/csv")}, data={"strategy": "partial"})
    assert r.status_code == 200
    text = r.text
    assert "rahul.s@example.com" not in text and "ra****@example.com" in text
    assert "6123456789" in text  # order IDs are not personal and stay as they were


def test_workspace_export_import_and_wipe(app):
    a = Client(app, "g" * 40)
    a.scan_csv("people.csv", PEOPLE)
    exported = a.get("/api/workspace/export").content
    b = Client(app, "h" * 40)
    assert b.post("/api/workspace/import", files={"file": ("w.json", exported, "application/json")}).status_code == 200
    assert len(b.get("/api/inventory").json()["rows"]) == 5
    assert b.get("/api/audit/verify").json()["ok"]
    assert a.post("/api/workspace/wipe", json={"confirm": "yes"}).status_code == 400
    w = a.post("/api/workspace/wipe", json={"confirm": "WIPE"}).json()
    assert w["wiped"] and w["deleted"]["findings"] == 5
    assert a.get("/api/inventory").json()["rows"] == []


def test_errors_are_friendly(client):
    r = client.post("/api/scan", files={"file": ("x.exe", b"MZ", "application/octet-stream")}, data={"sample_size": "1000", "strategy": "head"})
    assert r.status_code == 400 and "Unsupported" in r.json()["detail"]
    r = client.post("/api/scan", files={"file": ("x.csv", b"a\n1\n", "text/csv")}, data={"sample_size": "7", "strategy": "head"})
    assert r.status_code == 400
    assert client.get("/api/findings/PT-99999").status_code == 404
    assert client.get("/api/diff", params={"a": 1, "b": 99}).status_code == 404
    assert "Traceback" not in client.get("/api/findings/PT-99999").text


def test_sqlite_upload_scan(client):
    from tests.test_ingest_rules_gaps import _sqlite_bytes
    r = client.post("/api/scan", files={"file": ("db.sqlite", _sqlite_bytes(), "application/octet-stream")},
                    data={"sample_size": "500", "strategy": "random"})
    events = [json.loads(x) for x in r.text.splitlines()]
    assert events[-1]["type"] == "done" and events[-1]["receipt"]["transient_copy"]
    src = client.get("/api/sources").json()["sources"][0]
    assert src["read_only_verified"] and src["kind"] == "SQLite"


def test_rate_limit(app):
    from privacytwin.api import RateLimiter
    rl = RateLimiter()
    assert all(rl.allow("x", 3, 60) for _ in range(3)) and not rl.allow("x", 3, 60)
