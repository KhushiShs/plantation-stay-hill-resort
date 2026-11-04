"""Integration test verifying structured event form submission, lane routing, and owner role assignment."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.db import get_db
from app.models import Enquiry


@pytest.fixture
def client(db_session: Session):
    def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, base_url="http://testserver") as c:
        yield c
    app.dependency_overrides.clear()


def test_structured_event_form_submission_lanes_and_owners(client, db_session):
    # 1. Destination Wedding
    # Retrieve CSRF and form token from GET /enquire
    r_get = client.get("/enquire")
    assert r_get.status_code == 200
    csrf = client.cookies.get("plantation_session")

    wedding_payload = {
        "csrf_token": client.app.dependency_overrides.get("csrf", "dummy"),  # Session-based
        "form_token": "token1",
        "sender_name": "Ananya Sharma",
        "sender_contact": "+91 98765 43210",
        "event_type": "Wedding",
        "preferred_venue": "Lawn",
        "budget_range": "₹15 Lakhs+",
        "preferred_check_in": "2027-02-14",
        "preferred_check_out": "2027-02-16",
        "preferred_guests": "250",
        "raw_message": "Looking for lawn venue for sister's wedding in February 2027, 250 guests, 2 nights.",
        "dpdp_consent": "yes"
    }

    # Simulate submission directly through form flow using session
    with client:
        res1 = client.get("/enquire")
        token1 = client.cookies.get("plantation_session")
        # Extract csrf_token and form_token from HTML
        import re
        csrf_val = re.search(r'name="csrf_token" value="([^"]+)"', res1.text).group(1)
        form_token_val = re.search(r'name="form_token" value="([^"]+)"', res1.text).group(1)
        wedding_payload["csrf_token"] = csrf_val
        wedding_payload["form_token"] = form_token_val

        r_post1 = client.post("/enquire", data=wedding_payload)
        assert r_post1.status_code == 200
        assert "Enquiry Received" in r_post1.text

        enq_wedding = db_session.query(Enquiry).filter(Enquiry.sender_name == "Ananya Sharma").order_by(Enquiry.created_at.desc()).first()
        assert enq_wedding is not None
        print(f"\n[Wedding] Category: {enq_wedding.category}, Owner Role: {enq_wedding.owner_role}")
        assert enq_wedding.category == "wedding"
        assert enq_wedding.owner_role == "sales"

        # 2. Corporate Offsite
        res2 = client.get("/enquire")
        csrf_val = re.search(r'name="csrf_token" value="([^"]+)"', res2.text).group(1)
        form_token_val = re.search(r'name="form_token" value="([^"]+)"', res2.text).group(1)
        offsite_payload = {
            "csrf_token": csrf_val,
            "form_token": form_token_val,
            "sender_name": "Vikram Malhotra",
            "sender_contact": "+91 91234 56789",
            "event_type": "Corporate Offsite",
            "preferred_venue": "Conference Hall",
            "budget_range": "₹7 - ₹15 Lakhs",
            "preferred_check_in": "2027-01-10",
            "preferred_check_out": "2027-01-12",
            "preferred_guests": "45",
            "raw_message": "Team of 45 wants a January corporate offsite with a conference hall.",
            "dpdp_consent": "yes"
        }
        r_post2 = client.post("/enquire", data=offsite_payload)
        assert r_post2.status_code == 200
        enq_offsite = db_session.query(Enquiry).filter(Enquiry.sender_name == "Vikram Malhotra").order_by(Enquiry.created_at.desc()).first()
        assert enq_offsite is not None
        print(f"[Offsite] Category: {enq_offsite.category}, Owner Role: {enq_offsite.owner_role}")
        assert enq_offsite.category == "offsite"
        assert enq_offsite.owner_role == "sales"

        # 3. Family Gathering (Room Stay / Family Villa enquiry)
        res3 = client.get("/enquire")
        csrf_val = re.search(r'name="csrf_token" value="([^"]+)"', res3.text).group(1)
        form_token_val = re.search(r'name="form_token" value="([^"]+)"', res3.text).group(1)
        family_payload = {
            "csrf_token": csrf_val,
            "form_token": form_token_val,
            "sender_name": "Rohan Mehra",
            "sender_contact": "+91 99887 76655",
            "event_type": "Family Gathering",
            "preferred_venue": "Villas / Rooms Only",
            "budget_range": "₹3 - ₹7 Lakhs",
            "preferred_check_in": "2026-12-24",
            "preferred_check_out": "2026-12-26",
            "preferred_guests": "8",
            "raw_message": "Looking for 2 villas for a family gathering and holiday over Christmas weekend.",
            "dpdp_consent": "yes"
        }
        r_post3 = client.post("/enquire", data=family_payload)
        assert r_post3.status_code == 200
        enq_family = db_session.query(Enquiry).filter(Enquiry.sender_name == "Rohan Mehra").order_by(Enquiry.created_at.desc()).first()
        assert enq_family is not None
        print(f"[Family Gathering] Category: {enq_family.category}, Owner Role: {enq_family.owner_role}")
        assert enq_family.category == "room"
        assert enq_family.owner_role == "reservations"
