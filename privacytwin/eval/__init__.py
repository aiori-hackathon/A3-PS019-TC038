"""Self-evaluation on the synthetic labelled benchmark in eval/.

Run: python -m privacytwin.eval
"""
from __future__ import annotations

import csv
import io
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .. import DISCLAIMER
from ..detect import classify_column, normalise_header, score_rule
from ..ingest import read_csv, read_sqlite_path
from ..rules import ALL_CLASSES, CLASSES, NOT_PERSONAL, content_hash, default_ruleset

ROOT = Path(__file__).resolve().parents[2] / "eval"
VARIANTS = [
    ("header_only", "Header only", (True, False, False)),
    ("header_value", "Header + value", (True, True, False)),
    ("all_signals", "Header + value + validator", (True, True, True)),
    ("value_validator", "Value + validator (no header)", (False, True, True)),
]


def metrics(pairs: list[tuple[str, str]]) -> dict:
    """pairs = [(true_class, predicted_class)]. Macro over the five personal classes."""
    per = {}
    for cls in CLASSES:
        tp = sum(1 for t, p in pairs if t == cls and p == cls)
        fp = sum(1 for t, p in pairs if t != cls and p == cls)
        fn = sum(1 for t, p in pairs if t == cls and p != cls)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        per[cls] = {"precision": round(prec, 4), "recall": round(rec, 4), "f1": round(f1, 4), "support": tp + fn,
                    "tp": tp, "fp": fp, "fn": fn}
    supported = [c for c in CLASSES if per[c]["support"]]
    macro = {k: round(sum(per[c][k] for c in supported) / len(supported), 4) if supported else 0.0
             for k in ("precision", "recall", "f1")}
    tp = sum(per[c]["tp"] for c in CLASSES)
    fp = sum(per[c]["fp"] for c in CLASSES)
    fn = sum(per[c]["fn"] for c in CLASSES)
    mp = tp / (tp + fp) if tp + fp else 0.0
    mr = tp / (tp + fn) if tp + fn else 0.0
    micro = {"precision": round(mp, 4), "recall": round(mr, 4), "f1": round(2 * mp * mr / (mp + mr), 4) if mp + mr else 0.0}
    confusion = {t: {p: 0 for p in ALL_CLASSES} for t in ALL_CLASSES}
    for t, p in pairs:
        confusion[t][p] += 1
    np_ = sum(1 for t, _ in pairs if t == NOT_PERSONAL)
    np_ok = sum(1 for t, p in pairs if t == NOT_PERSONAL and p == NOT_PERSONAL)
    return {"per_class": per, "macro": macro, "micro": micro,
            "accuracy": round(sum(1 for t, p in pairs if t == p) / len(pairs), 4) if pairs else 0.0,
            "not_personal": {"support": np_, "correct": np_ok,
                             "specificity": round(np_ok / np_, 4) if np_ else None},
            "confusion": confusion, "labels": ALL_CLASSES, "columns": len(pairs)}


def load_labels(root: Path = ROOT) -> list[dict]:
    with open(root / "labels.csv", newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def load_tables(root: Path = ROOT) -> dict[tuple[str, str], tuple[list[str], list[list], int]]:
    tables = {}
    for path in sorted((root / "datasets").iterdir()):
        if path.suffix == ".csv":
            read = read_csv(path.read_bytes(), path.name, 1000, "head")
        elif path.suffix == ".sqlite":
            read = read_sqlite_path(path, 1000, "head")
        else:
            continue
        for t in read.tables:
            tables[(path.name, t.name)] = (t.headers, t.rows, t.total_rows)
    return tables


def likely_cause(true_cls: str, pred: dict, column: str, values: list, ruleset: dict) -> str:
    _, tokens = normalise_header(column)
    nonnull = [str(v).strip() for v in values if v is not None and str(v).strip()]
    if true_cls == NOT_PERSONAL:
        s = pred["signals"]
        if s.get("header") and s.get("value", 0) < 0.5:
            return f"Header keyword '{pred.get('header_keyword')}' matched a column that is not personal data"
        if s.get("embedded"):
            return "Free text happened to contain identifier-shaped strings"
        if s.get("header"):
            return (f"Header and values both look like {pred.get('rule_name')}; only the table's context shows "
                    "the values describe a business object, not a person")
        return (f"Values look like {pred.get('rule_name')} and passed its validator "
                f"({round(100 * s.get('validator', 0))}%); the header did not rule it out")
    if len(nonnull) < 5:
        return "Too few non-null values in the sample to measure value signals"
    best_true = None
    for r in ruleset["rules"]:
        if r["class"] == true_cls and r["enabled"]:
            s = score_rule(r, ruleset, tokens, nonnull, {})
            if best_true is None or s["score"] > best_true["score"]:
                best_true = s
    if best_true is None:
        return "No rule exists for this class"
    sig = best_true["signals"]
    if pred["class"] != NOT_PERSONAL:
        return (f"Competing rule '{pred.get('rule_name')}' scored {pred['confidence']:.2f}, above "
                f"'{best_true['rule_name']}' at {best_true['score']:.2f}")
    if "requires_header" in best_true["notes"]:
        return f"'{best_true['rule_name']}' needs header support, and the header '{column}' gave no hint"
    if best_true["negative_keywords"]:
        return f"Negative keyword ({', '.join(best_true['negative_keywords'])}) in the name reduced the score"
    if sig["value"] >= 0.5 and sig["validator"] < 0.5:
        return (f"{round(100 * sig['value'])}% matched the {best_true['rule_name']} pattern but only "
                f"{round(100 * sig['validator'])}% passed the validator (masked, invalid or out-of-range values)")
    if sig["value"] < 0.05 and not sig["header"]:
        return "No rule recognises this identifier's format or header (a rule could be added in the Rule Playground)"
    if sig["value"] < 0.5:
        return (f"Only {round(100 * sig['value'])}% of values matched the {best_true['rule_name']} pattern "
                "(unusual format, masking or mixed content)")
    return f"Score {best_true['score']:.2f} stayed below the threshold {best_true['threshold']}"


def run_benchmark(ruleset: dict | None = None, root: Path = ROOT) -> dict:
    ruleset = ruleset or default_ruleset()
    labels = load_labels(root)
    tables = load_tables(root)
    results = {}
    errors = []
    pairs_by_variant: dict[str, list] = defaultdict(list)
    per_dataset: dict[str, list] = defaultdict(list)
    cache: dict = {}
    for lab in labels:
        key = (lab["source"], lab["table"])
        if key not in tables:
            raise ValueError(f"Labelled table {key} not found in eval/datasets")
        headers, rows, total = tables[key]
        if lab["column"] not in headers:
            raise ValueError(f"Labelled column {lab['column']} not found in {key}")
        i = headers.index(lab["column"])
        values = [r[i] for r in rows]
        truth = lab["true_class"]
        measured: dict = {}
        for vid, _, enabled in VARIANTS:
            pred = classify_column(lab["table"], lab["column"], values, ruleset, "eval", total, enabled, cache, measured)
            pairs_by_variant[vid].append((truth, pred["class"]))
            if vid == "all_signals":
                per_dataset[lab["source"]].append((truth, pred["class"]))
                results[(lab["source"], lab["table"], lab["column"])] = pred
                if pred["class"] != truth:
                    kind = "FN" if truth != NOT_PERSONAL and pred["class"] == NOT_PERSONAL else \
                           "FP" if truth == NOT_PERSONAL else "WRONG_CLASS"
                    errors.append({
                        "kind": kind, "source": lab["source"], "table": lab["table"], "column": lab["column"],
                        "true_class": truth, "predicted": pred["class"], "confidence": pred["confidence"],
                        "rule_id": pred["rule_id"], "signals": pred["signals"], "note": lab.get("note", ""),
                        "masked_examples": pred["masked_examples"],
                        "likely_cause": likely_cause(truth, pred, lab["column"], values, ruleset),
                    })
    main = metrics(pairs_by_variant["all_signals"])
    ablation = []
    for vid, label, _ in VARIANTS:
        m = metrics(pairs_by_variant[vid])
        ablation.append({"variant": vid, "label": label, "macro_f1": m["macro"]["f1"], "micro_f1": m["micro"]["f1"],
                         "macro_precision": m["macro"]["precision"], "macro_recall": m["macro"]["recall"],
                         "accuracy": m["accuracy"]})
    return {
        "benchmark": "PrivacyTwin synthetic benchmark (Faker en_IN + custom generators; no real people)",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ruleset_version": ruleset["version"], "ruleset_hash": content_hash(ruleset),
        "datasets": sorted({l["source"] for l in labels}), "tables": len({(l["source"], l["table"]) for l in labels}),
        **main,
        "per_dataset": {d: metrics(p)["macro"] | {"columns": len(p), "accuracy": metrics(p)["accuracy"]} for d, p in sorted(per_dataset.items())},
        "errors": sorted(errors, key=lambda e: (e["kind"], e["source"], e["table"], e["column"])),
        "ablation": ablation,
        "disclaimer": DISCLAIMER,
        "caveat": "Synthetic data written by the project team. Results show how the rules behave on these cases; "
                  "they are not a guarantee of accuracy on other data.",
    }


def to_csv(result: dict) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["class", "precision", "recall", "f1", "support"])
    for cls in CLASSES:
        p = result["per_class"][cls]
        w.writerow([cls, p["precision"], p["recall"], p["f1"], p["support"]])
    w.writerow(["macro", result["macro"]["precision"], result["macro"]["recall"], result["macro"]["f1"], ""])
    w.writerow(["micro", result["micro"]["precision"], result["micro"]["recall"], result["micro"]["f1"], ""])
    w.writerow([])
    w.writerow(["kind", "source", "table", "column", "true_class", "predicted", "confidence", "likely_cause"])
    for e in result["errors"]:
        w.writerow([e["kind"], e["source"], e["table"], e["column"], e["true_class"], e["predicted"], e["confidence"], e["likely_cause"]])
    return out.getvalue()


_CACHE: dict = {}


def cached_benchmark(ruleset: dict | None = None) -> dict:
    rs = ruleset or default_ruleset()
    h = content_hash(rs)
    if h not in _CACHE:
        _CACHE.clear()
        _CACHE[h] = run_benchmark(rs)
    return _CACHE[h]


def write_results(result: dict, root: Path = ROOT) -> None:
    (root / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (root / "results.csv").write_text(to_csv(result), encoding="utf-8")


def summary_table(result: dict) -> str:
    lines = ["| Class | Precision | Recall | F1 | Support |", "|---|---:|---:|---:|---:|"]
    for cls in CLASSES:
        p = result["per_class"][cls]
        lines.append(f"| {cls} | {p['precision']:.3f} | {p['recall']:.3f} | {p['f1']:.3f} | {p['support']} |")
    lines.append(f"| **Macro avg** | {result['macro']['precision']:.3f} | {result['macro']['recall']:.3f} | **{result['macro']['f1']:.3f}** | |")
    lines.append(f"| Micro avg | {result['micro']['precision']:.3f} | {result['micro']['recall']:.3f} | {result['micro']['f1']:.3f} | |")
    return "\n".join(lines)


def _counter_text(c: Counter) -> str:  # pragma: no cover - debugging helper
    return ", ".join(f"{k}={v}" for k, v in c.most_common())
