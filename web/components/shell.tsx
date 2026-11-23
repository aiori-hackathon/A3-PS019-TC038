"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ArrowRight, Bot, Check, ChevronsLeft, ChevronsRight, CircleHelp, Command, Menu, Moon, MoreHorizontal, Search, Sun, Upload, X } from "lucide-react";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { storage } from "@/lib/api";
import { ClassChip } from "@/lib/classes";
import { invalidate, useApi } from "@/lib/hooks";
import { ALL_NAV, MOBILE_TABS, NAV } from "@/lib/nav";
import type { Cls, Overview, ScanInfo } from "@/lib/types";
import { useApp } from "./app-context";
import { Assistant } from "./assistant";
import { FindingDrawer } from "./drawer";
import { CommandPalette, Shortcuts } from "./palette";
import { LegalFooter, Loader3D, Logo } from "./ui";

export function useNav() {
  const router = useRouter();
  const params = useSearchParams();
  const pathname = usePathname();
  /** Navigate within the app, keeping the scan selector. */
  const go = useCallback(
    (href: string, extra: Record<string, string> = {}) => {
      const p = new URLSearchParams();
      const scan = params.get("scan");
      if (scan) p.set("scan", scan);
      for (const [k, v] of Object.entries(extra)) p.set(k, v);
      const q = p.toString();
      router.push(href + (q ? `?${q}` : ""));
    },
    [router, params],
  );
  const openFinding = useCallback(
    (pt: string) => {
      const p = new URLSearchParams(params.toString());
      p.set("f", pt);
      router.replace(`${pathname}?${p.toString()}`, { scroll: false });
    },
    [router, params, pathname],
  );
  return { go, openFinding, params, pathname, router };
}

export function AppShell({ children }: { children: ReactNode }) {
  const { pathname, params, router, go } = useNav();
  const app = useApp();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileRail, setMobileRail] = useState(false);
  const { demoLoading, loadDemo } = app;
  const scan = params.get("scan");
  const { data: ov } = useApi<Overview & { kpis: { pending_review?: number } }>(`/api/overview${scan ? `?scan=${scan}` : ""}`);
  const { data: scans } = useApi<{ scans: ScanInfo[] }>("/api/scans");

  useEffect(() => {
    setCollapsed(storage.get("pt.rail") === "collapsed");
  }, []);

  // session continuity: remember the last page
  useEffect(() => {
    if (pathname.startsWith("/app/")) storage.set("pt.lastPage", pathname);
    setMobileRail(false);
  }, [pathname]);

  // ?demo=1 from the landing page: build the demo, then drop the parameter
  useEffect(() => {
    if (params.get("demo") === "1") {
      loadDemo().then(() => router.replace(pathname));
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const toggleRail = () => {
    const next = !collapsed;
    setCollapsed(next);
    storage.set("pt.rail", next ? "collapsed" : "open");
  };

  const nba = ov?.next_action;
  const runAction = () => {
    if (!nba) return;
    if (nba.action === "load_demo") loadDemo();
    else go(`/app/${nba.action}/`);
  };
  const current = ALL_NAV.find((n) => pathname.startsWith(n.href));
  const pending = ov?.kpis?.pending_review;

  return (
    <div className={`shell ${collapsed ? "collapsed" : ""}`}>
      <a className="skip-link" href="#main">Skip to content</a>
      <aside className={`rail ${mobileRail ? "open" : ""}`} aria-label="Main navigation">
        <Link href="/" className="brand" aria-label="PrivacyTwin home">
          <Logo />
          <span className="brand-text">PrivacyTwin</span>
        </Link>
        {NAV.map((g) => (
          <div className="rail-group" key={g.group}>
            <div className="rail-label">{g.group}</div>
            {g.items.map((it) => (
              <Link key={it.key} href={it.href + (scan ? `?scan=${scan}` : "")} className="nav-item" aria-current={pathname.startsWith(it.href) ? "page" : undefined}
                title={collapsed ? it.label : undefined} data-tour={`nav-${it.key}`}>
                <it.Icon aria-hidden />
                <span className="nav-text">{it.label}</span>
                {it.key === "review" && pending ? <span className="count num" aria-label={`${pending} pending`}>{pending}</span> : null}
              </Link>
            ))}
          </div>
        ))}
        <div className="rail-foot">
          <button className="nav-item btn ghost" style={{ width: "100%", justifyContent: collapsed ? "center" : "flex-start" }} onClick={toggleRail} aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}>
            {collapsed ? <ChevronsRight aria-hidden /> : <ChevronsLeft aria-hidden />}
            <span className="nav-text">Collapse</span>
          </button>
        </div>
      </aside>
      {mobileRail && <div className="scrim" onClick={() => setMobileRail(false)} />}

      <div className="main">
        <header className="topbar">
          <button className="btn icon ghost" style={{ display: "none" }} id="menu-btn" aria-label="Open navigation" onClick={() => setMobileRail(true)}>
            <Menu size={18} />
          </button>
          <div className="ws-name">
            <span className="hide-sm faint">Workspace</span>
            <span>{current?.label ?? "PrivacyTwin"}</span>
          </div>
          <ScanSelector scans={scans?.scans ?? []} />
          <div className="spacer" />
          <SavedIndicator at={app.saved} />
          <button className="palette-trigger" onClick={() => app.setPalette(true)} aria-label="Open command palette (Ctrl+K)">
            <Search size={15} aria-hidden />
            <span className="label">Jump to anything…</span>
            <kbd className="hide-sm"><Command size={10} style={{ verticalAlign: -1 }} />K</kbd>
          </button>
          <button className="btn sm" onClick={() => app.setAssistant(!app.assistant)} aria-label="Ask AI" aria-pressed={app.assistant} style={{ borderColor: "#7c6cf0" }}>
            <Bot size={16} color="#7c6cf0" /><span className="hide-sm">Ask AI</span>
          </button>
          <button className="btn icon ghost" onClick={app.toggleTheme} aria-label={`Switch to ${app.theme === "dark" ? "light" : "dark"} theme`}>
            {app.theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
          </button>
          <button className="btn icon ghost hide-sm" onClick={() => app.setHelp(true)} aria-label="Keyboard shortcuts">
            <CircleHelp size={18} />
          </button>
        </header>
        {nba && (
          <div className="nba" data-tour="nba" role="region" aria-label="Next best action">
            <span className="pulse" aria-hidden />
            <span className="nba-label">Next</span>
            <span className="nba-text">{nba.text}</span>
            <button className="btn sm primary" onClick={runAction} disabled={demoLoading}>
              {nba.label} <ArrowRight size={14} aria-hidden />
            </button>
          </div>
        )}
        <main id="main" className="content" tabIndex={-1}>
          {demoLoading ? (
            <div className="card pad" style={{ display: "grid", placeItems: "center", minHeight: 360 }}>
              <Loader3D label="Building the Acme Fintech India twin: 3 scans, 6 tables, reviews and metadata…" />
            </div>
          ) : (
            <div className="page" key={pathname}>{children}</div>
          )}
        </main>
        <LegalFooter />
      </div>

      <nav className="tabbar" aria-label="Main">
        {MOBILE_TABS.map((k) => {
          const it = ALL_NAV.find((n) => n.key === k)!;
          return (
            <Link key={k} href={it.href} aria-current={pathname.startsWith(it.href) ? "page" : undefined}>
              <it.Icon size={20} aria-hidden />
              {it.label.split(" ")[0]}
            </Link>
          );
        })}
        <button onClick={() => setMobileRail(true)} aria-label="More pages">
          <MoreHorizontal size={20} aria-hidden />
          More
        </button>
      </nav>

      <DropAnywhere />
      <ScanPanel />
      <Toasts />
      <FindingDrawer />
      <CommandPalette onLoadDemo={loadDemo} />
      <Shortcuts />
      {app.assistant && <Assistant />}
      <style>{`@media (max-width: 860px){#menu-btn{display:inline-flex !important}}`}</style>
    </div>
  );
}

/** Subtle autosave confirmation: appears after a save and fades after 2.5s. */
function SavedIndicator({ at }: { at: number }) {
  const [show, setShow] = useState(false);
  useEffect(() => {
    if (!at) return;
    setShow(true);
    const t = setTimeout(() => setShow(false), 2500);
    return () => clearTimeout(t);
  }, [at]);
  return (
    <span className={`saved ${show ? "show" : ""}`} aria-live="polite">
      {show && (<><Check size={14} aria-hidden /> Saved</>)}
    </span>
  );
}

function ScanSelector({ scans }: { scans: ScanInfo[] }) {
  const { params, pathname, router } = useNav();
  if (scans.length < 2) return null;
  const value = params.get("scan") ?? "";
  return (
    <label className="hide-sm" style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <span className="sr-only">Snapshot</span>
      <select className="input" style={{ minHeight: 34, width: "auto", padding: "4px 8px", fontSize: 13 }} value={value}
        onChange={(e) => {
          const p = new URLSearchParams(params.toString());
          if (e.target.value) p.set("scan", e.target.value);
          else p.delete("scan");
          router.push(`${pathname}${p.toString() ? `?${p}` : ""}`);
        }}>
        <option value="">Latest snapshot (scan #{scans[scans.length - 1].seq})</option>
        {scans.slice(0, -1).reverse().map((s) => (
          <option key={s.seq} value={s.seq}>As of scan #{s.seq} · {new Date(s.created_at).toLocaleDateString()}</option>
        ))}
      </select>
    </label>
  );
}

/** Drop a CSV or SQLite file anywhere in the app to scan it immediately with smart defaults. */
function DropAnywhere() {
  const app = useApp();
  const [over, setOver] = useState(false);
  useEffect(() => {
    let depth = 0;
    const hasFiles = (e: DragEvent) => Array.from(e.dataTransfer?.types ?? []).includes("Files");
    const enter = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      depth++;
      setOver(true);
    };
    const leave = () => {
      depth = Math.max(0, depth - 1);
      if (!depth) setOver(false);
    };
    const overFn = (e: DragEvent) => {
      if (hasFiles(e)) e.preventDefault();
    };
    const drop = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      depth = 0;
      setOver(false);
      const target = e.target as HTMLElement;
      if (target.closest("[data-own-drop]")) return; // a specific drop zone handles it
      const file = e.dataTransfer?.files?.[0];
      if (file) app.startScan(file);
    };
    window.addEventListener("dragenter", enter);
    window.addEventListener("dragleave", leave);
    window.addEventListener("dragover", overFn);
    window.addEventListener("drop", drop);
    return () => {
      window.removeEventListener("dragenter", enter);
      window.removeEventListener("dragleave", leave);
      window.removeEventListener("dragover", overFn);
      window.removeEventListener("drop", drop);
    };
  }, [app]);
  if (!over) return null;
  return (
    <div className="drop-overlay" aria-hidden>
      <div className="box">
        <Upload size={36} color="var(--accent)" />
        <h3>Drop to scan</h3>
        
      </div>
    </div>
  );
}

function ScanPanel() {
  const app = useApp();
  const { go } = useNav();
  const s = app.scan;
  if (!s.active) return null;
  const cols = s.events.filter((e) => e.type === "column") as Extract<(typeof s.events)[number], { type: "column" }>[];
  const personal = cols.filter((c) => c.class !== "NOT_PERSONAL");
  const start = s.events.find((e) => e.type === "start") as Extract<(typeof s.events)[number], { type: "start" }> | undefined;
  return (
    <section className="scanpanel card" aria-live="polite" aria-label="Scan progress">
      <div className="card-head">
        <div>
          <h4 className="row" style={{ gap: 8 }}>{s.done ? "Scan complete" : s.error ? "Scan stopped" : <span className="ai-typing">{s.events.some((e) => e.type === "triage") ? "AI is reviewing candidates" : "AI is classifying columns"}</span>}</h4>
          <div className="small faint mono" style={{ maxWidth: 300, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.file}</div>
        </div>
        <button className="btn sm icon ghost" onClick={app.closeScan} aria-label="Close scan panel"><X size={16} /></button>
      </div>
      <div className="progress" aria-hidden><span style={{ width: `${Math.round(s.progress * 100)}%` }} /></div>
      <div className="scan-feed">
        {s.error && <p role="alert" style={{ color: "var(--bad)" }}>{s.error}</p>}
        {start && <div className="faint small">{start.rescan ? "New snapshot of an existing source" : "New source"} · {start.tables} table(s) · {start.columns} columns · rules v{start.ruleset}</div>}
        {!s.done && !s.error && cols.length === 0 && <Loader3D />}
        {personal.slice(-8).map((c, i) => (
          <div className="scan-line" key={`${c.table}.${c.column}.${i}`}>
            <ClassChip cls={c.class as Cls} compact />
            <code style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.table}.{c.column}</code>
            <span className="faint small mono" style={{ marginLeft: "auto" }}>{c.masked_examples[0] ?? ""}</span>
          </div>
        ))}
        <div className="small muted">{cols.length} columns analysed · {personal.length} personal-data candidates so far</div>
        {s.done && (
          <div className="row wrap" style={{ marginTop: 8 }}>
            <button className="btn sm primary" onClick={() => { go("/app/inventory/"); app.closeScan(); }}>View inventory</button>
            <button className="btn sm" onClick={() => { go("/app/review/"); app.closeScan(); }}>Review candidates</button>
            <span className="small faint">Raw values discarded at {new Date(String(s.done.receipt.raw_values_discarded_at)).toLocaleTimeString()}</span>
          </div>
        )}
      </div>
    </section>
  );
}

function Toasts() {
  const app = useApp();
  return (
    <div className="toasts" role="status" aria-live="polite">
      {app.toasts.map((t) => (
        <div key={t.id} className={`toast ${t.kind ?? ""}`}>
          <span style={{ flex: 1 }}>{t.text}</span>
          {t.undo && (
            <button className="btn sm" onClick={async () => { app.dismiss(t.id); await t.undo?.(); invalidate(); app.toast("Undone"); }}>
              Undo <kbd>Z</kbd>
            </button>
          )}
          <button className="btn sm icon ghost" onClick={() => app.dismiss(t.id)} aria-label="Dismiss"><X size={14} /></button>
          <span className="bar" style={{ animationDuration: `${t.ms}ms` }} />
        </div>
      ))}
    </div>
  );
}
