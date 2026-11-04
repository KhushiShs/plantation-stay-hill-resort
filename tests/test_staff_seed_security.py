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
