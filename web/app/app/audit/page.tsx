"use client";

import { useVirtualizer } from "@tanstack/react-virtual";
import { CheckCircle2, Link2, ShieldCheck, XCircle } from "lucide-react";
import { useRef, useState } from "react";
import { EmptyState, ErrorCard, PageHead, Skeleton } from "@/components/ui";
import { get } from "@/lib/api";
import { fmtDate, useApi } from "@/lib/hooks";
import type { AuditEntry } from "@/lib/types";

type Verify = { ok: boolean; entries: number; broken_at: number | null; reason?: string; head?: string };

export default function AuditPage() {
  const { data, error, reload } = useApi<{ entries: AuditEntry[] }>("/api/audit");
  const [v, setV] = useState<Verify | null>(null);
  const [checking, setChecking] = useState(false);
  const [filter, setFilter] = useState("");
  const scroll = useRef<HTMLDivElement>(null);
  const entries = (data?.entries ?? []).slice().reverse().filter((e) => !filter || `${e.action} ${e.target} ${e.actor}`.toLowerCase().includes(filter.toLowerCase()));
  const virt = useVirtualizer({ count: entries.length, getScrollElement: () => scroll.current, estimateSize: () => 64, overscan: 10 });

  const verify = async () => {
    setChecking(true);
    const r = await get<Verify>("/api/audit/verify");
    await new Promise((res) => setTimeout(res, 400)); // let the check be seen
    setV(r);
    setChecking(false);
    if (!r.ok && r.broken_at) {
      const i = entries.findIndex((e) => e.seq === r.broken_at);
      if (i >= 0) virt.scrollToIndex(i, { align: "center" });
    }
  };

  if (error) return <ErrorCard message={error.message} onRetry={reload} />;
  return (
    <>
      <PageHead title="Audit log"
        desc="Every review, metadata change, rule change, scan and export is appended to a SHA-256 hash chain. Each entry includes the previous entry's hash, so any edit or deletion breaks the chain."
        actions={<button className="btn primary" onClick={verify} disabled={checking}><ShieldCheck size={16} /> {checking ? "Recomputing…" : "Verify integrity"}</button>} />
      {v && (
        <div className="card pad row wrap" role="status" style={{ marginBottom: 16, gap: 12, borderColor: v.ok ? "var(--ok)" : "var(--bad)" }}>
          {v.ok ? <CheckCircle2 size={22} color="var(--ok)" /> : <XCircle size={22} color="var(--bad)" />}
          <div>
            <b>{v.ok ? `Chain intact: all ${v.entries} entries recomputed and linked` : `Chain broken at entry #${v.broken_at}`}</b>
            <div className="small muted">{v.ok ? <>Head hash <code>{v.head?.slice(0, 24)}…</code></> : v.reason}</div>
          </div>
        </div>
      )}
      <input className="input" style={{ maxWidth: 320, marginBottom: 12 }} placeholder="Filter by action, PT-ID or person" value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filter audit entries" />
      {!data ? <Skeleton h={300} /> : !entries.length ? <EmptyState title="No audit entries yet" body="Scans, reviews and metadata changes will appear here, each chained to the one before." /> : (
        <div ref={scroll} className="card" style={{ maxHeight: "calc(100vh - 330px)", overflowY: "auto" }} role="list" aria-label="Audit entries, newest first">
          <div style={{ height: virt.getTotalSize(), position: "relative" }}>
            {virt.getVirtualItems().map((it) => {
              const e = entries[it.index];
              const broken = v && !v.ok && v.broken_at === e.seq;
              return (
                <div key={e.seq} role="listitem" className="row" style={{ position: "absolute", top: 0, left: 0, right: 0, transform: `translateY(${it.start}px)`, height: 64, padding: "0 16px", gap: 14, borderBottom: "1px solid var(--border)", background: broken ? "color-mix(in srgb, var(--bad) 14%, transparent)" : undefined }}>
                  <span className="num faint" style={{ width: 44 }}>#{e.seq}</span>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div className="row" style={{ gap: 8 }}><b className="small">{e.action}</b><code className="small">{e.target}</code>{broken && <span className="badge-bad small">broken link</span>}</div>
                    <div className="small faint" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {e.actor} · {fmtDate(e.ts, true)}{e.payload && (e.payload as { note?: string }).note ? ` · “${(e.payload as { note?: string }).note}”` : ""}
                    </div>
                  </div>
                  <span className="mono small faint hide-sm" title={`hash ${e.hash}\nprevious ${e.prev_hash}`}><Link2 size={12} style={{ verticalAlign: -2 }} /> {e.hash.slice(0, 12)}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </>
  );
}
