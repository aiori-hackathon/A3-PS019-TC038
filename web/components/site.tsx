"use client";

import Link from "next/link";
import { Moon, Sun } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { storage } from "@/lib/api";
import { DISCLAIMER, Logo } from "./ui";

export function ThemeToggle() {
  const [t, setT] = useState<"dark" | "light">("dark");
  useEffect(() => { setT((document.documentElement.dataset.theme as "dark" | "light") || "dark"); }, []);
  return (
    <button className="btn icon ghost" aria-label={`Switch to ${t === "dark" ? "light" : "dark"} theme`}
      onClick={() => { const n = t === "dark" ? "light" : "dark"; document.documentElement.dataset.theme = n; storage.set("pt.theme", n); setT(n); }}>
      {t === "dark" ? <Sun size={18} /> : <Moon size={18} />}
    </button>
  );
}

export function SiteNav() {
  return (
    <header className="site-nav">
      <Link href="/" className="brand" style={{ padding: 0 }} aria-label="PrivacyTwin home"><Logo /><span>PrivacyTwin</span></Link>
      <nav aria-label="Site">
        
        <Link href="/evaluation/">Evaluation</Link>
        <Link href="/security/">Security</Link>
        <Link href="/docs/">Docs</Link>
        <Link href="/faq/">FAQ</Link>
      </nav>
      <div style={{ flex: 1 }} />
      <ThemeToggle />
      <Link href="/app/" className="btn primary sm">Open the app</Link>
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="wrap">
        <div className="cols">
          <div className="stack-sm">
            <Link href="/" className="brand" style={{ padding: 0 }}><Logo /><span>PrivacyTwin</span></Link>
            <p className="muted small" style={{ maxWidth: 320 }}>Your personal-data estate, mirrored. Evidence, not verdicts.</p>
            <p className="small faint">No tracking cookies. No analytics. No sign-up.</p>
          </div>
          <div><b className="small">Product</b><Link href="/app/">Open the app</Link><Link href="/evaluation/">Evaluation results</Link><Link href="/docs/">Documentation</Link></div>
          <div><b className="small">Trust</b><Link href="/security/">Security</Link><Link href="/docs/#legality">Why we don&apos;t decide legality</Link><Link href="/privacy/">Privacy</Link><Link href="/terms/">Terms</Link></div>
          <div><b className="small">Company</b><Link href="/about/">About</Link><Link href="/faq/">FAQ</Link><Link href="/contact/">Contact</Link></div>
        </div>
        <hr className="divider" />
        <p className="small"><b>{DISCLAIMER}</b></p>
      </div>
    </footer>
  );
}

export function SitePage({ eyebrow, title, lede, children }: { eyebrow: string; title: string; lede?: string; children: ReactNode }) {
  return (
    <>
      <SiteNav />
      <main id="main" className="wrap" style={{ padding: "56px 0 24px" }}>
        <div className="eyebrow">{eyebrow}</div>
        <h1 style={{ fontSize: "clamp(30px, 4vw, 44px)", letterSpacing: "-0.03em", maxWidth: 820 }}>{title}</h1>
        {lede && <p className="muted" style={{ fontSize: 17, marginTop: 14, maxWidth: 720 }}>{lede}</p>}
        <div style={{ marginTop: 36 }}>{children}</div>
      </main>
      <SiteFooter />
    </>
  );
}
