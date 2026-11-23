"""Application database. Stores aggregates, metadata and decisions; never raw values.

Every row carries a workspace id. Review, metadata and audit history is append-only.
"""
from __future__ import annotations

import json
import os
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .rules import canonical, sha256

GENESIS = "0" * 64

SCHEMA = """
CREATE TABLE IF NOT EXISTS workspaces(
  id TEXT PRIMARY KEY, salt TEXT NOT NULL, name TEXT NOT NULL, settings TEXT NOT NULL,
  pt_counter INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sources(
  id TEXT PRIMARY KEY, ws TEXT NOT NULL, name TEXT NOT NULL, kind TEXT NOT NULL, origin TEXT NOT NULL,
  detail TEXT NOT NULL, read_only_verified INTEGER NOT NULL, read_only_detail TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS sources_ws ON sources(ws);
CREATE TABLE IF NOT EXISTS scans(
  id TEXT PRIMARY KEY, ws TEXT NOT NULL, seq INTEGER NOT NULL, source_id TEXT NOT NULL, created_at TEXT NOT NULL,
  ruleset_version TEXT NOT NULL, ruleset_hash TEXT NOT NULL, sample_size INTEGER NOT NULL, strategy TEXT NOT NULL,
  stats TEXT NOT NULL, receipt TEXT NOT NULL, UNIQUE(ws, seq));
CREATE TABLE IF NOT EXISTS columns(
  ws TEXT NOT NULL, key TEXT NOT NULL, pt_id TEXT NOT NULL, source_id TEXT NOT NULL, table_name TEXT NOT NULL,
  column_name TEXT NOT NULL, first_scan TEXT NOT NULL, PRIMARY KEY(ws, key), UNIQUE(ws, pt_id));
CREATE TABLE IF NOT EXISTS findings(
  scan_id TEXT NOT NULL, ws TEXT NOT NULL, column_key TEXT NOT NULL, pt_id TEXT NOT NULL, table_name TEXT NOT NULL,
  column_name TEXT NOT NULL, class TEXT NOT NULL, confidence REAL NOT NULL, band TEXT NOT NULL, rule_id TEXT,
  payload TEXT NOT NULL, PRIMARY KEY(scan_id, column_key));
CREATE INDEX IF NOT EXISTS findings_ws ON findings(ws, column_key);
CREATE TABLE IF NOT EXISTS table_stats(
  scan_id TEXT NOT NULL, ws TEXT NOT NULL, table_name TEXT NOT NULL, total_rows INTEGER NOT NULL,
  column_count INTEGER NOT NULL, kanon TEXT, age_hist TEXT, PRIMARY KEY(scan_id, table_name));
CREATE TABLE IF NOT EXISTS reviews(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ws TEXT NOT NULL, column_key TEXT NOT NULL, status TEXT NOT NULL,
  class_override TEXT, note TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL,
  decision_source TEXT NOT NULL DEFAULT 'human', automation_batch TEXT, decision_scan_id TEXT);
CREATE INDEX IF NOT EXISTS reviews_ws ON reviews(ws, column_key);
CREATE TABLE IF NOT EXISTS metadata(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ws TEXT NOT NULL, target TEXT NOT NULL, field TEXT NOT NULL,
  value TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS metadata_ws ON metadata(ws, target);
CREATE TABLE IF NOT EXISTS rulesets(
  ws TEXT NOT NULL, version TEXT NOT NULL, hash TEXT NOT NULL, content TEXT NOT NULL, note TEXT NOT NULL,
  created_at TEXT NOT NULL, PRIMARY KEY(ws, version));
CREATE TABLE IF NOT EXISTS audit(
  ws TEXT NOT NULL, seq INTEGER NOT NULL, ts TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL,
  target TEXT NOT NULL, payload TEXT NOT NULL, prev_hash TEXT NOT NULL, hash TEXT NOT NULL, PRIMARY KEY(ws, seq));
CREATE TABLE IF NOT EXISTS user_labels(
  ws TEXT NOT NULL, column_key TEXT NOT NULL, true_class TEXT NOT NULL, created_at TEXT NOT NULL,
  PRIMARY KEY(ws, column_key));
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;
"""

DEFAULT_SETTINGS = {"max_retention_days": 3650, "active_ruleset": "1.0.0", "tour_seen": False,
                    "auto_triage_enabled": False, "auto_triage_threshold": 0.95}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or os.environ.get("PRIVACYTWIN_DB", Path("data") / "privacytwin.sqlite3"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self.connect() as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.executescript(SCHEMA)
            # Existing workspaces keep their manual review history on upgrade.
            review_columns = {r['name'] for r in c.execute('PRAGMA table_info(reviews)')}
            if 'decision_source' not in review_columns:
                c.execute("ALTER TABLE reviews ADD COLUMN decision_source TEXT NOT NULL DEFAULT 'human'")
            if 'automation_batch' not in review_columns:
                c.execute('ALTER TABLE reviews ADD COLUMN automation_batch TEXT')
            if 'decision_scan_id' not in review_columns:
                c.execute('ALTER TABLE reviews ADD COLUMN decision_scan_id TEXT')

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=20, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=20000")
        conn.execute("PRAGMA secure_delete=ON")
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def tx(self):
        with self._lock, self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise

    # ------------------------------------------------------------ workspace

    def ensure_workspace(self, ws: str) -> dict:
        with self.connect() as c:
            row = c.execute("SELECT * FROM workspaces WHERE id=?", (ws,)).fetchone()
        if row:
            return dict(row) | {"settings": json.loads(row["settings"])}
        with self.tx() as c:
            c.execute("INSERT OR IGNORE INTO workspaces(id,salt,name,settings,created_at) VALUES(?,?,?,?,?)",
                      (ws, secrets.token_hex(16), "My workspace", canonical(DEFAULT_SETTINGS), now_iso()))
        return self.ensure_workspace(ws)

    def update_settings(self, c, ws: str, changes: dict) -> dict:
        row = c.execute("SELECT settings FROM workspaces WHERE id=?", (ws,)).fetchone()
        settings = json.loads(row["settings"]) | changes
        c.execute("UPDATE workspaces SET settings=? WHERE id=?", (canonical(settings), ws))
        return settings

    def next_pt_id(self, c, ws: str) -> str:
        c.execute("UPDATE workspaces SET pt_counter=pt_counter+1 WHERE id=?", (ws,))
        n = c.execute("SELECT pt_counter FROM workspaces WHERE id=?", (ws,)).fetchone()[0]
        return f"PT-{n:05d}"

    def wipe(self, ws: str) -> dict:
        counts = {}
        with self.tx() as c:
            for table in ("findings", "table_stats", "reviews", "metadata", "rulesets", "columns", "scans",
                          "sources", "user_labels"):
                counts[table] = c.execute(f"DELETE FROM {table} WHERE ws=?", (ws,)).rowcount
            c.execute("DROP TRIGGER IF EXISTS audit_no_update")
            counts["audit"] = c.execute("DELETE FROM audit WHERE ws=?", (ws,)).rowcount
            c.execute("CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;")
            counts["workspaces"] = c.execute("DELETE FROM workspaces WHERE id=?", (ws,)).rowcount
        with self.connect() as c:
            c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        return counts


# ---------------------------------------------------------------- audit chain

def audit_hash(prev_hash: str, entry: dict) -> str:
    return sha256((prev_hash + canonical(entry)).encode())


def append_audit(c, ws: str, actor: str, action: str, target: str, payload: dict | None = None) -> dict:
    last = c.execute("SELECT seq, hash FROM audit WHERE ws=? ORDER BY seq DESC LIMIT 1", (ws,)).fetchone()
    seq = (last["seq"] + 1) if last else 1
    prev = last["hash"] if last else GENESIS
    entry = {"seq": seq, "ts": now_iso(), "actor": actor[:80], "action": action, "target": target,
             "payload": payload or {}}
    h = audit_hash(prev, entry)
    c.execute("INSERT INTO audit(ws,seq,ts,actor,action,target,payload,prev_hash,hash) VALUES(?,?,?,?,?,?,?,?,?)",
              (ws, seq, entry["ts"], entry["actor"], action, target, canonical(entry["payload"]), prev, h))
    return entry | {"prev_hash": prev, "hash": h}


def audit_entries(c, ws: str) -> list[dict]:
    rows = c.execute("SELECT * FROM audit WHERE ws=? ORDER BY seq", (ws,)).fetchall()
    return [{"seq": r["seq"], "ts": r["ts"], "actor": r["actor"], "action": r["action"], "target": r["target"],
             "payload": json.loads(r["payload"]), "prev_hash": r["prev_hash"], "hash": r["hash"]} for r in rows]


def verify_chain(entries: list[dict]) -> dict:
    """Recompute every link. Returns the first broken entry, if any."""
    prev = GENESIS
    for i, e in enumerate(entries):
        body = {k: e[k] for k in ("seq", "ts", "actor", "action", "target", "payload")}
        expected = audit_hash(prev, body)
        if e["prev_hash"] != prev or e["hash"] != expected or e["seq"] != i + 1:
            return {"ok": False, "entries": len(entries), "broken_at": e["seq"],
                    "reason": "previous-hash mismatch" if e["prev_hash"] != prev else
                    ("sequence gap" if e["seq"] != i + 1 else "entry content does not match its hash")}
        prev = e["hash"]
    return {"ok": True, "entries": len(entries), "broken_at": None, "head": prev}
