"""Tests for security headers, body size limit, health check, trusted hosts, and static caching."""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings


@pytest.fixture
def client():
    # Use TestClient with allowed Host header
    return TestClient(app, base_url="http://testserver")


def test_health_check_returns_200_and_status_ok(client):
    """/health runs SELECT 1 and returns status ok."""
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_trusted_host_middleware_allows_valid_host():
    """Allowed hosts return normal status."""
    c = TestClient(app, base_url="http://localhost")
    res = c.get("/health")
    assert res.status_code == 200

    c2 = TestClient(app, base_url="http://127.0.0.1")
    res2 = c2.get("/health")
    assert res2.status_code == 200


def test_trusted_host_middleware_blocks_disallowed_host():
    """Disallowed Host headers receive 400 Invalid host."""
    c = TestClient(app, base_url="http://evil-attacker.com")
    res = c.get("/health")
    assert res.status_code == 400


def test_security_headers_present_on_responses(client):
    """Verify security headers: X-Content-Type-Options, X-Frame-Options, Referrer-Policy, CSP."""
    res = client.get("/health")
    assert res.status_code == 200
    assert res.headers.get("x-content-type-options") == "nosniff"
    assert res.headers.get("x-frame-options") == "DENY"
    assert res.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
    csp = res.headers.get("content-security-policy", "")
    assert "script-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp


def test_body_size_limit_blocks_payload_over_2mb(client):
    """BodySizeLimitMiddleware rejects requests larger than 2 MB with 413."""
    oversized_data = b"x" * (2 * 1024 * 1024 + 100)
    res = client.post("/enquire", content=oversized_data, headers={"Content-Type": "application/octet-stream"})
    assert res.status_code == 413


def test_static_caching_headers(client):
    """Static assets return cache-control headers."""
    res = client.get("/static/tokens.css")
    assert res.status_code == 200
    assert "public" in res.headers.get("cache-control", "")
    assert "max-age=" in res.headers.get("cache-control", "")


def test_docs_and_openapi_disabled_in_production(client):
    """In production mode, docs and openapi are disabled (404)."""
    if settings.app_env == "production":
        assert client.get("/docs").status_code == 404
        assert client.get("/redoc").status_code == 404
        assert client.get("/openapi.json").status_code == 404

