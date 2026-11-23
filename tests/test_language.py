"""The product never issues legal verdicts: forbidden words must not appear in UI or exports."""
import io
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = re.compile(r"\b(compliant|violation|illegal)\b", re.I)
DISCLAIMER = "Technical evidence for human review. Not a legal determination."


def test_no_verdict_words_in_ui_or_backend_source():
    files = [p for d in ("web/app", "web/components", "web/lib") for p in (ROOT / d).rglob("*") if p.suffix in (".ts", ".tsx", ".css")]
    # llm.py is exempt: it lists the words in order to forbid and filter them in model output
    files += [p for p in (ROOT / "privacytwin").rglob("*.py") if p.name != "llm.py"] + [ROOT / "privacytwin" / "default_rules.yaml"]
    assert len(files) > 30
    hits = [f"{p.relative_to(ROOT)}: {m.group(0)}" for p in files for m in FORBIDDEN.finditer(p.read_text(encoding="utf-8"))]
    assert not hits, hits


def test_exports_carry_disclaimer_and_no_verdict_words(demo):
    pack = demo.post("/api/evidence").content
    with zipfile.ZipFile(io.BytesIO(pack)) as z:
        texts = {n: z.read(n).decode("utf-8") for n in z.namelist()}
    for name, text in texts.items():
        assert not FORBIDDEN.search(text), name
    for name in ("summary.html", "manifest.json", "README.txt", "evaluation.json", "data_handling_receipts.json"):
        assert DISCLAIMER in texts[name], name
    inv = demo.get("/api/workspace/export").text
    assert DISCLAIMER in inv and not FORBIDDEN.search(inv)


def test_web_footer_has_disclaimer():
    assert DISCLAIMER in (ROOT / "web/components/ui.tsx").read_text(encoding="utf-8")
