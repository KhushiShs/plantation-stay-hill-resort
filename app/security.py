"""Security, hashing and authentication helpers."""
import bcrypt
import hmac
import hashlib
from typing import Optional
from app.config import settings


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a bcrypt hash."""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def generate_hmac_signature(payload: str, secret: Optional[str] = None) -> str:
    """Generate SHA256 HMAC hex digest for webhook verification."""
    key = (secret or settings.webhook_secret).encode("utf-8")
    return hmac.new(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_hmac_signature(payload: str, signature: str, secret: Optional[str] = None) -> bool:
    """Constant-time verification of HMAC signature."""
    expected = generate_hmac_signature(payload, secret)
    return hmac.compare_digest(expected, signature)
