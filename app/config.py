"""Application configuration module."""
import os
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_NAME = "Plantation Stay"

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = APP_NAME
    database_url: str = os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/plantation_test")
    secret_key: str = os.getenv("SECRET_KEY", "dev-secret-key-change-in-prod-1234567890")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "")  # No hardcoded default model; empty uses fallback
    webhook_secret: str = os.getenv("WEBHOOK_SECRET", "mock-webhook-secret-key")
    environment: str = os.getenv("ENVIRONMENT", "development")
    hold_minutes: int = int(os.getenv("HOLD_MINUTES", "10"))
    ai_confidence_threshold: float = float(os.getenv("AI_CONFIDENCE_THRESHOLD", "0.7"))

settings = Settings()
