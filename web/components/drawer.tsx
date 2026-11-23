"use client";

import { Check, Copy, HelpCircle, Sparkles, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { post } from "@/lib/api";
import { ALL_CLASSES, BandLabel, CLASS_META, ClassChip, SeverityBadge, StatusLabel } from "@/lib/classes";
import { fmtDate, invalidate, useApi } from "@/lib/hooks";
import type { Cls, Finding, Status } from "@/lib/types";
import { useApp } from "./app-context";
import { useNav } from "./shell";
import { AiText, ModelBadge } from "./ai-text";
import { AiBadge, ErrorCard, SignalBars, Skeleton, Tip } from "./ui";

type Detail = {
  finding: Finding;
  history: { class: Cls; confidence: number; band: string; seq: number; created_at: string; ruleset_version: string }[];
  reviews: { status: Status; class_override: Cls | null; note: string; actor: string; created_at: string }[];
  suggestion: Record<string, string>;
  suggestion_basis: string;
};

const FIELDS: [keyof Finding["meta"], string][] = [
  ["purpose", "Purpose"], ["retention", "Retention"], ["owner", "Owner"], ["legal_basis", "Legal basis (declared)"], ["system_of_record", "System of record"],
];

export function FindingDrawer() {
  const { params, router, pathname } = useNav();
  const pt = params.get("f");
  const close = () => {
    const p = new URLSearchParams(params.toString());
    p.delete("f");
    router.replace(`${pathname}${p.toString() ? `?${p}` : ""}`, { scroll: false });
  };
  const closeBtn = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!pt) return;
    closeBtn.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [pt]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!pt) return null;
  return (
    <>
      <div className="scrim" onClick={close} />
      <aside className="drawer" role="dialog" aria-modal="true" aria-label={`Evidence for ${pt}`}>
        <DrawerBody pt={pt} onClose={close} closeRef={closeBtn} />
      </aside>
    </>
  );
}

function DrawerBody({ pt, onClose, closeRef }: { pt: string; onClose: () => void; closeRef: React.RefObject<HTMLButtonElement | null> }) {
  const app = useApp();
  const { data, error, reload } = useApi<Detail>(`/api/findings/${pt}`);
  const f = data?.finding;
  const [note, setNote] = useState("");
  const [reclass, setReclass] = useState<Cls | "">("");
  const [mask, setMask] = useState<{ strategy: string; example: string; result: string } | null>(null);
  const [ai, setAi] = useState<{ explanation: string; mode: string; model?: string } | "loading" | null>(null);

  useEffect(() => {
    setNote("");
    setReclass("");
    setMask(null);
    setAi(null);
  }, [pt]);

  const review = async (status: Status, override?: Cls) => {
    if (!f) return;
    if ((status === "rejected" || override) && note.trim().length < 3) {
      app.toast("Add a short note to reject or reclassify (it goes into the audit log).", { kind: "error" });
      document.getElementById("drawer-note")?.focus();
      return;
    }
    try {
      const r = await post<{ previous: unknown[] }>("/api/reviews", { keys: [f.key], status, note, class_override: override ?? null });
      invalidate();
      reload();
      setNote("");
      app.toast(`${f.pt_id} marked ${status.replace("_", " ")}`, { undo: () => post("/api/reviews/undo", { previous: r.previous }) });
    } catch (e) {
      app.toast((e as Error).message, { kind: "error" });
    }
  };

  const saveMeta = async (field: string, value: string, target: "col" | "table") => {
    if (!f) return;
    const t = target === "col" ? `col:${f.key}` : `table:${f.source_id}/${f.table}`;
    try {
      const r = await post<{ previous: { target: string; values: Record<string, string> }[] }>("/api/metadata", { targets: [t], values: { [field]: value } });
      invalidate();
      reload();
      app.markSaved();
      app.toast(`${field.replace("_", " ")} declared for ${target === "col" ? f.column : f.table}`, { undo: () => post("/api/metadata/undo", { previous: r.previous }) });
    } catch (e) {
      app.toast((e as Error).message, { kind: "error" });
    }
  };

  const copyLink = async () => {
    const url = `${window.location.origin}${window.location.pathname}?f=${pt}`;
    try {
      await navigator.clipboard.writeText(url);
      app.toast("Evidence link copied");
    } catch {
      app.toast(url);
    }
  };

  const preview = async (strategy: string) => {
    const r = await post<{ example: string; result: string }>("/api/mask/preview", { pt_id: pt, strategy });
    setMask({ strategy, ...r });
  };

  return (
    <>
      <div className="drawer-head">
        <div className="stack-sm" style={{ gap: 6, minWidth: 0 }}>
          <div className="row" style={{ gap: 8 }}>
            <span className="tag">{pt}</span>
            {f && <ClassChip cls={f.class} />}
            {f && <StatusLabel status={f.status} />}
          </div>
          {f ? (
            <>
              <h3 className="mono" style={{ fontSize: 17, wordBreak: "break-all" }}>{f.table}.{f.column}</h3>
              <div className="small faint">{f.source} · scan #{f.scan_seq} · rules v{f.rule_version}</div>
            </>
          ) : (
            <Skeleton h={22} w={220} />
          )}
        </div>
        <div className="row" style={{ gap: 4 }}>
          <button className="btn sm icon ghost" onClick={copyLink} aria-label="Copy evidence link"><Copy size={16} /></button>
          <button ref={closeRef} className="btn sm icon ghost" onClick={onClose} aria-label="Close (Esc)"><X size={18} /></button>
        </div>
      </div>
      <div className="drawer-body">
        {error && <ErrorCard message={error.message} onRetry={reload} />}
        {!f && !error && <div className="stack"><Skeleton h={90} /><Skeleton h={120} /><Skeleton h={160} /></div>}
        {f && (
          <>
            <section aria-label="Confidence">
              <h4 className="row" style={{ gap: 8 }}>Confidence <AiBadge label="AI" how="Explainable AI detection: weight × (0.35 header + 0.30 value + 0.35 validator). HIGH ≥ 0.75, MEDIUM ≥ 0.55." /></h4>
              <div className="card pad stack-sm">
                <div className="row between">
                  <BandLabel band={f.band} score={f.confidence} />
                  {f.rule_id && <span className="tag">{f.rule_id} · v{f.rule_version}</span>}
                </div>
                <SignalBars signals={f.signals} validator={f.validator} />
                {f.negative_keywords.length > 0 && <p className="small faint">Reduced by negative keyword: {f.negative_keywords.join(", ")}</p>}
                {f.class !== f.detected_class && <p className="small">Reclassified by a reviewer from <ClassChip cls={f.detected_class} compact /></p>}
              </div>
            </section>
            <section aria-label="Rationale">
              <h4 className="row" style={{ gap: 8 }}>AI reasoning <Tip text="Generated from the measured signals. Raw values are never stored or shown." /></h4>
              <p style={{ lineHeight: 1.65 }}>{f.rationale}</p>
              <div style={{ marginTop: 10 }}>
                {ai === null && (
                  <button className="btn sm" style={{ borderColor: "#7c6cf0" }} onClick={async () => {
                    setAi("loading");
                    try { setAi(await post("/api/ai/explain", { pt_id: pt })); } catch { setAi(null); app.toast("AI explanation unavailable", { kind: "error" }); }
                  }}><Sparkles size={14} color="#7c6cf0" /> Explain with AI</button>
                )}
                {ai === "loading" && <div className="bubble"><span className="ai-typing">AI is explaining</span></div>}
                {ai && ai !== "loading" && (
                  <div className="bubble" style={{ borderLeft: "3px solid #7c6cf0" }}>
                    <div style={{ marginBottom: 6 }}><ModelBadge mode={ai.mode} model={ai.model} /></div>
                    <AiText text={ai.explanation} />
                  </div>
                )}
              </div>
              {f.alternatives.length > 0 && (
                <p className="small faint" style={{ marginTop: 8 }}>
                  Other interpretations: {f.alternatives.map((a) => `${CLASS_META[a.class].label} (${a.rule_id}, ${a.score.toFixed(2)})`).join(" · ")}
                </p>
              )}
            </section>
            <section aria-label="Masked examples">
              <h4>Masked examples</h4>
              <div className="row wrap" style={{ gap: 6 }}>
                {f.masked_examples.length ? f.masked_examples.map((m) => <code key={m} className="tag" style={{ fontSize: 12 }}>{m}</code>) : <span className="faint">None</span>}
              </div>
              <div className="grid cols-3 small" style={{ marginTop: 12, gap: 8 }}>
                <Stat label="Type" v={f.profile.inferred_type} />
                <Stat label="Null" v={`${f.profile.null_pct}%`} />
                <Stat label="Distinct" v={`${f.profile.distinct_pct}%`} />
                <Stat label="Length" v={`${f.profile.min_len}–${f.profile.max_len}`} />
                <Stat label="Sampled" v={f.profile.sample_size.toLocaleString()} />
                <Stat label="Total rows" v={f.profile.total_rows.toLocaleString()} />
              </div>
            </section>

            <section aria-label="Review">
              <h4>Review decisions</h4>
              {f.decision_source === "ai" && <p className="small" style={{ color: "var(--accent)" }}>{f.review_note}</p>}
              <div className="card pad stack-sm">
                <textarea id="drawer-note" className="input" placeholder="Note (required to reject or reclassify)" value={note} onChange={(e) => setNote(e.target.value)} aria-label="Review note" style={{ minHeight: 60 }} />
                <div className="row wrap" style={{ gap: 6 }}>
                  <button className="btn sm primary" onClick={() => review("confirmed")}><Check size={14} /> Confirm</button>
                  <button className="btn sm" onClick={() => review("rejected")}><X size={14} /> Reject</button>
                  <button className="btn sm" onClick={() => review("needs_info")}><HelpCircle size={14} /> Needs info</button>
                  <select className="input" style={{ minHeight: 32, width: "auto", fontSize: 13, padding: "2px 8px" }} value={reclass} aria-label="Reclassify as"
                    onChange={(e) => { const v = e.target.value as Cls; setReclass(v); if (v) review("confirmed", v); }}>
                    <option value="">Reclassify as…</option>
                    {ALL_CLASSES.filter((c) => c !== f.class).map((c) => <option key={c} value={c}>{CLASS_META[c].label}</option>)}
                  </select>
                </div>
                {data!.reviews.length > 0 && (
                  <ul className="small muted" style={{ margin: 0, paddingLeft: 18 }}>
                    {data!.reviews.slice(-4).reverse().map((r, i) => (
                      <li key={i}><b>{r.status.replace("_", " ")}</b>{r.class_override ? ` as ${CLASS_META[r.class_override].label}` : ""} by {r.actor}, {fmtDate(r.created_at, true)}{r.note ? `: “${r.note}”` : ""}</li>
                    ))}
                  </ul>
                )}
              </div>
            </section>

            {f.personal && (
              <section aria-label="Declared metadata">
                <h4 className="row" style={{ gap: 8 }}>Declared metadata <Tip text="Editing here declares for this column and overrides the table. Legal basis is free text you declare; it is never suggested." /></h4>
                <div className="card pad stack-sm">
                  {f.gaps.map((g) => (
                    <div key={g.field + g.message} className="row small" style={{ gap: 8 }}><SeverityBadge sev={g.severity} /> {g.message}</div>
                  ))}
                  {FIELDS.map(([k, label]) => {
                    const m = f.meta[k] as { value: string; origin: string | null };
                    const sug = data!.suggestion[k as string];
                    return (
                      <label key={k} className="field">
                        <span className="row between">
                          {label}
                          <span className="faint small">{m.origin ? `declared on ${m.origin}` : "not declared"}</span>
                        </span>
                        <input className="input" defaultValue={m.value} key={`${pt}-${k}-${m.value}`} placeholder={sug ? `Suggestion: ${sug}` : "Not declared"}
                          onBlur={(e) => e.target.value !== m.value && saveMeta(k as string, e.target.value, "col")} />
                        {sug && !m.value && (
                          <button className="suggest" onClick={() => saveMeta(k as string, sug, "table")} title={data!.suggestion_basis}>
                            <Sparkles size={13} /> AI suggestion: “{sug}” · accept
                          </button>
                        )}
                      </label>
                    );
                  })}
                </div>
              </section>
            )}

            <section aria-label="History across scans">
              <h4>History across scans</h4>
              <ol style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 8 }}>
                {data!.history.map((h, i) => (
                  <li key={h.seq} className="row small" style={{ gap: 10 }}>
                    <span className="timeline-dot" style={{ background: CLASS_META[h.class].color }} aria-hidden />
                    <b className="num">#{h.seq}</b>
                    <ClassChip cls={h.class} compact />
                    <span className="num">{h.confidence.toFixed(2)}</span>
                    <span className="faint">{fmtDate(h.created_at)} · rules v{h.ruleset_version}</span>
                    {i === 0 && <span className="faint">first seen</span>}
                  </li>
                ))}
              </ol>
            </section>

            {f.personal && (
              <section aria-label="Masking preview">
                <h4 className="row" style={{ gap: 8 }}>Masking preview <Tip text="Shown on an invented example: PrivacyTwin keeps no raw values. Download a masked copy of a CSV from Sources." /></h4>
                <div className="seg" role="group" aria-label="Masking strategy">
                  {["partial", "hash", "tokenise", "redact"].map((s) => (
                    <button key={s} aria-pressed={mask?.strategy === s} onClick={() => preview(s)}>{s[0].toUpperCase() + s.slice(1)}</button>
                  ))}
                </div>
                {mask && (
                  <div className="card pad small stack-sm" style={{ marginTop: 8 }}>
                    <div className="row"><span className="faint" style={{ width: 70 }}>Example</span><code>{mask.example}</code></div>
                    <div className="row"><span className="faint" style={{ width: 70 }}>Result</span><code style={{ color: "var(--accent)" }}>{mask.result}</code></div>
                  </div>
                )}
              </section>
            )}
          </>
        )}
      </div>
    </>
  );
}

function Stat({ label, v }: { label: string; v: string }) {
  return (
    <div style={{ padding: "8px 10px", borderRadius: 8, background: "var(--surface-2)" }}>
      <div className="faint" style={{ fontSize: 11 }}>{label}</div>
      <div className="num" style={{ fontWeight: 600 }}>{v}</div>
    </div>
  );
}
