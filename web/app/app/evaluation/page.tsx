"use client";

import { Download, UserCheck } from "lucide-react";
import { useMemo, useState } from "react";
import { useApp } from "@/components/app-context";
import { EvalReport } from "@/components/eval-report";
import { ErrorCard, PageHead, Skeleton } from "@/components/ui";
import { download, post } from "@/lib/api";
import { ALL_CLASSES, CLASS_META, CLASSES, ClassChip } from "@/lib/classes";
import { invalidate, useApi } from "@/lib/hooks";
import type { EvalResult, Finding } from "@/lib/types";

type Human = { reviewed: number; confirmed_correct: number; precision: number | null; per_class: Record<string, { reviewed: number; confirmed_correct: number; precision: number | null }> };
type Mine = { labels: Record<string, string>; labelled: number; metrics: (Omit<EvalResult, "errors" | "ablation" | "per_dataset">) | null };

export default function EvaluationPage() {
  const app = useApp();
  const { data, error, reload } = useApi<{ benchmark: EvalResult; human: Human; mine: Mine }>("/api/evaluation");
  const { data: inv } = useApi<{ rows: Finding[] }>("/api/inventory");
  const [tab, setTab] = useState<"benchmark" | "human" | "mine">("benchmark");
  const [labelFilter, setLabelFilter] = useState("");
  const rows = useMemo(() => (inv?.rows ?? []).filter((r) => !labelFilter || `${r.table}.${r.column}`.toLowerCase().includes(labelFilter.toLowerCase())).slice(0, 80), [inv, labelFilter]);

  const label = async (key: string, truth: string) => {
    try {
      await post("/api/labels", { key, true_class: truth || null });
      invalidate();
    } catch (e) {
      app.toast((e as Error).message, { kind: "error" });
    }
  };

  if (error) return <ErrorCard message={error.message} onRetry={reload} />;
  return (
    <>
      <PageHead title="Evaluation" ai="AI ACCURACY"
        desc="How accurate is detection? Measured on a synthetic labelled benchmark, by human review decisions, and on columns you label yourself."
        actions={<>
          <button className="btn sm" onClick={() => download("/api/evaluation/export?format=json")}><Download size={14} /> JSON</button>
          <button className="btn sm" onClick={() => download("/api/evaluation/export?format=csv")}><Download size={14} /> CSV</button>
        </>} />
      <div className="seg" role="tablist" style={{ marginBottom: 16 }}>
        <button role="tab" aria-pressed={tab === "benchmark"} aria-selected={tab === "benchmark"} onClick={() => setTab("benchmark")}>Synthetic benchmark</button>
        <button role="tab" aria-pressed={tab === "human"} aria-selected={tab === "human"} onClick={() => setTab("human")}>Human-confirmed precision</button>
        <button role="tab" aria-pressed={tab === "mine"} aria-selected={tab === "mine"} onClick={() => setTab("mine")}>Run on my data</button>
      </div>
      {!data ? <div className="stack"><Skeleton h={100} /><Skeleton h={300} /></div> : tab === "benchmark" ? (
        <EvalReport r={data.benchmark} />
      ) : tab === "human" ? (
        <section className="card" aria-label="Human-confirmed precision">
          <div className="card-head"><h3 className="row" style={{ gap: 8 }}><UserCheck size={16} /> Human-confirmed precision</h3>
            <b className="num" style={{ fontSize: 22, color: "var(--accent)" }}>{data.human.precision == null ? "—" : data.human.precision.toFixed(3)}</b></div>
          <div className="card-body stack-sm">
            <p className="muted small">{data.human.confirmed_correct} of {data.human.reviewed} reviewed candidates confirmed as detected.</p>
            <p className="muted small">Only human review decisions count here. AI auto-approvals are excluded.</p>
            <table className="table">
              <thead><tr><th>Detected class</th><th className="r">Reviewed</th><th className="r">Confirmed as detected</th><th className="r">Precision</th></tr></thead>
              <tbody>{CLASSES.map((c) => { const m = data.human.per_class[c]; return <tr key={c}><td><ClassChip cls={c} /></td><td className="r num">{m.reviewed}</td><td className="r num">{m.confirmed_correct}</td><td className="r num">{m.precision == null ? "—" : m.precision.toFixed(3)}</td></tr>; })}</tbody>
            </table>
          </div>
        </section>
      ) : (
        <div className="grid" style={{ gridTemplateColumns: "minmax(0, 1.3fr) minmax(0, 1fr)", alignItems: "start" }}>
          <section className="card" aria-label="Label your columns">
            <div className="card-head"><h3>Label a few of your columns</h3><input className="input" style={{ width: 200, minHeight: 34 }} placeholder="Filter columns" value={labelFilter} onChange={(e) => setLabelFilter(e.target.value)} aria-label="Filter columns" /></div>
            <div style={{ maxHeight: 520, overflowY: "auto" }}>
              <table className="table">
                <thead><tr><th>Column</th><th>Detected</th><th>True class (your label)</th></tr></thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.key}>
                      <td><code>{r.table}.{r.column}</code></td>
                      <td><ClassChip cls={r.detected_class} compact /></td>
                      <td>
                        <select className="input" style={{ minHeight: 32, fontSize: 13 }} value={data.mine.labels[r.key] ?? ""} onChange={(e) => label(r.key, e.target.value)} aria-label={`True class for ${r.column}`}>
                          <option value="">Not labelled</option>
                          {ALL_CLASSES.map((c) => <option key={c} value={c}>{CLASS_META[c].label}</option>)}
                        </select>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <section className="card pad stack-sm" aria-label="Your results">
            <b>Results on your data</b>
            {!data.mine.metrics ? <p className="muted small">Label a column to start.</p> : (
              <>
                <p className="small muted">{data.mine.labelled} labelled columns · accuracy <b className="num">{data.mine.metrics.accuracy.toFixed(3)}</b> · macro F1 <b className="num">{data.mine.metrics.macro.f1.toFixed(3)}</b></p>
                <table className="table">
                  <thead><tr><th>Class</th><th className="r">P</th><th className="r">R</th><th className="r">n</th></tr></thead>
                  <tbody>{CLASSES.filter((c) => data.mine.metrics!.per_class[c].support || data.mine.metrics!.per_class[c].fp).map((c) => { const m = data.mine.metrics!.per_class[c]; return <tr key={c}><td><ClassChip cls={c} compact /></td><td className="r num">{m.precision.toFixed(2)}</td><td className="r num">{m.recall.toFixed(2)}</td><td className="r num">{m.support}</td></tr>; })}</tbody>
                </table>
              </>
            )}
          </section>
        </div>
      )}
    </>
  );
}
