"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { health, session } from "@/lib/api";
import { Loader3D, Logo } from "./ui";

type Phase = "checking" | "waking" | "ready" | "failed";

/**
 * Cold-start screen. Free-tier hosts sleep; the first request can take ~30s.
 * We never hang on "Connecting": a progress bar and automatic retries show what is
 * happening, and after 90s we explain the problem with a retry button.
 */
export function ServerGate({ children }: { children: ReactNode }) {
  const [phase, setPhase] = useState<Phase>("checking");
  const [elapsed, setElapsed] = useState(0);
  const [attempt, setAttempt] = useState(0);
  const started = useRef(0);

  useEffect(() => {
    let cancelled = false;
    started.current = Date.now();
    const tick = setInterval(() => setElapsed((Date.now() - started.current) / 1000), 250);
    (async () => {
      for (let i = 0; !cancelled; i++) {
        setAttempt(i + 1);
        if (await health(i === 0 ? 2500 : 6000)) {
          try {
            await session(true);
            if (!cancelled) setPhase("ready");
            break;
          } catch {
            /* fall through and retry */
          }
        }
        if (cancelled) break;
        if (Date.now() - started.current > 90_000) {
          setPhase("failed");
          break;
        }
        setPhase("waking");
        await new Promise((r) => setTimeout(r, 2500));
      }
      clearInterval(tick);
    })();
    return () => {
      cancelled = true;
      clearInterval(tick);
    };
  }, []);

  if (phase === "ready") return <>{children}</>;
  const progress = Math.min(96, (elapsed / 35) * 100);
  return (
    <main className="gate">
      <div className="card" role="status" aria-live="polite">
        <Logo size={40} />
        {phase === "checking" && <Loader3D label="Connecting to your twin…" />}
        {phase === "waking" && (
          <>
            <Loader3D />
            <h2 style={{ fontSize: 20 }}>Waking up the server (~30s)</h2>
            <p className="muted">The demo backend sleeps when idle. It is starting now. This page retries automatically (attempt {attempt}).</p>
            <div className="meter" style={{ width: "100%" }} aria-label="Wake-up progress">
              <span style={{ width: `${progress}%` }} />
            </div>
            <p className="faint small">Meanwhile, the <Link href="/docs/">documentation</Link> and <Link href="/evaluation/">published evaluation</Link> work without the server.</p>
          </>
        )}
        {phase === "failed" && (
          <>
            <h2 style={{ fontSize: 20 }}>The server didn&apos;t answer</h2>
            <p className="muted">We tried for 90 seconds. The backend may be down or blocked by a network filter. Nothing was lost; your workspace key stays in this browser.</p>
            <div className="row">
              <button className="btn primary" onClick={() => window.location.reload()}>Try again</button>
              <Link className="btn" href="/">Back to home</Link>
            </div>
          </>
        )}
      </div>
    </main>
  );
}
