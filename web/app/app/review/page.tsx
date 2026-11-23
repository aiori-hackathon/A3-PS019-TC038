"use client";

import { Check, HelpCircle, Keyboard, Shuffle, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useApp } from "@/components/app-context";
import { AutoTriage } from "@/components/auto-triage";
import { isTyping } from "@/components/palette";
import { useNav } from "@/components/shell";
import { AiBadge, EmptyState, ErrorCard, PageHead, SignalBars, Skeleton } from "@/components/ui";
import { post } from "@/lib/api";
import { ALL_CLASSES, BandLabel, CLASS_META, ClassChip, SeverityBadge, StatusLabel } from "@/lib/classes";
import { invalidate, useApi } from "@/lib/hooks";
import type { Cls, Finding, Status } from "@/lib/types";

type Pending = { status: Status; override?: Cls } | null;

export default function ReviewPage() {
  const app = useApp();
  const { openFinding } = useNav();
  const { data, error, reload, setData } = useApi<{ rows: Finding[] }>("/api/review-queue");
  const rows = useMemo(() => data?.rows ?? [], [data]);
  const [idx, setIdx] = useState(0);
  const [note, setNote] = useState("");
  const [pending, setPending] = useState<Pending>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [lastUndo, setLastUndo] = useState<unknown[] | null>(null);
  const noteRef = useRef<HTMLInputElement>(null);
  const reclassRef = useRef<HTMLSelectElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const cur = rows[idx];
  const reviewed = rows.filter((r) => r.status === "confirmed" || r.status === "rejected").length;

  useEffect(() => {
    if (idx >= rows.length && rows.length) setIdx(rows.length - 1);
  }, [rows.length, idx]);
  useEffect(() => {
    listRef.current?.querySelector(`[data-i="${idx}"]`)?.scrollIntoView({ block: "nearest" });
  }, [idx]);

  const decide = useCallback(
    async (status: Status, override?: Cls, keys?: string[]) => {
      const target = keys ?? (cur ? [cur.key] : []);
      if (!target.length) return;
      if ((status === "rejected" || override) && note.trim().length < 3) {
        setPending({ status, override });
        noteRef.current?.focus();
        return;
      }
      // optimistic update
      const before = data;
      setData(data && { rows: data.rows.map((r) => (target.includes(r.key) ? { ...r, status, class: override ?? r.class } : r)) });
      setPending(null);
      const n = note;
      setNote("");
      if (!keys) {
        const next = rows.findIndex((r, i) => i > idx && r.status === "candidate");
        setIdx(next >= 0 ? next : Math.min(idx + 1, rows.length - 1));
      }
      try {
        const r = await post<{ previous: unknown[] }>("/api/reviews", { keys: target, status, note: n, class_override: override ?? null });
        setLastUndo(r.previous);
        invalidate();
        setSelected(new Set());
        app.toast(`${target.length === 1 ? (cur?.pt_id ?? "1 finding") : `${target.length} findings`} ${override ? `reclassified as ${CLASS_META[override].label}` : status.replace("_", " ")}`, {
          undo: async () => { await post("/api/reviews/undo", { previous: r.previous }); setLastUndo(null); },
        });
      } catch (e) {
        setData(before);
        app.toast((e as Error).message, { kind: "error" });
      }
    },
    [cur, note, data, setData, rows, idx, app],
  );

  const undo = useCallback(async () => {
    if (!lastUndo) return app.toast("Nothing to undo");
    await post("/api/reviews/undo", { previous: lastUndo });
    setLastUndo(null);
    invalidate();
    app.toast("Undone");
  }, [lastUndo, app]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (isTyping(e) || e.ctrlKey || e.metaKey || e.altKey || app.palette) return;
      const k = e.key.toLowerCase();
      const map: Record<string, () => void> = {
        j: () => setIdx((i) => Math.min(rows.length - 1, i + 1)),
        k: () => setIdx((i) => Math.max(0, i - 1)),
        arrowdown: () => setIdx((i) => Math.min(rows.length - 1, i + 1)),
        arrowup: () => setIdx((i) => Math.max(0, i - 1)),
        c: () => decide("confirmed"),
        r: () => decide("rejected"),
        i: () => decide("needs_info"),
        e: () => reclassRef.current?.focus(),
        n: () => noteRef.current?.focus(),
        z: () => undo(),
        x: () => cur && setSelected((s) => { const n = new Set(s); n.has(cur.key) ? n.delete(cur.key) : n.add(cur.key); return n; }),
        o: () => cur && openFinding(cur.pt_id),
      };
      if (map[k]) {
        e.preventDefault();
        map[k]();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [rows.length, decide, undo, cur, openFinding, app.palette]);

  if (error) return <ErrorCard message={error.message} onRetry={reload} />;
  if (!data) return <div className="stack"><Skeleton h={40} w={300} /><Skeleton h={420} /></div>;
  if (!rows.length) return (<><PageHead title="Review queue" /><AutoTriage /><EmptyState title="Nothing to review" body="Personal-data candidates appear here, sorted by risk, after a scan." action={<button className="btn primary" onClick={app.loadDemo}>Load demo</button>} /></>);

  return (
    <>
      <PageHead
        title="Review queue"
        desc="Sorted by risk (confidence × class sensitivity × gap severity). Keys: J/K move · C confirm · R reject · E reclassify · I needs info · N note · Z undo · O full evidence."
        actions={<span className="small muted num">{reviewed} of {rows.length} decided</span>}
      />
      <AutoTriage />
      <div className="meter" style={{ marginBottom: 16 }} aria-label={`${reviewed} of ${rows.length} reviewed`}><span style={{ width: `${(100 * reviewed) / rows.length}%` }} /></div>

      {selected.size > 0 && (
        <div className="card pad row wrap" style={{ marginBottom: 12, gap: 8, borderColor: "var(--accent)" }} role="region" aria-label="Bulk actions">
          <b>{selected.size} selected</b>
          <button className="btn sm primary" onClick={() => decide("confirmed", undefined, [...selected])}><Check size={14} /> Confirm all</button>
          <button className="btn sm" onClick={() => decide("rejected", undefined, [...selected])}><X size={14} /> Reject all</button>
          <button className="btn sm" onClick={() => decide("needs_info", undefined, [...selected])}><HelpCircle size={14} /> Needs info</button>
          <button className="btn sm ghost" onClick={() => setSelected(new Set())}>Clear</button>
          
        </div>
      )}

      <div className="grid" style={{ gridTemplateColumns: "minmax(0, 0.95fr) minmax(0, 1.25fr)", alignItems: "start" }}>
        <div ref={listRef} className="card" style={{ maxHeight: "calc(100vh - 300px)", overflowY: "auto" }} role="listbox" aria-label="Candidates" aria-activedescendant={cur ? `rq-${cur.pt_id}` : undefined}>
          <div className="row" style={{ padding: "10px 14px", borderBottom: "1px solid var(--border)", gap: 8 }}>
            <input type="checkbox" aria-label="Select all candidates" checked={selected.size > 0 && rows.filter((r) => r.status === "candidate").every((r) => selected.has(r.key))}
              onChange={(e) => setSelected(e.target.checked ? new Set(rows.filter((r) => r.status === "candidate").map((r) => r.key)) : new Set())} />
            <span className="small faint">Select all open candidates</span>
          </div>
          {rows.map((r, i) => (
            <div key={r.key} id={`rq-${r.pt_id}`} data-i={i} role="option" aria-selected={i === idx} onClick={() => setIdx(i)}
              className="row" style={{ padding: "10px 14px", gap: 10, cursor: "pointer", borderBottom: "1px solid var(--border)", background: i === idx ? "var(--accent-soft)" : undefined, boxShadow: i === idx ? "inset 3px 0 0 var(--accent)" : undefined, opacity: r.status === "rejected" ? 0.55 : 1 }}>
              <input type="checkbox" aria-label={`Select ${r.pt_id}`} checked={selected.has(r.key)} onClick={(e) => e.stopPropagation()}
                onChange={(e) => setSelected((s) => { const n = new Set(s); e.target.checked ? n.add(r.key) : n.delete(r.key); return n; })} />
              <div style={{ minWidth: 0, flex: 1, display: "grid", gap: 2 }}>
                <code style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.table}.{r.column}</code>
                <div className="row small" style={{ gap: 8 }}><ClassChip cls={r.class} compact /><StatusLabel status={r.status} />{r.decision_source === "ai" && <span className="tag">AI approved</span>}</div>
              </div>
              <span className="num small faint" title="Risk">{r.risk}</span>
            </div>
          ))}
        </div>

        {cur && (
          <section className="card" aria-label={`Candidate ${cur.pt_id}`} style={{ position: "sticky", top: 120 }}>
            <div className="card-head">
              <div className="stack-sm" style={{ gap: 4 }}>
                <div className="row" style={{ gap: 8 }}><span className="tag">{cur.pt_id}</span><ClassChip cls={cur.class} /><StatusLabel status={cur.status} /></div>
                <h3 className="mono" style={{ fontSize: 17 }}>{cur.table}.{cur.column}</h3>
                <span className="small faint">{cur.source} · rule {cur.rule_id} v{cur.rule_version}</span>
              </div>
              <button className="btn sm" onClick={() => openFinding(cur.pt_id)}>Full evidence <kbd>O</kbd></button>
            </div>
            <div className="card-body stack">
              <div className="row between"><span className="row" style={{ gap: 8 }}><AiBadge label={cur.decision_source === "ai" ? "AI APPROVED" : "AI SUGGESTS"} how="The engine proposes the class. Opt-in auto-triage can confirm eligible candidates. AI approvals are audited separately and excluded from human-confirmed precision." /><ClassChip cls={cur.detected_class} /><BandLabel band={cur.band} score={cur.confidence} /></span><span className="small faint">{idx + 1} / {rows.length}</span></div>
              {cur.decision_source === "ai" && <p className="small" style={{ color: "var(--accent)" }}>{cur.review_note}</p>}
              <SignalBars signals={cur.signals} validator={cur.validator} />
              <p style={{ lineHeight: 1.6 }}>{cur.rationale}</p>
              <div className="row wrap" style={{ gap: 6 }}>{cur.masked_examples.map((m) => <code key={m} className="tag">{m}</code>)}</div>
              {cur.gaps.length > 0 && <div className="row wrap" style={{ gap: 12 }}>{cur.gaps.map((g) => <span key={g.message} className="row small" style={{ gap: 6 }}><SeverityBadge sev={g.severity} />{g.field.replace("_", " ")}</span>)}</div>}
              <hr className="divider" style={{ margin: 0 }} />
              <form className="stack-sm" onSubmit={(e) => { e.preventDefault(); if (pending) decide(pending.status, pending.override); else decide("confirmed"); }}>
                <label className="field">
                  Note {pending && <span style={{ color: "var(--sev-medium)" }}>— required to {pending.override ? `reclassify as ${CLASS_META[pending.override].label}` : "reject"}. Press Enter to submit.</span>}
                  <input ref={noteRef} className="input" value={note} onChange={(e) => setNote(e.target.value)} placeholder={pending ? "Why? (goes into the audit log)" : "Optional for confirm · required for reject/reclassify"}
                    onKeyDown={(e) => { if (e.key === "Escape") { setPending(null); (e.target as HTMLInputElement).blur(); } }} />
                </label>
                <div className="row wrap" style={{ gap: 8 }}>
                  <button type="button" className="btn primary" onClick={() => decide("confirmed")}><Check size={15} /> Confirm <kbd>C</kbd></button>
                  <button type="button" className="btn" onClick={() => decide("rejected")}><X size={15} /> Reject <kbd>R</kbd></button>
                  <button type="button" className="btn" onClick={() => decide("needs_info")}><HelpCircle size={15} /> Needs info <kbd>I</kbd></button>
                  <label className="row" style={{ gap: 6 }}>
                    <Shuffle size={15} aria-hidden className="faint" />
                    <select ref={reclassRef} className="input" aria-label="Reclassify (E)" value="" style={{ width: "auto", minHeight: 40 }}
                      onChange={(e) => e.target.value && decide("confirmed", e.target.value as Cls)}>
                      <option value="">Reclassify… (E)</option>
                      {ALL_CLASSES.filter((c) => c !== cur.class).map((c) => <option key={c} value={c}>{CLASS_META[c].label}</option>)}
                    </select>
                  </label>
                </div>
              </form>
            </div>
          </section>
        )}
      </div>
      <style>{`@media (max-width: 960px){ .content .grid[style*="0.95fr"]{grid-template-columns:minmax(0,1fr) !important} .content section[style*="sticky"]{position:static !important} }`}</style>
    </>
  );
}
