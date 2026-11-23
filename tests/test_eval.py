from privacytwin.eval import load_labels, metrics, run_benchmark, summary_table, to_csv
from privacytwin.eval.__main__ import main


def test_metrics_on_toy_pairs():
    pairs = [("CONTACT", "CONTACT"), ("CONTACT", "NOT_PERSONAL"), ("NOT_PERSONAL", "CONTACT"),
             ("IDENTITY", "IDENTITY"), ("NOT_PERSONAL", "NOT_PERSONAL")]
    m = metrics(pairs)
    c = m["per_class"]["CONTACT"]
    assert (c["tp"], c["fp"], c["fn"]) == (1, 1, 1) and c["precision"] == 0.5 and c["recall"] == 0.5
    assert m["per_class"]["IDENTITY"]["f1"] == 1.0
    assert m["macro"]["f1"] == 0.75  # averaged over the classes with support
    assert m["confusion"]["CONTACT"]["NOT_PERSONAL"] == 1
    assert m["not_personal"] == {"support": 2, "correct": 1, "specificity": 0.5}


def test_benchmark_size_and_hard_cases():
    labels = load_labels()
    assert len(labels) >= 250
    assert len({l["source"] for l in labels}) >= 3
    notes = " ".join(l["note"] for l in labels)
    for hard in ("misleading header", "fails Verhoeff", "transliterated", "mixed formats", "null"):
        assert hard in notes


def test_benchmark_meets_target_and_explains_every_error():
    r = run_benchmark()
    assert r["macro"]["f1"] >= 0.90
    assert all(e["likely_cause"] for e in r["errors"])
    variants = {a["variant"]: a["macro_f1"] for a in r["ablation"]}
    assert variants["all_signals"] > variants["header_value"] > variants["header_only"]
    assert "| IDENTITY |" in summary_table(r) and to_csv(r).startswith("class,precision")


def test_cli(capsys):
    assert main(["--no-write", "--min-macro-f1", "0.9"]) == 0
    out = capsys.readouterr().out
    assert "Macro avg" in out and "Not a legal determination" in out
