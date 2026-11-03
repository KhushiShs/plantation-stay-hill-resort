"""Application configuration module."""
import os
import secrets
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator

APP_NAME = "Plantation Stay"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = APP_NAME
    database_url: str = os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/plantation_test")
    
    # APP_ENV: 'development' or 'production' (default 'production')
    app_env: str = os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "production")).lower()
    
    # Secrets without hardcoded defaults
    secret_key: str = os.getenv("SECRET_KEY", "")
    webhook_secret: str = os.getenv("WEBHOOK_SECRET", "")
    
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "")  # Empty uses fallback
    hold_minutes: int = int(os.getenv("HOLD_MINUTES", "10"))
    ai_confidence_threshold: float = float(os.getenv("AI_CONFIDENCE_THRESHOLD", "0.7"))

    @property
    def environment(self) -> str:
        """Alias for backwards compatibility with middleware checks."""
        return self.app_env

    @model_validator(mode="after")
    def validate_secrets_and_env(self):
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
