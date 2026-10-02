import re
from datetime import date
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator

UPI_SUFFIX = "@okmockbank"


class AccountType(str, Enum):
    CHECKING = "checking"
    SAVINGS = "savings"


class Currency(str, Enum):
    INR = "INR"
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"


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

    customer_id: str
    first_name: str
    last_name: str


class Account(BaseModel):
    model_config = {"from_attributes": True}

    account_id: str
    account_number: str
    customer_id: str
    owner_name: str
    account_name: str
    account_type: AccountType
    balance_cents: int
    currency: str = "USD"


class AccountCreate(BaseModel):
    customer_id: str
    account_type: AccountType
    account_name: str
    currency: Currency = Currency.USD


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
    account_id: str
    tran_type: TranType
    amount_cents: int = Field(gt=0)
    tran_date: date


class Transaction(BaseModel):
    model_config = {"from_attributes": True}

    transaction_id: str
    account_id: str
    tran_type: str
    posting_type: PostingType
    amount: int
    tran_date: date


class UpiCreate(BaseModel):
    customer_id: str
    handle: str
    account_id: str

    @field_validator("handle")
    @classmethod
    def handle_must_be_alphanumeric(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9]+", value):
            raise ValueError("handle must be alphanumeric")
        return value


class UpiUpdate(BaseModel):
    account_id: str


class Upi(BaseModel):
    model_config = {"from_attributes": True}

    upi_id: str
    customer_id: str
    account_id: str


class UpiBalance(BaseModel):
    upi_id: str
    owner_name: str
    account_type: AccountType
    balance_cents: int
    currency: str


class UpiTransactionCreate(BaseModel):
    tran_type: TranType
    amount_cents: int = Field(gt=0)
    tran_date: date


class UpiTransaction(BaseModel):
    transaction_id: str
    tran_type: str
    posting_type: PostingType
    amount: int
    tran_date: date


class UpiPaymentCreate(BaseModel):
    recipient_upi_id: str
    amount_cents: int = Field(gt=0)
    tran_date: date


class UpiPaymentResult(BaseModel):
    transaction_id: str
    sender_upi_id: str
    recipient_upi_id: str
    amount: int
    tran_date: date
