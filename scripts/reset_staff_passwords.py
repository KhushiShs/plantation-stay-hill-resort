"""Staff password reset and upsert script.

Updates the passwords of the three core staff users (reservations, gm, sales)
using DEMO_RESERVATIONS_PASSWORD, DEMO_GM_PASSWORD, and DEMO_SALES_PASSWORD
from environment or .env. Can be run safely in both development and production.
"""
import os
import sys
import logging
from dotenv import load_dotenv

load_dotenv()

from app.db import engine, SessionLocal
from scripts.seed import upsert_staff_users, get_staff_seed_passwords

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("reset_staff_passwords")


def reset_staff_passwords() -> None:
    from app.config import settings
    db_name = settings.database_url.rsplit("/", 1)[-1].split("?")[0]
    logger.info(f"Connected to database: {db_name}")
    logger.info("Resetting staff passwords from environment...")
    passwords = get_staff_seed_passwords()
    with SessionLocal() as session:
        upsert_staff_users(session, passwords)
        session.commit()
    logger.info("Staff passwords reset successfully!")


if __name__ == "__main__":
    try:
        reset_staff_passwords()
    except Exception as exc:
        logger.error(f"Error resetting staff passwords: {exc}")
        sys.exit(1)

