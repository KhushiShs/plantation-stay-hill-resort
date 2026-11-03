"""Tests for configuration, APP_ENV, and secret enforcement in dev vs prod."""
import os
import pytest
from unittest.mock import patch
from pydantic import ValidationError

from app.config import Settings


def test_config_dev_generates_random_secrets_if_unset():
    """In development, unset SECRET_KEY and WEBHOOK_SECRET are randomly populated."""
    with patch.dict(os.environ, {
        "APP_ENV": "development",
        "SECRET_KEY": "",
        "WEBHOOK_SECRET": ""
    }, clear=False):
        cfg = Settings()
        assert cfg.app_env == "development"
        assert cfg.secret_key != ""
        assert len(cfg.secret_key) >= 32
        assert cfg.webhook_secret != ""
        assert len(cfg.webhook_secret) >= 32

        # Multiple inits generate different random tokens
        cfg2 = Settings()
        assert cfg2.secret_key != cfg.secret_key


def test_config_dev_preserves_explicit_secrets():
    """In development, explicitly provided secrets are preserved."""
    with patch.dict(os.environ, {
        "APP_ENV": "development",
        "SECRET_KEY": "custom-dev-secret",
        "WEBHOOK_SECRET": "custom-dev-webhook"
    }, clear=False):
        cfg = Settings()
        assert cfg.secret_key == "custom-dev-secret"
        assert cfg.webhook_secret == "custom-dev-webhook"


def test_config_prod_raises_if_secret_key_missing():
    """In production, missing SECRET_KEY raises ValidationError."""
    with patch.dict(os.environ, {
        "APP_ENV": "production",
        "SECRET_KEY": "",
        "WEBHOOK_SECRET": "some-webhook-secret"
    }, clear=False):
        with pytest.raises(ValidationError) as excinfo:
            Settings()
        assert "SECRET_KEY" in str(excinfo.value)


def test_config_prod_raises_if_webhook_secret_missing():
    """In production, missing WEBHOOK_SECRET raises ValidationError."""
    with patch.dict(os.environ, {
        "APP_ENV": "production",
        "SECRET_KEY": "some-prod-secret",
        "WEBHOOK_SECRET": ""
    }, clear=False):
        with pytest.raises(ValidationError) as excinfo:
            Settings()
        assert "WEBHOOK_SECRET" in str(excinfo.value)


def test_config_prod_succeeds_when_both_secrets_present():
    """In production, when both secrets are provided, Settings initializes cleanly."""
    with patch.dict(os.environ, {
        "APP_ENV": "production",
        "SECRET_KEY": "prod-secret-12345",
        "WEBHOOK_SECRET": "prod-webhook-67890"
    }, clear=False):
        cfg = Settings()
        assert cfg.app_env == "production"
        assert cfg.secret_key == "prod-secret-12345"
        assert cfg.webhook_secret == "prod-webhook-67890"


def test_config_defaults_to_production():
    """If APP_ENV is unset, default is production, enforcing secrets."""
    with patch.dict(os.environ, {
        "APP_ENV": "",
        "ENVIRONMENT": "",
        "SECRET_KEY": "",
        "WEBHOOK_SECRET": ""
    }, clear=False):
        with pytest.raises(ValidationError) as excinfo:
            Settings()
        assert "Production startup error" in str(excinfo.value)
