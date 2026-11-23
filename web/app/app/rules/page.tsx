"use client";

import { CheckCircle2, Download, FlaskConical, Plus, Save, Upload, XCircle } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useApp } from "@/components/app-context";
import { ErrorCard, PageHead, Skeleton, Tip } from "@/components/ui";
import { download, post, upload } from "@/lib/api";
import { CLASS_META, CLASSES, ClassChip } from "@/lib/classes";
import { fmtDate, invalidate, useApi, useDebounced } from "@/lib/hooks";
import type { Cls, Rule, RuleSet } from "@/lib/types";

const VALIDATORS = ["", "email", "indian_mobile", "aadhaar", "pan", "passport", "voter_id", "driving_licence", "gstin", "ifsc", "bank_account", "card_number", "upi_id", "pin_code", "lat_long_pair", "latitude", "longitude", "ip_address", "date_of_birth", "age", "gender", "address", "indian_place", "person_name"];
type Versions = { active: RuleSet; versions: { version: string; hash: string; note: string; created_at: string; rules: number }[] };
type Impact = { summary: Record<string, number>; changes: { pt_id: string; column: string; before: Cls; after: Cls; before_band: string; after_band: string; approximate: boolean }[]; note: string };
type TestResult = { samples: { masked: string; matches: boolean; valid: boolean; embedded: boolean; timed_out: boolean }[]; header: { matched: boolean; keyword: string | null; excluded_by: string | null }; column: null | { class: Cls; confidence: number; band: string; rationale: string } };

const strip = (rs: RuleSet): RuleSet => { const { hash, ...rest } = rs; void hash; return rest as RuleSet; };

export default function RulesPage() {
  const app = useApp();
  const { data, error, reload } = useApi<Versions>("/api/rules");
  const [draft, setDraft] = useState<RuleSet | null>(null);
  const [sel, setSel] = useState<string>("");
  const [filter, setFilter] = useState("");
  const [header, setHeader] = useState("aadhaar_no");
  const [samples, setSamples] = useState("2345 6789 0124\n123456789012\nnot a number\nXXXX XXXX 1234");
  const [test, setTest] = useState<TestResult | null>(null);
  const [impact, setImpact] = useState<Impact | null>(null);
  const [note, setNote] = useState("");
  const importRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (data && !draft) {
      setDraft(strip(data.active));
      setSel(data.active.rules[0]?.id ?? "");
    }
  }, [data, draft]);

  const rule = draft?.rules.find((r) => r.id === sel);
  const dirty = useMemo(() => draft && data && JSON.stringify(draft) !== JSON.stringify(strip(data.active)), [draft, data]);
  const debRule = useDebounced(rule, 300);
  const debSamples = useDebounced(samples, 300);
  const debHeader = useDebounced(header, 300);
  const debDraft = useDebounced(draft, 600);

  useEffect(() => {
    if (!debRule) return;
    post<TestResult>("/api/rules/test", { rule: debRule, header: debHeader, samples: debSamples.split("\n").slice(0, 200) })
      .then(setTest).catch((e) => setTest({ samples: [], header: { matched: false, keyword: null, excluded_by: (e as Error).message }, column: null }));
  }, [debRule, debSamples, debHeader]);

  useEffect(() => {
    if (!debDraft || !dirty) { setImpact(null); return; }
    post<Impact>("/api/rules/impact", { ruleset: debDraft }).then(setImpact).catch(() => setImpact(null));
  }, [debDraft, dirty]);

  const update = (patch: Partial<Rule>) => setDraft((d) => d && { ...d, rules: d.rules.map((r) => (r.id === sel ? { ...r, ...patch } : r)) });
  const save = async () => {
    if (!draft) return;
    try {
      const r = await post<RuleSet>("/api/rules", { ruleset: draft, note: note || "Edited in the Rule Playground" });
      app.toast(`Saved rule set v${r.version}. New scans will use it.`, { kind: "ok" });
      setNote("");
      setDraft(null);
      invalidate();
      reload();
    } catch (e) {
      app.toast((e as Error).message, { kind: "error" });
    }
  };
  const addRule = () => {
    if (!draft) return;
    let id = "custom_rule";
    for (let i = 2; draft.rules.some((r) => r.id === id); i++) id = `custom_rule_${i}`;
    const r: Rule = { id, name: "New rule", class: "IDENTITY", header_keywords: ["keyword"], header_exclude: [], value_regex: "", validator: "", normalise: "none", threshold: 0.35, weight: 1, requires_header: false, embedded: false, enabled: true };
    setDraft({ ...draft, rules: [...draft.rules, r] });
    setSel(id);
  };

  if (error) return <ErrorCard message={error.message} onRetry={reload} />;
  if (!data || !draft) return <div className="stack"><Skeleton h={40} w={300} /><Skeleton h={500} /></div>;

  return (
    <>
      <PageHead title="Rule Playground" ai="AI ENGINE"
        desc={<>Rules are versioned. Active: <b>v{data.active.version}</b> <span className="tag">{data.active.hash?.slice(0, 12)}</span>. Every scan records the rule-set version and hash.</>}
        actions={<>
          <button className="btn sm" onClick={() => download("/api/rules/export?format=yaml")}><Download size={14} /> YAML</button>
          <button className="btn sm" onClick={() => download("/api/rules/export?format=json")}><Download size={14} /> JSON</button>
          <button className="btn sm" onClick={() => importRef.current?.click()}><Upload size={14} /> Import</button>
          <input ref={importRef} type="file" accept=".yaml,.yml,.json" hidden onChange={async (e) => {
            const f = e.target.files?.[0]; if (!f) return;
            try { const r = await upload<{ ruleset: RuleSet }>("/api/rules/import", f); setDraft(r.ruleset); setSel(r.ruleset.rules[0].id); app.toast("Imported into the editor. Review the impact, then save."); }
            catch (err) { app.toast((err as Error).message, { kind: "error" }); }
          }} />
        </>} />

      <div className="grid" style={{ gridTemplateColumns: "minmax(220px, 280px) minmax(0, 1fr) minmax(280px, 380px)", alignItems: "start" }}>
        <section className="card" aria-label="Rules">
          <div className="card-head" style={{ padding: 12 }}>
            <input className="input" style={{ minHeight: 34 }} placeholder="Filter rules" value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filter rules" />
            <button className="btn sm icon" onClick={addRule} aria-label="Add rule"><Plus size={16} /></button>
          </div>
          <div style={{ maxHeight: 620, overflowY: "auto", padding: 6 }}>
            {draft.rules.filter((r) => `${r.id} ${r.name} ${r.class}`.toLowerCase().includes(filter.toLowerCase())).map((r) => (
              <div key={r.id} className="row" style={{ gap: 8, padding: "6px 8px", borderRadius: 8, background: r.id === sel ? "var(--accent-soft)" : undefined }}>
                <input type="checkbox" checked={r.enabled} aria-label={`Enable ${r.name}`} onChange={(e) => setDraft({ ...draft, rules: draft.rules.map((x) => (x.id === r.id ? { ...x, enabled: e.target.checked } : x)) })} />
                <button className="btn ghost sm" style={{ flex: 1, justifyContent: "flex-start", minWidth: 0, opacity: r.enabled ? 1 : 0.5 }} onClick={() => setSel(r.id)}>
                  <span style={{ width: 8, height: 8, borderRadius: 3, background: CLASS_META[r.class].color, flex: "none" }} />
                  <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{r.name}</span>
                </button>
              </div>
            ))}
          </div>
        </section>

        {rule && (
          <section className="card" aria-label={`Edit ${rule.name}`}>
            <div className="card-head"><h3>{rule.name}</h3><span className="tag">{rule.id}</span></div>
            <div className="card-body grid cols-2" style={{ gap: 12 }}>
              <label className="field">Name<input className="input" value={rule.name} onChange={(e) => update({ name: e.target.value })} /></label>
              <label className="field">Class
                <select className="input" value={rule.class} onChange={(e) => update({ class: e.target.value as Cls })}>{CLASSES.map((c) => <option key={c} value={c}>{CLASS_META[c].label}</option>)}</select>
              </label>
              <label className="field" style={{ gridColumn: "1 / -1" }}><span className="row" style={{ gap: 4 }}>Header keywords <Tip text="Comma-separated; matched on normalised names (snake_case, camelCase, abbreviations)." /></span>
                <input className="input mono" value={rule.header_keywords.join(", ")} onChange={(e) => update({ header_keywords: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })} />
              </label>
              <label className="field" style={{ gridColumn: "1 / -1" }}>Exclude when the header also contains
                <input className="input mono" value={rule.header_exclude.join(", ")} onChange={(e) => update({ header_exclude: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })} />
              </label>
              <label className="field" style={{ gridColumn: "1 / -1" }}>Value pattern (regular expression, full match)
                <input className="input mono" value={rule.value_regex} onChange={(e) => update({ value_regex: e.target.value })} spellCheck={false} />
              </label>
              <label className="field">Validator
                <select className="input" value={rule.validator} onChange={(e) => update({ validator: e.target.value })}>{VALIDATORS.map((v) => <option key={v} value={v}>{v || "none"}</option>)}</select>
              </label>
              <label className="field">Normalise values
                <select className="input" value={rule.normalise} onChange={(e) => update({ normalise: e.target.value })}><option value="none">none</option><option value="strip_separators">strip separators</option><option value="upper">upper-case</option></select>
              </label>
              <label className="field">Threshold <b className="num">{rule.threshold.toFixed(2)}</b>
                <input type="range" min={0.05} max={1} step={0.05} value={rule.threshold} onChange={(e) => update({ threshold: Number(e.target.value) })} style={{ accentColor: "var(--accent)" }} />
              </label>
              <label className="field">Weight <b className="num">{rule.weight.toFixed(2)}</b>
                <input type="range" min={0.05} max={1} step={0.05} value={rule.weight} onChange={(e) => update({ weight: Number(e.target.value) })} style={{ accentColor: "var(--accent)" }} />
              </label>
              <label className="row small" style={{ gap: 8 }}><input type="checkbox" checked={rule.requires_header} onChange={(e) => update({ requires_header: e.target.checked })} /> Requires header support</label>
              <label className="row small" style={{ gap: 8 }}><input type="checkbox" checked={rule.embedded} onChange={(e) => update({ embedded: e.target.checked })} /> Also search inside free text</label>
            </div>
            <details style={{ padding: "0 20px 16px" }}>
              <summary className="small muted" style={{ cursor: "pointer" }}>Global scoring settings</summary>
              <div className="grid cols-3" style={{ marginTop: 12, gap: 12 }}>
                {(["header", "value", "validator"] as const).map((k) => (
                  <label key={k} className="field">{k} weight
                    <input className="input num" type="number" step={0.05} min={0} max={1} value={draft.signal_weights[k]} onChange={(e) => setDraft({ ...draft, signal_weights: { ...draft.signal_weights, [k]: Number(e.target.value) } })} />
                  </label>
                ))}
              </div>
              <Tip text={`Weights must add up to 1. Bands: high ≥ ${draft.bands.high}, medium ≥ ${draft.bands.medium}.`} />
            </details>
          </section>
        )}

        <aside className="stack">
          <section className="card" aria-label="Test on sample">
            <div className="card-head"><h4 className="row" style={{ gap: 6 }}><FlaskConical size={15} /> Test on sample</h4><span className="small faint">live</span></div>
            <div className="card-body stack-sm">
              <label className="field">Column header<input className="input mono" value={header} onChange={(e) => setHeader(e.target.value)} /></label>
              <label className="field">Sample values (one per line, not stored)<textarea className="input mono" value={samples} onChange={(e) => setSamples(e.target.value)} rows={6} /></label>
              {test && (
                <>
                  <div className="small">{test.header.matched ? <span className="badge-ok">Header matches “{test.header.keyword}”</span> : <span className="faint">Header does not match{test.header.excluded_by ? ` (excluded by “${test.header.excluded_by}”)` : ""}</span>}</div>
                  <table className="table">
                    <tbody>
                      {test.samples.map((s, i) => (
                        <tr key={i}>
                          <td><code className="small">{s.masked}</code></td>
                          <td className="small">{s.matches ? <span className="badge-ok"><CheckCircle2 size={13} /> pattern</span> : <span className="faint"><XCircle size={13} /> pattern</span>}</td>
                          <td className="small">{s.valid ? <span className="badge-ok"><CheckCircle2 size={13} /> valid</span> : s.matches ? <span style={{ color: "var(--sev-medium)" }}>fails validator</span> : null}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {test.column && <div className="small"><ClassChip cls={test.column.class} compact /> <span className="muted">as a column: {test.column.band.toLowerCase()} ({test.column.confidence.toFixed(2)})</span></div>}
                </>
              )}
            </div>
          </section>

          <section className="card" aria-label="Save">
            <div className="card-head"><h4 className="row" style={{ gap: 6 }}>Impact preview <Tip text="Re-scores the current scan from stored aggregate signals before you save. Approximate (≈) when a pattern or validator changes." /></h4>{dirty ? <span className="tag">unsaved changes</span> : <span className="small faint">no changes</span>}</div>
            <div className="card-body stack-sm">
              
              {dirty && !impact && <Skeleton h={60} />}
              {impact && (
                <>
                  <p><b className="num">{impact.summary.changed}</b> of {impact.summary.columns} findings would change: {impact.summary.newly_personal} newly personal, {impact.summary.no_longer_personal} no longer personal, {impact.summary.class_changed} change class, {impact.summary.band_changed} change confidence band.</p>
                  {impact.changes.slice(0, 6).map((c) => (
                    <div key={c.pt_id} className="row small" style={{ gap: 6 }}><span className="tag">{c.pt_id}</span><code>{c.column}</code><span className="faint">{CLASS_META[c.before].short} → {CLASS_META[c.after].short}{c.approximate ? " ≈" : ""}</span></div>
                  ))}
                  
                </>
              )}
              <input className="input" placeholder="Change note (recorded in the audit log)" value={note} onChange={(e) => setNote(e.target.value)} disabled={!dirty} />
              <div className="row">
                <button className="btn primary" onClick={save} disabled={!dirty}><Save size={15} /> Save as new version</button>
                {dirty && <button className="btn ghost" onClick={() => setDraft(strip(data.active))}>Discard</button>}
              </div>
            </div>
          </section>

          <section className="card" aria-label="Versions">
            <div className="card-head"><h4>Versions</h4></div>
            <ul style={{ listStyle: "none", margin: 0, padding: 8, display: "grid", gap: 4 }}>
              {data.versions.slice().reverse().map((v) => (
                <li key={v.version} className="row" style={{ gap: 8, padding: "6px 8px" }}>
                  <b className="num">v{v.version}</b><span className="tag">{v.hash.slice(0, 8)}</span>
                  <span className="small faint" style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={v.note}>{v.note} · {fmtDate(v.created_at)}</span>
                  {v.version === data.active.version ? <span className="badge-ok small">active</span> : (
                    <button className="btn sm" onClick={async () => { await post("/api/rules/activate", { version: v.version }); setDraft(null); invalidate(); reload(); app.toast(`Rule set v${v.version} is active`); }}>Activate</button>
                  )}
                </li>
              ))}
            </ul>
          </section>
        </aside>
      </div>
      <style>{`@media (max-width: 1200px){ .content .grid[style*="minmax(220px, 280px)"]{grid-template-columns:minmax(0,1fr) !important} }`}</style>
    </>
  );
}
