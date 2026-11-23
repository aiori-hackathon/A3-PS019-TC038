"""FastAPI application.

Security model
  * No login. The browser generates a random workspace key and sends it as
    X-Workspace-Key; the server only ever sees sha256(key), which scopes every query.
  * Writes need X-CSRF-Token = HMAC(secret, workspace | Origin) from GET /api/session,
    and the Origin (when present) must be an allowed frontend origin.
  * Per-IP rate limits, upload size/type validation, CORS locked to the frontend,
    CSP and other security headers on every response, no stack traces to clients.
"""
from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import logging
import os
import re
import secrets
import threading
import time
from collections import defaultdict, deque
from typing import Any, Iterator

import yaml
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from . import DISCLAIMER, __version__
from .assistant import SUGGESTED, ai_summary, answer, explain, llm_status
from .guard import CHAT_LIMIT, CHAT_WINDOW, MAX_QUESTION_CHARS, SAFE_REPLY, ChatLimiter
from .guard import check as check_prompt
from .demo import load_demo
from .detect import classify_column
from .eval import cached_benchmark, to_csv
from .evidence import public_row, verify_pack, build_pack
from .gaps import METADATA_FIELDS, suggest
from .ingest import (MAX_CSV_BYTES, MAX_SQLITE_BYTES, SAMPLE_SIZES, STRATEGIES, check_options, decode, dedupe_headers,
                     detect_kind, read_csv, read_postgres, read_sqlite_bytes, sniff_delimiter)
from .masking import SYNTHETIC_EXAMPLES, apply_strategy, mask
from .rules import ALL_CLASSES, export as export_rules, parse_import, validate_rule
from .store import Store
from .twin import STATUSES, Twin

log = logging.getLogger("privacytwin")

KEY_RE = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
PUBLIC_PATHS = {"/health", "/api/health", "/", "/docs", "/openapi.json"}
CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
# For the built frontend when the API serves it (single-container deployment).
PAGE_CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
            "base-uri 'self'; form-action 'self'; object-src 'none'")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReviewIn(Strict):
    keys: list[str] = Field(min_length=1, max_length=2000)
    status: str
    note: str = Field(default="", max_length=1000)
    class_override: str | None = None


class UndoReviewIn(Strict):
    previous: list[dict] = Field(max_length=2000)


class AutoTriageIn(Strict):
    enabled: bool
    threshold: float = Field(default=0.95, ge=0.9, le=1.0)


class UndoAutoTriageIn(Strict):
    batch_id: str = Field(min_length=1, max_length=80)


class MetadataIn(Strict):
    targets: list[str] = Field(min_length=1, max_length=2000)
    values: dict[str, str]


class UndoMetadataIn(Strict):
    previous: list[dict] = Field(max_length=2000)


class SettingsIn(Strict):
    max_retention_days: int | None = None
    tour_seen: bool | None = None
    name: str | None = Field(default=None, max_length=60)


class RulesetIn(Strict):
    ruleset: dict[str, Any]
    note: str = Field(default="", max_length=200)
    part: str = "minor"


class ActivateIn(Strict):
    version: str


class RuleTestIn(Strict):
    rule: dict[str, Any]
    header: str = Field(default="", max_length=200)
    samples: list[str] = Field(default_factory=list, max_length=200)


class ImpactIn(Strict):
    ruleset: dict[str, Any]


class LabelIn(Strict):
    key: str
    true_class: str | None


class RetentionIn(Strict):
    assume: dict[str, int] = Field(default_factory=dict)


class ExplainIn(Strict):
    pt_id: str = Field(max_length=20)


class AskIn(Strict):
    question: str = Field(max_length=2000)  # hard cap; the guard enforces the real limit


class PostgresIn(Strict):
    dsn: str = Field(max_length=1000)
    name: str = Field(default="PostgreSQL", max_length=120)
    sample_size: int = 1000
    strategy: str = "random"


class MaskPreviewIn(Strict):
    pt_id: str
    strategy: str


class WipeIn(Strict):
    confirm: str


class DemoIn(Strict):
    reset: bool = False


class RateLimiter:
    def __init__(self):
        self.hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str, limit: int, window: float) -> bool:
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True


def _safe(fn):
    try:
        fn()
    except Exception:  # pragma: no cover - warm-up is best effort
        log.exception("Benchmark warm-up failed")


def allowed_origins() -> list[str]:
    raw = os.environ.get("PRIVACYTWIN_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    return [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]


def create_app(db_path: str | None = None) -> FastAPI:
    store = Store(db_path)
    twin = Twin(store)
    secret = (os.environ.get("PRIVACYTWIN_SECRET") or secrets.token_hex(32)).encode()
    origins = allowed_origins()
    limiter = RateLimiter()
    chat_limiter = ChatLimiter()
    app = FastAPI(title="PrivacyTwin API", version=__version__, docs_url=None, redoc_url=None)
    app.state.twin = twin
    if os.environ.get("PRIVACYTWIN_WARM_EVAL", "1") == "1":
        # Warm the benchmark cache so the Evaluation page answers instantly.
        threading.Thread(target=lambda: _safe(cached_benchmark), daemon=True).start()

    def csrf_for(ws: str, origin: str) -> str:
        return hmac.new(secret, f"{ws}|{origin}".encode(), hashlib.sha256).hexdigest()

    static_dir = os.environ.get("PRIVACYTWIN_STATIC_DIR", "")

    def same_host(request: Request, origin: str) -> bool:
        """True when the page and the API share one address (single-container deployment)."""
        host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
        return bool(origin) and origin.split("://", 1)[-1] == host

    def csrf_origin(request: Request) -> str:
        """Origin the CSRF token is bound to. Browsers omit Origin on same-origin GETs but send it
        on POSTs, so "no Origin" and "same host" are treated as one binding."""
        origin = (request.headers.get("origin") or "").rstrip("/")
        if not origin or same_host(request, origin):
            return "self"
        return origin

    @app.middleware("http")
    async def guard(request: Request, call_next):
        path = request.url.path
        ip = request.client.host if request.client else "?"
        if request.method == "OPTIONS":
            return await call_next(request)
        if path.startswith("/api/") and path not in PUBLIC_PATHS:
            if not limiter.allow(f"all:{ip}", 600, 60):
                return JSONResponse({"detail": "Too many requests. Wait a moment and retry.", "code": "rate_limited"}, 429)
            key = request.headers.get("x-workspace-key", "")
            if not KEY_RE.match(key):
                return JSONResponse({"detail": "Missing or invalid workspace key.", "code": "workspace"}, 401)
            ws = hashlib.sha256(key.encode()).hexdigest()[:32]
            request.state.ws = ws
            origin = (request.headers.get("origin") or "").rstrip("/")
            if origin and origin not in origins and not same_host(request, origin):
                return JSONResponse({"detail": "Origin not allowed.", "code": "origin"}, 403)
            if request.method in WRITE_METHODS:
                token = request.headers.get("x-csrf-token", "")
                if not hmac.compare_digest(token, csrf_for(ws, csrf_origin(request))):
                    return JSONResponse({"detail": "Security token expired. Retrying.", "code": "csrf"}, 403)
                if path in ("/api/scan", "/api/scan/postgres", "/api/demo", "/api/evidence", "/api/auto-triage/run") and not limiter.allow(f"heavy:{ip}", 40, 600):
                    return JSONResponse({"detail": "Scan limit reached (40 per 10 minutes). Try again shortly.", "code": "rate_limited"}, 429)
            request.state.actor = re.sub(r"[^\w .@-]", "", request.headers.get("x-actor", "reviewer"))[:60] or "reviewer"
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = CSP if (path.startswith("/api/") or not static_dir) else PAGE_CSP
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cross-Origin-Resource-Policy"] = "cross-origin"
        if path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST", "PUT", "DELETE"],
                       allow_headers=["Content-Type", "X-Workspace-Key", "X-CSRF-Token", "X-Actor"],
                       expose_headers=["Content-Disposition", "X-Manifest-SHA256"], max_age=600)

    @app.exception_handler(ValueError)
    async def bad_request(_, exc):
        return JSONResponse({"detail": str(exc)[:500]}, 400)

    @app.exception_handler(KeyError)
    async def not_found(_, exc):
        return JSONResponse({"detail": str(exc).strip("'\"")[:300]}, 404)

    @app.exception_handler(Exception)
    async def unexpected(_, exc):
        log.exception("Unhandled error")
        return JSONResponse({"detail": "Something went wrong on the server. Your data is unchanged; please retry."}, 500)

    def ws_of(request: Request) -> str:
        return request.state.ws

    def actor_of(request: Request) -> str:
        return getattr(request.state, "actor", "reviewer")

    # ------------------------------------------------------------ health & session

    @app.get("/health")
    @app.get("/api/health")
    def health():
        return {"status": "ok", "service": "privacytwin", "version": __version__}

    if not static_dir:
        app.get("/")(health)

    @app.get("/api/session")
    def session(request: Request):
        info = store.ensure_workspace(ws_of(request))
        with store.connect() as c:
            n_scans = c.execute("SELECT COUNT(*) FROM scans WHERE ws=?", (info["id"],)).fetchone()[0]
        return {"csrf": csrf_for(info["id"], csrf_origin(request)), "workspace": {"name": info["name"], "settings": info["settings"],
                "created_at": info["created_at"], "scans": n_scans},
                "version": __version__, "disclaimer": DISCLAIMER, "llm": llm_status(),
                "limits": {"csv_mb": MAX_CSV_BYTES // 2**20, "sqlite_mb": MAX_SQLITE_BYTES // 2**20,
                           "sample_sizes": SAMPLE_SIZES, "strategies": STRATEGIES, "default_sample": 1000}}

    # ------------------------------------------------------------ scanning

    def stream(events: Iterator[dict]) -> StreamingResponse:
        def gen():
            try:
                for e in events:
                    yield json.dumps(e, default=str) + "\n"
            except ValueError as exc:
                yield json.dumps({"type": "error", "detail": str(exc)[:500]}) + "\n"
            except Exception:
                log.exception("Scan failed")
                yield json.dumps({"type": "error", "detail": "The scan failed unexpectedly. Nothing was saved."}) + "\n"
        return StreamingResponse(gen(), media_type="application/x-ndjson", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    @app.post("/api/scan")
    async def scan_upload(request: Request, file: UploadFile = File(...), sample_size: int = Form(1000),
                          strategy: str = Form("random"), name: str = Form("")):
        check_options(sample_size, strategy)
        data = await file.read(MAX_SQLITE_BYTES + 1)
        filename = (file.filename or "upload.csv")[:200]
        kind = detect_kind(filename, data)
        label = (name.strip() or filename)[:120]
        ws, actor = ws_of(request), actor_of(request)

        def events():
            yield {"type": "reading", "file": filename, "kind": kind, "bytes": len(data)}
            read = read_csv(data, filename, sample_size, strategy) if kind == "CSV" else read_sqlite_bytes(data, sample_size, strategy)
            yield from twin.scan(ws, read, label, "upload", sample_size, strategy, actor,
                                 {"filename": filename, "bytes": len(data)})
        return stream(events())

    @app.post("/api/scan/postgres")
    def scan_postgres(request: Request, body: PostgresIn):
        check_options(body.sample_size, body.strategy)
        ws, actor = ws_of(request), actor_of(request)
        redacted = re.sub(r"(://[^:/@]+):[^@]*@", r"\1:***@", body.dsn)
        redacted = re.sub(r"password=\S+", "password=***", redacted)

        def events():
            yield {"type": "reading", "file": redacted, "kind": "PostgreSQL"}
            read = read_postgres(body.dsn, body.sample_size, body.strategy)
            yield from twin.scan(ws, read, body.name, "postgres", body.sample_size, body.strategy, actor, {"dsn": redacted})
        return stream(events())

    @app.post("/api/demo")
    def demo(request: Request, body: DemoIn | None = None):
        ws = ws_of(request)
        if body and body.reset:
            store.wipe(ws)
        return load_demo(twin, ws, actor_of(request))

    @app.get("/api/sources")
    def sources(request: Request):
        ws = ws_of(request)
        scans = twin.scans(ws)
        with store.connect() as c:
            rows = [dict(r) for r in c.execute("SELECT * FROM sources WHERE ws=? ORDER BY created_at", (ws,))]
        out = []
        for r in rows:
            own = [s for s in scans if s["source_id"] == r["id"]]
            last = own[-1] if own else None
            out.append({"id": r["id"], "name": r["name"], "kind": r["kind"], "origin": r["origin"],
                        "detail": json.loads(r["detail"]), "read_only_verified": bool(r["read_only_verified"]),
                        "read_only_detail": r["read_only_detail"], "created_at": r["created_at"], "scans": len(own),
                        "last_scan": last, "receipt": twin.receipt(ws, last["id"]) if last else None})
        return {"sources": out}

    @app.get("/api/scans")
    def scans(request: Request):
        return {"scans": twin.scans(ws_of(request))}

    @app.get("/api/scans/{scan_id}/receipt")
    def receipt(request: Request, scan_id: str):
        return twin.receipt(ws_of(request), scan_id)

    # ------------------------------------------------------------ views

    @app.get("/api/overview")
    def overview(request: Request, scan: int | None = None):
        return twin.overview(ws_of(request), scan)

    @app.get("/api/inventory")
    def inventory(request: Request, scan: int | None = None):
        v = twin.view(ws_of(request), scan)
        return {"rows": [public_row(r) for r in v["rows"]], "tables": list(v["tables"].values()),
                "snapshot": [{"seq": s["seq"], "id": s["id"]} for s in v["snapshot"]]}

    @app.get("/api/findings/{pt_id}")
    def finding(request: Request, pt_id: str):
        ws = ws_of(request)
        v = twin.view(ws)
        row = next((r for r in v["rows"] if r["pt_id"] == pt_id), None)
        with store.connect() as c:
            col = c.execute("SELECT key FROM columns WHERE ws=? AND pt_id=?", (ws, pt_id)).fetchone()
            if not col:
                raise KeyError(f"Finding {pt_id} not found")
            hist = c.execute("""SELECT f.class, f.confidence, f.band, s.seq, s.created_at, s.ruleset_version FROM findings f
                                JOIN scans s ON s.id=f.scan_id WHERE f.ws=? AND f.column_key=? ORDER BY s.seq""", (ws, col["key"])).fetchall()
            reviews = c.execute("SELECT status, class_override, note, actor, created_at, decision_source, automation_batch FROM reviews WHERE ws=? AND column_key=? ORDER BY id",
                                (ws, col["key"])).fetchall()
        if row is None:
            raise KeyError(f"Finding {pt_id} is not in the current snapshot")
        audit = [e for e in twin.audit(ws) if e["target"] == pt_id][-20:]
        sug = suggest(row["table"], row["source"])
        return {"finding": public_row(row), "history": [dict(h) for h in hist], "reviews": [dict(r) for r in reviews],
                "audit": audit, "suggestion": {k: v for k, v in sug.items() if k in METADATA_FIELDS and not row["meta"][k]["value"]},
                "suggestion_basis": sug["basis"]}

    @app.get("/api/review-queue")
    def review_queue(request: Request):
        v = twin.view(ws_of(request))
        rows = [r for r in v["rows"] if r["detected_class"] != "NOT_PERSONAL" or r["status"] != "candidate"]
        order = {"candidate": 0, "needs_info": 1, "confirmed": 2, "rejected": 3}
        rows.sort(key=lambda r: (order[r["status"]], -r["risk"], -r["confidence"]))
        return {"rows": [public_row(r) for r in rows], "statuses": STATUSES, "classes": ALL_CLASSES}

    # ------------------------------------------------------------ reviews

    @app.get("/api/auto-triage")
    def auto_triage_status(request: Request):
        return twin.auto_triage_status(ws_of(request))

    @app.post("/api/auto-triage/settings")
    def auto_triage_settings(request: Request, body: AutoTriageIn):
        return twin.configure_auto_triage(ws_of(request), body.enabled, body.threshold, actor_of(request))

    @app.post("/api/auto-triage/run")
    def auto_triage_run(request: Request):
        return twin.auto_triage(ws_of(request))

    @app.post("/api/auto-triage/undo")
    def auto_triage_undo(request: Request, body: UndoAutoTriageIn):
        return twin.undo_auto_triage(ws_of(request), body.batch_id, actor_of(request))

    @app.post("/api/reviews")
    def review(request: Request, body: ReviewIn):
        return twin.review(ws_of(request), body.keys, body.status, body.note, actor_of(request), body.class_override)

    @app.post("/api/reviews/undo")
    def review_undo(request: Request, body: UndoReviewIn):
        return twin.undo_reviews(ws_of(request), body.previous, actor_of(request))

    # ------------------------------------------------------------ metadata

    @app.get("/api/metadata")
    def metadata(request: Request):
        return twin.metadata_overview(ws_of(request))

    @app.post("/api/metadata")
    def set_metadata(request: Request, body: MetadataIn):
        return twin.set_metadata(ws_of(request), body.targets, body.values, actor_of(request))

    @app.post("/api/metadata/undo")
    def undo_metadata(request: Request, body: UndoMetadataIn):
        n = 0
        for p in body.previous:
            twin.set_metadata(ws_of(request), [p["target"]], p["values"], actor_of(request), source="undo")
            n += 1
        return {"restored": n}

    @app.post("/api/metadata/import")
    async def import_metadata(request: Request, file: UploadFile = File(...)):
        data = await file.read(2 * 1024 * 1024 + 1)
        if len(data) > 2 * 1024 * 1024:
            raise ValueError("Metadata file exceeds 2 MB")
        text, _ = decode(data)
        name = (file.filename or "").lower()
        if name.endswith((".yaml", ".yml", ".json")):
            parsed = yaml.safe_load(text)
            records = parsed.get("metadata", parsed) if isinstance(parsed, dict) else parsed
            if not isinstance(records, list):
                raise ValueError("YAML/JSON must contain a list of records (or a 'metadata' list)")
        else:
            reader = csv.DictReader(io.StringIO(text), delimiter=sniff_delimiter(text))
            records = list(reader)
        return twin.import_metadata(ws_of(request), [r for r in records if isinstance(r, dict)], actor_of(request))

    @app.get("/api/metadata/template")
    def metadata_template(format: str = "csv"):
        fields = ["source", "table", "column", *METADATA_FIELDS]
        example = {"source": "Acme Fintech India (synthetic)", "table": "customers", "column": "",
                   "purpose": "Account management", "retention": "3 years", "owner": "Customer operations",
                   "legal_basis": "Contract (declared by owner)", "system_of_record": "Core banking"}
        if format == "yaml":
            body = ("# PrivacyTwin metadata template. Leave 'column' empty to declare for the whole table.\n"
                    "# Column declarations override table declarations field by field.\n" + yaml.safe_dump({"metadata": [example]}, sort_keys=False))
            return Response(body, media_type="application/x-yaml", headers={"Content-Disposition": 'attachment; filename="privacytwin-metadata-template.yaml"'})
        out = io.StringIO()
        w = csv.DictWriter(out, fieldnames=fields)
        w.writeheader()
        w.writerow(example)
        return Response(out.getvalue(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="privacytwin-metadata-template.csv"'})

    @app.put("/api/settings")
    def settings(request: Request, body: SettingsIn):
        return twin.update_settings(ws_of(request), body.model_dump(exclude_none=True), actor_of(request))

    # ------------------------------------------------------------ rules

    @app.get("/api/rules")
    def rules(request: Request):
        active, versions = twin.rulesets(ws_of(request))
        return {"active": active, "versions": versions}

    @app.get("/api/rules/export")
    def rules_export(request: Request, format: str = "yaml", version: str | None = None):
        rs = twin.ruleset_version(ws_of(request), version) if version else twin.rulesets(ws_of(request))[0]
        rs = {k: v for k, v in rs.items() if k != "hash"}
        fmt = "json" if format == "json" else "yaml"
        return Response(export_rules(rs, fmt), media_type="application/json" if fmt == "json" else "application/x-yaml",
                        headers={"Content-Disposition": f'attachment; filename="privacytwin-rules-{rs["version"]}.{fmt}"'})

    @app.get("/api/rules/{version}")
    def rules_version(request: Request, version: str):
        return twin.ruleset_version(ws_of(request), version)

    @app.post("/api/rules")
    def rules_save(request: Request, body: RulesetIn):
        if body.part not in ("major", "minor", "patch"):
            raise ValueError("part must be major, minor or patch")
        return twin.save_ruleset(ws_of(request), body.ruleset, body.note, actor_of(request), body.part)

    @app.post("/api/rules/activate")
    def rules_activate(request: Request, body: ActivateIn):
        return twin.activate_ruleset(ws_of(request), body.version, actor_of(request))

    @app.post("/api/rules/import")
    async def rules_import(file: UploadFile = File(...)):
        data = await file.read(500_001)
        text, _ = decode(data)
        return {"ruleset": parse_import(text)}

    @app.post("/api/rules/impact")
    def rules_impact(request: Request, body: ImpactIn):
        return twin.impact_preview(ws_of(request), body.ruleset)

    @app.post("/api/rules/test")
    def rules_test(request: Request, body: RuleTestIn):
        rule = validate_rule(body.rule)
        active, _ = twin.rulesets(ws_of(request))
        test_set = {**active, "rules": [rule | {"enabled": True}]}
        from .detect import header_signal, normalise_header, value_signals
        _, tokens = normalise_header(body.header or "col")
        out = []
        cache: dict = {}
        for s in body.samples[:200]:
            s = str(s)[:300]
            if not s.strip():
                continue
            v, c, e, timed_out = value_signals(rule, [s.strip()], cache)
            out.append({"masked": mask(s, rule["id"]) if (v and rule["id"] in SYNTHETIC_EXAMPLES) else mask(s, None),
                        "matches": bool(v), "valid": bool(c), "embedded": bool(e), "timed_out": timed_out})
        values = [s.strip() for s in body.samples if str(s).strip()]
        col = classify_column("test", body.header or "col", values, test_set, "test") if values or body.header else None
        h = header_signal(rule, tokens)
        return {"samples": out, "header": {"matched": bool(h[0]), "keyword": h[1], "excluded_by": h[2]},
                "column": {k: col[k] for k in ("class", "confidence", "band", "signals", "rationale")} if col else None,
                "note": "Test strings are processed in memory and are not stored."}

    # ------------------------------------------------------------ time machine & simulations

    @app.get("/api/timeline")
    def timeline(request: Request):
        ws = ws_of(request)
        return {"scans": twin.timeline(ws), "drift": twin.drift(ws)}

    @app.get("/api/diff")
    def diff(request: Request, a: int, b: int):
        return twin.diff(ws_of(request), a, b)

    @app.get("/api/lineage")
    def lineage(request: Request):
        return twin.lineage(ws_of(request))

    @app.get("/api/blast")
    def blast(request: Request, target: str):
        return twin.blast_radius(ws_of(request), target)

    @app.get("/api/reid")
    def reid(request: Request):
        return twin.reidentification(ws_of(request))

    @app.post("/api/retention")
    def retention(request: Request, body: RetentionIn):
        if any(not 1 <= d <= 36500 for d in body.assume.values()):
            raise ValueError("Hypothetical retention must be 1-36,500 days")
        return twin.retention_whatif(ws_of(request), body.assume)

    @app.get("/api/posture")
    def posture(request: Request):
        return twin.posture(twin.view(ws_of(request)))

    # ------------------------------------------------------------ evaluation

    @app.get("/api/evaluation")
    def evaluation(request: Request):
        ws = ws_of(request)
        active, _ = twin.rulesets(ws)
        return {"benchmark": cached_benchmark({k: v for k, v in active.items() if k != "hash"}),
                "human": twin.human_precision(ws), "mine": twin.user_label_eval(ws)}

    @app.get("/api/evaluation/public")
    def evaluation_public():
        return cached_benchmark()

    @app.get("/api/evaluation/export")
    def evaluation_export(request: Request, format: str = "json"):
        active, _ = twin.rulesets(ws_of(request))
        result = cached_benchmark({k: v for k, v in active.items() if k != "hash"})
        if format == "csv":
            return Response(to_csv(result), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="privacytwin-evaluation.csv"'})
        return Response(json.dumps(result, indent=2), media_type="application/json",
                        headers={"Content-Disposition": 'attachment; filename="privacytwin-evaluation.json"'})

    @app.post("/api/labels")
    def label(request: Request, body: LabelIn):
        twin.set_label(ws_of(request), body.key, body.true_class)
        return twin.user_label_eval(ws_of(request))

    # ------------------------------------------------------------ audit

    @app.get("/api/audit")
    def audit(request: Request):
        return {"entries": twin.audit(ws_of(request))}

    @app.get("/api/audit/verify")
    def audit_verify(request: Request):
        return twin.verify_audit(ws_of(request))

    # ------------------------------------------------------------ evidence

    @app.post("/api/evidence")
    def evidence(request: Request):
        data, meta = build_pack(twin, ws_of(request), actor_of(request))
        stamp = time.strftime("%Y%m%d-%H%M%S")
        return Response(data, media_type="application/zip", headers={
            "Content-Disposition": f'attachment; filename="privacytwin-evidence-{stamp}.zip"',
            "X-Manifest-SHA256": meta["manifest_sha256"]})

    @app.post("/api/evidence/verify")
    async def evidence_verify(request: Request, file: UploadFile = File(...)):
        data = await file.read(30 * 1024 * 1024 + 1)
        return verify_pack(data, twin, ws_of(request))

    # ------------------------------------------------------------ masking

    @app.post("/api/mask/preview")
    def mask_preview(request: Request, body: MaskPreviewIn):
        if body.strategy not in ("partial", "hash", "tokenise", "redact"):
            raise ValueError("Strategy must be partial, hash, tokenise or redact")
        v = twin.view(ws_of(request))
        row = next((r for r in v["rows"] if r["pt_id"] == body.pt_id), None)
        if not row:
            raise KeyError("Finding not found")
        example = SYNTHETIC_EXAMPLES.get(row["rule_id"] or "", "Sample text 123")
        info = store.ensure_workspace(ws_of(request))
        return {"example": example, "result": apply_strategy(example, body.strategy, row["rule_id"], info["salt"]),
                "note": "Illustrative synthetic value. PrivacyTwin does not keep your raw values, so previews use an invented example."}

    @app.post("/api/mask/csv")
    async def mask_csv(request: Request, file: UploadFile = File(...), strategy: str = Form("partial")):
        if strategy not in ("partial", "hash", "tokenise", "redact"):
            raise ValueError("Strategy must be partial, hash, tokenise or redact")
        data = await file.read(MAX_CSV_BYTES + 1)
        if len(data) > MAX_CSV_BYTES:
            raise ValueError("CSV exceeds the 20 MB limit")
        if detect_kind(file.filename or "x.csv", data) != "CSV":
            raise ValueError("Masked copies are available for CSV files")
        ws = ws_of(request)
        info = store.ensure_workspace(ws)
        active, _ = twin.rulesets(ws)
        text, _ = decode(data)
        del data
        delim = sniff_delimiter(text)
        rows = list(csv.reader(io.StringIO(text), delimiter=delim))
        del text
        if not rows:
            raise ValueError("The CSV file is empty")
        headers, _ = dedupe_headers(rows[0])
        body_rows = rows[1:]
        rules = []
        for i, h in enumerate(headers):
            res = classify_column("csv", h, [r[i] if i < len(r) else "" for r in body_rows[:1000]], active, info["salt"])
            rules.append(res["rule_id"] if res["class"] != "NOT_PERSONAL" else None)
        twin.log_audit(ws, actor_of(request), "mask.csv", "masked-copy",
                       {"columns_masked": sum(1 for r in rules if r), "strategy": strategy, "rows": len(body_rows)})

        def gen():
            out = io.StringIO()
            w = csv.writer(out)
            w.writerow(headers)
            for r in body_rows:
                w.writerow([apply_strategy(v, strategy, rules[i], info["salt"]) if i < len(rules) and rules[i] and v else v
                            for i, v in enumerate(r)])
                if out.tell() > 64_000:
                    yield out.getvalue()
                    out.seek(0)
                    out.truncate()
            yield out.getvalue()
            body_rows.clear()
        stem = re.sub(r"[^\w.-]", "_", (file.filename or "data").rsplit(".", 1)[0])[:60]
        return StreamingResponse(gen(), media_type="text/csv",
                                 headers={"Content-Disposition": f'attachment; filename="{stem}-masked.csv"'})

    # ------------------------------------------------------------ assistant

    @app.get("/api/assistant")
    def assistant_info():
        return {"suggestions": SUGGESTED, "llm": llm_status(), "limits": {"max_chars": MAX_QUESTION_CHARS, "per_window": CHAT_LIMIT, "window_minutes": CHAT_WINDOW // 60}}

    @app.get("/api/ai/summary")
    def ai_summary_route(request: Request):
        return ai_summary(twin, ws_of(request))

    @app.post("/api/ai/explain")
    def ai_explain(request: Request, body: ExplainIn):
        if not chat_limiter.allow(ws_of(request)):
            return JSONResponse({"detail": f"AI limit reached ({CHAT_LIMIT} requests per {CHAT_WINDOW // 60} minutes). Try again shortly.", "code": "rate_limited"}, 429)
        return explain(twin, ws_of(request), body.pt_id)

    @app.post("/api/assistant")
    def assistant(request: Request, body: AskIn):
        ws = ws_of(request)
        question, blocked = check_prompt(body.question)  # GuardError (ValueError) -> 400 with a friendly message
        if not chat_limiter.allow(ws):
            return JSONResponse({"detail": f"AI limit reached ({CHAT_LIMIT} questions per {CHAT_WINDOW // 60} minutes). Try again shortly.", "code": "rate_limited"}, 429)
        if blocked:
            twin.log_audit(ws, actor_of(request), "ai.prompt_blocked", "assistant", {"reason": blocked, "chars": len(question)})
            return {"answer": SAFE_REPLY, "findings": [], "docs": [], "mode": "guard", "blocked": blocked,
                    "suggestions": SUGGESTED, "privacy": "Blocked before reaching the LLM.", "disclaimer": DISCLAIMER}
        return answer(twin, ws, question)

    # ------------------------------------------------------------ workspace

    @app.get("/api/workspace/export")
    def ws_export(request: Request):
        body = json.dumps(twin.export_workspace(ws_of(request)), indent=1, default=str)
        return Response(body, media_type="application/json",
                        headers={"Content-Disposition": 'attachment; filename="privacytwin-workspace.json"'})

    @app.post("/api/workspace/import")
    async def ws_import(request: Request, file: UploadFile = File(...)):
        data = await file.read(50 * 1024 * 1024 + 1)
        if len(data) > 50 * 1024 * 1024:
            raise ValueError("Workspace file exceeds 50 MB")
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError as exc:
            raise ValueError("Workspace file is not valid JSON") from exc
        return twin.import_workspace(ws_of(request), parsed, actor_of(request))

    @app.post("/api/workspace/wipe")
    def ws_wipe(request: Request, body: WipeIn):
        if body.confirm != "WIPE":
            raise ValueError("Type WIPE to confirm")
        counts = store.wipe(ws_of(request))
        return {"wiped": True, "deleted": counts, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "message": "Every scan, finding, review, metadata entry, rule version and audit entry in this workspace was deleted."}

    if static_dir:
        # Single-container deployment: serve the built frontend (web/out) next to the API.
        from fastapi.staticfiles import StaticFiles
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="web")

    return app


app = create_app()
