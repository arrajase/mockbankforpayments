"""Idempotency, transaction metadata, locking constraint, sessions, API clients, UPI PINs,
collect requests, consents and the webhook outbox.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-03
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # accounts: the database itself refuses an overdraft
    with op.batch_alter_table("accounts") as batch:
        batch.create_check_constraint("ck_accounts_balance_non_negative", "balance_cents >= 0")

    # upi_ids: several per customer, plus status and a hashed UPI PIN with its own attempt counter
    with op.batch_alter_table("upi_ids") as batch:
        batch.drop_index("ix_upi_ids_customer_id")
        batch.create_index("ix_upi_ids_customer_id", ["customer_id"], unique=False)
        batch.add_column(sa.Column("status", sa.String(), nullable=False, server_default="ACTIVE"))
        batch.add_column(sa.Column("pin_hash", sa.String(), nullable=True))
        batch.add_column(sa.Column("pin_failed_attempts", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("pin_locked_until", sa.DateTime(), nullable=True))

    # TRANSACTION_HISTORY: who asked, why, against whom, and the resulting balance
    with op.batch_alter_table("TRANSACTION_HISTORY") as batch:
        batch.add_column(sa.Column("status", sa.String(), nullable=False, server_default="SUCCESS"))
        batch.add_column(sa.Column("failure_reason", sa.String(), nullable=True))
        batch.add_column(sa.Column("client_id", sa.String(), nullable=True))
        batch.add_column(sa.Column("client_reference", sa.String(64), nullable=True))
        batch.add_column(sa.Column("transfer_id", sa.String(), nullable=True))
        batch.add_column(sa.Column("upi_id", sa.String(), nullable=True))
        batch.add_column(sa.Column("counterparty_upi_id", sa.String(), nullable=True))
        batch.add_column(sa.Column("narration", sa.String(100), nullable=True))
        batch.add_column(sa.Column("currency", sa.String(), nullable=True))
        batch.add_column(sa.Column("balance_after_cents", sa.BigInteger(), nullable=True))
        batch.add_column(sa.Column("created_at", sa.DateTime(), nullable=True))

    # Backfill existing rows: currency from the account, created_at from the posting date.
    op.execute(
        'UPDATE "TRANSACTION_HISTORY" SET currency = '
        '(SELECT a.currency FROM accounts a WHERE a.account_id = "TRANSACTION_HISTORY".account_id)'
    )
    op.execute('UPDATE "TRANSACTION_HISTORY" SET created_at = tran_date WHERE created_at IS NULL')

    with op.batch_alter_table("TRANSACTION_HISTORY") as batch:
        batch.alter_column("created_at", existing_type=sa.DateTime(), nullable=False)
        batch.create_index("ux_txn_client_reference", ["client_id", "client_reference"], unique=True)
        batch.create_index("ix_txn_account_created", ["account_id", "created_at"])
        batch.create_index("ix_TRANSACTION_HISTORY_transfer_id", ["transfer_id"])

    op.create_table(
        "idempotency_keys",
        sa.Column("client_id", sa.String(), primary_key=True),
        sa.Column("key", sa.String(), primary_key=True),
        sa.Column("request_hash", sa.String(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("response_body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_idempotency_keys_created_at", "idempotency_keys", ["created_at"])

    op.create_table(
        "sessions",
        sa.Column("token_hash", sa.String(), primary_key=True),
        sa.Column("customer_id", sa.String(), sa.ForeignKey("customers.customer_id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_sessions_customer_id", "sessions", ["customer_id"])

    op.create_table(
        "api_clients",
        sa.Column("client_id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False, unique=True),
        sa.Column("key_prefix", sa.String(), nullable=False),
        sa.Column("key_hash", sa.String(), nullable=False),
        sa.Column("owner_customer_id", sa.String(), sa.ForeignKey("customers.customer_id"), nullable=False),
        sa.Column("webhook_url", sa.String(), nullable=True),
        sa.Column("webhook_secret", sa.String(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_api_clients_key_prefix", "api_clients", ["key_prefix"], unique=True)
    op.create_index("ix_api_clients_owner_customer_id", "api_clients", ["owner_customer_id"])

    op.create_table(
        "collect_requests",
        sa.Column("collect_id", sa.String(), primary_key=True),
        sa.Column("client_id", sa.String(), sa.ForeignKey("api_clients.client_id"), nullable=False),
        sa.Column("payer_upi_id", sa.String(), nullable=False),
        sa.Column("payee_upi_id", sa.String(), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(), nullable=False),
        sa.Column("client_reference", sa.String(64), nullable=False),
        sa.Column("note", sa.String(100), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("failure_reason", sa.String(), nullable=True),
        sa.Column("transaction_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("client_id", "client_reference", name="ux_collect_client_reference"),
    )
    op.create_index("ix_collect_requests_client_id", "collect_requests", ["client_id"])
    op.create_index("ix_collect_requests_payer_upi_id", "collect_requests", ["payer_upi_id"])
    op.create_index("ix_collect_requests_status", "collect_requests", ["status"])

    op.create_table(
        "consents",
        sa.Column("consent_id", sa.String(), primary_key=True),
        sa.Column("client_id", sa.String(), sa.ForeignKey("api_clients.client_id"), nullable=False),
        sa.Column("upi_id", sa.String(), nullable=False),
        sa.Column("purposes", sa.String(), nullable=False),
        sa.Column("statement_from", sa.Date(), nullable=True),
        sa.Column("statement_to", sa.Date(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_consents_client_id", "consents", ["client_id"])
    op.create_index("ix_consents_upi_id", "consents", ["upi_id"])
    op.create_index("ix_consents_status", "consents", ["status"])

    op.create_table(
        "outbox_events",
        sa.Column("seq", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("client_id", sa.String(), sa.ForeignKey("api_clients.client_id"), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("delivery_status", sa.String(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_outbox_events_event_id", "outbox_events", ["event_id"], unique=True)
    op.create_index("ix_outbox_events_client_id", "outbox_events", ["client_id"])
    op.create_index("ix_outbox_events_delivery_status", "outbox_events", ["delivery_status"])
    op.create_index("ix_outbox_events_next_attempt_at", "outbox_events", ["next_attempt_at"])


def downgrade() -> None:
    for table in ("outbox_events", "consents", "collect_requests", "api_clients", "sessions", "idempotency_keys"):
        op.drop_table(table)

    with op.batch_alter_table("TRANSACTION_HISTORY") as batch:
        batch.drop_index("ix_TRANSACTION_HISTORY_transfer_id")
        batch.drop_index("ix_txn_account_created")
        batch.drop_index("ux_txn_client_reference")
        for column in ("created_at", "balance_after_cents", "currency", "narration", "counterparty_upi_id",
                       "upi_id", "transfer_id", "client_reference", "client_id", "failure_reason", "status"):
            batch.drop_column(column)

    with op.batch_alter_table("upi_ids") as batch:
        for column in ("pin_locked_until", "pin_failed_attempts", "pin_hash", "status"):
            batch.drop_column(column)
        batch.drop_index("ix_upi_ids_customer_id")
        batch.create_index("ix_upi_ids_customer_id", ["customer_id"], unique=True)

    with op.batch_alter_table("accounts") as batch:
        batch.drop_constraint("ck_accounts_balance_non_negative", type_="check")
