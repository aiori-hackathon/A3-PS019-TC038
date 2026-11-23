"""Generate the synthetic labelled benchmark.

    python eval/generate.py

Writes eval/datasets/* and eval/labels.csv. Uses Faker (en_IN) plus custom
generators from privacytwin.synth. Every value is invented; no real people.
Re-running with the same seed produces identical files.
"""
from __future__ import annotations

import csv
import random
import sqlite3
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))

from faker import Faker  # noqa: E402

from privacytwin.synth import Gen  # noqa: E402
from privacytwin.validators import verhoeff_valid  # noqa: E402

SEED = 20251122
fake = Faker("en_IN")
Faker.seed(SEED)
g = Gen(SEED)
R = random.Random(SEED)

ID, C, GOV, FIN, LOC, NP = "IDENTITY", "CONTACT", "GOVERNMENT_ID", "FINANCIAL", "LOCATION", "NOT_PERSONAL"


def person():
    first, last = fake.first_name(), fake.last_name()
    city, state, pin_prefix = g.place()
    return {"first": first, "last": last, "name": f"{first} {last}", "city": city, "state": state,
            "pin": g.pin(pin_prefix), "email": f"{first.lower()}.{last.lower()}{R.randint(1, 99)}@{R.choice(['gmail.com', 'yahoo.co.in', 'outlook.com', 'rediffmail.com'])}",
            "mobile": g.mobile("plain")}


def maybe_null(p: float, fn):
    return lambda ctx: None if R.random() < p else fn(ctx)


def bad_verhoeff_12() -> str:
    while True:
        v = g.digits(12, "23456789")
        if not verhoeff_valid(v):
            return v


def mobile_shaped_10() -> str:
    return g.digits(10, "6789")


def bad_luhn_16() -> str:
    from privacytwin.validators import luhn_valid
    while True:
        v = "4" + g.digits(15)
        if not luhn_valid(v):
            return v


def imei() -> str:
    from privacytwin.validators import luhn_check_digit
    base = R.choice(["35", "86", "01"]) + g.digits(12)
    return base + luhn_check_digit(base)


def iccid() -> str:
    from privacytwin.validators import luhn_check_digit
    base = "8991" + g.digits(14)
    return base + luhn_check_digit(base)


def free_text_with(kind: str, share: float):
    plain = ["Customer asked about the refund timeline", "Requested a plan upgrade next month",
             "Issue resolved after a callback", "Network was slow in the evening", "Wants paper statements",
             "Asked to change the delivery slot", "Escalated to second line support", "Bill amount looked higher than usual"]

    def fn(ctx):
        if R.random() < share:
            if kind == "phone":
                return f"Please call me back on {g.mobile('plain')} after 6 pm"
            return f"Send the invoice to {ctx['email']} please"
        return R.choice(plain)
    return fn


T = dict  # (header, generator, true_class, note)


def col(header, fn, cls, note=""):
    return (header, fn, cls, note)


DATASETS = {
    "retail_bank.sqlite": {
        "customers": (400, [
            col("customer_id", lambda c: g.code("CUST", 6), NP, "internal key"),
            col("full_name", lambda c: c["name"], ID),
            col("email", lambda c: c["email"], C),
            col("mobile_no", lambda c: g.mobile(), C, "mixed formats"),
            col("dob", lambda c: g.dob(), ID),
            col("gender", lambda c: R.choice(["Male", "Female", "Other"]), ID),
            col("pan", lambda c: g.pan(), GOV),
            col("aadhaar_number", lambda c: g.aadhaar(), GOV),
            col("address", lambda c: fake.street_address() + ", " + c["city"], LOC),
            col("city", lambda c: c["city"], LOC),
            col("state", lambda c: c["state"], LOC),
            col("pincode", lambda c: c["pin"], LOC),
            col("occupation", lambda c: fake.job(), NP, "quasi-identifier, not personal alone"),
            col("annual_income", lambda c: R.randint(200000, 4000000), NP),
            col("kyc_status", lambda c: R.choice(["VERIFIED", "PENDING", "REJECTED"]), NP),
            col("created_at", lambda c: g.timestamp(), NP),
        ]),
        "accounts": (400, [
            col("account_id", lambda c: g.code("ACC", 7), NP, "internal key"),
            col("customer_id", lambda c: g.code("CUST", 6), NP, "internal key"),
            col("account_number", lambda c: g.bank_account(), FIN),
            col("ifsc", lambda c: g.ifsc(), FIN),
            col("branch_name", lambda c: c["city"] + " Main", NP),
            col("account_type", lambda c: R.choice(["Savings", "Current", "Salary"]), NP),
            col("balance", lambda c: round(R.uniform(100, 900000), 2), NP),
            col("opened_on", lambda c: g.date_between(3000), NP),
            col("nominee_name", lambda c: fake.name(), ID),
            col("status", lambda c: R.choice(["ACTIVE", "DORMANT", "CLOSED"]), NP),
        ]),
        "cards": (300, [
            col("card_id", lambda c: g.code("CRD", 6), NP),
            col("customer_id", lambda c: g.code("CUST", 6), NP),
            col("card_number", lambda c: g.card(), FIN),
            col("card_network", lambda c: R.choice(["VISA", "MASTERCARD", "RUPAY"]), NP),
            col("expiry_month", lambda c: f"{R.randint(1, 12):02d}/{R.randint(26, 31)}", NP),
            col("credit_limit", lambda c: R.choice([50000, 100000, 250000]), NP),
            col("cardholder_name", lambda c: c["name"].upper(), ID, "upper case"),
        ]),
        "upi_mandates": (300, [
            col("mandate_ref", lambda c: g.code("MND", 8), NP),
            col("vpa", lambda c: g.upi(c["name"]), FIN),
            col("payer_mobile", lambda c: c["mobile"], C),
            col("amount", lambda c: R.randint(100, 20000), NP),
            col("frequency", lambda c: R.choice(["MONTHLY", "WEEKLY", "ONCE"]), NP),
            col("txn_ref", lambda c: bad_verhoeff_12(), NP, "12-digit number failing Verhoeff"),
        ]),
        "branches": (80, [
            col("branch_code", lambda c: g.code("BR", 4), NP),
            col("branch_name", lambda c: c["city"] + " " + R.choice(["Main", "East", "MG Road"]), NP),
            col("ifsc_code", lambda c: g.ifsc(), NP, "branch routing code; not about a person (expected FP)"),
            col("branch_city", lambda c: c["city"], NP, "branch location, not a person's (expected FP)"),
            col("manager_email", lambda c: c["email"], C, "staff email is personal data"),
        ]),
    },
    "hr_export.csv": {
        "hr_export": (400, [
            col("emp_code", lambda c: g.code("EMP", 5), NP),
            col("emp_nm", lambda c: c["name"], ID, "abbreviated header"),
            col("pita_ka_naam", lambda c: fake.name_male(), ID, "transliterated: father's name"),
            col("mob", lambda c: g.mobile(), C, "abbreviated header"),
            col("alt_ph", lambda c: g.mobile(), C),
            col("email_id", lambda c: c["email"], C),
            col("janm_tithi", lambda c: g.dob("%d/%m/%Y"), ID, "transliterated: date of birth"),
            col("ling", lambda c: R.choice(["M", "F"]), ID, "transliterated: gender"),
            col("umar", lambda c: R.randint(21, 60), ID, "transliterated: age"),
            col("pata", lambda c: g.address(c["city"]), LOC, "transliterated: address"),
            col("shahar", lambda c: c["city"], LOC, "transliterated: city"),
            col("pin", lambda c: c["pin"], LOC),
            col("aadhar_no", lambda c: g.aadhaar(spaced=True), GOV, "misspelt header, spaced values"),
            col("pan_no", lambda c: g.pan(), GOV),
            col("bank_ac", lambda c: g.bank_account(), FIN),
            col("ifsc", lambda c: g.ifsc(), FIN),
            col("salary", lambda c: R.randint(25000, 400000), NP),
            col("designation", lambda c: fake.job(), NP),
            col("department", lambda c: R.choice(["Finance", "HR", "Engineering", "Sales", "Ops"]), NP),
            col("doj", lambda c: g.date_between(4000), NP, "date of joining"),
            col("reporting_mgr_code", lambda c: g.code("EMP", 5), NP),
            col("emergency_contact", lambda c: g.mobile("plain"), C),
            col("father_name", lambda c: fake.name_male(), ID),
            col("marital_status", lambda c: R.choice(["Single", "Married"]), NP),
            col("dl_no", lambda c: g.driving_licence(), GOV),
            col("passport_no", lambda c: maybe_null(0.6, lambda _: g.passport())(c), GOV, "60% null"),
            col("voter_id", lambda c: g.voter_id(), GOV),
            col("blood_group", lambda c: R.choice(["A+", "B+", "O+", "AB+", "O-"]), NP, "out of scope classes"),
        ]),
    },
    "ecommerce_orders.csv": {
        "ecommerce_orders": (400, [
            col("order_id", lambda c: mobile_shaped_10(), NP, "10 digits starting 6-9: mobile-shaped"),
            col("order_date", lambda c: g.date_between(400), NP),
            col("customer_name", lambda c: c["name"], ID),
            col("shipping_address", lambda c: g.address(c["city"]), LOC),
            col("billing_pincode", lambda c: c["pin"], LOC),
            col("customer_phone", lambda c: g.mobile(), C),
            col("customer_email", lambda c: c["email"], C),
            col("sku", lambda c: g.voter_id(), NP, "EPIC-shaped product code"),
            col("product_code", lambda c: g.passport(), NP, "passport-shaped product code"),
            col("product_name", lambda c: R.choice(["Steel Bottle", "Cotton Kurta", "Phone Case", "Basmati Rice 5kg"]), NP),
            col("qty", lambda c: R.randint(1, 5), NP),
            col("unit_price", lambda c: round(R.uniform(99, 4999), 2), NP),
            col("discount_code", lambda c: R.choice(["DIWALI10", "NEW50", "", "FESTIVE"]), NP),
            col("payment_method", lambda c: R.choice(["UPI", "CARD", "COD", "NETBANKING"]), NP),
            col("upi_id", lambda c: maybe_null(0.5, lambda _: g.upi(c["name"]))(c), FIN, "50% null"),
            col("invoice_no", lambda c: f"INV-2025-{R.randint(1, 999999):06d}", NP),
            col("txn_ref", lambda c: bad_verhoeff_12(), NP, "12-digit failing Verhoeff"),
            col("awb_number", lambda c: g.digits(12), NP, "courier airway bill"),
            col("courier", lambda c: R.choice(["BlueDart", "Delhivery", "Ekart"]), NP),
            col("delivery_lat", lambda c: g.latlong(c["city"])[0], LOC),
            col("delivery_lng", lambda c: g.latlong(c["city"])[1], LOC),
            col("device_ip", lambda c: fake.ipv4_public(), LOC),
            col("user_agent", lambda c: fake.user_agent(), NP),
            col("buyer_gstin", lambda c: maybe_null(0.7, lambda _: g.gstin())(c), GOV, "70% null"),
            col("rating", lambda c: R.randint(1, 5), NP),
            col("review_text", lambda c: R.choice(["Good quality", "Late delivery", "Value for money", "Packaging could be better"]), NP),
            col("created_at", lambda c: g.timestamp(), NP),
            col("updated_at", lambda c: g.timestamp(), NP),
            col("coupon", lambda c: g.pan(), NP, "PAN-shaped coupon code"),
            col("return_window_days", lambda c: R.choice([7, 10, 30]), NP),
        ]),
    },
    "hard_cases.csv": {
        "hard_cases": (400, [
            col("col_1", lambda c: c["email"], C, "misleading header"),
            col("col_2", lambda c: g.mobile(), C, "misleading header"),
            col("col_3", lambda c: c["name"], ID, "misleading header"),
            col("col_4", lambda c: g.aadhaar(), GOV, "misleading header"),
            col("col_5", lambda c: bad_verhoeff_12(), NP, "Aadhaar-shaped, fails Verhoeff"),
            col("col_6", lambda c: g.pan(), GOV, "misleading header"),
            col("col_7", lambda c: g.card(spaced=False), FIN, "misleading header"),
            col("col_8", lambda c: bad_luhn_16(), NP, "card-shaped, fails Luhn"),
            col("col_9", lambda c: c["city"], LOC, "misleading header"),
            col("col_10", lambda c: str(uuid.UUID(int=R.getrandbits(128))), NP),
            col("field_a", lambda c: g.gstin(), GOV, "misleading header"),
            col("field_b", lambda c: fake.ipv4_public(), LOC, "misleading header"),
            col("data1", lambda c: g.dob(), ID, "DOB under a generic header (expected FN: rule needs header)"),
            col("email_mostly_null", maybe_null(0.9, lambda c: c["email"]), C, "90% null"),
            col("phone_mostly_null", maybe_null(0.95, lambda c: g.mobile()), C, "95% null"),
            col("mobile_mixed_formats", lambda c: g.mobile(), C),
            col("aadhaar_spaced", lambda c: g.aadhaar(spaced=True), GOV),
            col("aadhaar_masked", lambda c: "XXXX XXXX " + g.digits(4), GOV, "masked values (expected FN)"),
            col("pan_lowercase", lambda c: g.pan().lower(), GOV),
            col("remarks", free_text_with("phone", 0.35), C, "phone numbers embedded in free text"),
            col("notes", lambda c: R.choice(["Called twice", "Prefers email", "VIP customer", "Follow up next week"]), NP),
            col("comments", free_text_with("email", 0.3), C, "emails embedded in free text"),
            col("order_no", lambda c: mobile_shaped_10(), NP, "mobile-shaped order number"),
            col("invoice_number", lambda c: g.digits(12, "23456789"), NP),
            col("sku_code", lambda c: g.voter_id(), NP, "EPIC-shaped"),
            col("zip", lambda c: c["pin"], LOC),
            col("lat", lambda c: g.latlong(c["city"])[0], LOC),
            col("lon", lambda c: g.latlong(c["city"])[1], LOC),
            col("geo", lambda c: "{}, {}".format(*g.latlong(c["city"])), LOC),
            col("product_name", lambda c: R.choice(["Gold Plan", "Silver Plan", "Basic"]), NP),
            col("company_name", lambda c: fake.company(), NP),
            col("bank_name", lambda c: R.choice(["HDFC Bank", "State Bank of India", "ICICI Bank"]), NP),
            col("status", lambda c: R.choice(["open", "closed"]), NP),
            col("amount", lambda c: round(R.uniform(10, 9999), 2), NP),
            col("otp", lambda c: g.digits(6, "123456789"), NP, "six digits like a PIN code"),
            col("version", lambda c: f"{R.randint(1, 4)}.{R.randint(0, 9)}.{R.randint(0, 20)}", NP),
            col("Contact", lambda c: c["email"], C, "CamelCase, generic header"),
            col("CustomerName", lambda c: c["name"], ID, "CamelCase"),
            col("DateOfBirth", lambda c: g.dob("%d-%m-%Y"), ID, "CamelCase"),
            col("PinCode", lambda c: c["pin"], LOC, "CamelCase"),
            col("MobileNumber", lambda c: g.mobile(), C, "CamelCase"),
            col("upi_handle", lambda c: g.upi(c["name"]), FIN),
            col("ifsc_lower", lambda c: g.ifsc().lower(), FIN),
            col("voterId", lambda c: g.voter_id(), GOV),
            col("DLNumber", lambda c: g.driving_licence(), GOV),
            col("passportNo", lambda c: g.passport(), GOV),
            col("age_years", lambda c: R.randint(18, 80), ID),
            col("sex", lambda c: R.choice(["M", "F"]), ID),
            col("job_title", lambda c: fake.job(), NP, "quasi-identifier only"),
            col("country", lambda c: "India", NP),
            col("state_name", lambda c: c["state"], LOC),
            col("imei", lambda c: imei(), NP, "Luhn-valid device ID, not a card"),
            col("sim_iccid", lambda c: iccid(), NP, "Luhn-valid SIM serial, not a card"),
        ]),
    },
    "telecom_crm.sqlite": {
        "subscribers": (400, [
            col("msisdn", lambda c: "91" + c["mobile"], C, "telecom term; no header keyword"),
            col("subscriber_name", lambda c: c["name"], ID),
            col("alt_contact", lambda c: g.mobile(), C),
            col("email", lambda c: c["email"], C),
            col("dob", lambda c: g.dob(), ID),
            col("id_proof_type", lambda c: R.choice(["AADHAAR", "PAN", "VOTER"]), NP),
            col("id_proof_number", lambda c: R.choice([g.aadhaar(), g.pan(), g.voter_id()]), GOV, "mixed ID types (expected FN)"),
            col("plan_name", lambda c: R.choice(["Unlimited 299", "Postpaid 599", "Data 199"]), NP),
            col("activation_date", lambda c: g.date_between(2500), NP),
            col("circle", lambda c: c["state"], LOC, "telecom circle = subscriber's home state"),
            col("tower_lat_long", lambda c: "{},{}".format(*g.latlong(c["city"])), LOC),
            col("last_login_ip", lambda c: fake.ipv4_public(), LOC),
            col("arpu", lambda c: round(R.uniform(99, 999), 2), NP),
            col("imei", lambda c: imei(), NP, "Luhn-valid device ID"),
            col("sim_serial", lambda c: iccid(), NP),
        ]),
        "recharges": (400, [
            col("recharge_id", lambda c: g.code("RC", 8), NP),
            col("msisdn", lambda c: "91" + c["mobile"], C),
            col("amount", lambda c: R.choice([199, 299, 399, 599]), NP),
            col("channel", lambda c: R.choice(["APP", "RETAIL", "WEB"]), NP),
            col("upi_vpa", lambda c: g.upi(c["name"]), FIN),
            col("recharged_at", lambda c: g.timestamp(), NP),
            col("retailer_code", lambda c: g.code("RT", 5), NP),
        ]),
        "complaints": (300, [
            col("ticket_no", lambda c: g.code("TKT", 7), NP),
            col("msisdn", lambda c: "91" + c["mobile"], C),
            col("complaint_text", free_text_with("phone", 0.3), C, "phone numbers embedded in text"),
            col("category", lambda c: R.choice(["Billing", "Network", "Porting"]), NP),
            col("agent_name", lambda c: fake.name(), ID, "staff names are personal data"),
            col("resolved_on", lambda c: g.date_between(300), NP),
            col("escalation_email", lambda c: c["email"], C),
        ]),
    },
    "healthcare_appointments.csv": {
        "healthcare_appointments": (400, [
            col("appointment_id", lambda c: g.code("APT", 7), NP),
            col("patient_name", lambda c: c["name"], ID),
            col("patient_age", lambda c: R.randint(1, 95), ID),
            col("patient_gender", lambda c: R.choice(["Male", "Female"]), ID),
            col("contact_number", lambda c: g.mobile(), C),
            col("email_address", lambda c: c["email"], C),
            col("residential_address", lambda c: g.address(c["city"]), LOC),
            col("city", lambda c: c["city"], LOC),
            col("pin_code", lambda c: c["pin"], LOC),
            col("abha_number", lambda c: "-".join([g.digits(2, "123456789"), g.digits(4), g.digits(4), g.digits(4)]), GOV,
                "Ayushman Bharat health ID: no rule yet (expected FN)"),
            col("doctor_name", lambda c: "Dr. " + fake.name(), ID),
            col("department", lambda c: R.choice(["Cardiology", "ENT", "Orthopaedics", "General Medicine"]), NP),
            col("appointment_date", lambda c: g.date_between(60), NP),
            col("slot_time", lambda c: f"{R.randint(9, 17):02d}:{R.choice(['00', '30'])}", NP),
            col("fee", lambda c: R.choice([300, 500, 800]), NP),
            col("payment_mode", lambda c: R.choice(["UPI", "Cash", "Card"]), NP),
            col("emergency_contact_name", lambda c: fake.name(), ID),
            col("emergency_contact_phone", lambda c: g.mobile(), C),
            col("bed_no", lambda c: R.choice(["", f"W{R.randint(1, 9)}-{R.randint(1, 40)}"]), NP),
            col("visit_reason", lambda c: R.choice(["Follow-up", "Fever", "Routine check", "Back pain"]), NP),
            col("referral_code", lambda c: g.code("REF", 5), NP),
            col("insurer", lambda c: R.choice(["Star Health", "HDFC Ergo", "Niva Bupa", ""]), NP),
        ]),
    },
    "loan_applications.csv": {
        "loan_applications": (400, [
            col("application_id", lambda c: g.code("LN", 8), NP),
            col("applicant_name", lambda c: c["name"], ID),
            col("co_applicant", lambda c: maybe_null(0.5, lambda _: fake.name())(c), ID, "50% null"),
            col("applicant_mobile", lambda c: g.mobile(), C),
            col("applicant_email", lambda c: c["email"], C),
            col("pan_number", lambda c: g.pan(), GOV),
            col("aadhaar", lambda c: g.aadhaar(), GOV),
            col("dob", lambda c: g.dob("%d.%m.%Y"), ID, "dotted date format"),
            col("residential_city", lambda c: c["city"], LOC),
            col("permanent_address", lambda c: g.address(c["city"]), LOC),
            col("pincode", lambda c: c["pin"], LOC),
            col("employer_name", lambda c: fake.company(), NP, "company names built from surnames"),
            col("monthly_income", lambda c: R.randint(20000, 300000), NP),
            col("loan_amount", lambda c: R.choice([100000, 250000, 500000, 1000000]), NP),
            col("tenure_months", lambda c: R.choice([12, 24, 36, 60]), NP),
            col("emi", lambda c: round(R.uniform(2000, 40000), 2), NP),
            col("cibil_score", lambda c: R.randint(550, 900), NP),
            col("salary_account_no", lambda c: g.bank_account(), FIN),
            col("salary_ifsc", lambda c: g.ifsc(), FIN),
            col("disbursal_upi", lambda c: g.upi(c["name"]), FIN),
            col("guarantor_name", lambda c: fake.name(), ID),
            col("guarantor_phone", lambda c: g.mobile(), C),
            col("application_ts", lambda c: g.timestamp(), NP),
            col("loan_status", lambda c: R.choice(["APPROVED", "REJECTED", "UNDER_REVIEW"]), NP),
            col("gender", lambda c: R.choice(["F", "M"]), ID),
        ]),
    },
    "marketing_leads.csv": {
        "marketing_leads": (400, [
            col("lead_id", lambda c: g.code("LD", 7), NP),
            col("lead_name", lambda c: c["name"], ID),
            col("lead_email", lambda c: c["email"], C),
            col("whatsapp_no", lambda c: g.mobile(), C),
            col("source_campaign", lambda c: R.choice(["diwali_sale", "search_brand", "insta_reel"]), NP),
            col("utm_source", lambda c: R.choice(["google", "instagram", "newsletter"]), NP),
            col("landing_page", lambda c: R.choice(["/offers", "/loans", "/cards"]), NP),
            col("city", lambda c: c["city"], LOC),
            col("interested_product", lambda c: R.choice(["Personal loan", "Credit card", "FD"]), NP),
            col("consent_flag", lambda c: R.choice(["Y", "N"]), NP),
            col("lead_score", lambda c: R.randint(1, 100), NP),
            col("created_on", lambda c: g.date_between(500), NP),
            col("assigned_to", lambda c: g.code("EMP", 5), NP),
            col("last_contacted", lambda c: g.date_between(90), NP),
            col("preferred_language", lambda c: R.choice(["Hindi", "English", "Tamil", "Marathi"]), NP),
            col("budget", lambda c: R.choice([50000, 100000, 500000]), NP),
            col("occupation", lambda c: fake.job(), NP),
            col("company", lambda c: fake.company(), NP),
            col("ip_address", lambda c: fake.ipv4_public(), LOC),
            col("geo_coordinates", lambda c: "{}, {}".format(*g.latlong(c["city"])), LOC),
            col("date_of_birth", lambda c: g.dob("%d/%m/%Y"), ID),
            col("pan_card", lambda c: maybe_null(0.4, lambda _: g.pan())(c), GOV),
        ]),
    },
}


def build_rows(n, columns):
    rows = []
    for _ in range(n):
        ctx = person()
        rows.append([fn(ctx) for _, fn, _, _ in columns])
    return rows


def main():
    out = ROOT / "datasets"
    out.mkdir(exist_ok=True)
    for p in out.iterdir():
        p.unlink()
    labels = []
    for dataset, tables in DATASETS.items():
        path = out / dataset
        if dataset.endswith(".csv"):
            (table, (n, columns)), = tables.items()
            rows = build_rows(n, columns)
            with open(path, "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow([h for h, *_ in columns])
                w.writerows([["" if v is None else v for v in r] for r in rows])
            labels += [(dataset, table, h, cls, note) for h, _, cls, note in columns]
        else:
            conn = sqlite3.connect(path)
            for table, (n, columns) in tables.items():
                conn.execute(f'CREATE TABLE "{table}" ({", ".join(chr(34) + h + chr(34) for h, *_ in columns)})')
                conn.executemany(f'INSERT INTO "{table}" VALUES ({",".join("?" * len(columns))})', build_rows(n, columns))
                labels += [(dataset, table, h, cls, note) for h, _, cls, note in columns]
            conn.commit()
            conn.execute("VACUUM")
            conn.close()
    with open(ROOT / "labels.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["source", "table", "column", "true_class", "note"])
        w.writerows(labels)
    from collections import Counter
    print(f"{len(labels)} labelled columns in {sum(len(t) for t in DATASETS.values())} tables, {len(DATASETS)} datasets")
    print(Counter(l[3] for l in labels))


if __name__ == "__main__":
    main()
