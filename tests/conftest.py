"""Fixtures and test setup. Aborts if DB name does not end in _test."""
import os

# Ensure tests run under development mode so https_only is False for test client sessions
os.environ.setdefault("APP_ENV", "development")
# Ensure tests use default local demo credentials when seeding
os.environ.setdefault("DEMO_RESERVATIONS_PASSWORD", "ReservationsDemo2026!")
os.environ.setdefault("DEMO_GM_PASSWORD", "GMDemo2026!")
os.environ.setdefault("DEMO_SALES_PASSWORD", "SalesDemo2026!")

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from app.config import settings
from app.db import Base
from scripts.seed import seed_database
from app.security import reset_rate_limits

# Safety requirement: The test setup must abort unless the DB name ends in _test.
db_name = settings.database_url.rsplit("/", 1)[-1].split("?")[0]
if not db_name.endswith("_test"):
    raise RuntimeError(
        f"CRITICAL SAFETY VIOLATION: Test database name must end with '_test', got '{db_name}'. Aborting tests."
    )

test_engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=40,
    max_overflow=20
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Create all tables once per test session."""
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(autouse=True)
def reset_db_and_rate_limits_per_test():
    """
    Ensure every test is completely independent:
    1. Truncate all tables and reseed with baseline seed data.
    2. Reset in-memory rate limits.
    """
    reset_rate_limits()
    
    # Truncate all tables with CASCADE
    table_names = [table.name for table in Base.metadata.sorted_tables]
    if table_names:
        truncate_sql = f"TRUNCATE TABLE {', '.join(table_names)} RESTART IDENTITY CASCADE;"
        with test_engine.connect() as conn:
            conn.execute(text(truncate_sql))
            conn.commit()

    with TestSessionLocal() as session:
        seed_database(session)

    yield

    reset_rate_limits()


@pytest.fixture
def db_session():
    """Yield a database session for each test."""
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def session_factory():
    """Return the session factory for multi-threaded tests."""
    return TestSessionLocal
