# Synthetic labelled benchmark

All data here is **synthetic**: generated with Faker (`en_IN`) and the custom generators in `privacytwin/synth.py`. No real people.

| File | Purpose |
| --- | --- |
| `generate.py` | Regenerates every dataset and `labels.csv` from a fixed seed (`python eval/generate.py`, needs `requirements-dev.txt`). |
| `datasets/` | 8 datasets (CSV and SQLite), 14 tables. |
| `labels.csv` | Ground truth: `source, table, column, true_class, note`. |
| `results.json` / `results.csv` | Output of `python -m privacytwin.eval`. |

## Labelling guide

- **IDENTITY**: person names (including staff, nominees, guardians), date of birth, age, gender.
- **CONTACT**: email addresses, phone numbers, and free text in which a meaningful share of rows contains them.
- **GOVERNMENT_ID**: Aadhaar (also masked or spaced), PAN, passport, voter ID, driving licence, GSTIN, health IDs.
- **FINANCIAL**: card numbers, bank accounts, IFSC *when paired with a person's account*, UPI IDs.
- **LOCATION**: addresses, PIN codes, cities and states *of a person*, coordinates, IP addresses.
- **NOT_PERSONAL**: internal keys (`customer_id`), order/invoice/transaction references, product codes, timestamps, amounts, device IDs (IMEI/ICCID), business attributes (a branch's IFSC or city).

## Hard cases included on purpose

Misleading headers (`col_1`…`col_10`, `field_a`), PII-looking non-PII (mobile-shaped order IDs, 12-digit numbers failing Verhoeff, EPIC-shaped SKUs, passport-shaped product codes, Luhn-valid IMEIs and ICCIDs, PAN-shaped coupons), transliterated headers (`naam`, `pita_ka_naam`, `pata`, `shahar`, `janm_tithi`, `ling`, `umar`), mixed formats, CamelCase headers, and columns that are 50–95% null.

Some errors remain by design because they reflect real limits (masked Aadhaar, a DOB under a generic header, a health ID with no rule, IFSC/city in a branch table). Each is listed with a likely cause in `results.json`.
