"""Immutable double-entry ledger application boundary for wallet operations."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable
from uuid import UUID

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.core.money import ZERO_MONEY, money
from app.models.ledger import (
    LedgerAccount,
    LedgerAccountTypeEnum,
    LedgerEntry,
    LedgerEntrySideEnum,
    LedgerJournal,
)
from app.models.user import Transaction, TransactionTypeEnum, Wallet


ESCROW_ACCOUNT_CODE = "SYSTEM:ESCROW"
PLATFORM_REVENUE_ACCOUNT_CODE = "SYSTEM:PLATFORM_REVENUE"
LEGACY_CLEARING_ACCOUNT_CODE = "SYSTEM:LEGACY_CLEARING"


class LedgerIntegrityError(RuntimeError):
    """Raised when a wallet or proposed journal cannot reconcile."""


def _system_account(db: Session, code: str) -> LedgerAccount:
    account = db.query(LedgerAccount).filter(LedgerAccount.code == code).first()
    if account is None:
        raise LedgerIntegrityError(f"Required ledger account {code} is missing")
    return account


def _wallet_account(db: Session, wallet: Wallet) -> LedgerAccount:
    account = (
        db.query(LedgerAccount)
        .filter(LedgerAccount.wallet_id == wallet.id)
        .first()
    )
    if account is not None:
        return account

    account = LedgerAccount(
        code=f"WALLET:{wallet.id}",
        name=f"Wallet liability {wallet.id}",
        account_type=LedgerAccountTypeEnum.LIABILITY,
        wallet_id=wallet.id,
        currency=wallet.currency,
        is_system=False,
    )
    db.add(account)
    db.flush()
    return account


def _credit_balance(db: Session, account_id: UUID) -> Decimal:
    signed_amount = case(
        (LedgerEntry.side == LedgerEntrySideEnum.CREDIT, LedgerEntry.amount),
        else_=-LedgerEntry.amount,
    )
    value = (
        db.query(func.coalesce(func.sum(signed_amount), 0))
        .join(LedgerJournal, LedgerJournal.id == LedgerEntry.journal_id)
        .filter(
            LedgerEntry.account_id == account_id,
            LedgerJournal.posted_at.is_not(None),
        )
        .scalar()
    )
    return money(value or ZERO_MONEY)


def _posted_entry_count(db: Session, account_id: UUID) -> int:
    return (
        db.query(func.count(LedgerEntry.id))
        .join(LedgerJournal, LedgerJournal.id == LedgerEntry.journal_id)
        .filter(
            LedgerEntry.account_id == account_id,
            LedgerJournal.posted_at.is_not(None),
        )
        .scalar()
        or 0
    )


def _post_journal(
    db: Session,
    *,
    operation_key: str,
    reference_type: str,
    reference_id: UUID | None,
    description: str,
    entries: Iterable[tuple[LedgerAccount, LedgerEntrySideEnum, Decimal]],
) -> tuple[LedgerJournal, bool]:
    existing = (
        db.query(LedgerJournal)
        .filter(LedgerJournal.operation_key == operation_key)
        .first()
    )
    if existing is not None:
        if existing.posted_at is None:
            raise LedgerIntegrityError(f"Ledger operation {operation_key} is not posted")
        return existing, False

    normalized_entries = [
        (account, side, money(amount))
        for account, side, amount in entries
        if money(amount) > ZERO_MONEY
    ]
    debit_total = sum(
        (amount for _, side, amount in normalized_entries if side == LedgerEntrySideEnum.DEBIT),
        ZERO_MONEY,
    )
    credit_total = sum(
        (amount for _, side, amount in normalized_entries if side == LedgerEntrySideEnum.CREDIT),
        ZERO_MONEY,
    )
    currencies = {account.currency for account, _, _ in normalized_entries}
    if len(normalized_entries) < 2 or debit_total != credit_total or len(currencies) != 1:
        raise LedgerIntegrityError(
            f"Unbalanced ledger operation {operation_key}: debits={debit_total}, credits={credit_total}"
        )

    journal = LedgerJournal(
        operation_key=operation_key,
        reference_type=reference_type,
        reference_id=reference_id,
        description=description,
    )
    db.add(journal)
    db.flush()

    for account, side, amount in normalized_entries:
        db.add(LedgerEntry(
            journal_id=journal.id,
            account_id=account.id,
            side=side,
            amount=amount,
            currency=account.currency,
        ))
    db.flush()

    # PostgreSQL validates entry count, currency, and debit/credit equality here.
    journal.posted_at = datetime.now(timezone.utc)
    db.flush()
    return journal, True


def initialize_wallet_ledger(db: Session, wallet: Wallet) -> LedgerAccount:
    """Create/reconcile a wallet liability account, including an opening balance."""
    account = _wallet_account(db, wallet)
    current_balance = money(wallet.balance)
    ledger_balance = _credit_balance(db, account.id)
    entry_count = _posted_entry_count(db, account.id)

    if entry_count == 0 and current_balance != ZERO_MONEY:
        clearing = _system_account(db, LEGACY_CLEARING_ACCOUNT_CODE)
        if current_balance > ZERO_MONEY:
            entries = (
                (clearing, LedgerEntrySideEnum.DEBIT, current_balance),
                (account, LedgerEntrySideEnum.CREDIT, current_balance),
            )
        else:
            entries = (
                (account, LedgerEntrySideEnum.DEBIT, -current_balance),
                (clearing, LedgerEntrySideEnum.CREDIT, -current_balance),
            )
        _post_journal(
            db,
            operation_key=f"wallet-opening:{wallet.id}",
            reference_type="wallet_opening",
            reference_id=wallet.id,
            description="Wallet opening balance",
            entries=entries,
        )
        ledger_balance = _credit_balance(db, account.id)

    if ledger_balance != current_balance:
        raise LedgerIntegrityError(
            f"Wallet {wallet.id} does not reconcile: balance={current_balance}, ledger={ledger_balance}"
        )
    return account


def reconcile_wallet(db: Session, wallet: Wallet) -> bool:
    account = _wallet_account(db, wallet)
    return _credit_balance(db, account.id) == money(wallet.balance)


def record_wallet_payment(
    db: Session,
    *,
    wallet: Wallet,
    checkout_order_id: UUID,
    amount: Decimal,
) -> bool:
    amount = money(amount)
    wallet_account = initialize_wallet_ledger(db, wallet)
    if money(wallet.balance) < amount:
        raise LedgerIntegrityError("Wallet balance is insufficient for the ledger payment")
    escrow = _system_account(db, ESCROW_ACCOUNT_CODE)
    journal, created = _post_journal(
        db,
        operation_key=f"checkout:{checkout_order_id}:wallet-payment",
        reference_type="checkout_order",
        reference_id=checkout_order_id,
        description=f"Wallet payment for checkout {checkout_order_id}",
        entries=(
            (wallet_account, LedgerEntrySideEnum.DEBIT, amount),
            (escrow, LedgerEntrySideEnum.CREDIT, amount),
        ),
    )
    if not created:
        return False

    wallet.balance = money(wallet.balance) - amount
    db.add(Transaction(
        wallet_id=wallet.id,
        ledger_journal_id=journal.id,
        type=TransactionTypeEnum.PAYMENT,
        amount=-amount,
        reference_id=checkout_order_id,
        reference_type="checkout_order",
        status="COMPLETED",
        description=f"Payment for order {checkout_order_id}",
    ))
    return True


def record_wallet_refund(
    db: Session,
    *,
    wallet: Wallet,
    seller_order_id: UUID,
    amount: Decimal,
) -> bool:
    amount = money(amount)
    wallet_account = initialize_wallet_ledger(db, wallet)
    escrow = _system_account(db, ESCROW_ACCOUNT_CODE)
    if _credit_balance(db, escrow.id) < amount:
        raise LedgerIntegrityError("Escrow ledger balance is insufficient for the refund")
    journal, created = _post_journal(
        db,
        operation_key=f"seller-order:{seller_order_id}:refund",
        reference_type="seller_order",
        reference_id=seller_order_id,
        description=f"Refund for seller order {seller_order_id}",
        entries=(
            (escrow, LedgerEntrySideEnum.DEBIT, amount),
            (wallet_account, LedgerEntrySideEnum.CREDIT, amount),
        ),
    )
    if not created:
        return False

    wallet.balance = money(wallet.balance) + amount
    db.add(Transaction(
        wallet_id=wallet.id,
        ledger_journal_id=journal.id,
        type=TransactionTypeEnum.REFUND,
        amount=amount,
        reference_id=seller_order_id,
        reference_type="seller_order",
        status="COMPLETED",
        description=f"Refund for seller order {seller_order_id}",
    ))
    return True


def record_escrow_payout(
    db: Session,
    *,
    seller_wallet: Wallet,
    seller_order_id: UUID,
    seller_amount: Decimal,
    platform_fee: Decimal,
) -> bool:
    seller_amount = money(seller_amount)
    platform_fee = money(platform_fee)
    total_amount = money(seller_amount + platform_fee)
    wallet_account = initialize_wallet_ledger(db, seller_wallet)
    escrow = _system_account(db, ESCROW_ACCOUNT_CODE)
    revenue = _system_account(db, PLATFORM_REVENUE_ACCOUNT_CODE)
    if _credit_balance(db, escrow.id) < total_amount:
        raise LedgerIntegrityError("Escrow ledger balance is insufficient for the payout")

    journal, created = _post_journal(
        db,
        operation_key=f"seller-order:{seller_order_id}:payout",
        reference_type="seller_order",
        reference_id=seller_order_id,
        description=f"Escrow settlement for seller order {seller_order_id}",
        entries=(
            (escrow, LedgerEntrySideEnum.DEBIT, total_amount),
            (wallet_account, LedgerEntrySideEnum.CREDIT, seller_amount),
            (revenue, LedgerEntrySideEnum.CREDIT, platform_fee),
        ),
    )
    if not created:
        return False

    seller_wallet.balance = money(seller_wallet.balance) + seller_amount
    db.add(Transaction(
        wallet_id=seller_wallet.id,
        ledger_journal_id=journal.id,
        type=TransactionTypeEnum.ESCROW_RELEASE,
        amount=seller_amount,
        reference_id=seller_order_id,
        reference_type="seller_order",
        status="COMPLETED",
        description=f"Escrow release for order {seller_order_id}",
    ))
    return True
