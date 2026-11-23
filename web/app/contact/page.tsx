import type { Metadata } from "next";
import { SitePage } from "@/components/site";

export const metadata: Metadata = { title: "Contact", description: "How to reach the PrivacyTwin team." };

const REPO = "https://github.com/niveditapalanisamy/Privacy_Twin";

export default function Contact() {
  return (
    <SitePage eyebrow="Contact" title="Get in touch" lede="Questions, feedback or a bug? The fastest route is the project's issue tracker.">
      <div className="grid cols-2" style={{ maxWidth: 820 }}>
        <a className="card pad stack-sm" href={`${REPO}/issues/new`} rel="noopener noreferrer" style={{ color: "var(--text)" }}>
          <b>Open an issue</b>
          <span className="muted small">Bugs, feature ideas and questions. Please never include real personal data.</span>
        </a>
        <a className="card pad stack-sm" href={`${REPO}/blob/main/SECURITY.md`} rel="noopener noreferrer" style={{ color: "var(--text)" }}>
          <b>Report a security issue</b>
          <span className="muted small">Follow the responsible-disclosure steps in SECURITY.md.</span>
        </a>
      </div>
    </SitePage>
  );
}
