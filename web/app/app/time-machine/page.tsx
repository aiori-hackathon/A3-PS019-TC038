"use client";

import { ArrowRight, GitCompare } from "lucide-react";
import { useEffect, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useApp } from "@/components/app-context";
import { useNav } from "@/components/shell";
import { ChartFrame, EmptyState, ErrorCard, PageHead, Skeleton } from "@/components/ui";
import { ClassChip, SeverityBadge } from "@/lib/classes";
import { fmtDate, useApi } from "@/lib/hooks";
import type { Cls, Drift, Severity } from "@/lib/types";

type TL = { seq: number; id: string; at: string; source: string; ruleset: string; candidates: number; open_gaps: number; posture: number | null; columns: number };
type Brief = { pt_id: string; key: string; source: string; table: string; column: string; class: Cls; confidence: number; band: string; status: string };
type Diff = {
  a: number; b: number; new: Brief[]; removed: Brief[];
  class_changes: (Brief & { before: Cls; after: Cls })[]; confidence_changes: (Brief & { before: number; after: number; before_band: string })[];
  gaps_opened: { pt_id: string; column: string; field: string; severity: Severity }[]; gaps_closed: { pt_id: string; column: string; field: string; severity: Severity }[];
  summary: Record<string, number>;
};
const tip = { background: "var(--surface-3)", border: "1px solid var(--border-strong)", borderRadius: 10, color: "var(--text)", fontSize: 12.5 };

export default function TimeMachinePage() {
  const app = useApp();
  const { openFinding, go } = useNav();
  const { data, error, reload } = useApi<{ scans: TL[]; drift: Drift[] }>("/api/timeline");
  const scans = data?.scans ?? [];
  const [b, setB] = useState<number | null>(null);
  const [a, setA] = useState<number | null>(null);
  useEffect(() => {
    if (scans.length >= 2 && b == null) {
      setB(scans[scans.length - 1].seq);
      setA(scans[scans.length - 2].seq);
    }
  }, [scans, b]);
  const { data: diff } = useApi<Diff>(a && b && a !== b ? `/api/diff?a=${Math.min(a, b)}&b=${Math.max(a, b)}` : null);

  if (error) return <ErrorCard message={error.message} onRetry={reload} />;
  if (!data) return <div className="stack"><Skeleton h={220} /><Skeleton h={260} /></div>;
  if (scans.length < 2)
    return (
      <>
        <PageHead title="Time Machine" />
        <EmptyState title="Rewind needs at least two scans" body="Each scan is a snapshot of the twin. Drop the same file again after it changes (or load the demo, which has three scans) to compare snapshots."
          action={<button className="btn primary" onClick={app.loadDemo}>Load demo with 3 scans</button>} />
      </>
    );

  const bi = scans.findIndex((s) => s.seq === b);
  return (
    <>
      <PageHead title="Time Machine" desc="Rewind the twin. Pick a snapshot, then compare any two scans to see what personal data appeared, disappeared or changed." />

      <section className="card pad" aria-label="Snapshots">
        <div className="deck" aria-hidden>
          {scans.map((s, i) => {
            const off = i - bi;
            const style = {
              transform: `translateX(calc(-50% + ${off * 64}%)) translateZ(${-Math.abs(off) * 120}px) rotateY(${off * -22}deg) scale(${1 - Math.abs(off) * 0.08})`,
              opacity: Math.abs(off) > 3 ? 0 : 1 - Math.abs(off) * 0.18,
              zIndex: 10 - Math.abs(off),
            };
            return (
              <button key={s.seq} tabIndex={-1} className={`deck-card ${s.seq === b ? "active" : ""}`} style={style} onClick={() => { setA(b); setB(s.seq); }}>
                <div className="row between"><b>Scan #{s.seq}</b><span className="tag">rules v{s.ruleset}</span></div>
                <div className="small faint">{fmtDate(s.at, true)}</div>
                <div className="grid cols-3" style={{ marginTop: 14, gap: 6 }}>
                  <div><div className="faint small">PII</div><b className="num" style={{ fontSize: 22 }}>{s.candidates}</b></div>
                  <div><div className="faint small">Gaps</div><b className="num" style={{ fontSize: 22 }}>{s.open_gaps}</b></div>
                  <div><div className="faint small">Posture</div><b className="num" style={{ fontSize: 22 }}>{s.posture ?? "—"}</b></div>
                </div>
              </button>
            );
          })}
        </div>
        <label className="field" style={{ marginTop: 8 }}>
          <span className="row between">Timeline <span className="faint">Snapshot #{b} selected · {fmtDate(scans[bi]?.at, true)}</span></span>
          <input type="range" min={0} max={scans.length - 1} value={bi < 0 ? scans.length - 1 : bi} aria-valuetext={`Scan ${b}`}
            onChange={(e) => setB(scans[Number(e.target.value)].seq)} style={{ width: "100%", accentColor: "var(--accent)" }} />
        </label>
        <div className="row between small faint">{scans.map((s) => <span key={s.seq}>#{s.seq}</span>)}</div>
        <div className="row" style={{ marginTop: 12 }}>
          <button className="btn sm" onClick={() => go("/app/overview/", { scan: String(b) })}>View the twin as of scan #{b} <ArrowRight size={14} /></button>
        </div>
      </section>

      <div className="grid cols-2" style={{ marginTop: 16 }}>
        <ChartFrame title="The twin over time" desc="Personal-data candidates, open gaps and posture per scan."
          table={{ head: ["Scan", "Date", "Candidates", "Open gaps", "Posture"], rows: scans.map((s) => [`#${s.seq}`, fmtDate(s.at), s.candidates, s.open_gaps, s.posture ?? "—"]) }}>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={scans.map((s) => ({ ...s, name: `#${s.seq}` }))} margin={{ left: 0, right: 16, top: 8, bottom: 16 }}>
              <CartesianGrid stroke="var(--border)" vertical={false} />
              <XAxis dataKey="name" stroke="var(--text-3)" fontSize={12} label={{ value: "Scan", position: "insideBottom", offset: -8, fill: "var(--text-3)", fontSize: 12 }} />
              <YAxis stroke="var(--text-3)" fontSize={12} label={{ value: "Count / score", angle: -90, position: "insideLeft", fill: "var(--text-3)", fontSize: 12 }} />
              <Tooltip contentStyle={tip} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Line type="monotone" dataKey="candidates" name="PII candidates" stroke="var(--c-contact)" strokeWidth={2.5} dot={{ r: 4 }} />
              <Line type="monotone" dataKey="open_gaps" name="Open gaps" stroke="var(--sev-high)" strokeWidth={2.5} strokeDasharray="6 4" dot={{ r: 4 }} />
              <Line type="monotone" dataKey="posture" name="Posture" stroke="var(--accent)" strokeWidth={2.5} dot={{ r: 4 }} />
            </LineChart>
          </ResponsiveContainer>
        </ChartFrame>
        <section className="card" aria-label="Drift alerts">
          <div className="card-head"><h3>PII drift alerts</h3><span className="small faint">{data.drift.length} total</span></div>
          <ul style={{ listStyle: "none", margin: 0, padding: "8px 16px 16px", display: "grid", gap: 8, maxHeight: 280, overflowY: "auto" }}>
            {data.drift.length === 0 && <li className="faint">No drift: no new personal data appeared between scans.</li>}
            {[...data.drift].reverse().map((d) => (
              <li key={d.pt_id + d.message} className="row wrap" style={{ gap: 8 }}>
                <SeverityBadge sev={d.severity} /><ClassChip cls={d.class} compact />
                <button className="btn sm ghost mono" onClick={() => openFinding(d.pt_id)}>{d.pt_id}</button>
                <span className="small">{d.message}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <section className="card" style={{ marginTop: 16 }} aria-label="Compare snapshots">
        <div className="card-head">
          <h3 className="row" style={{ gap: 8 }}><GitCompare size={16} /> Compare snapshots</h3>
          <div className="row" style={{ gap: 8 }}>
            <select className="input" style={{ width: "auto", minHeight: 34 }} value={a ?? ""} onChange={(e) => setA(Number(e.target.value))} aria-label="Compare from scan">
              {scans.map((s) => <option key={s.seq} value={s.seq}>Scan #{s.seq}</option>)}
            </select>
            <ArrowRight size={16} aria-hidden />
            <select className="input" style={{ width: "auto", minHeight: 34 }} value={b ?? ""} onChange={(e) => setB(Number(e.target.value))} aria-label="Compare to scan">
              {scans.map((s) => <option key={s.seq} value={s.seq}>Scan #{s.seq}</option>)}
            </select>
          </div>
        </div>
        <div className="card-body">
          {a === b ? <p className="faint">Pick two different scans.</p> : !diff ? <Skeleton h={160} /> : (
            <div className="stack">
              <div className="kpis">
                {[["New PII columns", diff.summary.new], ["Removed", diff.summary.removed], ["Class changes", diff.summary.class_changes], ["Confidence changes", diff.summary.confidence_changes], ["Gaps opened", diff.summary.gaps_opened], ["Gaps closed", diff.summary.gaps_closed]].map(([l, v]) => (
                  <div key={l as string} className="kpi" style={{ cursor: "default" }}><span className="label">{l}</span><span className="value num">{v}</span></div>
                ))}
              </div>
              <DiffList title="New personal-data columns" items={diff.new.map((x) => ({ pt: x.pt_id, text: `${x.table}.${x.column}`, cls: x.class, extra: x.band }))} onOpen={openFinding} />
              <DiffList title="Removed" items={diff.removed.map((x) => ({ pt: x.pt_id, text: `${x.table}.${x.column}`, cls: x.class, extra: "no longer present" }))} onOpen={openFinding} />
              <DiffList title="Class changes" items={diff.class_changes.map((x) => ({ pt: x.pt_id, text: `${x.table}.${x.column}`, cls: x.after, extra: `was ${x.before}` }))} onOpen={openFinding} />
              <DiffList title="Confidence changes" items={diff.confidence_changes.map((x) => ({ pt: x.pt_id, text: `${x.table}.${x.column}`, cls: x.class, extra: `${x.before.toFixed(2)} → ${x.after.toFixed(2)}` }))} onOpen={openFinding} />
              <DiffList title="Gaps opened" items={diff.gaps_opened.map((x) => ({ pt: x.pt_id, text: x.column, sev: x.severity, extra: `no ${x.field.replace("_", " ")}` }))} onOpen={openFinding} />
              <DiffList title="Gaps closed" items={diff.gaps_closed.map((x) => ({ pt: x.pt_id, text: x.column, sev: x.severity, extra: `${x.field.replace("_", " ")} declared` }))} onOpen={openFinding} />
            </div>
          )}
        </div>
      </section>
    </>
  );
}

function DiffList({ title, items, onOpen }: { title: string; items: { pt: string; text: string; cls?: Cls; sev?: Severity; extra: string }[]; onOpen: (pt: string) => void }) {
  const [all, setAll] = useState(false);
  if (!items.length) return null;
  const shown = all ? items : items.slice(0, 8);
  return (
    <div>
      <h4 style={{ fontSize: 14, marginBottom: 8 }}>{title} <span className="faint num">({items.length})</span></h4>
      <div className="stack-sm">
        {shown.map((it, i) => (
          <div key={it.pt + i} className="row wrap small" style={{ gap: 8 }}>
            {it.cls && <ClassChip cls={it.cls} compact />}{it.sev && <SeverityBadge sev={it.sev} />}
            <button className="btn sm ghost mono" onClick={() => onOpen(it.pt)}>{it.pt}</button>
            <code>{it.text}</code><span className="faint">{it.extra}</span>
          </div>
        ))}
      </div>
      {items.length > 8 && <button className="btn sm ghost" onClick={() => setAll(!all)}>{all ? "Show fewer" : `Show all ${items.length}`}</button>}
    </div>
  );
}
