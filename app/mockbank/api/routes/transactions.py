from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.mockbank.db.database import get_db
from app.mockbank.models.schemas import Transaction, TransactionCreate
from app.mockbank.services import transactions as transactions_service

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.post("", response_model=Transaction)
def post_transaction(payload: TransactionCreate, db: Session = Depends(get_db)):
    return transactions_service.post_transaction(db, payload)


@router.get("", response_model=list[Transaction])
def list_transactions(account_id: str, db: Session = Depends(get_db)):
    return transactions_service.list_transactions_for_account(db, account_id)
