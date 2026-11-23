import type { Metadata } from "next";
import Link from "next/link";
import { SitePage } from "@/components/site";

export const metadata: Metadata = { title: "Documentation", description: "How PrivacyTwin works: detection, rules, metadata gaps, review, Time Machine, simulations, evaluation and evidence packs." };

const TOC = [["overview", "Overview"], ["quickstart", "Quick start"], ["detection", "Detection & confidence"], ["rules", "Rules"], ["metadata", "Metadata & gaps"], ["review", "Review & audit"], ["time-machine", "Time Machine"], ["simulations", "Simulations"], ["posture", "Posture indicator"], ["evidence", "Evidence pack"], ["keyboard", "Keyboard"], ["legality", "Why we don't decide legality"], ["api", "Self-hosting & API"]];

export default function Docs() {
  return (
    <SitePage eyebrow="Documentation" title="How PrivacyTwin works" lede="Everything in one page. Use the contents to jump.">
      <div className="grid" style={{ gridTemplateColumns: "220px minmax(0, 1fr)", alignItems: "start", gap: 40 }}>
        <nav aria-label="Contents" className="card pad stack-sm" style={{ position: "sticky", top: 88 }}>
          {TOC.map(([id, t]) => <a key={id} href={`#${id}`} className="small">{t}</a>)}
        </nav>
        <article className="prose">
          <h2 id="overview">Overview</h2>
          <p>PrivacyTwin is a digital twin of an organisation&apos;s personal-data estate. Each scan creates a snapshot. You can <b>discover</b> where personal data lives, <b>rewind</b> the twin over time, <b>simulate</b> what-if scenarios, <b>prove</b> detection accuracy and <b>export</b> tamper-evident evidence.</p>

          <h2 id="quickstart">Quick start</h2>
          <ol>
            <li>Click <Link href="/app/overview/?demo=1">Try live demo</Link>, or drop a CSV/SQLite file anywhere in the app.</li>
            <li>Follow the <b>Next</b> bar at the top. It always shows the most useful next step.</li>
            <li>Review candidates (<kbd>C</kbd> confirm, <kbd>R</kbd> reject), declare metadata, then export the evidence pack.</li>
          </ol>

          <h2 id="detection">Detection & confidence</h2>
          <p>Classes: <b>Identity</b>, <b>Contact</b>, <b>Government ID</b>, <b>Financial</b>, <b>Location</b>; everything else is <b>Not personal</b>. Each rule measures three signals per column:</p>
          <ul>
            <li><b>Header</b>: whether the normalised name (snake, camel, abbreviations such as <code>mob</code>, <code>dob</code>, <code>cust_nm</code>, and transliterations such as <code>naam</code>, <code>pata</code>) matches a keyword.</li>
            <li><b>Value</b>: the share of sampled non-null values that match the class pattern.</li>
            <li><b>Validator</b>: the share that pass a real check: Verhoeff (Aadhaar), Luhn with issuer prefixes (cards), the GSTIN checksum, PAN structure, passport, EPIC, driving licence, IFSC, UPI handle, PIN region, coordinates, IP addresses and plausible birth dates.</li>
          </ul>
          <pre>score = weight × (0.35 × header + 0.30 × value + 0.35 × validator){"\n"}HIGH ≥ 0.75 · MEDIUM ≥ 0.55 · LOW ≥ rule threshold (0.35)</pre>
          <p>Negative rules cut false positives: names containing <code>order</code>, <code>invoice</code>, <code>sku</code>, <code>txn</code>, <code>ref</code> or timestamps reduce the score unless a checksum passes for 90% of values; values sharing one prefix (ACC1234567) are treated as system codes. Some rules (PIN code, bank account, date of birth, age) need header support because their shapes are too common. Each finding stores a stable ID (PT-00001…), the rule ID and rule-set version, the signal values, masked examples and a rationale ending with “Raw values were not retained.”</p>

          <h2 id="rules">Rules</h2>
          <p>The default rule set ships as documented YAML (<code>privacytwin/default_rules.yaml</code>). In the Rule Playground you can edit keywords, patterns, validators, thresholds and weights, test against sample strings live, and preview how many findings in the current scan would change. Saving creates a new semantic version with a content hash; every scan records which version and hash it used. Impact previews re-score stored aggregate signals; if you change a pattern or validator, results are marked approximate until the next scan.</p>

          <h2 id="metadata">Metadata & gaps</h2>
          <p>Declare purpose, retention, owner, legal basis (free text you declare) and system of record per table, or override per column. Gap severity: no purpose or no retention = <b>High</b>; no owner or no legal basis = <b>Medium</b>; retention longer than the workspace maximum = <b>Low</b> (for review). Suggestions are labelled and never stored until accepted. Templates are available in CSV and YAML.</p>

          <h2 id="review">Review & audit</h2>
          <p>The queue is sorted by risk = confidence × class sensitivity × gap severity. Actions: Confirm, Reject, Reclassify, Needs info. A note is required to reject or reclassify. Every action is appended to a SHA-256 hash chain (<code>hash = SHA-256(previous hash + entry)</code>); <b>Verify integrity</b> recomputes it and highlights the first broken link. Human decisions feed a human-confirmed precision metric.</p>
          <p><b>AI auto-triage</b> is off by default. Enable Auto-approve in Sources or Review queue to review existing untouched HIGH-confidence candidates and automatically review new ones after scans. Type a minimum detection confidence between 90 and 100% (default 95; decimals such as 92.5 are allowed). The configured AI must explicitly approve each candidate from metadata; missing AI, invalid responses and abstentions leave it unchanged. Each run considers up to 200 candidates. AI approvals show their reasons and are excluded from human-confirmed precision. Undo latest AI batch restores candidates to manual review without overwriting later human decisions. Turning the toggle off stops further approvals; existing approvals remain until undone. No metadata is automatically declared.</p>
          <h3 id="audit">Undo</h3>
          <p>Reversible actions never ask for confirmation; a 5-second <b>Undo</b> toast appears instead. Undo is itself an audit entry, so history is never rewritten.</p>

          <h2 id="time-machine">Time Machine</h2>
          <p>Rescanning a source (drop the same file name again) creates a new snapshot. Pick any two scans to see new and removed personal-data columns, class and confidence changes, and metadata gaps opened or closed, evaluated with the metadata as it was at each scan. Drift alerts flag new personal data, for example “support_tickets.aadhaar_no appeared in scan #3 with no declared purpose”.</p>

          <h2 id="simulations">Simulations</h2>
          <ul>
            <li><b>Blast radius</b>: exposed classes, column and record counts, identifier combinations made possible (e.g. name + date of birth + PIN code) and tables linked by shared identifiers. Technical exposure only.</li>
            <li><b>Re-identification</b>: quasi-identifiers (date of birth, age, gender, PIN code, city, job title) are grouped on the in-memory sample to estimate k-anonymity; only minimum k and % unique rows are stored.</li>
            <li><b>Retention what-if</b>: applies declared or hypothetical retention to the record-age histogram and lists fields that would never be cleaned up.</li>
            <li><b>Lineage</b>: tables linked by the same normalised column name or by overlapping keyed fingerprints, never raw values.</li>
          </ul>

          <h2 id="posture">Posture indicator</h2>
          <pre>score = 100 × (0.35 × metadata coverage + 0.25 × review completion{"\n"}             + 0.25 × (1 − gap severity index) + 0.15 × (1 − re-identification risk))</pre>
          <p>A technical posture indicator, not a compliance rating.</p>

          <h2 id="evidence">Evidence pack</h2>
          <p>One click builds a ZIP with inventory (CSV and JSON), gaps, reviews, the audit chain, the latest scan diff, drift, evaluation, the rule set, data-handling receipts, a printable summary and <code>manifest.json</code> (SHA-256 of every file plus scan metadata). The manifest&apos;s own hash goes into the audit chain. <b>Verify pack</b> recomputes every hash and reports pass or fail per file.</p>

          <h2 id="keyboard">Keyboard</h2>
          <p><kbd>Ctrl/⌘ K</kbd> command palette · <kbd>?</kbd> all shortcuts · <kbd>G</kbd> then <kbd>S</kbd>/<kbd>I</kbd>/<kbd>R</kbd>/<kbd>M</kbd>/<kbd>T</kbd>/<kbd>E</kbd> for Sources, Inventory, Review, Metadata, Time Machine, Evaluation · in review: <kbd>J</kbd>/<kbd>K</kbd>, <kbd>C</kbd>, <kbd>R</kbd>, <kbd>E</kbd>, <kbd>N</kbd>, <kbd>Z</kbd>.</p>

          <h2 id="legality">Why we don&apos;t decide legality</h2>
          <p>Whether processing personal data is lawful depends on purpose, consent, contracts, notices, sector rules and context that no scanner can see. A column that looks like an Aadhaar number may be test data; a perfectly valid PAN may belong to a company. So PrivacyTwin never issues legal verdicts or legal labels of any kind. It produces <b>technical evidence</b> (what was found, how confident we are and why, what is declared and what is missing) for people and counsel to judge. Every page and export carries the same line: <i>Technical evidence for human review. Not a legal determination.</i></p>

          <h2 id="api">Self-hosting & API</h2>
          <pre>pip install -r requirements.txt{"\n"}uvicorn privacytwin.api:app --port 8000{"\n"}cd web && npm ci && npm run dev</pre>
          <p>The backend exposes <code>/health</code> for keep-alive pings. See the README for deployment to Render (API) and Vercel (static frontend).</p>
        </article>
      </div>
      <style>{`@media (max-width: 860px){ main .grid[style*="220px"]{grid-template-columns:minmax(0,1fr) !important} main nav[aria-label="Contents"]{position:static !important} }`}</style>
    </SitePage>
  );
}
