"use client";

import { ChevronDown, Download, Sparkles, Upload, Wand2 } from "lucide-react";
import { useRef, useState } from "react";
import { useApp } from "@/components/app-context";
import { useNav } from "@/components/shell";
import { EmptyState, ErrorCard, PageHead, Skeleton, Tip } from "@/components/ui";
import { download, post, put, upload } from "@/lib/api";
import { ClassChip, SeverityBadge } from "@/lib/classes";
import { invalidate, useApi } from "@/lib/hooks";
import type { Finding } from "@/lib/types";

type TableMeta = {
  key: string; target: string; table: string; source: string; declared: Record<string, string>; suggestion: Record<string, string>;
  suggestion_basis: string; columns: number; gaps: number;
};
type MetaOverview = { coverage: { documented: number; personal: number; pct: number }; tables: TableMeta[]; fields: { key: string; label: string }[]; max_retention_days: number };
type Prev = { previous: { target: string; values: Record<string, string> }[] };

const PLACEHOLDER: Record<string, string> = {
  purpose: "e.g. Account management", retention: "e.g. 3 years after closure", owner: "e.g. Customer operations",
  legal_basis: "Your declared basis (free text)", system_of_record: "e.g. Core banking",
};

export default function MetadataPage() {
  const app = useApp();
  const { openFinding } = useNav();
  const { data, error, reload } = useApi<MetaOverview>("/api/metadata");
  const { data: inv } = useApi<{ rows: Finding[] }>("/api/inventory");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulk, setBulk] = useState<Record<string, string>>({});
  const [open, setOpen] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const save = async (targets: string[], values: Record<string, string>, label: string) => {
    try {
      const r = await post<Prev>("/api/metadata", { targets, values });
      invalidate();
      app.markSaved();
      app.toast(label, { undo: () => post("/api/metadata/undo", { previous: r.previous }) });
    } catch (e) {
      app.toast((e as Error).message, { kind: "error" });
    }
  };

  const acceptAll = async (tables: TableMeta[]) => {
    const withSug = tables.filter((t) => Object.keys(t.suggestion).length);
    if (!withSug.length) return app.toast("No open suggestions");
    const prev: Prev["previous"] = [];
    for (const t of withSug) {
      const r = await post<Prev>("/api/metadata", { targets: [t.target], values: t.suggestion });
      prev.push(...r.previous);
    }
    invalidate();
    app.markSaved();
    app.toast(`Accepted suggestions for ${withSug.length} table(s)`, { undo: () => post("/api/metadata/undo", { previous: prev }) });
  };

  const onImport = async (f: File) => {
    try {
      const r = await upload<{ applied: number; skipped: { row: number; reason: string }[] }>("/api/metadata/import", f);
      invalidate();
      app.toast(`Imported ${r.applied} record(s)${r.skipped.length ? `; skipped ${r.skipped.length} (${r.skipped[0].reason})` : ""}`, { kind: r.skipped.length ? "info" : "ok", ms: 6000 });
    } catch (e) {
      app.toast((e as Error).message, { kind: "error" });
    }
  };

  if (error) return <ErrorCard message={error.message} onRetry={reload} />;
  if (!data) return <div className="stack"><Skeleton h={80} /><Skeleton h={240} /><Skeleton h={240} /></div>;
  const c = data.coverage;
  const personalRows = (inv?.rows ?? []).filter((r) => r.personal);

  return (
    <>
      <PageHead title="Metadata & gaps"
        ai="AI SUGGESTIONS" desc="Suggestions come from table names and are never stored until accepted; legal basis is never suggested. Declare purpose, retention, owner, legal basis and system of record for each table (or override per column). Changes save automatically."
        actions={
          <>
            <button className="btn sm" onClick={() => download("/api/metadata/template?format=csv")}><Download size={14} /> CSV template</button>
            <button className="btn sm" onClick={() => download("/api/metadata/template?format=yaml")}><Download size={14} /> YAML template</button>
            <button className="btn sm" onClick={() => fileRef.current?.click()}><Upload size={14} /> Import</button>
            <input ref={fileRef} type="file" accept=".csv,.yaml,.yml,.json" hidden onChange={(e) => e.target.files?.[0] && onImport(e.target.files[0])} />
          </>
        } />

      <section className="card pad" aria-label="Metadata coverage" style={{ marginBottom: 16 }}>
        <div className="row between wrap">
          <div>
            <b style={{ fontSize: 16 }}><span className="num">{c.documented}</span> of <span className="num">{c.personal}</span> personal-data fields fully documented (<span className="num">{c.pct}%</span>)</b> <Tip text="Fully documented = purpose, readable retention, owner and legal basis declared." />
            
          </div>
          <div className="row wrap" style={{ gap: 8 }}>
            <button className="btn sm primary" onClick={() => acceptAll(data.tables)}><Wand2 size={14} /> Accept all AI suggestions</button>
            <label className="row small" style={{ gap: 6 }}>
              Max retention
              <select className="input" style={{ width: "auto", minHeight: 32, fontSize: 13 }} value={data.max_retention_days}
                onChange={async (e) => { await put("/api/settings", { max_retention_days: Number(e.target.value) }); invalidate(); app.markSaved(); }}>
                {[1, 3, 5, 7, 10, 15].map((y) => <option key={y} value={y * 365}>{y} years</option>)}
              </select>
            </label>
          </div>
        </div>
        <div className="meter" style={{ marginTop: 12 }}><span style={{ width: `${c.pct}%` }} /></div>
      </section>

      {!data.tables.length ? (
        <EmptyState title="No personal-data tables yet" body="After a scan, every table holding personal-data candidates appears here with suggested metadata." action={<button className="btn primary" onClick={app.loadDemo}>Load demo</button>} />
      ) : (
        <>
          {selected.size > 0 && (
            <section className="card pad stack-sm" style={{ marginBottom: 12, borderColor: "var(--accent)" }} aria-label="Bulk apply">
              <b>Apply to {selected.size} selected table(s)</b>
              <div className="grid cols-3" style={{ gap: 8 }}>
                {data.fields.map((f) => (
                  <input key={f.key} className="input" placeholder={f.label} value={bulk[f.key] ?? ""} onChange={(e) => setBulk((b) => ({ ...b, [f.key]: e.target.value }))} aria-label={`Bulk ${f.label}`} />
                ))}
              </div>
              <div className="row">
                <button className="btn sm primary" onClick={async () => {
                  const values = Object.fromEntries(Object.entries(bulk).filter(([, v]) => v.trim()));
                  if (!Object.keys(values).length) return app.toast("Enter at least one value");
                  await save([...selected], values, `Applied to ${selected.size} table(s)`);
                  setBulk({}); setSelected(new Set());
                }}>Apply</button>
                <button className="btn sm ghost" onClick={() => setSelected(new Set())}>Cancel</button>
              </div>
            </section>
          )}

          <div className="stack">
            {data.tables.map((t) => {
              const cols = personalRows.filter((r) => `${r.source_id}/${r.table}` === t.key);
              const sugCount = Object.keys(t.suggestion).length;
              return (
                <section key={t.key} className="card" aria-label={`Table ${t.table}`}>
                  <div className="card-head">
                    <div className="row" style={{ gap: 10 }}>
                      <input type="checkbox" aria-label={`Select ${t.table} for bulk apply`} checked={selected.has(t.target)}
                        onChange={(e) => setSelected((s) => { const n = new Set(s); e.target.checked ? n.add(t.target) : n.delete(t.target); return n; })} />
                      <div>
                        <h3 className="mono" style={{ fontSize: 15 }}>{t.table}</h3>
                        <span className="small faint">{t.source} · {t.columns} personal fields · {t.gaps} open gaps</span>
                      </div>
                    </div>
                    {sugCount > 0 && (
                      <button className="suggest" onClick={() => save([t.target], t.suggestion, `Accepted ${sugCount} suggestion(s) for ${t.table}`)} title={t.suggestion_basis}>
                        <Sparkles size={13} /> Accept {sugCount} AI suggestion{sugCount > 1 ? "s" : ""}
                      </button>
                    )}
                  </div>
                  <div className="card-body grid cols-3" style={{ gap: 12 }}>
                    {data.fields.map((f) => {
                      const declared = t.declared[f.key];
                      const sug = t.suggestion[f.key];
                      return (
                        <label key={f.key} className="field">
                          <span className="row between">{f.label}{!declared && f.key !== "system_of_record" && <span className="small" style={{ color: f.key === "purpose" || f.key === "retention" ? "var(--sev-high)" : "var(--sev-medium)" }}>missing</span>}</span>
                          <input className="input" defaultValue={declared} key={`${t.target}-${f.key}-${declared}`} placeholder={PLACEHOLDER[f.key]}
                            onBlur={(e) => e.target.value.trim() !== (declared ?? "") && save([t.target], { [f.key]: e.target.value.trim() }, `${f.label} saved for ${t.table}`)} />
                          {sug && (
                            <button type="button" className="suggest" onClick={() => save([t.target], { [f.key]: sug }, `${f.label} declared for ${t.table}`)} title={t.suggestion_basis}>
                              <Sparkles size={12} /> AI: “{sug}”
                            </button>
                          )}
                        </label>
                      );
                    })}
                  </div>
                  <button className="btn ghost sm" style={{ margin: "0 12px 12px" }} aria-expanded={open === t.key} onClick={() => setOpen(open === t.key ? null : t.key)}>
                    <ChevronDown size={14} style={{ transform: open === t.key ? "rotate(180deg)" : undefined, transition: "transform 160ms" }} /> Columns and per-column gaps
                  </button>
                  {open === t.key && (
                    <table className="table" style={{ marginBottom: 8 }}>
                      <thead><tr><th>Column</th><th>Class</th><th>Gaps</th><th>Column override: retention</th></tr></thead>
                      <tbody>
                        {cols.map((r) => (
                          <tr key={r.key}>
                            <td><button className="btn sm ghost mono" onClick={() => openFinding(r.pt_id)}>{r.column}</button></td>
                            <td><ClassChip cls={r.class} compact /></td>
                            <td><div className="row wrap" style={{ gap: 8 }}>{r.gaps.length ? r.gaps.map((g) => <span key={g.message} title={g.message} className="row small" style={{ gap: 4 }}><SeverityBadge sev={g.severity} />{g.field.replace("_", " ")}</span>) : <span className="badge-ok small">Documented</span>}</div></td>
                            <td style={{ width: 220 }}>
                              <input className="inline-edit" defaultValue={r.meta.retention.origin === "column" ? r.meta.retention.value : ""} placeholder={r.meta.retention.value ? `inherits: ${r.meta.retention.value}` : "not declared"}
                                aria-label={`Retention override for ${r.column}`} key={`${r.key}-${r.meta.retention.value}`}
                                onBlur={(e) => e.target.value.trim() !== (r.meta.retention.origin === "column" ? r.meta.retention.value : "") && save([`col:${r.key}`], { retention: e.target.value.trim() }, `Retention override saved for ${r.column}`)} />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </section>
              );
            })}
          </div>
        </>
      )}
    </>
  );
}
