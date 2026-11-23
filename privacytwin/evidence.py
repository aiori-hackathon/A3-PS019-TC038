"""Evidence pack (ZIP + manifest of SHA-256 hashes) and its verification."""
from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import zipfile

from . import DISCLAIMER, __version__
from .eval import cached_benchmark
from .ingest import now_iso
from .rules import CLASSES, export as export_rules
from .store import verify_chain
from .twin import Twin

CLASS_COLOURS = {"IDENTITY": "#7c6cf0", "CONTACT": "#1f9bd1", "GOVERNMENT_ID": "#d9822b", "FINANCIAL": "#2aa876",
                 "LOCATION": "#d6497a"}
MAX_PACK_BYTES = 30 * 1024 * 1024


def _safe_cell(v) -> str:
    """Neutralise spreadsheet formula injection."""
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def _csv(rows: list[dict], fields: list[str]) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(fields)
    for r in rows:
        w.writerow([_safe_cell(r.get(f)) for f in fields])
    return out.getvalue()


INVENTORY_FIELDS = ["pt_id", "source", "table", "column", "class", "detected_class", "confidence", "band", "rule_id",
                    "rule_version", "status", "signal_header", "signal_value", "signal_validator", "masked_examples",
                    "purpose", "retention", "owner", "legal_basis", "system_of_record", "gaps", "risk", "rationale",
                    "decision_source", "reviewed_by", "review_note", "automation_batch"]


def inventory_rows(view: dict) -> list[dict]:
    out = []
    for r in view["rows"]:
        out.append({
            "pt_id": r["pt_id"], "source": r["source"], "table": r["table"], "column": r["column"], "class": r["class"],
            "detected_class": r["detected_class"], "confidence": r["confidence"], "band": r["band"],
            "rule_id": r["rule_id"] or "", "rule_version": r["rule_version"], "status": r["status"],
            "signal_header": r["signals"]["header"], "signal_value": r["signals"]["value"],
            "signal_validator": r["signals"]["validator"], "masked_examples": " | ".join(r["masked_examples"]),
            **{f: r["meta"][f]["value"] for f in ("purpose", "retention", "owner", "legal_basis", "system_of_record")},
            "gaps": "; ".join(f"{g['severity']}: {g['message']}" for g in r["gaps"]), "risk": r["risk"],
            "rationale": r["rationale"],
            "decision_source": r.get("decision_source"), "reviewed_by": r["reviewed_by"],
            "review_note": r["review_note"], "automation_batch": r.get("automation_batch"),
        })
    return out


def public_row(r: dict) -> dict:
    return {k: v for k, v in r.items() if not k.startswith("_")}


def _bar_svg(data: dict[str, int], colours: dict[str, str], title: str) -> str:
    maxv = max(data.values() or [1]) or 1
    rows = []
    for i, (k, v) in enumerate(data.items()):
        w = 260 * v / maxv
        y = 10 + i * 26
        rows.append(f'<text x="0" y="{y + 13}" font-size="11">{html.escape(k)}</text>'
                    f'<rect x="120" y="{y}" width="{w:.1f}" height="16" rx="3" fill="{colours.get(k, "#888")}"/>'
                    f'<text x="{126 + w:.1f}" y="{y + 13}" font-size="11">{v}</text>')
    h = 20 + 26 * len(data)
    return f'<svg role="img" aria-label="{html.escape(title)}" viewBox="0 0 420 {h}" width="420" height="{h}">{"".join(rows)}</svg>'


def summary_html(view: dict, overview: dict, evaluation: dict, chain: dict, receipts: list[dict], created: str, ws_name: str) -> str:
    k = overview["kpis"]
    p = overview["posture"]
    esc = html.escape
    eval_rows = "".join(
        f"<tr><td>{c}</td><td>{evaluation['per_class'][c]['precision']:.3f}</td><td>{evaluation['per_class'][c]['recall']:.3f}</td>"
        f"<td>{evaluation['per_class'][c]['f1']:.3f}</td><td>{evaluation['per_class'][c]['support']}</td></tr>" for c in CLASSES)
    top = "".join(f"<tr><td>{esc(t['table'])}</td><td>{t['personal']}</td><td>{t['risk']}</td></tr>" for t in overview["top_tables"])
    gaps = "".join(f"<tr><td>{esc(r['pt_id'])}</td><td><code>{esc(r['table'])}.{esc(r['column'])}</code></td><td>{esc(r['class'])}</td>"
                   f"<td>{esc('; '.join(g['severity'] + ': ' + g['message'] for g in r['gaps']))}</td></tr>"
                   for r in sorted(view["rows"], key=lambda r: -r["risk"]) if r["gaps"])[:60000]
    rec = "".join(f"<li>Scan #{x.get('scan_seq')} of {esc(str(x.get('source')))}: {sum(t['rows_sampled'] for t in x['tables'])} rows sampled "
                  f"({esc(x['strategy'])}), processed in memory, values discarded at {esc(x['raw_values_discarded_at'])}.</li>" for x in receipts)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>PrivacyTwin evidence summary</title>
<style>
body{{font:14px/1.5 Inter,system-ui,sans-serif;color:#14181f;margin:32px;max-width:900px}}
h1{{font-size:24px;margin:0 0 4px}} h2{{font-size:16px;margin:28px 0 8px;border-bottom:1px solid #d8dde6;padding-bottom:4px}}
.kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}} .kpi{{border:1px solid #d8dde6;border-radius:10px;padding:10px}}
.kpi b{{display:block;font-size:22px;font-variant-numeric:tabular-nums}} table{{border-collapse:collapse;width:100%;font-size:12px}}
td,th{{border-bottom:1px solid #e6e9ef;padding:4px 6px;text-align:left;vertical-align:top}} code{{font-family:'JetBrains Mono',monospace}}
.ok{{color:#1d7f4e}} .bad{{color:#b42318}} footer{{margin-top:32px;padding-top:8px;border-top:2px solid #14181f;font-weight:600}}
@media print{{body{{margin:12mm}} h2{{break-after:avoid}} tr{{break-inside:avoid}}}}
</style></head><body>
<h1>PrivacyTwin evidence summary</h1>
<p>Workspace <b>{esc(ws_name)}</b> &middot; generated {esc(created)} &middot; PrivacyTwin {__version__}</p>
<p><b>{DISCLAIMER}</b> Every finding is a candidate until a person reviews it.</p>
<h2>Key figures</h2>
<div class="kpis">
<div class="kpi">Sources<b>{k['sources']}</b></div><div class="kpi">Columns scanned<b>{k['columns']}</b></div>
<div class="kpi">Personal-data candidates<b>{k['candidates']}</b></div><div class="kpi">Confirmed<b>{k['confirmed']}</b></div>
<div class="kpi">Open metadata gaps<b>{k['open_gaps']}</b></div><div class="kpi">Reviewed<b>{k['reviewed_pct']}%</b></div>
<div class="kpi">Posture indicator<b>{p['score'] if p['score'] is not None else 'n/a'}</b></div>
<div class="kpi">Audit chain<b class="{'ok' if chain['ok'] else 'bad'}">{'Intact' if chain['ok'] else 'Broken'}</b></div>
</div>
<p style="font-size:12px">Posture: {esc(p['formula'])}. {esc(p['label'])}</p>
<h2>Candidates by class</h2>{_bar_svg(overview['by_class'], CLASS_COLOURS, 'Personal-data candidates by class')}
<h2>Gaps by severity</h2>{_bar_svg(overview['gaps_by_severity'], {'High': '#b42318', 'Medium': '#b54708', 'Low': '#667085'}, 'Metadata gaps by severity')}
<h2>Highest-risk tables</h2><table><tr><th>Table</th><th>Personal fields</th><th>Risk sum</th></tr>{top}</table>
<h2>Open gaps</h2><table><tr><th>ID</th><th>Column</th><th>Class</th><th>Gaps</th></tr>{gaps}</table>
<h2>Detection accuracy (synthetic benchmark)</h2>
<p>{evaluation['columns']} labelled columns; macro F1 <b>{evaluation['macro']['f1']:.3f}</b>. {esc(evaluation['caveat'])}</p>
<table><tr><th>Class</th><th>Precision</th><th>Recall</th><th>F1</th><th>Support</th></tr>{eval_rows}</table>
<h2>Data handling</h2><ul>{rec}</ul>
<p>Raw values are never stored. Only aggregates, masked examples and keyed fingerprints are persisted.</p>
<footer>{DISCLAIMER}</footer>
</body></html>"""


def build_pack(twin: Twin, ws: str, actor: str) -> tuple[bytes, dict]:
    info = twin.store.ensure_workspace(ws)
    view = twin.view(ws)
    if not view["rows"]:
        raise ValueError("Nothing to export yet. Load the demo or scan a source first.")
    overview = twin.overview(ws)
    ruleset, _ = twin.rulesets(ws)
    evaluation = cached_benchmark({k: v for k, v in ruleset.items() if k != "hash"})
    audit = twin.audit(ws)
    chain = verify_chain(audit)
    scans = twin.scans(ws)
    receipts = [twin.receipt(ws, s["id"]) for s in view["snapshot"]]
    created = now_iso()
    inv = inventory_rows(view)
    gap_rows = [{"pt_id": r["pt_id"], "source": r["source"], "table": r["table"], "column": r["column"], "class": r["class"],
                 "field": g["field"], "severity": g["severity"], "message": g["message"]}
                for r in view["rows"] for g in r["gaps"]]
    reviews = [{"pt_id": r["pt_id"], "column": f"{r['table']}.{r['column']}", "status": r["status"], "class": r["class"],
                "detected_class": r["detected_class"], "note": r["review_note"], "reviewed_by": r["reviewed_by"],
                "reviewed_at": r["reviewed_at"]} for r in view["rows"] if r["status"] != "candidate"]
    files: dict[str, str] = {
        "inventory.csv": _csv(inv, INVENTORY_FIELDS),
        "inventory.json": json.dumps([public_row({k: v for k, v in r.items()}) for r in view["rows"]], indent=1, default=str),
        "gaps.csv": _csv(gap_rows, ["pt_id", "source", "table", "column", "class", "field", "severity", "message"]),
        "reviews.json": json.dumps({"reviews": reviews, "human_confirmed_precision": twin.human_precision(ws)}, indent=1),
        "audit_chain.json": json.dumps({"entries": audit, "verification": chain}, indent=1),
        "evaluation.json": json.dumps(evaluation, indent=1),
        "ruleset.yaml": export_rules({k: v for k, v in ruleset.items() if k != "hash"}, "yaml"),
        "data_handling_receipts.json": json.dumps(receipts, indent=1),
        "drift.json": json.dumps(twin.drift(ws), indent=1),
    }
    if len(scans) >= 2:
        files["scan_diff.json"] = json.dumps(twin.diff(ws, scans[-2]["seq"], scans[-1]["seq"]), indent=1)
    files["summary.html"] = summary_html(view, overview, evaluation, chain, receipts, created, info["name"])
    files["README.txt"] = (
        "PrivacyTwin evidence pack\n\n"
        "manifest.json lists the SHA-256 hash of every file in this pack. To verify, upload the ZIP on the\n"
        "Evidence pack page (Verify pack), or recompute each hash yourself, e.g. `sha256sum inventory.csv`.\n"
        "The manifest's own SHA-256 is recorded in the workspace audit chain when the pack is exported.\n"
        "Hashes show the files were not changed after export; they do not prove who created them.\n\n"
        f"{DISCLAIMER}\n")
    encoded = {name: body.encode("utf-8") for name, body in files.items()}
    manifest = {
        "format": "privacytwin-evidence-pack", "version": __version__, "created_at": created,
        "workspace": info["name"],
        "scans": [{"seq": s["seq"], "created_at": s["created_at"], "source": s["source_name"],
                   "ruleset_version": s["ruleset_version"], "ruleset_hash": s["ruleset_hash"]} for s in scans],
        "snapshot": [{"seq": s["seq"], "scan_id": s["id"]} for s in view["snapshot"]],
        "ruleset": {"version": ruleset["version"], "hash": ruleset["hash"]},
        "audit_head": chain.get("head"), "audit_entries": chain["entries"],
        "files": [{"path": n, "sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b)} for n, b in sorted(encoded.items())],
        "disclaimer": DISCLAIMER,
    }
    manifest_bytes = json.dumps(manifest, indent=1).encode()
    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, b in sorted(encoded.items()):
            z.writestr(name, b)
        z.writestr("manifest.json", manifest_bytes)
    twin.log_audit(ws, actor, "evidence.exported", "evidence-pack",
                   {"manifest_sha256": manifest_hash, "files": len(encoded)})
    return buf.getvalue(), {"manifest_sha256": manifest_hash, "files": len(encoded) + 1, "bytes": buf.tell()}


def verify_pack(data: bytes, twin: Twin | None = None, ws: str | None = None) -> dict:
    if len(data) > MAX_PACK_BYTES:
        raise ValueError("Pack exceeds 30 MB")
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValueError("This is not a ZIP file") from exc
    with z:
        names = set(z.namelist())
        if "manifest.json" not in names:
            raise ValueError("manifest.json is missing; this is not a PrivacyTwin evidence pack")
        if sum(i.file_size for i in z.infolist()) > 200 * 1024 * 1024:
            raise ValueError("Pack expands to more than 200 MB")
        manifest_bytes = z.read("manifest.json")
        try:
            manifest = json.loads(manifest_bytes)
        except json.JSONDecodeError as exc:
            raise ValueError("manifest.json is not valid JSON") from exc
        results = []
        listed = set()
        for f in manifest.get("files", []):
            path = f.get("path")
            listed.add(path)
            if path not in names:
                results.append({"path": path, "ok": False, "reason": "missing from the pack"})
                continue
            actual = hashlib.sha256(z.read(path)).hexdigest()
            results.append({"path": path, "ok": actual == f.get("sha256"), "expected": f.get("sha256"), "actual": actual,
                            "reason": "hash matches" if actual == f.get("sha256") else "content changed after export"})
        for extra in sorted(names - listed - {"manifest.json"}):
            results.append({"path": extra, "ok": False, "reason": "not listed in the manifest"})
        chain = None
        if "audit_chain.json" in names:
            try:
                entries = json.loads(z.read("audit_chain.json"))["entries"]
                chain = verify_chain(entries)
            except (KeyError, ValueError, TypeError):
                chain = {"ok": False, "reason": "audit_chain.json could not be read"}
    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
    anchored = None
    if twin is not None and ws is not None:
        anchored = any(e["action"] == "evidence.exported" and e["payload"].get("manifest_sha256") == manifest_hash
                       for e in twin.audit(ws))
    return {"ok": all(r["ok"] for r in results) and (chain is None or chain.get("ok", False)),
            "files": results, "manifest_sha256": manifest_hash, "created_at": manifest.get("created_at"),
            "audit_chain": chain, "anchored_in_this_workspace": anchored, "disclaimer": DISCLAIMER}
