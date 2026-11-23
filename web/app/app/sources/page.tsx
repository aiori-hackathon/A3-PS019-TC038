"use client";

import { ChevronDown, Database, EyeOff, FileSpreadsheet, HardDrive, Lock, Play, Receipt, Server, ShieldCheck, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { useApp } from "@/components/app-context";
import { AutoTriage } from "@/components/auto-triage";
import { EmptyState, ErrorCard, PageHead, Skeleton, Tip } from "@/components/ui";
import { download } from "@/lib/api";
import { ago, fmtDate, useApi } from "@/lib/hooks";

type Source = {
  id: string; name: string; kind: string; origin: string; detail: Record<string, unknown>; read_only_verified: boolean; read_only_detail: string;
  created_at: string; scans: number; last_scan: { seq: number; created_at: string; ruleset_version: string; stats: { columns: number; personal: number; tables: number } } | null;
  receipt: Record<string, unknown> & { tables: { table: string; rows_sampled: number; total_rows: number }[]; fields_persisted: string[] } | null;
};

export default function SourcesPage() {
  const app = useApp();
  const { data, error, reload } = useApi<{ sources: Source[] }>("/api/sources");
  const [over, setOver] = useState(false);
  const [opts, setOpts] = useState(false);
  const [pg, setPg] = useState({ dsn: "", name: "PostgreSQL" });
  const [receipt, setReceipt] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const maskRef = useRef<HTMLInputElement>(null);
  const [maskStrategy, setMaskStrategy] = useState("partial");

  const onFiles = (files: FileList | null) => {
    const f = files?.[0];
    if (f) app.startScan(f);
  };
  const masked = async (f: File) => {
    const fd = new FormData();
    fd.append("file", f, f.name);
    fd.append("strategy", maskStrategy);
    try {
      await download("/api/mask/csv", "POST", fd);
      app.toast("Masked copy downloaded. It was generated in memory and not stored.", { kind: "ok" });
    } catch (e) {
      app.toast((e as Error).message, { kind: "error" });
    }
  };

  return (
    <>
      <PageHead title="Sources" desc="Add a source and the first findings appear while it scans. Sources are opened read-only; values are sampled in memory and discarded." />
      <AutoTriage />

      <div className="grid" style={{ gridTemplateColumns: "minmax(0, 1.4fr) minmax(0, 1fr)", alignItems: "start" }}>
        <div className="stack">
          <div data-own-drop className={`dropzone ${over ? "over" : ""}`}
            onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
            onDrop={(e) => { e.preventDefault(); setOver(false); onFiles(e.dataTransfer.files); }}>
            <Upload size={32} color="var(--accent)" aria-hidden />
            <h3>Drop a CSV or SQLite file</h3>
            
            <div className="row wrap" style={{ justifyContent: "center" }}>
              <button className="btn primary" onClick={() => fileRef.current?.click()}><Upload size={15} /> Choose file</button>
              <button className="btn" onClick={app.loadDemo} disabled={app.demoLoading}><Play size={15} /> Load demo company</button>
            </div>
            <input ref={fileRef} type="file" hidden accept=".csv,.tsv,.txt,.db,.sqlite,.sqlite3" onChange={(e) => onFiles(e.target.files)} aria-label="Choose a CSV or SQLite file" />
            <button className="btn sm ghost" onClick={() => setOpts((v) => !v)} aria-expanded={opts}>
              Scan options: {app.scanOptions.sample_size.toLocaleString()} rows, {app.scanOptions.strategy} <ChevronDown size={14} style={{ transform: opts ? "rotate(180deg)" : undefined }} />
            </button>
            {opts && (
              <div className="row wrap" style={{ justifyContent: "center", gap: 12 }}>
                <label className="field" style={{ minWidth: 160 }}>Rows sampled per table
                  <select className="input" value={app.scanOptions.sample_size} onChange={(e) => app.setScanOptions({ ...app.scanOptions, sample_size: Number(e.target.value) })}>
                    {[500, 1000, 5000].map((n) => <option key={n} value={n}>{n.toLocaleString()}</option>)}
                  </select>
                </label>
                <label className="field" style={{ minWidth: 180 }}>Sampling strategy
                  <select className="input" value={app.scanOptions.strategy} onChange={(e) => app.setScanOptions({ ...app.scanOptions, strategy: e.target.value })}>
                    <option value="random">Random (default)</option>
                    <option value="head">First rows (head)</option>
                    <option value="stratified">Stratified (spread across the file)</option>
                  </select>
                </label>
              </div>
            )}
          </div>

          <div className="grid cols-2">
            <SourceCard icon={<FileSpreadsheet />} title="CSV" body="Up to 20 MB. UTF-8 with fallbacks (UTF-8 BOM, Windows-1252, Latin-1). Delimiter auto-detected; duplicate headers renamed." />
            <SourceCard icon={<HardDrive />} title="SQLite" body="Up to 50 MB (.db, .sqlite, .sqlite3). Opened with mode=ro; a write probe must be refused before scanning." />
            <section className="card pad stack-sm" aria-label="PostgreSQL">
              <div className="row" style={{ gap: 8 }}><Server size={18} color="var(--accent)" /><b>PostgreSQL</b><Tip text="Use a read-only user. Runs in a read-only transaction; the password is never stored." /></div>
              
              <input className="input mono" placeholder="postgresql://readonly@host:5432/db" value={pg.dsn} onChange={(e) => setPg({ ...pg, dsn: e.target.value })} aria-label="Connection string" autoComplete="off" />
              <div className="row">
                <input className="input" style={{ flex: 1 }} value={pg.name} onChange={(e) => setPg({ ...pg, name: e.target.value })} aria-label="Source name" />
                <button className="btn" disabled={!pg.dsn} onClick={() => app.startPostgres(pg.dsn, pg.name)}><Database size={15} /> Scan</button>
              </div>
            </section>
            <section className="card pad stack-sm" aria-label="Not supported in this build" style={{ opacity: 0.75 }}>
              <div className="row" style={{ gap: 8 }}><Lock size={18} className="faint" /><b>MySQL · SQL Server</b></div>
              <p className="small muted">Not supported in this build: use a CSV export.</p>
              <div className="row" style={{ gap: 8 }}>
                <button className="btn sm" disabled>MySQL</button>
                <button className="btn sm" disabled>SQL Server</button>
              </div>
            </section>
          </div>
        </div>

        <aside className="stack">
          <section className="card pad stack-sm" aria-label="Ingestion limits">
            <b className="row" style={{ gap: 8 }}><ShieldCheck size={16} color="var(--ok)" /> How your data is handled</b>
            <ul className="small muted" style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 4 }}>
              <li>Bounded sample per table: 500, 1,000 (default) or 5,000 rows.</li>
              <li>Processed in memory; raw values are discarded when the scan ends.</li>
              <li>Stored: counts, ratios, rule IDs, masked examples, keyed fingerprints.</li>
              <li>SQLite uploads use a private temporary copy, deleted immediately.</li>
              <li>Every scan writes a data-handling receipt (below).</li>
            </ul>
          </section>
          <section className="card pad stack-sm" aria-label="Masked copy">
            <b className="row" style={{ gap: 8 }}><EyeOff size={16} color="var(--accent)" /> Masked copy of a CSV <Tip text="AI detects personal-data columns and masks them in memory; the file is streamed back and nothing is stored." /></b>
            
            <div className="row">
              <select className="input" value={maskStrategy} onChange={(e) => setMaskStrategy(e.target.value)} aria-label="Masking strategy" style={{ width: "auto" }}>
                <option value="partial">Partial mask</option><option value="hash">Keyed hash</option><option value="tokenise">Tokenise</option><option value="redact">Redact</option>
              </select>
              <button className="btn" data-own-drop onClick={() => maskRef.current?.click()}><Upload size={15} /> Choose CSV</button>
              <input ref={maskRef} type="file" hidden accept=".csv,.tsv,.txt" onChange={(e) => e.target.files?.[0] && masked(e.target.files[0])} aria-label="CSV to mask" />
            </div>
          </section>
        </aside>
      </div>

      <h2 style={{ fontSize: 18, margin: "28px 0 12px" }}>Scanned sources</h2>
      {error && <ErrorCard message={error.message} onRetry={reload} />}
      {!data && !error && <Skeleton h={120} />}
      {data && !data.sources.length && <EmptyState title="No sources yet" body="Drop a file above or load the demo company. Rescanning the same file name creates a new snapshot for the Time Machine." />}
      <div className="stack">
        {data?.sources.map((s) => (
          <section key={s.id} className="card" aria-label={s.name}>
            <div className="card-head">
              <div className="row" style={{ gap: 12 }}>
                <span className="kpi" style={{ padding: 8, cursor: "default" }} aria-hidden>{s.kind === "CSV" ? <FileSpreadsheet size={18} /> : s.kind === "PostgreSQL" ? <Server size={18} /> : <HardDrive size={18} />}</span>
                <div>
                  <h3 style={{ fontSize: 15 }}>{s.name}</h3>
                  <span className="small faint">{s.kind} · {s.origin === "demo" ? "synthetic demo" : s.origin} · {s.scans} scan{s.scans === 1 ? "" : "s"}{s.last_scan ? ` · last ${ago(s.last_scan.created_at)}` : ""}</span>
                </div>
              </div>
              <div className="row wrap" style={{ gap: 8 }}>
                {s.read_only_verified ? <span className="badge-ok" title={s.read_only_detail}><ShieldCheck size={15} /> Read-only verified</span> : <span className="badge-bad">Not verified</span>}
                <button className="btn sm" onClick={() => setReceipt(receipt === s.id ? null : s.id)} aria-expanded={receipt === s.id}><Receipt size={14} /> Data-handling receipt</button>
              </div>
            </div>
            {s.last_scan && (
              <div className="card-body row wrap small" style={{ gap: 20 }}>
                <span><b className="num">{s.last_scan.stats.tables}</b> tables</span>
                <span><b className="num">{s.last_scan.stats.columns}</b> columns</span>
                <span><b className="num">{s.last_scan.stats.personal}</b> personal-data candidates</span>
                <span className="faint">Scan #{s.last_scan.seq} · rules v{s.last_scan.ruleset_version} · {fmtDate(s.last_scan.created_at, true)}</span>
              </div>
            )}
            {receipt === s.id && s.receipt && (
              <div className="card-body" style={{ borderTop: "1px solid var(--border)" }}>
                <div className="grid cols-2 small">
                  <div className="stack-sm">
                    <div><b>Strategy:</b> {String(s.receipt.strategy)} · up to {String(s.receipt.sample_size_requested)} rows per table</div>
                    <div><b>Processed in memory:</b> yes{s.receipt.transient_copy ? " (temporary copy deleted at " + fmtDate(String(s.receipt.transient_copy_deleted_at), true) + ")" : ""}</div>
                    <div><b>Raw values discarded at:</b> {fmtDate(String(s.receipt.raw_values_discarded_at), true)}</div>
                    <div><b>Raw values persisted:</b> no</div>
                    <div><b>Read-only check:</b> {String(s.receipt.read_only_detail)}</div>
                    {s.receipt.encoding ? <div><b>Encoding:</b> {String(s.receipt.encoding)} · delimiter “{String(s.receipt.delimiter) === "\t" ? "tab" : String(s.receipt.delimiter)}”</div> : null}
                    {(s.receipt.notes as string[] | undefined)?.map((n) => <div key={n} className="faint">Note: {n}</div>)}
                  </div>
                  <div className="stack-sm">
                    <b>Rows sampled</b>
                    {s.receipt.tables.map((t) => <div key={t.table} className="row between"><code>{t.table}</code><span className="num">{t.rows_sampled.toLocaleString()} of {t.total_rows.toLocaleString()}</span></div>)}
                    <b style={{ marginTop: 8 }}>Fields persisted</b>
                    <div className="faint">{s.receipt.fields_persisted.join(" · ")}</div>
                  </div>
                </div>
              </div>
            )}
          </section>
        ))}
      </div>
      <style>{`@media (max-width: 960px){ .content .grid[style*="1.4fr"]{grid-template-columns:minmax(0,1fr) !important} }`}</style>
    </>
  );
}

function SourceCard({ icon, title, body }: { icon: React.ReactNode; title: string; body: string }) {
  return (
    <section className="card pad stack-sm" aria-label={title}>
      <div className="row" style={{ gap: 8, color: "var(--accent)" }}>{icon}<b style={{ color: "var(--text)" }}>{title}</b><span className="badge-ok small" style={{ marginLeft: "auto" }}>Supported</span></div>
      <Tip text={body} />
    </section>
  );
}
