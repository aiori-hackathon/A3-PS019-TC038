import type { Metadata } from "next";
import { EvalReport } from "@/components/eval-report";
import { SitePage } from "@/components/site";
import results from "@/lib/eval-results.json";
import type { EvalResult } from "@/lib/types";

export const metadata: Metadata = { title: "Evaluation results", description: "Published precision, recall and F1 of PrivacyTwin's personal-data detection on a labelled synthetic benchmark." };

export default function PublicEvaluation() {
  const r = results as unknown as EvalResult | null;
  return (
    <SitePage eyebrow="Evaluation" title="Detection accuracy, published"
      lede="Measured on a synthetic labelled benchmark generated with Faker (en_IN) and custom generators. No real people. Every error is listed with the signals and a likely cause.">
      {r ? <EvalReport r={r} /> : <p className="muted">Run <code>python -m privacytwin.eval</code> to generate results.</p>}
      <div className="prose" style={{ marginTop: 32 }}>
        <h2>How the benchmark is built</h2>
        <ul>
          <li><b>{r?.columns ?? "250+"} labelled columns</b> in {r?.tables} tables across {r?.datasets.length} datasets: {r?.datasets.join(", ")}.</li>
          <li><b>Hard cases on purpose:</b> misleading headers (<code>col_7</code> holding emails), look-alike non-personal values (order IDs shaped like mobile numbers, 12-digit numbers failing Verhoeff, SKUs shaped like voter IDs, Luhn-valid IMEIs), transliterated headers (<code>naam</code>, <code>pata</code>, <code>janm_tithi</code>), mixed formats and 90–95% null columns.</li>
          <li><b>Ground truth</b> lives in <code>eval/labels.csv</code> (source, table, column, true class, note). The generator is <code>eval/generate.py</code>.</li>
          <li><b>Reproduce:</b> <code>python -m privacytwin.eval</code> prints this table and writes <code>eval/results.json</code>.</li>
        </ul>
        <h2>Honest limitations</h2>
        <p>{r?.caveat} Some errors are left in on purpose because they reflect real limits: masked Aadhaar values, a date of birth under a generic header, and IFSC codes in a branch table (a business object, not a person).</p>
      </div>
    </SitePage>
  );
}
