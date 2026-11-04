"""Application configuration module."""
import os
import secrets
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator

APP_NAME = "Plantation Stay"


def normalize_database_url(url: str) -> str:
    """
    Ensure the PostgreSQL connection URL uses the psycopg (psycopg3) SQLAlchemy driver.
    Converts postgresql:// and postgres:// to postgresql+psycopg://.
    """
    if not url:
        return url
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://") and not url.startswith("postgresql+"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = APP_NAME
    database_url: str = os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/plantation_test")
    
    # APP_ENV: 'development' or 'production' (default 'production')
    app_env: str = os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "production")).lower()
    
    # Secrets without hardcoded defaults
    secret_key: str = os.getenv("SECRET_KEY", "")
    webhook_secret: str = os.getenv("WEBHOOK_SECRET", "")
    
    # Allowed hosts for TrustedHostMiddleware
    # Comma-separated or default list
    allowed_hosts_raw: str = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver,*.onrender.com")

    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "")  # Empty uses fallback
    hold_minutes: int = int(os.getenv("HOLD_MINUTES", "10"))
    ai_confidence_threshold: float = float(os.getenv("AI_CONFIDENCE_THRESHOLD", "0.7"))

    @property
    def environment(self) -> str:
        """Alias for backwards compatibility with middleware checks."""
        return self.app_env

    @property
    def allowed_hosts(self) -> List[str]:
        """Parsed list of allowed hosts."""
        if not self.allowed_hosts_raw:
            return ["localhost", "127.0.0.1", "testserver", "*.onrender.com"]
        return [h.strip() for h in self.allowed_hosts_raw.split(",") if h.strip()]

    @model_validator(mode="after")
    def validate_and_normalize(self):
        # Normalize database_url to postgresql+psycopg://
        self.database_url = normalize_database_url(self.database_url)

        # Validate APP_ENV
        if self.app_env not in ("development", "production"):
            self.app_env = "production"

        # Production requirements: SECRET_KEY and WEBHOOK_SECRET must be set and non-empty
        if self.app_env == "production":
            missing = []
            if not self.secret_key or not self.secret_key.strip():
                missing.append("SECRET_KEY")
            if not self.webhook_secret or not self.webhook_secret.strip():
                missing.append("WEBHOOK_SECRET")
            if missing:
                raise ValueError(
                    f"Production startup error: missing required environment variable(s): {', '.join(missing)}. "
                    "SECRET_KEY and WEBHOOK_SECRET must be configured in production."
                )
        else:
            # Development: generate secure random values at startup if unset
            if not self.secret_key or not self.secret_key.strip():
                self.secret_key = secrets.token_hex(32)
            if not self.webhook_secret or not self.webhook_secret.strip():
                self.webhook_secret = secrets.token_hex(32)

        return self


settings = Settings()
