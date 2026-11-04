import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db import get_db


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_public_pages_navigation_links_and_no_demo_text(client):
    """
    Ensure every public page links back to home,
    the home page contains links to /enquire and /booking-lookup,
    and no public template contains the word 'Demo'.
    """
    public_paths = [
        "/",
        "/rooms/estate-room",
        "/rooms/luxury-villa",
        "/enquire",
        "/booking-lookup",
    ]

    for path in public_paths:
        res = client.get(path)
        assert res.status_code == 200, f"Expected 200 for {path}, got {res.status_code}"
        # Every public page links to home
        assert 'href="/"' in res.text, f"Page {path} must contain link to home href='/'"
        # No public page leaks 'Demo' text
        assert "Demo" not in res.text, f"Page {path} should not contain 'Demo'"

    # Verify home page contains links to /enquire and /booking-lookup
    home_res = client.get("/")
    assert home_res.status_code == 200
    assert 'href="/enquire"' in home_res.text
    assert 'href="/booking-lookup"' in home_res.text
    assert 'href="/staff/login"' in home_res.text
