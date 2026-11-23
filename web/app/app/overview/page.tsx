"use client";

import { AlertTriangle, ArrowRight, CheckCircle2, Database, FileWarning, Gauge as GaugeIcon, ListChecks, ScanSearch, Table2 } from "lucide-react";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useNav } from "@/components/shell";
import { AiPanel, StartScreen } from "@/components/ai";
import { ChartFrame, ErrorCard, Gauge, KpiTile, PageHead, SkeletonPage, Tip } from "@/components/ui";
import { CLASS_META, CLASSES, ClassChip, SeverityBadge } from "@/lib/classes";
import { useApi } from "@/lib/hooks";
import type { Overview } from "@/lib/types";

const tooltipStyle = { background: "var(--surface-3)", border: "1px solid var(--border-strong)", borderRadius: 10, color: "var(--text)", fontSize: 12.5 };

export default function OverviewPage() {
    const { go, params, openFinding } = useNav();
  const scan = params.get("scan");
  const { data, error, reload } = useApi<Overview>(`/api/overview${scan ? `?scan=${scan}` : ""}`);
  const [overlay, setOverlay] = useState(false);

  if (error) return <ErrorCard message={error.message} onRetry={reload} />;
  if (!data) return <SkeletonPage />;
  const k = data.kpis;
  const p = data.previous;

  if (!k.columns) return <StartScreen />;

  const classData = CLASSES.map((c) => ({ name: CLASS_META[c].label, cls: c, value: data.by_class[c] ?? 0 }));
  const gapData = (["High", "Medium", "Low"] as const).map((s) => ({ name: s, value: data.gaps_by_severity[s] ?? 0 }));
  const maxHeat = Math.max(1, ...data.heatmap.flatMap((h) => Object.values(h.counts)));

  return (
    <>
      <PageHead
        title={scan ? `Personal-data estate · scan #${scan}` : "Personal-data estate"}
        desc="What the twin found and what needs attention. Every finding is a candidate until a person reviews it."
      />
      <AiPanel />

      <div className="grid" style={{ gridTemplateColumns: "minmax(260px, 320px) minmax(0, 1fr)", alignItems: "stretch" }}>
        <section className="card pad stack-sm" aria-label="Privacy posture" style={{ justifyItems: "center", textAlign: "center" }} title={data.posture.formula}>
          <div className="row" style={{ gap: 6 }}><GaugeIcon size={16} color="var(--accent)" /><b>Privacy posture</b><Tip text={`${data.posture.label} ${data.posture.formula}`} /></div>
          <Gauge score={data.posture.score} />
          <div className="stack-sm" style={{ width: "100%", textAlign: "left" }}>
            {Object.entries(data.posture.components).map(([key, v]) => (
              <div key={key} className="row between small">
                <span className="muted">{key.replace(/_/g, " ")}</span>
                <span className="num">{key.includes("risk") || key.includes("gap") ? v.toFixed(2) : `${Math.round(v * 100)}%`}</span>
              </div>
            ))}
          </div>
        </section>
        <div className="kpis" data-tour="kpis" style={{ alignContent: "start" }}>
          <KpiTile label="Sources" value={k.sources} prev={p?.sources} icon={<Database size={14} />} onClick={() => go("/app/sources/")} />
          <KpiTile label="Columns scanned" value={k.columns} prev={p?.columns} icon={<Table2 size={14} />} onClick={() => go("/app/inventory/")} />
          <KpiTile label="PII candidates" value={k.candidates} prev={p?.candidates} icon={<ScanSearch size={14} />} invert onClick={() => go("/app/inventory/", { personal: "1" })} />
          <KpiTile label="Confirmed" value={k.confirmed} prev={p?.confirmed} icon={<CheckCircle2 size={14} />} onClick={() => go("/app/inventory/", { status: "confirmed" })} />
          <KpiTile label="Open gaps" value={k.open_gaps} prev={p?.open_gaps} icon={<FileWarning size={14} />} invert onClick={() => go("/app/metadata/")} />
          <KpiTile label="Reviewed" value={k.reviewed_pct} prev={p?.reviewed_pct} suffix="%" icon={<ListChecks size={14} />} onClick={() => go("/app/review/")} />
          <KpiTile label="Posture" value={k.posture} prev={p?.posture} icon={<GaugeIcon size={14} />} onClick={() => go("/app/simulator/", { tab: "posture" })} hint={data.posture.formula} />
        </div>
      </div>

      {data.drift.length > 0 && (
        <section className="card" style={{ marginTop: 16 }} aria-label="Drift alerts">
          <div className="card-head">
            <h3 className="row" style={{ gap: 8 }}><AlertTriangle size={16} color="var(--sev-high)" /> PII drift since the previous scan</h3>
            <button className="btn sm ghost" onClick={() => go("/app/time-machine/")}>Open Time Machine <ArrowRight size={14} /></button>
          </div>
          <ul style={{ listStyle: "none", margin: 0, padding: "8px 20px 16px", display: "grid", gap: 8 }}>
            {data.drift.map((d) => (
              <li key={d.pt_id + d.message} className="row wrap" style={{ gap: 10 }}>
                <SeverityBadge sev={d.severity} />
                <ClassChip cls={d.class} compact />
                <button className="btn sm ghost mono" onClick={() => openFinding(d.pt_id)}>{d.pt_id}</button>
                <span>{d.message}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="grid cols-2" style={{ marginTop: 16 }}>
        <ChartFrame title="Candidates by class" desc={`Personal-data candidates by class: ${classData.map((c) => `${c.name} ${c.value}`).join(", ")}.`}
          table={{ head: ["Class", "Candidates"], rows: classData.map((c) => [c.name, c.value]) }}>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={classData} layout="vertical" margin={{ left: 12, right: 24, top: 4, bottom: 16 }}>
              <CartesianGrid horizontal={false} stroke="var(--border)" />
              <XAxis type="number" allowDecimals={false} stroke="var(--text-3)" fontSize={12} label={{ value: "Columns", position: "insideBottom", offset: -8, fill: "var(--text-3)", fontSize: 12 }} />
              <YAxis type="category" dataKey="name" width={110} stroke="var(--text-3)" fontSize={12} />
              <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "var(--surface-2)" }} />
              <Bar dataKey="value" name="Candidates" radius={[0, 6, 6, 0]} onClick={(d: { cls?: string }) => d.cls && go("/app/inventory/", { class: d.cls })} style={{ cursor: "pointer" }}>
                {classData.map((c) => <Cell key={c.cls} fill={CLASS_META[c.cls].color} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartFrame>
        <ChartFrame title="Metadata gaps by severity" desc={`Open gaps: ${gapData.map((g) => `${g.name} ${g.value}`).join(", ")}.`}
          table={{ head: ["Severity", "Open gaps"], rows: gapData.map((g) => [g.name, g.value]) }}>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={gapData} margin={{ left: 0, right: 12, top: 4, bottom: 16 }}>
              <CartesianGrid vertical={false} stroke="var(--border)" />
              <XAxis dataKey="name" stroke="var(--text-3)" fontSize={12} label={{ value: "Severity", position: "insideBottom", offset: -8, fill: "var(--text-3)", fontSize: 12 }} />
              <YAxis allowDecimals={false} stroke="var(--text-3)" fontSize={12} label={{ value: "Gaps", angle: -90, position: "insideLeft", fill: "var(--text-3)", fontSize: 12 }} />
              <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "var(--surface-2)" }} />
              <Bar dataKey="value" name="Open gaps" radius={[6, 6, 0, 0]} onClick={() => go("/app/metadata/")} style={{ cursor: "pointer" }}>
                {gapData.map((g) => <Cell key={g.name} fill={`var(--sev-${g.name.toLowerCase()})`} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartFrame>
      </div>

      <div className="grid" style={{ gridTemplateColumns: "minmax(0, 1.6fr) minmax(0, 1fr)", marginTop: 16 }}>
        <ChartFrame
          title="Tables × classes"
          desc="Heatmap of personal-data candidates per table and class, with optional re-identification risk."
          table={{ head: ["Table", ...CLASSES.map((c) => CLASS_META[c].label), "Unique rows %"], rows: data.heatmap.map((h) => [h.table, ...CLASSES.map((c) => h.counts[c] ?? 0), h.unique_pct ?? "—"]) }}
          actions={
            <label className="row small" style={{ gap: 6, cursor: "pointer" }}>
              <input type="checkbox" checked={overlay} onChange={(e) => setOverlay(e.target.checked)} /> Re-identification overlay
            </label>
          }
        >
          <div className="heat" style={{ gridTemplateColumns: `minmax(110px, 1.4fr) repeat(${CLASSES.length}, minmax(36px, 1fr))${overlay ? " minmax(64px, 0.9fr)" : ""}` }}>
            <span />
            {CLASSES.map((c) => <span key={c} className="faint small" style={{ textAlign: "center" }} title={CLASS_META[c].label}>{CLASS_META[c].short}</span>)}
            {overlay && <span className="faint small" style={{ textAlign: "center" }}>Unique</span>}
            {data.heatmap.map((h) => (
              <div key={h.key} style={{ display: "contents" }}>
                <button className="rowlabel btn ghost sm" style={{ justifyContent: "flex-start" }} onClick={() => go("/app/inventory/", { q: h.table })}>{h.table}</button>
                {CLASSES.map((c) => {
                  const v = h.counts[c] ?? 0;
                  return (
                    <span key={c} className={`cell ${v ? "" : "zero"}`} title={`${h.table}: ${v} ${CLASS_META[c].label}`}
                      style={v ? { background: `color-mix(in srgb, ${CLASS_META[c].color} ${18 + (60 * v) / maxHeat}%, transparent)`, color: "var(--text)" } : undefined}>
                      {v || "·"}
                    </span>
                  );
                })}
                {overlay && (
                  <span className="cell" style={{ background: h.unique_pct == null ? "var(--surface-2)" : `color-mix(in srgb, var(--sev-high) ${10 + h.unique_pct * 0.6}%, transparent)` }}>
                    {h.unique_pct == null ? "—" : `${Math.round(h.unique_pct)}%`}
                  </span>
                )}
              </div>
            ))}
          </div>
        </ChartFrame>
        <section className="card" aria-label="Top-risk tables">
          <div className="card-head"><h3 className="row" style={{ gap: 6 }}>Highest-risk tables <Tip text="Risk = confidence × class sensitivity × metadata-gap severity. Click a table to simulate its breach blast radius." /></h3></div>
          <ol style={{ listStyle: "none", margin: 0, padding: 8 }}>
            {data.top_tables.map((t, i) => (
              <li key={t.key}>
                <button className="btn ghost" style={{ width: "100%", justifyContent: "flex-start", minHeight: 52 }} onClick={() => go("/app/simulator/", { target: t.key })}>
                  <span className="num faint" style={{ width: 18 }}>{i + 1}</span>
                  <span style={{ display: "grid", textAlign: "left" }}>
                    <code>{t.table}</code>
                    <span className="small faint">{t.personal} personal fields · {t.rows?.toLocaleString() ?? "?"} rows</span>
                  </span>
                  <span style={{ marginLeft: "auto", width: 80 }} className="meter" aria-label={`Risk ${t.risk}`}>
                    <span style={{ width: `${Math.min(100, (t.risk / Math.max(...data.top_tables.map((x) => x.risk))) * 100)}%`, background: "var(--sev-high)" }} />
                  </span>
                </button>
              </li>
            ))}
          </ol>
        </section>
      </div>
      <style>{`@media (max-width: 960px){ .content .grid[style*="minmax(260px"]{grid-template-columns:minmax(0,1fr) !important} .content .grid[style*="1.6fr"]{grid-template-columns:minmax(0,1fr) !important} }`}</style>
    </>
  );
}
