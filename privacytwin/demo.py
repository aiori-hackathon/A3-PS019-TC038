"""Synthetic demo company: Acme Fintech India.

Three historical scans tell a small story:
  scan #1 (55 days ago)  customers, kyc_documents, payments, support_tickets
  scan #2 (25 days ago)  + marketing_leads, payments gains upi_id, kyc gains dl_number
  scan #3 (today)        + employees; support_tickets gains aadhaar_no (drift with no purpose);
                          marketing_leads drops lead_ip
Metadata is declared and reviews are done between scans, so every screen has content.
All values are generated in memory from a fixed seed. No real people.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .gaps import column_target, table_target
from .ingest import read_memory_tables
from .synth import JOBS, Gen
from .twin import Twin

DEMO_NAME = "Acme Fintech India (synthetic)"
SEED = 4242


def _ts(days_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat(timespec="seconds")


def _tables(version: int) -> dict[str, tuple[list[str], list[list]]]:
    g = Gen(SEED + version)
    n_customers = 600 if version < 3 else 720
    customers, people = [], []
    for i in range(n_customers):
        name = g.name()
        city, state, prefix = g.place()
        person = {"id": f"C{100000 + i}", "name": name, "city": city, "pin": g.pin(prefix), "email": g.email(name),
                  "mobile": g.mobile()}
        people.append(person)
        customers.append([person["id"], name, person["email"], person["mobile"], g.dob(), g.choice(["Male", "Female", "Male", "Female", "Other"]),
                          g.pan(), city, person["pin"], g.address(city), g.date_between(1600), g.choice(["VERIFIED", "PENDING"])])
    t = {"customers": (["customer_id", "full_name", "email", "mobile", "dob", "gender", "pan", "city", "pincode",
                        "address", "created_at", "kyc_status"], customers)}

    kyc_h = ["kyc_id", "customer_id", "document_type", "pan_number", "passport_no", "voter_id", "verified_by", "verified_on"]
    if version >= 2:
        kyc_h.append("dl_number")
    kyc = []
    for i, p in enumerate(people[:450]):
        row = [f"K{500000 + i}", p["id"], g.choice(["PAN", "PASSPORT", "VOTER_ID"]), g.pan(), g.passport(), g.voter_id(),
               g.name(), g.date_between(1200)]
        if version >= 2:
            row.append(g.driving_licence())
        kyc.append(row)
    t["kyc_documents"] = (kyc_h, kyc)

    pay_h = ["payment_id", "customer_id", "card_number", "bank_account", "ifsc", "amount", "txn_ref", "paid_at"]
    if version >= 2:
        pay_h.insert(3, "upi_id")
    pays = []
    for i in range(700):
        p = g.choice(people)
        row = [f"P{9000000 + i}", p["id"], g.card(), g.bank_account(), g.ifsc(), round(g.r.uniform(99, 50000), 2),
               g.digits(12, "123456789"), g.timestamp(700)]
        if version >= 2:
            row.insert(3, g.upi(p["name"]))
        pays.append(row)
    t["payments"] = (pay_h, pays)

    sup_h = ["ticket_id", "customer_id", "message", "agent_name", "channel", "created_at"]
    if version >= 3:
        sup_h.append("aadhaar_no")
    msgs = ["Unable to log in to the app", "Refund not received yet", "Card blocked after travel", "Need statement for tax filing",
            "UPI payment failed twice", "Change my registered address"]
    tickets = []
    for i in range(420):
        p = g.choice(people)
        r = g.r.random()
        msg = (f"Please call me on {p['mobile']} about my refund" if r < 0.22 else
               f"Send the statement to {p['email']}" if r < 0.36 else g.choice(msgs))
        row = [f"T{70000 + i}", p["id"], msg, g.name(), g.choice(["app", "email", "phone"]), g.timestamp(500)]
        if version >= 3:
            row.append(g.aadhaar() if g.r.random() < 0.6 else "")
        tickets.append(row)
    t["support_tickets"] = (sup_h, tickets)

    if version >= 2:
        lead_h = ["lead_id", "lead_name", "email", "whatsapp_no", "city", "utm_source", "created_on"]
        if version == 2:
            lead_h.append("lead_ip")
        leads = []
        for i in range(500):
            name = g.name()
            city = g.place()[0]
            row = [f"L{30000 + i}", name, g.email(name), g.mobile(), city, g.choice(["google", "instagram", "partner"]), g.date_between(900)]
            if version == 2:
                row.append(g.ip())
            leads.append(row)
        t["marketing_leads"] = (lead_h, leads)

    if version >= 3:
        emp = []
        for i in range(140):
            name = g.name()
            city, _, prefix = g.place()
            emp.append([f"E{1000 + i}", name, g.email(name).split("@")[0] + "@acme-fintech.example", g.mobile(), g.dob(),
                        g.choice(["Male", "Female"]), g.bank_account(), g.ifsc(), g.address(city), g.pin(prefix),
                        g.choice(JOBS), g.date_between(3000)])
        t["employees"] = (["emp_code", "emp_name", "work_email", "mobile", "dob", "gender", "salary_account", "ifsc",
                           "home_address", "pin_code", "designation", "joined_on"], emp)
    return t


def has_demo(twin: Twin, ws: str) -> bool:
    with twin.store.connect() as c:
        return c.execute("SELECT 1 FROM sources WHERE ws=? AND origin='demo'", (ws,)).fetchone() is not None


def load_demo(twin: Twin, ws: str, actor: str = "demo") -> dict:
    if has_demo(twin, ws):
        return {"loaded": False, "reason": "Demo already loaded"}
    twin.store.ensure_workspace(ws)
    detail = {"synthetic": True, "company": "Acme Fintech India", "note": "Generated in memory from a fixed seed"}
    source_id = None
    results = []
    for version, days in ((1, 55), (2, 25), (3, 0.01)):
        read = read_memory_tables(_tables(version), 1000, "head")
        done = twin.run_scan(ws, read, DEMO_NAME, "demo", 1000, "head", actor, detail, _ts(days), source_id)
        source_id = done["source_id"]
        results.append(done["scan_seq"])
        if version == 1:
            _after_scan_1(twin, ws, source_id)
        elif version == 2:
            _after_scan_2(twin, ws, source_id)
    return {"loaded": True, "source_id": source_id, "scans": results}


def _key(source_id: str, table: str, column: str) -> str:
    return f"{source_id}/{table}/{column}"


def _after_scan_1(twin: Twin, ws: str, sid: str) -> None:
    t = _ts(50)
    twin.set_metadata(ws, [table_target(sid, "customers")], {
        "purpose": "Account management", "owner": "Customer operations", "retention": "3 years",
        "legal_basis": "Contract with the customer (declared by owner)", "system_of_record": "Core banking (Acme CBS)"},
        "priya.ops", t)
    twin.set_metadata(ws, [table_target(sid, "payments")], {
        "purpose": "Billing & payments", "owner": "Finance team", "retention": "8 years", "system_of_record": "Payments ledger"},
        "arjun.fin", t)
    twin.set_metadata(ws, [column_target(_key(sid, "payments", "card_number"))], {"retention": "180 days"}, "arjun.fin", t)
    twin.review(ws, [_key(sid, "customers", c) for c in ("email", "mobile", "pan", "dob", "full_name")], "confirmed",
                "Matches the customer master schema", "priya.ops", created_at=_ts(49))


def _after_scan_2(twin: Twin, ws: str, sid: str) -> None:
    t = _ts(20)
    twin.set_metadata(ws, [table_target(sid, "kyc_documents")], {
        "purpose": "Customer identity verification (KYC)", "owner": "Compliance team", "retention": "15 years",
        "legal_basis": "Legal obligation (declared by compliance)", "system_of_record": "KYC vault"}, "meera.compliance", t)
    twin.set_metadata(ws, [table_target(sid, "marketing_leads")], {"purpose": "Marketing outreach"}, "rohit.mkt", t)
    twin.review(ws, [_key(sid, "kyc_documents", c) for c in ("pan_number", "passport_no", "voter_id")], "confirmed",
                "KYC document fields", "meera.compliance", created_at=_ts(19))
    twin.review(ws, [_key(sid, "payments", "card_number"), _key(sid, "payments", "bank_account")], "confirmed",
                "Payment instrument data", "arjun.fin", created_at=_ts(19))
    twin.review(ws, [_key(sid, "payments", "ifsc")], "rejected",
                "Branch routing code on its own; does not identify the payer", "arjun.fin", created_at=_ts(18))
    twin.review(ws, [_key(sid, "marketing_leads", "lead_ip")], "needs_info",
                "Ask marketing whether IPs come from the consent form", "rohit.mkt", created_at=_ts(18))
