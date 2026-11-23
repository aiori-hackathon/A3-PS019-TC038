"""Synthetic defence-R&D (DRDO-style) test estate for PrivacyTwin.

    python docs/test-data/drdo/make_drdo_data.py

Every value is generated from a fixed seed. Lab codes (LAB-01…), domains (*.example.in)
and people are fictional. No real personnel, labs, projects or classified content.
"""
import csv
import io
import random
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
from privacytwin.synth import CITIES, Gen  # noqa: E402

SEED = 1958
g = Gen(SEED)
R = random.Random(SEED)
LABS = [f"LAB-{i:02d}" for i in range(1, 13)]
GRADES = ["Scientist 'B'", "Scientist 'C'", "Scientist 'D'", "Scientist 'E'", "Scientist 'F'", "Scientist 'G'",
          "Technical Officer 'A'", "Technical Officer 'B'", "Admin Officer", "Store Officer"]
CLEARANCE = ["RESTRICTED", "CONFIDENTIAL", "SECRET"]


def write_csv(path: Path, header, rows):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buf.getvalue().encode("utf-8"))


def vehicle_no():
    state = R.choice(["DL", "KA", "TS", "MH", "TN", "UP", "OD", "KL"])
    return f"{state}{R.randint(1, 30):02d}{R.choice('ABCDEFGHJKLMNPRSTUVWXYZ')}{R.choice('ABCDEFGHJKLMNPRSTUVWXYZ')}{R.randint(1000, 9999)}"


# ---------------------------------------------------------------- personnel
officers = []
for i in range(420):
    name = g.name()
    city, _, prefix = g.place()
    lab = R.choice(LABS)
    officers.append({"emp_no": f"DS{R.randint(10000, 99999)}", "name": name, "lab": lab, "city": city, "prefix": prefix,
                     "email": f"{name.lower().replace(' ', '.')}@{lab.lower()}.example.in", "mobile": g.mobile()})
personnel_header = ["emp_no", "officer_name", "designation", "lab_code", "gender", "dob", "mobile_no", "official_email",
                    "aadhaar_no", "pan_no", "passport_no", "permanent_address", "pin_code", "salary_acct_no", "ifsc",
                    "clearance_level", "blood_group", "date_of_joining"]
personnel = [[o["emp_no"], o["name"], R.choice(GRADES), o["lab"], R.choice(["Male", "Female"]), g.dob(), o["mobile"],
              o["email"], g.aadhaar(), g.pan(), g.passport() if R.random() < 0.55 else "", g.address(o["city"]),
              g.pin(o["prefix"]), g.bank_account(), g.ifsc(), R.choice(CLEARANCE), R.choice(["A+", "B+", "O+", "AB+"]),
              g.date_between(9000)] for o in officers]
write_csv(HERE / "personnel.csv", personnel_header, personnel)

# ---------------------------------------------------------------- visitor gate register (v1, v2 adds aadhaar_no)
visitor_header = ["pass_no", "visitor_name", "organisation", "mobile_no", "id_proof_type", "id_proof_no",
                  "vehicle_reg_no", "host_officer", "host_emp_no", "purpose_of_visit", "gate", "entry_time"]
visitors_v1, visitors_v2 = [], []
for i in range(500):
    name = g.name()
    kind = R.choice(["DL", "VOTER", "PASSPORT"])
    proof = g.driving_licence() if kind == "DL" else g.voter_id() if kind == "VOTER" else g.passport()
    host = R.choice(officers)
    row = [f"GP{R.randint(100000, 999999)}", name, R.choice(["Vendor", "University", "PSU", "Contractor", "Family"]),
           g.mobile(), kind, proof, vehicle_no() if R.random() < 0.6 else "", host["name"], host["emp_no"],
           R.choice(["Project review", "Equipment delivery", "Interview", "Maintenance", "Meeting"]),
           R.choice(["Gate 1", "Gate 2", "Gate 3"]), g.timestamp(120)]
    visitors_v1.append(row)
    visitors_v2.append(row + [g.aadhaar()])
write_csv(HERE / "visitor_register.csv", visitor_header, visitors_v1)
write_csv(HERE / "v2" / "visitor_register.csv", visitor_header + ["aadhaar_no"], visitors_v2)

# ---------------------------------------------------------------- lab access log
access = []
for i in range(800):
    o = R.choice(officers)
    lat, lon = g.latlong(o["city"])
    access.append([f"BDG-{o['emp_no'][2:]}", o["name"], o["lab"], R.choice(["Main door", "Clean room", "Test range", "Server room"]),
                   f"10.{R.randint(0, 40)}.{R.randint(0, 255)}.{R.randint(1, 254)}", f"{lat}, {lon}", g.timestamp(60),
                   R.choice(["GRANTED", "GRANTED", "GRANTED", "DENIED"])])
write_csv(HERE / "lab_access_log.csv", ["badge_id", "officer_name", "lab_code", "door", "terminal_ip", "gps_location",
                                        "access_time", "result"], access)

# ---------------------------------------------------------------- TA/DA travel claims
claims = []
for i in range(350):
    o = R.choice(officers)
    frm, to = R.sample([c[0] for c in CITIES], 2)
    remark = R.choice([f"Contact me on {o['mobile']} for bills", f"Receipts mailed to {o['email']}",
                       "Train tickets attached", "Hotel invoice pending", "Advance adjusted"])
    claims.append([f"TA/{R.randint(2024, 2026)}/{R.randint(1000, 9999)}", o["emp_no"], o["name"], frm, to,
                   g.date_between(400), R.randint(2500, 85000), g.bank_account(), g.ifsc(), remark])
write_csv(HERE / "ta_da_claims.csv", ["claim_no", "emp_no", "claimant_name", "from_city", "to_city", "journey_date",
                                      "amount_inr", "credit_account", "ifsc", "remarks"], claims)

# ---------------------------------------------------------------- vendor / procurement database
db = HERE / "procurement.sqlite"
db.unlink(missing_ok=True)
con = sqlite3.connect(db)
con.execute("CREATE TABLE vendors(vendor_code, firm_name, proprietor_name, gstin, pan, contact_mobile, contact_email, "
            "bank_account, ifsc, registered_address, pin_code)")
vendors = []
for i in range(160):
    name = g.name()
    city, _, prefix = g.place()
    vendors.append((f"VND{i:04d}", f"{name.split()[1]} {R.choice(['Precision Works', 'Electronics', 'Composites', 'Systems'])} Pvt Ltd",
                    name, g.gstin(), g.pan(), g.mobile(), g.email(name), g.bank_account(), g.ifsc(), g.address(city), g.pin(prefix)))
con.executemany("INSERT INTO vendors VALUES(?,?,?,?,?,?,?,?,?,?,?)", vendors)
con.execute("CREATE TABLE purchase_orders(po_no, vendor_code, lab_code, item_description, quantity, value_inr, po_date, approving_officer)")
con.executemany("INSERT INTO purchase_orders VALUES(?,?,?,?,?,?,?,?)", [
    (g.digits(10, "6789"), R.choice(vendors)[0], R.choice(LABS), R.choice(["Servo actuator", "FPGA board", "Carbon prepreg", "Oscilloscope", "Test fixture"]),
     R.randint(1, 50), R.randint(10000, 9000000), g.date_between(700), R.choice(officers)["name"]) for _ in range(400)])
con.commit()
con.execute("VACUUM")
con.close()
print("DRDO-style synthetic estate written to", HERE)
