import { Activity, ClipboardCheck, Database, FileCheck2, FlaskConical, History, LayoutDashboard, ListChecks, Radar, ScrollText, SlidersHorizontal, Table2 } from "lucide-react";

export type NavItem = { key: string; href: string; label: string; Icon: typeof LayoutDashboard; g: string };

export const NAV: { group: string; items: NavItem[] }[] = [
  {
    group: "Scan",
    items: [
      { key: "overview", href: "/app/overview/", label: "Overview", Icon: LayoutDashboard, g: "o" },
      { key: "sources", href: "/app/sources/", label: "Sources", Icon: Database, g: "s" },
      { key: "inventory", href: "/app/inventory/", label: "Inventory", Icon: Table2, g: "i" },
    ],
  },
  {
    group: "Review",
    items: [
      { key: "review", href: "/app/review/", label: "Review queue", Icon: ListChecks, g: "r" },
      { key: "metadata", href: "/app/metadata/", label: "Metadata & gaps", Icon: ClipboardCheck, g: "m" },
      { key: "rules", href: "/app/rules/", label: "Rules", Icon: SlidersHorizontal, g: "u" },
    ],
  },
  {
    group: "Prove",
    items: [
      { key: "time-machine", href: "/app/time-machine/", label: "Time Machine", Icon: History, g: "t" },
      { key: "simulator", href: "/app/simulator/", label: "Simulator", Icon: Radar, g: "x" },
      { key: "evaluation", href: "/app/evaluation/", label: "Evaluation", Icon: FlaskConical, g: "e" },
      { key: "evidence", href: "/app/evidence/", label: "Evidence pack", Icon: FileCheck2, g: "p" },
      { key: "audit", href: "/app/audit/", label: "Audit log", Icon: ScrollText, g: "a" },
    ],
  },
];

export const ALL_NAV: NavItem[] = NAV.flatMap((g) => g.items);
export const MOBILE_TABS = ["overview", "inventory", "review", "time-machine"] as const;
export const ActivityIcon = Activity;
