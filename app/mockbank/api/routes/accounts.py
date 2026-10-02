from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.mockbank.db.database import get_db
from app.mockbank.models.schemas import Account, AccountCreate
from app.mockbank.services import accounts as accounts_service

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.post("", response_model=Account)
def create_account(payload: AccountCreate, db: Session = Depends(get_db)):
    return accounts_service.create_account(db, payload)


@router.get("/{account_id}", response_model=Account)
def get_account(account_id: str, db: Session = Depends(get_db)):
    return accounts_service.get_account(db, account_id)


@router.get("", response_model=list[Account])
def list_accounts(customer_id: str, db: Session = Depends(get_db)):
    return accounts_service.list_accounts_for_customer(db, customer_id)
