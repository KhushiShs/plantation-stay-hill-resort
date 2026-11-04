"""Regression tests for payment page, payment failure retry, and invalid phone rendering."""
import re
import pytest
from datetime import date, timedelta, datetime, timezone
from fastapi.testclient import TestClient

from app.main import app
from app.db import get_db
from app.models import Booking, RoomType, RatePlan


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def create_sample_held_booking(db_session) -> Booking:
    today = date.today()
    b = Booking(
        reference="BK-REGRESS-PAY",
        room_type_id="estate-room",
        rate_plan_id="room_only",
        check_in=today + timedelta(days=10),
        check_out=today + timedelta(days=12),
        num_guests=2,
        num_rooms=1,
        guest_name="Kavita Rao",
        guest_email="kavita@example.com",
        guest_phone="+91 98765 43210",
        room_total_paise=1400000,
        discount_paise=0,
        gst_paise=168000,
        grand_total_paise=1568000,
        dpdp_consent=True,
        hold_expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        status="held"
    )
    db_session.add(b)
    db_session.commit()
    db_session.refresh(b)
    return b


def test_render_payment_page_200_and_expected_text(client, db_session):
    """
    Renders /book/{reference}/pay:
    - Status 200
    - Shows room name, dates, nights, guests count
    - Shows countdown timer ("Hold expires in")
    - Shows the 3 buttons: 'Pay Rs ... (test)', 'Payment fails', 'Cancel booking'
    """
    booking = create_sample_held_booking(db_session)
    # Simulate session cookie holding reference
    client.cookies.set("plantation_session", "")
    with client:
        # Step through hold or establish session
        res_book = client.get("/book?room_type_id=estate-room&rate_plan_id=room_only&check_in=2026-12-01&check_out=2026-12-03")
        csrf = re.search(r'name="csrf_token"\s+value="([^"]+)"', res_book.text).group(1)
        payload = {
            "csrf_token": csrf,
            "room_type_id": "estate-room",
            "rate_plan_id": "room_only",
            "check_in": "2026-12-01",
            "check_out": "2026-12-03",
            "guest_name": "Kavita Rao",
            "guest_email": "kavita@example.com",
            "guest_phone": "+91 98765 43210",
            "dpdp_consent": "true"
        }
        res_hold = client.post("/book/hold", data=payload, follow_redirects=False)
        assert res_hold.status_code == 303
        pay_url = res_hold.headers["location"]

        res = client.get(pay_url)
        assert res.status_code == 200

        # Expected texts
        assert "HOLD EXPIRES IN" in res.text
        assert "Estate Room" in res.text
        assert "Pay " in res.text
        assert "(test)" in res.text
        assert "Payment fails" in res.text
        assert "Cancel booking" in res.text
        assert "Confirms your booking instantly" in res.text
        assert "Releases the 10-minute hold immediately" in res.text


def test_render_payment_failed_retry_page_200_and_expected_text(client, db_session):
    """
    Renders /book/{reference}/pay?failed=1:
    - Status 200
    - Shows payment failure warning banner
    - Retains hold and displays remaining hold time notice
    - Retains retry button ("Pay Rs ... (test)")
    """
    with client:
        res_book = client.get("/book?room_type_id=estate-room&rate_plan_id=room_only&check_in=2026-12-01&check_out=2026-12-03")
        csrf = re.search(r'name="csrf_token"\s+value="([^"]+)"', res_book.text).group(1)
        payload = {
            "csrf_token": csrf,
            "room_type_id": "estate-room",
            "rate_plan_id": "room_only",
            "check_in": "2026-12-01",
            "check_out": "2026-12-03",
            "guest_name": "Kavita Rao",
            "guest_email": "kavita@example.com",
            "guest_phone": "+91 98765 43210",
            "dpdp_consent": "true"
        }
        res_hold = client.post("/book/hold", data=payload, follow_redirects=False)
        assert res_hold.status_code == 303
        pay_url = res_hold.headers["location"]

        res = client.get(f"{pay_url}?failed=1")
        assert res.status_code == 200

        assert "Payment did not go through." in res.text
        assert "Your room remains held for" in res.text
        assert "more minutes" in res.text
        assert "Pay " in res.text
        assert "Cancel booking" in res.text


def test_render_enquire_invalid_phone_retains_and_renders_error(client, db_session):
    """
    Submits invalid phone to /enquire:
    - Status 200/400 (returns form with inline error beside field)
    - Shows "Please correct the contact number below."
    - Shows country code requirement message
    - Retains entered sender name and contact
    """
    res_form = client.get("/enquire")
    assert res_form.status_code == 200
    m_csrf = re.search(r'name="csrf_token"\s+value="([^"]+)"', res_form.text)
    m_token = re.search(r'name="form_token"\s+value="([^"]+)"', res_form.text)
    assert m_csrf and m_token
    csrf = m_csrf.group(1)
    ftoken = m_token.group(1)

    bad_payload = {
        "csrf_token": csrf,
        "form_token": ftoken,
        "sender_name": "Deepak Kumar",
        "sender_contact": "9876543210",  # missing + country code
        "raw_message": "Looking for conference lawn booking.",
        "dpdp_consent": "yes"
    }
    res = client.post("/enquire", data=bad_payload)
    # The form response is returned with the error (HTTP 400 Bad Request)
    assert res.status_code in (200, 400)
    assert "Please correct the contact number below." in res.text
    assert "must include country code starting with" in res.text
    assert "&#39;+&#39;" in res.text or "'+'" in res.text
    assert 'value="Deepak Kumar"' in res.text
    assert 'value="9876543210"' in res.text


def test_render_booking_step2_invalid_phone_retains_and_renders_error(client, db_session):
    """
    Submits invalid phone to /book/hold:
    - Status 400 (or 200) rendering Step 2 with inline error
    - Shows "Please correct the phone number below."
    - Shows country code requirement message
    - Retains entered guest details
    """
    res_book = client.get("/book?room_type_id=estate-room&rate_plan_id=room_only&check_in=2026-12-01&check_out=2026-12-03")
    assert res_book.status_code == 200
    m_csrf = re.search(r'name="csrf_token"\s+value="([^"]+)"', res_book.text)
    assert m_csrf
    csrf = m_csrf.group(1)

    bad_payload = {
        "csrf_token": csrf,
        "room_type_id": "estate-room",
        "rate_plan_id": "room_only",
        "check_in": "2026-12-01",
        "check_out": "2026-12-03",
        "guest_name": "Rohan Mehra",
        "guest_email": "rohan@example.com",
        "guest_phone": "9876543210",  # missing +
        "dpdp_consent": "true"
    }
    res = client.post("/book/hold", data=bad_payload)
    assert res.status_code in (200, 400)
    assert "Please correct the phone number below." in res.text
    assert "must include country code starting with" in res.text
    assert "&#39;+&#39;" in res.text or "'+'" in res.text
    assert 'value="Rohan Mehra"' in res.text
    assert 'value="rohan@example.com"' in res.text
    assert 'value="9876543210"' in res.text

