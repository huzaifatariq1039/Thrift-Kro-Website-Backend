"""Add an immutable, reconcilable double-entry wallet ledger.

Revision ID: 20261014_07
Revises: 20261014_06
Create Date: 2026-10-14
"""

from decimal import Decimal
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20261014_07"
down_revision: Union[str, Sequence[str], None] = "20261014_06"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


account_type_enum = postgresql.ENUM(
    "ASSET", "LIABILITY", "EQUITY", "REVENUE", "EXPENSE",
    name="ledgeraccounttypeenum",
    create_type=False,
)
entry_side_enum = postgresql.ENUM(
    "DEBIT", "CREDIT",
    name="ledgerentrysideenum",
    create_type=False,
)


def _as_decimal(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def upgrade() -> None:
    bind = op.get_bind()
    account_type_enum.create(bind, checkfirst=True)
    entry_side_enum.create(bind, checkfirst=True)

    op.create_table(
        "ledger_accounts",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("account_type", account_type_enum, nullable=False),
        sa.Column("wallet_id", sa.UUID(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="PKR"),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["wallet_id"], ["wallets.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("code", name="uq_ledger_accounts_code"),
        sa.UniqueConstraint("wallet_id", name="uq_ledger_accounts_wallet_id"),
    )
    op.create_table(
        "ledger_journals",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("operation_key", sa.String(length=255), nullable=False),
        sa.Column("reference_type", sa.String(length=64), nullable=False),
        sa.Column("reference_id", sa.UUID(), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("operation_key", name="uq_ledger_journals_operation_key"),
    )
    op.create_index(
        "idx_ledger_journals_reference",
        "ledger_journals",
        ["reference_type", "reference_id"],
    )
    op.create_table(
        "ledger_entries",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("journal_id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("side", entry_side_enum, nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="PKR"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("amount > 0.0", name="ledger_entries_positive_amount_check"),
        sa.ForeignKeyConstraint(["journal_id"], ["ledger_journals.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["account_id"], ["ledger_accounts.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "journal_id", "account_id", "side",
            name="uq_ledger_entries_journal_account_side",
        ),
    )
    op.create_index("idx_ledger_entries_account", "ledger_entries", ["account_id"])

    op.add_column("transactions", sa.Column("ledger_journal_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_transactions_ledger_journal_id",
        "transactions",
        "ledger_journals",
        ["ledger_journal_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_transactions_ledger_journal_id",
        "transactions",
        ["ledger_journal_id"],
    )

    system_accounts = {
        "SYSTEM:ESCROW": (str(uuid4()), "Escrow liability", "LIABILITY"),
        "SYSTEM:PLATFORM_REVENUE": (str(uuid4()), "Platform fee revenue", "REVENUE"),
        "SYSTEM:LEGACY_CLEARING": (str(uuid4()), "Legacy migration clearing", "EQUITY"),
    }
    for code, (account_id, name, account_type) in system_accounts.items():
        bind.execute(sa.text("""
            INSERT INTO ledger_accounts
                (id, code, name, account_type, currency, is_system)
            VALUES
                (CAST(:id AS uuid), :code, :name, CAST(:account_type AS ledgeraccounttypeenum), 'PKR', true)
        """), {
            "id": account_id,
            "code": code,
            "name": name,
            "account_type": account_type,
        })

    wallet_rows = bind.execute(sa.text("""
        SELECT id, currency, balance
        FROM wallets
        ORDER BY id
    """)).mappings().all()
    transaction_rows = bind.execute(sa.text("""
        SELECT id, wallet_id, type::text AS type, amount, reference_id,
               reference_type, description, created_at
        FROM transactions
        ORDER BY created_at, id
    """)).mappings().all()
    transactions_by_wallet = {}
    for transaction in transaction_rows:
        transactions_by_wallet.setdefault(transaction["wallet_id"], []).append(transaction)

    wallet_accounts = {}
    for wallet in wallet_rows:
        account_id = str(uuid4())
        wallet_accounts[wallet["id"]] = account_id
        bind.execute(sa.text("""
            INSERT INTO ledger_accounts
                (id, code, name, account_type, wallet_id, currency, is_system)
            VALUES
                (CAST(:id AS uuid), :code, :name, 'LIABILITY', CAST(:wallet_id AS uuid), :currency, false)
        """), {
            "id": account_id,
            "code": f"WALLET:{wallet['id']}",
            "name": f"Wallet liability {wallet['id']}",
            "wallet_id": str(wallet["id"]),
            "currency": wallet["currency"] or "PKR",
        })

    def insert_journal(operation_key, reference_type, reference_id, description, entries, posted_at=None):
        journal_id = str(uuid4())
        bind.execute(sa.text("""
            INSERT INTO ledger_journals
                (id, operation_key, reference_type, reference_id, description, posted_at, created_at)
            VALUES
                (CAST(:id AS uuid), :operation_key, :reference_type,
                 CAST(:reference_id AS uuid), :description,
                 COALESCE(:posted_at, CURRENT_TIMESTAMP), COALESCE(:posted_at, CURRENT_TIMESTAMP))
        """), {
            "id": journal_id,
            "operation_key": operation_key,
            "reference_type": reference_type,
            "reference_id": str(reference_id) if reference_id else None,
            "description": description,
            "posted_at": posted_at,
        })
        for account_id, side, amount, currency in entries:
            amount = abs(_as_decimal(amount))
            if amount == 0:
                continue
            bind.execute(sa.text("""
                INSERT INTO ledger_entries
                    (id, journal_id, account_id, side, amount, currency)
                VALUES
                    (CAST(:id AS uuid), CAST(:journal_id AS uuid), CAST(:account_id AS uuid),
                     CAST(:side AS ledgerentrysideenum), :amount, :currency)
            """), {
                "id": str(uuid4()),
                "journal_id": journal_id,
                "account_id": account_id,
                "side": side,
                "amount": amount,
                "currency": currency or "PKR",
            })
        return journal_id

    clearing_id = system_accounts["SYSTEM:LEGACY_CLEARING"][0]
    escrow_id = system_accounts["SYSTEM:ESCROW"][0]
    revenue_id = system_accounts["SYSTEM:PLATFORM_REVENUE"][0]

    for wallet in wallet_rows:
        wallet_transactions = transactions_by_wallet.get(wallet["id"], [])
        historical_total = sum(
            (_as_decimal(transaction["amount"]) for transaction in wallet_transactions),
            Decimal("0.00"),
        )
        opening_adjustment = _as_decimal(wallet["balance"]) - historical_total
        if opening_adjustment != 0:
            wallet_account_id = wallet_accounts[wallet["id"]]
            if opening_adjustment > 0:
                entries = (
                    (clearing_id, "DEBIT", opening_adjustment, wallet["currency"]),
                    (wallet_account_id, "CREDIT", opening_adjustment, wallet["currency"]),
                )
            else:
                entries = (
                    (wallet_account_id, "DEBIT", -opening_adjustment, wallet["currency"]),
                    (clearing_id, "CREDIT", -opening_adjustment, wallet["currency"]),
                )
            insert_journal(
                f"wallet-opening:{wallet['id']}",
                "wallet_opening",
                wallet["id"],
                "Migrated wallet opening balance",
                entries,
            )

    for transaction in transaction_rows:
        amount = _as_decimal(transaction["amount"])
        wallet_account_id = wallet_accounts[transaction["wallet_id"]]
        currency = next(
            (wallet["currency"] for wallet in wallet_rows if wallet["id"] == transaction["wallet_id"]),
            "PKR",
        )
        transaction_type = transaction["type"]
        counter_account_id = clearing_id
        counter_amount = abs(amount)
        extra_entries = []

        if transaction_type in ("PAYMENT", "REFUND"):
            counter_account_id = escrow_id
        elif transaction_type == "ESCROW_RELEASE" and transaction["reference_id"]:
            allocation = bind.execute(sa.text("""
                SELECT total_amount, platform_fee
                FROM seller_orders
                WHERE id = CAST(:id AS uuid)
            """), {"id": str(transaction["reference_id"])}).mappings().first()
            if allocation:
                counter_account_id = escrow_id
                counter_amount = _as_decimal(allocation["total_amount"])
                fee = _as_decimal(allocation["platform_fee"])
                if fee > 0:
                    extra_entries.append((revenue_id, "CREDIT", fee, currency))

        if amount < 0:
            entries = [
                (wallet_account_id, "DEBIT", -amount, currency),
                (counter_account_id, "CREDIT", -amount, currency),
            ]
        else:
            entries = [
                (counter_account_id, "DEBIT", counter_amount, currency),
                (wallet_account_id, "CREDIT", amount, currency),
                *extra_entries,
            ]

        journal_id = insert_journal(
            f"legacy-transaction:{transaction['id']}",
            transaction["reference_type"] or "legacy_transaction",
            transaction["reference_id"],
            transaction["description"] or f"Migrated transaction {transaction['id']}",
            entries,
            transaction["created_at"],
        )
        bind.execute(sa.text("""
            UPDATE transactions
            SET ledger_journal_id = CAST(:journal_id AS uuid)
            WHERE id = CAST(:transaction_id AS uuid)
        """), {
            "journal_id": journal_id,
            "transaction_id": str(transaction["id"]),
        })

    op.alter_column("transactions", "ledger_journal_id", nullable=False)

    op.execute("""
        CREATE FUNCTION guard_ledger_journal_mutation() RETURNS trigger AS $$
        DECLARE
            entry_count integer;
            currency_count integer;
            debit_total numeric(14,2);
            credit_total numeric(14,2);
        BEGIN
            IF TG_OP = 'DELETE' THEN
                IF OLD.posted_at IS NOT NULL THEN
                    RAISE EXCEPTION 'posted ledger journals are immutable';
                END IF;
                RETURN OLD;
            END IF;

            IF TG_OP = 'INSERT' THEN
                IF NEW.posted_at IS NOT NULL THEN
                    RAISE EXCEPTION 'ledger journals must be posted after entries are created';
                END IF;
                RETURN NEW;
            END IF;

            IF OLD.posted_at IS NOT NULL THEN
                RAISE EXCEPTION 'posted ledger journals are immutable';
            END IF;
            IF NEW.posted_at IS NULL THEN
                RETURN NEW;
            END IF;

            SELECT count(*), count(DISTINCT currency),
                   COALESCE(sum(amount) FILTER (WHERE side = 'DEBIT'), 0),
                   COALESCE(sum(amount) FILTER (WHERE side = 'CREDIT'), 0)
            INTO entry_count, currency_count, debit_total, credit_total
            FROM ledger_entries
            WHERE journal_id = NEW.id;

            IF entry_count < 2 OR currency_count <> 1 OR debit_total <> credit_total THEN
                RAISE EXCEPTION 'ledger journal % is not balanced', NEW.id;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER ledger_journals_immutable
        BEFORE INSERT OR UPDATE OR DELETE ON ledger_journals
        FOR EACH ROW EXECUTE FUNCTION guard_ledger_journal_mutation()
    """)
    op.execute("""
        CREATE FUNCTION guard_ledger_entry_mutation() RETURNS trigger AS $$
        DECLARE
            target_journal_id uuid;
            journal_posted_at timestamptz;
        BEGIN
            target_journal_id := CASE WHEN TG_OP = 'DELETE' THEN OLD.journal_id ELSE NEW.journal_id END;
            SELECT posted_at INTO journal_posted_at
            FROM ledger_journals WHERE id = target_journal_id;
            IF journal_posted_at IS NOT NULL THEN
                RAISE EXCEPTION 'entries in posted ledger journals are immutable';
            END IF;
            RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER ledger_entries_immutable
        BEFORE INSERT OR UPDATE OR DELETE ON ledger_entries
        FOR EACH ROW EXECUTE FUNCTION guard_ledger_entry_mutation()
    """)
    op.execute("""
        CREATE FUNCTION guard_ledger_account_mutation() RETURNS trigger AS $$
        BEGIN
            IF OLD.is_system OR EXISTS (
                SELECT 1 FROM ledger_entries WHERE account_id = OLD.id
            ) THEN
                RAISE EXCEPTION 'used ledger accounts are immutable';
            END IF;
            RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER ledger_accounts_immutable
        BEFORE UPDATE OR DELETE ON ledger_accounts
        FOR EACH ROW EXECUTE FUNCTION guard_ledger_account_mutation()
    """)
    op.execute("""
        CREATE FUNCTION assert_wallet_reconciles(target_wallet_id uuid, expected_balance numeric)
        RETURNS void AS $$
        DECLARE
            account_id_value uuid;
            ledger_balance numeric(14,2);
        BEGIN
            SELECT id INTO account_id_value
            FROM ledger_accounts WHERE wallet_id = target_wallet_id;
            IF account_id_value IS NULL THEN
                IF expected_balance <> 0 THEN
                    RAISE EXCEPTION 'wallet % has no ledger account', target_wallet_id;
                END IF;
                RETURN;
            END IF;
            SELECT COALESCE(sum(CASE WHEN entries.side = 'CREDIT' THEN entries.amount ELSE -entries.amount END), 0)
            INTO ledger_balance
            FROM ledger_entries AS entries
            JOIN ledger_journals AS journals ON journals.id = entries.journal_id
            WHERE entries.account_id = account_id_value AND journals.posted_at IS NOT NULL;
            IF ledger_balance <> expected_balance THEN
                RAISE EXCEPTION 'wallet % does not reconcile: balance %, ledger %',
                    target_wallet_id, expected_balance, ledger_balance;
            END IF;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE FUNCTION enforce_wallet_row_reconciliation() RETURNS trigger AS $$
        DECLARE current_balance numeric(14,2);
        BEGIN
            SELECT balance INTO current_balance FROM wallets WHERE id = NEW.id;
            PERFORM assert_wallet_reconciles(NEW.id, current_balance);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE CONSTRAINT TRIGGER wallets_reconcile_with_ledger
        AFTER INSERT OR UPDATE ON wallets
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION enforce_wallet_row_reconciliation()
    """)
    op.execute("""
        CREATE FUNCTION enforce_journal_wallet_reconciliation() RETURNS trigger AS $$
        DECLARE wallet_row record;
        BEGIN
            IF NEW.posted_at IS NULL THEN
                RETURN NEW;
            END IF;
            FOR wallet_row IN
                SELECT DISTINCT wallets.id, wallets.balance
                FROM ledger_entries AS entries
                JOIN ledger_accounts AS accounts ON accounts.id = entries.account_id
                JOIN wallets ON wallets.id = accounts.wallet_id
                WHERE entries.journal_id = NEW.id
            LOOP
                PERFORM assert_wallet_reconciles(wallet_row.id, wallet_row.balance);
            END LOOP;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE CONSTRAINT TRIGGER posted_journals_reconcile_wallets
        AFTER INSERT OR UPDATE ON ledger_journals
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION enforce_journal_wallet_reconciliation()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS posted_journals_reconcile_wallets ON ledger_journals")
    op.execute("DROP FUNCTION IF EXISTS enforce_journal_wallet_reconciliation()")
    op.execute("DROP TRIGGER IF EXISTS wallets_reconcile_with_ledger ON wallets")
    op.execute("DROP FUNCTION IF EXISTS enforce_wallet_row_reconciliation()")
    op.execute("DROP FUNCTION IF EXISTS assert_wallet_reconciles(uuid, numeric)")
    op.execute("DROP TRIGGER IF EXISTS ledger_accounts_immutable ON ledger_accounts")
    op.execute("DROP FUNCTION IF EXISTS guard_ledger_account_mutation()")
    op.execute("DROP TRIGGER IF EXISTS ledger_entries_immutable ON ledger_entries")
    op.execute("DROP FUNCTION IF EXISTS guard_ledger_entry_mutation()")
    op.execute("DROP TRIGGER IF EXISTS ledger_journals_immutable ON ledger_journals")
    op.execute("DROP FUNCTION IF EXISTS guard_ledger_journal_mutation()")

    op.drop_constraint("uq_transactions_ledger_journal_id", "transactions", type_="unique")
    op.drop_constraint("fk_transactions_ledger_journal_id", "transactions", type_="foreignkey")
    op.drop_column("transactions", "ledger_journal_id")
    op.drop_index("idx_ledger_entries_account", table_name="ledger_entries")
    op.drop_table("ledger_entries")
    op.drop_index("idx_ledger_journals_reference", table_name="ledger_journals")
    op.drop_table("ledger_journals")
    op.drop_table("ledger_accounts")
    entry_side_enum.drop(op.get_bind(), checkfirst=True)
    account_type_enum.drop(op.get_bind(), checkfirst=True)
