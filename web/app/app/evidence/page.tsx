"use client";

import { CheckCircle2, Download, FileArchive, FileCheck2, Import, Trash2, Upload, XCircle } from "lucide-react";
import { useRef, useState } from "react";
import { useApp } from "@/components/app-context";
import { Loader3D, PageHead, Tip } from "@/components/ui";
import { download, newWorkspace, post, upload } from "@/lib/api";
import { clearCache } from "@/lib/hooks";

type Verify = { ok: boolean; files: { path: string; ok: boolean; reason: string; expected?: string; actual?: string }[]; manifest_sha256: string; created_at: string; audit_chain: { ok: boolean; entries?: number } | null; anchored_in_this_workspace: boolean | null };

const CONTENTS = [
  ["inventory.csv / .json", "Every column, class, confidence, signals, masked examples, metadata"],
  ["gaps.csv", "Open metadata gaps with severity"],
  ["reviews.json", "Human decisions and human-confirmed precision"],
  ["audit_chain.json", "The SHA-256 hash-chained audit log and its verification"],
  ["scan_diff.json · drift.json", "What changed between the last two scans"],
  ["evaluation.json", "Benchmark precision/recall/F1 for the rule set used"],
  ["ruleset.yaml", "The exact rule set (version + hash)"],
  ["data_handling_receipts.json", "Rows sampled, in-memory processing, discard times"],
  ["summary.html", "Printable summary with charts (Print → Save as PDF)"],
  ["manifest.json", "SHA-256 of every file + scan metadata"],
];

export default function EvidencePage() {
  const app = useApp();
  const [busy, setBusy] = useState(false);
  const [last, setLast] = useState<string | null>(null);
  const [verify, setVerify] = useState<Verify | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [over, setOver] = useState(false);
  const [wipe, setWipe] = useState("");
  const [wiped, setWiped] = useState<null | { at: string; deleted: Record<string, number>; message: string }>(null);
  const packRef = useRef<HTMLInputElement>(null);
  const wsRef = useRef<HTMLInputElement>(null);

  const exportPack = async () => {
    setBusy(true);
    try {
      const r = await download("/api/evidence", "POST");
      setLast(r.headers.get("x-manifest-sha256"));
      app.toast("Evidence pack downloaded. Its manifest hash is now in the audit log.", { kind: "ok" });
    } catch (e) {
      app.toast((e as Error).message, { kind: "error" });
    } finally {
      setBusy(false);
    }
  };
  const verifyPack = async (f: File) => {
    setVerifying(true);
    setVerify(null);
    try {
      setVerify(await upload<Verify>("/api/evidence/verify", f));
    } catch (e) {
      app.toast((e as Error).message, { kind: "error" });
    } finally {
      setVerifying(false);
    }
  };

  return (
    <>
      <PageHead title="Evidence pack" desc="Export tamper-evident technical evidence, verify a pack later, and manage this browser's workspace." />
      <div className="grid cols-2" style={{ alignItems: "start" }}>
        <section className="card" aria-label="Export">
          <div className="card-head"><h3 className="row" style={{ gap: 8 }}><FileArchive size={16} /> Export</h3></div>
          <div className="card-body stack">
            <button className="btn primary lg" onClick={exportPack} disabled={busy} style={{ justifySelf: "start" }}>
              <Download size={17} /> {busy ? "Building the pack…" : "Export evidence pack"}
            </button>
            {busy && <Loader3D label="Hashing every file…" />}
            {last && <p className="small">Manifest SHA-256 <code className="tag" style={{ wordBreak: "break-all" }}>{last}</code></p>}
            <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 8 }}>
              {CONTENTS.map(([f, d]) => (
                <li key={f} className="row small" style={{ gap: 10, alignItems: "flex-start" }}>
                  <FileCheck2 size={15} color="var(--accent)" style={{ marginTop: 2, flex: "none" }} />
                  <span><code>{f}</code> <span className="muted">· {d}</span></span>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="card" aria-label="Verify a pack">
          <div className="card-head"><h3 className="row" style={{ gap: 8 }}><CheckCircle2 size={16} /> Verify a pack <Tip text="Recomputes the SHA-256 of every file against manifest.json. Hashes show files were not changed after export; they do not prove who created them." /></h3></div>
          <div className="card-body stack">
            <div data-own-drop className={`dropzone ${over ? "over" : ""}`} style={{ padding: 28 }}
              onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
              onDrop={(e) => { e.preventDefault(); setOver(false); const f = e.dataTransfer.files[0]; if (f) verifyPack(f); }}>
              <Upload size={24} color="var(--accent)" />
              <span className="muted small">Drop an evidence pack ZIP to recompute every hash</span>
              <button className="btn sm" onClick={() => packRef.current?.click()}>Choose ZIP</button>
              <input ref={packRef} type="file" accept=".zip" hidden onChange={(e) => e.target.files?.[0] && verifyPack(e.target.files[0])} />
            </div>
            {verifying && <Loader3D label="Recomputing SHA-256 hashes…" />}
            {verify && (
              <div className="stack-sm" role="status">
                <div className={verify.ok ? "badge-ok" : "badge-bad"} style={{ fontSize: 16 }}>
                  {verify.ok ? <CheckCircle2 size={20} /> : <XCircle size={20} />} {verify.ok ? "Pack verified: every file matches its manifest hash" : "Verification failed"}
                </div>
                <p className="small muted">Created {new Date(verify.created_at).toLocaleString()} · audit chain inside the pack {verify.audit_chain?.ok ? "intact" : "broken"}
                  {verify.anchored_in_this_workspace != null && ` · ${verify.anchored_in_this_workspace ? "manifest hash found in this workspace's audit log" : "manifest hash not in this workspace's audit log"}`}</p>
                <table className="table">
                  <tbody>
                    {verify.files.map((f) => (
                      <tr key={f.path}>
                        <td>{f.ok ? <CheckCircle2 size={15} color="var(--ok)" aria-label="pass" /> : <XCircle size={15} color="var(--bad)" aria-label="fail" />}</td>
                        <td><code>{f.path}</code></td>
                        <td className="small" style={{ color: f.ok ? "var(--text-3)" : "var(--bad)" }}>{f.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                
              </div>
            )}
          </div>
        </section>
      </div>

      <section className="card" style={{ marginTop: 16 }} aria-label="Workspace">
        <div className="card-head"><h3 className="row" style={{ gap: 8 }}>Workspace <Tip text="No login: this browser holds a random workspace key." /></h3></div>
        <div className="card-body grid cols-3">
          <div className="stack-sm">
            <b className="row" style={{ gap: 6 }}>Move to another device <Tip text="Export holds aggregates, metadata, decisions and the audit chain only (no raw values). Importing replaces this workspace." /></b>
            <div className="row wrap">
              <button className="btn sm" onClick={() => download("/api/workspace/export")}><Download size={14} /> Export workspace</button>
              <button className="btn sm" onClick={() => wsRef.current?.click()}><Import size={14} /> Import</button>
              <input ref={wsRef} type="file" accept=".json" hidden onChange={async (e) => {
                const f = e.target.files?.[0];
                if (!f) return;
                try { await upload("/api/workspace/import", f); clearCache(); app.toast("Workspace imported and audit chain verified", { kind: "ok" }); }
                catch (err) { app.toast((err as Error).message, { kind: "error" }); }
              }} />
            </div>
          </div>
          <div className="stack-sm">
            <b className="row" style={{ gap: 6 }}>Start fresh <Tip text="Switches this browser to a new empty workspace. The old one stays on the server, reachable only with its key." /></b>
            <button className="btn sm" onClick={() => { newWorkspace(); clearCache(); window.location.href = "/app/overview/"; }}>New empty workspace</button>
          </div>
          <div className="stack-sm">
            <b className="row" style={{ gap: 6, color: "var(--bad)" }}>Wipe workspace <Tip text="Permanently deletes every scan, finding, review, metadata entry, rule version and audit entry. Cannot be undone." /></b>
            <label className="field">Type WIPE to confirm
              <input className="input mono" value={wipe} onChange={(e) => setWipe(e.target.value)} placeholder="WIPE" aria-label="Type WIPE to confirm" />
            </label>
            <button className="btn sm danger" disabled={wipe !== "WIPE"} onClick={async () => {
              const r = await post<{ at: string; deleted: Record<string, number>; message: string }>("/api/workspace/wipe", { confirm: "WIPE" });
              setWiped(r); setWipe(""); clearCache();
            }}><Trash2 size={14} /> Wipe everything</button>
            {wiped && (
              <div className="card pad small" role="status" style={{ borderColor: "var(--ok)" }}>
                <b className="badge-ok">Deleted at {new Date(wiped.at).toLocaleString()}</b>
                <p className="muted">{wiped.message}</p>
                <p className="faint">{Object.entries(wiped.deleted).filter(([, v]) => v).map(([k, v]) => `${v} ${k}`).join(" · ")}</p>
              </div>
            )}
          </div>
        </div>
      </section>
    </>
  );
}
