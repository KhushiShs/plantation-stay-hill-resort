"""Unit tests for staff demo passwords and environment-based seed validation."""
import os
import pytest
from scripts.seed import get_staff_seed_passwords


def test_seeding_aborts_when_passwords_are_missing_in_any_environment(monkeypatch):
    """In all environments (including dev/prod), seeding must abort if any password env var is unset."""
    for env in ["development", "production", "test"]:
        monkeypatch.setenv("APP_ENV", env)
        monkeypatch.delenv("DEMO_RESERVATIONS_PASSWORD", raising=False)
        monkeypatch.delenv("DEMO_GM_PASSWORD", raising=False)
        monkeypatch.delenv("DEMO_SALES_PASSWORD", raising=False)

        with pytest.raises(ValueError) as exc_info:
            get_staff_seed_passwords()
        err = str(exc_info.value)
        assert "Database seeding aborted" in err
        assert "DEMO_RESERVATIONS_PASSWORD" in err
        assert "DEMO_GM_PASSWORD" in err
        assert "DEMO_SALES_PASSWORD" in err


def test_seeding_aborts_when_password_too_short(monkeypatch):
    """Seeding must abort in any environment if any password is shorter than 12 characters."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DEMO_RESERVATIONS_PASSWORD", "ValidLengthResPassword123!")
    monkeypatch.setenv("DEMO_GM_PASSWORD", "short_pwd")  # 9 chars (< 12)
    monkeypatch.setenv("DEMO_SALES_PASSWORD", "ValidLengthSalesPassword123!")

    with pytest.raises(ValueError) as exc_info:
        get_staff_seed_passwords()
    err = str(exc_info.value)
    assert "Database seeding aborted" in err
    assert "DEMO_GM_PASSWORD (missing or < 12 chars)" in err


def test_seeding_succeeds_when_all_passwords_valid(monkeypatch):
    """When all environment variables are valid (>= 12 characters), passwords are resolved cleanly."""
    monkeypatch.setenv("DEMO_RESERVATIONS_PASSWORD", "SuperSecureResPassword123!")
    monkeypatch.setenv("DEMO_GM_PASSWORD", "SuperSecureGMPassword123!")
    monkeypatch.setenv("DEMO_SALES_PASSWORD", "SuperSecureSalesPassword123!")

    passwords = get_staff_seed_passwords()
    assert passwords["reservations"] == "SuperSecureResPassword123!"
    assert passwords["gm"] == "SuperSecureGMPassword123!"
    assert passwords["sales"] == "SuperSecureSalesPassword123!"


def test_staff_password_upsert_and_login_flow(monkeypatch, db_session):
    """
    Test seed with password A, seed again with password B:
    staff login works with B and fails with A.
    """
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db import get_db
    from scripts.seed import seed_database
    import re

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    pwd_a = "InitialSecretPassword123!"
    pwd_b = "UpdatedSecretPassword456!"

    # 1. Seed with Password A
    monkeypatch.setenv("DEMO_RESERVATIONS_PASSWORD", pwd_a)
    monkeypatch.setenv("DEMO_GM_PASSWORD", pwd_a)
    monkeypatch.setenv("DEMO_SALES_PASSWORD", pwd_a)
    seed_database(db_session, allow_test=True)
    db_session.commit()

    with TestClient(app) as client:
        # Verify login works with password A
        res_page = client.get("/staff/login")
        csrf = re.search(r'name="csrf_token"\s+value="([^"]+)"', res_page.text).group(1)
        r_login_a = client.post("/staff/login", data={
            "email": "reservations@plantationstay.local",
            "password": pwd_a,
            "csrf_token": csrf
        }, follow_redirects=False)
        assert r_login_a.status_code == 303
        assert "/staff/calendar" in r_login_a.headers["location"]

        # 2. Seed again with Password B (UPSERT)
        monkeypatch.setenv("DEMO_RESERVATIONS_PASSWORD", pwd_b)
        monkeypatch.setenv("DEMO_GM_PASSWORD", pwd_b)
        monkeypatch.setenv("DEMO_SALES_PASSWORD", pwd_b)
        seed_database(db_session, allow_test=True)
        db_session.commit()

        # Login with old Password A must now fail
        res_page2 = client.get("/staff/login")
        csrf2 = re.search(r'name="csrf_token"\s+value="([^"]+)"', res_page2.text).group(1)
        r_login_old = client.post("/staff/login", data={
            "email": "reservations@plantationstay.local",
            "password": pwd_a,
            "csrf_token": csrf2
        }, follow_redirects=False)
        assert r_login_old.status_code == 401
        assert "Invalid email or password" in r_login_old.text

        # Login with new Password B must now succeed
        res_page3 = client.get("/staff/login")
        csrf3 = re.search(r'name="csrf_token"\s+value="([^"]+)"', res_page3.text).group(1)
        r_login_new = client.post("/staff/login", data={
            "email": "reservations@plantationstay.local",
            "password": pwd_b,
            "csrf_token": csrf3
        }, follow_redirects=False)
        assert r_login_new.status_code == 303
        assert "/staff/calendar" in r_login_new.headers["location"]

    app.dependency_overrides.clear()

