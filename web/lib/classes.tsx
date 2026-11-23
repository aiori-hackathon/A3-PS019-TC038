import { AtSign, CircleSlash, CreditCard, IdCard, Info, MapPin, OctagonAlert, TriangleAlert, UserRound } from "lucide-react";
import type { ComponentType } from "react";
import type { Cls, Severity, Status } from "./types";

export const CLASSES: Cls[] = ["IDENTITY", "CONTACT", "GOVERNMENT_ID", "FINANCIAL", "LOCATION"];
export const ALL_CLASSES: Cls[] = [...CLASSES, "NOT_PERSONAL"];

export const CLASS_META: Record<Cls, { label: string; short: string; color: string; Icon: ComponentType<{ size?: number; "aria-hidden"?: boolean }>; blurb: string }> = {
  IDENTITY: { label: "Identity", short: "ID", color: "var(--c-identity)", Icon: UserRound, blurb: "Names, date of birth, age, gender" },
  CONTACT: { label: "Contact", short: "CT", color: "var(--c-contact)", Icon: AtSign, blurb: "Email addresses and phone numbers" },
  GOVERNMENT_ID: { label: "Government ID", short: "GOV", color: "var(--c-government)", Icon: IdCard, blurb: "Aadhaar, PAN, passport, voter ID, licence, GSTIN" },
  FINANCIAL: { label: "Financial", short: "FIN", color: "var(--c-financial)", Icon: CreditCard, blurb: "Cards, bank accounts, IFSC, UPI IDs" },
  LOCATION: { label: "Location", short: "LOC", color: "var(--c-location)", Icon: MapPin, blurb: "Addresses, PIN codes, cities, coordinates, IPs" },
  NOT_PERSONAL: { label: "Not personal", short: "—", color: "var(--c-none)", Icon: CircleSlash, blurb: "No rule reached its threshold" },
};

export const SEVERITY_META: Record<Severity, { Icon: ComponentType<{ size?: number; "aria-hidden"?: boolean }>; order: number }> = {
  High: { Icon: OctagonAlert, order: 3 },
  Medium: { Icon: TriangleAlert, order: 2 },
  Low: { Icon: Info, order: 1 },
};

export const STATUS_META: Record<Status, { label: string; color: string }> = {
  candidate: { label: "Candidate", color: "var(--text-2)" },
  confirmed: { label: "Confirmed", color: "var(--ok)" },
  rejected: { label: "Rejected", color: "var(--text-3)" },
  needs_info: { label: "Needs info", color: "var(--sev-medium)" },
};

export function ClassChip({ cls, compact = false }: { cls: Cls; compact?: boolean }) {
  const m = CLASS_META[cls] ?? CLASS_META.NOT_PERSONAL;
  return (
    <span className="chip" style={{ ["--chip" as string]: m.color }} title={m.blurb}>
      <m.Icon aria-hidden />
      {compact ? m.short : m.label}
    </span>
  );
}

export function SeverityBadge({ sev }: { sev: Severity }) {
  const m = SEVERITY_META[sev];
  return (
    <span className={`sev ${sev}`}>
      <m.Icon aria-hidden />
      {sev}
    </span>
  );
}

export function StatusLabel({ status }: { status: Status }) {
  const m = STATUS_META[status];
  return (
    <span className="status" style={{ color: m.color }}>
      <span className="dot" aria-hidden />
      {m.label}
    </span>
  );
}

export function BandLabel({ band, score }: { band: string; score?: number }) {
  if (band === "NONE") return <span className="faint small">—</span>;
  const color = band === "HIGH" ? "var(--text)" : band === "MEDIUM" ? "var(--text-2)" : "var(--text-3)";
  return (
    <span className="num" style={{ color, fontWeight: 600, fontSize: 12.5 }}>
      {band[0] + band.slice(1).toLowerCase()}
      {score !== undefined && <span className="faint" style={{ fontWeight: 400 }}> · {score.toFixed(2)}</span>}
    </span>
  );
}
