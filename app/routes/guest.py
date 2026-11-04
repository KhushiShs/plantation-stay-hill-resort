"""Guest-facing routes for rooms, HTMX quotes, 3-step booking flow, and payments."""
from datetime import date, datetime, timedelta, timezone
from typing import Optional, List
import time
import secrets
from fastapi import APIRouter, Request, Depends, HTTPException, status, Form, Header
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_

from app.config import settings
from app.db import get_db
from app.models import RoomType, RatePlan, DailyRate, Allotment, Booking, BookingNight, Payment
from app.services.pricing import calculate_pricing
from app.services.allotment import (
    create_atomic_hold,
    release_booking_hold,
    confirm_booking_payment,
    release_expired_holds,
    get_stay_nights,
    SoldOutException
)
from app.security import (
    generate_booking_reference,
    generate_csrf_token,
    generate_hmac_signature,
    verify_hmac_signature,
    check_rate_limit
)
from app.validators import validate_phone_number
from app.formatters import format_paise, format_date_str, format_date_short

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# Register custom Jinja filters
templates.env.filters["format_paise"] = format_paise
templates.env.filters["format_date_str"] = format_date_str
templates.env.filters["format_date_short"] = format_date_short


def get_or_set_csrf_token(request: Request) -> str:
    """Retrieve existing CSRF token from session or create a new one."""
    token = request.session.get("csrf_token")
    if not token:
        token = generate_csrf_token()
        request.session["csrf_token"] = token
    return token


def verify_csrf_token(request: Request, submitted_token: Optional[str]) -> None:
    """Verify CSRF token against session."""
    session_token = request.session.get("csrf_token")
    if not session_token or not submitted_token or session_token != submitted_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")


def find_nearest_available_dates(session: Session, room_type_id: str, length_nights: int = 2) -> List[dict]:
    """Find the next 3 available date windows for this room type."""
    today = date.today()
    allotments = session.scalars(
        select(Allotment).where(
            Allotment.room_type_id == room_type_id,
            Allotment.date >= today,
            Allotment.date <= today + timedelta(days=60)
        ).order_by(Allotment.date.asc())
    ).all()
    
    avail_by_date = {a.date: (a.total - a.sold - a.held > 0 and not a.blackout) for a in allotments}
    candidates = []
    
    curr = today
    while curr <= today + timedelta(days=50) and len(candidates) < 3:
        all_ok = True
        for i in range(length_nights):
            d = curr + timedelta(days=i)
            if not avail_by_date.get(d, False):
                all_ok = False
                break
        if all_ok:
            candidates.append({"check_in": curr, "check_out": curr + timedelta(days=length_nights)})
            curr += timedelta(days=length_nights)  # Step forward
        else:
            curr += timedelta(days=1)
            
    return candidates


# ---------------------------------------------------------
# Screen 1: Home
# ---------------------------------------------------------
@router.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    # Lazy release expired holds
    release_expired_holds(db)
    
    room_types = db.scalars(select(RoomType).order_by(RoomType.base_price_paise.asc())).all()
    today = date.today()
    
    # Calculate real dynamic "From Rs X" = minimum upcoming daily rate
    room_list = []
    for rt in room_types:
        min_rate = db.scalar(
            select(func.min(DailyRate.price_paise)).where(
                DailyRate.room_type_id == rt.id,
                DailyRate.date >= today
            )
        )
        room_list.append({
            "id": rt.id,
            "name": rt.name,
            "description": rt.description,
            "base_occupancy": rt.base_occupancy,
            "max_occupancy": rt.max_occupancy,
            "total_inventory": rt.total_inventory,
            "image_url": rt.image_url,
            "min_rate_paise": min_rate or rt.base_price_paise
        })
        
    return templates.TemplateResponse(request, "home.html", {
        "app_name": settings.app_name,
        "room_types": room_list
    })


# ---------------------------------------------------------
# Screen 2: Room Page with 30-Day Calendar & HTMX Quote
# ---------------------------------------------------------
@router.get("/rooms/{room_type_id}", response_class=HTMLResponse)
def room_detail(room_type_id: str, request: Request, check_in: Optional[date] = None, check_out: Optional[date] = None, db: Session = Depends(get_db)):
    release_expired_holds(db)
    room = db.get(RoomType, room_type_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room type not found")
        
    rate_plans = db.scalars(select(RatePlan).where(RatePlan.is_active == True)).all()
    today = date.today()
    
    # Up to 180 days of calendar availability and daily rates
    calendar_allotments = db.scalars(
        select(Allotment).where(
            Allotment.room_type_id == room_type_id,
            Allotment.date >= today,
            Allotment.date < today + timedelta(days=180)
        ).order_by(Allotment.date.asc())
    ).all()
    allot_map = {a.date: a for a in calendar_allotments}
    
    daily_rates = db.scalars(
        select(DailyRate).where(
            DailyRate.room_type_id == room_type_id,
            DailyRate.date >= today,
            DailyRate.date < today + timedelta(days=180)
        )
    ).all()
    rates_map = {r.date: r.price_paise for r in daily_rates}
    
    # Render all months that have rate/allotment data (up to 180 days)
    # Mon-Sun weekday layout: Monday is weekday 0, Sunday is 6
    import calendar
    calendar_months = []
    
    # Collect unique (year, month) pairs spanning the 180 days
    month_keys = []
    cur_d = today.replace(day=1)
    end_d = today + timedelta(days=180)
    while cur_d < end_d:
        key = (cur_d.year, cur_d.month)
        if key not in month_keys:
            month_keys.append(key)
        # Advance to next month
        if cur_d.month == 12:
            cur_d = date(cur_d.year + 1, 1, 1)
        else:
            cur_d = date(cur_d.year, cur_d.month + 1, 1)
            
    for idx, (y, m) in enumerate(month_keys):
        cal = calendar.Calendar(firstweekday=0)  # Monday first
        month_days = []
        month_name = date(y, m, 1).strftime("%B %Y")
        month_iso = f"{y:04d}-{m:02d}"
        
        for d in cal.itermonthdates(y, m):
            in_current_month = (d.month == m)
            is_past = (d < today)
            alt = allot_map.get(d)
            price = rates_map.get(d, room.base_price_paise)
            remaining = (alt.total - alt.sold - alt.held) if alt else 0
            is_blackout = (alt.blackout if alt else False)
            available = (remaining > 0) and not is_blackout and not is_past and in_current_month
            sold_out = (not available and not is_past and in_current_month)
            disabled = (not available) if not in_current_month else (is_past or not available)

            month_days.append({
                "date": d,
                "iso": d.isoformat(),
                "day_num": d.day,
                "in_month": in_current_month,
                "is_past": is_past,
                "price_paise": price,
                "remaining": remaining,
                "available": available,
                "sold_out": sold_out,
                "disabled": (is_past or not available)
            })
            
        calendar_months.append({
            "name": month_name,
            "month_iso": month_iso,
            "days": month_days,
            "is_first": (idx == 0)
        })
    
    calendar_days = []
    for i in range(30):
        d = today + timedelta(days=i)
        alt = allot_map.get(d)
        price = rates_map.get(d, room.base_price_paise)
        remaining = (alt.total - alt.sold - alt.held) if alt else 0
        available = (remaining > 0) and not (alt.blackout if alt else False)
        calendar_days.append({
            "date": d,
            "price_paise": price,
            "remaining": remaining,
            "available": available
        })
        
    def_check_in = check_in or (today + timedelta(days=1))
    def_check_out = check_out or (today + timedelta(days=3))
    
    # Generate initial quote HTML
    stay_dates = get_stay_nights(def_check_in, def_check_out)
    is_avail = True
    for d in stay_dates:
        alt = allot_map.get(d)
        if not alt or (alt.total - alt.sold - alt.held <= 0) or alt.blackout:
            is_avail = False
            break
            
    breakdown = None
    nearest = []
    if is_avail:
        breakdown = calculate_pricing(db, room_type_id, rate_plans[0].id, stay_dates, num_guests=2)
    else:
        nearest = find_nearest_available_dates(db, room_type_id, len(stay_dates))
        
    initial_quote_html = templates.get_template("partials/price_quote.html").render({
        "request": request,
        "room_type": room,
        "rate_plan_id": rate_plans[0].id,
        "check_in": def_check_in,
        "check_out": def_check_out,
        "num_guests": 2,
        "promo_code": "",
        "is_available": is_avail,
        "breakdown": breakdown,
        "nearest_dates": nearest,
        "requested_nights": len(stay_dates)
    })
    
    return templates.TemplateResponse(request, "room_detail.html", {
        "app_name": settings.app_name,
        "room": room,
        "rate_plans": rate_plans,
        "calendar_days": calendar_days,
        "calendar_months": calendar_months,
        "default_check_in": def_check_in.strftime("%Y-%m-%d"),
        "default_check_out": def_check_out.strftime("%Y-%m-%d"),
        "initial_quote_html": initial_quote_html
    })


@router.get("/rooms/{room_type_id}/quote", response_class=HTMLResponse)
def get_quote_fragment(
    room_type_id: str,
    check_in: date,
    check_out: date,
    rate_plan_id: str,
    request: Request,
    num_guests: int = 1,
    promo_code: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """HTMX quote partial endpoint."""
    release_expired_holds(db)
    room = db.get(RoomType, room_type_id)
    if not room or check_out <= check_in:
        return "<p class='caption-line' style='color: var(--color-accent);'>Invalid dates selected.</p>"
        
    stay_dates = get_stay_nights(check_in, check_out)
    
    # Check live allotment
    allotments = db.scalars(
        select(Allotment).where(
            Allotment.room_type_id == room_type_id,
            Allotment.date.in_(stay_dates)
        )
    ).all()
    allot_map = {a.date: a for a in allotments}
    
    is_available = len(allotments) == len(stay_dates)
    for d in stay_dates:
        alt = allot_map.get(d)
        if not alt or (alt.total - alt.sold - alt.held < 1) or alt.blackout:
            is_available = False
            break
            
    breakdown = None
    nearest_dates = []
    if is_available:
        breakdown = calculate_pricing(db, room_type_id, rate_plan_id, stay_dates, num_guests, promo_code)
    else:
        nearest_dates = find_nearest_available_dates(db, room_type_id, len(stay_dates))
        
    return templates.TemplateResponse(request, "partials/price_quote.html", {
        "room_type": room,
        "rate_plan_id": rate_plan_id,
        "check_in": check_in,
        "check_out": check_out,
        "num_guests": num_guests,
        "promo_code": promo_code or "",
        "is_available": is_available,
        "breakdown": breakdown,
        "nearest_dates": nearest_dates,
        "requested_nights": len(stay_dates)
    })


# ---------------------------------------------------------
# Screen 3: Booking Stepper (Step 1 & 2)
# ---------------------------------------------------------
@router.get("/book", response_class=HTMLResponse)
def book_step_1_2(
    request: Request,
    room_type_id: str,
    rate_plan_id: str,
    check_in: date,
    check_out: date,
    num_guests: int = 1,
    num_rooms: int = 1,
    promo_code: Optional[str] = None,
    db: Session = Depends(get_db)
):
    release_expired_holds(db)
    room = db.get(RoomType, room_type_id)
    rate_plan = db.get(RatePlan, rate_plan_id)
    if not room or not rate_plan:
        raise HTTPException(status_code=404, detail="Invalid booking parameters")
        
    stay_dates = get_stay_nights(check_in, check_out)
    breakdown = calculate_pricing(db, room_type_id, rate_plan_id, stay_dates, num_guests, promo_code)
    csrf_token = get_or_set_csrf_token(request)
    
    return templates.TemplateResponse(request, "booking_step1_2.html", {
        "app_name": settings.app_name,
        "room": room,
        "rate_plan": rate_plan,
        "check_in": check_in,
        "check_out": check_out,
        "num_guests": num_guests,
        "num_rooms": num_rooms,
        "promo_code": promo_code or "",
        "breakdown": breakdown,
        "csrf_token": csrf_token
    })


@router.post("/book/hold")
def create_hold_endpoint(
    request: Request,
    csrf_token: str = Form(...),
    room_type_id: str = Form(...),
    rate_plan_id: str = Form(...),
    check_in: date = Form(...),
    check_out: date = Form(...),
    num_guests: int = Form(1),
    num_rooms: int = Form(1),
    guest_name: str = Form(...),
    guest_email: str = Form(...),
    guest_phone: str = Form(...),
    dpdp_consent: bool = Form(False),
    promo_code: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    # Rate limit check on /book/hold
    check_rate_limit(request, "book_hold", max_requests=10, window_seconds=60)
    verify_csrf_token(request, csrf_token)
    
    # Phone validation
    is_valid_phone, phone_err, cleaned_phone = validate_phone_number(guest_phone)
    if not is_valid_phone:
        stay_dates = get_stay_nights(check_in, check_out)
        breakdown = calculate_pricing(db, room_type_id, rate_plan_id, stay_dates, num_guests, promo_code)
        room = db.get(RoomType, room_type_id)
        rate_plan = db.get(RatePlan, rate_plan_id)
        return templates.TemplateResponse(request, "booking_step1_2.html", {
            "app_name": settings.app_name,
            "room": room,
            "rate_plan": rate_plan,
            "check_in": check_in,
            "check_out": check_out,
            "num_guests": num_guests,
            "num_rooms": num_rooms,
            "promo_code": promo_code or "",
            "breakdown": breakdown,
            "csrf_token": get_or_set_csrf_token(request),
            "error": "Please correct the phone number below.",
            "phone_error": phone_err,
            "form_data": {
                "guest_name": guest_name,
                "guest_email": guest_email,
                "guest_phone": guest_phone
            }
        }, status_code=400)

    if not dpdp_consent:
        raise HTTPException(status_code=422, detail="DPDP Act 2023 consent is required to proceed.")
        
    stay_dates = get_stay_nights(check_in, check_out)
    
    # Recompute price server-side
    breakdown = calculate_pricing(db, room_type_id, rate_plan_id, stay_dates, num_guests, promo_code)
    
    try:
        # Atomic hold on allotment
        create_atomic_hold(db, room_type_id, stay_dates, num_rooms)
    except SoldOutException:
        nearest = find_nearest_available_dates(db, room_type_id, len(stay_dates))
        return templates.TemplateResponse(request, "errors/sold_out.html", {
            "app_name": settings.app_name,
            "room_type_id": room_type_id,
            "nearest_dates": nearest
        }, status_code=409)
        
    # Generate unguessable reference
    ref = generate_booking_reference()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.hold_minutes)
    
    booking = Booking(
        reference=ref,
        room_type_id=room_type_id,
        rate_plan_id=rate_plan_id,
        check_in=check_in,
        check_out=check_out,
        num_guests=num_guests,
        num_rooms=num_rooms,
        status="held",
        hold_expires_at=expires_at,
        guest_name=guest_name.strip(),
        guest_email=guest_email.strip().lower(),
        guest_phone=cleaned_phone,
        dpdp_consent=True,
        room_total_paise=breakdown.room_total_paise,
        discount_paise=breakdown.discount_paise,
        gst_paise=breakdown.gst_paise,
        grand_total_paise=breakdown.grand_total_paise,
        promo_code=breakdown.promo_code
    )
    db.add(booking)
    db.flush()
    
    # Store snapshot of nightly rates
    for n in breakdown.nights:
        bn = BookingNight(
            booking_id=booking.id,
            date=n.date,
            base_rate_paise=n.base_rate_paise,
            breakfast_addon_paise=n.breakfast_addon_paise,
            discount_paise=n.discount_paise,
            taxable_amount_paise=n.taxable_amount_paise,
            gst_bps=n.gst_bps,
            gst_paise=n.gst_paise,
            total_night_paise=n.total_night_paise
        )
        db.add(bn)
        
    # Create pending payment at Step 3
    payment_id = f"PAY-{secrets.token_hex(8).upper()}"
    payment = Payment(
        id=payment_id,
        booking_id=booking.id,
        amount_paise=breakdown.grand_total_paise,
        status="pending",
        provider="mock"
    )
    db.add(payment)
    db.commit()
    
    # Tie guest session securely to this booking reference
    request.session["guest_booking_ref"] = ref
    
    return RedirectResponse(f"/book/{ref}/pay", status_code=status.HTTP_303_SEE_OTHER)


# ---------------------------------------------------------
# Screen 3: Step 3 Mock Payment Gateway
# ---------------------------------------------------------
@router.get("/book/{reference}/pay", response_class=HTMLResponse)
def mock_payment_page(reference: str, request: Request, db: Session = Depends(get_db)):
    release_expired_holds(db)
    booking = db.scalar(select(Booking).where(Booking.reference == reference))
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
        
    # Check session authorization
    if request.session.get("guest_booking_ref") != reference:
        raise HTTPException(status_code=403, detail="Unauthorized booking session")
        
    # Check if already confirmed
    if booking.status == "confirmed":
        return RedirectResponse(f"/booking/{reference}", status_code=status.HTTP_303_SEE_OTHER)
        
    now = datetime.now(timezone.utc)
    if booking.status != "held" or (booking.hold_expires_at and booking.hold_expires_at <= now):
        # Hold expired!
        release_booking_hold(db, booking.id, reason="expired")
        db.commit()
        return templates.TemplateResponse(request, "errors/hold_expired.html", {
            "app_name": settings.app_name
        }, status_code=410)
        
    remaining_secs = max(0, int((booking.hold_expires_at - now).total_seconds()))
    csrf_token = get_or_set_csrf_token(request)
    
    room = db.get(RoomType, booking.room_type_id)
    room_name = room.name if room else booking.room_type_id
    nights = db.scalars(select(BookingNight).where(BookingNight.booking_id == booking.id)).all()
    nights_count = len(nights) if nights else max(1, (booking.check_out - booking.check_in).days)
    payment_failed = request.query_params.get("failed") == "1"

    return templates.TemplateResponse(request, "booking_payment.html", {
        "app_name": settings.app_name,
        "booking": booking,
        "room_name": room_name,
        "nights_count": nights_count,
        "payment_failed": payment_failed,
        "remaining_seconds": remaining_secs,
        "minutes_left": remaining_secs // 60,
        "seconds_left": remaining_secs % 60,
        "hold_minutes": settings.hold_minutes,
        "csrf_token": csrf_token
    })


@router.post("/book/{reference}/mock-pay")
def mock_pay_action(
    reference: str,
    request: Request,
    csrf_token: str = Form(...),
    db: Session = Depends(get_db)
):
    verify_csrf_token(request, csrf_token)
    if request.session.get("guest_booking_ref") != reference:
        raise HTTPException(status_code=403, detail="Unauthorized booking session")
        
    booking = db.scalar(select(Booking).where(Booking.reference == reference))
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
        
    payment = db.scalar(
        select(Payment).where(Payment.booking_id == booking.id, Payment.status == "pending")
    )
    if not payment:
        raise HTTPException(status_code=400, detail="No pending payment found")
        
    # Server signs the payload
    sig = generate_hmac_signature(f"{payment.id}:{booking.id}:{payment.amount_paise}:{int(time.time())}")
    
    result = confirm_booking_payment(db, payment.id, booking.id, payment.amount_paise, signature=sig)
    db.commit()
    
    if result in ("confirmed", "confirmed_after_rehold", "already_confirmed"):
        return RedirectResponse(f"/booking/{reference}", status_code=status.HTTP_303_SEE_OTHER)
    elif result == "needs_refund":
        return templates.TemplateResponse(request, "errors/hold_expired.html", {
            "app_name": settings.app_name,
            "message": "Your hold expired and the room was sold to another guest. Your mock payment has been registered for an automated refund."
        }, status_code=409)


@router.post("/book/{reference}/mock-fail")
def mock_fail_action(
    reference: str,
    request: Request,
    csrf_token: str = Form(...),
    db: Session = Depends(get_db)
):
    verify_csrf_token(request, csrf_token)
    if request.session.get("guest_booking_ref") != reference:
        raise HTTPException(status_code=403, detail="Unauthorized booking session")
        
    booking = db.scalar(select(Booking).where(Booking.reference == reference))
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Payment fails must NOT release the hold.
    # Keep booking in 'held' status so guest can retry before hold expiry.
    return RedirectResponse(f"/book/{reference}/pay?failed=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/book/{reference}/mock-abandon")
def mock_abandon_action(
    reference: str,
    request: Request,
    csrf_token: str = Form(...),
    db: Session = Depends(get_db)
):
    verify_csrf_token(request, csrf_token)
    if request.session.get("guest_booking_ref") != reference:
        raise HTTPException(status_code=403, detail="Unauthorized booking session")
        
    booking = db.scalar(select(Booking).where(Booking.reference == reference))
    if booking:
        release_booking_hold(db, booking.id, reason="cancelled")
        payment = db.scalar(select(Payment).where(Payment.booking_id == booking.id, Payment.status == "pending"))
        if payment:
            payment.status = "failed"
        db.commit()
        
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)


# ---------------------------------------------------------
# Webhook Endpoint (HMAC Signed)
# ---------------------------------------------------------
@router.post("/api/webhooks/payment")
async def payment_webhook(request: Request, db: Session = Depends(get_db)):
    """
    HMAC signed webhook endpoint.
    Payload signed as: payment_id:booking_id:amount:timestamp
    Rejects timestamps older than 5 minutes (300 seconds) -> 400.
    Compares amount to stored payment amount; ignores client body amount tampering.
    """
    x_signature = request.headers.get("X-Signature")
    if not x_signature:
        raise HTTPException(status_code=400, detail="Missing X-Signature header")
        
    try:
        body = await request.json()
        payment_id = body.get("payment_id")
        booking_id = body.get("booking_id")
        timestamp = int(body.get("timestamp", 0))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
        
    now = int(time.time())
    if abs(now - timestamp) > 300:
        raise HTTPException(status_code=400, detail="Timestamp stale or invalid")
        
    payment = db.get(Payment, payment_id)
    if not payment or payment.booking_id != booking_id:
        raise HTTPException(status_code=400, detail="Payment record mismatch")
        
    # Verify signature against stored amount
    expected_payload = f"{payment.id}:{booking_id}:{payment.amount_paise}:{timestamp}"
    if not verify_hmac_signature(expected_payload, x_signature):
        raise HTTPException(status_code=400, detail="Invalid HMAC signature")
        
    result = confirm_booking_payment(db, payment.id, booking_id, payment.amount_paise, signature=x_signature)
    db.commit()
    
    return {"status": "ok", "result": result}


# ---------------------------------------------------------
# Screen 4: Confirmation Pass
# ---------------------------------------------------------
@router.get("/booking/{reference}", response_class=HTMLResponse)
def booking_confirmation_page(reference: str, request: Request, db: Session = Depends(get_db)):
    booking = db.scalar(select(Booking).where(Booking.reference == reference))
    if not booking or booking.status != "confirmed":
        raise HTTPException(status_code=404, detail="Confirmed booking not found")
        
    room = db.get(RoomType, booking.room_type_id)
    rate_plan = db.get(RatePlan, booking.rate_plan_id)
    
    return templates.TemplateResponse(request, "booking_confirmation.html", {
        "app_name": settings.app_name,
        "booking": booking,
        "room": room,
        "rate_plan": rate_plan
    })


# ---------------------------------------------------------
# Booking Lookup Tool
# ---------------------------------------------------------
@router.get("/booking-lookup", response_class=HTMLResponse)
def lookup_form(request: Request):
    csrf_token = get_or_set_csrf_token(request)
    return templates.TemplateResponse(request, "booking_lookup.html", {
        "app_name": settings.app_name,
        "csrf_token": csrf_token,
        "error": None
    })


@router.post("/booking-lookup", response_class=HTMLResponse)
def process_lookup(
    request: Request,
    reference: str = Form(...),
    email: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db)
):
    check_rate_limit(request, "booking_lookup", max_requests=10, window_seconds=60)
    verify_csrf_token(request, csrf_token)
    
    clean_ref = reference.strip().upper()
    clean_email = email.strip().lower()
    
    booking = db.scalar(
        select(Booking).where(
            Booking.reference == clean_ref,
            func.lower(Booking.guest_email) == clean_email
        )
    )
    
    if not booking or booking.status != "confirmed":
        # Identical uniform error message
        return templates.TemplateResponse(request, "booking_lookup.html", {
            "app_name": settings.app_name,
            "csrf_token": csrf_token,
            "reference": reference,
            "email": email,
            "error": "No booking found with this reference and email combination."
        }, status_code=404)
        
    return RedirectResponse(f"/booking/{clean_ref}", status_code=status.HTTP_303_SEE_OTHER)
