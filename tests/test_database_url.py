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

