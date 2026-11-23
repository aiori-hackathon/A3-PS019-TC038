import type { Metadata } from "next";
import { SitePage } from "@/components/site";

export const metadata: Metadata = { title: "About", description: "Why PrivacyTwin exists." };

export default function About() {
  return (
    <SitePage eyebrow="About" title="Built for the people who have to answer “where is our personal data?”"
      lede="PrivacyTwin was built for hackathon problem statement PS-019: personal-data discovery and privacy evidence inventory.">
      <div className="prose">
        <p>Privacy teams are asked to produce inventories of personal data, explain how they know, and keep the answer current as systems change. Spreadsheets go stale; scanners give verdicts without showing their work.</p>
        <p>PrivacyTwin takes a different approach. It treats the inventory as a <b>digital twin</b>: every scan is a snapshot you can rewind and compare. Every finding shows the signals behind it and starts as a candidate. People can review findings directly or enable AI auto-triage to automatically approve eligible high-confidence candidates. Every decision identifies its source and is chained into an audit log, and the whole state exports as verifiable evidence.</p>
        <h2>Principles</h2>
        <ul>
          <li><b>Evidence, not verdicts.</b> We never decide legality.</li>
          <li><b>Show the work.</b> Exact signal values, rule versions and published accuracy, including our errors.</li>
          <li><b>Never become the leak.</b> No raw values stored, read-only sources, fully offline.</li>
          <li><b>Respect people&apos;s time.</b> Real findings within ten seconds, keyboard-first review, undo instead of confirmation dialogs.</li>
        </ul>
        <p>All data in the demo and benchmark is synthetic. Any resemblance to real people is coincidental.</p>
      </div>
    </SitePage>
  );
}
