"use client";

import { useEffect, useRef } from "react";
import { usePrefersReducedMotion } from "@/lib/hooks";

const COLORS = ["var(--c-identity)", "var(--c-contact)", "var(--c-government)", "var(--c-financial)", "var(--c-location)"];

// Deterministic "columns" per layer: [x, y, class index or -1 for not personal]
const LAYERS: [number, number, number][][] = [
  [[0, 0, 0], [1, 0, 1], [2, 0, -1], [3, 0, 2], [0, 1, -1], [1, 1, 4], [2, 1, 1], [3, 1, -1], [0, 2, 3], [2, 2, -1], [3, 2, 4]],
  [[0, 0, -1], [1, 0, 3], [2, 0, 3], [3, 0, -1], [0, 1, 0], [1, 1, -1], [3, 1, 1], [0, 2, -1], [1, 2, 2], [2, 2, 4], [3, 2, -1]],
  [[0, 0, 1], [1, 0, -1], [2, 0, 0], [3, 0, 4], [1, 1, 2], [2, 1, -1], [3, 1, 3], [0, 2, 0], [1, 2, -1], [3, 2, 1]],
];

function Stack({ x, y, mirrored, label }: { x: number; y: number; mirrored: boolean; label: string }) {
  return (
    <div className="twin-stack" style={{ left: x, top: y, width: 190, height: 150 }}>
      {LAYERS.map((cells, i) => (
        <div key={i} className="twin-layer" style={{ transform: `translateZ(${i * 46}px)`, animationDelay: `${i * -1.4}s` }}>
          {cells.map(([cx, cy, c], j) => (
            <span
              key={j}
              className={`cell ${!mirrored || c < 0 ? "dim" : ""}`}
              style={{ left: 22 + cx * 40, top: 24 + cy * 40, ["--c" as string]: c >= 0 ? COLORS[c] : "var(--c-none)" }}
            />
          ))}
          {!mirrored && i === 1 && <div className="scan-beam" />}
        </div>
      ))}
      <span className="twin-label" style={{ transform: "translateZ(150px) rotateZ(38deg) rotateX(-58deg)", left: 40, top: -10 }}>{label}</span>
    </div>
  );
}

/** Immersive hero: the estate on the left is scanned; particles carry classified columns to the twin. */
export function TwinHero() {
  const rig = useRef<HTMLDivElement>(null);
  const reduced = usePrefersReducedMotion();

  useEffect(() => {
    const el = rig.current;
    if (!el || reduced) return;
    let raf = 0;
    const move = (e: PointerEvent) => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const dx = e.clientX / window.innerWidth - 0.5;
        const dy = e.clientY / window.innerHeight - 0.5;
        el.style.transform = `rotateX(${-dy * 8}deg) rotateY(${dx * 12}deg)`;
      });
    };
    window.addEventListener("pointermove", move, { passive: true });
    return () => {
      window.removeEventListener("pointermove", move);
      cancelAnimationFrame(raf);
    };
  }, [reduced]);

  const paths = [
    "path('M 150 250 C 230 160, 300 170, 380 140')",
    "path('M 170 290 C 250 230, 320 210, 400 190')",
    "path('M 130 210 C 220 120, 300 110, 370 100')",
    "path('M 190 260 C 260 220, 330 240, 410 170')",
    "path('M 160 230 C 250 180, 310 140, 395 120')",
  ];

  return (
    <div className="twin-scene" style={{ height: 440, maxWidth: 560, width: "100%", margin: "0 auto" }} role="img"
      aria-label="Illustration: a source database on the left is scanned layer by layer, and its columns appear on the right as a colour-coded digital twin.">
      <div ref={rig} className="twin-rig" style={{ width: "100%", height: "100%" }}>
        <Stack x={10} y={170} mirrored={false} label="Your estate" />
        <Stack x={290} y={70} mirrored label="The twin" />
      </div>
      {!reduced && (
        <div aria-hidden style={{ position: "absolute", inset: 0, pointerEvents: "none" }}>
          {paths.map((p, i) => (
            <span key={i} className="particle" style={{ offsetPath: p, animationDelay: `${i * 0.62}s`, ["--c" as string]: COLORS[i] } as React.CSSProperties} />
          ))}
        </div>
      )}
    </div>
  );
}
