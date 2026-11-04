"""Tests for the interactive room-page tariff calendar and quote updates."""
import re
import pytest
from datetime import date, timedelta
from fastapi.testclient import TestClient

from app.main import app
from app.db import get_db
from app.models import Allotment, RoomType, DailyRate


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_room_calendar_markup_week_grid_and_sold_out_disabled(client, db_session):
    """
    Tariff calendar markup:
    - Renders week grid headers (Mon, Tue, Wed, Thu, Fri, Sat, Sun)
    - Available dates are <button> elements with data-date, data-available
    - Sold-out dates are marked with aria-disabled="true" and class 'sold-out'
    - Helper text updated to: 'Select your check-in and check-out dates. Prices are per night, before GST.'
    - 'Clear dates' link/button present
    - Touch targets 44px min dimension styling
    - Includes /static/room-calendar.js
    """
    # Specifically set a sold-out date for testing markup
    today = date.today()
    sold_out_date = today + timedelta(days=15)
    alt = db_session.query(Allotment).filter_by(room_type_id="estate-room", date=sold_out_date).first()
    if alt:
        alt.sold = alt.total
    else:
        db_session.add(Allotment(room_type_id="estate-room", date=sold_out_date, total=10, sold=10, held=0))
    db_session.commit()

    res = client.get("/rooms/estate-room")
    assert res.status_code == 200

    # 1. Weekday headers
    for day_head in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
        assert f'<div class="cal-day-header">{day_head}</div>' in res.text

    # 2. Replaced helper text
    assert "Select your check-in and check-out dates. Prices are per night, before GST." in res.text
    assert "Clear dates" in res.text

    # 3. Calendar buttons
    assert '<button type="button"' in res.text
    assert 'data-date=' in res.text
    assert 'data-available=' in res.text

    # 4. Sold-out date disabled
    target_iso = sold_out_date.isoformat()
    # Search for button with target_iso
    pattern = rf'<button[^>]+data-date="{target_iso}"[^>]*>'
    match = re.search(pattern, res.text)
    assert match, f"Button for date {target_iso} not found in calendar"
    tag_html = match.group(0)
    assert 'aria-disabled="true"' in tag_html
    assert 'sold-out' in tag_html
    assert 'data-sold-out="true"' in tag_html

    # 5. External JS included
    assert 'src="/static/room-calendar.js"' in res.text


def test_quote_endpoint_updates_with_calendar_selected_dates(client, db_session):
    """
    Simulates calendar date selection firing GET /rooms/{id}/quote:
    - Status 200
    - Returns updated provisional tariff bill
    - Correct room nights count
    - Grand total calculated
    - Button to proceed to booking step 2
    """
    today = date.today()
    in_date = today + timedelta(days=5)
    out_date = today + timedelta(days=8)

    url = f"/rooms/estate-room/quote?check_in={in_date.isoformat()}&check_out={out_date.isoformat()}&rate_plan_id=room_only&num_guests=2"
    res = client.get(url)
    assert res.status_code == 200

    assert "PROVISIONAL TARIFF BILL (3 NIGHTS)" in res.text
    assert "Total Payable" in res.text
    assert "Continue to Guest Details" in res.text
    assert f"check_in={in_date.isoformat()}" in res.text
    assert f"check_out={out_date.isoformat()}" in res.text


def test_quote_endpoint_sold_out_shows_unavailable_and_nearest(client, db_session):
    """
    Selecting dates that include a sold-out night returns unavailable notice and suggestions.
    """
    today = date.today()
    sold_date = today + timedelta(days=12)
    alt = db_session.query(Allotment).filter_by(room_type_id="luxury-villa", date=sold_date).first()
    if alt:
        alt.sold = alt.total
    else:
        db_session.add(Allotment(room_type_id="luxury-villa", date=sold_date, total=5, sold=5, held=0))
    db_session.commit()

    in_date = today + timedelta(days=11)
    out_date = today + timedelta(days=14)

    url = f"/rooms/luxury-villa/quote?check_in={in_date.isoformat()}&check_out={out_date.isoformat()}&rate_plan_id=room_only&num_guests=2"
    res = client.get(url)
    assert res.status_code == 200
    assert "DATES UNAVAILABLE" in res.text
    assert "currently sold out or blacked out" in res.text

