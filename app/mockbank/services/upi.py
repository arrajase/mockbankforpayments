from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.mockbank.db.models import AccountModel, CustomerModel, TransactionHistoryModel, UpiModel
from app.mockbank.models.schemas import (
    UPI_SUFFIX,
    TransactionCreate,
    Upi,
    UpiBalance,
    UpiCreate,
    UpiPaymentCreate,
    UpiPaymentResult,
    UpiTransaction,
    UpiTransactionCreate,
    UpiUpdate,
)
from app.mockbank.services import transactions as transactions_service
from app.mockbank.utils.common import new_id

FUND_TRANSFER_TO_TYPE = "Fund Transfer To"
FUND_TRANSFER_FROM_TYPE = "Fund Transfer From"


def _account_belongs_to_customer(db: Session, account_id: str, customer_id: str) -> AccountModel:
    account = db.get(AccountModel, account_id)
    if account is None or account.customer_id != customer_id:
        raise HTTPException(status_code=404, detail="account not found for this customer")
    return account


def create_upi(db: Session, payload: UpiCreate) -> Upi:
    customer = db.get(CustomerModel, payload.customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="customer not found")

    existing = db.query(UpiModel).filter(UpiModel.customer_id == payload.customer_id).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="customer already has a UPI ID")

    _account_belongs_to_customer(db, payload.account_id, payload.customer_id)

    upi_id = f"{payload.handle}{UPI_SUFFIX}"
    if db.get(UpiModel, upi_id) is not None:
        raise HTTPException(status_code=409, detail="UPI ID already taken")

    upi = UpiModel(upi_id=upi_id, customer_id=payload.customer_id, account_id=payload.account_id)
    db.add(upi)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="UPI ID already taken")
    db.refresh(upi)
    return Upi.model_validate(upi)


def get_upi_for_customer(db: Session, customer_id: str) -> Upi | None:
    upi = db.query(UpiModel).filter(UpiModel.customer_id == customer_id).first()
    if upi is None:
        return None
    return Upi.model_validate(upi)


def update_upi_account(db: Session, upi_id: str, payload: UpiUpdate) -> Upi:
    upi = db.get(UpiModel, upi_id)
    if upi is None:
        raise HTTPException(status_code=404, detail="UPI ID not found")

    _account_belongs_to_customer(db, payload.account_id, upi.customer_id)

    upi.account_id = payload.account_id
    db.commit()
    db.refresh(upi)
    return Upi.model_validate(upi)


def _resolve_upi(db: Session, upi_id: str) -> UpiModel:
    upi = db.get(UpiModel, upi_id)
    if upi is None:
        raise HTTPException(status_code=404, detail="UPI ID not found")
    return upi


def get_balance_by_upi(db: Session, upi_id: str) -> UpiBalance:
    upi = _resolve_upi(db, upi_id)
    account = db.get(AccountModel, upi.account_id)
    return UpiBalance(
        upi_id=upi.upi_id,
        owner_name=account.owner_name,
        account_type=account.account_type,
        balance_cents=account.balance_cents,
        currency=account.currency,
    )


def get_statement_by_upi(db: Session, upi_id: str) -> list[UpiTransaction]:
    upi = _resolve_upi(db, upi_id)
    transactions = transactions_service.list_transactions_for_account(db, upi.account_id)
    return [
        UpiTransaction(
            transaction_id=t.transaction_id,
            tran_type=t.tran_type,
            posting_type=t.posting_type,
            amount=t.amount,
            tran_date=t.tran_date,
        )
        for t in transactions
    ]


def post_transaction_by_upi(db: Session, upi_id: str, payload: UpiTransactionCreate) -> UpiTransaction:
    upi = _resolve_upi(db, upi_id)
    transaction = transactions_service.post_transaction(
        db,
        TransactionCreate(
            account_id=upi.account_id,
            tran_type=payload.tran_type,
            amount_cents=payload.amount_cents,
            tran_date=payload.tran_date,
        ),
    )
    return UpiTransaction(
        transaction_id=transaction.transaction_id,
        tran_type=transaction.tran_type,
        posting_type=transaction.posting_type,
        amount=transaction.amount,
        tran_date=transaction.tran_date,
    )


def pay_via_upi(db: Session, sender_upi_id: str, payload: UpiPaymentCreate) -> UpiPaymentResult:
    sender_upi = _resolve_upi(db, sender_upi_id)
    recipient_upi = _resolve_upi(db, payload.recipient_upi_id)

    if sender_upi.upi_id == recipient_upi.upi_id:
        raise HTTPException(status_code=400, detail="cannot pay your own UPI ID")

    sender_account = db.get(AccountModel, sender_upi.account_id)
    recipient_account = db.get(AccountModel, recipient_upi.account_id)

    debit_posting_type = transactions_service.posting_type_for(db, FUND_TRANSFER_TO_TYPE)
    credit_posting_type = transactions_service.posting_type_for(db, FUND_TRANSFER_FROM_TYPE)

    if sender_account.balance_cents < payload.amount_cents:
        raise HTTPException(status_code=400, detail="insufficient funds")

    sender_account.balance_cents -= payload.amount_cents
    recipient_account.balance_cents += payload.amount_cents

    sender_leg = TransactionHistoryModel(
        transaction_id=new_id("txn"),
        account_id=sender_account.account_id,
        tran_type=FUND_TRANSFER_TO_TYPE,
        posting_type=debit_posting_type,
        amount=payload.amount_cents,
        tran_date=payload.tran_date,
    )
    recipient_leg = TransactionHistoryModel(
        transaction_id=new_id("txn"),
        account_id=recipient_account.account_id,
        tran_type=FUND_TRANSFER_FROM_TYPE,
        posting_type=credit_posting_type,
        amount=payload.amount_cents,
        tran_date=payload.tran_date,
    )

    db.add(sender_leg)
    db.add(recipient_leg)
    db.commit()
    db.refresh(sender_leg)

    return UpiPaymentResult(
        transaction_id=sender_leg.transaction_id,
        sender_upi_id=sender_upi.upi_id,
        recipient_upi_id=recipient_upi.upi_id,
        amount=payload.amount_cents,
        tran_date=payload.tran_date,
    )
