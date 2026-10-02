from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.mockbank.db.models import AccountModel, GenLedgerModel, TransactionHistoryModel, TranTypeModel
from app.mockbank.models.schemas import PostingType, Transaction, TranType, TransactionCreate
from app.mockbank.utils.common import new_id

GL_NAME_BY_TRAN_TYPE = {
    TranType.ATM_DEPOSIT: "Liability",
    TranType.ATM_WITHDRAWAL: "Liability",
    TranType.ATM_FEES: "Income",
    TranType.POS_PURCHASE: "Liability",
    TranType.CASH_BACK: "Liability",
    TranType.CREDIT_INTEREST: "Liability",
}


def posting_type_for(db: Session, posting_name: str) -> str:
    row = db.get(TranTypeModel, posting_name)
    if row is None:
        raise HTTPException(status_code=500, detail=f"no TRAN_TYPE entry for '{posting_name}'")
    return row.POSTING_TYPE


def _gl_account_for(db: Session, gl_name: str) -> str:
    row = db.query(GenLedgerModel).filter(GenLedgerModel.GL_NAME == gl_name).first()
    if row is None:
        raise HTTPException(status_code=500, detail=f"no GEN_LDGR entry for '{gl_name}'")
    return row.GL_ACCOUNT


def post_transaction(db: Session, payload: TransactionCreate) -> Transaction:
    account = db.get(AccountModel, payload.account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="account not found")

    posting_name = payload.tran_type.value
    contra_name = f"Contra {posting_name}"

    customer_posting_type = posting_type_for(db, posting_name)
    contra_posting_type = posting_type_for(db, contra_name)
    gl_account = _gl_account_for(db, GL_NAME_BY_TRAN_TYPE[payload.tran_type])

    if customer_posting_type == PostingType.DEBIT.value:
        if account.balance_cents < payload.amount_cents:
            raise HTTPException(status_code=400, detail="insufficient funds")
        account.balance_cents -= payload.amount_cents
    else:
        account.balance_cents += payload.amount_cents

    customer_leg = TransactionHistoryModel(
        transaction_id=new_id("txn"),
        account_id=account.account_id,
        tran_type=posting_name,
        posting_type=customer_posting_type,
        amount=payload.amount_cents,
        tran_date=payload.tran_date,
    )
    gl_leg = TransactionHistoryModel(
        transaction_id=new_id("txn"),
        account_id=gl_account,
        tran_type=contra_name,
        posting_type=contra_posting_type,
        amount=payload.amount_cents,
        tran_date=payload.tran_date,
    )

    db.add(customer_leg)
    db.add(gl_leg)
    db.commit()
    db.refresh(customer_leg)
    return Transaction.model_validate(customer_leg)


def list_transactions_for_account(db: Session, account_id: str) -> list[Transaction]:
    rows = (
        db.query(TransactionHistoryModel)
        .filter(TransactionHistoryModel.account_id == account_id)
        .order_by(TransactionHistoryModel.tran_date.desc(), TransactionHistoryModel.transaction_id.desc())
        .all()
    )
    return [Transaction.model_validate(row) for row in rows]
