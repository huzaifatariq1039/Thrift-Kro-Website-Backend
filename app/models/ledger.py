import enum
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base
from app.core.money import MONEY_PRECISION, MONEY_SCALE


class LedgerAccountTypeEnum(str, enum.Enum):
    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    REVENUE = "REVENUE"
    EXPENSE = "EXPENSE"


class LedgerEntrySideEnum(str, enum.Enum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


class LedgerAccount(Base):
    __tablename__ = "ledger_accounts"
    __table_args__ = (
        UniqueConstraint("wallet_id", name="uq_ledger_accounts_wallet_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String(128), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    account_type = Column(Enum(LedgerAccountTypeEnum), nullable=False)
    wallet_id = Column(
        UUID(as_uuid=True),
        ForeignKey("wallets.id", ondelete="RESTRICT"),
        nullable=True,
    )
    currency = Column(String(3), nullable=False, default="PKR", server_default="PKR")
    is_system = Column(Boolean, nullable=False, default=False, server_default="false")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    wallet = relationship("Wallet", back_populates="ledger_account")
    entries = relationship("LedgerEntry", back_populates="account")


class LedgerJournal(Base):
    __tablename__ = "ledger_journals"
    __table_args__ = (
        Index("idx_ledger_journals_reference", "reference_type", "reference_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    operation_key = Column(String(255), unique=True, nullable=False)
    reference_type = Column(String(64), nullable=False)
    reference_id = Column(UUID(as_uuid=True), nullable=True)
    description = Column(String(500), nullable=True)
    posted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    entries = relationship("LedgerEntry", back_populates="journal")
    wallet_transaction = relationship(
        "Transaction",
        back_populates="ledger_journal",
        uselist=False,
    )


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    __table_args__ = (
        CheckConstraint("amount > 0.0", name="ledger_entries_positive_amount_check"),
        UniqueConstraint(
            "journal_id",
            "account_id",
            "side",
            name="uq_ledger_entries_journal_account_side",
        ),
        Index("idx_ledger_entries_account", "account_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    journal_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ledger_journals.id", ondelete="RESTRICT"),
        nullable=False,
    )
    account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ledger_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    side = Column(Enum(LedgerEntrySideEnum), nullable=False)
    amount = Column(Numeric(MONEY_PRECISION, MONEY_SCALE), nullable=False)
    currency = Column(String(3), nullable=False, default="PKR", server_default="PKR")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    journal = relationship("LedgerJournal", back_populates="entries")
    account = relationship("LedgerAccount", back_populates="entries")
