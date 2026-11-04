"""Unit tests for staff demo passwords and environment-based seed validation."""
import os
import pytest
from scripts.seed import (
    get_staff_seed_passwords,
    DEFAULT_LOCAL_RESERVATIONS_PWD,
    DEFAULT_LOCAL_GM_PWD,
    DEFAULT_LOCAL_SALES_PWD
)


def test_development_mode_defaults_to_local_demo_passwords(monkeypatch):
    """In development mode, unset password env vars fall back to local demo passwords."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("DEMO_RESERVATIONS_PASSWORD", raising=False)
    monkeypatch.delenv("DEMO_GM_PASSWORD", raising=False)
    monkeypatch.delenv("DEMO_SALES_PASSWORD", raising=False)

    passwords = get_staff_seed_passwords()
    assert passwords["reservations"] == DEFAULT_LOCAL_RESERVATIONS_PWD
    assert passwords["gm"] == DEFAULT_LOCAL_GM_PWD
    assert passwords["sales"] == DEFAULT_LOCAL_SALES_PWD


def test_production_mode_aborts_when_passwords_are_missing(monkeypatch):
    """In production mode, seeding must abort if any password env var is unset."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("DEMO_RESERVATIONS_PASSWORD", raising=False)
    monkeypatch.delenv("DEMO_GM_PASSWORD", raising=False)
    monkeypatch.delenv("DEMO_SALES_PASSWORD", raising=False)

    with pytest.raises(ValueError) as exc_info:
        get_staff_seed_passwords()
    err = str(exc_info.value)
    assert "Production database seeding aborted" in err
    assert "DEMO_RESERVATIONS_PASSWORD" in err
    assert "DEMO_GM_PASSWORD" in err
    assert "DEMO_SALES_PASSWORD" in err


def test_production_mode_aborts_when_password_too_short(monkeypatch):
    """In production mode, seeding must abort if any password is shorter than 12 characters."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DEMO_RESERVATIONS_PASSWORD", "SecretValid123!")
    monkeypatch.setenv("DEMO_GM_PASSWORD", "short")  # < 12 chars
    monkeypatch.setenv("DEMO_SALES_PASSWORD", "SecretValid456!")

    with pytest.raises(ValueError) as exc_info:
        get_staff_seed_passwords()
    err = str(exc_info.value)
    assert "DEMO_GM_PASSWORD (missing or < 12 chars)" in err


def test_production_mode_succeeds_with_strong_explicit_passwords(monkeypatch):
    """In production mode, seeding succeeds when all passwords meet the >= 12 char requirement."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DEMO_RESERVATIONS_PASSWORD", "ResLongSecurePass2026!")
    monkeypatch.setenv("DEMO_GM_PASSWORD", "GMLongSecurePass2026!")
    monkeypatch.setenv("DEMO_SALES_PASSWORD", "SalesLongSecurePass2026!")

    passwords = get_staff_seed_passwords()
    assert passwords["reservations"] == "ResLongSecurePass2026!"
    assert passwords["gm"] == "GMLongSecurePass2026!"
    assert passwords["sales"] == "SalesLongSecurePass2026!"

