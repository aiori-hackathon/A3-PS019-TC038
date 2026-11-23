"use client";

import { useEffect, useState } from "react";
import { useApp } from "./app-context";
import { post } from "@/lib/api";
import { invalidate, useApi } from "@/lib/hooks";

type Policy = {
  enabled: boolean; threshold: number; last_batch: string | null; undoable: number; limit: number;
  llm: { enabled: boolean; provider: string | null; model: string | null };
};
type Result = { approved: number; eligible: number; remaining: number; status: string; batch_id: string | null };

const MIN_PCT = 90;
const MAX_PCT = 100;

/** Minimum detection confidence as a typed percentage (90-100, decimals allowed). Saves on Enter or blur. */
function ThresholdInput({ value, disabled, onSave }: { value: number; disabled: boolean; onSave: (threshold: number) => void }) {
  const saved = String(Math.round(value * 1000) / 10);
  const [text, setText] = useState(saved);
  const [error, setError] = useState("");
  useEffect(() => { setText(saved); setError(""); }, [saved]);

  const commit = () => {
    const t = text.trim().replace(/%$/, "").trim();
    if (t === saved) return setError("");
    if (!/^\d{1,3}(\.\d{1,2})?$/.test(t)) return setError("Enter a number, e.g. 95 or 92.5");
    const pct = Number(t);
    if (pct < MIN_PCT || pct > MAX_PCT) return setError(`Must be between ${MIN_PCT} and ${MAX_PCT}%`);
    setError("");
    onSave(Math.round(pct * 100) / 10000);
  };

  return (
    <label className="row small" style={{ gap: 8 }}>
      Minimum detection confidence
      <span className="row" style={{ gap: 4 }}>
        <input className="input num" type="text" inputMode="decimal" aria-label="Auto-approval minimum confidence (percent)"
          aria-invalid={!!error} aria-describedby={error ? "triage-threshold-error" : undefined}
          style={{ width: 72, minHeight: 34, textAlign: "right", borderColor: error ? "var(--bad)" : undefined }}
          value={text} maxLength={6} disabled={disabled}
          onChange={(e) => { setText(e.target.value); setError(""); }}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === "Enter") { e.preventDefault(); commit(); }
            if (e.key === "Escape") { setText(saved); setError(""); }
          }} />
        %
      </span>
      {error && <span id="triage-threshold-error" role="alert" style={{ color: "var(--bad)" }}>{error}</span>}
    </label>
  );
}

export function AutoTriage() {
  const app = useApp();
  const { data, error, reload, setData } = useApi<Policy>("/api/auto-triage");
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [undoing, setUndoing] = useState(false);
  const [message, setMessage] = useState("");

  async function undo(batch: string) {
    setUndoing(true);
    try {
      const r = await post<{ restored: number }>("/api/auto-triage/undo", { batch_id: batch });
      setMessage(`${r.restored} AI approvals undone. These candidates now stay in manual review.`);
      invalidate();
    } catch (e) { app.toast((e as Error).message, { kind: "error" }); }
    finally { setUndoing(false); }
  }

  async function run() {
    setRunning(true);
    setMessage("AI is reviewing eligible candidates. You can switch automation off while it runs.");
    try {
      const r = await post<Result>("/api/auto-triage/run", {});
      setMessage(r.status === "unavailable"
        ? `${r.approved} approved. AI was unavailable or returned an invalid response; remaining candidates need review.`
        : r.status === "disabled" || r.status === "stopped"
          ? `${r.approved} approved before automation stopped.`
          : `${r.approved} of ${r.eligible} eligible candidates approved. ${r.remaining ? `${r.remaining} beyond this run; select Run now to continue.` : "Other candidates remain for manual review."}`);
      invalidate();
      if (r.batch_id) {
        const batch = r.batch_id;
        app.toast(`${r.approved} candidates auto-approved by AI`, { undo: () => undo(batch) });
      }
    } catch (e) {
      setMessage("Auto-triage did not finish. Refresh to check recorded decisions before retrying.");
      app.toast((e as Error).message, { kind: "error" });
      invalidate();
    } finally { setRunning(false); }
  }

  async function configure(enabled: boolean, threshold: number) {
    setSaving(true);
    let runExisting = false;
    try {
      const policy = await post<Policy>("/api/auto-triage/settings", { enabled, threshold });
      setData(policy);
      invalidate();
      setMessage(enabled ? "Enabled for future scans." : "Automation off. Existing decisions are unchanged.");
      runExisting = enabled && !data?.enabled;
    } catch (e) { app.toast((e as Error).message, { kind: "error" }); }
    finally { setSaving(false); }
    if (runExisting) await run();
  }

  return (
    <section className="card pad stack-sm" aria-label="AI auto-triage" style={{ marginBottom: 16 }}>
      <div className="row between wrap" style={{ gap: 12 }}>
        <div><b>AI auto-triage</b><p className="small muted" style={{ marginTop: 4 }}>Let AI approve high-confidence candidates automatically. Off by default.</p></div>
        {data && <label className="row" style={{ gap: 8 }}>
          <input type="checkbox" role="switch" aria-label="Enable AI auto-approval" checked={data.enabled}
            disabled={saving} onChange={(e) => configure(e.target.checked, data.threshold)} />
          {data.enabled ? "Auto-approve on" : "Auto-approve off"}
        </label>}
      </div>
      {error && <div role="alert" className="small">Could not load automation settings. <button className="btn sm" onClick={reload}>Retry</button></div>}
      {!data && !error && <span className="small muted">Loading automation settings...</span>}
      {data && <>
        <div className="row wrap" style={{ gap: 12 }}>
          <ThresholdInput value={data.threshold} disabled={saving || running} onSave={(t) => configure(data.enabled, t)} />
          <button className="btn sm primary" disabled={!data.enabled || !data.llm.enabled || running || saving} onClick={run}>{running ? "AI reviewing..." : "Run now"}</button>
          <button className="btn sm" disabled={!data.last_batch || !data.undoable || undoing} onClick={() => data.last_batch && undo(data.last_batch)}>Undo latest AI batch{data.undoable ? ` (${data.undoable})` : ""}</button>
        </div>
        <p className="small muted">{data.llm.enabled ? `${data.llm.provider} · ${data.llm.model}` : "Configure Groq or another supported AI provider to make automatic decisions. No offline approvals."} Only untouched HIGH-confidence personal-data candidates qualify. Each needs an explicit AI approval; other candidates stay for manual review.</p>
        <p className="small faint">Enabling reviews existing candidates, then runs after every scan (up to {data.limit} per run). Decisions and reasons are audited and excluded from human-confirmed precision. Human decisions and metadata declarations are preserved.</p>
      </>}
      {message && <p className="small" role="status">{message}</p>}
    </section>
  );
}
