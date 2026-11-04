"""Tests for the interactive room-page tariff calendar and month navigation."""
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


def test_room_calendar_markup_and_month_navigation(client, db_session):
    """
    Tariff calendar requirements:
    1. Server renders each month as <section class="cal-month" data-month="YYYY-MM">
    2. Contains a Mon-Sun week grid (weekday headers, blank leading cells).
    3. Renders all months that have rate/allotment data (up to 180 days).
    4. Each day is a <button type="button" data-date="YYYY-MM-DD" data-price="...">
    5. Shows ONE month at a time (first month visible, subsequent months have 'hidden' attribute).
    6. Navigation header has [‹] / [›] buttons with aria-labels 'Previous month' and 'Next month'.
    7. Previous is disabled on the first month.
    8. Sold-out days are disabled + aria-disabled="true".
    9. Scarcity label 'N left' appears only when remaining <= 3.
    10. Script tag loads /static/js/calendar.js with defer.
    """
    today = date.today()
    # Mark a future date as sold-out
    sold_out_date = today + timedelta(days=15)
    alt = db_session.query(Allotment).filter_by(room_type_id="estate-room", date=sold_out_date).first()
    if alt:
        alt.sold = alt.total
    else:
        db_session.add(Allotment(room_type_id="estate-room", date=sold_out_date, total=10, sold=10, held=0))
    db_session.commit()

    res = client.get("/rooms/estate-room")
    assert res.status_code == 200

    # 1. Month sections
    assert '<section class="cal-month"' in res.text
    month_sections = re.findall(r'<section class="cal-month"[^>]*>', res.text)
    assert len(month_sections) >= 5, f"Expected at least 5 months for 180 days, found {len(month_sections)}"

    # 2. Exactly one visible month, rest hidden
    visible_months = [m for m in month_sections if "hidden" not in m]
    hidden_months = [m for m in month_sections if "hidden" in m]
    assert len(visible_months) == 1, f"Expected exactly 1 visible month, got {len(visible_months)}"
    assert len(hidden_months) >= 4

    # 3. Navigation buttons with aria-labels
    assert 'aria-label="Previous month"' in res.text
    assert 'aria-label="Next month"' in res.text
    assert 'id="cal-prev-btn"' in res.text
    assert 'id="cal-next-btn"' in res.text

    # Previous is disabled on first month
    assert re.search(r'id="cal-prev-btn"[^>]*disabled', res.text) is not None

    # 4. Weekday headers Mon-Sun
    for day_head in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
        assert f'<div class="cal-day-header">{day_head}</div>' in res.text

    # 5. Day buttons with data-date and data-price
    date_buttons = re.findall(r'<button[^>]+data-date="(\d{4}-\d{2}-\d{2})"[^>]*>', res.text)
    assert len(date_buttons) >= 150, f"Expected at least 150 day buttons across 180 days, found {len(date_buttons)}"
    assert 'data-price=' in res.text

    # 6. Sold-out days disabled + aria-disabled="true"
    target_iso = sold_out_date.isoformat()
    match = re.search(rf'<button[^>]+data-date="{target_iso}"[^>]*>', res.text)
    assert match, f"Button for {target_iso} not found"
    btn_html = match.group(0)
    assert 'disabled' in btn_html
    assert 'aria-disabled="true"' in btn_html
    assert 'sold-out' in btn_html

    # 7. Script tag loads /static/js/calendar.js with defer
    assert '<script src="/static/js/calendar.js" defer></script>' in res.text

    # 8. Helper text and clear dates
    assert "Select your check-in and check-out dates. Prices are per night, before GST." in res.text
    assert "Clear dates" in res.text


def test_room_page_regression_returns_200_with_calendar_grid_present(client, db_session):
    """Regression test ensuring page returns 200 with the calendar grid present."""
    res = client.get("/rooms/estate-room")
    assert res.status_code == 200
    assert 'id="tariff-calendar"' in res.text
    assert '<div class="calendar-grid">' in res.text
    assert 'data-date=' in res.text


def test_quote_endpoint_updates_with_calendar_selected_dates(client, db_session):
    """Selecting a range updates the quote with the right bill."""
    today = date.today()
    in_date = today + timedelta(days=10)
    out_date = today + timedelta(days=13)

    url = f"/rooms/estate-room/quote?check_in={in_date.isoformat()}&check_out={out_date.isoformat()}&rate_plan_id=room_only&num_guests=2"
    res = client.get(url)
    assert res.status_code == 200

    assert "PROVISIONAL TARIFF BILL (3 NIGHTS)" in res.text
    assert "Total Payable" in res.text
    assert "Continue to Guest Details" in res.text
    assert f"check_in={in_date.isoformat()}" in res.text
    assert f"check_out={out_date.isoformat()}" in res.text


def test_quote_endpoint_sold_out_shows_unavailable_and_nearest(client, db_session):
    """Selecting dates that include a sold-out night returns unavailable notice and alternatives."""
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
