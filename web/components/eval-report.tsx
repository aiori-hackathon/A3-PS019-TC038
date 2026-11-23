"use client";

import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ALL_CLASSES, CLASS_META, CLASSES, ClassChip } from "@/lib/classes";
import type { EvalResult } from "@/lib/types";
import { ChartFrame, Tip } from "./ui";

export function EvalReport({ r }: { r: EvalResult }) {
  const [kind, setKind] = useState<string>("");
  const errors = r.errors.filter((e) => !kind || e.kind === kind);
  const maxConf = Math.max(...ALL_CLASSES.flatMap((t) => ALL_CLASSES.map((p) => r.confusion[t]?.[p] ?? 0)));
  return (
    <div className="stack">
      <div className="kpis">
        {[
          ["Macro F1", r.macro.f1.toFixed(3), "Average over the five personal-data classes"],
          ["Macro precision", r.macro.precision.toFixed(3), ""],
          ["Macro recall", r.macro.recall.toFixed(3), ""],
          ["Micro F1", r.micro.f1.toFixed(3), "Pooled over all personal-data predictions"],
          ["Accuracy", r.accuracy.toFixed(3), "Including NOT_PERSONAL columns"],
          ["Labelled columns", String(r.columns), `${r.tables} tables in ${r.datasets.length} datasets`],
        ].map(([l, v, h]) => (
          <div key={l} className="kpi" style={{ cursor: "default" }} title={h}>
            <span className="label">{l}</span>
            <span className="value num" style={{ color: l === "Macro F1" ? "var(--accent)" : undefined }}>{v}</span>
            <span className="trend">{h}</span>
          </div>
        ))}
      </div>

      <div className="grid cols-2">
        <section className="card" aria-label="Per-class metrics">
          <div className="card-head"><h3 className="row" style={{ gap: 6 }}>Per-class results <Tip text={`${r.caveat} Generated ${new Date(r.generated_at).toLocaleString()}.`} /></h3><span className="small faint">rules v{r.ruleset_version} · {r.ruleset_hash.slice(0, 10)}</span></div>
          <table className="table">
            <thead><tr><th>Class</th><th className="r">Precision</th><th className="r">Recall</th><th className="r">F1</th><th className="r">Support</th></tr></thead>
            <tbody>
              {CLASSES.map((c) => {
                const m = r.per_class[c];
                return (
                  <tr key={c}>
                    <td><ClassChip cls={c} /></td>
                    <td className="r num">{m.precision.toFixed(3)}</td><td className="r num">{m.recall.toFixed(3)}</td>
                    <td className="r num"><b>{m.f1.toFixed(3)}</b></td><td className="r num">{m.support}</td>
                  </tr>
                );
              })}
              <tr><td><b>Macro average</b></td><td className="r num">{r.macro.precision.toFixed(3)}</td><td className="r num">{r.macro.recall.toFixed(3)}</td><td className="r num"><b>{r.macro.f1.toFixed(3)}</b></td><td /></tr>
              <tr><td>Micro average</td><td className="r num">{r.micro.precision.toFixed(3)}</td><td className="r num">{r.micro.recall.toFixed(3)}</td><td className="r num">{r.micro.f1.toFixed(3)}</td><td /></tr>
              <tr><td className="faint">Not personal (specificity)</td><td colSpan={3} className="r num faint">{r.not_personal.specificity?.toFixed(3)}</td><td className="r num faint">{r.not_personal.support}</td></tr>
            </tbody>
          </table>
        </section>

        <ChartFrame title="Confusion matrix" desc="Rows are true classes, columns are predicted classes."
          table={{ head: ["True \\ Predicted", ...ALL_CLASSES.map((c) => CLASS_META[c].label)], rows: ALL_CLASSES.map((t) => [CLASS_META[t].label, ...ALL_CLASSES.map((p) => r.confusion[t]?.[p] ?? 0)]) }}>
          <div className="heat" style={{ gridTemplateColumns: `112px repeat(${ALL_CLASSES.length}, minmax(32px, 1fr))` }}>
            <span className="faint small">true ↓ / pred →</span>
            {ALL_CLASSES.map((c) => <span key={c} className="faint small" style={{ textAlign: "center" }} title={CLASS_META[c].label}>{CLASS_META[c].short}</span>)}
            {ALL_CLASSES.map((t) => (
              <div key={t} style={{ display: "contents" }}>
                <span className="rowlabel small" title={CLASS_META[t].label}>{CLASS_META[t].label}</span>
                {ALL_CLASSES.map((p) => {
                  const v = r.confusion[t]?.[p] ?? 0;
                  const diag = t === p;
                  return (
                    <span key={p} className={`cell ${v ? "" : "zero"}`} title={`True ${CLASS_META[t].label}, predicted ${CLASS_META[p].label}: ${v}`}
                      style={v ? { background: diag ? `color-mix(in srgb, var(--ok) ${20 + (60 * v) / maxConf}%, transparent)` : `color-mix(in srgb, var(--sev-high) ${30 + (50 * v) / maxConf}%, transparent)`, color: "var(--text)" } : undefined}>
                      {v || "·"}
                    </span>
                  );
                })}
              </div>
            ))}
          </div>
        </ChartFrame>
      </div>

      <ChartFrame title="Ablation: what each signal adds" desc={`Macro F1 by signal combination: ${r.ablation.map((a) => `${a.label} ${a.macro_f1}`).join("; ")}.`}
        table={{ head: ["Signals", "Macro F1", "Micro F1", "Macro precision", "Macro recall", "Accuracy"], rows: r.ablation.map((a) => [a.label, a.macro_f1, a.micro_f1, a.macro_precision, a.macro_recall, a.accuracy]) }}>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={r.ablation} margin={{ left: 0, right: 16, top: 8, bottom: 24 }}>
            <CartesianGrid vertical={false} stroke="var(--border)" />
            <XAxis dataKey="label" stroke="var(--text-3)" fontSize={11.5} interval={0} label={{ value: "Signals used", position: "insideBottom", offset: -16, fill: "var(--text-3)", fontSize: 12 }} />
            <YAxis domain={[0.6, 1]} stroke="var(--text-3)" fontSize={12} label={{ value: "Macro F1", angle: -90, position: "insideLeft", fill: "var(--text-3)", fontSize: 12 }} />
            <Tooltip contentStyle={{ background: "var(--surface-3)", border: "1px solid var(--border-strong)", borderRadius: 10, color: "var(--text)" }} cursor={{ fill: "var(--surface-2)" }} />
            <Bar dataKey="macro_f1" name="Macro F1" fill="var(--accent)" radius={[6, 6, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </ChartFrame>

      <section className="card" aria-label="Errors">
        <div className="card-head">
          <h3>Every false positive and false negative ({r.errors.length})</h3>
          <div className="seg" role="group" aria-label="Filter errors">
            {[["", "All"], ["FP", "False positives"], ["FN", "False negatives"], ["WRONG_CLASS", "Wrong class"]].map(([k, l]) => (
              <button key={k} aria-pressed={kind === k} onClick={() => setKind(k)}>{l}</button>
            ))}
          </div>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table className="table">
            <thead><tr><th>Kind</th><th>Column</th><th>True</th><th>Predicted</th><th>Signals (H / V / C)</th><th>Likely cause</th></tr></thead>
            <tbody>
              {errors.map((e) => (
                <tr key={`${e.source}.${e.table}.${e.column}`}>
                  <td><span className="tag">{e.kind}</span></td>
                  <td><code>{e.table}.{e.column}</code><div className="small faint">{e.source}{e.note ? ` · ${e.note}` : ""}</div></td>
                  <td><ClassChip cls={e.true_class} compact /></td>
                  <td><ClassChip cls={e.predicted} compact /></td>
                  <td className="num small">{e.signals.header} / {Math.round(e.signals.value * 100)}% / {Math.round(e.signals.validator * 100)}%</td>
                  <td className="small" style={{ minWidth: 260 }}>{e.likely_cause}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      
    </div>
  );
}
