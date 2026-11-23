"""Format and checksum validators.

Each validator takes a *normalised* string and returns True when the value passes
real structural checks (checksums, ranges, allowed prefixes). A pass is technical
evidence that a value is well formed; it never proves issuance or ownership.
"""
from __future__ import annotations

import ipaddress
import re
from datetime import date, datetime

# ---------------------------------------------------------------- helpers

_SEPARATORS = re.compile(r"[\s\-().]")


def strip_separators(value: str) -> str:
    return _SEPARATORS.sub("", value)


# ---------------------------------------------------------------- Verhoeff

_D = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9), (1, 2, 3, 4, 0, 6, 7, 8, 9, 5), (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7), (4, 0, 1, 2, 3, 9, 5, 6, 7, 8), (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2), (7, 6, 5, 9, 8, 2, 1, 0, 4, 3), (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)
_P = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9), (1, 5, 7, 6, 2, 8, 3, 0, 9, 4), (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7), (9, 4, 5, 3, 1, 2, 6, 8, 7, 0), (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5), (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)
_INV = (0, 4, 3, 2, 1, 5, 6, 7, 8, 9)


def verhoeff_valid(digits: str) -> bool:
    if not digits.isdigit():
        return False
    c = 0
    for i, n in enumerate(reversed(digits)):
        c = _D[c][_P[i % 8][int(n)]]
    return c == 0


def verhoeff_check_digit(digits: str) -> str:
    c = 0
    for i, n in enumerate(reversed(digits)):
        c = _D[c][_P[(i + 1) % 8][int(n)]]
    return str(_INV[c])


# ---------------------------------------------------------------- Luhn

def luhn_valid(digits: str) -> bool:
    if not digits.isdigit() or len(digits) < 2:
        return False
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def luhn_check_digit(digits: str) -> str:
    for d in "0123456789":
        if luhn_valid(digits + d):
            return d
    raise ValueError("unreachable")


# ---------------------------------------------------------------- validators

_EMAIL = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._%+\-]{0,62}[A-Za-z0-9])?@(?:[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,24}$")


def email(value: str) -> bool:
    v = value.strip()
    return len(v) <= 254 and ".." not in v and bool(_EMAIL.match(v))


def indian_mobile(value: str) -> bool:
    """+91 / 91 / 0 prefix optional; ten digits starting 6-9; rejects repeated digits."""
    v = strip_separators(value)
    if v.startswith("+91"):
        v = v[3:]
    elif len(v) == 12 and v.startswith("91"):
        v = v[2:]
    elif len(v) == 11 and v.startswith("0"):
        v = v[1:]
    if not (len(v) == 10 and v.isdigit() and v[0] in "6789"):
        return False
    return len(set(v)) > 2


def aadhaar(value: str) -> bool:
    v = strip_separators(value)
    return len(v) == 12 and v.isdigit() and v[0] not in "01" and verhoeff_valid(v)


_PAN = re.compile(r"^[A-Z]{3}[ABCFGHLJPT][A-Z][0-9]{4}[A-Z]$")


def pan(value: str) -> bool:
    return bool(_PAN.match(value.strip().upper()))


_PASSPORT = re.compile(r"^[A-PR-WY][1-9][0-9]{5}[1-9]$")


def passport(value: str) -> bool:
    """Indian passport: one letter (not Q, X, Z), seven digits, first and last non-zero."""
    return bool(_PASSPORT.match(strip_separators(value).upper()))


_EPIC = re.compile(r"^[A-Z]{3}[0-9]{7}$")


def voter_id(value: str) -> bool:
    v = strip_separators(value).upper()
    return bool(_EPIC.match(v)) and v[3:] != "0000000"


STATE_CODES = {
    "AN", "AP", "AR", "AS", "BR", "CH", "CG", "DD", "DL", "DN", "GA", "GJ", "HP", "HR", "JH", "JK", "KA", "KL",
    "LA", "LD", "MH", "ML", "MN", "MP", "MZ", "NL", "OD", "OR", "PB", "PY", "RJ", "SK", "TN", "TR", "TS", "UK",
    "UP", "WB",
}
_DL = re.compile(r"^([A-Z]{2})([0-9]{2})([0-9]{4})([0-9]{7})$")


def driving_licence(value: str) -> bool:
    """SS RR YYYY NNNNNNN (state, RTO, year of issue, serial)."""
    m = _DL.match(strip_separators(value).upper())
    if not m:
        return False
    year = int(m.group(3))
    return m.group(1) in STATE_CODES and m.group(2) != "00" and 1950 <= year <= date.today().year


_GSTIN_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_GSTIN = re.compile(r"^[0-3][0-9][A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")


def gstin_check_char(first14: str) -> str:
    total, factor = 0, 2
    for ch in reversed(first14):
        product = _GSTIN_ALPHABET.index(ch) * factor
        total += product // 36 + product % 36
        factor = 1 if factor == 2 else 2
    return _GSTIN_ALPHABET[(36 - total % 36) % 36]


def gstin(value: str) -> bool:
    v = value.strip().upper()
    if not _GSTIN.match(v) or not 1 <= int(v[:2]) <= 38:
        return False
    return gstin_check_char(v[:14]) == v[14]


_IFSC = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")


def ifsc(value: str) -> bool:
    return bool(_IFSC.match(value.strip().upper()))


def bank_account(value: str) -> bool:
    """Indian bank accounts are 9-18 digits. Format only, so rules require header support."""
    v = strip_separators(value)
    return v.isdigit() and 9 <= len(v) <= 18 and len(set(v)) > 1


def _card_network(v: str) -> bool:
    """Issuer prefixes: Visa 4, Mastercard 51-55/2221-2720, RuPay 60/65/81/82/508, Amex 34/37, Diners 36/38.

    Device identifiers such as IMEI (TAC 35/86/01...) and SIM ICCIDs (89...) also pass
    Luhn, so the prefix check matters.
    """
    if v[0] == "4":
        return True
    two, four = int(v[:2]), int(v[:4])
    return (51 <= two <= 55 or 2221 <= four <= 2720 or two in (60, 65, 81, 82, 34, 37, 36, 38)
            or v[:3] == "508")


def card_number(value: str) -> bool:
    v = strip_separators(value)
    return v.isdigit() and 13 <= len(v) <= 19 and _card_network(v) and luhn_valid(v)


UPI_HANDLES = {
    "upi", "ybl", "ibl", "axl", "okaxis", "oksbi", "okhdfcbank", "okicici", "paytm", "apl", "axisbank", "icici",
    "hdfcbank", "sbi", "kotak", "yesbank", "idfcbank", "federal", "barodampay", "pnb", "unionbank", "jupiteraxis",
    "freecharge", "waicici", "wahdfcbank", "airtel", "jio", "slice", "fbl", "rbl", "indus", "aubank", "cnrb",
}
_UPI = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-_]{1,255}@([A-Za-z]{2,64})$")


def upi_id(value: str) -> bool:
    m = _UPI.match(value.strip())
    return bool(m) and m.group(1).lower() in UPI_HANDLES


def pin_code(value: str) -> bool:
    v = strip_separators(value)
    return len(v) == 6 and v.isdigit() and v[0] != "0" and (11 <= int(v[:2]) <= 85 or v[0] == "9")


_LATLON = re.compile(r"^\s*(-?\d{1,2}(?:\.\d+)?)\s*[,;\s]\s*(-?\d{1,3}(?:\.\d+)?)\s*$")


def lat_long_pair(value: str) -> bool:
    m = _LATLON.match(value)
    if not m:
        return False
    lat, lon = float(m.group(1)), float(m.group(2))
    return -90 <= lat <= 90 and -180 <= lon <= 180 and ("." in m.group(1) or "." in m.group(2))


def latitude(value: str) -> bool:
    try:
        return "." in value and -90 <= float(value) <= 90
    except ValueError:
        return False


def longitude(value: str) -> bool:
    try:
        return "." in value and -180 <= float(value) <= 180
    except ValueError:
        return False


def ip_address(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value.strip())
    except ValueError:
        return False
    return not (ip.is_unspecified or ip.is_multicast)


_TEXT_DATE_FORMATS = ("%d %b %Y", "%d %B %Y", "%b %d, %Y", "%d-%b-%Y")
_YMD = re.compile(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$")
_DMY = re.compile(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$")


def parse_date(value: str) -> date | None:
    """ISO / Indian day-first numeric dates, plus a few month-name formats."""
    v = value.strip()
    if len(v) < 6 or len(v) > 20:
        return None
    m = _YMD.match(v)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m = _DMY.match(v)
        if m:
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        elif any(c.isalpha() for c in v):
            for fmt in _TEXT_DATE_FORMATS:
                try:
                    return datetime.strptime(v, fmt).date()
                except ValueError:
                    continue
            return None
        else:
            return None
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def date_of_birth(value: str) -> bool:
    d = parse_date(value)
    return d is not None and 1900 <= d.year and d <= date.today()


def age(value: str) -> bool:
    v = value.strip()
    return v.isdigit() and 0 < int(v) <= 120


GENDERS = {"m", "f", "male", "female", "other", "o", "transgender", "non-binary", "nonbinary", "purush", "mahila", "x"}


def gender(value: str) -> bool:
    return value.strip().lower() in GENDERS


ADDRESS_TOKENS = {
    "road", "rd", "street", "st", "nagar", "colony", "lane", "ln", "sector", "block", "marg", "layout", "apartment",
    "apartments", "apt", "flat", "floor", "house", "h.no", "plot", "phase", "cross", "main", "near", "opp",
    "society", "chowk", "gali", "village", "post", "taluk", "district", "tower", "residency", "enclave", "vihar",
    "bagh", "puram", "pet", "peth", "halli", "pally", "wadi", "ganj", "bazar", "market", "complex", "building",
}


def address(value: str) -> bool:
    v = value.lower()
    tokens = set(re.findall(r"[a-z.]+", v))
    return bool(re.search(r"\d", v)) and len(v) >= 12 and bool(tokens & ADDRESS_TOKENS)


INDIAN_PLACES = {
    "mumbai", "delhi", "new delhi", "bengaluru", "bangalore", "hyderabad", "ahmedabad", "chennai", "kolkata", "surat",
    "pune", "jaipur", "lucknow", "kanpur", "nagpur", "indore", "thane", "bhopal", "visakhapatnam", "patna", "vadodara",
    "ghaziabad", "ludhiana", "agra", "nashik", "faridabad", "meerut", "rajkot", "varanasi", "srinagar", "aurangabad",
    "dhanbad", "amritsar", "allahabad", "prayagraj", "ranchi", "howrah", "coimbatore", "jabalpur", "gwalior",
    "vijayawada", "jodhpur", "madurai", "raipur", "kota", "guwahati", "chandigarh", "solapur", "mysuru", "mysore",
    "tiruchirappalli", "bareilly", "aligarh", "tiruppur", "gurgaon", "gurugram", "noida", "kochi", "cochin",
    "thiruvananthapuram", "trivandrum", "dehradun", "bhubaneswar", "salem", "warangal", "mangaluru", "mangalore",
    "udaipur", "jamshedpur", "puducherry", "shimla", "goa", "panaji", "siliguri", "nellore", "belgaum", "hubli",
    # states and union territories
    "maharashtra", "karnataka", "tamil nadu", "kerala", "telangana", "andhra pradesh", "gujarat", "rajasthan",
    "uttar pradesh", "madhya pradesh", "west bengal", "bihar", "odisha", "punjab", "haryana", "assam", "jharkhand",
    "chhattisgarh", "uttarakhand", "himachal pradesh", "jammu and kashmir", "tripura", "meghalaya", "manipur",
    "nagaland", "mizoram", "arunachal pradesh", "sikkim", "ladakh",
}


def indian_place(value: str) -> bool:
    return value.strip().lower() in INDIAN_PLACES


# A compact dictionary of common Indian given names and surnames, used only as a
# validator for name-shaped values. Matching any token is enough.
NAME_TOKENS = set("""
aarav aditya amit amitabh ananya anil anita anjali ankit anushka arjun arun asha ashok bhavna deepak deepika dev
divya gaurav geeta harish isha ishaan jaya karan kavita kiran krishna lakshmi manish meena mohan nandini neha nikhil
nisha pooja prakash pranav priya rahul raj rajesh rakesh ramesh ravi rekha rohit sachin sandeep sanjay sarita shalini
shreya shruti simran sneha sonia sunil sunita suresh swati tanvi uma varun vijay vikram vinod yash zoya aisha farhan
imran irfan javed nasreen salman sameer shabana tariq zainab harpreet gurpreet manpreet jaspreet simranjeet baldev
balwinder kuldeep lalit mahesh mukesh naresh pankaj rajiv sudhir sushil umesh vivek yogesh abhishek akash alok
aman anand arvind ashwin bharat chetan dinesh ganesh girish gopal hari jagdish kamal kishore manoj mayank naveen
nitin prateek rajendra ramya rashmi ritu sapna savita seema shweta smita sudha usha vandana vidya aarti bhavya
charu diya gauri hema ira jyoti kajal komal madhu mansi megha monika nidhi parul preeti radha riya sakshi shikha
tara trisha vaishali kavya saanvi myra aadhya ishita navya kiara advik vihaan reyansh ayaan atharv shaurya
sharma verma gupta singh kumar patel shah mehta joshi iyer iyengar nair menon pillai reddy rao naidu chowdhury
choudhary banerjee chatterjee mukherjee ghosh bose das dutta sen roy kapoor khanna malhotra arora bhatia chopra
saxena srivastava mishra tiwari pandey dubey trivedi chaturvedi agarwal aggarwal jain bansal goyal mittal kulkarni
deshpande patil pawar jadhav shinde gaikwad more naik desai bhatt pathak yadav chauhan thakur rathore rajput
sinha prasad jha thakkar parikh modi kaur gill sandhu sidhu dhillon grewal khan ahmed ali hussain siddiqui qureshi
ansari sheikh syed fernandes dsouza pinto rodrigues mathew thomas varghese joseph george kurian chacko abraham
krishnan subramanian venkatesh raman murthy hegde shetty kamath bhat gowda acharya mohanty panda sahu behera
""".split())


ORG_TOKENS = {"pvt", "ltd", "llp", "limited", "private", "inc", "corp", "corporation", "co", "company", "works",
              "industries", "enterprises", "systems", "electronics", "technologies", "solutions", "traders", "agency",
              "associates", "labs", "laboratory", "group", "services", "precision", "composites", "engineering"}


def person_name(value: str) -> bool:
    tokens = re.findall(r"[A-Za-z]+", value.lower())
    if not 1 <= len(tokens) <= 5 or any(ch.isdigit() for ch in value):
        return False
    if any(t in ORG_TOKENS for t in tokens):  # "Sharma Precision Works Pvt Ltd" is a firm, not a person
        return False
    return any(t in NAME_TOKENS for t in tokens)


VALIDATORS = {
    "email": email,
    "indian_mobile": indian_mobile,
    "aadhaar": aadhaar,
    "pan": pan,
    "passport": passport,
    "voter_id": voter_id,
    "driving_licence": driving_licence,
    "gstin": gstin,
    "ifsc": ifsc,
    "bank_account": bank_account,
    "card_number": card_number,
    "upi_id": upi_id,
    "pin_code": pin_code,
    "lat_long_pair": lat_long_pair,
    "latitude": latitude,
    "longitude": longitude,
    "ip_address": ip_address,
    "date_of_birth": date_of_birth,
    "age": age,
    "gender": gender,
    "address": address,
    "indian_place": indian_place,
    "person_name": person_name,
}

# Validators backed by a real checksum. A high pass rate here can override a
# negative-header penalty, because random data rarely passes these checks.
CHECKSUM_VALIDATORS = {"aadhaar", "gstin", "card_number"}
