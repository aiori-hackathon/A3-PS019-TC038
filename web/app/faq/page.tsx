import type { Metadata } from "next";
import { SitePage } from "@/components/site";

export const metadata: Metadata = { title: "FAQ", description: "Frequently asked questions about PrivacyTwin." };

const QA: [string, string][] = [
  ["Does PrivacyTwin tell me whether my processing is lawful?", "No. It produces technical evidence (candidates, confidence, signals, declared metadata and gaps) for people to review. Legal conclusions need context a scanner cannot see. Every page and export says so."],
  ["Do you store my data?", "No raw values. Sources are sampled in memory and the values are discarded when the scan ends. We store counts, ratios, rule IDs, masked examples and keyed fingerprints. An automated test checks the database and every export for raw values."],
  ["Does anything leave my machine?", "No. PrivacyTwin makes no external calls. The optional help-assistant LLM endpoint is off by default; if you configure one, it receives metadata only and the UI shows that clearly."],
  ["How accurate is detection?", "On our synthetic labelled benchmark, macro F1 is published on the Evaluation page with every error explained. It is synthetic data, so treat it as evidence of how the rules behave, not a guarantee on your data. Use “Run on my data” to measure on your own columns."],
  ["Which identifiers are supported?", "Email, Indian mobile, Aadhaar (Verhoeff), PAN, passport, voter ID (EPIC), driving licence, GSTIN (checksum), IFSC, bank account, card numbers (Luhn plus issuer prefixes), UPI ID, PIN code, coordinates, IP addresses, date of birth, age, gender, names, addresses, cities and states."],
  ["Which sources can I scan?", "CSV (up to 20 MB) and SQLite (up to 50 MB) uploads, plus PostgreSQL with a read-only user. MySQL and SQL Server are not supported in this build; use a CSV export."],
  ["How do I see changes over time?", "Drop the same file (same name) again. Each scan becomes a snapshot; the Time Machine diffs any two and raises drift alerts."],
  ["Why do I need a note to reject a finding?", "Rejections and reclassifications change what the evidence says, so the reason goes into the hash-chained audit log for whoever reviews it later."],
  ["Is there a login?", "No. Your browser holds a random workspace key. Export the workspace to move it to another device; wipe it to delete everything."],
  ["Can I customise the rules?", "Yes. The Rule Playground lets you edit and test rules, preview their impact and save new versions. Rule sets import and export as YAML or JSON."],
];

export default function Faq() {
  return (
    <SitePage eyebrow="FAQ" title="Frequently asked questions">
      <div className="stack" style={{ maxWidth: 820 }}>
        {QA.map(([q, a]) => (
          <details key={q} className="card pad">
            <summary style={{ cursor: "pointer", fontWeight: 600, fontSize: 15.5 }}>{q}</summary>
            <p className="muted" style={{ marginTop: 10, lineHeight: 1.65 }}>{a}</p>
          </details>
        ))}
      </div>
    </SitePage>
  );
}
