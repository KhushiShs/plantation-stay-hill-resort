"""Unit tests and integration tests for phone number validation."""
import pytest
import re
from fastapi.testclient import TestClient

from app.validators import validate_phone_number
from app.main import app
from app.db import get_db


def test_valid_indian_numbers():
    valid_numbers = [
        "+91 98765 43210",
        "+919876543210",
        "+91-98765-43210",
        "+91 8123456789",
        "+91 7001234567",
        "+91 6398765432",
    ]
    for num in valid_numbers:
        is_valid, err, cleaned = validate_phone_number(num)
        assert is_valid, f"Expected {num} to be valid, got error: {err}"
        assert err is None
        assert cleaned.startswith("+91")
        assert len(cleaned) == 13


def test_valid_foreign_numbers():
    valid_foreign = [
        "+1 415 555 2671",      # US
        "+44 20 7946 0958",     # UK
        "+65 6789 0123",        # Singapore
        "+971 50 123 4567",     # UAE
        "+49 30 123456",        # Germany
    ]
    for num in valid_foreign:
        is_valid, err, cleaned = validate_phone_number(num)
        assert is_valid, f"Expected {num} to be valid, got: {err}"
        assert err is None
        assert cleaned.startswith("+")


def test_phone_missing_plus_prefix():
    invalid_cases = [
        "9876543210",
        "919876543210",
        "09876543210",
    ]
    for num in invalid_cases:
        is_valid, err, _ = validate_phone_number(num)
        assert not is_valid
        assert "must include country code starting with '+'" in err


def test_phone_contains_letters():
    invalid_cases = [
        "+91 98765 4321A",
        "+1 415 CALL ME",
        "+91-PHONE-1234",
    ]
    for num in invalid_cases:
        is_valid, err, _ = validate_phone_number(num)
        assert not is_valid
        assert "only numbers" in err


def test_phone_too_short():
    invalid_cases = [
        "+91",
        "+1234",
        "+441234",
    ]
    for num in invalid_cases:
        is_valid, err, _ = validate_phone_number(num)
        assert not is_valid
        assert "too short" in err


def test_phone_too_long():
    too_long = "+12345678901234567"
    is_valid, err, _ = validate_phone_number(too_long)
    assert not is_valid
    assert "too long" in err


def test_invalid_indian_mobile_rules():
    is_valid, err, _ = validate_phone_number("+91 98765 4321")
    assert not is_valid
    assert "exactly 10 digits" in err

    is_valid, err, _ = validate_phone_number("+91 98765 432109")
    assert not is_valid
    assert "exactly 10 digits" in err

    is_valid, err, _ = validate_phone_number("+91 58765 43210")
    assert not is_valid
    assert "start with 6, 7, 8, or 9" in err

    is_valid2, err2, _ = validate_phone_number("+91 12345 67890")
    assert not is_valid2
    assert "start with 6, 7, 8, or 9" in err2


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def get_csrf_token(client):
    res_book = client.get("/book?room_type_id=estate-room&rate_plan_id=room_only&check_in=2026-12-01&check_out=2026-12-03")
    assert res_book.status_code == 200
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', res_book.text)
    assert m, "CSRF token not found in response HTML"
    return m.group(1)


def test_booking_step2_phone_validation_inline_error(client, db_session):
    """
    Booking Step 2 phone validation:
    - Missing + country code returns 400 with inline error beside field.
    - Preserves entered guest details and inputs.
    - Valid Indian / foreign numbers succeed (redirect to /pay).
    """
    csrf = get_csrf_token(client)

    # 1. Invalid phone: missing + prefix
    bad_payload = {
        "csrf_token": csrf,
        "room_type_id": "estate-room",
        "rate_plan_id": "room_only",
        "check_in": "2026-12-01",
        "check_out": "2026-12-03",
        "guest_name": "Anita Sharma",
        "guest_email": "anita@example.com",
        "guest_phone": "9876543210",
        "dpdp_consent": "true"
    }
    res_bad = client.post("/book/hold", data=bad_payload)
    assert res_bad.status_code == 400
    assert "Please correct the phone number below" in res_bad.text
    # Jinja2 auto-escapes single quotes to &#39;
    assert "must include country code starting with" in res_bad.text
    assert "&#39;+&#39;" in res_bad.text or "'+'" in res_bad.text
    assert 'value="Anita Sharma"' in res_bad.text
    assert 'value="anita@example.com"' in res_bad.text
    assert 'value="9876543210"' in res_bad.text

    # 2. Invalid Indian phone: starts with 4 instead of 6-9
    bad_indian_payload = bad_payload.copy()
    bad_indian_payload["guest_phone"] = "+91 48765 43210"
    res_bad2 = client.post("/book/hold", data=bad_indian_payload)
    assert res_bad2.status_code == 400
    assert "start with 6, 7, 8, or 9" in res_bad2.text

    # 3. Valid Indian phone: succeeds with 303 redirect to /pay
    valid_payload = bad_payload.copy()
    valid_payload["guest_phone"] = "+91 98765 43210"
    res_ok = client.post("/book/hold", data=valid_payload, follow_redirects=False)
    assert res_ok.status_code == 303
    assert "/pay" in res_ok.headers["location"]


def test_enquire_form_phone_validation_inline_error(client, db_session):
    """
    /enquire form phone validation:
    - Missing + returns 400 with inline error and keeps entered values.
    - Valid +44 or +91 phone succeeds.
    """
    res_form = client.get("/enquire")
    m_csrf = re.search(r'name="csrf_token"\s+value="([^"]+)"', res_form.text)
    m_token = re.search(r'name="form_token"\s+value="([^"]+)"', res_form.text)
    assert m_csrf and m_token
    csrf = m_csrf.group(1)
    ftoken = m_token.group(1)

    # 1. Invalid phone without +
    bad_enq = {
        "csrf_token": csrf,
        "form_token": ftoken,
        "sender_name": "Robert Smith",
        "sender_contact": "9876543210",
        "raw_message": "Need venue for wedding next year.",
        "dpdp_consent": "yes"
    }
    res_bad = client.post("/enquire", data=bad_enq)
    assert res_bad.status_code == 400
    assert "Please correct the contact number below" in res_bad.text
    # Jinja2 auto-escapes single quotes to &#39;
    assert "must include country code starting with" in res_bad.text
    assert "&#39;+&#39;" in res_bad.text or "'+'" in res_bad.text
    assert 'value="Robert Smith"' in res_bad.text

    # 2. Valid foreign phone
    valid_enq = bad_enq.copy()
    valid_enq["sender_contact"] = "+44 20 7946 0958"
    res_ok = client.post("/enquire", data=valid_enq)
    assert res_ok.status_code == 200
    assert "Enquiry Received" in res_ok.text
