"use client";

import dynamic from "next/dynamic";
import { Bomb, Clock, Fingerprint, Gauge as GaugeIcon, Link2, Network } from "lucide-react";
import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useApp } from "@/components/app-context";
import type { Lineage } from "@/components/lineage";
import { useNav } from "@/components/shell";
import { ChartFrame, EmptyState, ErrorCard, Gauge, PageHead, Skeleton, Tip } from "@/components/ui";
import { post } from "@/lib/api";
import { CLASS_META, ClassChip, SeverityBadge } from "@/lib/classes";
import { useApi, useDebounced } from "@/lib/hooks";
import type { Cls, Posture, Severity } from "@/lib/types";

const LineageGraph = dynamic(() => import("@/components/lineage"), { ssr: false, loading: () => <Skeleton h={520} r={12} /> });

const TABS = [
  { key: "blast", label: "Blast radius", Icon: Bomb },
  { key: "reid", label: "Re-identification", Icon: Fingerprint },
  { key: "retention", label: "Retention what-if", Icon: Clock },
  { key: "lineage", label: "Lineage", Icon: Network },
  { key: "posture", label: "Posture", Icon: GaugeIcon },
] as const;

export default function SimulatorPage() {
  const { params, router, pathname } = useNav();
  const tab = params.get("tab") ?? "blast";
  const setTab = (t: string, extra: Record<string, string> = {}) => {
    const p = new URLSearchParams(params.toString());
    p.set("tab", t);
    for (const [k, v] of Object.entries(extra)) p.set(k, v);
    router.replace(`${pathname}?${p}`, { scroll: false });
  };
  const { data: lin, error } = useApi<Lineage>("/api/lineage");
  const app = useApp();
  if (error) return <ErrorCard message={error.message} />;
  if (lin && !lin.nodes.length)
    return (<><PageHead eyebrow="Prove" title="Simulator" /><EmptyState title="Nothing to simulate yet" body="Simulations run on the twin's aggregates. Load the demo or scan a source first." action={<button className="btn primary" onClick={app.loadDemo}>Load demo</button>} /></>);

  return (
    <>
      <PageHead title="Simulator" ai="AI SIMULATION" desc="“What if” scenarios on the twin. Simulations use stored aggregates only and change nothing." />
      <div className="seg" role="tablist" aria-label="Simulations" style={{ marginBottom: 16, flexWrap: "wrap" }}>
        {TABS.map((t) => (
          <button key={t.key} role="tab" aria-selected={tab === t.key} aria-pressed={tab === t.key} onClick={() => setTab(t.key)}>
            <span className="row" style={{ gap: 6 }}><t.Icon size={15} aria-hidden />{t.label}</span>
          </button>
        ))}
      </div>
      {tab === "blast" && <Blast lineage={lin} onPick={(k) => setTab("blast", { target: k })} />}
      {tab === "reid" && <Reid />}
      {tab === "retention" && <Retention />}
      {tab === "lineage" && (lin ? (
        <section className="stack-sm">
          <LineageGraph data={lin} onSelect={(id) => setTab("blast", { target: id })} />
          <div className="row small faint" style={{ gap: 6 }}>Solid: same column name · Dashed: fingerprint overlap <Tip text={`${lin.method} Click a table to simulate its blast radius.`} /></div>
        </section>
      ) : <Skeleton h={520} />)}
      {tab === "posture" && <PostureTab />}
    </>
  );
}

type BlastResult = {
  target: string; tables: string[]; classes: Record<string, number>; columns: { pt_id: string; column: string; class: Cls }[]; records: number;
  combinations: { name: string; severity: Severity }[]; linked_tables: { key: string; table: string; via: string[] }[];
  combinations_if_joined: { name: string; severity: Severity }[]; linked_records: number; label: string;
};

function Blast({ lineage, onPick }: { lineage?: Lineage; onPick: (k: string) => void }) {
  const { params, openFinding } = useNav();
  const target = params.get("target") ?? lineage?.nodes.slice().sort((a, b) => b.risk - a.risk)[0]?.id ?? null;
  const { data, error } = useApi<BlastResult>(target ? `/api/blast?target=${encodeURIComponent(target)}` : null);
  const sources = Array.from(new Map((lineage?.nodes ?? []).map((n) => [n.id.split("/")[0], n.source])).entries());
  return (
    <div className="grid" style={{ gridTemplateColumns: "minmax(220px, 300px) minmax(0, 1fr)", alignItems: "start" }}>
      <section className="card" aria-label="Pick a table">
        <div className="card-head"><h4>Pick a table or source</h4></div>
        <div style={{ padding: 8, display: "grid", gap: 2 }}>
          {sources.map(([id, name]) => (
            <button key={id} className="btn ghost sm" style={{ justifyContent: "flex-start", fontWeight: target === id ? 700 : 500, width: "100%", whiteSpace: "normal", textAlign: "left", height: "auto", padding: "8px 10px" }} onClick={() => onPick(id)}>Whole source: {name}</button>
          ))}
          {(lineage?.nodes ?? []).map((n) => (
            <button key={n.id} className="btn ghost sm mono" aria-pressed={target === n.id} style={{ justifyContent: "flex-start", width: "100%", background: target === n.id ? "var(--accent-soft)" : undefined }} onClick={() => onPick(n.id)}>
              <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{n.table}</span><span className="faint" style={{ marginLeft: "auto" }} aria-label={`${n.personal} personal fields`}>{n.personal}</span>
            </button>
          ))}
        </div>
      </section>
      <section className="stack">
        {error && <ErrorCard message={error.message} />}
        {!data ? <Skeleton h={300} /> : (
          <>
            <div className="card pad" style={{ borderColor: "color-mix(in srgb, var(--sev-high) 40%, var(--border))", background: "linear-gradient(135deg, color-mix(in srgb, var(--sev-high) 8%, var(--surface)), var(--surface))" }}>
              <div className="eyebrow row" style={{ color: "var(--sev-high)", gap: 6 }}>Simulation: technical exposure only <Tip text={data.label} /></div>
              <h3 className="mono">{data.tables.join(", ")}</h3>
              <div className="kpis" style={{ marginTop: 16 }}>
                <div className="kpi" style={{ cursor: "default" }}><span className="label">Records exposed (approx.)</span><span className="value num">{data.records.toLocaleString()}</span></div>
                <div className="kpi" style={{ cursor: "default" }}><span className="label">Personal-data columns</span><span className="value num">{data.columns.length}</span></div>
                <div className="kpi" style={{ cursor: "default" }}><span className="label">Classes exposed</span><span className="value num">{Object.keys(data.classes).length}</span></div>
                <div className="kpi" style={{ cursor: "default" }}><span className="label">Linked tables</span><span className="value num">{data.linked_tables.length}</span></div>
              </div>
              <div className="row wrap" style={{ gap: 6, marginTop: 12 }}>{Object.entries(data.classes).map(([c, n]) => <span key={c} className="row" style={{ gap: 4 }}><ClassChip cls={c as Cls} /> <span className="num small">×{n}</span></span>)}</div>
              
            </div>
            <div className="grid cols-2">
              <section className="card pad stack-sm" aria-label="Identifier combinations">
                <b>Identifier combinations made possible</b>
                {data.combinations.length === 0 && <span className="faint small">No known high-risk combination within this selection.</span>}
                {data.combinations.map((c) => <div key={c.name} className="row small" style={{ gap: 8 }}><SeverityBadge sev={c.severity} />{c.name}</div>)}
                {data.combinations_if_joined.length > 0 && (
                  <>
                    <b style={{ marginTop: 8 }}>If joined with linked tables</b>
                    {data.combinations_if_joined.map((c) => <div key={c.name} className="row small" style={{ gap: 8 }}><SeverityBadge sev={c.severity} />{c.name}</div>)}
                  </>
                )}
              </section>
              <section className="card pad stack-sm" aria-label="Linked tables">
                <b className="row" style={{ gap: 6 }}><Link2 size={15} /> Linked via shared identifiers</b>
                {data.linked_tables.length === 0 && <span className="faint small">No links found.</span>}
                {data.linked_tables.map((l) => (
                  <button key={l.key} className="btn ghost sm" style={{ justifyContent: "flex-start" }} onClick={() => onPick(l.key)}>
                    <code>{l.table}</code><span className="faint small">via {l.via.join(", ")}</span>
                  </button>
                ))}
                {data.linked_records > 0 && <span className="small faint">≈{data.linked_records.toLocaleString()} more records reachable through links.</span>}
              </section>
            </div>
            <section className="card pad" aria-label="Exposed columns">
              <b>Exposed columns</b>
              <div className="row wrap" style={{ gap: 6, marginTop: 8 }}>
                {data.columns.map((c) => <button key={c.pt_id} className="suggest mono" onClick={() => openFinding(c.pt_id)} style={{ borderColor: CLASS_META[c.class].color }}>{c.column}</button>)}
              </div>
            </section>
          </>
        )}
      </section>
      <style>{`@media (max-width: 900px){ .content .grid[style*="minmax(220px"]{grid-template-columns:minmax(0,1fr) !important} }`}</style>
    </div>
  );
}

type ReidResult = { tables: { key: string; table: string; source: string; quasi_identifiers: { column: string; kind: string }[]; kanon: null | { quasi_identifiers: string[]; sample_rows: number; exact: { min_k: number; unique_pct: number; groups: number; rows_k_lt_5_pct: number }; generalised: { min_k: number; unique_pct: number; groups: number; rows_k_lt_5_pct: number } } }[]; method: string };

function Reid() {
  const { data } = useApi<ReidResult>("/api/reid");
  if (!data) return <Skeleton h={300} />;
  const withK = data.tables.filter((t) => t.kanon);
  return (
    <div className="stack">
      <ChartFrame title="Share of sampled rows that are unique on their quasi-identifiers" desc="Per table: percentage of sampled rows unique on exact and generalised quasi-identifiers."
        table={{ head: ["Table", "Quasi-identifiers", "Unique (exact) %", "Unique (generalised) %", "Min k (exact)"], rows: withK.map((t) => [t.table, t.kanon!.quasi_identifiers.join(", "), t.kanon!.exact.unique_pct, t.kanon!.generalised.unique_pct, t.kanon!.exact.min_k]) }}>
        <ResponsiveContainer width="100%" height={Math.max(160, withK.length * 56)}>
          <BarChart data={withK.map((t) => ({ name: t.table, exact: t.kanon!.exact.unique_pct, generalised: t.kanon!.generalised.unique_pct }))} layout="vertical" margin={{ left: 12, right: 24, bottom: 16 }}>
            <CartesianGrid horizontal={false} stroke="var(--border)" />
            <XAxis type="number" domain={[0, 100]} unit="%" stroke="var(--text-3)" fontSize={12} label={{ value: "Unique rows in sample", position: "insideBottom", offset: -8, fill: "var(--text-3)", fontSize: 12 }} />
            <YAxis type="category" dataKey="name" width={130} stroke="var(--text-3)" fontSize={12} />
            <Tooltip contentStyle={{ background: "var(--surface-3)", border: "1px solid var(--border-strong)", borderRadius: 10, color: "var(--text)" }} />
            <Bar dataKey="exact" name="Exact values" fill="var(--sev-high)" radius={[0, 4, 4, 0]} />
            <Bar dataKey="generalised" name="Generalised" fill="var(--sev-medium)" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </ChartFrame>
      <div className="grid cols-3">
        {withK.map((t) => (
          <section key={t.key} className="card pad stack-sm" aria-label={t.table}>
            <code><b>{t.table}</b></code>
            <p className="small"><b className="num">{Math.round(t.kanon!.exact.unique_pct)}%</b> of {t.kanon!.sample_rows.toLocaleString()} sampled rows are unique on {"{"}{t.kanon!.quasi_identifiers.join(", ")}{"}"}.</p>
            <p className="small muted">Generalised (5-year birth bands, 3-digit PIN): <b className="num">{Math.round(t.kanon!.generalised.unique_pct)}%</b> unique, min k = {t.kanon!.generalised.min_k}.</p>
          </section>
        ))}
      </div>
      
      
    </div>
  );
}

type RetentionResult = { tables: { key: string; table: string; rows: number; age_hist: null | { column: string; sampled: number; oldest_days: number; median_days: number }; columns: { pt_id: string; column: string; class: Cls; retention_days: number | null; retention_text: string; hypothetical: boolean; expired_pct: number | null }[] }[]; never_cleaned: { pt_id: string; column: string; class: Cls }[]; label: string };

function Retention() {
  const { openFinding } = useNav();
  const [assume, setAssume] = useState<Record<string, number>>({});
  const da = useDebounced(assume, 250);
  const [data, setData] = useState<RetentionResult | null>(null);
  useEffect(() => {
    post<RetentionResult>("/api/retention", { assume: da }).then(setData).catch(() => undefined);
  }, [da]);
  if (!data) return <Skeleton h={300} />;
  return (
    <div className="stack">
      <div className="card pad" style={{ borderColor: "color-mix(in srgb, var(--sev-medium) 40%, var(--border))" }}>
        <b className="row" style={{ gap: 6 }}>{data.never_cleaned.length} personal-data fields would never be cleaned up <Tip text={`No declared retention period. ${data.label} Percentages are estimated from the record-age histogram of the sample.`} /></b>
        
        <div className="row wrap" style={{ gap: 6, marginTop: 8 }}>
          {data.never_cleaned.slice(0, 40).map((c) => <button key={c.pt_id} className="suggest mono" onClick={() => openFinding(c.pt_id)}><ClassChip cls={c.class} compact /> {c.column}</button>)}
        </div>
      </div>
      <div className="grid cols-2">
        {data.tables.map((t) => {
          const hyp = assume[t.key];
          const maxDays = Math.max(365, Math.ceil((t.age_hist?.oldest_days ?? 3650) / 30) * 30);
          return (
            <section key={t.key} className="card pad stack-sm" aria-label={t.table}>
              <div className="row between"><code><b>{t.table}</b></code><span className="small faint">{t.rows.toLocaleString()} rows</span></div>
              {t.age_hist ? <span className="small faint">Record age from <code>{t.age_hist.column}</code>: median {Math.round(t.age_hist.median_days / 30)} months, oldest {Math.round(t.age_hist.oldest_days / 365 * 10) / 10} years (sample).</span> : <span className="small faint">No creation date column found, so expiry cannot be estimated.</span>}
              <label className="field">
                <span className="row between">Hypothetical retention for all fields <b className="num">{hyp ? `${Math.round(hyp / 30)} months` : "declared values"}</b></span>
                <input type="range" min={30} max={maxDays} step={30} value={hyp ?? maxDays} style={{ accentColor: "var(--accent)" }}
                  onChange={(e) => setAssume((a) => ({ ...a, [t.key]: Number(e.target.value) }))} aria-label={`Hypothetical retention for ${t.table}`} />
              </label>
              {hyp && <button className="btn sm ghost" onClick={() => setAssume((a) => { const n = { ...a }; delete n[t.key]; return n; })}>Reset to declared</button>}
              <table className="table">
                <thead><tr><th>Column</th><th>Retention</th><th className="r">Would be removed</th></tr></thead>
                <tbody>
                  {t.columns.map((c) => (
                    <tr key={c.pt_id}>
                      <td><code>{c.column}</code></td>
                      <td className="small">{c.retention_days ? (c.hypothetical ? `${Math.round(c.retention_days / 30)} mo (what-if)` : c.retention_text) : <span style={{ color: "var(--sev-high)" }}>never</span>}</td>
                      <td className="r num">{c.expired_pct == null ? "—" : `≈${c.expired_pct}%`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          );
        })}
      </div>
      
    </div>
  );
}

function PostureTab() {
  const { data } = useApi<Posture>("/api/posture");
  if (!data) return <Skeleton h={300} />;
  const weights: Record<string, number> = { metadata_coverage: 0.35, review_completion: 0.25, gap_severity_index: 0.25, reidentification_risk: 0.15 };
  return (
    <div className="grid" style={{ gridTemplateColumns: "minmax(240px, 320px) minmax(0, 1fr)", alignItems: "start" }}>
      <section className="card pad stack-sm" style={{ justifyItems: "center", textAlign: "center" }}>
        <Gauge score={data.score} size={220} />
        
      </section>
      <section className="card pad stack">
        <b className="row" style={{ gap: 6 }}>Transparent formula <Tip text={data.label} /></b>
        <code style={{ fontSize: 13, lineHeight: 1.7 }}>{data.formula}</code>
        {Object.entries(data.components).map(([k, v]) => {
          const inverted = k.includes("gap") || k.includes("risk");
          const contrib = weights[k] * (inverted ? 1 - v : v) * 100;
          return (
            <div key={k} className="stack-sm">
              <div className="row between small"><span>{k.replace(/_/g, " ")} {inverted && <span className="faint">(lower is better)</span>}</span><span className="num">{inverted ? v.toFixed(2) : `${Math.round(v * 100)}%`} → +{contrib.toFixed(1)} pts</span></div>
              <div className="meter"><span style={{ width: `${(contrib / (weights[k] * 100)) * 100}%` }} /></div>
            </div>
          );
        })}
      </section>
    </div>
  );
}
