"""CLI: python -m privacytwin.eval [--no-write] [--json]"""
from __future__ import annotations

import argparse
import json
import sys

from . import ROOT, run_benchmark, summary_table, write_results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m privacytwin.eval",
                                     description="Evaluate PrivacyTwin detection on the synthetic labelled benchmark.")
    parser.add_argument("--no-write", action="store_true", help="do not write eval/results.json and results.csv")
    parser.add_argument("--json", action="store_true", help="print the full JSON result")
    parser.add_argument("--min-macro-f1", type=float, default=None, help="exit 1 if macro F1 is below this value")
    args = parser.parse_args(argv)
    result = run_benchmark()
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Benchmark: {result['columns']} labelled columns, {result['tables']} tables, {len(result['datasets'])} datasets")
        print(f"Rule set {result['ruleset_version']} ({result['ruleset_hash'][:12]})\n")
        print(summary_table(result))
        print(f"\nAccuracy (incl. NOT_PERSONAL): {result['accuracy']:.3f}")
        print("\nAblation:")
        for a in result["ablation"]:
            print(f"  {a['label']:<32} macro F1 {a['macro_f1']:.3f}  micro F1 {a['micro_f1']:.3f}")
        print(f"\nErrors ({len(result['errors'])}):")
        for e in result["errors"]:
            print(f"  [{e['kind']}] {e['source']}:{e['table']}.{e['column']} true={e['true_class']} "
                  f"pred={e['predicted']} - {e['likely_cause']}")
        print("\nTechnical evidence for human review. Not a legal determination.")
    if not args.no_write:
        write_results(result)
        print(f"\nWrote {ROOT / 'results.json'} and {ROOT / 'results.csv'}", file=sys.stderr)
    if args.min_macro_f1 is not None and result["macro"]["f1"] < args.min_macro_f1:
        print(f"Macro F1 {result['macro']['f1']:.3f} is below {args.min_macro_f1}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
