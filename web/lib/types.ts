export type Cls = "IDENTITY" | "CONTACT" | "GOVERNMENT_ID" | "FINANCIAL" | "LOCATION" | "NOT_PERSONAL";
export type Status = "candidate" | "confirmed" | "rejected" | "needs_info";
export type Severity = "High" | "Medium" | "Low";

export type Signals = { header: number; value: number; validator: number; embedded: number };
export type MetaField = { value: string; origin: "column" | "table" | null };
export type Meta = {
  purpose: MetaField; retention: MetaField; owner: MetaField; legal_basis: MetaField; system_of_record: MetaField;
  retention_days: number | null;
};
export type Gap = { field: string; severity: Severity; message: string };

export type Finding = {
  pt_id: string; key: string; source_id: string; source: string; table: string; column: string;
  class: Cls; detected_class: Cls; confidence: number; band: "HIGH" | "MEDIUM" | "LOW" | "NONE";
  rule_id: string | null; rule_name: string | null; rule_version: string; signals: Signals; validator: string | null;
  header_keyword: string | null; negative_keywords: string[]; notes: string[];
  alternatives: { rule_id: string; class: Cls; score: number }[]; masked_examples: string[]; rationale: string;
  profile: { sample_size: number; non_null: number; null_pct: number; distinct_pct: number; min_len: number; max_len: number; inferred_type: string; total_rows: number };
  quasi_identifier: string | null; status: Status; review_note: string; reviewed_by: string | null; reviewed_at: string | null;
  decision_source?: "human" | "ai" | null; automation_batch?: string | null;
  meta: Meta; gaps: Gap[]; max_gap: Severity | null; documented: boolean | null; personal: boolean; risk: number;
  scan_id: string; scan_seq: number;
};

export type Kpis = { sources: number; columns: number; candidates: number; confirmed: number; open_gaps: number; reviewed_pct: number; posture: number | null };
export type NextAction = { text: string; action: string; label: string; count?: number };
export type Posture = { score: number | null; components: Record<string, number>; formula: string; label: string };
export type Drift = { scan_seq: number; at: string; pt_id: string; key: string; column: string; class: Cls; severity: Severity; message: string };

export type Overview = {
  kpis: Kpis; previous: Kpis | null; by_class: Record<string, number>; gaps_by_severity: Record<Severity, number>;
  heatmap: { key: string; table: string; source: string; counts: Record<string, number>; unique_pct: number | null }[];
  top_tables: { key: string; table: string; risk: number; personal: number; rows: number }[];
  posture: Posture; next_action: NextAction; scan_seq: number | null; drift: Drift[];
};

export type ScanInfo = {
  id: string; seq: number; source_id: string; created_at: string; ruleset_version: string; ruleset_hash: string;
  sample_size: number; strategy: string; source_name: string; stats: { tables: number; columns: number; personal: number; by_class: Record<string, number> };
};

export type Rule = {
  id: string; name: string; class: Cls; header_keywords: string[]; header_exclude: string[]; value_regex: string;
  validator: string; normalise: string; threshold: number; weight: number; requires_header: boolean; embedded: boolean; enabled: boolean;
};
export type RuleSet = {
  name: string; version: string; hash?: string; signal_weights: { header: number; value: number; validator: number };
  bands: { high: number; medium: number }; negative_penalty: number; negative_keywords: string[]; rules: Rule[];
};

export type ClassMetrics = { precision: number; recall: number; f1: number; support: number; tp: number; fp: number; fn: number };
export type EvalResult = {
  benchmark: string; generated_at: string; ruleset_version: string; ruleset_hash: string; datasets: string[]; tables: number; columns: number;
  per_class: Record<string, ClassMetrics>; macro: { precision: number; recall: number; f1: number }; micro: { precision: number; recall: number; f1: number };
  accuracy: number; not_personal: { support: number; correct: number; specificity: number | null };
  confusion: Record<string, Record<string, number>>; labels: string[];
  errors: { kind: string; source: string; table: string; column: string; true_class: Cls; predicted: Cls; confidence: number; rule_id: string | null; signals: Signals; note: string; masked_examples: string[]; likely_cause: string }[];
  ablation: { variant: string; label: string; macro_f1: number; micro_f1: number; macro_precision: number; macro_recall: number; accuracy: number }[];
  per_dataset: Record<string, { precision: number; recall: number; f1: number; columns: number; accuracy: number }>;
  disclaimer: string; caveat: string;
};

export type AuditEntry = { seq: number; ts: string; actor: string; action: string; target: string; payload: Record<string, unknown>; prev_hash: string; hash: string };
