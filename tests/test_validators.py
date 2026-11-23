import pytest

from privacytwin import validators as v
from privacytwin.synth import Gen

g = Gen(1)

CASES = {
    "email": (["ravi.kumar@example.in", "a@b.co", "x_y+tag@mail.example.com"],
              ["ravi@", "@example.in", "ravi..k@example.in", "ravi@example", "not an email"]),
    "indian_mobile": (["9876543210", "+91 98765 43210", "09876543210", "+91-9876543210", "919876543210"],
                      ["5876543210", "98765", "9999999999", "+44 7911 123456", "12345678901"]),
    "aadhaar": ([g.aadhaar(), g.aadhaar(spaced=True)],
                ["123456789012", "012345678901", "234567890120", "23456789012"]),
    "pan": (["ABCPK1234F", "abcpk1234f"], ["ABCDE1234F", "ABCP1234F", "1BCPK1234F"]),
    "passport": (["K1234567", "A2345678"], ["Q1234567", "K0234567", "K123456", "12345678"]),
    "voter_id": (["XYZ1234567", "abc7654321"], ["XY1234567", "XYZ0000000", "XYZ123456A"]),
    "driving_licence": (["MH1220150012345", "KA-01 2019 0001234"], ["ZZ1220150012345", "MH0020150012345", "MH1218000012345"]),
    "gstin": ([g.gstin(), "27AAPFU0939F1ZV"], ["27AAPFU0939F1ZX", "99AAPFU0939F1ZV", "27AAPFU0939F1Z"]),
    "ifsc": (["HDFC0001234", "sbin0000123"], ["HDFC1001234", "HDF0001234", "HDFC00012345"]),
    "bank_account": (["50100012345678", "123456789"], ["12345678", "1234567890123456789", "000000000000"]),
    "card_number": (["4111 1111 1111 1111", "5500-0000-0000-0004", g.card()],
                    ["4111 1111 1111 1112", "1234567812345678", "356938035643809"]),
    "upi_id": (["ravi.k@okaxis", "9876543210@ybl"], ["ravi@gmail", "ravi.k@unknownbank", "ravi@okaxis.com"]),
    "pin_code": (["560034", "110001"], ["056003", "5600341", "000000", "86000a"]),
    "lat_long_pair": (["12.9716, 77.5946", "-33.86;151.2"], ["12,77", "123.4, 77.5", "12.97, 190.1"]),
    "latitude": (["12.9716", "-45.5"], ["12", "95.1", "abc"]),
    "longitude": (["77.5946", "-170.25"], ["77", "190.5"]),
    "ip_address": (["203.0.113.42", "2001:db8::1"], ["256.1.1.1", "1.2.3", "0.0.0.0"]),
    "date_of_birth": (["1990-04-17", "17/04/1990", "17.04.1990", "17 Apr 1990"], ["2990-01-01", "1899-12-31", "31/02/1990", "hello"]),
    "age": (["34", "1", "120"], ["0", "121", "-4", "3.5"]),
    "gender": (["Male", "f", "Other"], ["Yes", "Unknown", "1"]),
    "address": (["Flat 12, 4th Cross, Indiranagar, Bengaluru", "221B MG Road Pune"], ["Bengaluru", "Call me back", "12345"]),
    "indian_place": (["Mumbai", "tamil nadu"], ["Atlantis", "India"]),
    "person_name": (["Rahul Sharma", "PRIYA IYER", "Imran Khan"], ["Gold Plan", "Rahul 123", "Steel Bottle"]),
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_validator_accepts_valid(name):
    fn = v.VALIDATORS[name]
    good, _ = CASES[name]
    for value in good:
        nv = v.strip_separators(value) if name in ("aadhaar", "bank_account") else value
        assert fn(nv), f"{name} should accept {value!r}"


@pytest.mark.parametrize("name", sorted(CASES))
def test_validator_rejects_invalid(name):
    fn = v.VALIDATORS[name]
    _, bad = CASES[name]
    for value in bad:
        assert not fn(value), f"{name} should reject {value!r}"


def test_every_validator_is_covered():
    assert set(CASES) == set(v.VALIDATORS)


def test_verhoeff_roundtrip():
    for base in ("23456789012", "99999999999", "20000000000"):
        assert v.verhoeff_valid(base + v.verhoeff_check_digit(base))
        wrong = str((int(v.verhoeff_check_digit(base)) + 1) % 10)
        assert not v.verhoeff_valid(base + wrong)


def test_luhn_roundtrip():
    assert v.luhn_valid("79927398713")
    assert not v.luhn_valid("79927398710")
    assert v.luhn_valid("411111111111111" + v.luhn_check_digit("411111111111111"))


def test_card_prefix_rejects_device_ids():
    imei_like = "35693803564380" + v.luhn_check_digit("35693803564380")
    iccid_like = "899100000000000000" + v.luhn_check_digit("899100000000000000")
    assert v.luhn_valid(imei_like) and not v.card_number(imei_like)
    assert v.luhn_valid(iccid_like) and not v.card_number(iccid_like)


def test_gstin_check_char():
    assert v.gstin_check_char("27AAPFU0939F1Z") == "V"


def test_parse_date_formats():
    assert v.parse_date("1990-04-17").isoformat() == "1990-04-17"
    assert v.parse_date("17/04/1990").isoformat() == "1990-04-17"
    assert v.parse_date("17 April 1990").isoformat() == "1990-04-17"
    assert v.parse_date("31/02/1990") is None
    assert v.parse_date("12345") is None
