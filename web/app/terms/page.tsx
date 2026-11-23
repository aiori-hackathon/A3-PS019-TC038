import type { Metadata } from "next";
import { SitePage } from "@/components/site";

export const metadata: Metadata = { title: "Terms", description: "Terms of use for PrivacyTwin." };

export default function Terms() {
  return (
    <SitePage eyebrow="Terms" title="Terms of use">
      <div className="prose">
        <h2>Not legal advice</h2>
        <p>PrivacyTwin provides technical evidence for human review. It is not a legal determination and does not provide legal advice. Decisions about lawfulness, notification or remediation remain yours and your advisers&apos;.</p>
        <h2>Your data, your responsibility</h2>
        <p>Only scan data you are authorised to process. Prefer read-only credentials and exports with the minimum columns you need.</p>
        <h2>No warranty</h2>
        <p>The software is provided “as is”. Detection can miss personal data or flag data that is not personal; published accuracy figures come from a synthetic benchmark and may not reflect your data.</p>
        <h2>Demo deployment</h2>
        <p>The public demo runs on free infrastructure that may sleep, restart or be reset. Do not rely on it for storage; export your workspace if you need to keep it.</p>
      </div>
    </SitePage>
  );
}
