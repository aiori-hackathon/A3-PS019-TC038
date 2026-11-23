import type { Metadata } from "next";
import { SitePage } from "@/components/site";

export const metadata: Metadata = { title: "Privacy", description: "PrivacyTwin's own privacy notice." };

export default function Privacy() {
  return (
    <SitePage eyebrow="Privacy" title="Privacy notice" lede="How this deployment of PrivacyTwin treats information about you and the data you scan.">
      <div className="prose">
        <h2>No accounts, no tracking</h2>
        <p>There is no sign-up and no tracking. We set no cookies. Your browser stores a random workspace key and a few preferences (theme, last page, saved views) in local storage; clearing site data removes them.</p>
        <h2>Data you scan</h2>
        <p>Files and database tables are sampled and processed in memory. Raw values are discarded when the scan ends and are never written to the application database or logs. Stored: column names, aggregate statistics, rule IDs, masked examples and keyed fingerprints, plus the metadata, reviews and notes you enter. Each scan&apos;s data-handling receipt lists exactly what was kept.</p>
        <h2>Notes and metadata you type</h2>
        <p>Review notes, declared purposes and similar free text are stored as you write them. Please don&apos;t paste personal data into them.</p>
        <h2>Deleting your data</h2>
        <p>Use <b>Evidence pack → Wipe workspace</b> to permanently delete everything in your workspace. The page confirms what was deleted.</p>
        <h2>Third parties</h2>
        <p>None by default. If an operator configures the optional help-assistant LLM endpoint, it receives table and column names, candidate classes and gap counts only, and the assistant panel says so.</p>
      </div>
    </SitePage>
  );
}
