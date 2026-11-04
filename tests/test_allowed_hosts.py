"""Specific test verifying ALLOWED_HOSTS configuration and onrender.com host validation."""
from starlette.testclient import TestClient
from starlette.applications import Starlette
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from app.config import Settings


def make_test_app(allowed_hosts):
    async def homepage(request):
        return PlainTextResponse("OK")
    app = Starlette(routes=[Route("/", homepage)])
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
    return app


def test_allowed_hosts_env_parsing_and_resolution():
    # 1. Custom ALLOWED_HOSTS comma-separated string
    custom_settings = Settings(
        allowed_hosts_raw="localhost,127.0.0.1,plantation-stay-hill-resort.onrender.com"
    )
    hosts = custom_settings.allowed_hosts
    assert "localhost" in hosts
    assert "127.0.0.1" in hosts
    assert "plantation-stay-hill-resort.onrender.com" in hosts

    test_app = make_test_app(hosts)

    # 2. Listed host works (returns 200)
    c1 = TestClient(test_app, base_url="https://plantation-stay-hill-resort.onrender.com")
    res1 = c1.get("/")
    assert res1.status_code == 200
    assert res1.text == "OK"

    # Localhost works
    c_local = TestClient(test_app, base_url="http://localhost")
    assert c_local.get("/").status_code == 200

    # 3. Disallowed host (when not listed) returns 400 Invalid host
    c2 = TestClient(test_app, base_url="https://random-unlisted-domain.com")
    res2 = c2.get("/")
    assert res2.status_code == 400

    # Disallowed if onrender.com is omitted
    strict_settings = Settings(allowed_hosts_raw="localhost,127.0.0.1")
    strict_app = make_test_app(strict_settings.allowed_hosts)
    c3 = TestClient(strict_app, base_url="https://plantation-stay-hill-resort.onrender.com")
    res3 = c3.get("/")
    assert res3.status_code == 400

