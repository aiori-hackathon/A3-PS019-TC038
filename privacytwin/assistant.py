"""AI assistant and analyst.

Offline intent/retrieval answers over the app's docs and workspace metadata are always
computed first. When an LLM is configured (Groq via GROQ_API_KEY, see llm.py) it rewrites
answers and summaries from the same metadata-only context. Raw values and masked
examples are never sent.
"""
from __future__ import annotations

import json
import re

from . import DISCLAIMER
from .llm import chat, finding_context
from .llm import status as _llm_status
from .twin import Twin

SUGGESTED = [
    "Which tables have Aadhaar with no retention?",
    "Why was customers.mobile flagged?",
    "What changed since the last scan?",
    "How is the posture score calculated?",
    "Which fields have no owner?",
    "How do I verify an evidence pack?",
]

TOPICS = {
    "aadhaar": ("rule", "aadhaar"), "pan": ("rule", "pan"), "passport": ("rule", "passport_in"),
    "voter": ("rule", "voter_id"), "licence": ("rule", "driving_licence"), "license": ("rule", "driving_licence"),
    "gstin": ("rule", "gstin"), "card": ("rule", "card_number"), "upi": ("rule", "upi_id"),
    "bank account": ("rule", "bank_account"), "ifsc": ("rule", "ifsc"), "email": ("rule", "email"),
    "mobile": ("rule", "mobile_in"), "phone": ("rule", "mobile_in"), "date of birth": ("rule", "date_of_birth"),
    "dob": ("rule", "date_of_birth"), "address": ("rule", "address"), "ip": ("rule", "ip_address"),
    "identity": ("class", "IDENTITY"), "contact": ("class", "CONTACT"), "government": ("class", "GOVERNMENT_ID"),
    "financial": ("class", "FINANCIAL"), "location": ("class", "LOCATION"), "personal": ("class", "*"),
}
FIELDS = {"retention": "retention", "purpose": "purpose", "owner": "owner", "legal basis": "legal_basis",
          "system of record": "system_of_record"}

DOCS = [
    ("What PrivacyTwin does", "PrivacyTwin builds a digital twin of your personal-data estate. Each scan creates a snapshot. "
     "You can discover where personal data lives, rewind the twin with the Time Machine, simulate breach blast radius, "
     "re-identification and retention, prove accuracy on a labelled benchmark, and export a hash-verified evidence pack.", "/docs#overview"),
    ("Why we don't decide legality", "Detection produces candidates with technical evidence. Whether processing is lawful depends "
     "on context only people and counsel can judge. PrivacyTwin never issues legal verdicts of any kind.", "/docs#legality"),
    ("Confidence", "Each column is scored on three signals: the header keyword match, the share of sampled values that match the "
     "class pattern, and the share that pass a real validator such as Verhoeff (Aadhaar), Luhn (cards) or the GSTIN checksum. "
     "score = weight x (0.35 header + 0.30 value + 0.35 validator). HIGH >= 0.75, MEDIUM >= 0.55, LOW >= the rule threshold.", "/docs#detection"),
    ("Data handling", "Sources are read-only. Uploads are processed in memory on a bounded sample (500, 1,000 or 5,000 rows) and "
     "discarded. Only aggregates, masked examples and keyed MinHash fingerprints are stored. Every scan has a data-handling receipt.", "/security"),
    ("Audit log", "Every review, metadata change, rule change, scan and export is appended to a SHA-256 hash chain. Each entry "
     "includes the previous entry's hash. Verify integrity recomputes the chain and highlights the first broken link.", "/docs#audit"),
    ("Evidence pack", "Export evidence pack builds a ZIP with inventory, gaps, reviews, the audit chain, scan diff, evaluation, "
     "rule set and receipts, plus manifest.json with the SHA-256 of every file. Upload the ZIP under Verify pack to recompute hashes.", "/docs#evidence"),
    ("Posture score", "score = 100 x (0.35 x metadata coverage + 0.25 x review completion + 0.25 x (1 - gap severity index) + "
     "0.15 x (1 - re-identification risk)). It is a technical posture indicator, not a compliance rating.", "/docs#posture"),
    ("Time Machine", "Pick two scans to diff them: new or removed personal-data columns, class or confidence changes, and metadata "
     "gaps opened or closed. Drift alerts flag new personal data that appeared without a declared purpose.", "/docs#time-machine"),
    ("Rules", "Rules are versioned (semantic versions plus a content hash). Edit a rule in the Rule Playground, test it on sample "
     "strings, preview the impact on the current scan, then save a new version. Every scan records the rule-set version and hash.", "/docs#rules"),
    ("Keyboard", "Ctrl/Cmd+K opens the command palette. In the review queue: J/K next/previous, C confirm, R reject, E reclassify, "
     "N note, Z undo. G then S/I/R/M/T/E jumps to Sources, Inventory, Review, Metadata, Time Machine or Evaluation. ? shows all shortcuts.", "/docs#keyboard"),
]


def _tokens(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def _match_topic(q: str):
    for word, topic in TOPICS.items():
        if re.search(r"\b" + re.escape(word) + r"\b", q):
            return word, topic
    return None, None


def _offline_answer(twin: Twin, ws: str, question: str) -> dict:
    q = question.strip().lower()[:500]
    if not q:
        return {"answer": "Ask about your scans, findings, gaps or how PrivacyTwin works.", "suggestions": SUGGESTED}
    view = twin.view(ws)
    rows = view["rows"]
    mode = "offline"
    sources: list[dict] = []

    # 1. "why was X flagged"
    m = re.search(r"why (?:was|is|did) ([\w.\-]+)", q)
    if m and rows:
        target = m.group(1).strip(".?")
        hits = [r for r in rows if f"{r['table']}.{r['column']}".lower() == target or r["column"].lower() == target
                or r["pt_id"].lower() == target]
        if hits:
            r = hits[0]
            s = r["signals"]
            text = (f"{r['pt_id']} {r['table']}.{r['column']} is a {r['class']} candidate ({r['band']}, {r['confidence']:.2f}). "
                    f"{r['rationale']} Signals: header {s['header']:.0f}, value {s['value']:.0%}, validator {s['validator']:.0%}. "
                    f"Review status: {r['status']}.")
            return _out(text, [{"pt_id": r["pt_id"], "label": f"{r['table']}.{r['column']}"}], mode)
        return _out(f"I could not find a column called '{target}'. Try table.column, for example customers.email.", [], mode)

    # 2. "what changed"
    if re.search(r"what changed|since (the )?last scan|drift|diff", q):
        scans = twin.scans(ws)
        if len(scans) < 2:
            return _out("There is only one scan so far. Rescan a source (drop the same file again) to compare snapshots.", [], mode)
        d = twin.diff(ws, scans[-2]["seq"], scans[-1]["seq"])
        sm = d["summary"]
        parts = [f"Between scan #{d['a']} and #{d['b']}: {sm['new']} new personal-data columns, {sm['removed']} removed, "
                 f"{sm['class_changes']} class changes, {sm['gaps_opened']} gaps opened and {sm['gaps_closed']} closed."]
        for n in d["new"][:5]:
            parts.append(f"New: {n['table']}.{n['column']} ({n['class']}).")
        return _out(" ".join(parts), [{"pt_id": n["pt_id"], "label": f"{n['table']}.{n['column']}"} for n in d["new"][:5]], mode)

    # 3. "which ... with no <field>"
    field = next((f for word, f in FIELDS.items() if word in q), None)
    word, topic = _match_topic(q)
    if (field or topic) and re.search(r"which|what|list|show|how many|where", q) and rows:
        sel = [r for r in rows if r["personal"]]
        if topic and topic[0] == "rule":
            sel = [r for r in sel if r["rule_id"] == topic[1]]
        elif topic and topic[0] == "class" and topic[1] != "*":
            sel = [r for r in sel if r["class"] == topic[1]]
        negative = re.search(r"\bno\b|without|missing|lack", q)
        if field and negative:
            sel = [r for r in sel if not r["meta"][field]["value"]]
        label = f"{word or 'personal-data'} fields" + (f" with no {field.replace('_', ' ')}" if field and negative else "")
        if not sel:
            return _out(f"No {label} in the current snapshot.", [], mode)
        tables = sorted({r["table"] for r in sel})
        text = (f"{len(sel)} {label} across {len(tables)} table(s): {', '.join(tables)}. "
                + " ".join(f"{r['pt_id']} {r['table']}.{r['column']}." for r in sel[:8]))
        return _out(text, [{"pt_id": r["pt_id"], "label": f"{r['table']}.{r['column']}"} for r in sel[:8]], mode)

    # 3b. riskiest / most exposed tables
    if re.search(r"riskiest|highest risk|most (exposed|sensitive|risky)|fix first|prioriti", q) and rows:
        from collections import defaultdict
        risk: dict[str, float] = defaultdict(float)
        for r in rows:
            if r["personal"]:
                risk[r["table"]] += r["risk"]
        ranked = sorted(risk.items(), key=lambda kv: -kv[1])[:3]
        top = sorted((r for r in rows if r["personal"] and r["table"] == ranked[0][0]), key=lambda r: -r["risk"])[:3]
        text = (f"Highest risk: {ranked[0][0]} (risk {ranked[0][1]:.0f}), driven by "
                + ", ".join(f"{r['pt_id']} {r['column']} ({r['class'].replace('_', ' ').lower()}, gaps: "
                            f"{', '.join(g['field'] for g in r['gaps']) or 'none'})" for r in top)
                + ". Next: " + ", ".join(f"{t} ({v:.0f})" for t, v in ranked[1:]) + ". Risk = confidence × class sensitivity × gap severity.")
        return _out(text, [{"pt_id": r["pt_id"], "label": f"{r['table']}.{r['column']}"} for r in top], mode)

    # 4. posture
    if "posture" in q or "score" in q:
        p = twin.posture(view)
        if p["score"] is None:
            return _out("The posture indicator appears after the first scan finds personal data. " + DOCS[6][1], [], mode)
        c = p["components"]
        return _out(f"Current posture indicator: {p['score']}/100. Metadata coverage {c['metadata_coverage']:.0%}, review completion "
                    f"{c['review_completion']:.0%}, gap severity index {c['gap_severity_index']:.2f}, re-identification risk "
                    f"{c['reidentification_risk']:.0%}. {p['formula']}. {p['label']}", [], mode)


    # 6. docs retrieval
    qt = _tokens(q)
    ranked = sorted(DOCS, key=lambda d: -len(qt & _tokens(d[0] + " " + d[1])))
    best = ranked[0]
    if not qt & _tokens(best[0] + " " + best[1]):
        return _out("I can answer questions about this workspace's findings, gaps and changes, and about how PrivacyTwin works. "
                    "Try one of the suggestions.", [], mode)
    sources = [{"title": best[0], "href": best[2]}]
    return _out(best[1], [], mode, sources)


def ai_summary(twin: Twin, ws: str) -> dict:
    """Auto-generated, prioritised insights about the current twin (metadata only)."""
    view = twin.view(ws)
    rows = [r for r in view["rows"] if r["personal"]]
    if not rows:
        return {"headline": None, "insights": [], "mode": "offline"}
    from collections import Counter
    by_table = Counter(r["table"] for r in rows)
    risk = Counter()
    for r in rows:
        risk[r["table"]] += r["risk"]
    classes = Counter(r["class"] for r in rows)
    gov = [r for r in rows if r["class"] == "GOVERNMENT_ID" and not r["meta"]["purpose"]["value"]]
    no_ret = [r for r in rows if not r["meta"]["retention_days"]]
    pending = [r for r in rows if r["status"] == "candidate"]
    insights = []
    top_table, top_risk = risk.most_common(1)[0]
    top_cols = sorted((r for r in rows if r["table"] == top_table), key=lambda r: -r["risk"])[:3]
    insights.append({"severity": "High", "title": f"Highest exposure: {top_table}",
                     "text": f"{by_table[top_table]} personal-data fields, led by "
                             + ", ".join(f"{r['column']} ({r['class'].replace('_', ' ').lower()})" for r in top_cols) + ".",
                     "findings": [r["pt_id"] for r in top_cols], "action": {"label": "Simulate breach", "href": f"/app/simulator/?target={top_cols[0]['source_id']}/{top_table}"}})
    drift = sorted(twin.drift(ws), key=lambda d: (-d["scan_seq"], d["severity"] != "High"))
    if drift:
        d = drift[0]
        insights.append({"severity": d["severity"], "title": "New personal data appeared", "text": d["message"] + ".",
                         "findings": [d["pt_id"]], "action": {"label": "Open Time Machine", "href": "/app/time-machine/"}})
    if gov:
        insights.append({"severity": "High", "title": f"{len(gov)} government-ID field{'s have' if len(gov) > 1 else ' has'} no declared purpose",
                         "text": ", ".join(f"{r['table']}.{r['column']}" for r in gov[:4]) + ("…" if len(gov) > 4 else "") + ".",
                         "findings": [r["pt_id"] for r in gov[:4]], "action": {"label": "Declare purpose", "href": "/app/metadata/"}})
    if no_ret:
        insights.append({"severity": "Medium", "title": f"{len(no_ret)} fields would never be cleaned up",
                         "text": "No retention period is declared for them.", "findings": [r["pt_id"] for r in no_ret[:4]],
                         "action": {"label": "Retention what-if", "href": "/app/simulator/?tab=retention"}})
    reid = [t for t in view["tables"].values() if t["kanon"] and t["kanon"]["generalised"]["unique_pct"] >= 30]
    if reid:
        t = max(reid, key=lambda t: t["kanon"]["generalised"]["unique_pct"])
        insights.append({"severity": "Medium", "title": f"Re-identification risk in {t['table']}",
                         "text": f"{round(t['kanon']['generalised']['unique_pct'])}% of sampled rows are unique on "
                                 f"{{{', '.join(t['kanon']['quasi_identifiers'])}}} even after generalisation.",
                         "findings": [], "action": {"label": "See k-anonymity", "href": "/app/simulator/?tab=reid"}})
    if pending:
        insights.append({"severity": "Low", "title": f"{len(pending)} candidates await review",
                         "text": "Start with the highest-risk ones; each decision is hash-chained into the audit log.",
                         "findings": [], "action": {"label": "Review now", "href": "/app/review/"}})
    headline = (f"{len(rows)} personal-data fields across {len(by_table)} tables. "
                + ", ".join(f"{n} {c.replace('_', ' ').lower()}" for c, n in classes.most_common()) + ".")
    out = {"headline": headline, "insights": insights[:5], "mode": "offline", "narrative": None}
    if llm_status()["enabled"]:
        text = chat("Write a 2-sentence executive summary of this personal-data estate for a hackathon judge, "
                    "then stop. Insights (already ranked): " + json.dumps({"headline": headline, "insights": insights[:5]}),
                    max_tokens=160)
        if text:
            out.update(narrative=text, mode="llm", model=llm_status()["model"])
    return out


def _out(text: str, findings: list, mode: str, docs: list | None = None) -> dict:
    return {"answer": text, "findings": findings, "docs": docs or [], "mode": mode, "suggestions": SUGGESTED,
            "privacy": "Answered from workspace metadata only; no raw or masked values were used.", "disclaimer": DISCLAIMER}


def llm_status() -> dict:
    return _llm_status()


def _context(view: dict) -> list[str]:
    """Compact one-line-per-finding context (keeps prompts under free-tier token limits)."""
    out = []
    for r in sorted((r for r in view["rows"] if r["personal"]), key=lambda r: -r["risk"])[:60]:
        out.append(f"{r['pt_id']} {r['table']}.{r['column']} {r['class']} conf={r['confidence']:.2f} risk={r['risk']} "
                   f"status={r['status']} gaps={','.join(g['field'] for g in r['gaps']) or 'none'}")
    return out


def answer(twin: Twin, ws: str, question: str) -> dict:
    """Offline answer first (grounded facts + links); Groq rewrites it with full context when enabled."""
    base = _offline_answer(twin, ws, question)
    if not llm_status()["enabled"] or not question.strip():
        return base
    view = twin.view(ws)
    scans = twin.scans(ws)
    diff = twin.diff(ws, scans[-2]["seq"], scans[-1]["seq"])["summary"] if len(scans) >= 2 else None
    prompt = "\n\n".join([
        f"Question: {question[:500]}",
        f"Facts already computed by PrivacyTwin (trust these numbers):\n{base['answer']}",
        f"Posture: {json.dumps(twin.posture(view)['components'])}\nLatest scan diff: {json.dumps(diff)}",
        "Personal-data findings, highest risk first (metadata only):\n" + "\n".join(_context(view)),
        "Answer in at most 5 short sentences or bullets. Mention PT-IDs where relevant.",
    ])
    text = chat(prompt)
    if not text:
        return base
    return base | {"answer": text, "mode": "llm", "model": llm_status()["model"],
                   "privacy": "Sent to Groq: workspace metadata only (names, classes, signal scores, gaps). No raw or masked values."}


def explain(twin: Twin, ws: str, pt_id: str) -> dict:
    view = twin.view(ws)
    r = next((x for x in view["rows"] if x["pt_id"] == pt_id), None)
    if r is None:
        raise KeyError("Finding not found")
    if not llm_status()["enabled"]:
        return {"explanation": r["rationale"], "mode": "offline"}
    prompt = (f"Explain this personal-data finding for a privacy reviewer: why it was flagged, what the risk is, "
              f"and the single most useful next step. 3-4 sentences.\nFinding: {json.dumps(finding_context(r))}\n"
              f"Engine rationale: {r['rationale']}")
    text = chat(prompt, max_tokens=300)
    return {"explanation": text or r["rationale"], "mode": "llm" if text else "offline", "model": llm_status()["model"]}
