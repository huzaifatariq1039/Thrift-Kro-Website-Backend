from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from .config import settings
from .runtime_capacity import load_runtime_capacity

runtime_capacity = load_runtime_capacity()

engine = create_engine(
    settings.SQLALCHEMY_DATABASE_URI,
    pool_pre_ping=True,
    pool_size=runtime_capacity.database_pool_size,
    max_overflow=runtime_capacity.database_max_overflow,
    pool_timeout=runtime_capacity.database_pool_timeout_seconds,
    pool_recycle=runtime_capacity.database_pool_recycle_seconds,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
