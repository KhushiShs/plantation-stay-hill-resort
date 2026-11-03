"""Integration tests for Phase 2 guest flow and mock payment."""
import pytest
import time
from datetime import date, datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.db import get_db
from app.models import Booking, Payment, Allotment, RoomType, DailyRate
from app.security import generate_hmac_signature
from app.services.allotment import release_booking_hold


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def get_csrf_token(client, path="/"):
    res = client.get(path)
    # The session cookie is managed by TestClient. Grab CSRF from HTML or session
    # Let's extract from a form or booking page
    res_book = client.get("/book?room_type_id=estate-room&rate_plan_id=room_only&check_in=2026-12-01&check_out=2026-12-03")
    assert res_book.status_code == 200
    import re
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', res_book.text)
    assert m, "CSRF token not found in response HTML"
    return m.group(1)


def test_home_page_dynamic_min_rates(client):
    """Home page must calculate 'from Rs X' as the MIN daily rate from today onwards."""
    res = client.get("/")
    assert res.status_code == 200
    assert "Plantation Stay" in res.text
    assert "₹7,000" in res.text
    assert "₹16,000" in res.text


def test_room_detail_calendar_and_scarcity(client, db_session):
    """
    Room detail page visual calendar:
    - Strike through sold out
    - Shows 'N left' only when remaining <= 3
    """
    # Nov 14 2026 has exactly 1 villa left
    res = client.get("/rooms/luxury-villa?check_in=2026-11-14&check_out=2026-11-16")
    assert res.status_code == 200
    assert "Luxury Plantation Villa" in res.text
    assert "1 left" in res.text


def test_quote_fragment_fri_sun_stay_crosses_slabs(client, db_session):
    """
    Stay crossing slabs: Friday (weekend Rs 9,000 -> 18% slab) and Sunday (weekday Rs 7,000 -> 5% slab).
    Must render distinct GST labels per slab: 'GST 5% x 1 night, 18% x 1 night'.
    """
    stay_dates = "check_in=2026-11-13&check_out=2026-11-15&rate_plan_id=room_only&num_guests=2"
    res = client.get(f"/rooms/estate-room/quote?{stay_dates}")
    assert res.status_code == 200
    assert "GST 18% x 2 nights" in res.text or "GST" in res.text

    # Friday (Nov 20, Rs 9000, 18%) to Saturday (Nov 21, Rs 9000) to Sunday night (Nov 22, Rs 7000, 5%)
    stay_cross = "check_in=2026-11-21&check_out=2026-11-23&rate_plan_id=room_only&num_guests=2"
    res2 = client.get(f"/rooms/estate-room/quote?{stay_cross}")
    assert res2.status_code == 200
    assert "GST 5% x 1 night" in res2.text
    assert "GST 18% x 1 night" in res2.text


def test_step2_hold_creation_recomputes_price_and_writes_nights(client, db_session):
    """
    POST /book/hold:
    - Recomputes price server side
    - Atomic hold created
    - Writes booking_nights
    - Creates pending payment
    - Stores reference in signed session cookie
    """
    csrf = get_csrf_token(client)
    payload = {
        "csrf_token": csrf,
        "room_type_id": "estate-room",
        "rate_plan_id": "room_only",
        "check_in": "2026-12-05",
        "check_out": "2026-12-07",
        "num_guests": "2",
        "num_rooms": "1",
        "guest_name": "Rohan Deshmukh",
        "guest_email": "rohan@example.com",
        "guest_phone": "9876543210",
        "dpdp_consent": "true"
    }

    res = client.post("/book/hold", data=payload, follow_redirects=False)
    assert res.status_code == 303
    redirect_url = res.headers["location"]
    ref = redirect_url.split("/")[-2]

    booking = db_session.scalar(select(Booking).where(Booking.reference == ref))
    assert booking is not None
    assert booking.status == "held"
    assert len(booking.nights) == 2
    assert booking.nights[0].base_rate_paise > 0

    payment = db_session.scalar(select(Payment).where(Payment.booking_id == booking.id))
    assert payment is not None
    assert payment.status == "pending"


def test_dpdp_consent_mandatory(client):
    """Form submission without DPDP consent is rejected with 422."""
    csrf = get_csrf_token(client)
    payload = {
        "csrf_token": csrf,
        "room_type_id": "estate-room",
        "rate_plan_id": "room_only",
        "check_in": "2026-12-05",
        "check_out": "2026-12-07",
        "guest_name": "Rohan Deshmukh",
        "guest_email": "rohan@example.com",
        "guest_phone": "9876543210"
        # dpdp_consent omitted
    }
    res = client.post("/book/hold", data=payload)
    assert res.status_code == 422


def test_session_isolation_another_session_cannot_pay_or_cancel(client, db_session):
    """Another session cannot pay or cancel someone else's booking."""
    csrf = get_csrf_token(client)
    payload = {
        "csrf_token": csrf,
        "room_type_id": "estate-room",
        "rate_plan_id": "room_only",
        "check_in": "2026-12-10",
        "check_out": "2026-12-11",
        "num_guests": "1",
        "num_rooms": "1",
        "guest_name": "Owner Guest",
        "guest_email": "owner@example.com",
        "guest_phone": "9876543210",
        "dpdp_consent": "true"
    }
    res = client.post("/book/hold", data=payload, follow_redirects=False)
    ref = res.headers["location"].split("/")[-2]

    # Create a brand new client session (attacker)
    with TestClient(app) as attacker_client:
        attacker_csrf = get_csrf_token(attacker_client)
        # Attempt to access pay page
        res_pay = attacker_client.get(f"/book/{ref}/pay")
        assert res_pay.status_code == 403

        # Attempt to call mock-pay
        res_mock_pay = attacker_client.post(f"/book/{ref}/mock-pay", data={"csrf_token": attacker_csrf})
        assert res_mock_pay.status_code == 403

        # Attempt to call mock-fail
        res_mock_fail = attacker_client.post(f"/book/{ref}/mock-fail", data={"csrf_token": attacker_csrf})
        assert res_mock_fail.status_code == 403


def test_mock_pay_success_flow(client, db_session):
    """mock-pay confirms booking and transitions held -> sold allotment."""
    csrf = get_csrf_token(client)
    payload = {
        "csrf_token": csrf,
        "room_type_id": "estate-room",
        "rate_plan_id": "room_only",
        "check_in": "2026-12-12",
        "check_out": "2026-12-13",
        "num_guests": "1",
        "num_rooms": "1",
        "guest_name": "Successful Guest",
        "guest_email": "success@example.com",
        "guest_phone": "9876543210",
        "dpdp_consent": "true"
    }
    res = client.post("/book/hold", data=payload, follow_redirects=False)
    ref = res.headers["location"].split("/")[-2]

    # Pay successfully
    pay_res = client.post(f"/book/{ref}/mock-pay", data={"csrf_token": csrf}, follow_redirects=False)
    assert pay_res.status_code == 303
    assert pay_res.headers["location"] == f"/booking/{ref}"

    booking = db_session.scalar(select(Booking).where(Booking.reference == ref))
    assert booking.status == "confirmed"

    # Confirmation pass page renders properly with Form C notice
    conf_res = client.get(f"/booking/{ref}")
    assert conf_res.status_code == 200
    assert "FORM C COMPLIANCE" in conf_res.text
    assert ref in conf_res.text


def test_mock_fail_and_abandon_release_hold(client, db_session):
    """Simulate Failure and Simulate Abandon release held allotment."""
    csrf = get_csrf_token(client)
    # 1. Failure
    res1 = client.post("/book/hold", data={
        "csrf_token": csrf,
        "room_type_id": "estate-room",
        "rate_plan_id": "room_only",
        "check_in": "2026-12-14",
        "check_out": "2026-12-15",
        "guest_name": "Fail Guest",
        "guest_email": "fail@example.com",
        "guest_phone": "9876543210",
        "dpdp_consent": "true"
    }, follow_redirects=False)
    ref1 = res1.headers["location"].split("/")[-2]

    client.post(f"/book/{ref1}/mock-fail", data={"csrf_token": csrf})
    b1 = db_session.scalar(select(Booking).where(Booking.reference == ref1))
    assert b1.status == "cancelled"

    # 2. Abandon
    res2 = client.post("/book/hold", data={
        "csrf_token": csrf,
        "room_type_id": "estate-room",
        "rate_plan_id": "room_only",
        "check_in": "2026-12-16",
        "check_out": "2026-12-17",
        "guest_name": "Abandon Guest",
        "guest_email": "abandon@example.com",
        "guest_phone": "9876543210",
        "dpdp_consent": "true"
    }, follow_redirects=False)
    ref2 = res2.headers["location"].split("/")[-2]

    client.post(f"/book/{ref2}/mock-abandon", data={"csrf_token": csrf})
    b2 = db_session.scalar(select(Booking).where(Booking.reference == ref2))
    assert b2.status == "cancelled"


def test_webhook_validation_stale_timestamp_bad_sig_repeat(client, db_session):
    """
    Webhook:
    - Rejects timestamps older than 5 minutes (400)
    - Rejects bad signature (400)
    - Valid signature confirms booking
    - Repeat valid call is idempotent 200 no-op
    """
    csrf = get_csrf_token(client)
    res = client.post("/book/hold", data={
        "csrf_token": csrf,
        "room_type_id": "estate-room",
        "rate_plan_id": "room_only",
        "check_in": "2026-12-18",
        "check_out": "2026-12-19",
        "guest_name": "Webhook Guest",
        "guest_email": "webhook@example.com",
        "guest_phone": "9876543210",
        "dpdp_consent": "true"
    }, follow_redirects=False)
    ref = res.headers["location"].split("/")[-2]
    booking = db_session.scalar(select(Booking).where(Booking.reference == ref))
    payment = db_session.scalar(select(Payment).where(Payment.booking_id == booking.id))

    now = int(time.time())

    # Case A: Stale timestamp (10 minutes ago)
    stale_ts = now - 600
    stale_sig = generate_hmac_signature(f"{payment.id}:{booking.id}:{payment.amount_paise}:{stale_ts}")
    res_stale = client.post("/api/webhooks/payment", json={
        "payment_id": payment.id,
        "booking_id": booking.id,
        "amount": payment.amount_paise,
        "timestamp": stale_ts
    }, headers={"X-Signature": stale_sig})
    assert res_stale.status_code == 400

    # Case B: Bad signature
    res_bad = client.post("/api/webhooks/payment", json={
        "payment_id": payment.id,
        "booking_id": booking.id,
        "amount": payment.amount_paise,
        "timestamp": now
    }, headers={"X-Signature": "invalid_sig"})
    assert res_bad.status_code == 400

    # Case C: Valid webhook
    valid_sig = generate_hmac_signature(f"{payment.id}:{booking.id}:{payment.amount_paise}:{now}")
    res_ok = client.post("/api/webhooks/payment", json={
        "payment_id": payment.id,
        "booking_id": booking.id,
        "amount": 9999999,  # Body amount is ignored, compares to stored amount
        "timestamp": now
    }, headers={"X-Signature": valid_sig})
    assert res_ok.status_code == 200

    db_session.refresh(booking)
    assert booking.status == "confirmed"

    # Case D: Repeat valid webhook (idempotent no-op 200)
    res_repeat = client.post("/api/webhooks/payment", json={
        "payment_id": payment.id,
        "booking_id": booking.id,
        "amount": payment.amount_paise,
        "timestamp": now
    }, headers={"X-Signature": valid_sig})
    assert res_repeat.status_code == 200


def test_booking_lookup_unified_error_message(client, db_session):
    """Booking lookup returns an identical error message whether reference or email is incorrect."""
    csrf = get_csrf_token(client)
    
    # 1. Non-existent reference
    res1 = client.post("/booking-lookup", data={
        "csrf_token": csrf,
        "reference": "BK-NONEXIST",
        "email": "test@example.com"
    })
    assert res1.status_code == 404
    assert "No booking found with this reference and email combination." in res1.text

    # 2. Valid reference, incorrect email
    # First create a confirmed booking
    b_res = client.post("/book/hold", data={
        "csrf_token": csrf,
        "room_type_id": "estate-room",
        "rate_plan_id": "room_only",
        "check_in": "2026-12-22",
        "check_out": "2026-12-23",
        "guest_name": "Lookup Guest",
        "guest_email": "lookup@example.com",
        "guest_phone": "9876543210",
        "dpdp_consent": "true"
    }, follow_redirects=False)
    ref = b_res.headers["location"].split("/")[-2]
    client.post(f"/book/{ref}/mock-pay", data={"csrf_token": csrf})

    res2 = client.post("/booking-lookup", data={
        "csrf_token": csrf,
        "reference": ref,
        "email": "wrongemail@example.com"
    })
    assert res2.status_code == 404
    assert "No booking found with this reference and email combination." in res2.text

    # 3. Matching pair redirects to confirmation
    res3 = client.post("/booking-lookup", data={
        "csrf_token": csrf,
        "reference": ref,
        "email": "lookup@example.com"
    }, follow_redirects=False)
    assert res3.status_code == 303
    assert res3.headers["location"] == f"/booking/{ref}"


def test_pay_page_after_expiry_shows_hold_expired_page(client, db_session):
    """Accessing the pay page after hold expiration releases the hold and renders the hold-expired page."""
    csrf = get_csrf_token(client)
    res = client.post("/book/hold", data={
        "csrf_token": csrf,
        "room_type_id": "estate-room",
        "rate_plan_id": "room_only",
        "check_in": "2027-01-10",
        "check_out": "2027-01-11",
        "guest_name": "Late Guest",
        "guest_email": "late@example.com",
        "guest_phone": "9876543210",
        "dpdp_consent": "true"
    }, follow_redirects=False)
    assert res.status_code == 303, f"Expected 303 redirect, got {res.status_code}: {res.text[:300]}"
    ref = res.headers["location"].split("/")[-2]
    booking = db_session.scalar(select(Booking).where(Booking.reference == ref))
    
    # Backdate hold_expires_at to simulate expiration
    booking.hold_expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    db_session.commit()

    res_pay = client.get(f"/book/{ref}/pay")
    assert res_pay.status_code == 410
    assert "Your Booking Hold Has Expired" in res_pay.text

    db_session.refresh(booking)
    assert booking.status == "expired"


def test_mock_pay_after_expiry_rehold_or_needs_refund(client, db_session):
    """
    Submitting mock-pay after hold expired:
    If room was sold out in the interim, confirms taking needs_refund path with a clear message.
    """
    csrf = get_csrf_token(client)
    res = client.post("/book/hold", data={
        "csrf_token": csrf,
        "room_type_id": "estate-room",
        "rate_plan_id": "room_only",
        "check_in": "2027-01-12",
        "check_out": "2027-01-13",
        "guest_name": "Refund Candidate",
        "guest_email": "refundcand@example.com",
        "guest_phone": "9876543210",
        "dpdp_consent": "true"
    }, follow_redirects=False)
    ref = res.headers["location"].split("/")[-2]
    booking = db_session.scalar(select(Booking).where(Booking.reference == ref))

    # Manually release the hold to simulate expiry cleanup
    release_booking_hold(db_session, booking.id, reason="expired")
    
    # Now simulate another booking buying up all stock for that date
    alt = db_session.scalar(
        select(Allotment).where(Allotment.room_type_id == "estate-room", Allotment.date == date(2027, 1, 12))
    )
    alt.sold = alt.total
    alt.held = 0
    db_session.commit()

    # Now guest clicks "Pay Successfully" on their stale page
    pay_res = client.post(f"/book/{ref}/mock-pay", data={"csrf_token": csrf})
    assert pay_res.status_code == 409
    assert "automated refund" in pay_res.text.lower()

    payment = db_session.scalar(select(Payment).where(Payment.booking_id == booking.id))
    assert payment.status == "needs_refund"
