"""Integration test verifying reservations CSV export and formula injection escaping."""
import csv
import io
import re
from datetime import date
from starlette.testclient import TestClient

from app.main import app
from app.db import get_db
from app.models import Booking, User
from app.security import hash_password


def test_reservations_csv_export_and_formula_escaping(db_session):
    # Ensure a reservations user exists
    res_user = db_session.query(User).filter_by(email="res_tester@plantationstay.com").first()
    if not res_user:
        res_user = User(
            email="res_tester@plantationstay.com",
            hashed_password=hash_password("ResSecret123!"),
            full_name="Reservations Staff Tester",
            role="reservations",
            is_active=True
        )
        db_session.add(res_user)
        db_session.commit()

    # Create a test booking with an injection prefix in guest_name
    test_d = date(2026, 12, 1)
    b = Booking(
        reference="BK-CSVTEST",
        room_type_id="estate-room",
        rate_plan_id="room_only",
        check_in=test_d,
        check_out=date(2026, 12, 3),
        num_guests=2,
        num_rooms=1,
        status="confirmed",
        guest_name="=cmd|' /C calc'!A0",  # Spreadsheet formula injection attempt
        guest_email="testguest@example.com",
        guest_phone="+91 98765 43210",
        dpdp_consent=True,
        room_total_paise=1400000,
        discount_paise=0,
        gst_paise=70000,
        grand_total_paise=1470000
    )
    db_session.add(b)
    db_session.commit()

    def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app, base_url="http://testserver") as client:
        # 1. Fetch staff login page to obtain CSRF token
        login_page = client.get("/staff/login")
        assert login_page.status_code == 200
        csrf_token = re.search(r'name="csrf_token" value="([^"]+)"', login_page.text).group(1)

        # 2. Authenticate as reservations staff
        login_res = client.post("/staff/login", data={
            "email": "res_tester@plantationstay.com",
            "password": "ResSecret123!",
            "csrf_token": csrf_token
        }, follow_redirects=False)
        assert login_res.status_code == 303

        # 3. Request CSV export for test_d
        res = client.get(f"/staff/bookings/export-csv?date_str={test_d.isoformat()}")
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/csv")

        csv_text = res.text
        lines = [line for line in csv_text.splitlines() if line.strip()]
        header = lines[0]
        data_row = lines[1]

        print(f"\nHeader Row: {header}")
        print(f"Data Row: {data_row}")

        # Assertions
        assert header == "Reference,Guest Name,Guest Email,Guest Phone,Room Type,Rate Plan,Check In,Check Out,Guests,Grand Total (Paise),Status,Created At"
        # Formula escaping check: '=' must be escaped with single quote "'"
        reader = csv.reader(io.StringIO(csv_text))
        rows = list(reader)
        row_dict = dict(zip(rows[0], rows[1]))
        assert row_dict["Reference"] == "BK-CSVTEST"
        assert row_dict["Guest Name"] == "'=cmd|' /C calc'!A0", f"Expected escaped formula, got: {row_dict['Guest Name']}"
        assert row_dict["Guest Name"].startswith("'=")
