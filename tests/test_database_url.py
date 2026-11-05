"""Tests for database URL normalization and settings."""
from app.config import normalize_database_url


def test_normalize_database_url_converts_postgresql_prefix():
    raw_neon = "postgresql://user:pass@ep-cool-lake-1234.us-east-2.aws.neon.tech/neondb?sslmode=require"
    expected = "postgresql+psycopg://user:pass@ep-cool-lake-1234.us-east-2.aws.neon.tech/neondb?sslmode=require"
    assert normalize_database_url(raw_neon) == expected


def test_normalize_database_url_converts_postgres_shorthand():
    raw_legacy = "postgres://user:pass@localhost:5432/db"
    expected = "postgresql+psycopg://user:pass@localhost:5432/db"
    assert normalize_database_url(raw_legacy) == expected


def test_normalize_database_url_preserves_already_driver_prefixed_url():
    already_correct = "postgresql+psycopg://user:pass@localhost:5432/db"
    assert normalize_database_url(already_correct) == already_correct


def test_test_session_database_name_must_end_in_test():
    from app.config import settings
    db_name = settings.database_url.rsplit("/", 1)[-1].split("?")[0]
    assert db_name.endswith("_test"), f"Test session database '{db_name}' must end in _test"


def test_settings_database_url_outside_pytest_must_not_end_in_test(monkeypatch):
    from app.config import Settings
    # Simulate running outside pytest with default environment
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    s = Settings()
    db_name = s.database_url.rsplit("/", 1)[-1].split("?")[0]
    assert not db_name.endswith("_test"), (
        f"Default app database '{db_name}' outside pytest must not end in _test"
    )


