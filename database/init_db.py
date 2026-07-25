"""
Database Initialization Manager for Thrift Kro Backend.

Verifies PostgreSQL database connection with connection retries, creates tables via 
SQLAlchemy Base metadata, and invokes the database seeder script.
"""

import sys
import os
import time
import logging

# Add root directory to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.core.config import settings
from app.core.database import Base, engine
from app.models import *  # Ensure all SQLAlchemy models are registered
from database.seed_data import seed_database

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def wait_for_db(max_retries: int = 10, delay_seconds: int = 2):
    """Attempt database connection with backoff retry logic."""
    logger.info(f"Connecting to database: {settings.SQLALCHEMY_DATABASE_URI}")
    
    for attempt in range(1, max_retries + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1;"))
                logger.info("✅ PostgreSQL connection test successful.")
                return True
        except Exception as e:
            logger.warning(f"⚠️ Attempt {attempt}/{max_retries}: PostgreSQL not ready yet ({e}). Retrying in {delay_seconds}s...")
            time.sleep(delay_seconds)
            
    logger.error("❌ Failed to connect to PostgreSQL after multiple retries.")
    return False


def init_database():
    """Create all schema tables and seed default data."""
    if not wait_for_db():
        sys.exit(1)

    try:
        # Create all tables if they don't exist
        logger.info("🔨 Creating database tables via SQLAlchemy metadata...")
        Base.metadata.create_all(bind=engine)
        logger.info("✅ Database schema creation completed successfully.")

        # Seed initial data
        seed_database()

    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    init_database()
