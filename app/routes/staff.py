"""Staff administration router: Auth, Calendar, Rates, Allotment, Promos, Bookings, CSV."""
from datetime import date, datetime, timedelta, timezone
from typing import Optional, List
import csv
import io
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select, text, func, and_

from app.config import settings
from app.db import get_db
from app.models import (
    User, RoomType, DailyRate, Allotment, PromoCode, Booking, BookingNight,
    Payment, AuditLog
)
from app.security import (
    verify_password,
    generate_csrf_token,
    check_rate_limit,
    get_current_staff_user,
    require_role
)
from app.formatters import format_paise, format_date_str, format_date_short
from app.services.staff import (
    parse_rupees_to_paise,
    parse_percent_to_bps,
    log_audit_event
)

router = APIRouter(prefix="/staff")
templates = Jinja2Templates(directory="app/templates")

# Register custom Jinja filters
templates.env.filters["format_paise"] = format_paise
templates.env.filters["format_date_str"] = format_date_str
templates.env.filters["format_date_short"] = format_date_short


def get_staff_csrf_token(request: Request) -> str:
    """Retrieve or generate CSRF token in session."""
    token = request.session.get("csrf_token")
    if not token:
        token = generate_csrf_token()
        request.session["csrf_token"] = token
    return token


def verify_staff_csrf(request: Request, submitted_token: str):
    """Enforce CSRF token verification."""
    session_token = request.session.get("csrf_token")
    if not session_token or session_token != submitted_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")


def sanitize_csv_cell(value: str) -> str:
    """Escape formula-leading characters in CSV to prevent CSV injection."""
    if not value:
        return ""
    s = str(value)
    if s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return f"'{s}"
    return s


# -----------------------------------------------------------------------------
# Staff Authentication & Session
# -----------------------------------------------------------------------------
@router.get("", include_in_schema=False)
def staff_root_redirect():
    """Default redirect to calendar."""
    return RedirectResponse(url="/staff/calendar", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/login", response_class=HTMLResponse)
def staff_login_page(request: Request, next: Optional[str] = None):
    # Check if already authenticated
    if request.session.get("staff_user_id"):
        return RedirectResponse(url="/staff/calendar", status_code=status.HTTP_303_SEE_OTHER)
        
    csrf_token = get_staff_csrf_token(request)
    return templates.TemplateResponse(request, "staff/login.html", {
        "app_name": settings.app_name,
        "csrf_token": csrf_token,
        "next_url": next or "",
        "error": None
    })


@router.post("/login")
def staff_login_action(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    next: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    # Enforce rate limit (max 5 login attempts / 60 seconds per IP)
    check_rate_limit(request, "staff_login", max_requests=5, window_seconds=60)
    verify_staff_csrf(request, csrf_token)

    # Generic invalid credentials message
    generic_error = "Invalid email or password. Please verify credentials."

    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if not user or not user.is_active or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse(request, "staff/login.html", {
            "app_name": settings.app_name,
            "csrf_token": csrf_token,
            "next_url": next or "",
            "error": generic_error
        }, status_code=401)

    # Regenerate session on login
    request.session.clear()
    request.session["csrf_token"] = generate_csrf_token()
    request.session["staff_user_id"] = user.id
    request.session["staff_role"] = user.role
    request.session["staff_name"] = user.full_name

    # Validate next redirect URL: must start with /staff only (prevents open redirects)
    redirect_target = "/staff/calendar"
    if next and next.startswith("/staff") and not next.startswith("//"):
        redirect_target = next

    return RedirectResponse(url=redirect_target, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/logout")
def staff_logout_action(request: Request, csrf_token: str = Form(...)):
    verify_staff_csrf(request, csrf_token)
    request.session.clear()
    return RedirectResponse(url="/staff/login", status_code=status.HTTP_303_SEE_OTHER)


# -----------------------------------------------------------------------------
# Rate & Allotment Calendar
# -----------------------------------------------------------------------------
@router.get("/calendar", response_class=HTMLResponse)
def view_calendar(
    request: Request,
    room_type_id: Optional[str] = None,
    success: Optional[str] = None,
    error: Optional[str] = None,
    current_user: User = Depends(require_role("reservations", "gm")),
    db: Session = Depends(get_db)
):
    room_types = db.scalars(select(RoomType).order_by(RoomType.id)).all()
    selected_room = None
    if room_type_id:
        selected_room = db.get(RoomType, room_type_id)
    if not selected_room:
        selected_room = room_types[0] if room_types else None

    # Load 60 days starting from today
    start_d = date.today()
    end_d = start_d + timedelta(days=60)

    # Fetch daily rates and allotments
    rates_q = db.scalars(
        select(DailyRate).where(
            DailyRate.room_type_id == selected_room.id,
            DailyRate.date >= start_d,
            DailyRate.date <= end_d
        )
    ).all()
    rates_map = {r.date: r for r in rates_q}

    allot_q = db.scalars(
        select(Allotment).where(
            Allotment.room_type_id == selected_room.id,
            Allotment.date >= start_d,
            Allotment.date <= end_d
        )
    ).all()
    allot_map = {a.date: a for a in allot_q}

    ledger_rows = []
    curr = start_d
    while curr <= end_d:
        rate_entry = rates_map.get(curr)
        price_p = rate_entry.price_paise if rate_entry else selected_room.base_price_paise
        allot_entry = allot_map.get(curr)
        if not allot_entry:
            allot_entry = Allotment(
                room_type_id=selected_room.id,
                date=curr,
                total=selected_room.total_inventory,
                sold=0,
                held=0,
                blackout=False
            )
        remaining = max(0, allot_entry.total - allot_entry.sold - allot_entry.held)
        ledger_rows.append({
            "date": curr,
            "price_paise": price_p,
            "price_rupees": f"{price_p / 100:.2f}".rstrip("0").rstrip("."),
            "allotment": allot_entry,
            "remaining": remaining
        })
        curr += timedelta(days=1)

    # Audit logs (GM only)
    audit_logs = []
    if current_user.role == "gm":
        audit_logs = db.scalars(
            select(AuditLog).order_by(AuditLog.created_at.desc()).limit(25)
        ).all()

    csrf_token = get_staff_csrf_token(request)
    return templates.TemplateResponse(request, "staff/calendar.html", {
        "app_name": settings.app_name,
        "active_tab": "calendar",
        "current_user": current_user,
        "room_types": room_types,
        "current_room_type": selected_room,
        "ledger_rows": ledger_rows,
        "default_start_date": start_d.strftime("%Y-%m-%d"),
        "default_end_date": (start_d + timedelta(days=14)).strftime("%Y-%m-%d"),
        "csrf_token": csrf_token,
        "audit_logs": audit_logs,
        "success_msg": success,
        "error_msg": error
    })


@router.post("/calendar/single-update")
def single_update_calendar(
    request: Request,
    room_type_id: str = Form(...),
    target_date: str = Form(...),
    rate_rupees: Optional[str] = Form(None),
    total_allotment: Optional[int] = Form(None),
    csrf_token: str = Form(...),
    current_user: User = Depends(require_role("reservations", "gm")),
    db: Session = Depends(get_db)
):
    verify_staff_csrf(request, csrf_token)
    t_date = date.fromisoformat(target_date)
    room = db.get(RoomType, room_type_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room type not found")

    alt = db.scalar(
        select(Allotment).where(Allotment.room_type_id == room_type_id, Allotment.date == t_date)
    )
    if not alt:
        alt = Allotment(room_type_id=room_type_id, date=t_date, total=room.total_inventory, sold=0, held=0)
        db.add(alt)

    changes = {}
    if total_allotment is not None:
        if total_allotment < 0 or total_allotment > room.total_inventory:
            return RedirectResponse(
                url=f"/staff/calendar?room_type_id={room_type_id}&error=Allotment+must+be+between+0+and+{room.total_inventory}",
                status_code=status.HTTP_303_SEE_OTHER
            )
        if total_allotment < (alt.sold + alt.held):
            return RedirectResponse(
                url=f"/staff/calendar?room_type_id={room_type_id}&error=Cannot+reduce+allotment+to+{total_allotment}.+There+are+currently+{alt.sold}+sold+and+{alt.held}+held+rooms+on+{target_date}+(minimum+allowed:+{alt.sold + alt.held}).",
                status_code=status.HTTP_303_SEE_OTHER
            )
        if alt.total != total_allotment:
            changes["total_allotment"] = {"old": alt.total, "new": total_allotment}
            alt.total = total_allotment

    if rate_rupees:
        try:
            rate_paise = parse_rupees_to_paise(rate_rupees)
        except ValueError as e:
            return RedirectResponse(
                url=f"/staff/calendar?room_type_id={room_type_id}&error={str(e)}",
                status_code=status.HTTP_303_SEE_OTHER
            )
        dr = db.scalar(
            select(DailyRate).where(DailyRate.room_type_id == room_type_id, DailyRate.date == t_date)
        )
        if not dr:
            dr = DailyRate(room_type_id=room_type_id, date=t_date, price_paise=rate_paise)
            db.add(dr)
            changes["rate_paise"] = {"old": room.base_price_paise, "new": rate_paise}
        elif dr.price_paise != rate_paise:
            changes["rate_paise"] = {"old": dr.price_paise, "new": rate_paise}
            dr.price_paise = rate_paise

    if changes:
        log_audit_event(db, current_user, "single_calendar_update", "allotment", f"{room_type_id}:{target_date}", changes)
        db.commit()

    return RedirectResponse(
        url=f"/staff/calendar?room_type_id={room_type_id}&success=Updated+{target_date}+successfully",
        status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/calendar/toggle-blackout")
def toggle_blackout_action(
    request: Request,
    room_type_id: str = Form(...),
    target_date: str = Form(...),
    csrf_token: str = Form(...),
    current_user: User = Depends(require_role("reservations", "gm")),
    db: Session = Depends(get_db)
):
    verify_staff_csrf(request, csrf_token)
    t_date = date.fromisoformat(target_date)
    room = db.get(RoomType, room_type_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room type not found")

    alt = db.scalar(
        select(Allotment).where(Allotment.room_type_id == room_type_id, Allotment.date == t_date)
    )
    if not alt:
        alt = Allotment(room_type_id=room_type_id, date=t_date, total=room.total_inventory, sold=0, held=0, blackout=True)
        db.add(alt)
        new_state = True
    else:
        new_state = not alt.blackout
        alt.blackout = new_state

    # Check affected existing bookings
    affected_count = 0
    if new_state:
        # Count confirmed bookings that overlap this date
        affected_count = db.scalar(
            select(func.count(Booking.id)).where(
                Booking.room_type_id == room_type_id,
                Booking.status == "confirmed",
                Booking.check_in <= t_date,
                Booking.check_out > t_date
            )
        ) or 0

    log_audit_event(
        db, current_user, "toggle_blackout", "allotment",
        f"{room_type_id}:{target_date}",
        {"blackout": new_state, "affected_existing_confirmed": affected_count}
    )
    db.commit()

    msg = f"Blackout {'set' if new_state else 'cleared'} for {target_date}."
    if new_state and affected_count > 0:
        msg += f" Note: {affected_count} existing confirmed booking(s) remain honored."

    return RedirectResponse(
        url=f"/staff/calendar?room_type_id={room_type_id}&success={msg}",
        status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/calendar/batch-update")
def batch_update_calendar(
    request: Request,
    room_type_id: str = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    weekday_rate_rupees: Optional[str] = Form(None),
    weekend_rate_rupees: Optional[str] = Form(None),
    total_allotment: Optional[int] = Form(None),
    blackout_action: str = Form("preserve"),
    csrf_token: str = Form(...),
    current_user: User = Depends(require_role("reservations", "gm")),
    db: Session = Depends(get_db)
):
    verify_staff_csrf(request, csrf_token)
    room = db.get(RoomType, room_type_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room type not found")

    s_date = date.fromisoformat(start_date)
    e_date = date.fromisoformat(end_date)

    if e_date < s_date:
        return RedirectResponse(
            url=f"/staff/calendar?room_type_id={room_type_id}&error=End+date+must+be+equal+to+or+after+start+date.",
            status_code=status.HTTP_303_SEE_OTHER
        )
    num_days = (e_date - s_date).days + 1
    if num_days > 180:
        return RedirectResponse(
            url=f"/staff/calendar?room_type_id={room_type_id}&error=Batch+range+cannot+exceed+180+days.",
            status_code=status.HTTP_303_SEE_OTHER
        )

    # Parse rates if provided
    weekday_paise = None
    if weekday_rate_rupees and weekday_rate_rupees.strip():
        try:
            weekday_paise = parse_rupees_to_paise(weekday_rate_rupees)
        except ValueError as e:
            return RedirectResponse(
                url=f"/staff/calendar?room_type_id={room_type_id}&error={str(e)}",
                status_code=status.HTTP_303_SEE_OTHER
            )

    weekend_paise = None
    if weekend_rate_rupees and weekend_rate_rupees.strip():
        try:
            weekend_paise = parse_rupees_to_paise(weekend_rate_rupees)
        except ValueError as e:
            return RedirectResponse(
                url=f"/staff/calendar?room_type_id={room_type_id}&error={str(e)}",
                status_code=status.HTTP_303_SEE_OTHER
            )

    # Validate allotment bounds
    if total_allotment is not None:
        if total_allotment < 0 or total_allotment > room.total_inventory:
            return RedirectResponse(
                url=f"/staff/calendar?room_type_id={room_type_id}&error=Total+allotment+must+be+between+0+and+{room.total_inventory}.",
                status_code=status.HTTP_303_SEE_OTHER
            )

    # Single Transaction check: Load existing allotments
    target_dates = [s_date + timedelta(days=i) for i in range(num_days)]
    existing_allots = db.scalars(
        select(Allotment).where(
            Allotment.room_type_id == room_type_id,
            Allotment.date.in_(target_dates)
        )
    ).all()
    allot_map = {a.date: a for a in existing_allots}

    # If lowering allotment, verify that no date falls below sold+held
    if total_allotment is not None:
        failing_dates = []
        for d in target_dates:
            alt = allot_map.get(d)
            if alt and total_allotment < (alt.sold + alt.held):
                failing_dates.append(f"{d} (sold {alt.sold}, held {alt.held})")
        if failing_dates:
            err = f"Cannot set allotment to {total_allotment}. The following dates exceed this limit: " + ", ".join(failing_dates[:5])
            if len(failing_dates) > 5:
                err += f" and {len(failing_dates)-5} more."
            return RedirectResponse(
                url=f"/staff/calendar?room_type_id={room_type_id}&error={err}",
                status_code=status.HTTP_303_SEE_OTHER
            )

    # Load existing daily rates
    existing_rates = db.scalars(
        select(DailyRate).where(
            DailyRate.room_type_id == room_type_id,
            DailyRate.date.in_(target_dates)
        )
    ).all()
    rates_map = {r.date: r for r in existing_rates}

    updated_count = 0
    # Apply batch updates in one transaction
    for d in target_dates:
        is_weekend = d.weekday() in (4, 5)  # Friday or Saturday
        target_rate = weekend_paise if is_weekend else weekday_paise

        if target_rate is not None:
            dr = rates_map.get(d)
            if not dr:
                dr = DailyRate(room_type_id=room_type_id, date=d, price_paise=target_rate)
                db.add(dr)
            else:
                dr.price_paise = target_rate

        alt = allot_map.get(d)
        if not alt:
            alt = Allotment(
                room_type_id=room_type_id,
                date=d,
                total=total_allotment if total_allotment is not None else room.total_inventory,
                sold=0,
                held=0,
                blackout=(blackout_action == "enable")
            )
            db.add(alt)
        else:
            if total_allotment is not None:
                alt.total = total_allotment
            if blackout_action == "enable":
                alt.blackout = True
            elif blackout_action == "disable":
                alt.blackout = False

        updated_count += 1

    log_audit_event(
        db, current_user, "batch_calendar_update", "room_type", room_type_id,
        {
            "range": f"{start_date} to {end_date}",
            "days_updated": updated_count,
            "weekday_paise": weekday_paise,
            "weekend_paise": weekend_paise,
            "total_allotment": total_allotment,
            "blackout_action": blackout_action
        }
    )
    db.commit()

    return RedirectResponse(
        url=f"/staff/calendar?room_type_id={room_type_id}&success=Batch+update+applied+successfully+to+{updated_count}+dates.",
        status_code=status.HTTP_303_SEE_OTHER
    )


# -----------------------------------------------------------------------------
# Promo Codes Administration
# -----------------------------------------------------------------------------
@router.get("/promos", response_class=HTMLResponse)
def view_promos(
    request: Request,
    success: Optional[str] = None,
    error: Optional[str] = None,
    current_user: User = Depends(require_role("reservations", "gm")),
    db: Session = Depends(get_db)
):
    promos = db.scalars(select(PromoCode).order_by(PromoCode.valid_from.desc())).all()
    csrf_token = get_staff_csrf_token(request)
    today = date.today()
    return templates.TemplateResponse(request, "staff/promos.html", {
        "app_name": settings.app_name,
        "active_tab": "promos",
        "current_user": current_user,
        "promos": promos,
        "today_str": today.strftime("%Y-%m-%d"),
        "next_year_str": (today + timedelta(days=365)).strftime("%Y-%m-%d"),
        "csrf_token": csrf_token,
        "success_msg": success,
        "error_msg": error
    })


@router.post("/promos/save")
def save_promo(
    request: Request,
    code: str = Form(...),
    discount_percent: str = Form(...),
    valid_from: str = Form(...),
    valid_to: str = Form(...),
    csrf_token: str = Form(...),
    current_user: User = Depends(require_role("reservations", "gm")),
    db: Session = Depends(get_db)
):
    verify_staff_csrf(request, csrf_token)
    code_clean = code.strip().upper()
    if not code_clean:
        return RedirectResponse(url="/staff/promos?error=Promo+code+is+required", status_code=status.HTTP_303_SEE_OTHER)

    try:
        discount_bps = parse_percent_to_bps(discount_percent)
    except ValueError as e:
        return RedirectResponse(url=f"/staff/promos?error={str(e)}", status_code=status.HTTP_303_SEE_OTHER)

    v_from = date.fromisoformat(valid_from)
    v_to = date.fromisoformat(valid_to)
    if v_to < v_from:
        return RedirectResponse(url="/staff/promos?error=Valid+until+must+be+after+valid+from", status_code=status.HTTP_303_SEE_OTHER)

    existing = db.get(PromoCode, code_clean)
    if existing:
        existing.discount_bps = discount_bps
        existing.valid_from = v_from
        existing.valid_to = v_to
        existing.is_active = True
        action = "update_promo"
    else:
        existing = PromoCode(
            code=code_clean,
            discount_bps=discount_bps,
            discount_flat_paise=0,
            valid_from=v_from,
            valid_to=v_to,
            is_active=True
        )
        db.add(existing)
        action = "create_promo"

    log_audit_event(
        db, current_user, action, "promo_code", code_clean,
        {"discount_bps": discount_bps, "valid_from": valid_from, "valid_to": valid_to}
    )
    db.commit()

    return RedirectResponse(
        url=f"/staff/promos?success=Promotion+{code_clean}+saved+successfully.",
        status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/promos/toggle-active")
def toggle_promo_active(
    request: Request,
    code: str = Form(...),
    csrf_token: str = Form(...),
    current_user: User = Depends(require_role("reservations", "gm")),
    db: Session = Depends(get_db)
):
    verify_staff_csrf(request, csrf_token)
    promo = db.get(PromoCode, code)
    if not promo:
        raise HTTPException(status_code=404, detail="Promo code not found")

    promo.is_active = not promo.is_active
    log_audit_event(
        db, current_user, "toggle_promo", "promo_code", code,
        {"is_active": promo.is_active}
    )
    db.commit()

    state = "reactivated" if promo.is_active else "deactivated"
    return RedirectResponse(
        url=f"/staff/promos?success=Promotion+{code}+{state}.",
        status_code=status.HTTP_303_SEE_OTHER
    )


# -----------------------------------------------------------------------------
# Bookings Ledger, Refund Queue & CSV Export
# -----------------------------------------------------------------------------
@router.get("/bookings", response_class=HTMLResponse)
def view_bookings(
    request: Request,
    status: Optional[str] = None,
    filter_date: Optional[str] = None,
    success: Optional[str] = None,
    error: Optional[str] = None,
    current_user: User = Depends(require_role("reservations", "gm")),
    db: Session = Depends(get_db)
):
    # Query Needs Refund queue
    refund_q = db.scalars(
        select(Payment).where(Payment.status == "needs_refund").order_by(Payment.created_at.desc())
    ).all()
    refund_queue = []
    for p in refund_q:
        b = db.get(Booking, p.booking_id)
        if b:
            refund_queue.append({"payment": p, "booking": b})

    # Main bookings query
    stmt = select(Booking).order_by(Booking.created_at.desc())
    if status:
        stmt = stmt.where(Booking.status == status)
    if filter_date:
        f_date = date.fromisoformat(filter_date)
        stmt = stmt.where(Booking.check_in == f_date)

    bookings = db.scalars(stmt.limit(100)).all()
    csrf_token = get_staff_csrf_token(request)

    return templates.TemplateResponse(request, "staff/bookings.html", {
        "app_name": settings.app_name,
        "active_tab": "bookings",
        "current_user": current_user,
        "bookings": bookings,
        "refund_queue": refund_queue,
        "filter_status": status or "",
        "filter_date_val": filter_date or "",
        "selected_date_str": date.today().strftime("%Y-%m-%d"),
        "csrf_token": csrf_token,
        "success_msg": success,
        "error_msg": error
    })


@router.post("/bookings/mark-refunded")
def mark_payment_refunded(
    request: Request,
    payment_id: str = Form(...),
    csrf_token: str = Form(...),
    current_user: User = Depends(require_role("reservations", "gm")),
    db: Session = Depends(get_db)
):
    """
    Conditional idempotent update: needs_refund -> refunded.
    If already refunded or not in needs_refund, returns cleanly.
    """
    verify_staff_csrf(request, csrf_token)
    
    # Conditional atomic update
    res = db.execute(
        text("UPDATE payments SET status = 'refunded' WHERE id = :pid AND status = 'needs_refund' RETURNING id"),
        {"pid": payment_id}
    )
    row = res.first()
    if row:
        log_audit_event(
            db, current_user, "mark_refunded", "payment", payment_id,
            {"note": "Simulated customer reversal dispatched"}
        )
        db.commit()
        msg = f"Payment {payment_id} marked as refunded."
    else:
        msg = f"Payment {payment_id} was already processed or not in refund queue."

    return RedirectResponse(
        url=f"/staff/bookings?success={msg}",
        status_code=status.HTTP_303_SEE_OTHER
    )


@router.get("/bookings/export-csv")
def export_bookings_csv(
    date_str: str,
    current_user: User = Depends(require_role("reservations", "gm")),
    db: Session = Depends(get_db)
):
    """
    Export bookings for a specific check-in date as CSV.
    Formula-leading cells are sanitized against spreadsheet injection.
    """
    d = date_str.strip()
    target_d = date.fromisoformat(d)
    
    bookings = db.scalars(
        select(Booking).where(Booking.check_in == target_d).order_by(Booking.reference)
    ).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Reference", "Guest Name", "Guest Email", "Guest Phone",
        "Room Type", "Rate Plan", "Check In", "Check Out",
        "Guests", "Grand Total (Paise)", "Status", "Created At"
    ])

    for b in bookings:
        writer.writerow([
            sanitize_csv_cell(b.reference),
            sanitize_csv_cell(b.guest_name),
            sanitize_csv_cell(b.guest_email),
            sanitize_csv_cell(b.guest_phone),
            sanitize_csv_cell(b.room_type_id),
            sanitize_csv_cell(b.rate_plan_id),
            str(b.check_in),
            str(b.check_out),
            b.num_guests,
            b.grand_total_paise,
            b.status,
            b.created_at.isoformat()
        ])

    output.seek(0)
    filename = f"plantation_bookings_{d}.csv"
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
