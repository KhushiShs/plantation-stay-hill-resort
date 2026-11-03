"""Fixtures and test setup. Aborts if DB name does not end in _test."""
import pytest
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.config import settings
from app.db import Base
from scripts.seed import seed_database

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
    """Create all tables and seed baseline data once per test session."""
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    with TestSessionLocal() as session:
        seed_database(session)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db_session():
    """Yield a database session for each test, rolling back on completion."""
    connection = test_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def session_factory():
    """Return the session factory for multi-threaded tests."""
    return TestSessionLocal
