from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.mockbank.db.database import Base
from app.mockbank.utils.common import utcnow


class CustomerModel(Base):
    __tablename__ = "customers"

    customer_id: Mapped[str] = mapped_column(String, primary_key=True)
    first_name: Mapped[str] = mapped_column(String)
    last_name: Mapped[str] = mapped_column(String)
    login_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String)


class AccountModel(Base):
    __tablename__ = "accounts"
    __table_args__ = (CheckConstraint("balance_cents >= 0", name="ck_accounts_balance_non_negative"),)

    account_id: Mapped[str] = mapped_column(String, primary_key=True)
    account_number: Mapped[str] = mapped_column(String, unique=True, index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"), index=True)
    owner_name: Mapped[str] = mapped_column(String)
    account_name: Mapped[str] = mapped_column(String)
    account_type: Mapped[str] = mapped_column(String)
    balance_cents: Mapped[int]
    currency: Mapped[str] = mapped_column(String, default="INR")


class GenLedgerModel(Base):
    __tablename__ = "GEN_LDGR"

    GL_ACCOUNT: Mapped[str] = mapped_column(String, primary_key=True)
    GL_NAME: Mapped[str] = mapped_column(String)


class TranTypeModel(Base):
    __tablename__ = "TRAN_TYPE"

    POSTING_NAME: Mapped[str] = mapped_column(String, primary_key=True)
    POSTING_TYPE: Mapped[str] = mapped_column(String)


class UpiModel(Base):
    __tablename__ = "upi_ids"

    upi_id: Mapped[str] = mapped_column(String, primary_key=True)
    # A customer may hold several UPI IDs (e.g. a business with escrow + operating IDs).
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"), index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.account_id"), index=True)
    status: Mapped[str] = mapped_column(String, default="ACTIVE", server_default="ACTIVE")
    pin_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    pin_failed_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    pin_locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class TransactionHistoryModel(Base):
    __tablename__ = "TRANSACTION_HISTORY"
    __table_args__ = (
        # client_reference is set only on the leg the client initiated, so the other legs stay NULL.
        Index("ux_txn_client_reference", "client_id", "client_reference", unique=True),
        Index("ix_txn_account_created", "account_id", "created_at"),
    )

    transaction_id: Mapped[str] = mapped_column(String, primary_key=True)
    account_id: Mapped[str] = mapped_column(String, index=True)
    tran_type: Mapped[str] = mapped_column(String)
    posting_type: Mapped[str] = mapped_column(String)
    amount: Mapped[int]
    tran_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String, default="SUCCESS", server_default="SUCCESS")
    failure_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    client_id: Mapped[str | None] = mapped_column(String, nullable=True)
    client_reference: Mapped[str | None] = mapped_column(String(64), nullable=True)
    transfer_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    upi_id: Mapped[str | None] = mapped_column(String, nullable=True)
    counterparty_upi_id: Mapped[str | None] = mapped_column(String, nullable=True)
    narration: Mapped[str | None] = mapped_column(String(100), nullable=True)
    currency: Mapped[str | None] = mapped_column(String, nullable=True)
    balance_after_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class IdempotencyKeyModel(Base):
    __tablename__ = "idempotency_keys"

    client_id: Mapped[str] = mapped_column(String, primary_key=True)
    key: Mapped[str] = mapped_column(String, primary_key=True)
    request_hash: Mapped[str] = mapped_column(String)
    status_code: Mapped[int] = mapped_column(Integer)
    response_body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class SessionModel(Base):
    __tablename__ = "sessions"

    token_hash: Mapped[str] = mapped_column(String, primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ApiClientModel(Base):
    __tablename__ = "api_clients"

    client_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    key_prefix: Mapped[str] = mapped_column(String, unique=True, index=True)
    key_hash: Mapped[str] = mapped_column(String)
    owner_customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"), index=True)
    webhook_url: Mapped[str | None] = mapped_column(String, nullable=True)
    webhook_secret: Mapped[str] = mapped_column(String)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CollectRequestModel(Base):
    __tablename__ = "collect_requests"
    __table_args__ = (UniqueConstraint("client_id", "client_reference", name="ux_collect_client_reference"),)

    collect_id: Mapped[str] = mapped_column(String, primary_key=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("api_clients.client_id"), index=True)
    payer_upi_id: Mapped[str] = mapped_column(String, index=True)
    payee_upi_id: Mapped[str] = mapped_column(String)
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String)
    client_reference: Mapped[str] = mapped_column(String(64))
    note: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String, default="PENDING", index=True)
    failure_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    transaction_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class ConsentModel(Base):
    __tablename__ = "consents"

    consent_id: Mapped[str] = mapped_column(String, primary_key=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("api_clients.client_id"), index=True)
    upi_id: Mapped[str] = mapped_column(String, index=True)
    purposes: Mapped[str] = mapped_column(String)  # comma-separated: LINK,STATEMENT,BALANCE
    statement_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    statement_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String, default="PENDING", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class OutboxEventModel(Base):
    __tablename__ = "outbox_events"

    seq: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("api_clients.client_id"), index=True)
    type: Mapped[str] = mapped_column(String)
    payload: Mapped[str] = mapped_column(Text)  # the exact JSON body that is signed and delivered
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    delivery_status: Mapped[str] = mapped_column(String, default="PENDING", index=True)  # PENDING/DELIVERED/FAILED/NO_ENDPOINT
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
