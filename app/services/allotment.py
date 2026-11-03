"""Allotment and booking hold/confirm/release service."""
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional
import time
from sqlalchemy.orm import Session
from sqlalchemy import select, update, text
from sqlalchemy.exc import DBAPIError
from app.models import Allotment, Booking, BookingNight, Payment
from app.config import settings


class SoldOutException(Exception):
    pass


class HoldExpiredException(Exception):
    pass


class InvalidPaymentException(Exception):
    pass


def get_stay_nights(check_in: date, check_out: date) -> List[date]:
    """Generate sorted list of dates for the stay."""
    if check_out <= check_in:
        raise ValueError("check_out must be after check_in")
    curr = check_in
    nights = []
    while curr < check_out:
        nights.append(curr)
        curr += timedelta(days=1)
    # Return in strict date order to avoid deadlocks
    return sorted(nights)


def release_expired_holds(session: Session) -> int:
    """
    Find held bookings that have expired, claim them, and decrement held allotment.
    Lazy release on read / periodic cleanup.
    """
    now = datetime.now(timezone.utc)
    expired_bookings = session.scalars(
        select(Booking).where(
            Booking.status == "held",
            Booking.hold_expires_at <= now
        )
    ).all()

    released_count = 0
    for b in expired_bookings:
        if release_booking_hold(session, b.id, reason="expired"):
            released_count += 1
    return released_count


def create_atomic_hold(
    session: Session,
    room_type_id: str,
    stay_dates: List[date],
    num_rooms: int = 1
) -> None:
    """
    Atomic hold in one transaction.
    Update rows in date order, with 1 retry on deadlock.
    UPDATE allotment SET held = held + :num_rooms
    WHERE room_type_id = :r AND date IN (:nights) AND sold + held + :num_rooms <= total AND NOT blackout
    """
    sorted_nights = sorted(stay_dates)
    max_retries = 2
    for attempt in range(max_retries):
        try:
            # We execute the update in date order
            stmt = text("""
                UPDATE allotment
                SET held = held + :num_rooms
                WHERE room_type_id = :room_type_id
                  AND date = ANY(:nights)
                  AND (sold + held + :num_rooms) <= total
                  AND NOT blackout;
            """)
            res = session.execute(stmt, {
                "num_rooms": num_rooms,
                "room_type_id": room_type_id,
                "nights": sorted_nights
            })
            if res.rowcount < len(sorted_nights):
                raise SoldOutException("just sold out")
            return
        except DBAPIError as e:
            # Check for PostgreSQL deadlock (SQLSTATE 40P01)
            orig = getattr(e, "orig", None)
            sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
            if sqlstate == "40P01" and attempt < max_retries - 1:
                session.rollback()
                time.sleep(0.05 * (attempt + 1))
                continue
            raise


def release_booking_hold(
    session: Session,
    booking_id: int,
    reason: str = "expired"
) -> bool:
    """
    Claim booking first:
    UPDATE bookings SET status=:reason WHERE id=:id AND status='held' RETURNING ...
    Decrement allotment ONLY if row was claimed.
    Uses date range (date >= check_in AND date < check_out).
    """
    stmt = text("""
        UPDATE bookings
        SET status = :reason
        WHERE id = :booking_id AND status = 'held'
        RETURNING id, room_type_id, check_in, check_out, num_rooms;
    """)
    res = session.execute(stmt, {"reason": reason, "booking_id": booking_id}).fetchone()
    if not res:
        return False

    b_id, room_type_id, check_in, check_out, num_rooms = res
    # Refresh in-memory identity map if object exists in session
    b_obj = session.get(Booking, booking_id)
    if b_obj:
        session.refresh(b_obj)

    # Decrement allotment for dates in range
    decr_stmt = text("""
        UPDATE allotment
        SET held = held - :num_rooms
        WHERE room_type_id = :room_type_id
          AND date >= :check_in
          AND date < :check_out
          AND held >= :num_rooms;
    """)
    session.execute(decr_stmt, {
        "num_rooms": num_rooms,
        "room_type_id": room_type_id,
        "check_in": check_in,
        "check_out": check_out
    })
    return True


def confirm_booking_payment(
    session: Session,
    payment_id: str,
    booking_id: int,
    amount_paise: int,
    signature: Optional[str] = None
) -> str:
    """
    Order:
    (a) UPDATE payments pending -> success with amount check. rowcount 0 = no-op or invalid amount.
    (b) UPDATE bookings held -> confirmed. rowcount 0 = hold expired:
        Retry atomic hold. If retry fails, mark payment 'needs_refund' and return 'needs_refund'.
    (c) Move held -> sold with AND held >= n (or sold = sold + n if retry succeeded).
    """
    # (a) Claim payment
    pay_stmt = text("""
        UPDATE payments
        SET status = 'success', signature = :signature
        WHERE id = :payment_id
          AND booking_id = :booking_id
          AND amount_paise = :amount_paise
          AND status = 'pending'
        RETURNING id;
    """)
    pay_res = session.execute(pay_stmt, {
        "payment_id": payment_id,
        "booking_id": booking_id,
        "amount_paise": amount_paise,
        "signature": signature
    }).fetchone()

    if not pay_res:
        # Check if already processed (idempotent repeat)
        existing = session.get(Payment, payment_id)
        if existing and existing.status == "success":
            return "already_confirmed"
        raise InvalidPaymentException("Payment update failed: payment not found, wrong amount, or not pending")

    # Refresh payment object in session identity map
    pay_obj = session.get(Payment, payment_id)
    if pay_obj:
        session.refresh(pay_obj)

    # (b) Try to confirm booking
    b_stmt = text("""
        UPDATE bookings
        SET status = 'confirmed', hold_expires_at = NULL
        WHERE id = :booking_id AND status = 'held'
        RETURNING id, room_type_id, check_in, check_out, num_rooms;
    """)
    b_res = session.execute(b_stmt, {"booking_id": booking_id}).fetchone()

    if b_res:
        _, room_type_id, check_in, check_out, num_rooms = b_res
        b_obj = session.get(Booking, booking_id)
        if b_obj:
            session.refresh(b_obj)
        # (c) Normal flow: move held -> sold
        allot_stmt = text("""
            UPDATE allotment
            SET held = held - :num_rooms,
                sold = sold + :num_rooms
            WHERE room_type_id = :room_type_id
              AND date >= :check_in
              AND date < :check_out
              AND held >= :num_rooms;
        """)
        session.execute(allot_stmt, {
            "num_rooms": num_rooms,
            "room_type_id": room_type_id,
            "check_in": check_in,
            "check_out": check_out
        })
        return "confirmed"
    else:
        # Hold had expired! Retrieve booking details to attempt re-holding
        booking = session.get(Booking, booking_id)
        if not booking:
            raise ValueError(f"Booking {booking_id} not found")

        nights = get_stay_nights(booking.check_in, booking.check_out)
        try:
            # Try to grab hold again
            create_atomic_hold(session, booking.room_type_id, nights, booking.num_rooms)
            # Acquired! Now confirm booking and move held -> sold
            booking.status = "confirmed"
            booking.hold_expires_at = None
            session.flush()

            allot_stmt = text("""
                UPDATE allotment
                SET held = held - :num_rooms,
                    sold = sold + :num_rooms
                WHERE room_type_id = :room_type_id
                  AND date >= :check_in
                  AND date < :check_out
                  AND held >= :num_rooms;
            """)
            session.execute(allot_stmt, {
                "num_rooms": booking.num_rooms,
                "room_type_id": booking.room_type_id,
                "check_in": booking.check_in,
                "check_out": booking.check_out
            })
            return "confirmed_after_rehold"
        except SoldOutException:
            # Room sold out while hold expired; cannot fulfill, mark needs_refund
            refund_stmt = text("""
                UPDATE payments
                SET status = 'needs_refund'
                WHERE id = :payment_id;
            """)
            session.execute(refund_stmt, {"payment_id": payment_id})
            pay_obj = session.get(Payment, payment_id)
            if pay_obj:
                session.refresh(pay_obj)
            return "needs_refund"
