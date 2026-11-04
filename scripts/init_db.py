"""Database initialisation script.

Creates all database tables and seeds reference/allotment data if empty.
Idempotent and intended to be run as a one-off setup command, NEVER on application startup.
"""
import sys
import logging
from sqlalchemy import text
from app.db import engine, SessionLocal, Base
import app.models  # Ensures all model classes are registered on Base.metadata
from scripts.seed import seed_database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("init_db")


def init_db():
    logger.info("Verifying database schema...")
    Base.metadata.create_all(bind=engine)
    logger.info("Schema verified.")

    db = SessionLocal()
    try:
        # Check if users or room_types table has records
        room_types_count = db.execute(text("SELECT COUNT(*) FROM room_types")).scalar()
        if room_types_count == 0:
            logger.info("Database is empty. Seeding initial estate reference data...")
            seed_database(db)
            logger.info("Seeding completed.")
        else:
            logger.info(f"Database already populated ({room_types_count} room types). Skipping seed.")
    except Exception as e:
        logger.error(f"Error during init_db: {e}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    init_db()
