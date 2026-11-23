"""The twin service: scans, snapshots, reviews, metadata, diffs and simulations.

All functions take a workspace id; every query is scoped to it.
"""
from __future__ import annotations

import json
import uuid
from collections import Counter, defaultdict
from itertools import combinations
from typing import Iterator

from . import DISCLAIMER, __version__
from .detect import classify_column, k_anonymity, record_age_histogram, rescore, rule_hashes
from .gaps import (FIELD_LABELS, METADATA_FIELDS, SEVERITY_ORDER, column_target, effective, gaps_for, is_documented,
                   parse_retention, suggest, table_target)
from .ingest import SourceRead, now_iso
from .masking import overlap
from .rules import ALL_CLASSES, CLASS_SENSITIVITY, CLASSES, NOT_PERSONAL, bump, canonical, content_hash, default_ruleset, validate_ruleset
from .store import Store, append_audit, audit_entries, verify_chain

STATUSES = ("candidate", "confirmed", "rejected", "needs_info")
PERSISTED_FIELDS = [
    "column name", "inferred type", "null %", "distinct %", "min/max length", "sample size", "total row count",
    "candidate class", "confidence", "signal rates (header/value/validator)", "rule ID + version",
    "masked examples", "keyed MinHash fingerprint (32 x 32-bit)", "k-anonymity aggregates", "record-age histogram",
]

COMBOS = [
    ("Name + date of birth + PIN code", {"person_name", "date_of_birth", "pin_code"}, "High"),
    ("Date of birth + gender + PIN code", {"date_of_birth", "gender", "pin_code"}, "High"),
    ("Aadhaar + name", {"aadhaar", "person_name"}, "High"),
    ("PAN + name + date of birth", {"pan", "person_name", "date_of_birth"}, "High"),
    ("Card number + name", {"card_number", "person_name"}, "High"),
    ("Bank account + IFSC", {"bank_account", "ifsc"}, "High"),
    ("Name + mobile", {"person_name", "mobile_in"}, "Medium"),
    ("Name + email", {"person_name", "email"}, "Medium"),
    ("Email + mobile", {"email", "mobile_in"}, "Medium"),
    ("Name + address", {"person_name", "address"}, "Medium"),
    ("Name + precise location", {"person_name", "geo_pair"}, "Medium"),
    ("Passport + name", {"passport_in", "person_name"}, "High"),
]
GENERIC_COLUMNS = {"id", "created_at", "updated_at", "status", "name", "type", "notes", "amount", "date", "description"}


def actor_name(actor: str | None) -> str:
    return (actor or "reviewer").strip()[:80] or "reviewer"


class Twin:
    def __init__(self, store: Store):
        self.store = store

    # ================================================================ rules

    def rulesets(self, ws: str) -> tuple[dict, list[dict]]:
        info = self.store.ensure_workspace(ws)
        with self.store.connect() as c:
            rows = c.execute("SELECT version, hash, note, created_at, content FROM rulesets WHERE ws=? ORDER BY created_at", (ws,)).fetchall()
        if not rows:
            rs = default_ruleset()
            with self.store.tx() as c:
                c.execute("INSERT OR IGNORE INTO rulesets VALUES(?,?,?,?,?,?)",
                          (ws, rs["version"], content_hash(rs), canonical(rs), "Default rule set", now_iso()))
            return self.rulesets(ws)
        versions = [{"version": r["version"], "hash": r["hash"], "note": r["note"], "created_at": r["created_at"],
                     "rules": len(json.loads(r["content"])["rules"])} for r in rows]
        active_v = info["settings"].get("active_ruleset", "1.0.0")
        active = next((r for r in rows if r["version"] == active_v), rows[-1])
        rs = json.loads(active["content"]) | {"hash": active["hash"]}
        return rs, versions

    def ruleset_version(self, ws: str, version: str) -> dict:
        with self.store.connect() as c:
            row = c.execute("SELECT content, hash FROM rulesets WHERE ws=? AND version=?", (ws, version)).fetchone()
        if not row:
            raise KeyError(f"Rule set {version} not found")
        return json.loads(row["content"]) | {"hash": row["hash"]}

    def save_ruleset(self, ws: str, raw: dict, note: str, actor: str, part: str = "minor") -> dict:
        active, versions = self.rulesets(ws)
        candidate = validate_ruleset({k: v for k, v in raw.items() if k != "hash"})
        h = content_hash(candidate)
        if h == active["hash"]:
            raise ValueError("No changes to save: the rule set is identical to the active version")
        existing = {v["version"] for v in versions}
        version = bump(max(existing, key=lambda v: tuple(map(int, v.split(".")))), part)
        candidate["version"] = version
        with self.store.tx() as c:
            c.execute("INSERT INTO rulesets VALUES(?,?,?,?,?,?)", (ws, version, h, canonical(candidate), note[:200] or "Edited rules", now_iso()))
            self.store.update_settings(c, ws, {"active_ruleset": version})
            append_audit(c, ws, actor_name(actor), "rules.saved", f"ruleset:{version}", {"hash": h, "note": note[:200]})
        return candidate | {"hash": h}

    def activate_ruleset(self, ws: str, version: str, actor: str) -> dict:
        rs = self.ruleset_version(ws, version)
        with self.store.tx() as c:
            self.store.update_settings(c, ws, {"active_ruleset": version})
            append_audit(c, ws, actor_name(actor), "rules.activated", f"ruleset:{version}", {"hash": rs["hash"]})
        return rs

    # ================================================================ scanning

    def _find_source(self, c, ws: str, name: str, kind: str):
        return c.execute("SELECT * FROM sources WHERE ws=? AND name=? AND kind=?", (ws, name, kind)).fetchone()

    def scan(self, ws: str, read: SourceRead, name: str, origin: str, sample_size: int, strategy: str,
             actor: str = "system", detail: dict | None = None, created_at: str | None = None,
             source_id: str | None = None) -> Iterator[dict]:
        """Scan an in-memory source read. Yields progress events; persists aggregates at the end."""
        info = self.store.ensure_workspace(ws)
        ruleset, _ = self.rulesets(ws)
        salt = info["salt"]
        with self.store.connect() as c:
            existing = None
            if source_id:
                existing = c.execute("SELECT * FROM sources WHERE ws=? AND id=?", (ws, source_id)).fetchone()
            if existing is None:
                existing = self._find_source(c, ws, name, read.kind)
            known = {r["key"]: r["pt_id"] for r in c.execute("SELECT key, pt_id FROM columns WHERE ws=?", (ws,))}
        sid = existing["id"] if existing else (source_id or str(uuid.uuid4()))
        total_columns = sum(len(t.headers) for t in read.tables)
        yield {"type": "start", "source_id": sid, "source": name, "kind": read.kind, "tables": len(read.tables),
               "columns": total_columns, "rescan": bool(existing), "ruleset": ruleset["version"]}
        results, stats, receipt_tables = [], [], []
        done = 0
        cache: dict = {}
        for table in read.tables:
            yield {"type": "table", "table": table.name, "columns": len(table.headers), "rows_sampled": len(table.rows),
                   "total_rows": table.total_rows}
            dict_rows = [dict(zip(table.headers, r)) for r in table.rows]
            qi: dict[str, str] = {}
            for i, col in enumerate(table.headers):
                values = [r[i] if i < len(r) else None for r in table.rows]
                res = classify_column(table.name, col, values, ruleset, salt, table.total_rows, cache=cache)
                key = f"{sid}/{table.name}/{col}"
                res["key"] = key
                if res["quasi_identifier"]:
                    qi[col] = res["quasi_identifier"]
                results.append(res)
                done += 1
                yield {"type": "column", "progress": round(done / max(1, total_columns), 4), "table": table.name,
                       "column": col, "class": res["class"], "confidence": res["confidence"], "band": res["band"],
                       "pt_id": known.get(key), "masked_examples": res["masked_examples"]}
            kanon = k_anonymity(dict_rows, qi)
            age_hist = record_age_histogram(dict_rows, table.headers)
            stats.append((table.name, table.total_rows, len(table.headers), kanon, age_hist))
            receipt_tables.append({"table": table.name, "rows_sampled": len(table.rows), "total_rows": table.total_rows})
            # release raw values for this table immediately
            table.rows.clear()
            del dict_rows
        discarded_at = now_iso()
        ts = created_at or now_iso()
        receipt = {
            "source": name, "kind": read.kind, "origin": origin,
            "sample_size_requested": sample_size, "strategy": strategy, "tables": receipt_tables,
            "processed_in_memory": True,
            "transient_copy": read.transient_copy,
            "transient_copy_deleted_at": read.transient_deleted_at,
            "raw_values_discarded_at": discarded_at,
            "fields_persisted": PERSISTED_FIELDS,
            "raw_values_persisted": False,
            "encoding": read.encoding, "delimiter": read.delimiter, "notes": read.notes,
            "read_only_verified": read.read_only_verified, "read_only_detail": read.read_only_detail,
            "ruleset_version": ruleset["version"], "ruleset_hash": ruleset["hash"],
            "disclaimer": DISCLAIMER,
        }
        scan_id = str(uuid.uuid4())
        with self.store.tx() as c:
            if not existing:
                c.execute("INSERT INTO sources VALUES(?,?,?,?,?,?,?,?,?)",
                          (sid, ws, name, read.kind, origin, canonical(detail or {}), int(read.read_only_verified),
                           read.read_only_detail, ts))
            else:
                c.execute("UPDATE sources SET read_only_verified=?, read_only_detail=? WHERE id=? AND ws=?",
                          (int(read.read_only_verified), read.read_only_detail, sid, ws))
            seq = (c.execute("SELECT MAX(seq) FROM scans WHERE ws=?", (ws,)).fetchone()[0] or 0) + 1
            summary = {"tables": len(read.tables), "columns": len(results),
                       "personal": sum(1 for r in results if r["class"] != NOT_PERSONAL),
                       "by_class": dict(Counter(r["class"] for r in results if r["class"] != NOT_PERSONAL))}
            receipt["scan_id"] = scan_id
            receipt["scan_seq"] = seq
            c.execute("INSERT INTO scans VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                      (scan_id, ws, seq, sid, ts, ruleset["version"], ruleset["hash"], sample_size, strategy,
                       canonical(summary), canonical(receipt)))
            for res in results:
                key = res["key"]
                pt = known.get(key)
                if not pt:
                    pt = self.store.next_pt_id(c, ws)
                    c.execute("INSERT INTO columns VALUES(?,?,?,?,?,?,?)", (ws, key, pt, sid, res["table"], res["column"], scan_id))
                    known[key] = pt
                payload = {k: v for k, v in res.items() if k not in ("key", "table", "column", "class", "confidence", "band", "rule_id")}
                c.execute("INSERT INTO findings VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                          (scan_id, ws, key, pt, res["table"], res["column"], res["class"], res["confidence"], res["band"],
                           res["rule_id"], canonical(payload)))
            for table_name, total, ncols, kanon, hist in stats:
                c.execute("INSERT INTO table_stats VALUES(?,?,?,?,?,?,?)",
                          (scan_id, ws, table_name, total, ncols, canonical(kanon) if kanon else None,
                           canonical(hist) if hist else None))
            append_audit(c, ws, actor_name(actor), "scan.completed", f"scan:{seq}",
                         {"source": name, "columns": len(results), "personal": summary["personal"],
                          "ruleset": ruleset["version"], "ruleset_hash": ruleset["hash"]})
        triage = None
        if self.auto_triage_status(ws)["enabled"]:
            yield {"type": "triage", "detail": "AI is reviewing high-confidence candidates"}
            triage = self.auto_triage(ws, source_id=sid)
        yield {"type": "done", "scan_id": scan_id, "scan_seq": seq, "source_id": sid, "summary": summary,
               "receipt": receipt, "auto_triage": triage}

    def run_scan(self, *args, **kwargs) -> dict:
        last = None
        for event in self.scan(*args, **kwargs):
            last = event
        return last

    # ================================================================ snapshot views

    def scans(self, ws: str) -> list[dict]:
        with self.store.connect() as c:
            rows = c.execute("""SELECT s.id, s.seq, s.source_id, s.created_at, s.ruleset_version, s.ruleset_hash,
                                s.sample_size, s.strategy, s.stats, src.name source_name
                                FROM scans s JOIN sources src ON src.id=s.source_id WHERE s.ws=? ORDER BY s.seq""", (ws,)).fetchall()
        return [dict(r) | {"stats": json.loads(r["stats"])} for r in rows]

    def receipt(self, ws: str, scan_id: str) -> dict:
        with self.store.connect() as c:
            row = c.execute("SELECT receipt FROM scans WHERE ws=? AND (id=? OR CAST(seq AS TEXT)=?)", (ws, scan_id, scan_id)).fetchone()
        if not row:
            raise KeyError("Scan not found")
        return json.loads(row["receipt"])

    def _snapshot_scans(self, c, ws: str, as_of_seq: int | None) -> list:
        q = """SELECT s.* FROM scans s WHERE s.ws=? AND s.seq = (
                 SELECT MAX(s2.seq) FROM scans s2 WHERE s2.ws=s.ws AND s2.source_id=s.source_id AND s2.seq<=?)"""
        return c.execute(q, (ws, as_of_seq if as_of_seq is not None else 10**9)).fetchall()

    def _meta(self, c, ws: str, ts: str | None = None) -> dict[str, dict]:
        rows = c.execute("SELECT target, field, value FROM metadata WHERE ws=? AND created_at<=? ORDER BY id",
                         (ws, ts or "9999")).fetchall()
        out: dict[str, dict] = defaultdict(dict)
        for r in rows:
            out[r["target"]][r["field"]] = r["value"]
        return out

    def _reviews(self, c, ws: str, ts: str | None = None) -> dict[str, dict]:
        rows = c.execute("SELECT * FROM reviews WHERE ws=? AND created_at<=? ORDER BY id", (ws, ts or "9999")).fetchall()
        return {r["column_key"]: dict(r) for r in rows}

    def view(self, ws: str, as_of_seq: int | None = None, at_scan_time: bool = False) -> dict:
        """The twin at a point in time: latest scan of each source up to `as_of_seq`."""
        info = self.store.ensure_workspace(ws)
        max_ret = int(info["settings"].get("max_retention_days", 3650))
        with self.store.connect() as c:
            snap = self._snapshot_scans(c, ws, as_of_seq)
            ts = max((s["created_at"] for s in snap), default=None) if at_scan_time else None
            meta = self._meta(c, ws, ts)
            reviews = self._reviews(c, ws, ts)
            sources = {r["id"]: dict(r) for r in c.execute("SELECT * FROM sources WHERE ws=?", (ws,))}
            scan_ids = [s["id"] for s in snap]
            marks = ",".join("?" * len(scan_ids)) or "''"
            findings = c.execute(f"SELECT * FROM findings WHERE scan_id IN ({marks}) ORDER BY pt_id", scan_ids).fetchall()
            tstats = c.execute(f"SELECT * FROM table_stats WHERE scan_id IN ({marks})", scan_ids).fetchall()
        scan_by_id = {s["id"]: s for s in snap}
        rows = []
        for f in findings:
            p = json.loads(f["payload"])
            scan = scan_by_id[f["scan_id"]]
            sid = scan["source_id"]
            review = reviews.get(f["column_key"])
            # An AI approval applies only to the measured scan it assessed.
            if review and review["decision_source"] == "ai" and review["decision_scan_id"] != f["scan_id"]:
                review = None
            status = review["status"] if review else "candidate"
            cls = (review["class_override"] if review and review["class_override"] else f["class"])
            m = effective(meta, sid, f["table_name"], f["column_key"])
            personal = cls != NOT_PERSONAL and status != "rejected"
            g = gaps_for(m, max_ret) if personal else []
            gap_weight = sum(SEVERITY_ORDER[x["severity"]] for x in g)
            risk = round(100 * f["confidence"] * CLASS_SENSITIVITY.get(cls, 0) * (0.5 + 0.5 * min(1, gap_weight / 6)), 1) if personal else 0.0
            rows.append({
                "pt_id": f["pt_id"], "key": f["column_key"], "source_id": sid,
                "source": sources.get(sid, {}).get("name", "?"), "table": f["table_name"], "column": f["column_name"],
                "class": cls, "detected_class": f["class"], "confidence": f["confidence"], "band": f["band"],
                "rule_id": f["rule_id"], "rule_name": p.get("rule_name"), "rule_version": scan["ruleset_version"],
                "signals": p["signals"], "validator": p.get("validator"), "header_keyword": p.get("header_keyword"),
                "negative_keywords": p.get("negative_keywords", []), "notes": p.get("notes", []),
                "alternatives": p.get("alternatives", []), "masked_examples": p["masked_examples"],
                "rationale": p["rationale"], "profile": p["profile"], "quasi_identifier": p.get("quasi_identifier"),
                "status": status, "review_note": review["note"] if review else "", "reviewed_by": review["actor"] if review else None,
                "decision_source": review["decision_source"] if review else None,
                "automation_batch": review["automation_batch"] if review else None,
                "decision_scan_id": review["decision_scan_id"] if review else None,
                "reviewed_at": review["created_at"] if review else None,
                "meta": m, "gaps": g, "max_gap": max((x["severity"] for x in g), key=lambda s: SEVERITY_ORDER[s], default=None),
                "documented": is_documented(m) if personal else None, "personal": personal, "risk": risk,
                "scan_id": scan["id"], "scan_seq": scan["seq"],
            })
        tables = {}
        for t in tstats:
            scan = scan_by_id[t["scan_id"]]
            key = f"{scan['source_id']}/{t['table_name']}"
            tables[key] = {"key": key, "source_id": scan["source_id"], "source": sources.get(scan["source_id"], {}).get("name"),
                           "table": t["table_name"], "total_rows": t["total_rows"], "columns": t["column_count"],
                           "kanon": json.loads(t["kanon"]) if t["kanon"] else None,
                           "age_hist": json.loads(t["age_hist"]) if t["age_hist"] else None}
        return {"rows": rows, "tables": tables, "sources": list(sources.values()), "snapshot": [dict(s) for s in snap],
                "settings": info["settings"], "_fingerprints": {f["column_key"]: json.loads(f["payload"]).get("fingerprint", []) for f in findings},
                "_payloads": {f["column_key"]: json.loads(f["payload"]) for f in findings}}

    # ================================================================ overview & posture

    def posture(self, view: dict) -> dict:
        personal = [r for r in view["rows"] if r["personal"]]
        n = len(personal)
        if not n:
            return {"score": None, "components": {}, "formula": POSTURE_FORMULA, "label": POSTURE_LABEL}
        coverage = sum(1 for r in personal if r["documented"]) / n
        reviewed = sum(1 for r in personal if r["status"] in ("confirmed", "rejected")) / n
        gap_index = sum(SEVERITY_ORDER[g["severity"]] for r in personal for g in r["gaps"]) / (n * 10)
        # generalised quasi-identifiers (birth year bands, 3-digit PIN) are what an attacker
        # realistically has; exact values overstate risk on any table with a full DOB
        kanon = [t["kanon"]["generalised"]["unique_pct"] / 100 for t in view["tables"].values() if t["kanon"]]
        reid = sum(kanon) / len(kanon) if kanon else 0.0
        score = 100 * (0.35 * coverage + 0.25 * reviewed + 0.25 * (1 - min(1, gap_index)) + 0.15 * (1 - reid))
        return {"score": round(score), "components": {
            "metadata_coverage": round(coverage, 3), "review_completion": round(reviewed, 3),
            "gap_severity_index": round(min(1, gap_index), 3), "reidentification_risk": round(reid, 3)},
            "formula": POSTURE_FORMULA, "label": POSTURE_LABEL}

    def _kpis(self, view: dict) -> dict:
        rows = view["rows"]
        personal = [r for r in rows if r["personal"]]
        candidates = [r for r in rows if r["detected_class"] != NOT_PERSONAL or r["status"] != "candidate"]
        return {
            "sources": len({r["source_id"] for r in rows}),
            "columns": len(rows),
            "candidates": len([r for r in rows if r["detected_class"] != NOT_PERSONAL]),
            "confirmed": len([r for r in rows if r["status"] == "confirmed"]),
            "open_gaps": sum(len(r["gaps"]) for r in personal),
            "reviewed_pct": round(100 * len([r for r in candidates if r["status"] != "candidate"]) / len(candidates)) if candidates else 0,
            "pending_review": len([r for r in rows if r["detected_class"] != NOT_PERSONAL and r["status"] == "candidate"]),
            "posture": self.posture(view)["score"],
        }

    def overview(self, ws: str, as_of_seq: int | None = None) -> dict:
        view = self.view(ws, as_of_seq)
        scans = self.scans(ws)
        current_seq = as_of_seq or (scans[-1]["seq"] if scans else None)
        kpis = self._kpis(view)
        prev = None
        if current_seq and current_seq > 1:
            prev = self._kpis(self.view(ws, current_seq - 1, at_scan_time=True))
        rows = view["rows"]
        personal = [r for r in rows if r["personal"]]
        by_class = Counter(r["class"] for r in personal)
        gaps_by_sev = Counter(g["severity"] for r in personal for g in r["gaps"])
        heat: dict[str, Counter] = defaultdict(Counter)
        for r in personal:
            heat[f"{r['source_id']}/{r['table']}"][r["class"]] += 1
        heatmap = []
        for key, t in view["tables"].items():
            heatmap.append({"key": key, "table": t["table"], "source": t["source"], "counts": {c: heat[key].get(c, 0) for c in CLASSES},
                            "unique_pct": t["kanon"]["exact"]["unique_pct"] if t["kanon"] else None})
        table_risk = defaultdict(float)
        for r in personal:
            table_risk[f"{r['source_id']}/{r['table']}"] += r["risk"]
        top = sorted(({"key": k, "table": view["tables"].get(k, {}).get("table", k.split("/")[-1]), "risk": round(v, 1),
                       "personal": sum(1 for r in personal if f"{r['source_id']}/{r['table']}" == k),
                       "rows": view["tables"].get(k, {}).get("total_rows")} for k, v in table_risk.items()),
                     key=lambda x: -x["risk"])[:6]
        return {"kpis": kpis, "previous": prev, "by_class": {c: by_class.get(c, 0) for c in CLASSES},
                "gaps_by_severity": {s: gaps_by_sev.get(s, 0) for s in ("High", "Medium", "Low")},
                "heatmap": heatmap, "top_tables": top, "posture": self.posture(view),
                "next_action": self.next_action(ws, view, scans), "scan_seq": current_seq,
                "drift": sorted(self.drift(ws), key=lambda d: (-d["scan_seq"], d["severity"] != "High",
                                                               -CLASS_SENSITIVITY.get(d["class"], 0)))[:4]}

    def next_action(self, ws: str, view: dict, scans: list) -> dict:
        rows = view["rows"]
        if not scans:
            return {"text": "No data yet. Load the demo company or drop a CSV/SQLite file anywhere.", "action": "load_demo", "label": "Load demo"}
        pending = [r for r in rows if r["detected_class"] != NOT_PERSONAL and r["status"] == "candidate"]
        no_ret = [r for r in rows if r["personal"] and any(g["field"] == "retention" and g["severity"] == "High" for g in r["gaps"])]
        no_purpose = [r for r in rows if r["personal"] and any(g["field"] == "purpose" for g in r["gaps"])]
        if len(pending) >= 1:
            return {"text": f"{len(pending)} candidates await review", "action": "review", "label": "Start reviewing", "count": len(pending)}
        if no_purpose:
            return {"text": f"{len(no_purpose)} personal-data fields have no declared purpose", "action": "metadata", "label": "Add metadata", "count": len(no_purpose)}
        if no_ret:
            return {"text": f"{len(no_ret)} personal-data fields have no retention", "action": "metadata", "label": "Add metadata", "count": len(no_ret)}
        return {"text": "Everything is reviewed and documented. Export a verifiable evidence pack.", "action": "evidence", "label": "Export evidence"}

    # ================================================================ reviews

    def auto_triage_status(self, ws: str) -> dict:
        from .llm import status
        settings = self.store.ensure_workspace(ws)["settings"]
        with self.store.connect() as c:
            last = c.execute("SELECT automation_batch FROM reviews WHERE ws=? AND decision_source='ai' "
                             "AND automation_batch IS NOT NULL ORDER BY id DESC LIMIT 1", (ws,)).fetchone()
            batch = last["automation_batch"] if last else None
            undoable = c.execute("SELECT COUNT(*) FROM reviews r WHERE r.ws=? AND r.decision_source='ai' "
                                 "AND r.automation_batch=? AND r.id=(SELECT MAX(r2.id) FROM reviews r2 "
                                 "WHERE r2.ws=r.ws AND r2.column_key=r.column_key)", (ws, batch)).fetchone()[0]
        return {"enabled": bool(settings.get("auto_triage_enabled", False)),
                "threshold": settings.get("auto_triage_threshold", 0.95), "llm": status(),
                "revision": settings.get("auto_triage_revision"), "last_batch": batch, "undoable": undoable, "limit": 200}

    def configure_auto_triage(self, ws: str, enabled: bool, threshold: float, actor: str) -> dict:
        if not 0.9 <= threshold <= 1:
            raise ValueError("Auto-triage confidence must be between 0.90 and 1.00")
        self.store.ensure_workspace(ws)
        with self.store.tx() as c:
            self.store.update_settings(c, ws, {"auto_triage_enabled": enabled, "auto_triage_threshold": threshold,
                                               "auto_triage_revision": str(uuid.uuid4())})
            append_audit(c, ws, actor_name(actor), "automation.configured", "auto-triage",
                         {"enabled": enabled, "threshold": threshold})
        return self.auto_triage_status(ws)

    def auto_triage(self, ws: str, source_id: str | None = None) -> dict:
        from .triage import MAX_BATCH, propose
        policy = self.auto_triage_status(ws)
        result = {"approved": 0, "eligible": 0, "remaining": 0, "batch_id": None, "status": "disabled"}
        if not policy["enabled"]:
            return result
        if not policy["llm"]["enabled"]:
            return result | {"status": "unavailable"}
        rows = [r for r in self.view(ws)["rows"] if r["status"] == "candidate" and r["reviewed_by"] is None
                and r["detected_class"] != NOT_PERSONAL and r["band"] == "HIGH"
                and r["confidence"] >= policy["threshold"] and (source_id is None or r["source_id"] == source_id)]
        rows.sort(key=lambda r: (-r["risk"], r["pt_id"]))
        result.update(eligible=len(rows), remaining=max(0, len(rows)-policy["limit"]), status="complete")
        if not rows:
            return result
        batch_id = str(uuid.uuid4())
        errors = 0
        for offset in range(0, min(len(rows), policy["limit"]), MAX_BATCH):
            # Recheck opt-in between model calls as well as inside the write transaction.
            if not self.auto_triage_status(ws)["enabled"]:
                result["status"] = "stopped"
                break
            candidates = rows[offset:offset+MAX_BATCH]
            try:
                approvals, model = propose(candidates)
            except Exception:
                # A provider or malformed output must not break a committed scan.
                approvals, model = [], None
            if model is None:
                errors += 1
                # Avoid repeating a slow failed provider call for every batch.
                result["remaining"] += min(len(rows), policy["limit"]) - offset
                break
            by_pt = {r["pt_id"]: r for r in candidates}
            with self.store.tx() as c:
                workspace = c.execute("SELECT settings FROM workspaces WHERE id=?", (ws,)).fetchone()
                current = json.loads(workspace[0]) if workspace else {}
                if not current.get("auto_triage_enabled", False) or current.get("auto_triage_revision") != policy["revision"]:
                    result["status"] = "stopped"
                    break
                for approval in approvals:
                    r = by_pt[approval["pt_id"]]
                    # Never overwrite a human decision or apply reasoning to a superseded scan.
                    latest = c.execute("SELECT id FROM scans WHERE ws=? AND source_id=? ORDER BY seq DESC LIMIT 1",
                                       (ws, r["source_id"])).fetchone()
                    reviewed = c.execute("SELECT decision_source, decision_scan_id FROM reviews WHERE ws=? AND column_key=? ORDER BY id DESC LIMIT 1", (ws, r["key"])).fetchone()
                    if ((reviewed and (reviewed["decision_source"] != "ai" or reviewed["decision_scan_id"] == r["scan_id"]))
                            or not latest or latest["id"] != r["scan_id"] or r["confidence"] < current.get("auto_triage_threshold", .95)):
                        continue
                    note = f"AI auto-approved: {approval['reason']}"
                    c.execute("INSERT INTO reviews(ws,column_key,status,class_override,note,actor,created_at,decision_source,automation_batch,decision_scan_id) "
                              "VALUES(?,?,'confirmed',NULL,?,'AI auto-triage',?,'ai',?,?)",
                              (ws, r["key"], note, now_iso(), batch_id, r["scan_id"]))
                    append_audit(c, ws, "AI auto-triage", "review.auto_approved", r["pt_id"],
                                 {"status": "confirmed", "decision_source": "ai", "batch_id": batch_id,
                                  "reason": approval["reason"], "confidence": r["confidence"],
                                  "threshold": current.get("auto_triage_threshold", .95), "scan_id": r["scan_id"],
                                  "rule_version": r["rule_version"], **model})
                    result["approved"] += 1
        result["batch_id"] = batch_id if result["approved"] else None
        if errors:
            result["status"] = "unavailable"
        with self.store.tx() as c:
            append_audit(c, ws, "AI auto-triage", "automation.completed", "auto-triage", result)
        return result

    def undo_auto_triage(self, ws: str, batch_id: str, actor: str) -> dict:
        self.store.ensure_workspace(ws)
        restored = 0
        with self.store.tx() as c:
            rows = c.execute("SELECT r.*, col.pt_id FROM reviews r JOIN columns col ON col.ws=r.ws AND col.key=r.column_key "
                             "WHERE r.ws=? AND r.decision_source='ai' AND r.automation_batch=? "
                             "AND r.id=(SELECT MAX(r2.id) FROM reviews r2 WHERE r2.ws=r.ws AND r2.column_key=r.column_key)",
                             (ws, batch_id)).fetchall()
            for r in rows:
                c.execute("INSERT INTO reviews(ws,column_key,status,class_override,note,actor,created_at) "
                          "VALUES(?,?,'candidate',NULL,'Undid AI auto-approval',?,?)",
                          (ws, r["column_key"], actor_name(actor), now_iso()))
                append_audit(c, ws, actor_name(actor), "review.undo_auto_approval", r["pt_id"], {"batch_id": batch_id})
                restored += 1
        return {"restored": restored}

    def review(self, ws: str, keys: list[str], status: str, note: str, actor: str, class_override: str | None = None,
               undo: bool = False, created_at: str | None = None, decision_source: str = "human",
               automation_batch: str | None = None, decision_scan_id: str | None = None) -> dict:
        if status not in STATUSES:
            raise ValueError(f"Status must be one of {', '.join(STATUSES)}")
        if class_override and class_override not in ALL_CLASSES:
            raise ValueError("Unknown class")
        if not undo and (status == "rejected" or class_override) and len(note.strip()) < 3:
            raise ValueError("A short note is required to reject or reclassify a candidate")
        if not keys or len(keys) > 2000:
            raise ValueError("Select between 1 and 2000 findings")
        note = note.strip()[:1000]
        previous = []
        with self.store.tx() as c:
            known = {r["key"]: r["pt_id"] for r in c.execute("SELECT key, pt_id FROM columns WHERE ws=?", (ws,))}
            for key in keys:
                if key not in known:
                    raise KeyError(f"Unknown finding {key}")
                old = c.execute("SELECT status, class_override, note, decision_source, automation_batch, decision_scan_id FROM reviews WHERE ws=? AND column_key=? ORDER BY id DESC LIMIT 1", (ws, key)).fetchone()
                previous.append({"key": key, "status": old["status"] if old else "candidate",
                                 "class_override": old["class_override"] if old else None, "note": old["note"] if old else "",
                                 "decision_source": old["decision_source"] if old else "human",
                                 "automation_batch": old["automation_batch"] if old else None,
                                 "decision_scan_id": old["decision_scan_id"] if old else None})
                c.execute("INSERT INTO reviews(ws,column_key,status,class_override,note,actor,created_at,decision_source,automation_batch,decision_scan_id) VALUES(?,?,?,?,?,?,?,?,?,?)",
                          (ws, key, status, class_override, note, actor_name(actor), created_at or now_iso(), decision_source, automation_batch, decision_scan_id))
                append_audit(c, ws, actor_name(actor), "review.undo" if undo else f"review.{status}", known[key],
                             {"status": status, "class_override": class_override, "note": note,
                              "previous": previous[-1]["status"], "decision_source": decision_source,
                              "automation_batch": automation_batch, "decision_scan_id": decision_scan_id})
        return {"updated": len(keys), "previous": previous}

    def undo_reviews(self, ws: str, previous: list[dict], actor: str) -> dict:
        n = 0
        for p in previous[:2000]:
            self.review(ws, [p["key"]], p["status"], p.get("note") or "Undo", actor, p.get("class_override"), undo=True,
                        decision_source="ai" if p.get("decision_source") == "ai" else "human",
                        automation_batch=p.get("automation_batch"), decision_scan_id=p.get("decision_scan_id"))
            n += 1
        return {"restored": n}

    def human_precision(self, ws: str) -> dict:
        view = self.view(ws)
        reviewed = [r for r in view["rows"] if r["detected_class"] != NOT_PERSONAL and r["status"] in ("confirmed", "rejected")
                    and r["decision_source"] != "ai"]
        correct = [r for r in reviewed if r["status"] == "confirmed" and r["class"] == r["detected_class"]]
        per = {}
        for cls in CLASSES:
            sub = [r for r in reviewed if r["detected_class"] == cls]
            ok = [r for r in sub if r in correct]
            per[cls] = {"reviewed": len(sub), "confirmed_correct": len(ok), "precision": round(len(ok) / len(sub), 3) if sub else None}
        return {"reviewed": len(reviewed), "confirmed_correct": len(correct),
                "precision": round(len(correct) / len(reviewed), 3) if reviewed else None, "per_class": per}

    # ================================================================ metadata

    def set_metadata(self, ws: str, targets: list[str], values: dict, actor: str, created_at: str | None = None,
                     source: str = "declared") -> dict:
        unknown = set(values) - set(METADATA_FIELDS)
        if unknown:
            raise ValueError(f"Unknown metadata fields: {', '.join(sorted(unknown))}")
        if not targets or len(targets) > 2000:
            raise ValueError("Select between 1 and 2000 targets")
        for t in targets:
            if not (t.startswith("table:") or t.startswith("col:")) or len(t) > 600:
                raise ValueError("Invalid metadata target")
        cleaned = {k: str(v or "").strip()[:500] for k, v in values.items()}
        previous = []
        ts = created_at or now_iso()
        with self.store.tx() as c:
            for t in targets:
                before = {}
                for f in cleaned:
                    row = c.execute("SELECT value FROM metadata WHERE ws=? AND target=? AND field=? ORDER BY id DESC LIMIT 1", (ws, t, f)).fetchone()
                    before[f] = row["value"] if row else ""
                    if before[f] == cleaned[f]:
                        continue
                    c.execute("INSERT INTO metadata(ws,target,field,value,actor,created_at) VALUES(?,?,?,?,?,?)",
                              (ws, t, f, cleaned[f], actor_name(actor), ts))
                previous.append({"target": t, "values": before})
                append_audit(c, ws, actor_name(actor), "metadata.set", t, {"values": cleaned, "source": source})
        return {"updated": len(targets), "previous": previous}

    def metadata_overview(self, ws: str) -> dict:
        view = self.view(ws)
        personal = [r for r in view["rows"] if r["personal"]]
        documented = sum(1 for r in personal if r["documented"])
        with self.store.connect() as c:
            meta = self._meta(c, ws)
        tables = []
        for key, t in view["tables"].items():
            cols = [r for r in personal if f"{r['source_id']}/{r['table']}" == key]
            if not cols:
                continue
            declared = meta.get(table_target(t["source_id"], t["table"]), {})
            sug = suggest(t["table"], t["source"] or "")
            tables.append({"key": key, "target": table_target(t["source_id"], t["table"]), "table": t["table"],
                           "source": t["source"], "declared": {f: declared.get(f, "") for f in METADATA_FIELDS},
                           "suggestion": {f: v for f, v in sug.items() if f in METADATA_FIELDS and not declared.get(f)},
                           "suggestion_basis": sug["basis"], "columns": len(cols),
                           "gaps": sum(len(r["gaps"]) for r in cols)})
        return {"coverage": {"documented": documented, "personal": len(personal),
                             "pct": round(100 * documented / len(personal)) if personal else 0},
                "tables": tables, "fields": [{"key": f, "label": FIELD_LABELS[f]} for f in METADATA_FIELDS],
                "max_retention_days": view["settings"].get("max_retention_days", 3650)}

    def import_metadata(self, ws: str, records: list[dict], actor: str) -> dict:
        """Records: {table, column?, source?, purpose, retention, owner, legal_basis, system_of_record}."""
        view = self.view(ws)
        tables = {}
        for t in view["tables"].values():
            tables.setdefault(t["table"].lower(), []).append(t)
        applied, skipped = 0, []
        for i, rec in enumerate(records[:5000]):
            tname = str(rec.get("table", "")).strip().lower()
            matches = [t for t in tables.get(tname, []) if not rec.get("source") or t["source"] == rec.get("source")]
            if not matches:
                skipped.append({"row": i + 1, "reason": f"Table '{rec.get('table')}' not found"})
                continue
            values = {f: rec[f] for f in METADATA_FIELDS if rec.get(f) not in (None, "")}
            if not values:
                skipped.append({"row": i + 1, "reason": "No metadata values"})
                continue
            col = str(rec.get("column", "") or "").strip()
            targets = [column_target(f"{t['source_id']}/{t['table']}/{col}") if col else table_target(t["source_id"], t["table"]) for t in matches]
            self.set_metadata(ws, targets, values, actor, source="import")
            applied += 1
        return {"applied": applied, "skipped": skipped}

    def update_settings(self, ws: str, changes: dict, actor: str) -> dict:
        allowed = {"max_retention_days", "tour_seen", "name"}
        if set(changes) - allowed:
            raise ValueError("Unknown setting")
        if "max_retention_days" in changes:
            v = changes["max_retention_days"]
            if type(v) is not int or not 30 <= v <= 36500:
                raise ValueError("Maximum retention must be between 30 and 36,500 days")
        self.store.ensure_workspace(ws)
        with self.store.tx() as c:
            name = changes.pop("name", None)
            if name is not None:
                c.execute("UPDATE workspaces SET name=? WHERE id=?", (str(name).strip()[:60] or "My workspace", ws))
            s = self.store.update_settings(c, ws, changes)
            if "max_retention_days" in changes:
                append_audit(c, ws, actor_name(actor), "settings.changed", "workspace", changes)
        return s

    # ================================================================ time machine

    def diff(self, ws: str, a_seq: int, b_seq: int) -> dict:
        known = {s["seq"] for s in self.scans(ws)}
        missing = [s for s in (a_seq, b_seq) if s not in known]
        if missing:
            raise KeyError(f"Scan #{missing[0]} not found")
        a = self.view(ws, a_seq, at_scan_time=True)
        b = self.view(ws, b_seq, at_scan_time=True)
        ra = {r["key"]: r for r in a["rows"]}
        rb = {r["key"]: r for r in b["rows"]}
        def brief(r):
            return {k: r[k] for k in ("pt_id", "key", "source", "table", "column", "class", "confidence", "band", "status")}
        new = [brief(r) for k, r in rb.items() if r["detected_class"] != NOT_PERSONAL and (k not in ra or ra[k]["detected_class"] == NOT_PERSONAL)]
        removed = [brief(r) for k, r in ra.items() if r["detected_class"] != NOT_PERSONAL and k not in rb]
        class_changes, conf_changes = [], []
        for k in ra.keys() & rb.keys():
            x, y = ra[k], rb[k]
            if x["detected_class"] != y["detected_class"] and x["detected_class"] != NOT_PERSONAL and y["detected_class"] != NOT_PERSONAL:
                class_changes.append(brief(y) | {"before": x["detected_class"], "after": y["detected_class"]})
            elif y["detected_class"] != NOT_PERSONAL and (x["band"] != y["band"] or abs(x["confidence"] - y["confidence"]) >= 0.1):
                conf_changes.append(brief(y) | {"before": x["confidence"], "after": y["confidence"], "before_band": x["band"]})
        ga = {(k, g["field"], g["severity"]) for k, r in ra.items() for g in r["gaps"]}
        gb = {(k, g["field"], g["severity"]) for k, r in rb.items() for g in r["gaps"]}
        name = {k: f"{r['table']}.{r['column']}" for k, r in {**ra, **rb}.items()}
        pt = {k: r["pt_id"] for k, r in {**ra, **rb}.items()}
        opened = [{"key": k, "pt_id": pt[k], "column": name[k], "field": f, "severity": s} for k, f, s in sorted(gb - ga)]
        closed = [{"key": k, "pt_id": pt[k], "column": name[k], "field": f, "severity": s} for k, f, s in sorted(ga - gb)]
        return {"a": a_seq, "b": b_seq, "new": new, "removed": removed, "class_changes": class_changes,
                "confidence_changes": conf_changes, "gaps_opened": opened, "gaps_closed": closed,
                "summary": {"new": len(new), "removed": len(removed), "class_changes": len(class_changes),
                            "confidence_changes": len(conf_changes), "gaps_opened": len(opened), "gaps_closed": len(closed)}}

    def drift(self, ws: str) -> list[dict]:
        scans = self.scans(ws)
        alerts = []
        for i in range(1, len(scans)):
            d = self.diff(ws, scans[i - 1]["seq"], scans[i]["seq"])
            after = {r["key"]: r for r in self.view(ws, scans[i]["seq"], at_scan_time=True)["rows"]}
            # drift = change inside a source that was already scanned; a brand-new source is onboarding
            seen_sources = {s["source_id"] for s in scans[:i]}
            for n in d["new"]:
                if n["key"].split("/")[0] not in seen_sources:
                    continue
                r = after.get(n["key"])
                no_purpose = r is not None and not r["meta"]["purpose"]["value"]
                alerts.append({"scan_seq": scans[i]["seq"], "at": scans[i]["created_at"], "pt_id": n["pt_id"], "key": n["key"],
                               "column": f"{n['table']}.{n['column']}", "class": n["class"],
                               "severity": "High" if no_purpose else "Medium",
                               "message": f"{n['table']}.{n['column']} appeared in scan #{scans[i]['seq']}" +
                                          (" with no declared purpose" if no_purpose else "")})
            for cch in d["class_changes"]:
                alerts.append({"scan_seq": scans[i]["seq"], "at": scans[i]["created_at"], "pt_id": cch["pt_id"], "key": cch["key"],
                               "column": f"{cch['table']}.{cch['column']}", "class": cch["after"], "severity": "Medium",
                               "message": f"{cch['table']}.{cch['column']} changed from {cch['before']} to {cch['after']} in scan #{scans[i]['seq']}"})
        return alerts

    def timeline(self, ws: str) -> list[dict]:
        out = []
        for s in self.scans(ws):
            v = self.view(ws, s["seq"], at_scan_time=True)
            k = self._kpis(v)
            out.append({"seq": s["seq"], "id": s["id"], "at": s["created_at"], "source": s["source_name"],
                        "ruleset": s["ruleset_version"], "candidates": k["candidates"], "open_gaps": k["open_gaps"],
                        "posture": k["posture"], "columns": k["columns"]})
        return out

    # ================================================================ simulator

    def lineage(self, ws: str, view: dict | None = None) -> dict:
        view = view or self.view(ws)
        rows = view["rows"]
        fps = view["_fingerprints"]
        by_table: dict[str, list] = defaultdict(list)
        for r in rows:
            by_table[f"{r['source_id']}/{r['table']}"].append(r)
        nodes = []
        for key, cols in by_table.items():
            personal = [r for r in cols if r["personal"]]
            t = view["tables"].get(key, {})
            nodes.append({"id": key, "table": cols[0]["table"], "source": cols[0]["source"], "personal": len(personal),
                          "classes": sorted({r["class"] for r in personal}), "rows": t.get("total_rows"),
                          "risk": round(sum(r["risk"] for r in personal), 1)})
        edges = []
        for ka, kb in combinations(sorted(by_table), 2):
            shared = []
            for ra in by_table[ka]:
                linkable_a = ra["personal"] or view["_payloads"].get(ra["key"], {}).get("id_like")
                if not linkable_a:
                    continue
                for rb in by_table[kb]:
                    linkable_b = rb["personal"] or view["_payloads"].get(rb["key"], {}).get("id_like")
                    if not linkable_b:
                        continue
                    na = view["_payloads"][ra["key"]].get("normalised", ra["column"].lower())
                    nb = view["_payloads"][rb["key"]].get("normalised", rb["column"].lower())
                    ov = overlap(fps.get(ra["key"], []), fps.get(rb["key"], []))
                    if na == nb and na not in GENERIC_COLUMNS:
                        shared.append({"a": ra["column"], "b": rb["column"], "via": "same name", "overlap": ov,
                                       "class": ra["class"] if ra["personal"] else "JOIN_KEY"})
                    elif ov >= 0.15:
                        shared.append({"a": ra["column"], "b": rb["column"], "via": "value fingerprint overlap",
                                       "overlap": ov, "class": ra["class"] if ra["personal"] else "JOIN_KEY"})
            if shared:
                edges.append({"id": f"{ka}->{kb}", "source": ka, "target": kb, "shared": shared})
        return {"nodes": nodes, "edges": edges,
                "method": "Tables are linked when personal or key-like columns share a normalised name, or when keyed "
                          "MinHash fingerprints of their values overlap (estimated Jaccard >= 0.15). Raw values are never compared."}

    def blast_radius(self, ws: str, target: str) -> dict:
        view = self.view(ws)
        if target.count("/") == 0:
            keys = [k for k, t in view["tables"].items() if t["source_id"] == target]
        else:
            keys = [target] if target in view["tables"] else []
        if not keys:
            raise KeyError("Table or source not found")
        def summarise(table_keys):
            cols = [r for r in view["rows"] if f"{r['source_id']}/{r['table']}" in table_keys and r["personal"]]
            rules = {r["rule_id"] for r in cols if r["rule_id"]}
            combos = [{"name": n, "severity": s} for n, req, s in COMBOS if req <= rules]
            return cols, combos
        cols, combos = summarise(set(keys))
        lin = self.lineage(ws, view)
        linked = []
        for e in lin["edges"]:
            other = e["target"] if e["source"] in keys else e["source"] if e["target"] in keys else None
            if other and other not in keys:
                linked.append({"key": other, "table": view["tables"].get(other, {}).get("table"),
                               "via": sorted({s["a"] if e["source"] in keys else s["b"] for s in e["shared"]})})
        joined_cols, joined_combos = summarise(set(keys) | {l["key"] for l in linked})
        new_combos = [c for c in joined_combos if c not in combos]
        return {
            "target": target, "tables": [view["tables"][k]["table"] for k in keys],
            "classes": dict(Counter(r["class"] for r in cols)),
            "columns": [{"pt_id": r["pt_id"], "column": f"{r['table']}.{r['column']}", "class": r["class"]} for r in cols],
            "records": sum(view["tables"][k]["total_rows"] for k in keys),
            "combinations": combos, "linked_tables": linked, "combinations_if_joined": new_combos,
            "linked_records": sum(view["tables"].get(l["key"], {}).get("total_rows", 0) for l in linked),
            "label": "Simulation: technical exposure only. Not an assessment of harm or of legal notification duties.",
        }

    def reidentification(self, ws: str) -> dict:
        view = self.view(ws)
        tables = []
        for key, t in view["tables"].items():
            qi = [r for r in view["rows"] if f"{r['source_id']}/{r['table']}" == key and r["quasi_identifier"]]
            tables.append({"key": key, "table": t["table"], "source": t["source"],
                           "quasi_identifiers": [{"column": r["column"], "kind": r["quasi_identifier"]} for r in qi],
                           "kanon": t["kanon"]})
        tables.sort(key=lambda x: -(x["kanon"]["exact"]["unique_pct"] if x["kanon"] else -1))
        return {"tables": tables,
                "method": "k-anonymity is estimated on the in-memory sample by grouping rows on their quasi-identifier "
                          "values (exact, and generalised: birth year in 5-year bands, age in 5-year bands, 3-digit PIN prefix). "
                          "Only aggregates (minimum k, % unique rows) are stored."}

    def retention_whatif(self, ws: str, assume: dict | None = None) -> dict:
        """assume: {table_key: days} hypothetical retention per table (not saved)."""
        view = self.view(ws)
        assume = assume or {}
        out_tables, never = [], []
        for key, t in view["tables"].items():
            cols = [r for r in view["rows"] if f"{r['source_id']}/{r['table']}" == key and r["personal"]]
            if not cols:
                continue
            hist = t["age_hist"]
            col_out = []
            for r in cols:
                days = assume.get(key) or r["meta"]["retention_days"]
                hypothetical = bool(assume.get(key))
                expired = _expired_share(hist, days) if days else None
                entry = {"pt_id": r["pt_id"], "column": r["column"], "class": r["class"], "retention_days": days,
                         "retention_text": r["meta"]["retention"]["value"], "hypothetical": hypothetical,
                         "expired_pct": expired}
                col_out.append(entry)
                if not days:
                    never.append({"pt_id": r["pt_id"], "column": f"{r['table']}.{r['column']}", "class": r["class"]})
            out_tables.append({"key": key, "table": t["table"], "rows": t["total_rows"], "age_hist": hist, "columns": col_out})
        return {"tables": out_tables, "never_cleaned": never,
                "label": "What-if only. Nothing is deleted and no retention is saved by this simulation."}

    # ================================================================ rules: impact & test

    def impact_preview(self, ws: str, raw: dict) -> dict:
        candidate = validate_ruleset({k: v for k, v in raw.items() if k != "hash"})
        view = self.view(ws)
        hashes_cache: dict[str, dict] = {}
        changes, approx = [], 0
        for r in view["rows"]:
            p = view["_payloads"][r["key"]]
            v = r["rule_version"]
            if v not in hashes_cache:
                try:
                    hashes_cache[v] = rule_hashes(self.ruleset_version(ws, v))
                except KeyError:
                    hashes_cache[v] = {}
            res = rescore(r["column"], p["profile"], p.get("rule_signals", {}), candidate, hashes_cache[v],
                          p.get("constant_prefix", False))
            approx += int(res["approximate"])
            if res["class"] != r["detected_class"] or res["band"] != r["band"]:
                changes.append({"pt_id": r["pt_id"], "column": f"{r['table']}.{r['column']}", "before": r["detected_class"],
                                "after": res["class"], "before_band": r["band"], "after_band": res["band"],
                                "approximate": res["approximate"]})
        return {"changes": changes[:200], "summary": {
            "changed": len(changes),
            "newly_personal": sum(1 for c in changes if c["before"] == NOT_PERSONAL and c["after"] != NOT_PERSONAL),
            "no_longer_personal": sum(1 for c in changes if c["before"] != NOT_PERSONAL and c["after"] == NOT_PERSONAL),
            "class_changed": sum(1 for c in changes if NOT_PERSONAL not in (c["before"], c["after"]) and c["before"] != c["after"]),
            "band_changed": sum(1 for c in changes if c["before"] == c["after"]),
            "approximate": approx, "columns": len(view["rows"])},
            "note": "Re-scored from stored aggregate signals. Rules whose pattern or validator changed need a rescan "
                    "for exact value signals; those results are marked approximate."}

    # ================================================================ user labels (run on my data)

    def set_label(self, ws: str, key: str, true_class: str | None) -> None:
        with self.store.tx() as c:
            if true_class is None:
                c.execute("DELETE FROM user_labels WHERE ws=? AND column_key=?", (ws, key))
                return
            if true_class not in ALL_CLASSES:
                raise ValueError("Unknown class")
            c.execute("INSERT OR REPLACE INTO user_labels VALUES(?,?,?,?)", (ws, key, true_class, now_iso()))

    def user_label_eval(self, ws: str) -> dict:
        from .eval import metrics
        view = self.view(ws)
        with self.store.connect() as c:
            labels = {r["column_key"]: r["true_class"] for r in c.execute("SELECT * FROM user_labels WHERE ws=?", (ws,))}
        pairs = [(labels[r["key"]], r["detected_class"]) for r in view["rows"] if r["key"] in labels]
        out = metrics(pairs) if pairs else None
        return {"labels": labels, "labelled": len(pairs), "metrics": out}

    # ================================================================ audit & workspace

    def audit(self, ws: str) -> list[dict]:
        with self.store.connect() as c:
            return audit_entries(c, ws)

    def verify_audit(self, ws: str) -> dict:
        return verify_chain(self.audit(ws))

    def log_audit(self, ws: str, actor: str, action: str, target: str, payload: dict) -> dict:
        with self.store.tx() as c:
            return append_audit(c, ws, actor_name(actor), action, target, payload)

    def export_workspace(self, ws: str) -> dict:
        info = self.store.ensure_workspace(ws)
        out = {"format": "privacytwin-workspace", "version": __version__, "exported_at": now_iso(),
               "note": "Contains aggregates, metadata and decisions only. No raw values.", "disclaimer": DISCLAIMER,
               "workspace": {k: info[k] for k in ("name", "salt", "settings", "pt_counter")}}
        with self.store.connect() as c:
            for table in ("sources", "scans", "columns", "findings", "table_stats", "reviews", "metadata", "rulesets", "audit", "user_labels"):
                rows = [dict(r) for r in c.execute(f"SELECT * FROM {table} WHERE ws=?", (ws,))]
                for r in rows:
                    r.pop("ws", None)
                    r.pop("id", None) if table in ("reviews", "metadata") else None
                out[table] = rows
        return out

    def import_workspace(self, ws: str, data: dict, actor: str) -> dict:
        if not isinstance(data, dict) or data.get("format") != "privacytwin-workspace":
            raise ValueError("This is not a PrivacyTwin workspace export")
        entries = [r | {"payload": json.loads(r["payload"])} for r in data.get("audit", [])]
        chain = verify_chain(entries)
        if not chain["ok"]:
            raise ValueError(f"The audit chain in this file is broken at entry {chain['broken_at']}; import refused")
        self.store.wipe(ws)
        w = data["workspace"]
        # Fresh source/scan ids so a file can be imported next to its original workspace.
        sid_map = {s["id"]: str(uuid.uuid4()) for s in data.get("sources", [])}
        scan_map = {s["id"]: str(uuid.uuid4()) for s in data.get("scans", [])}

        def rekey(value: str | None) -> str | None:
            if not value:
                return value
            for old, new in sid_map.items():
                if old in value:
                    return value.replace(old, new)
            return value

        data = json.loads(json.dumps(data))
        for s in data.get("sources", []):
            s["id"] = sid_map[s["id"]]
        for s in data.get("scans", []):
            s["id"], s["source_id"] = scan_map[s["id"]], sid_map.get(s["source_id"], s["source_id"])
            receipt = json.loads(s["receipt"])
            receipt["scan_id"] = s["id"]
            s["receipt"] = canonical(receipt)
        for r in data.get("columns", []):
            r["key"], r["source_id"], r["first_scan"] = rekey(r["key"]), sid_map.get(r["source_id"], r["source_id"]), scan_map.get(r["first_scan"], r["first_scan"])
        for r in data.get("findings", []) + data.get("table_stats", []):
            r["scan_id"] = scan_map.get(r["scan_id"], r["scan_id"])
            if "column_key" in r:
                r["column_key"] = rekey(r["column_key"])
        for r in data.get("reviews", []) + data.get("user_labels", []):
            r["column_key"] = rekey(r["column_key"])
            if r.get("decision_scan_id"):
                r["decision_scan_id"] = scan_map.get(r["decision_scan_id"], r["decision_scan_id"])
        for r in data.get("metadata", []):
            r["target"] = rekey(r["target"])
        cols = {
            "sources": ["id", "name", "kind", "origin", "detail", "read_only_verified", "read_only_detail", "created_at"],
            "scans": ["id", "seq", "source_id", "created_at", "ruleset_version", "ruleset_hash", "sample_size", "strategy", "stats", "receipt"],
            "columns": ["key", "pt_id", "source_id", "table_name", "column_name", "first_scan"],
            "findings": ["scan_id", "column_key", "pt_id", "table_name", "column_name", "class", "confidence", "band", "rule_id", "payload"],
            "table_stats": ["scan_id", "table_name", "total_rows", "column_count", "kanon", "age_hist"],
            "reviews": ["column_key", "status", "class_override", "note", "actor", "created_at", "decision_source", "automation_batch", "decision_scan_id"],
            "metadata": ["target", "field", "value", "actor", "created_at"],
            "rulesets": ["version", "hash", "content", "note", "created_at"],
            "audit": ["seq", "ts", "actor", "action", "target", "payload", "prev_hash", "hash"],
            "user_labels": ["column_key", "true_class", "created_at"],
        }
        with self.store.tx() as c:
            c.execute("INSERT INTO workspaces(id,salt,name,settings,pt_counter,created_at) VALUES(?,?,?,?,?,?)",
                      (ws, w["salt"], w["name"], canonical(w["settings"] | {"auto_triage_enabled": False}), int(w["pt_counter"]), now_iso()))
            for table, fields in cols.items():
                for r in data.get(table, []):
                    if table == "reviews":
                        r.setdefault("decision_source", "human")
                    c.execute(f"INSERT INTO {table}(ws,{','.join(fields)}) VALUES(?{',?' * len(fields)})",
                              [ws] + [r.get(f) for f in fields])
        self.log_audit(ws, actor, "workspace.imported", "workspace", {"entries": chain["entries"]})
        return {"imported": {t: len(data.get(t, [])) for t in cols}}


POSTURE_FORMULA = ("score = 100 x (0.35 x metadata coverage + 0.25 x review completion + "
                   "0.25 x (1 - gap severity index) + 0.15 x (1 - re-identification risk))")
POSTURE_LABEL = "Technical posture indicator, not a compliance rating."


def _expired_share(hist: dict | None, days: int) -> float | None:
    if not hist:
        return None
    total = sum(hist["counts"])
    if not total:
        return None
    lower = 0
    older = 0.0
    for edge, count in zip(hist["edges_days"], hist["counts"]):
        if lower >= days:
            older += count
        elif edge > days and count:
            span = min(edge, hist["oldest_days"]) - lower
            if span > 0:
                older += count * max(0.0, (min(edge, hist["oldest_days"]) - days) / span)
        lower = edge
    return round(100 * older / total, 1)
