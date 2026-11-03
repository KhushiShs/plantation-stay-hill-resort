"""Security, hashing, HMAC signatures, CSRF protection, and rate limiting."""
import bcrypt
import hmac
import hashlib
import os
import secrets
import time
from typing import Optional, Dict, Tuple
from fastapi import Request, HTTPException, status, Depends
from sqlalchemy.orm import Session
from app.config import settings
from app.db import get_db
from app.models import User

# In-memory rate limiting dictionary: (ip, route) -> list of timestamp floats
# Note: Recorded in ASSUMPTIONS.md as in-memory and resets on server restart/deploy.
_RATE_LIMIT_STORE: Dict[Tuple[str, str], list[float]] = {}


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a bcrypt hash."""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def generate_booking_reference() -> str:
    """Generate an unguessable booking reference code using secrets."""
    # Format: BK- followed by 8 URL-safe alphanumeric characters
    token = secrets.token_urlsafe(6).replace("-", "").replace("_", "").upper()[:8]
    return f"BK-{token}"


def generate_csrf_token() -> str:
    """Generate a secure random CSRF token."""
    return secrets.token_hex(32)


def generate_hmac_signature(payload: str, secret: Optional[str] = None) -> str:
    """Generate SHA256 HMAC hex digest for webhook verification."""
    key = (secret or settings.webhook_secret).encode("utf-8")
    return hmac.new(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_hmac_signature(payload: str, signature: str, secret: Optional[str] = None) -> bool:
    """Constant-time verification of HMAC signature."""
    if not signature:
        return False
    expected = generate_hmac_signature(payload, secret)
    return hmac.compare_digest(expected, signature)


def reset_rate_limits() -> None:
    """Clear all in-memory rate limiting counters."""
    _RATE_LIMIT_STORE.clear()


def check_rate_limit(request: Request, route_key: str, max_requests: int = 10, window_seconds: int = 60) -> None:
    """
    In-memory rate limiter keyed on client IP and route_key.
    Raises HTTP 429 Too Many Requests if threshold is exceeded.
    """
    client_ip = request.client.host if request.client else "127.0.0.1"
    key = (client_ip, route_key)
    now = time.time()
    
    timestamps = _RATE_LIMIT_STORE.get(key, [])
    # Filter timestamps within window
    timestamps = [t for t in timestamps if now - t < window_seconds]
    
    if len(timestamps) >= max_requests:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please slow down and try again shortly."
        )
    
    timestamps.append(now)
    _RATE_LIMIT_STORE[key] = timestamps


def get_current_staff_user(request: Request, db: Session = Depends(get_db)) -> User:
    """
    Dependency: Authenticates staff user from session.
    Redirects unauthenticated staff to /staff/login?next=... (or 403 on API).
    """
    user_id = request.session.get("staff_user_id")
    if not user_id:
        # Check if browser GET request or API request
        next_url = request.url.path
        if request.method == "GET" and not next_url.startswith("/api/"):
            raise HTTPException(
                status_code=status.HTTP_303_SEE_OTHER,
                headers={"Location": f"/staff/login?next={next_url}"}
            )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Authentication required")
        
    user = db.get(User, user_id)
    if not user or not user.is_active:
        request.session.clear()
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/staff/login"}
        )
    return user


def require_role(*allowed_roles: str):
    """Dependency factory checking staff role authorization."""
    def role_checker(user: User = Depends(get_current_staff_user)) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access forbidden: role '{user.role}' lacks sufficient privileges."
            )
        return user
    return role_checker
