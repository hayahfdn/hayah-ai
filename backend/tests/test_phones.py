"""Phone number normalisation (E.164) with the original kept for review."""
import pytest

from app.services.phones import normalize
from tests.conftest import login


@pytest.mark.parametrize("raw,country,e164", [
    ("+44 07712345678", None, "+447712345678"),       # extra local 0 after the country code
    ("+447712345678", None, "+447712345678"),          # already international: kept
    ("0791234567", "JO", "+962791234567"),             # local + country chosen
    ("0791234567", "الأردن", "+962791234567"),         # country by Arabic name
    ("00962 79 123 4567", None, "+962791234567"),      # 00 prefix
    ("+962 0791234567", None, "+962791234567"),
    ("0501234567", "Saudi Arabia", "+966501234567"),
    ("050 123 4567", "UAE", "+971501234567"),
    ("33123456", "QA", "+97433123456"),
    ("+965 5123 4567", None, "+96551234567"),
    ("٠٧٩١٢٣٤٥٦٧", "JO", "+962791234567"),             # Arabic-Indic digits
])
def test_valid_numbers(raw, country, e164):
    r = normalize(raw, country)
    assert r["status"] == "valid" and r["e164"] == e164 and r["original"] == raw and r["whatsapp_ok"]


def test_local_without_country_is_not_guessed():
    r = normalize("0791234567")
    assert r["status"] == "needs_country" and r["e164"] is None


def test_country_taken_from_same_number_in_international_form():
    r = normalize("07712345678", None, hints=["+447712345678"])
    assert r["e164"] == "+447712345678"
    # a different number on the order is not used as a hint
    assert normalize("0791234567", None, hints=["+447712345678"])["status"] == "needs_country"


def test_invalid_numbers_are_flagged_not_fixed():
    # Hayah's example "+44 0771234567" has one digit too few for a UK mobile.
    r = normalize("+44 0771234567")
    assert r["status"] == "invalid" and r["e164"] is None
    assert normalize("12")["status"] == "invalid"
    assert normalize("")["status"] == "empty"


def test_project_keeps_original_and_stores_e164(client, seeded):
    staff = login(client, "staff@hayah.local")
    r = client.post("/api/projects", headers=staff, json={"well_id": 8101, "customer_phone": "0791234567"})
    assert r.status_code == 201
    p = r.json()
    assert p["customer_phone"] == "0791234567" and p["customer_phone_status"] == "needs_country" and not p["customer_phone_e164"]
    p = client.patch("/api/projects/8101", headers=staff, json={"customer_phone_country": "jo"}).json()
    assert p["customer_phone"] == "0791234567" and p["customer_phone_e164"] == "+962791234567"
    assert p["customer_phone_country"] == "JO" and p["customer_phone_status"] == "valid"


def test_phone_check_endpoint(client, seeded):
    staff = login(client, "staff@hayah.local")
    r = client.post("/api/phones/check", headers=staff, json={"phone": "+44 07712345678"}).json()
    assert r["e164"] == "+447712345678"
    cs = client.get("/api/phones/countries", headers=staff).json()
    assert [c["code"] for c in cs[:6]] == ["GB", "JO", "SA", "AE", "QA", "KW"]
    assert client.post("/api/phones/check", json={"phone": "1"}).status_code == 401
