from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from .config import settings

# Optimized SQLAlchemy Engine for High-Concurrency API Workloads
engine = create_engine(
    settings.SQLALCHEMY_DATABASE_URI,
    pool_pre_ping=True,      # Tests connection liveness before reuse to prevent stale connection errors
    pool_size=15,             # Base pool of persistent database connections
    max_overflow=25,          # Maximum temporary connections allowed under burst load
    pool_recycle=1800,        # Recycles connections every 30 mins to avoid firewall/DB timeout drops
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

