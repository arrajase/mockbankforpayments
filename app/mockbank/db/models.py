from datetime import date

from sqlalchemy import Date, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.mockbank.db.database import Base


class CustomerModel(Base):
    __tablename__ = "customers"

    customer_id: Mapped[str] = mapped_column(String, primary_key=True)
    first_name: Mapped[str] = mapped_column(String)
    last_name: Mapped[str] = mapped_column(String)
    login_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String)


class AccountModel(Base):
    __tablename__ = "accounts"

    account_id: Mapped[str] = mapped_column(String, primary_key=True)
    account_number: Mapped[str] = mapped_column(String, unique=True, index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"), index=True)
    owner_name: Mapped[str] = mapped_column(String)
    account_name: Mapped[str] = mapped_column(String)
    account_type: Mapped[str] = mapped_column(String)
    balance_cents: Mapped[int]
    currency: Mapped[str] = mapped_column(String, default="USD")


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
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"), unique=True, index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.account_id"), index=True)


class TransactionHistoryModel(Base):
    __tablename__ = "TRANSACTION_HISTORY"

    transaction_id: Mapped[str] = mapped_column(String, primary_key=True)
    account_id: Mapped[str] = mapped_column(String, index=True)
    tran_type: Mapped[str] = mapped_column(String)
    posting_type: Mapped[str] = mapped_column(String)
    amount: Mapped[int]
    tran_date: Mapped[date] = mapped_column(Date)
