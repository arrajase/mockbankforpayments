"""Baseline: the schema as Base.metadata.create_all created it before migrations existed.

Tables that already exist (e.g. on the Neon database) are left alone, so this revision is safe
to run against a database created by the old create_all.

Revision ID: 0001
Revises:
Create Date: 2026-10-03
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _exists(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if not _exists("customers"):
        op.create_table(
            "customers",
            sa.Column("customer_id", sa.String(), primary_key=True),
            sa.Column("first_name", sa.String(), nullable=False),
            sa.Column("last_name", sa.String(), nullable=False),
            sa.Column("login_id", sa.String(), nullable=False),
            sa.Column("password_hash", sa.String(), nullable=False),
        )
        op.create_index("ix_customers_login_id", "customers", ["login_id"], unique=True)

    if not _exists("accounts"):
        op.create_table(
            "accounts",
            sa.Column("account_id", sa.String(), primary_key=True),
            sa.Column("account_number", sa.String(), nullable=False),
            sa.Column("customer_id", sa.String(), sa.ForeignKey("customers.customer_id"), nullable=False),
            sa.Column("owner_name", sa.String(), nullable=False),
            sa.Column("account_name", sa.String(), nullable=False),
            sa.Column("account_type", sa.String(), nullable=False),
            sa.Column("balance_cents", sa.Integer(), nullable=False),
            sa.Column("currency", sa.String(), nullable=False),
        )
        op.create_index("ix_accounts_account_number", "accounts", ["account_number"], unique=True)
        op.create_index("ix_accounts_customer_id", "accounts", ["customer_id"])

    if not _exists("GEN_LDGR"):
        op.create_table(
            "GEN_LDGR",
            sa.Column("GL_ACCOUNT", sa.String(), primary_key=True),
            sa.Column("GL_NAME", sa.String(), nullable=False),
        )

    if not _exists("TRAN_TYPE"):
        op.create_table(
            "TRAN_TYPE",
            sa.Column("POSTING_NAME", sa.String(), primary_key=True),
            sa.Column("POSTING_TYPE", sa.String(), nullable=False),
        )

    if not _exists("upi_ids"):
        op.create_table(
            "upi_ids",
            sa.Column("upi_id", sa.String(), primary_key=True),
            sa.Column("customer_id", sa.String(), sa.ForeignKey("customers.customer_id"), nullable=False),
            sa.Column("account_id", sa.String(), sa.ForeignKey("accounts.account_id"), nullable=False),
        )
        op.create_index("ix_upi_ids_customer_id", "upi_ids", ["customer_id"], unique=True)
        op.create_index("ix_upi_ids_account_id", "upi_ids", ["account_id"])

    if not _exists("TRANSACTION_HISTORY"):
        op.create_table(
            "TRANSACTION_HISTORY",
            sa.Column("transaction_id", sa.String(), primary_key=True),
            sa.Column("account_id", sa.String(), nullable=False),
            sa.Column("tran_type", sa.String(), nullable=False),
            sa.Column("posting_type", sa.String(), nullable=False),
            sa.Column("amount", sa.Integer(), nullable=False),
            sa.Column("tran_date", sa.Date(), nullable=False),
        )
        op.create_index("ix_TRANSACTION_HISTORY_account_id", "TRANSACTION_HISTORY", ["account_id"])


def downgrade() -> None:
    for table in ("TRANSACTION_HISTORY", "upi_ids", "TRAN_TYPE", "GEN_LDGR", "accounts", "customers"):
        op.drop_table(table)
