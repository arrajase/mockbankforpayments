from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.mockbank.api.deps import current_customer, same_origin
from app.mockbank.db.database import get_db
from app.mockbank.db.models import CustomerModel
from app.mockbank.models.schemas import Account, AccountCreate
from app.mockbank.services import accounts as accounts_service

router = APIRouter(prefix="/accounts", tags=["website: accounts"], dependencies=[Depends(same_origin)])


@router.post("", response_model=Account)
def create_account(payload: AccountCreate, customer: CustomerModel = Depends(current_customer), db: Session = Depends(get_db)):
    return accounts_service.create_account(db, customer, payload)


@router.get("/{account_id}", response_model=Account)
def get_account(account_id: str, customer: CustomerModel = Depends(current_customer), db: Session = Depends(get_db)):
    return Account.model_validate(accounts_service.get_own_account(db, customer, account_id))


@router.get("", response_model=list[Account])
def list_accounts(customer: CustomerModel = Depends(current_customer), db: Session = Depends(get_db)):
    return accounts_service.list_accounts_for_customer(db, customer.customer_id)
