"use client";

import { BarChart3, Info, Sparkles, Table2 } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { usePrefersReducedMotion } from "@/lib/hooks";

export const DISCLAIMER = "Technical evidence for human review. Not a legal determination.";

export function Logo({ size = 30 }: { size?: number }) {
  return (
    <svg className="brand-mark" width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <defs>
        <linearGradient id="ptg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="var(--accent)" />
          <stop offset="1" stopColor="var(--c-contact)" />
        </linearGradient>
      </defs>
      <path d="M16 3 28 9.5 16 16 4 9.5Z" fill="url(#ptg)" opacity="0.95" />
      <path d="M4 15.5 16 22l12-6.5" fill="none" stroke="url(#ptg)" strokeWidth="2.2" strokeLinejoin="round" opacity="0.75" />
      <path d="M4 21.5 16 28l12-6.5" fill="none" stroke="url(#ptg)" strokeWidth="2.2" strokeLinejoin="round" opacity="0.45" />
    </svg>
  );
}

export function Skeleton({ h = 16, w = "100%", r = 8, style }: { h?: number; w?: number | string; r?: number; style?: React.CSSProperties }) {
  return <div className="skel" style={{ height: h, width: w, borderRadius: r, ...style }} aria-hidden />;
}

export function SkeletonPage() {
  return (
    <div className="stack" aria-busy="true" aria-label="Loading">
      <Skeleton h={28} w={260} />
      <div className="kpis">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} h={96} r={12} />
        ))}
      </div>
      <div className="grid cols-2">
        <Skeleton h={280} r={12} />
        <Skeleton h={280} r={12} />
      </div>
    </div>
  );
}

export function EmptyState({ title, body, action }: { title: string; body: string; action?: ReactNode }) {
  return (
    <div className="empty card">
      <svg className="art" viewBox="0 0 120 90" aria-hidden>
        <g transform="translate(60 48) skewY(-18) scale(1 .6)">
          {[0, 1, 2].map((i) => (
            <rect key={i} x={-40 + i * 4} y={-28 - i * 14} width="80" height="56" rx="8" fill="none" stroke="var(--border-strong)" strokeWidth="2" strokeDasharray={i === 2 ? "5 5" : undefined} />
          ))}
        </g>
        <circle cx="86" cy="22" r="5" fill="var(--accent)" />
      </svg>
      <h3 style={{ fontSize: 17 }}>{title}</h3>
      <p>{body}</p>
      {action}
    </div>
  );
}

/** Helper text lives in tooltips: an (i) button that reveals on hover or keyboard focus. */
export function Tip({ text, align }: { text: ReactNode; align?: "right" }) {
  return (
    <span className={`tip ${align ?? ""}`}>
      <button type="button" aria-label={typeof text === "string" ? text : "More information"}><Info size={14} aria-hidden /></button>
      <span className="bubble-tip" role="tooltip">{text}</span>
    </span>
  );
}

/** Visible marker for AI-driven features. The tooltip says how it works. */
export function AiBadge({ label = "AI", how }: { label?: string; how?: string }) {
  return (
    <span className="row" style={{ gap: 2, display: "inline-flex" }}>
      <span className="ai-badge"><Sparkles size={11} aria-hidden />{label}</span>
      {how && <Tip text={how} />}
    </span>
  );
}

export function PageHead({ title, desc, actions, ai }: { eyebrow?: string; title: string; desc?: ReactNode; actions?: ReactNode; ai?: string }) {
  return (
    <div className="page-head" style={{ alignItems: "center" }}>
      <div className="row" style={{ gap: 8 }}>
        <h1>{title}</h1>
        {ai && <AiBadge label={ai} />}
        {desc && <Tip text={desc} />}
      </div>
      {actions && <div className="row wrap">{actions}</div>}
    </div>
  );
}

/** Every chart: title, description for screen readers, and a "View as table" toggle. */
export function ChartFrame({ title, desc, children, table, actions }: { title: string; desc: string; children: ReactNode; table: { head: string[]; rows: (string | number)[][] }; actions?: ReactNode }) {
  const [asTable, setAsTable] = useState(false);
  return (
    <section className="card" aria-label={title}>
      <div className="card-head">
        <h3>{title}</h3>
        <div className="row">
          {actions}
          <button className="btn sm ghost" onClick={() => setAsTable((v) => !v)} aria-pressed={asTable}>
            {asTable ? <BarChart3 size={15} aria-hidden /> : <Table2 size={15} aria-hidden />}
            {asTable ? "View as chart" : "View as table"}
          </button>
        </div>
      </div>
      <div className="card-body">
        <p className="sr-only">{desc}</p>
        {asTable ? (
          <table className="table">
            <thead>
              <tr>{table.head.map((h) => <th key={h}>{h}</th>)}</tr>
            </thead>
            <tbody>
              {table.rows.map((r, i) => (
                <tr key={i}>{r.map((c, j) => <td key={j} className={typeof c === "number" ? "num" : undefined}>{c}</td>)}</tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div aria-hidden>{children}</div>
        )}
      </div>
    </section>
  );
}

/** Pointer-driven 3D tilt with a soft glare. Disabled under reduced motion. */
export function useTilt<T extends HTMLElement>(max = 6) {
  const ref = useRef<T>(null);
  const reduced = usePrefersReducedMotion();
  useEffect(() => {
    const el = ref.current;
    if (!el || reduced) return;
    const move = (e: PointerEvent) => {
      const r = el.getBoundingClientRect();
      const x = (e.clientX - r.left) / r.width;
      const y = (e.clientY - r.top) / r.height;
      el.style.transform = `perspective(700px) rotateX(${(0.5 - y) * max}deg) rotateY(${(x - 0.5) * max}deg) translateZ(0)`;
      el.style.setProperty("--gx", `${x * 100}%`);
      el.style.setProperty("--gy", `${y * 100}%`);
    };
    const leave = () => (el.style.transform = "");
    el.addEventListener("pointermove", move);
    el.addEventListener("pointerleave", leave);
    return () => {
      el.removeEventListener("pointermove", move);
      el.removeEventListener("pointerleave", leave);
    };
  }, [max, reduced]);
  return ref;
}

export function KpiTile({ label, value, prev, icon, onClick, suffix = "", invert = false, hint }: { label: string; value: number | null; prev?: number | null; icon?: ReactNode; onClick?: () => void; suffix?: string; invert?: boolean; hint?: string }) {
  const ref = useTilt<HTMLButtonElement>();
  const delta = value != null && prev != null ? value - prev : null;
  const good = delta == null || delta === 0 ? null : invert ? delta < 0 : delta > 0;
  return (
    <button ref={ref} className="kpi" onClick={onClick} title={hint} aria-label={`${label}: ${value ?? "not available"}${suffix}. ${delta ? `${delta > 0 ? "Up" : "Down"} ${Math.abs(delta)} since the previous scan.` : ""} ${onClick ? "Open filtered inventory." : ""}`}>
      <span className="glare" aria-hidden />
      <span className="label">{icon}{label}</span>
      <span className="value">{value == null ? "—" : <CountUp value={value} />}{value != null && suffix}</span>
      <span className={`trend ${good == null ? "" : good ? "up" : "down"}`}>
        {delta == null ? "No previous scan" : delta === 0 ? "No change since last scan" : `${delta > 0 ? "▲" : "▼"} ${Math.abs(delta)} vs previous scan`}
      </span>
    </button>
  );
}

export function CountUp({ value, ms = 700 }: { value: number; ms?: number }) {
  const [v, setV] = useState(value);
  const from = useRef(0);
  const reduced = usePrefersReducedMotion();
  useEffect(() => {
    if (reduced) {
      setV(value);
      return;
    }
    const start = performance.now();
    const a = from.current;
    let raf = 0;
    const tick = (t: number) => {
      const p = Math.min(1, (t - start) / ms);
      const e = 1 - Math.pow(1 - p, 3);
      setV(Math.round(a + (value - a) * e));
      if (p < 1) raf = requestAnimationFrame(tick);
      else from.current = value;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, ms, reduced]);
  return <span className="num">{v.toLocaleString()}</span>;
}

export function Gauge({ score, size = 180 }: { score: number | null; size?: number }) {
  const s = score ?? 0;
  const r = 70;
  const c = Math.PI * r;
  const color = s >= 75 ? "var(--ok)" : s >= 50 ? "var(--sev-medium)" : "var(--sev-high)";
  return (
    <div className="gauge" style={{ width: size, height: size * 0.58 }} role="img" aria-label={`Posture indicator ${score ?? "not available"} out of 100`}>
      <svg viewBox="0 0 180 104" aria-hidden>
        <path d="M20 94 A70 70 0 0 1 160 94" fill="none" stroke="var(--surface-3)" strokeWidth="14" strokeLinecap="round" />
        <path d="M20 94 A70 70 0 0 1 160 94" fill="none" stroke={color} strokeWidth="14" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c * (1 - s / 100)} style={{ transition: "stroke-dashoffset 900ms var(--ease)" }} />
        {[0, 25, 50, 75, 100].map((t) => {
          const a = Math.PI * (1 - t / 100);
          return <line key={t} x1={90 + 54 * Math.cos(a)} y1={94 - 54 * Math.sin(a)} x2={90 + 48 * Math.cos(a)} y2={94 - 48 * Math.sin(a)} stroke="var(--text-3)" strokeWidth="1.5" />;
        })}
      </svg>
      <div className="score">{score == null ? "—" : <CountUp value={score} />}</div>
    </div>
  );
}

export function SignalBars({ signals, validator }: { signals: { header: number; value: number; validator: number; embedded?: number }; validator?: string | null }) {
  const rows: [string, number, string][] = [
    ["Header", signals.header, signals.header ? "Name matched a keyword" : "No keyword in the name"],
    ["Value", signals.embedded && signals.embedded > signals.value ? signals.embedded : signals.value, signals.embedded && signals.embedded > signals.value ? "Share of values containing a match in free text" : "Share of sampled values matching the pattern"],
    ["Validator", signals.validator, `Share passing ${validator ? validator.replace(/_/g, " ") : "the validator"}`],
  ];
  return (
    <div className="stack-sm">
      {rows.map(([label, v, title]) => (
        <div className="signal" key={label} title={title}>
          <span className="muted">{label}</span>
          <span className="track" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(v * 100)} aria-label={`${label} signal`}>
            <span className="fill" style={{ width: `${Math.max(2, v * 100)}%`, background: label === "Validator" ? "var(--c-financial)" : label === "Value" ? "var(--c-contact)" : "var(--accent)" }} />
          </span>
          <span className="num" style={{ textAlign: "right" }}>{Math.round(v * 100)}%</span>
        </div>
      ))}
    </div>
  );
}

export function Loader3D({ label }: { label?: string }) {
  return (
    <div className="stack-sm" style={{ justifyItems: "center" }} role="status" aria-live="polite">
      <div className="loader3d" aria-hidden>
        <div className="rig">
          <div className="plate" style={{ ["--z" as string]: "0px" }} />
          <div className="plate" style={{ ["--z" as string]: "18px" }} />
          <div className="plate" style={{ ["--z" as string]: "36px" }} />
        </div>
      </div>
      {label && <span className="muted">{label}</span>}
    </div>
  );
}

export function LegalFooter() {
  return (
    <footer className="legal-footer">
      <span><strong>{DISCLAIMER}</strong></span>
      <span>No tracking cookies. No sign-up. Raw values never leave this deployment.</span>
    </footer>
  );
}

export function ErrorCard({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="card pad row between wrap" role="alert" style={{ borderColor: "color-mix(in srgb, var(--bad) 40%, var(--border))" }}>
      <div>
        <b>That didn&apos;t load.</b> <span className="muted">{message}</span>
      </div>
      {onRetry && <button className="btn sm" onClick={onRetry}>Retry</button>}
    </div>
  );
}
