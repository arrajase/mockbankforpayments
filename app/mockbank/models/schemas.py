from enum import Enum

from pydantic import BaseModel


class PaymentStatus(str, Enum):
    PENDING = "pending"
    SETTLED = "settled"
    FAILED = "failed"


class Account(BaseModel):
    account_id: str
    owner_name: str
    balance_cents: int
    currency: str = "USD"


class AccountCreate(BaseModel):
    owner_name: str
    opening_balance_cents: int = 0
    currency: str = "USD"


class PaymentRequest(BaseModel):
    from_account_id: str
    to_account_id: str
    amount_cents: int
    currency: str = "USD"
    webhook_url: str | None = None


class Payment(BaseModel):
    payment_id: str
    from_account_id: str
    to_account_id: str
    amount_cents: int
    currency: str
    status: PaymentStatus
