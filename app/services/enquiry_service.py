"""Enquiry intake and management pipeline service."""
import json
import logging
from datetime import datetime, date, timezone
from typing import Optional, Tuple, Dict, Any, List

from sqlalchemy.orm import Session
from sqlalchemy import select, and_, func, desc

from app.models import Enquiry, EnquiryEvent, Alert, User
from app.services.router import (
    classify_enquiry,
    fallback_classify,
    determine_routing,
    build_draft_reply,
    verify_draft_prices,
    sanitize_extracted_dates
)

logger = logging.getLogger(__name__)


def generate_next_enquiry_id(db: Session) -> str:
    """
    Generates next ENQ-xxxx ID.
    Starts at ENQ-4413 if seed ENQ-4410/4411/4412 exist, or max(existing)+1.
    """
    rows = db.execute(select(Enquiry.id)).scalars().all()
    max_num = 4409
    for eid in rows:
        if eid.startswith("ENQ-"):
            try:
                num = int(eid.replace("ENQ-", ""))
                if num > max_num:
                    max_num = num
            except ValueError:
                pass
    next_num = max_num + 1
    return f"ENQ-{next_num}"


def process_new_enquiry(
    db: Session,
    raw_message: str,
    sender_name: str,
    sender_contact: str,
    channel: str = "web_form",
    preferred_check_in: Optional[date] = None,
    preferred_check_out: Optional[date] = None,
    preferred_guests: Optional[int] = None,
    enquiry_id: Optional[str] = None,
    force_fallback: bool = False
) -> Enquiry:
    """
    Core intake pipeline:
    1. Generates ID (or uses given ID for seeds).
    2. Runs classifier (AI with fallback, or force fallback).
    3. Merges explicit guest inputs with extracted fields.
    4. Routes via deterministic code rules (threshold, owner, complaint).
    5. Builds code-generated draft with allowed prices.
    6. Always triggers GM alert on complaint.
    7. Logs initial classification event.
    """
    eid = enquiry_id or generate_next_enquiry_id(db)

    # 1. Classification
    if force_fallback:
        res = fallback_classify(raw_message)
        classified_by = "fallback"
    else:
        res, classified_by = classify_enquiry(raw_message)

    # 2. Field reconciliation (explicit form input overrides extraction if valid)
    check_in = preferred_check_in or (res.dates.check_in if res.dates else None)
    check_out = preferred_check_out or (res.dates.check_out if res.dates else None)
    check_in, check_out = sanitize_extracted_dates(check_in, check_out)

    guests = preferred_guests or res.guests

    # 3. Routing
    category, owner_role = determine_routing(res)

    # 4. Draft Generation
    draft_reply, allowed_prices = build_draft_reply(
        db=db,
        category=category,
        guest_name=sender_name,
        check_in=check_in,
        check_out=check_out,
        guests=guests
    )

    enquiry = Enquiry(
        id=eid,
        channel=channel,
        sender_name=sender_name,
        sender_contact=sender_contact,
        raw_message=raw_message,
        category=category,
        confidence=res.confidence,
        extracted_check_in=check_in,
        extracted_check_out=check_out,
        extracted_guests=guests,
        extracted_budget=res.budget,
        summary=res.summary,
        owner_role=owner_role,
        status="new",
        classified_by=classified_by,
        draft_reply=draft_reply,
        code_inserted_prices=json.dumps(allowed_prices)
    )
    db.add(enquiry)
    db.flush()

    # 5. Events
    event = EnquiryEvent(
        enquiry_id=eid,
        event_type="classified",
        actor_id=None,
        actor_role="system",
        from_value=None,
        to_value=category,
        notes=f"Classified by {classified_by} (confidence: {float(res.confidence):.2f}) -> {category} (owner: {owner_role})"
    )
    db.add(event)

    # 6. GM Alert on complaint (regardless of confidence or channel)
    if category == "complaint" or res.category == "complaint":
        alert = Alert(
            enquiry_id=eid,
            target_role="gm",
            alert_type="complaint_received",
            message=f"Complaint received ({eid}) from {sender_name}: {res.summary}"
        )
        db.add(alert)

    db.flush()
    return enquiry


def reroute_enquiry(
    db: Session,
    enquiry: Enquiry,
    new_category: str,
    actor_user: User
) -> Tuple[bool, Optional[str]]:
    """
    One-click re-route:
    - Visibility check: user's role must be authorized to view the current enquiry.
    - Owner role updated based on new category.
    - Re-routing to complaint creates GM alert.
    - Event logged keeping original AI category and confidence for traceability.
    """
    # Allowed role mapping
    category_owners = {
        "room": "reservations",
        "wedding": "sales",
        "offsite": "sales",
        "complaint": "gm",
        "unsorted": "gm"
    }

    if new_category not in category_owners:
        return False, "Invalid target category."

    old_category = enquiry.category
    new_owner = category_owners[new_category]

    enquiry.category = new_category
    enquiry.owner_role = new_owner

    # Re-build draft for new category
    allowed_prices_list = json.loads(enquiry.code_inserted_prices or "[]")
    new_draft, new_allowed_prices = build_draft_reply(
        db=db,
        category=new_category,
        guest_name=enquiry.sender_name,
        check_in=enquiry.extracted_check_in,
        check_out=enquiry.extracted_check_out,
        guests=enquiry.extracted_guests
    )
    enquiry.draft_reply = new_draft
    enquiry.code_inserted_prices = json.dumps(new_allowed_prices)

    event = EnquiryEvent(
        enquiry_id=enquiry.id,
        event_type="rerouted",
        actor_id=actor_user.id,
        actor_role=actor_user.role,
        from_value=old_category,
        to_value=new_category,
        notes=f"Re-routed by {actor_user.full_name} ({actor_user.role}) from {old_category} to {new_category} (original classified: {enquiry.classified_by})"
    )
    db.add(event)

    # Re-routing to complaint creates GM alert if not already alerted
    if new_category == "complaint":
        existing_alert = db.query(Alert).filter(
            Alert.enquiry_id == enquiry.id,
            Alert.alert_type == "complaint_received"
        ).first()
        if not existing_alert:
            db.add(Alert(
                enquiry_id=enquiry.id,
                target_role="gm",
                alert_type="complaint_received",
                message=f"Enquiry {enquiry.id} re-routed to complaint by {actor_user.full_name}."
            ))

    db.flush()
    return True, None


def save_enquiry_draft(
    db: Session,
    enquiry: Enquiry,
    new_draft_text: str,
    actor_user: User
) -> Tuple[bool, Optional[str]]:
    """Saves updated draft text and logs an event."""
    # Verify price guard
    allowed_prices = json.loads(enquiry.code_inserted_prices or "[]")
    is_valid, err = verify_draft_prices(new_draft_text, allowed_prices)
    if not is_valid:
        return False, err

    enquiry.draft_reply = new_draft_text
    if enquiry.status == "new":
        enquiry.status = "drafted"

    event = EnquiryEvent(
        enquiry_id=enquiry.id,
        event_type="draft_saved",
        actor_id=actor_user.id,
        actor_role=actor_user.role,
        notes=f"Draft updated by {actor_user.full_name}"
    )
    db.add(event)
    db.flush()
    return True, None


def send_enquiry_reply(
    db: Session,
    enquiry: Enquiry,
    draft_text: str,
    actor_user: User
) -> Tuple[bool, Optional[str]]:
    """
    Simulated Send:
    - Price defense guard checks draft body.
    - Idempotent update (first_replied_at is never overwritten once set).
    - Status set to 'sent'.
    """
    allowed_prices = json.loads(enquiry.code_inserted_prices or "[]")
    is_valid, err = verify_draft_prices(draft_text, allowed_prices)
    if not is_valid:
        return False, err

    enquiry.draft_reply = draft_text
    enquiry.status = "sent"
    if not enquiry.first_replied_at:
        enquiry.first_replied_at = datetime.now(timezone.utc)

    event = EnquiryEvent(
        enquiry_id=enquiry.id,
        event_type="reply_sent",
        actor_id=actor_user.id,
        actor_role=actor_user.role,
        notes=f"Reply sent (simulated) by {actor_user.full_name}"
    )
    db.add(event)
    db.flush()
    return True, None


def seed_enquiries_offline(db: Session, seed_json_path: str = "data/enquiries_seed.json"):
    """
    Seeds enquiries from data/enquiries_seed.json through the real pipeline using the fallback,
    ensuring ENQ-4410, ENQ-4411, ENQ-4412 and messy cases are seeded offline.
    """
    import os
    if not os.path.exists(seed_json_path):
        logger.warning(f"Seed file {seed_json_path} not found.")
        return

    with open(seed_json_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    for item in cases:
        existing = db.get(Enquiry, item["id"])
        if not existing:
            process_new_enquiry(
                db=db,
                raw_message=item["raw_message"],
                sender_name=item["sender_name"],
                sender_contact=item["sender_contact"],
                channel=item.get("channel", "web_form"),
                enquiry_id=item["id"],
                force_fallback=True
            )
    db.commit()
