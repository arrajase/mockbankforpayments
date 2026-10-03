import re
from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator

UPI_SUFFIX = "@okmockbank"
PIN_PATTERN = r"^\d{4,6}$"


class AccountType(str, Enum):
    CHECKING = "checking"
    SAVINGS = "savings"


class Currency(str, Enum):
    INR = "INR"
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"


# ---------- website: auth ----------

class SignupRequest(BaseModel):
    first_name: str
    last_name: str
    login_id: str
    password: str
    confirm_password: str

    @model_validator(mode="after")
    def passwords_must_match(self):
        if self.password != self.confirm_password:
            raise ValueError("password and confirm_password do not match")
        return self


class CustomerOut(BaseModel):
    model_config = {"from_attributes": True}

    customer_id: str
    first_name: str
    last_name: str
    login_id: str


class LoginRequest(BaseModel):
    login_id: str
    password: str


class LoginResponse(BaseModel):
    model_config = {"from_attributes": True}

    first_name: str
    last_name: str


# ---------- website: accounts & transactions ----------

class Account(BaseModel):
    model_config = {"from_attributes": True}

    account_id: str
    account_number: str
    customer_id: str
    owner_name: str
    account_name: str
    account_type: AccountType
    balance_cents: int
    currency: str


class AccountCreate(BaseModel):
    account_type: AccountType
    account_name: str
    currency: Currency = Currency.INR


class TranType(str, Enum):
    ATM_DEPOSIT = "ATM Deposit"
    ATM_WITHDRAWAL = "ATM Withdrawal"
    ATM_FEES = "ATM Fees"
    POS_PURCHASE = "POS Purchase"
    CASH_BACK = "Cash Back"
    CREDIT_INTEREST = "Credit Interest"


class PostingType(str, Enum):
    DEBIT = "Debit"
    CREDIT = "Credit"


class TransactionCreate(BaseModel):
    """Website form. Any tran_date sent by the browser is ignored: the bank sets the date."""

    account_id: str
    tran_type: TranType
    amount_cents: int = Field(gt=0)


class Transaction(BaseModel):
    transaction_id: str
    account_id: str
    tran_type: str
    posting_type: PostingType
    amount_cents: int
    currency: str | None
    status: str
    failure_reason: str | None = None
    counterparty_upi_id: str | None = None
    narration: str | None = None
    balance_after_cents: int | None = None
    created_at: str | None
    tran_date: date


# ---------- website: UPI IDs ----------

def _check_pin(value: str) -> str:
    if not re.fullmatch(PIN_PATTERN, value):
        raise ValueError("UPI PIN must be 4 to 6 digits")
    return value


class UpiCreate(BaseModel):
    handle: str
    account_id: str
    upi_pin: str

    @field_validator("handle")
    @classmethod
    def handle_must_be_alphanumeric(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9]+", value):
            raise ValueError("handle must be alphanumeric")
        return value

    @field_validator("upi_pin")
    @classmethod
    def pin_format(cls, value: str) -> str:
        return _check_pin(value)


class UpiUpdate(BaseModel):
    account_id: str


class UpiPinSet(BaseModel):
    new_pin: str
    current_pin: str | None = None

    @field_validator("new_pin")
    @classmethod
    def pin_format(cls, value: str) -> str:
        return _check_pin(value)


class Upi(BaseModel):
    upi_id: str
    customer_id: str
    account_id: str
    status: str
    pin_set: bool


class PinApproval(BaseModel):
    upi_pin: str


# ---------- gateway (API clients) ----------

class UpiBalance(BaseModel):
    upi_id: str
    owner_name: str
    account_type: AccountType
    balance_cents: int
    currency: str


class UpiVerifyResult(BaseModel):
    upi_id: str
    account_holder_name: str
    currency: str
    status: str


class _ClientMoneyRequest(BaseModel):
    amount_cents: int = Field(gt=0)
    currency: Currency
    client_reference: str = Field(min_length=1, max_length=64)
    narration: str | None = Field(default=None, max_length=100)


class UpiTransactionCreate(_ClientMoneyRequest):
    tran_type: TranType


class UpiPaymentCreate(_ClientMoneyRequest):
    recipient_upi_id: str


class TransactionRecord(BaseModel):
    """A client-visible transaction: returned by pay, by transaction lookups and as statement lines."""

    transaction_id: str
    transfer_id: str | None
    status: str
    failure_reason: str | None
    tran_type: str
    posting_type: PostingType
    amount_cents: int
    currency: str | None
    upi_id: str | None
    counterparty_upi_id: str | None
    sender_upi_id: str | None
    recipient_upi_id: str | None
    client_reference: str | None
    narration: str | None
    balance_after_cents: int | None
    created_at: str | None
    tran_date: date


class StatementPage(BaseModel):
    items: list[TransactionRecord]
    next_cursor: str | None


class CollectRequestCreate(BaseModel):
    payer_upi_id: str
    payee_upi_id: str
    amount_cents: int = Field(gt=0)
    currency: Currency
    client_reference: str = Field(min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=100)
    expires_in_seconds: int = Field(default=300, gt=0, le=900)


class CollectRequestOut(BaseModel):
    collect_id: str
    status: str
    failure_reason: str | None
    payer_upi_id: str
    payee_upi_id: str
    payee_name: str | None = None
    amount_cents: int
    currency: str
    client_reference: str
    note: str | None
    transaction_id: str | None
    created_at: str
    updated_at: str
    expires_at: str


class ConsentPurpose(str, Enum):
    LINK = "LINK"
    STATEMENT = "STATEMENT"
    BALANCE = "BALANCE"


class ConsentCreate(BaseModel):
    upi_id: str
    purposes: list[ConsentPurpose] = Field(min_length=1)
    statement_from: date | None = None
    statement_to: date | None = None
    expires_at: datetime

    @model_validator(mode="after")
    def statement_range_rules(self):
        if ConsentPurpose.STATEMENT in self.purposes:
            if self.statement_from is None or self.statement_to is None:
                raise ValueError("statement_from and statement_to are required for the STATEMENT purpose")
        if self.statement_from and self.statement_to and self.statement_from > self.statement_to:
            raise ValueError("statement_from must be on or before statement_to")
        return self


class ConsentOut(BaseModel):
    consent_id: str
    client_name: str | None = None
    upi_id: str
    purposes: list[str]
    statement_from: date | None
    statement_to: date | None
    status: str
    created_at: str
    updated_at: str
    expires_at: str


class PurposeAccess(BaseModel):
    enabled: bool
    expires_at: str | None


class AppAccess(BaseModel):
    client_id: str
    client_name: str
    upi_id: str
    purposes: dict[str, PurposeAccess]


class AppAccessUpdate(BaseModel):
    client_id: str
    upi_id: str
    purpose: ConsentPurpose
    enabled: bool
    upi_pin: str | None = None


class EventOut(BaseModel):
    event_id: str
    type: str
    created_at: str
    data: dict


class EventPage(BaseModel):
    items: list[EventOut]
