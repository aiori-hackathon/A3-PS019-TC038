"use client";

import { Background, Controls, MarkerType, ReactFlow, type Edge, type Node } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMemo } from "react";
import { CLASS_META } from "@/lib/classes";
import type { Cls } from "@/lib/types";

export type Lineage = {
  nodes: { id: string; table: string; source: string; personal: number; classes: Cls[]; rows: number; risk: number }[];
  edges: { id: string; source: string; target: string; shared: { a: string; b: string; via: string; overlap: number; class: string }[] }[];
  method: string;
};

/** Tables linked by shared personal or key-like columns. Click a node to simulate its blast radius. */
export default function LineageGraph({ data, onSelect }: { data: Lineage; onSelect: (id: string) => void }) {
  const { nodes, edges } = useMemo(() => {
    const n = data.nodes.length;
    const radius = Math.max(180, n * 42);
    const nodes: Node[] = data.nodes.map((t, i) => {
      const a = (2 * Math.PI * i) / n - Math.PI / 2;
      return {
        id: t.id,
        position: { x: radius + radius * Math.cos(a), y: radius * 0.75 + radius * 0.75 * Math.sin(a) },
        data: {
          label: (
            <div style={{ textAlign: "left", display: "grid", gap: 4 }}>
              <b style={{ fontFamily: "var(--mono)", fontSize: 12 }}>{t.table}</b>
              <span style={{ fontSize: 11, color: "var(--text-3)" }}>{t.personal} personal · {t.rows?.toLocaleString()} rows</span>
              <span style={{ display: "flex", gap: 3 }}>
                {t.classes.map((c) => <span key={c} title={CLASS_META[c].label} style={{ width: 10, height: 10, borderRadius: 3, background: CLASS_META[c].color }} />)}
              </span>
            </div>
          ),
        },
        style: {
          background: "var(--surface)", color: "var(--text)", border: `1px solid ${t.personal ? "var(--accent)" : "var(--border-strong)"}`,
          borderRadius: 12, padding: 10, width: 170, boxShadow: t.risk > 50 ? "0 0 0 4px color-mix(in srgb, var(--sev-high) 25%, transparent)" : "var(--shadow)",
        },
      };
    });
    const edges: Edge[] = data.edges.map((e) => {
      const fp = e.shared.some((s) => s.via !== "same name");
      return {
        id: e.id, source: e.source, target: e.target, animated: true,
        label: e.shared.slice(0, 2).map((s) => s.a).join(", ") + (e.shared.length > 2 ? ` +${e.shared.length - 2}` : ""),
        labelStyle: { fill: "var(--text-2)", fontSize: 11, fontFamily: "var(--mono)" },
        labelBgStyle: { fill: "var(--surface-2)" },
        style: { stroke: fp ? "var(--c-identity)" : "var(--accent)", strokeWidth: 1.5 + Math.min(3, e.shared.length), strokeDasharray: fp ? "6 4" : undefined },
        markerEnd: { type: MarkerType.ArrowClosed, color: "var(--accent)" },
      };
    });
    return { nodes, edges };
  }, [data]);

  return (
    <div style={{ height: 520, borderRadius: 12, border: "1px solid var(--border)", overflow: "hidden", background: "var(--bg-elev)" }}>
      <ReactFlow nodes={nodes} edges={edges} fitView proOptions={{ hideAttribution: true }} onNodeClick={(_, n) => onSelect(n.id)} nodesConnectable={false} colorMode="system">
        <Background color="var(--border)" gap={20} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
