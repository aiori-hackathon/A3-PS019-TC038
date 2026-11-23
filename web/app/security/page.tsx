import type { Metadata } from "next";
import { SitePage } from "@/components/site";

export const metadata: Metadata = { title: "Security", description: "How PrivacyTwin handles data: read-only sources, in-memory sampling, no raw values stored, CSRF, isolation and a hash-chained audit log." };

const ROWS: [string, string][] = [
  ["Read-only sources", "SQLite is opened with file:…?mode=ro and PRAGMA query_only; before scanning, a write probe inside a rolled-back transaction must be refused. PostgreSQL runs in a read-only transaction, and we warn if the user has write privileges."],
  ["Bounded, in-memory sampling", "Each table is sampled (500, 1,000 or 5,000 rows; head, random or stratified) and processed in memory. Uploaded SQLite files use a private temporary copy that is deleted as soon as the read ends."],
  ["No raw values stored", "Only schema metadata, counts, ratios, rule IDs, masked examples (ra****@gmail.com, XXXX-XXXX-1234) and keyed MinHash fingerprints are persisted. An automated test scans the database and every export for raw sample values and fails if it finds any."],
  ["Keyed fingerprints", "Lineage compares 32 truncated keyed hashes per column (HMAC with a server-side pepper and a per-workspace salt). They estimate overlap between columns; they cannot be used to list values."],
  ["Workspace isolation", "No login. Your browser creates a random 256-bit workspace key; the server only sees its SHA-256, which scopes every query."],
  ["CSRF and origin checks", "Every write needs an HMAC token bound to your workspace and the page origin. Requests from other origins are refused; CORS is locked to the frontend."],
  ["Hardening", "Rate limits per client, upload type and size validation, quoted identifiers (no SQL injection), formula-injection guards in CSV exports, user regexes run with a timeout, and security headers (CSP, nosniff, no-referrer, frame denial) on every response. Errors never include stack traces."],
  ["Tamper evidence", "Reviews, metadata, rules, scans and exports are appended to a SHA-256 hash chain. The evidence pack carries a manifest of file hashes; its own hash is written to the audit chain."],
  ["AI (Groq LLM)", "When a Groq key is configured, the AI analyst, Ask AI and Explain with AI send workspace metadata only (table and column names, classes, signal scores, gaps). Raw values and masked examples never leave the server. Without a key everything runs offline."],
];

export default function SecurityPage() {
  return (
    <SitePage eyebrow="Security" title="Designed so your personal data never becomes our data" lede="PrivacyTwin produces evidence about personal data without keeping the personal data itself.">
      <div className="card" style={{ overflowX: "auto" }}>
        <table className="table">
          <tbody>
            {ROWS.map(([k, v]) => (
              <tr key={k}><td style={{ width: 240, verticalAlign: "top" }}><b>{k}</b></td><td className="muted">{v}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="prose" style={{ marginTop: 32 }}>
        <h2>Data-handling receipt</h2>
        <p>Every scan writes a receipt: rows sampled per table, strategy, that processing happened in memory, when values were discarded, and exactly which fields were persisted. Find it on the Sources page and inside every evidence pack.</p>
        <h2>Reporting a vulnerability</h2>
        <p>See <code>SECURITY.md</code> in the repository. Please do not include real personal data in reports.</p>
      </div>
    </SitePage>
  );
}
