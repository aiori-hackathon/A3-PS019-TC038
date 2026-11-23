"use client";

import { ArrowRight, FileSearch, Play, Send, Sparkles, Upload } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";
import { post } from "@/lib/api";
import { SeverityBadge } from "@/lib/classes";
import { useApi } from "@/lib/hooks";
import type { Severity } from "@/lib/types";
import { useApp } from "./app-context";
import { useNav } from "./shell";
import { TwinHero } from "./twin3d";
import { AiText, CharCount, MAX_CHARS, ModelBadge } from "./ai-text";
export { ModelBadge };
import { AiBadge, Skeleton, Tip } from "./ui";

type Summary = { headline: string | null; narrative: string | null; model?: string; insights: { severity: Severity; title: string; text: string; findings: string[]; action: { label: string; href: string } }[]; mode: string };
type Answer = { answer: string; findings: { pt_id: string; label: string }[]; mode: string; model?: string };

const HOW = "The AI analyst ranks the twin's findings by risk, drift, gaps and re-identification. When Groq is configured, an LLM writes the narrative and answers questions. Only metadata is sent (table/column names, classes, signal scores, gaps), never raw or masked values.";

const CHIPS = ["Which tables have Aadhaar with no retention?", "What changed since the last scan?", "Why was customers.mobile flagged?"];

/** AI summary + inline question box at the top of the Overview. */
export function AiPanel() {
  const { data } = useApi<Summary>("/api/ai/summary");
  const { openFinding } = useNav();
  const [q, setQ] = useState("");
  const [a, setA] = useState<Answer | null>(null);
  const [busy, setBusy] = useState(false);
  const ask = async (question: string) => {
    if (!question.trim()) return;
    setBusy(true);
    setQ(question);
    try {
      setA(await post<Answer>("/api/assistant", { question }));
    } catch (e) {
      setA({ answer: (e as Error).message, findings: [], mode: "error" });
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="card ai-card" aria-label="AI summary" style={{ marginBottom: 16 }}>
      <div className="card-head" style={{ borderBottomColor: "transparent", paddingBottom: 4 }}>
        <div className="row" style={{ gap: 8 }}>
          <AiBadge label="AI ANALYST" />
          <h3>{data?.headline ?? <span className="ai-typing">Analysing the twin</span>}</h3>
          {data && <ModelBadge mode={data.mode} model={data.model} />}
          <Tip text={HOW} />
        </div>
      </div>
      <div className="card-body" style={{ paddingTop: 4 }}>
        {data?.narrative && (
          <div className="bubble" style={{ marginBottom: 8, borderLeft: "3px solid #7c6cf0" }}>
            <AiText text={data.narrative} onFinding={openFinding} />
          </div>
        )}
        {!data ? <Skeleton h={120} /> : (
          <div>
            {data.insights.map((i) => (
              <div key={i.title} className="ai-insight">
                <SeverityBadge sev={i.severity} />
                <div>
                  <b>{i.title}</b>
                  <div className="muted small">
                    {i.text}{" "}
                    {i.findings.slice(0, 3).map((pt) => <button key={pt} className="btn sm ghost mono" style={{ minHeight: 24, padding: "0 6px" }} onClick={() => openFinding(pt)}>{pt}</button>)}
                  </div>
                </div>
                <Link className="btn sm" href={i.action.href}>{i.action.label} <ArrowRight size={13} /></Link>
              </div>
            ))}
          </div>
        )}
        <form className="row" style={{ gap: 8, marginTop: 12 }} onSubmit={(e) => { e.preventDefault(); ask(q); }}>
          <Sparkles size={16} color="#7c6cf0" aria-hidden />
          <input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask AI about your personal data…" aria-label="Ask AI" maxLength={MAX_CHARS} />
          <CharCount n={q.length} />
          <button className="btn primary" disabled={busy || q.trim().length < 3 || q.length > MAX_CHARS} aria-label="Ask"><Send size={15} /></button>
        </form>
        <div className="row wrap" style={{ gap: 6, marginTop: 8 }}>
          {CHIPS.map((c) => <button key={c} className="suggest" onClick={() => ask(c)}>{c}</button>)}
        </div>
        {(busy || a) && (
          <div className="bubble" style={{ marginTop: 12 }} aria-live="polite">
            {busy ? <span className="ai-typing">Thinking</span> : (
              <>
                <div style={{ marginBottom: 6 }}><ModelBadge mode={a!.mode} model={a!.model} /></div>
                <AiText text={a!.answer} onFinding={openFinding} />
              </>
            )}
            {a && !busy && a.mode !== "llm" && a.findings.length > 0 && (
              <div className="row wrap" style={{ gap: 6, marginTop: 8 }}>
                {a.findings.map((f) => <button key={f.pt_id} className="suggest mono" onClick={() => openFinding(f.pt_id)}>{f.pt_id} {f.label}</button>)}
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

/** First screen when the twin is empty: do the job immediately. */
export function StartScreen() {
  const app = useApp();
  const fileRef = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  return (
    <div className="start">
      <div className="stack">
        <div className="row" style={{ gap: 8 }}>
          <AiBadge label="AI DETECTION" how="Every column is scored on three explainable signals: header keywords, value patterns and real validators (Verhoeff, Luhn, GSTIN checksum…). Runs offline; raw values are discarded after the scan." />
        </div>
        <h1 style={{ fontSize: "clamp(30px, 4vw, 44px)", letterSpacing: "-0.03em" }}>Find the personal data in your systems.</h1>
        <div data-own-drop className={`dropzone ${over ? "over" : ""}`}
          onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
          onDrop={(e) => { e.preventDefault(); setOver(false); const f = e.dataTransfer.files[0]; if (f) app.startScan(f); }}>
          <Upload size={30} color="var(--accent)" aria-hidden />
          <b>Drop a CSV or SQLite file</b>
          <div className="row wrap" style={{ justifyContent: "center" }}>
            <button className="btn primary lg" onClick={app.loadDemo} disabled={app.demoLoading}><Play size={16} /> Load sample company</button>
            <button className="btn lg" onClick={() => fileRef.current?.click()}><FileSearch size={16} /> Choose file</button>
            <Tip text="The sample is Acme Fintech India: synthetic data with 3 historical scans. Your files are sampled in memory (1,000 rows by default) and raw values are never stored." />
          </div>
          <input ref={fileRef} type="file" hidden accept=".csv,.tsv,.txt,.db,.sqlite,.sqlite3" aria-label="Choose a CSV or SQLite file" onChange={(e) => e.target.files?.[0] && app.startScan(e.target.files[0])} />
        </div>
      </div>
      <TwinHero />
    </div>
  );
}
