"""FastAPI Application entry point."""
import logging
from typing import Callable
from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy import text

from app.config import settings
from app.db import SessionLocal
from app.routes.guest import router as guest_router, templates
from app.routes.staff import router as staff_router
from app.routes.enquire import router as enquire_router

logger = logging.getLogger("app.main")

# Disable /docs, /redoc, /openapi.json in production
docs_kwargs = {}
if settings.app_env == "production":
    docs_kwargs = {
        "docs_url": None,
        "redoc_url": None,
        "openapi_url": None
    }

app = FastAPI(title=settings.app_name, **docs_kwargs)


# -------------------------------------------------------------
# Security & Request Validation Middleware
# -------------------------------------------------------------

class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Enforce a strict 2 MB body size limit on incoming requests."""
    def __init__(self, app, max_bytes: int = 2 * 1024 * 1024):
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next: Callable):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.max_bytes:
            return Response("Request body too large. Maximum size is 2 MB.", status_code=413)
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Apply security headers across all responses:
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY
    - Referrer-Policy: strict-origin-when-cross-origin
    - Content-Security-Policy: script-src 'self'
    - HSTS: Strict-Transport-Security (production only)
    """
    async def dispatch(self, request: Request, call_next: Callable):
        response: Response = await call_next(request)
        
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # CSP: strict script-src 'self', allows images, inline styles for minimal tokens
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self';"
        )

        if settings.app_env == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"

        return response


class CacheControlStaticFiles(StaticFiles):
    """Static file handler serving assets with optimal cache-control headers."""
    async def get_response(self, path: str, scope) -> Response:
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            # 7 days caching (604800s) for unversioned static assets
            response.headers["Cache-Control"] = "public, max-age=604800, stale-while-revalidate=86400"
        return response


# Middleware stack (applied in reverse execution order)
# 1. GZip Compression
app.add_middleware(GZipMiddleware, minimum_size=1000)

# 2. Security Headers
app.add_middleware(SecurityHeadersMiddleware)

# 3. Request body size limit (2 MB)
app.add_middleware(BodySizeLimitMiddleware, max_bytes=2 * 1024 * 1024)

# 4. Session middleware for signed cookies and CSRF
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie="plantation_session",
    max_age=3600 * 24,
    same_site="lax",
    https_only=(settings.app_env == "production")
)

# 5. Trusted host middleware
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.allowed_hosts
)

# Static files with Cache-Control
app.mount("/static", CacheControlStaticFiles(directory="app/static"), name="static")


# -------------------------------------------------------------
# System & Health Check Endpoints
# -------------------------------------------------------------

@app.get("/health", response_class=JSONResponse)
def health_check():
    """
    Health check running 'SELECT 1' against the PostgreSQL database.
    Returns only {'status': 'ok'} with 200 OK.
    """
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Health check failed database ping: {e}", exc_info=True)
        return JSONResponse(status_code=503, content={"status": "error"})
    finally:
        db.close()


# Include Routers
app.include_router(guest_router)
app.include_router(staff_router)
app.include_router(enquire_router)


# -------------------------------------------------------------
# Global Error Handlers
# -------------------------------------------------------------

@app.exception_handler(404)
async def custom_404_handler(request: Request, exc):
    return templates.TemplateResponse(request, "errors/404.html", {
        "app_name": settings.app_name
    }, status_code=404)


@app.exception_handler(500)
async def custom_500_handler(request: Request, exc: Exception):
    logger.error(
        "Internal server error (500) at %s %s: %s",
        request.method,
        request.url.path,
        exc,
        exc_info=True
    )
    return templates.TemplateResponse(request, "errors/500.html", {
        "app_name": settings.app_name
    }, status_code=500)
