"""Integration and unit tests for Phase 3 Staff Administration."""
import pytest
from datetime import date, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import select, text
import re

from app.main import app
from app.db import get_db
from app.models import (
    User, RoomType, DailyRate, Allotment, PromoCode, Booking, BookingNight,
    Payment, AuditLog
)
from app.security import hash_password


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def staff_login(client, email, password):
    """Perform login through the staff login endpoint."""
    res_login_page = client.get("/staff/login")
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', res_login_page.text)
    csrf = m.group(1)

    res = client.post("/staff/login", data={
        "email": email,
        "password": password,
        "csrf_token": csrf
    }, follow_redirects=False)
    # The session cookie was regenerated on login with a new CSRF token!
    new_csrf = client.cookies.get("plantation_session")
    # Fetch calendar to get the regenerated session's CSRF token
    res_cal = client.get("/staff/calendar")
    m_new = re.search(r'name="csrf_token"\s+value="([^"]+)"', res_cal.text)
    active_csrf = m_new.group(1) if m_new else csrf
    return res, active_csrf


# -----------------------------------------------------------------------------
# 1. RBAC & Access Control
# -----------------------------------------------------------------------------
def test_unauthenticated_staff_redirects_to_login(client):
    """Guest cannot reach /staff or /staff/calendar without authentication."""
    res = client.get("/staff/calendar", follow_redirects=False)
    assert res.status_code == 303
    assert "/staff/login?next=/staff/calendar" in res.headers["location"]


def test_login_rejects_external_next_url(client):
    """Test that open-redirect via ?next=https://evil.com is ignored and redirected to /staff/calendar."""
    res_page = client.get("/staff/login?next=https://evil.com")
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', res_page.text)
    csrf = m.group(1)

    res = client.post("/staff/login", data={
        "email": "reservations@plantationstay.local",
        "password": "ReservationsDemo2026!",
        "csrf_token": csrf,
        "next": "https://evil.com"
    }, follow_redirects=False)

    assert res.status_code == 303
    assert res.headers["location"] == "/staff/calendar"


def test_sales_role_forbidden_on_rate_and_promos(client):
    """Sales role gets 403 Forbidden on rate, promo, and booking admin."""
    staff_login(client, "sales@plantationstay.local", "SalesDemo2026!")

    # Attempt to view calendar
    res_cal = client.get("/staff/calendar")
    assert res_cal.status_code == 403

    # Attempt to view promos
    res_pro = client.get("/staff/promos")
    assert res_pro.status_code == 403

    # Attempt to view bookings
    res_bk = client.get("/staff/bookings")
    assert res_bk.status_code == 403


def test_gm_can_view_audit_log_reservations_cannot(client):
    """Audit log is visible to GM only."""
    # 1. Reservations user
    staff_login(client, "reservations@plantationstay.local", "ReservationsDemo2026!")
    res_res = client.get("/staff/calendar")
    assert res_res.status_code == 200
    assert "GM Audit Log" not in res_res.text

    # 2. GM user
    client.cookies.clear()
    staff_login(client, "gm@plantationstay.local", "GMDemo2026!")
    res_gm = client.get("/staff/calendar")
    assert res_gm.status_code == 200
    assert "GM Audit Log" in res_gm.text


# -----------------------------------------------------------------------------
# 2. Rates & Allotment Operations
# -----------------------------------------------------------------------------
def test_single_date_rate_and_allotment_update(client, db_session):
    """Single date rate update converts rupees to paise and saves correctly."""
    _, csrf = staff_login(client, "reservations@plantationstay.local", "ReservationsDemo2026!")
    target_d = date.today() + timedelta(days=5)

    res = client.post("/staff/calendar/single-update", data={
        "csrf_token": csrf,
        "room_type_id": "estate-room",
        "target_date": target_d.isoformat(),
        "rate_rupees": "8250.50",
        "total_allotment": "20"
    }, follow_redirects=False)
    assert res.status_code == 303

    # Verify DailyRate in database
    dr = db_session.scalar(
        select(DailyRate).where(DailyRate.room_type_id == "estate-room", DailyRate.date == target_d)
    )
    assert dr.price_paise == 825050

    # Verify Allotment total
    alt = db_session.scalar(
        select(Allotment).where(Allotment.room_type_id == "estate-room", Allotment.date == target_d)
    )
    assert alt.total == 20


def test_lowering_allotment_below_sold_plus_held_rejected_friendly(client, db_session):
    """If staff set total below sold + held, reject with friendly error without raising DB 500 error."""
    _, csrf = staff_login(client, "reservations@plantationstay.local", "ReservationsDemo2026!")
    target_d = date.today() + timedelta(days=7)

    # Setup 4 sold, 1 held on that date
    alt = db_session.scalar(
        select(Allotment).where(Allotment.room_type_id == "estate-room", Allotment.date == target_d)
    )
    alt.sold = 4
    alt.held = 1
    alt.total = 10
    db_session.commit()

    # Attempt to lower total to 3 (< 4 + 1 = 5)
    res = client.post("/staff/calendar/single-update", data={
        "csrf_token": csrf,
        "room_type_id": "estate-room",
        "target_date": target_d.isoformat(),
        "total_allotment": "3"
    }, follow_redirects=True)

    assert res.status_code == 200
    assert "Cannot reduce allotment to 3" in res.text
    assert "4 sold and 1 held" in res.text

    # DB allotment remains unchanged
    db_session.refresh(alt)
    assert alt.total == 10


def test_batch_range_update_with_weekday_weekend_pattern(client, db_session):
    """Batch range updates weekday vs weekend rates across range in a single transaction."""
    _, csrf = staff_login(client, "reservations@plantationstay.local", "ReservationsDemo2026!")
    start_d = date.today() + timedelta(days=10)
    end_d = start_d + timedelta(days=6)

    res = client.post("/staff/calendar/batch-update", data={
        "csrf_token": csrf,
        "room_type_id": "estate-room",
        "start_date": start_d.isoformat(),
        "end_date": end_d.isoformat(),
        "weekday_rate_rupees": "7200",
        "weekend_rate_rupees": "9500",
        "total_allotment": "18",
        "blackout_action": "preserve"
    }, follow_redirects=False)
    assert res.status_code == 303

    # Check that rates were set according to day of week
    curr = start_d
    while curr <= end_d:
        dr = db_session.scalar(
            select(DailyRate).where(DailyRate.room_type_id == "estate-room", DailyRate.date == curr)
        )
        if curr.weekday() in (4, 5):  # Fri, Sat
            assert dr.price_paise == 950000
        else:
            assert dr.price_paise == 720000
        curr += timedelta(days=1)


def test_batch_update_rejects_if_any_night_exceeds_capacity(client, db_session):
    """If any single night in a batch would fall below sold+held, reject entire transaction."""
    _, csrf = staff_login(client, "reservations@plantationstay.local", "ReservationsDemo2026!")
    start_d = date.today() + timedelta(days=20)
    end_d = start_d + timedelta(days=4)

    # Make the 3rd day have 5 sold
    problem_d = start_d + timedelta(days=2)
    alt = db_session.scalar(
        select(Allotment).where(Allotment.room_type_id == "estate-room", Allotment.date == problem_d)
    )
    alt.sold = 5
    alt.held = 0
    alt.total = 10
    db_session.commit()

    # Attempt to set total allotment for entire range to 4 (< 5)
    res = client.post("/staff/calendar/batch-update", data={
        "csrf_token": csrf,
        "room_type_id": "estate-room",
        "start_date": start_d.isoformat(),
        "end_date": end_d.isoformat(),
        "total_allotment": "4",
        "blackout_action": "preserve"
    }, follow_redirects=True)

    assert res.status_code == 200
    assert "Cannot set allotment to 4" in res.text
    assert str(problem_d) in res.text

    # Ensure no nights were updated (atomic transaction)
    db_session.refresh(alt)
    assert alt.total == 10


def test_blackout_blocks_new_holds_but_honors_existing_confirmed(client, db_session):
    """
    Blackout toggling blocks new holds on the guest site.
    Existing confirmed bookings remain unaffected and warning is logged.
    """
    target_d = date.today() + timedelta(days=30)
    # Create an existing confirmed booking overlapping this date
    b = Booking(
        reference="BK-HONOR01",
        room_type_id="estate-room",
        rate_plan_id="room_only",
        check_in=target_d,
        check_out=target_d + timedelta(days=1),
        num_guests=1,
        num_rooms=1,
        status="confirmed",
        guest_name="Existing Confirmed",
        guest_email="existing@example.com",
        guest_phone="9876543210",
        dpdp_consent=True,
        room_total_paise=700000,
        discount_paise=0,
        gst_paise=35000,
        grand_total_paise=735000
    )
    db_session.add(b)
    db_session.commit()

    # Staff toggles blackout
    _, csrf = staff_login(client, "reservations@plantationstay.local", "ReservationsDemo2026!")
    res = client.post("/staff/calendar/toggle-blackout", data={
        "csrf_token": csrf,
        "room_type_id": "estate-room",
        "target_date": target_d.isoformat()
    }, follow_redirects=True)

    assert res.status_code == 200
    assert "1 existing confirmed booking(s) remain honored" in res.text

    # Existing booking remains confirmed
    db_session.refresh(b)
    assert b.status == "confirmed"

    # Now verify guest site: HTMX quote fragment shows dates unavailable
    res_quote = client.get(
        f"/rooms/estate-room/quote?check_in={target_d.isoformat()}&check_out={(target_d+timedelta(days=1)).isoformat()}&rate_plan_id=room_only"
    )
    assert "DATES UNAVAILABLE" in res_quote.text
    assert "currently sold out or blacked out" in res_quote.text


def test_rate_edit_does_not_alter_existing_booking_snapshots(client, db_session):
    """Editing daily rates does not mutate prices in existing booking_nights records."""
    target_d = date.today() + timedelta(days=15)
    # Create booking with 700000 paise base rate snapshot
    b = Booking(
        reference="BK-SNAP01",
        room_type_id="estate-room",
        rate_plan_id="room_only",
        check_in=target_d,
        check_out=target_d + timedelta(days=1),
        num_guests=1,
        num_rooms=1,
        status="confirmed",
        guest_name="Snapshot Guest",
        guest_email="snap@example.com",
        guest_phone="9876543210",
        dpdp_consent=True,
        room_total_paise=700000,
        discount_paise=0,
        gst_paise=35000,
        grand_total_paise=735000
    )
    db_session.add(b)
    db_session.flush()

    bn = BookingNight(
        booking_id=b.id,
        date=target_d,
        base_rate_paise=700000,
        breakfast_addon_paise=0,
        discount_paise=0,
        taxable_amount_paise=700000,
        gst_bps=500,
        gst_paise=35000,
        total_night_paise=735000
    )
    db_session.add(bn)
    db_session.commit()

    # Staff changes daily rate for target_d to Rs 12,000 (1200000 paise)
    _, csrf = staff_login(client, "reservations@plantationstay.local", "ReservationsDemo2026!")
    client.post("/staff/calendar/single-update", data={
        "csrf_token": csrf,
        "room_type_id": "estate-room",
        "target_date": target_d.isoformat(),
        "rate_rupees": "12000"
    })

    # Verify booking snapshot is completely untouched
    db_session.refresh(bn)
    assert bn.base_rate_paise == 700000
    assert bn.total_night_paise == 735000


# -----------------------------------------------------------------------------
# 3. Promotions Management
# -----------------------------------------------------------------------------
def test_create_and_toggle_promo_code(client, db_session):
    """Staff can create promo in percentage and toggle active/inactive."""
    _, csrf = staff_login(client, "reservations@plantationstay.local", "ReservationsDemo2026!")

    # Create 15.5% promo
    res = client.post("/staff/promos/save", data={
        "csrf_token": csrf,
        "code": "SUMMER15",
        "discount_percent": "15.5",
        "valid_from": date.today().isoformat(),
        "valid_to": (date.today() + timedelta(days=60)).isoformat()
    }, follow_redirects=False)
    assert res.status_code == 303

    p = db_session.get(PromoCode, "SUMMER15")
    assert p is not None
    assert p.discount_bps == 1550
    assert p.is_active is True

    # Toggle deactivate
    res_toggle = client.post("/staff/promos/toggle-active", data={
        "csrf_token": csrf,
        "code": "SUMMER15"
    }, follow_redirects=False)
    assert res_toggle.status_code == 303

    db_session.refresh(p)
    assert p.is_active is False


# -----------------------------------------------------------------------------
# 4. Refund Queue & Simulated Action
# -----------------------------------------------------------------------------
def test_mark_payment_refunded_idempotent(client, db_session):
    """Mark Refunded executes a conditional update (needs_refund -> refunded) and is idempotent."""
    b = Booking(
        reference="BK-REFUND01",
        room_type_id="estate-room",
        rate_plan_id="room_only",
        check_in=date.today(),
        check_out=date.today() + timedelta(days=1),
        num_guests=1,
        num_rooms=1,
        status="expired",
        guest_name="Stale Payer",
        guest_email="stale@example.com",
        guest_phone="9876543210",
        dpdp_consent=True,
        room_total_paise=700000,
        discount_paise=0,
        gst_paise=35000,
        grand_total_paise=735000
    )
    db_session.add(b)
    db_session.flush()

    payment = Payment(
        id="PAY-REFUND123",
        booking_id=b.id,
        amount_paise=735000,
        status="needs_refund",
        provider="mock"
    )
    db_session.add(payment)
    db_session.commit()

    _, csrf = staff_login(client, "reservations@plantationstay.local", "ReservationsDemo2026!")

    # 1. First execution
    res1 = client.post("/staff/bookings/mark-refunded", data={
        "csrf_token": csrf,
        "payment_id": "PAY-REFUND123"
    }, follow_redirects=True)
    assert res1.status_code == 200
    assert "marked as refunded" in res1.text

    db_session.refresh(payment)
    assert payment.status == "refunded"

    # 2. Repeated execution (idempotent no-op)
    res2 = client.post("/staff/bookings/mark-refunded", data={
        "csrf_token": csrf,
        "payment_id": "PAY-REFUND123"
    }, follow_redirects=True)
    assert res2.status_code == 200
    assert "already processed" in res2.text


# -----------------------------------------------------------------------------
# 5. CSV Export & Spreadsheet Formula Sanitization
# -----------------------------------------------------------------------------
def test_csv_export_escapes_formula_cells(client, db_session):
    """CSV export escapes leading formula characters (=, +, -, @) to prevent injection."""
    target_d = date.today() + timedelta(days=3)
    b = Booking(
        reference="=CMD('calc')",  # Formula injection attempt in reference
        room_type_id="estate-room",
        rate_plan_id="room_only",
        check_in=target_d,
        check_out=target_d + timedelta(days=1),
        num_guests=1,
        num_rooms=1,
        status="confirmed",
        guest_name="+Dr. Evil",     # Leading '+'
        guest_email="@evil@example.com", # Leading '@'
        guest_phone="9876543210",
        dpdp_consent=True,
        room_total_paise=700000,
        discount_paise=0,
        gst_paise=35000,
        grand_total_paise=735000
    )
    db_session.add(b)
    db_session.commit()

    _, _ = staff_login(client, "reservations@plantationstay.local", "ReservationsDemo2026!")
    res = client.get(f"/staff/bookings/export-csv?date_str={target_d.isoformat()}")
    assert res.status_code == 200
    assert res.headers["content-type"] == "text/csv; charset=utf-8"

    csv_text = res.text
    assert "'=CMD('calc')" in csv_text
    assert "'+Dr. Evil" in csv_text
    assert "'@evil@example.com" in csv_text
