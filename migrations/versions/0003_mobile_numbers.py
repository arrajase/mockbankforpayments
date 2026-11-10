"""Customer mobile numbers, and linking one UPI ID per customer to that number.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-10
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable: customers who signed up before mobile numbers were required add one on their profile.
    with op.batch_alter_table("customers") as batch:
        batch.add_column(sa.Column("mobile_number", sa.String(), nullable=True))
        batch.create_index("ix_customers_mobile_number", ["mobile_number"], unique=True)

    with op.batch_alter_table("upi_ids") as batch:
        batch.add_column(sa.Column("mobile_linked", sa.Boolean(), nullable=False, server_default=sa.false()))

    op.create_index(
        "ux_upi_ids_mobile_linked",
        "upi_ids",
        ["customer_id"],
        unique=True,
        postgresql_where=sa.text("mobile_linked"),
        sqlite_where=sa.text("mobile_linked"),
    )


def downgrade() -> None:
    op.drop_index("ux_upi_ids_mobile_linked", table_name="upi_ids")
    with op.batch_alter_table("upi_ids") as batch:
        batch.drop_column("mobile_linked")
    with op.batch_alter_table("customers") as batch:
        batch.drop_index("ix_customers_mobile_number")
        batch.drop_column("mobile_number")
