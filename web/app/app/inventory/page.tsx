"use client";

import { useVirtualizer } from "@tanstack/react-virtual";
import { Bookmark, Columns3, Download, Search, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useApp } from "@/components/app-context";
import { useNav } from "@/components/shell";
import { EmptyState, ErrorCard, PageHead, Skeleton } from "@/components/ui";
import { saveBlob, storage } from "@/lib/api";
import { ALL_CLASSES, BandLabel, CLASS_META, ClassChip, SeverityBadge, StatusLabel } from "@/lib/classes";
import { useApi, useDebounced } from "@/lib/hooks";
import type { Finding } from "@/lib/types";

type Col = { key: string; label: string; width: string; render: (r: Finding) => React.ReactNode; text: (r: Finding) => string };
const COLUMNS: Col[] = [
  { key: "pt_id", label: "ID", width: "96px", render: (r) => <span className="tag">{r.pt_id}</span>, text: (r) => r.pt_id },
  { key: "column", label: "Column", width: "minmax(180px, 1.6fr)", render: (r) => <code title={`${r.table}.${r.column}`}><span className="faint">{r.table}.</span>{r.column}</code>, text: (r) => `${r.table}.${r.column}` },
  { key: "class", label: "Class", width: "150px", render: (r) => <ClassChip cls={r.class} />, text: (r) => r.class },
  { key: "confidence", label: "Confidence", width: "120px", render: (r) => <BandLabel band={r.band} score={r.confidence} />, text: (r) => r.confidence.toFixed(2) },
  { key: "status", label: "Status", width: "112px", render: (r) => <span className="stack-sm"><StatusLabel status={r.status} />{r.decision_source === "ai" && <span className="small" style={{ color: "var(--accent)" }}>AI approved</span>}</span>, text: (r) => r.decision_source === "ai" ? `${r.status} (AI)` : r.status },
  { key: "gap", label: "Top gap", width: "100px", render: (r) => (r.max_gap ? <SeverityBadge sev={r.max_gap} /> : <span className="faint">—</span>), text: (r) => r.max_gap ?? "" },
  { key: "example", label: "Masked example", width: "minmax(140px, 1fr)", render: (r) => <span className="mono small faint">{r.masked_examples[0] ?? ""}</span>, text: (r) => r.masked_examples.join(" | ") },
  { key: "source", label: "Source", width: "minmax(120px, 0.9fr)", render: (r) => <span className="small muted">{r.source}</span>, text: (r) => r.source },
  { key: "rule", label: "Rule", width: "130px", render: (r) => <span className="mono small faint">{r.rule_id ?? "—"}</span>, text: (r) => r.rule_id ?? "" },
  { key: "risk", label: "Risk", width: "70px", render: (r) => <span className="num">{r.risk || "—"}</span>, text: (r) => String(r.risk) },
  { key: "purpose", label: "Purpose", width: "minmax(120px, 1fr)", render: (r) => <span className="small">{r.meta.purpose.value || <span className="faint">—</span>}</span>, text: (r) => r.meta.purpose.value },
];
const DEFAULT_COLS = ["pt_id", "column", "class", "confidence", "status", "gap", "example", "source"];
const FILTERS = ["class", "band", "status", "gap", "source", "personal", "q"] as const;

export default function InventoryPage() {
  const app = useApp();
  const { params, router, pathname, openFinding } = useNav();
  const scan = params.get("scan");
  const { data, error, reload } = useApi<{ rows: Finding[] }>(`/api/inventory${scan ? `?scan=${scan}` : ""}`);
  const [q, setQ] = useState(params.get("q") ?? "");
  const dq = useDebounced(q, 200);
  const [cols, setCols] = useState<string[]>(DEFAULT_COLS);
  const [chooser, setChooser] = useState(false);
  const [views, setViews] = useState<{ name: string; query: string }[]>([]);
  const filters = Object.fromEntries(FILTERS.map((f) => [f, params.get(f) ?? ""])) as Record<(typeof FILTERS)[number], string>;

  useEffect(() => {
    try {
      setCols(JSON.parse(storage.get("pt.invCols") || "null") ?? DEFAULT_COLS);
      setViews(JSON.parse(storage.get("pt.views") || "[]"));
    } catch {
      /* ignore */
    }
  }, []);

  const setFilter = (k: string, v: string) => {
    const p = new URLSearchParams(params.toString());
    if (v) p.set(k, v);
    else p.delete(k);
    router.replace(`${pathname}?${p.toString()}`, { scroll: false });
  };
  useEffect(() => {
    if (dq !== (params.get("q") ?? "")) setFilter("q", dq);
  }, [dq]); // eslint-disable-line react-hooks/exhaustive-deps

  const rows = useMemo(() => {
    const all = data?.rows ?? [];
    const needle = (params.get("q") ?? "").toLowerCase();
    return all.filter((r) =>
      (!filters.class || r.class === filters.class) &&
      (!filters.band || r.band === filters.band) &&
      (!filters.status || r.status === filters.status) &&
      (!filters.gap || r.max_gap === filters.gap) &&
      (!filters.source || r.source === filters.source) &&
      (!filters.personal || r.detected_class !== "NOT_PERSONAL") &&
      (!needle || `${r.pt_id} ${r.table}.${r.column} ${r.class} ${r.rule_id ?? ""} ${r.source} ${r.meta.purpose.value}`.toLowerCase().includes(needle)),
    );
  }, [data, params]); // eslint-disable-line react-hooks/exhaustive-deps

  const shown = COLUMNS.filter((c) => cols.includes(c.key));
  const template = shown.map((c) => c.width).join(" ");
  const scrollRef = useRef<HTMLDivElement>(null);
  const virt = useVirtualizer({ count: rows.length, getScrollElement: () => scrollRef.current, estimateSize: () => 52, overscan: 12 });
  const sources = Array.from(new Set((data?.rows ?? []).map((r) => r.source)));
  const active = FILTERS.filter((f) => filters[f]).length;

  const exportView = (fmt: "csv" | "json") => {
    const stamp = new Date().toISOString().slice(0, 10);
    if (fmt === "json") {
      saveBlob(new Blob([JSON.stringify(rows.map(({ meta, ...r }) => ({ ...r, meta })), null, 1)], { type: "application/json" }), `privacytwin-inventory-${stamp}.json`);
    } else {
      const head = ["pt_id", "source", "table", "column", "class", "confidence", "band", "status", "rule_id", "masked_examples", "purpose", "retention", "owner", "gaps"];
      const esc = (v: string) => { const s = /^[=+\-@]/.test(v) ? `'${v}` : v; return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
      const lines = rows.map((r) => [r.pt_id, r.source, r.table, r.column, r.class, r.confidence.toFixed(2), r.band, r.status, r.rule_id ?? "", r.masked_examples.join(" | "), r.meta.purpose.value, r.meta.retention.value, r.meta.owner.value, r.gaps.map((g) => `${g.severity}: ${g.message}`).join("; ")].map((v) => esc(String(v))).join(","));
      saveBlob(new Blob([[head.join(","), ...lines, "", "# Technical evidence for human review. Not a legal determination."].join("\n")], { type: "text/csv" }), `privacytwin-inventory-${stamp}.csv`);
    }
    app.toast(`Exported ${rows.length} rows (masked values only)`);
  };

  const saveView = () => {
    const parts = FILTERS.filter((f) => filters[f]).map((f) => (f === "class" ? CLASS_META[filters.class as keyof typeof CLASS_META]?.label : f === "personal" ? "Personal only" : `${f}: ${filters[f]}`));
    const name = parts.join(" · ") || "All columns";
    const next = [...views.filter((v) => v.name !== name), { name, query: params.toString() }];
    setViews(next);
    storage.set("pt.views", JSON.stringify(next));
    app.toast(`Saved view “${name}”. Share the URL to share the filters.`);
  };

  if (error) return <ErrorCard message={error.message} onRetry={reload} />;
  return (
    <>
      <PageHead title="Inventory" ai="AI DETECTION" desc="Every scanned column with its candidate class, signals and gaps. Click a row for the evidence card." />
      <div className="toolbar">
        <label className="row" style={{ position: "relative", flex: "1 1 260px", maxWidth: 380 }}>
          <Search size={15} style={{ position: "absolute", left: 12 }} className="faint" aria-hidden />
          <input className="input" style={{ paddingLeft: 34 }} placeholder="Search columns, tables, PT-IDs, rules…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search inventory" />
        </label>
        <Select label="Class" value={filters.class} onChange={(v) => setFilter("class", v)} options={ALL_CLASSES.map((c) => [c, CLASS_META[c].label])} />
        <Select label="Confidence" value={filters.band} onChange={(v) => setFilter("band", v)} options={[["HIGH", "High"], ["MEDIUM", "Medium"], ["LOW", "Low"], ["NONE", "None"]]} />
        <Select label="Status" value={filters.status} onChange={(v) => setFilter("status", v)} options={[["candidate", "Candidate"], ["confirmed", "Confirmed"], ["rejected", "Rejected"], ["needs_info", "Needs info"]]} />
        <Select label="Gap" value={filters.gap} onChange={(v) => setFilter("gap", v)} options={[["High", "High"], ["Medium", "Medium"], ["Low", "Low"]]} />
        {sources.length > 1 && <Select label="Source" value={filters.source} onChange={(v) => setFilter("source", v)} options={sources.map((s) => [s, s])} />}
        {active > 0 && <button className="btn sm ghost" onClick={() => { setQ(""); router.replace(pathname); }}><X size={14} /> Clear {active}</button>}
        <div style={{ flex: 1 }} />
        <button className="btn sm" onClick={saveView}><Bookmark size={14} /> Save view</button>
        <div style={{ position: "relative" }}>
          <button className="btn sm" onClick={() => setChooser((v) => !v)} aria-expanded={chooser}><Columns3 size={14} /> Columns</button>
          {chooser && (
            <div className="card pad stack-sm" style={{ position: "absolute", right: 0, top: 40, zIndex: 10, width: 200 }}>
              {COLUMNS.map((c) => (
                <label key={c.key} className="row small" style={{ gap: 8 }}>
                  <input type="checkbox" checked={cols.includes(c.key)} disabled={c.key === "column"} onChange={(e) => {
                    const next = e.target.checked ? COLUMNS.map((x) => x.key).filter((k) => k === c.key || cols.includes(k)) : cols.filter((k) => k !== c.key);
                    setCols(next);
                    storage.set("pt.invCols", JSON.stringify(next));
                  }} /> {c.label}
                </label>
              ))}
            </div>
          )}
        </div>
        <button className="btn sm" onClick={() => exportView("csv")}><Download size={14} /> CSV</button>
        <button className="btn sm" onClick={() => exportView("json")}><Download size={14} /> JSON</button>
      </div>
      {views.length > 0 && (
        <div className="row wrap small" style={{ gap: 6, marginBottom: 12 }}>
          <span className="faint">Saved views:</span>
          {views.map((v) => (
            <span key={v.name} className="row" style={{ gap: 2 }}>
              <button className="suggest" onClick={() => router.replace(`${pathname}?${v.query}`)}>{v.name}</button>
              <button className="btn sm icon ghost" aria-label={`Delete view ${v.name}`} onClick={() => { const next = views.filter((x) => x.name !== v.name); setViews(next); storage.set("pt.views", JSON.stringify(next)); }}><X size={12} /></button>
            </span>
          ))}
        </div>
      )}
      <p className="small faint" style={{ marginBottom: 8 }} aria-live="polite">{data ? `${rows.length.toLocaleString()} of ${data.rows.length.toLocaleString()} columns` : "Loading…"}</p>

      {!data ? (
        <div className="stack-sm">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} h={44} />)}</div>
      ) : data.rows.length === 0 ? (
        <EmptyState title="No columns yet" body="Scan a file or load the demo company. Findings appear here as soon as the first table is read." action={<button className="btn primary" onClick={app.loadDemo}>Load demo</button>} />
      ) : (
        <>
          <div className="vt vt-desktop" role="table" aria-label="Inventory" aria-rowcount={rows.length}>
            <div ref={scrollRef} className="vt-scroll">
              <div className="vt-head" role="row" style={{ gridTemplateColumns: template, minWidth: 900 }}>
                {shown.map((c) => <div key={c.key} role="columnheader">{c.label}</div>)}
              </div>
              <div style={{ height: virt.getTotalSize(), position: "relative", minWidth: 900 }}>
                {virt.getVirtualItems().map((v) => {
                  const r = rows[v.index];
                  return (
                    <div key={r.key} role="row" tabIndex={0} aria-rowindex={v.index + 2} className="vt-row"
                      style={{ position: "absolute", top: 0, left: 0, right: 0, transform: `translateY(${v.start}px)`, gridTemplateColumns: template, opacity: r.status === "rejected" ? 0.6 : 1 }}
                      onClick={() => openFinding(r.pt_id)} onKeyDown={(e) => e.key === "Enter" && openFinding(r.pt_id)}>
                      {shown.map((c) => <div key={c.key} role="cell">{c.render(r)}</div>)}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
          <div className="cards-sm">
            {rows.slice(0, 200).map((r) => (
              <button key={r.key} className="mini-card" onClick={() => openFinding(r.pt_id)} style={{ textAlign: "left", color: "var(--text)", fontFamily: "var(--font)" }}>
                <div className="row between"><span className="tag">{r.pt_id}</span><ClassChip cls={r.class} compact /></div>
                <code>{r.table}.{r.column}</code>
                <div className="row between small"><StatusLabel status={r.status} /><BandLabel band={r.band} score={r.confidence} /></div>
              </button>
            ))}
          </div>
        </>
      )}
    </>
  );
}

function Select({ label, value, onChange, options }: { label: string; value: string; onChange: (v: string) => void; options: [string, string][] }) {
  return (
    <select className="input" aria-label={label} value={value} onChange={(e) => onChange(e.target.value)} style={{ width: "auto", minHeight: 36, padding: "4px 10px", fontSize: 13, borderColor: value ? "var(--accent)" : undefined }}>
      <option value="">{label}: all</option>
      {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
    </select>
  );
}
