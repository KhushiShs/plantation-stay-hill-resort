"""Public enquiry routes with rate limiting, CSRF, DPDP consent, and phone validation."""
import secrets
from datetime import date
from typing import Optional
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.security import generate_csrf_token, check_rate_limit
from app.services.enquiry_service import process_new_enquiry
from app.validators import validate_phone_number

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def get_guest_csrf_token(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = generate_csrf_token()
        request.session["csrf_token"] = token
    return token


def verify_guest_csrf(request: Request, submitted_token: str):
    session_token = request.session.get("csrf_token")
    if not session_token or session_token != submitted_token:
        raise HTTPException(status_code=403, detail="Invalid or expired CSRF token")


@router.get("/enquire", response_class=HTMLResponse)
def get_enquire_page(request: Request):
    """Renders the public enquiry web form."""
    csrf_token = get_guest_csrf_token(request)
    form_token = secrets.token_hex(16)
    request.session["enquiry_form_token"] = form_token

    return templates.TemplateResponse(request, "enquire.html", {
        "app_name": settings.app_name,
        "csrf_token": csrf_token,
        "form_token": form_token,
        "success": False,
        "error": None,
        "phone_error": None,
        "form_data": None
    })


@router.post("/enquire", response_class=HTMLResponse)
def post_enquiry(
    request: Request,
    csrf_token: str = Form(...),
    form_token: str = Form(...),
    sender_name: str = Form(...),
    sender_contact: str = Form(...),
    raw_message: str = Form(...),
    event_type: Optional[str] = Form(None),
    preferred_venue: Optional[str] = Form(None),
    budget_range: Optional[str] = Form(None),
    preferred_check_in: Optional[str] = Form(None),
    preferred_check_out: Optional[str] = Form(None),
    preferred_guests: Optional[str] = Form(None),
    dpdp_consent: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """Handles public enquiry submissions."""
    # 1. CSRF Validation
    verify_guest_csrf(request, csrf_token)

    # 2. Rate limit: 5 enquiries per IP per minute
    check_rate_limit(request, "public_enquire", max_requests=5, window_seconds=60)

    # 3. Double submit prevention token
    stored_token = request.session.get("enquiry_form_token")
    if not stored_token or stored_token != form_token:
        return templates.TemplateResponse(request, "enquire.html", {
            "app_name": settings.app_name,
            "csrf_token": get_guest_csrf_token(request),
            "form_token": secrets.token_hex(16),
            "success": False,
            "error": "This form was already submitted or expired. Please refresh and try again.",
            "phone_error": None,
            "form_data": None
        }, status_code=400)

    form_data = {
        "sender_name": sender_name,
        "sender_contact": sender_contact,
        "raw_message": raw_message,
        "event_type": event_type,
        "preferred_venue": preferred_venue,
        "budget_range": budget_range,
        "preferred_check_in": preferred_check_in,
        "preferred_check_out": preferred_check_out,
        "preferred_guests": preferred_guests
    }

    # 4. Contact validation: If sender_contact contains '+' or digits (phone format), validate phone rules
    # If not email (@), enforce full phone rules
    contact_val = sender_contact.strip()
    phone_err = None
    if "@" not in contact_val:
        # Validate as phone number
        is_valid_phone, phone_err, cleaned_phone = validate_phone_number(contact_val)
        if not is_valid_phone:
            return templates.TemplateResponse(request, "enquire.html", {
                "app_name": settings.app_name,
                "csrf_token": get_guest_csrf_token(request),
                "form_token": form_token,  # Keep token so user can correct without full reload
                "success": False,
                "error": "Please correct the contact number below.",
                "phone_error": phone_err,
                "form_data": form_data
            }, status_code=400)
        contact_val = cleaned_phone
    else:
        # Simple email sanity check
        if len(contact_val) < 5 or "." not in contact_val:
            return templates.TemplateResponse(request, "enquire.html", {
                "app_name": settings.app_name,
                "csrf_token": get_guest_csrf_token(request),
                "form_token": form_token,
                "success": False,
                "error": "Please enter a valid email address or phone number.",
                "phone_error": None,
                "form_data": form_data
            }, status_code=400)

    # 5. DPDP consent check
    if not dpdp_consent:
        return templates.TemplateResponse(request, "enquire.html", {
            "app_name": settings.app_name,
            "csrf_token": get_guest_csrf_token(request),
            "form_token": form_token,
            "success": False,
            "error": "Please provide your consent under the DPDP Act 2023 to proceed.",
            "phone_error": None,
            "form_data": form_data
        }, status_code=400)

    # 6. Message length cap (2,000 chars)
    trimmed_message = raw_message.strip()
    if len(trimmed_message) > 2000:
        return templates.TemplateResponse(request, "enquire.html", {
            "app_name": settings.app_name,
            "csrf_token": get_guest_csrf_token(request),
            "form_token": form_token,
            "success": False,
            "error": "Enquiry message exceeds maximum allowed length of 2,000 characters.",
            "phone_error": None,
            "form_data": form_data
        }, status_code=400)

    # Invalidate token only upon passing all validations
    request.session.pop("enquiry_form_token", None)

    # Parse dates & guests if provided
    p_in = None
    p_out = None
    p_guests = None
    if preferred_check_in:
        try:
            p_in = date.fromisoformat(preferred_check_in.strip())
        except ValueError:
            pass
    if preferred_check_out:
        try:
            p_out = date.fromisoformat(preferred_check_out.strip())
        except ValueError:
            pass
    if preferred_guests:
        try:
            p_guests = int(preferred_guests.strip())
        except ValueError:
            pass

    # Build enriched message incorporating structured wedding/event selections
    details_prefix = []
    if event_type:
        details_prefix.append(f"Event Type: {event_type}")
    if preferred_venue:
        details_prefix.append(f"Venue Preference: {preferred_venue}")
    if budget_range:
        details_prefix.append(f"Budget Range: {budget_range}")

    final_raw_message = trimmed_message
    if details_prefix:
        final_raw_message = "[" + " | ".join(details_prefix) + "]\n" + trimmed_message

    # Process through pipeline
    enquiry = process_new_enquiry(
        db=db,
        raw_message=final_raw_message,
        sender_name=sender_name.strip(),
        sender_contact=contact_val,
        channel="web_form",
        preferred_check_in=p_in,
        preferred_check_out=p_out,
        preferred_guests=p_guests
    )

    return templates.TemplateResponse(request, "enquire.html", {
        "app_name": settings.app_name,
        "csrf_token": get_guest_csrf_token(request),
        "form_token": secrets.token_hex(16),
        "success": True,
        "enquiry": enquiry,
        "error": None,
        "phone_error": None,
        "form_data": None
    })
