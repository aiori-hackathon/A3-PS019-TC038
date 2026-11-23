"use client";

import { ArrowRight, Download, FileSearch, GitCompare, Moon, Play, ShieldCheck, Table2, Upload } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { download, get } from "@/lib/api";
import { ClassChip } from "@/lib/classes";
import { useApi } from "@/lib/hooks";
import { ALL_NAV } from "@/lib/nav";
import type { Finding } from "@/lib/types";
import { useApp } from "./app-context";
import { useNav } from "./shell";

type Item = { id: string; label: string; group: string; hint?: string; icon?: ReactNode; run: () => void; keywords?: string };

export function isTyping(e: KeyboardEvent): boolean {
  const t = e.target as HTMLElement | null;
  return !!t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable);
}

function score(q: string, text: string): number {
  if (!q) return 1;
  const t = text.toLowerCase();
  const s = q.toLowerCase();
  if (t.startsWith(s)) return 3;
  if (t.includes(s)) return 2;
  let i = 0;
  for (const ch of t) if (ch === s[i]) i++;
  return i === s.length ? 1 : 0;
}

export function CommandPalette({ onLoadDemo }: { onLoadDemo: () => void }) {
  const app = useApp();
  const { go, openFinding } = useNav();
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const { data } = useApi<{ rows: Finding[] }>(app.palette ? "/api/inventory" : null);

  useEffect(() => {
    if (app.palette) {
      setQ("");
      setSel(0);
      setTimeout(() => input.current?.focus(), 10);
    }
  }, [app.palette]);

  const items = useMemo<Item[]>(() => {
    const close = () => app.setPalette(false);
    const base: Item[] = [
      ...ALL_NAV.map((n) => ({ id: `nav-${n.key}`, label: n.label, group: "Pages", icon: <n.Icon size={16} />, hint: `G ${n.g.toUpperCase()}`, run: () => { go(n.href); close(); } })),
      { id: "a-demo", label: "Load demo company", group: "Actions", icon: <Play size={16} />, run: () => { onLoadDemo(); close(); }, keywords: "acme sample" },
      { id: "a-scan", label: "Scan a file…", group: "Actions", icon: <Upload size={16} />, run: () => { go("/app/sources/"); close(); }, keywords: "upload csv sqlite" },
      { id: "a-evidence", label: "Export evidence pack", group: "Actions", icon: <Download size={16} />, run: async () => { close(); app.toast("Building the evidence pack…"); try { await download("/api/evidence", "POST"); app.toast("Evidence pack downloaded", { kind: "ok" }); } catch (e) { app.toast((e as Error).message, { kind: "error" }); } } },
      { id: "a-compare", label: "Compare scans", group: "Actions", icon: <GitCompare size={16} />, run: () => { go("/app/time-machine/"); close(); }, keywords: "diff drift" },
      { id: "a-verify", label: "Verify audit log integrity", group: "Actions", icon: <ShieldCheck size={16} />, run: async () => { close(); const r = await get<{ ok: boolean; entries: number; broken_at: number | null }>("/api/audit/verify"); app.toast(r.ok ? `Audit chain intact: ${r.entries} entries verified` : `Audit chain broken at entry #${r.broken_at}`, { kind: r.ok ? "ok" : "error" }); } },
      { id: "a-theme", label: "Toggle light/dark theme", group: "Actions", icon: <Moon size={16} />, run: () => { app.toggleTheme(); close(); } },
      { id: "a-help", label: "Ask the help assistant", group: "Actions", icon: <FileSearch size={16} />, run: () => { app.setAssistant(true); close(); } },
    ];
    const rows = data?.rows ?? [];
    const tables = Array.from(new Set(rows.map((r) => r.table)));
    const tableItems: Item[] = tables.map((t) => ({ id: `t-${t}`, label: t, group: "Tables", icon: <Table2 size={16} />, run: () => { go("/app/inventory/", { q: t }); close(); } }));
    const colItems: Item[] = rows.map((r) => ({
      id: `c-${r.pt_id}`, label: `${r.table}.${r.column}`, group: "Columns & findings", hint: r.pt_id, keywords: `${r.pt_id} ${r.class}`,
      icon: <ClassChip cls={r.class} compact />, run: () => { openFinding(r.pt_id); close(); },
    }));
    return [...base, ...tableItems, ...colItems];
  }, [data, app, go, openFinding, onLoadDemo]);

  const filtered = useMemo(() => {
    const scored = items.map((it) => ({ it, s: Math.max(score(q, it.label), score(q, it.keywords ?? ""), score(q, it.hint ?? "")) })).filter((x) => x.s > 0);
    if (q) scored.sort((a, b) => b.s - a.s);
    return scored.slice(0, q ? 40 : 18).map((x) => x.it);
  }, [items, q]);

  if (!app.palette) return null;
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(filtered.length - 1, s + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(0, s - 1)); }
    else if (e.key === "Enter") { e.preventDefault(); filtered[sel]?.run(); }
    else if (e.key === "Escape") app.setPalette(false);
  };
  let lastGroup = "";
  return (
    <>
      <div className="scrim" onClick={() => app.setPalette(false)} />
      <div className="palette" role="dialog" aria-modal="true" aria-label="Command palette">
        <input ref={input} value={q} onChange={(e) => { setQ(e.target.value); setSel(0); }} onKeyDown={onKey}
          placeholder="Jump to a page, table, column, PT-ID or action…" aria-label="Search commands" role="combobox" aria-expanded="true" aria-controls="palette-list"
          aria-activedescendant={filtered[sel] ? `pi-${filtered[sel].id}` : undefined} />
        <ul id="palette-list" role="listbox">
          {filtered.length === 0 && <li className="faint">No matches. Try a table name or PT-00012.</li>}
          {filtered.map((it, i) => {
            const header = it.group !== lastGroup ? <div className="group" key={`g-${it.group}`}>{it.group}</div> : null;
            lastGroup = it.group;
            return (
              <div key={it.id}>
                {header}
                <li id={`pi-${it.id}`} role="option" aria-selected={i === sel} onMouseEnter={() => setSel(i)} onClick={it.run}>
                  {it.icon}
                  <span>{it.label}</span>
                  <span className="kind">{it.hint ?? <ArrowRight size={14} />}</span>
                </li>
              </div>
            );
          })}
        </ul>
      </div>
    </>
  );
}

const SHORTCUTS: [string, string][] = [
  ["Open the command palette", "Ctrl/⌘ K"],
  ["Show this help", "?"],
  ["Go to Overview / Sources / Inventory", "G O · G S · G I"],
  ["Go to Review / Metadata / Rules", "G R · G M · G U"],
  ["Go to Time Machine / Simulator / Evaluation", "G T · G X · G E"],
  ["Go to Evidence pack / Audit log", "G P · G A"],
  ["Review: next / previous", "J · K"],
  ["Review: confirm / reject / reclassify", "C · R · E"],
  ["Review: needs info / focus note", "I · N"],
  ["Undo last action", "Z"],
  ["Close drawer or dialog", "Esc"],
];

/** Global keyboard layer: palette, help overlay and "G then letter" navigation. */
export function Shortcuts() {
  const app = useApp();
  const { go } = useNav();
  const gPressed = useRef(0);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        app.setPalette(!app.palette);
        return;
      }
      if (e.key === "Escape") {
        app.setPalette(false);
        app.setHelp(false);
        return;
      }
      if (isTyping(e) || e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.key === "?") {
        e.preventDefault();
        app.setHelp(!app.help);
        return;
      }
      if (e.key.toLowerCase() === "g") {
        gPressed.current = Date.now();
        return;
      }
      if (Date.now() - gPressed.current < 1200) {
        const target = ALL_NAV.find((n) => n.g === e.key.toLowerCase());
        gPressed.current = 0;
        if (target) {
          e.preventDefault();
          go(target.href);
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [app, go]);

  if (!app.help) return null;
  return (
    <>
      <div className="scrim" onClick={() => app.setHelp(false)} />
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="sc-title">
        <div className="row between" style={{ marginBottom: 16 }}>
          <h3 id="sc-title">Keyboard shortcuts</h3>
          <button className="btn sm" onClick={() => app.setHelp(false)}>Close</button>
        </div>
        <div className="shortcut-grid">
          {SHORTCUTS.map(([d, k]) => (
            <div key={d} style={{ display: "contents" }}>
              <span className="muted">{d}</span>
              <span>{k.split(" · ").map((x) => <kbd key={x} style={{ marginLeft: 4 }}>{x}</kbd>)}</span>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
