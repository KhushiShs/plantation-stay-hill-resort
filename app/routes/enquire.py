"""Public enquiry routes with rate limiting, CSRF, and DPDP consent."""
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
        # Invalid or reused form token
        return templates.TemplateResponse(request, "enquire.html", {
            "app_name": settings.app_name,
            "csrf_token": get_guest_csrf_token(request),
            "form_token": secrets.token_hex(16),
            "success": False,
            "error": "This form was already submitted or expired. Please refresh and try again.",
            "form_data": None
        }, status_code=400)

    # Invalidate token immediately
    request.session.pop("enquiry_form_token", None)

    # 4. DPDP consent check
    if not dpdp_consent:
        return templates.TemplateResponse(request, "enquire.html", {
            "app_name": settings.app_name,
            "csrf_token": get_guest_csrf_token(request),
            "form_token": secrets.token_hex(16),
            "success": False,
            "error": "Please provide your consent under the DPDP Act 2023 to proceed.",
            "form_data": {
                "sender_name": sender_name,
                "sender_contact": sender_contact,
                "raw_message": raw_message,
                "preferred_check_in": preferred_check_in,
                "preferred_check_out": preferred_check_out,
                "preferred_guests": preferred_guests
            }
        }, status_code=400)

    # 5. Message length cap (2,000 chars)
    trimmed_message = raw_message.strip()
    if len(trimmed_message) > 2000:
        return templates.TemplateResponse(request, "enquire.html", {
            "app_name": settings.app_name,
            "csrf_token": get_guest_csrf_token(request),
            "form_token": secrets.token_hex(16),
            "success": False,
            "error": "Enquiry message exceeds maximum allowed length of 2,000 characters.",
            "form_data": None
        }, status_code=400)

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

    # Process through pipeline
    enquiry = process_new_enquiry(
        db=db,
        raw_message=trimmed_message,
        sender_name=sender_name.strip(),
        sender_contact=sender_contact.strip(),
        channel="web_form",
        preferred_check_in=p_in,
        preferred_check_out=p_out,
        preferred_guests=p_guests
    )
    db.commit()

    return templates.TemplateResponse(request, "enquire.html", {
        "app_name": settings.app_name,
        "csrf_token": get_guest_csrf_token(request),
        "form_token": secrets.token_hex(16),
        "success": True,
        "enquiry": enquiry,
        "error": None,
        "form_data": None
    })
