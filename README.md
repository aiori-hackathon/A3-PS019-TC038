# PrivacyTwin 🔐
### Evidence-Based Personal Data Discovery and Privacy Review

**AIORI Hackathon 3 | Challenge PS-019: Personal-Data Discovery and Privacy Evidence Inventory**

## 1. Overview

PrivacyTwin is a proposed platform that helps identify potential personal data in CSV files and SQLite databases. Instead of simply classifying a field, it provides supporting evidence, highlights conflicting signals, and helps reviewers understand why a field may contain personal information.

The platform combines deterministic detection rules, data validation, evidence analysis, and AI-assisted explanations using Google Gemini. It also includes **ReviewGuard**, which tracks human review decisions and identifies when a previous decision may need to be revisited after relevant changes.

The goal is to make personal-data discovery more transparent, traceable, and efficient while keeping humans involved in important decisions.

## 2. Problem Statement

Identifying personal information in real-world datasets can be challenging for several reasons:

- Column names may be unclear, misleading, or specific to a business domain.
- Pattern-based rules may incorrectly identify business identifiers as personal identifiers.
- A single classification or confidence score may hide conflicting evidence.
- Previously approved classifications may become outdated when data, rules, or metadata change.
- Repeating the entire review process after every change consumes time and effort.
- Missing information about data purpose, retention, or ownership can make privacy reviews incomplete.

PrivacyTwin addresses these challenges by connecting detection results with evidence, review history, and change tracking.

## 3. Objectives

- Discover potential personal-data fields in structured datasets.
- Combine multiple detection signals instead of relying on a single rule.
- Preserve supporting and contradicting evidence.
- Use AI to explain ambiguous fields and provide contextual suggestions.
- Maintain versioned human review decisions.
- Identify decisions affected by relevant changes.
- Highlight missing metadata, including purpose, retention, and ownership.
- Generate reviewable reports and field-level evidence summaries.
- Minimise the exposure of sensitive data during AI-assisted analysis.

## 4. Key Features

### 4.1 Personal Data Discovery

Analyse CSV files and SQLite data sources to identify fields that may contain personal information.

The proposed classification categories are:

- Identity
- Contact
- Location
- Government or Official ID
- Demographic Information

### 4.2 Evidence Collection and Fusion

Collect evidence from column names, data characteristics, configured rules, validators, and metadata.

Combine the collected signals to produce candidate classifications while preserving conflicting evidence and ambiguity.

### 4.3 AI-Assisted Explanation

Use Google Gemini to help interpret ambiguous fields and explain possible classifications.

AI-generated suggestions are validated before being used. The system does not treat an LLM response as unquestionable evidence or as a final legal decision.

### 4.4 ReviewGuard

ReviewGuard tracks human review decisions and their dependencies.

When relevant data, rules, or metadata change, the system checks whether an earlier decision may have become outdated. It marks affected reviews for reconsideration rather than requiring every field to be reviewed again.

### 4.5 Metadata Checklist and Fix Preview

Identify missing metadata such as:

- Data purpose
- Retention information
- Data owner

The Fix Preview feature displays proposed metadata updates before they are saved. Changes require explicit user confirmation.

### 4.6 Reports and Exports

The proposed outputs include:

- Field-level Evidence Passport
- Personal-data inventory
- Human review history
- Metadata gap checklist
- `gap_report.csv`

## 5. System Architecture

The proposed architecture uses a modular Python application with a Streamlit interface, SQLite persistence, and an optional Gemini API integration.

```text
                  CSV / SQLite Sources
                           |
                           v
                  Data Profiler
                           |
                           v
              Deterministic Detectors
                           |
                           v
               Evidence Fusion Layer
                           |
                 +---------+---------+
                 |                   |
                 v                   v
          Gemini Assistance    Conflict Analysis
                 |                   |
                 +---------+---------+
                           |
                           v
                Field Evidence Case
                           |
              +------------+------------+
              |                         |
              v                         v
         ReviewGuard             Metadata Checklist
              |                         |
              v                         v
       Review State Tracking       Fix Preview
              |                         |
              +------------+------------+
                           |
                           v
                    Streamlit UI
                           |
                           v
            Evidence Passport / Inventory /
               Review History / Gap Report
```

## 6. Technology Stack

| Component | Technology |
|---|---|
| Programming language | Python |
| User interface | Streamlit |
| Local persistence | SQLite |
| Input sources | CSV and SQLite |
| AI-assisted explanation | Google Gemini API |
| Detection | Deterministic rules and validators |
| Review tracking | ReviewGuard |
| Output formats | CSV and reviewable application reports |

*This table describes the proposed implementation stack; individual components may depend on the final implementation.*

## 7. Data Flow

1. **Select source:** The user selects a CSV file or SQLite source.
2. **Profile data:** The system examines field names, schema, and data characteristics.
3. **Collect signals:** Detection rules and validators analyse candidate fields.
4. **Combine evidence:** The system combines supporting and contradicting signals.
5. **Explain ambiguity:** Gemini may provide contextual interpretations for unclear cases.
6. **Create evidence cases:** Candidate classifications, evidence references, scores, and ambiguity are recorded.
7. **Check review freshness:** ReviewGuard checks whether relevant dependencies have changed.
8. **Review metadata:** The system identifies missing metadata and presents proposed changes.
9. **Generate outputs:** Reviewers inspect the results and generate inventory and gap reports.

## 8. Privacy and Security Considerations

PrivacyTwin is designed to minimise unnecessary exposure of sensitive information.

- Prefer synthetic data for development and testing.
- Mask sensitive examples where possible.
- Send only the minimum necessary context to Gemini.
- Do not send complete datasets to the external model by default.
- Store API credentials in environment variables.
- Require explicit user confirmation before saving proposed metadata changes.
- Keep AI-generated suggestions separate from deterministic review-state decisions.

PrivacyTwin provides technical evidence to support human review. It does not independently determine legal compliance or establish a lawful basis for processing personal data.

## 9. Implementation Timeline

**Planned development period: 16 October – 31 October 2026**

| Phase | Focus Area | Planned Activities |
|---|---|---|
| Phase 1 | Foundation | Repository setup, CSV/SQLite processing, profiling, synthetic test data |
| Phase 2 | Detection | Rules, validators, grouped evidence, contradiction handling |
| Phase 3 | ReviewGuard | Review contracts, fingerprints, dependency comparison, stale-review reasons |
| Phase 4 | Metadata and UI | Checklist, Fix Preview, Evidence Passport, review history, exports |
| Phase 5 | Evaluation and Demo | Testing, change scenarios, evaluation, final demonstration |

The timeline is a plan for the implementation, not a claim that all features have already been completed.

## 10. Evaluation Plan

The system should be evaluated using representative test datasets and scenarios, including:

- Correct identification of personal-data fields.
- False positives involving business identifiers.
- Fields with mixed or ambiguous values.
- Cases with supporting and contradicting evidence.
- Changes to data, detection rules, and metadata.
- Correct identification of reviews that have become stale.
- Preservation of unaffected review decisions.
- Validation of AI-generated evidence references.
- Correct generation of inventory and metadata gap reports.

Evaluation should measure detection quality, false-positive behaviour, review-state correctness, and the reliability of exported results.

## 11. Expected Outcomes

PrivacyTwin aims to provide:

- A more explainable personal-data discovery process.
- Better visibility into uncertain or conflicting classifications.
- Traceable human review decisions.
- Selective reopening of reviews when relevant dependencies change.
- Faster identification of missing metadata.
- More structured evidence for privacy assessments.

The expected benefit is reduced unnecessary review effort without losing transparency or review integrity.

## 12. Future Enhancements

Potential future improvements include:

- Support for additional structured data sources.
- Configurable detection policies and validation rules.
- Expanded evaluation datasets and benchmark comparisons.
- More detailed dependency tracking.
- Improved evidence visualisation and reporting.
- Integration with enterprise metadata catalogues and data governance workflows.

## 13. Team

**Team Members:** 2

**Mentor:** 1

The team will collaborate on solution design, implementation, testing, and evaluation, with mentor guidance on technical decisions and overall solution quality.

## 14. Acknowledgement

Developed as a proposed solution for **AIORI Hackathon 3 – PS-019: Personal-Data Discovery and Privacy Evidence Inventory**.

**Project:** PrivacyTwin  
**Core idea:** Discover potential personal data, explain the evidence, preserve human decisions, and revisit only the decisions affected by relevant changes.
