"""Generate the files used by docs/TEST_GUIDE.md.

    python docs/test-data/make_test_data.py

All values are synthetic (fixed seed). The 25 MB oversize file is created on demand
and is not committed.
"""
import csv
import io
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from privacytwin.synth import Gen  # noqa: E402
from privacytwin.validators import verhoeff_valid  # noqa: E402

g = Gen(2024)


def write_csv(name, header, rows, delimiter=",", encoding="utf-8"):
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=delimiter, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    (HERE / name).write_bytes(buf.getvalue().encode(encoding))


def people(n, with_aadhaar=False):
    rows = []
    for i in range(n):
        name = g.name()
        city, _, prefix = g.place()
        row = [f"C{1000 + i}", name, g.email(name), g.mobile(), g.dob(), g.pan(), city, g.pin(prefix),
               g.digits(10, "6789"), g.timestamp()]
        if with_aadhaar:
            row.append(g.aadhaar())
        rows.append(row)
    return rows


HEADER = ["customer_id", "full_name", "email", "mobile_no", "dob", "pan", "city", "pincode", "order_id", "created_at"]

# Positive: a clean customer export, and a later version of the same file with a new Aadhaar column
rows = people(300)
write_csv("customers.csv", HEADER, rows)
g2 = Gen(2024)
(HERE / "v2").mkdir(exist_ok=True)
write_csv("v2/customers.csv", HEADER + ["aadhaar_no"], [r + [g2.aadhaar()] for r in rows])

# Positive: hard cases the AI engine must handle
hard = []
for _ in range(200):
    name = g.name()
    bad12 = next(x for x in iter(lambda: g.digits(12, "23456789"), None) if not verhoeff_valid(x))
    hard.append([g.email(name), name, g.mobile(), bad12, g.voter_id(), f"call me on {g.mobile('plain')}" if g.r.random() < 0.4 else "where is my refund"])
write_csv("hard_cases.csv", ["col_7", "naam", "mob", "txn_ref", "sku", "remarks"], hard)

# Negative-ish (accepted with notes): semicolons, Latin-1, duplicate headers, ragged rows
messy = [["José Iyer", "jose.iyer@example.in", "9876543210"], ["Ana Rao", "ana.rao@example.in"], ["Ravi Kumar", "ravi.k@example.in", "9123456780", "extra"]]
write_csv("messy_latin1.csv", ["name", "email", "email"], messy, delimiter=";", encoding="latin-1")

# Negative: rejected inputs
(HERE / "empty.csv").write_bytes(b"   \n")
(HERE / "fake.sqlite").write_bytes(b"this is not a database")
(HERE / "malware.exe").write_bytes(b"MZ\x90\x00 not really an executable")

# Positive: a small SQLite database with two tables
db = HERE / "bank.sqlite"
db.unlink(missing_ok=True)
con = sqlite3.connect(db)
con.execute("CREATE TABLE accounts(account_id, holder_name, account_number, ifsc, upi_id, balance)")
con.executemany("INSERT INTO accounts VALUES(?,?,?,?,?,?)",
                [(f"A{i}", n := g.name(), g.bank_account(), g.ifsc(), g.upi(n), round(g.r.uniform(100, 90000), 2)) for i in range(150)])
con.execute("CREATE TABLE cards(card_id, card_number, cardholder_name, expiry)")
con.executemany("INSERT INTO cards VALUES(?,?,?,?)", [(f"K{i}", g.card(), g.name().upper(), f"{g.r.randint(1, 12):02d}/29") for i in range(120)])
con.commit()
con.execute("VACUUM")
con.close()

# Metadata import: one good row, one unknown table, one with no values
write_csv("metadata_import.csv", ["source", "table", "column", "purpose", "retention", "owner", "legal_basis", "system_of_record"], [
    ["", "customers", "", "Account management", "3 years", "Customer operations", "Contract (declared)", "CRM"],
    ["", "no_such_table", "", "Anything", "1 year", "", "", ""],
    ["", "customers", "email", "", "", "", "", ""],
])

# Rules: a valid custom rule set (exported default + one rule) and a broken one
(HERE / "rules_broken.yaml").write_text("rules: [unclosed\n", encoding="utf-8")
(HERE / "rules_bad_class.yaml").write_text(
    "name: bad\nversion: 1.0.0\nsignal_weights: {header: 0.35, value: 0.30, validator: 0.35}\nbands: {high: 0.75, medium: 0.55}\n"
    "rules:\n  - id: secret\n    name: Secret thing\n    class: SECRET\n    header_keywords: [secret]\n", encoding="utf-8")

if "--oversize" in sys.argv:
    big = HERE / "oversize_25mb.csv"
    with big.open("w", encoding="utf-8") as fh:
        fh.write("id,email\n")
        line = "1,someone@example.com\n"
        fh.write(line * (25 * 1024 * 1024 // len(line)))
    print("wrote", big)
print("test data written to", HERE)
