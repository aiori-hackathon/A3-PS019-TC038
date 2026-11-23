from privacytwin.detect import (classify_column, k_anonymity, keyword_hit, normalise_header, record_age_histogram,
                                rescore, rule_hashes)
from privacytwin.masking import fingerprint, mask, mask_free_text, overlap, shape
from privacytwin.rules import default_ruleset
from privacytwin.synth import Gen

RS = default_ruleset()
g = Gen(3)


def classify(name, values):
    return classify_column("t", name, values, RS, "salt")


def test_header_normalisation():
    assert normalise_header("customerMobileNo")[1] == ["customer", "mobile", "no"]
    assert normalise_header("DLNumber")[1] == ["dl", "number"]
    assert normalise_header("addr1")[1] == ["addr", "1"]
    assert normalise_header("Cust-Nm")[1] == ["cust", "nm"]


def test_keyword_matching_tokens_and_compounds():
    assert keyword_hit(["mobile_no"], ["cust", "mobile", "no"]) == "mobile_no"
    assert keyword_hit(["email"], ["emailaddress"]) == "email"
    assert keyword_hit(["ph"], ["photo"]) is None  # short keywords match whole tokens only
    assert keyword_hit(["name"], ["username"]) is None


def test_strong_signals_give_high_confidence():
    r = classify("cust_mob", [g.mobile() for _ in range(200)])
    assert (r["class"], r["band"]) == ("CONTACT", "HIGH")
    assert r["signals"]["header"] == 1.0 and r["signals"]["validator"] > 0.9


def test_misleading_header_detected_from_values():
    r = classify("col_7", [g.email() for _ in range(200)])
    assert r["class"] == "CONTACT" and r["band"] == "MEDIUM"
    assert "gives no hint" in r["rationale"]


def test_rationale_is_plain_and_ends_with_retention_statement():
    r = classify("aadhaar_no", [g.aadhaar() for _ in range(100)])
    assert r["rationale"].endswith("Raw values were not retained.")
    assert "Verhoeff" in r["rationale"]


def test_negative_rules_cut_false_positives():
    assert classify("order_id", [g.digits(10, "6789") for _ in range(200)])["class"] == "NOT_PERSONAL"
    assert classify("txn_ref", [g.digits(12, "23456789") for _ in range(200)])["class"] == "NOT_PERSONAL"
    assert classify("sku", [g.voter_id() for _ in range(200)])["class"] == "NOT_PERSONAL"


def test_twelve_digits_failing_verhoeff_are_not_aadhaar():
    from privacytwin.validators import verhoeff_valid
    vals = [x for x in (g.digits(12, "23456789") for _ in range(400)) if not verhoeff_valid(x)][:200]
    assert classify("col_5", vals)["class"] == "NOT_PERSONAL"


def test_requires_header_rules():
    pins = [g.pin() for _ in range(100)]
    assert classify("pincode", pins)["class"] == "LOCATION"
    assert classify("otp", pins)["class"] == "NOT_PERSONAL"


def test_header_contradicted_by_values_is_not_a_candidate():
    assert classify("long_description", ["nice product"] * 50)["class"] == "NOT_PERSONAL"


def test_embedded_contacts_in_free_text():
    vals = [f"call me on {g.mobile()} thanks" if i % 3 == 0 else "where is my refund" for i in range(120)]
    r = classify("message", vals)
    assert r["class"] == "CONTACT" and "embedded" in r["notes"]
    assert all("[phone]" in e for e in r["masked_examples"])


def test_embedded_search_ignores_digits_inside_longer_numbers():
    vals = [g.digits(15, "3") for _ in range(100)]
    assert classify("device", vals)["class"] == "NOT_PERSONAL"


def test_constant_prefix_codes_are_not_government_ids():
    vals = [f"ACC{g.digits(7, '123456789')}" for _ in range(200)]
    assert classify("account_ref_code", vals)["class"] == "NOT_PERSONAL"


def test_timestamps_and_empty_columns():
    assert classify("createdAt", ["2024-01-02 10:11:12"] * 30)["class"] == "NOT_PERSONAL"
    r = classify("email", [None, "", "  "] * 10)
    assert r["profile"]["non_null"] == 0 and r["class"] == "CONTACT" and r["band"] == "LOW"


def test_profile_fields():
    r = classify("amount", ["10.5", "20.25", None, "30.00"])
    p = r["profile"]
    assert p["inferred_type"] == "decimal" and p["null_pct"] == 25.0 and p["sample_size"] == 4


def test_masking_never_returns_raw_values():
    raw = {"email": "ravi.kumar@example.in", "mobile_in": "9876543210", "aadhaar": g.aadhaar(), "pan": "ABCPK1234F",
           "card_number": "4111111111111111", "person_name": "Ravi Kumar", "address": "Flat 12, 4th Cross, Bengaluru",
           "date_of_birth": "1990-04-17", "bank_account": "50100012345678", "upi_id": "ravi.k@okaxis"}
    for rule, value in raw.items():
        assert mask(value, rule) != value
        assert value not in mask(value, rule)
    assert mask("ravi.kumar@example.in", "email") == "ra****@example.in"
    assert mask("4111111111111111", "card_number") == "XXXX-XXXX-XXXX-1111"
    assert mask("free text tomorrow at 5", "email") == shape("free text tomorrow at 5")


def test_free_text_mask_tags_identifiers():
    out = mask_free_text("Mail a.b@x.com or call +91 98765 43210")
    assert "[email]" in out and "[phone]" in out and "x.com" not in out


def test_fingerprint_overlap():
    a = [g.email() for _ in range(300)]
    fa, fb = fingerprint(a, "s"), fingerprint(a[:200] + [g.email() for _ in range(100)], "s")
    assert len(fa) == 32 and overlap(fa, fb) > 0.3
    assert overlap(fa, fingerprint([g.email() for _ in range(300)], "s")) < 0.15
    assert fingerprint(a, "s") != fingerprint(a, "other-salt")


def test_k_anonymity_aggregates():
    rows = [{"dob": "1990-01-01", "gender": "M", "pin": "560034"}, {"dob": "1990-01-01", "gender": "M", "pin": "560034"},
            {"dob": "1985-05-05", "gender": "F", "pin": "110001"}]
    k = k_anonymity(rows, {"dob": "dob", "gender": "gender", "pin": "pin"})
    assert k["exact"]["min_k"] == 1 and round(k["exact"]["unique_pct"]) == 33
    assert k_anonymity(rows, {"dob": "dob"}) is None


def test_record_age_histogram():
    rows = [{"created_at": g.date_between(2000)} for _ in range(50)]
    h = record_age_histogram(rows, ["created_at"])
    assert sum(h["counts"]) == 50 and h["oldest_days"] <= 2000


def test_rescore_matches_scan_for_unchanged_rules_and_flags_edits():
    vals = [g.mobile() for _ in range(100)]
    r = classify("cust_mob", vals)
    same = rescore("cust_mob", r["profile"], r["rule_signals"], RS, rule_hashes(RS))
    assert same["class"] == r["class"] and abs(same["confidence"] - r["confidence"]) < 1e-6 and not same["approximate"]
    edited = default_ruleset()
    for rule in edited["rules"]:
        if rule["id"] == "mobile_in":
            rule["header_keywords"] = ["zzz"]
    res = rescore("cust_mob", r["profile"], r["rule_signals"], edited, rule_hashes(RS))
    assert res["confidence"] < r["confidence"]
    edited["rules"][1]["value_regex"] = r"\d+"
    assert rescore("cust_mob", r["profile"], r["rule_signals"], edited, rule_hashes(RS))["approximate"]
