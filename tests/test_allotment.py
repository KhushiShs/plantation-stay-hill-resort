"""Tests for allotment lifecycle, holds, confirmation, releases, and edge cases."""
import pytest
from datetime import date, datetime, timedelta, timezone
from sqlalchemy import select
from app.models import Booking, Allotment, Payment
from app.services.allotment import (
    create_atomic_hold,
    release_booking_hold,
    confirm_booking_payment,
    release_expired_holds,
    SoldOutException,
    InvalidPaymentException
)
from app.security import generate_hmac_signature, verify_hmac_signature


def test_atomic_hold_and_release(db_session):
    """Test successful hold followed by release."""
    stay = [date(2026, 12, 1), date(2026, 12, 2)]
    # Grab initial held count
    alt = db_session.scalar(
        select(Allotment).where(Allotment.room_type_id == "estate-room", Allotment.date == stay[0])
    )
    initial_held = alt.held

    create_atomic_hold(db_session, "estate-room", stay, num_rooms=1)
    db_session.flush()

    db_session.refresh(alt)
    assert alt.held == initial_held + 1

    # Create a booking record
    booking = Booking(
        reference="BK-TEST01",
        room_type_id="estate-room",
        rate_plan_id="room_only",
        check_in=stay[0],
        check_out=stay[1] + timedelta(days=1),
        num_guests=2,
        num_rooms=1,
        status="held",
        guest_name="Test Guest",
        guest_email="guest@test.local",
        guest_phone="9876543210",
        room_total_paise=1400000,
        gst_paise=70000,
        grand_total_paise=1470000
    )
    db_session.add(booking)
    db_session.flush()

    # Release booking hold
    success = release_booking_hold(db_session, booking.id, reason="cancelled")
    assert success is True
    assert booking.status == "cancelled"

    db_session.refresh(alt)
    assert alt.held == initial_held


def test_double_release_idempotency(db_session):
    """Releasing an already released or non-held booking returns False and does not double-decrement."""
    stay = [date(2026, 12, 5)]
    alt = db_session.scalar(
        select(Allotment).where(Allotment.room_type_id == "estate-room", Allotment.date == stay[0])
    )
    initial_held = alt.held

    create_atomic_hold(db_session, "estate-room", stay, num_rooms=1)
    db_session.flush()

    booking = Booking(
        reference="BK-TEST02",
        room_type_id="estate-room",
        rate_plan_id="room_only",
        check_in=stay[0],
        check_out=stay[0] + timedelta(days=1),
        num_guests=1,
        num_rooms=1,
        status="held",
        guest_name="Guest Two",
        guest_email="guest2@test.local",
        guest_phone="9876543210",
        room_total_paise=700000,
        gst_paise=35000,
        grand_total_paise=735000
    )
    db_session.add(booking)
    db_session.flush()

    # First release -> True
    first_res = release_booking_hold(db_session, booking.id, reason="expired")
    assert first_res is True

    # Second release -> False (already released, rowcount=0)
    second_res = release_booking_hold(db_session, booking.id, reason="expired")
    assert second_res is False

    db_session.refresh(alt)
    assert alt.held == initial_held


def test_confirm_flow_and_idempotency(db_session):
    """Test full payment confirmation: pending -> success, held -> confirmed, held -> sold."""
    stay = [date(2026, 12, 10)]
    alt = db_session.scalar(
        select(Allotment).where(Allotment.room_type_id == "estate-room", Allotment.date == stay[0])
    )
    initial_sold = alt.sold
    initial_held = alt.held

    create_atomic_hold(db_session, "estate-room", stay, num_rooms=1)
    db_session.flush()

    booking = Booking(
        reference="BK-CONF01",
        room_type_id="estate-room",
        rate_plan_id="room_only",
        check_in=stay[0],
        check_out=stay[0] + timedelta(days=1),
        num_guests=1,
        num_rooms=1,
        status="held",
        guest_name="Confirm Guest",
        guest_email="confirm@test.local",
        guest_phone="9876543210",
        room_total_paise=700000,
        gst_paise=35000,
        grand_total_paise=735000
    )
    db_session.add(booking)
    db_session.flush()

    # Create pending payment at Step 3
    payment = Payment(
        id="PAY-MOCK-001",
        booking_id=booking.id,
        amount_paise=735000,
        status="pending",
        provider="mock"
    )
    db_session.add(payment)
    db_session.flush()

    sig = generate_hmac_signature("PAY-MOCK-001:735000")

    # Confirm payment
    result = confirm_booking_payment(
        db_session,
        payment_id="PAY-MOCK-001",
        booking_id=booking.id,
        amount_paise=735000,
        signature=sig
    )
    assert result == "confirmed"
    assert booking.status == "confirmed"
    assert payment.status == "success"

    db_session.refresh(alt)
    assert alt.held == initial_held
    assert alt.sold == initial_sold + 1

    # Repeat webhook / idempotency check
    repeat_res = confirm_booking_payment(
        db_session,
        payment_id="PAY-MOCK-001",
        booking_id=booking.id,
        amount_paise=735000,
        signature=sig
    )
    assert repeat_res == "already_confirmed"
    db_session.refresh(alt)
    assert alt.sold == initial_sold + 1


def test_confirm_wrong_amount_fails(db_session):
    """Payment confirmation with mismatched amount fails and raises InvalidPaymentException."""
    stay = [date(2026, 12, 12)]
    create_atomic_hold(db_session, "estate-room", stay, num_rooms=1)

    booking = Booking(
        reference="BK-AMT01",
        room_type_id="estate-room",
        rate_plan_id="room_only",
        check_in=stay[0],
        check_out=stay[0] + timedelta(days=1),
        num_guests=1,
        num_rooms=1,
        status="held",
        guest_name="Amt Guest",
        guest_email="amt@test.local",
        guest_phone="9876543210",
        room_total_paise=700000,
        gst_paise=35000,
        grand_total_paise=735000
    )
    db_session.add(booking)
    db_session.flush()

    payment = Payment(
        id="PAY-AMT-001",
        booking_id=booking.id,
        amount_paise=735000,
        status="pending",
        provider="mock"
    )
    db_session.add(payment)
    db_session.flush()

    with pytest.raises(InvalidPaymentException):
        confirm_booking_payment(
            db_session,
            payment_id="PAY-AMT-001",
            booking_id=booking.id,
            amount_paise=500000,  # Wrong amount!
            signature="test_sig"
        )


def test_confirm_after_expiry_reholds_or_refunds(db_session):
    """
    If booking hold expired before payment confirmation:
    (b) UPDATE bookings held->confirmed rowcount=0 -> re-hold attempt.
    Case 1: Capacity available -> successfully re-holds and confirms.
    Case 2: Sold out in meantime -> marks payment 'needs_refund'.
    """
    stay = [date(2026, 12, 15)]
    alt = db_session.scalar(
        select(Allotment).where(Allotment.room_type_id == "estate-room", Allotment.date == stay[0])
    )

    create_atomic_hold(db_session, "estate-room", stay, num_rooms=1)

    booking = Booking(
        reference="BK-EXP01",
        room_type_id="estate-room",
        rate_plan_id="room_only",
        check_in=stay[0],
        check_out=stay[0] + timedelta(days=1),
        num_guests=1,
        num_rooms=1,
        status="held",
        guest_name="Expired Guest",
        guest_email="exp@test.local",
        guest_phone="9876543210",
        room_total_paise=700000,
        gst_paise=35000,
        grand_total_paise=735000
    )
    db_session.add(booking)
    db_session.flush()

    payment = Payment(
        id="PAY-EXP-001",
        booking_id=booking.id,
        amount_paise=735000,
        status="pending",
        provider="mock"
    )
    db_session.add(payment)
    db_session.flush()

    # Simulate hold expired and released
    release_booking_hold(db_session, booking.id, reason="expired")
    assert booking.status == "expired"

    # Confirm arrives late: rooms are available, so re-hold succeeds!
    res = confirm_booking_payment(
        db_session,
        payment_id="PAY-EXP-001",
        booking_id=booking.id,
        amount_paise=735000
    )
    assert res == "confirmed_after_rehold"
    assert booking.status == "confirmed"

    # Case 2: Now simulate when room is completely sold out
    alt.sold = alt.total
    db_session.flush()

    booking2 = Booking(
        reference="BK-EXP02",
        room_type_id="estate-room",
        rate_plan_id="room_only",
        check_in=stay[0],
        check_out=stay[0] + timedelta(days=1),
        num_guests=1,
        num_rooms=1,
        status="expired",  # Already expired
        guest_name="Refund Guest",
        guest_email="refund@test.local",
        guest_phone="9876543210",
        room_total_paise=700000,
        gst_paise=35000,
        grand_total_paise=735000
    )
    db_session.add(booking2)
    db_session.flush()

    payment2 = Payment(
        id="PAY-EXP-002",
        booking_id=booking2.id,
        amount_paise=735000,
        status="pending",
        provider="mock"
    )
    db_session.add(payment2)
    db_session.flush()

    # Cannot re-hold because sold == total
    res2 = confirm_booking_payment(
        db_session,
        payment_id="PAY-EXP-002",
        booking_id=booking2.id,
        amount_paise=735000
    )
    assert res2 == "needs_refund"
    assert payment2.status == "needs_refund"


def test_hmac_signature_verification():
    """Test webhook HMAC signature validation with good and bad signatures."""
    payload = "PAY-12345:100000"
    secret = "my-test-secret"
    valid_sig = generate_hmac_signature(payload, secret)

    assert verify_hmac_signature(payload, valid_sig, secret) is True
    assert verify_hmac_signature(payload, "invalid_signature", secret) is False
    assert verify_hmac_signature("tampered_payload", valid_sig, secret) is False
