import random

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.mockbank.db.models import AccountModel, CustomerModel
from app.mockbank.models.schemas import Account, AccountCreate
from app.mockbank.utils.common import new_id


def _generate_account_number(db: Session) -> str:
    while True:
        candidate = "".join(str(random.randint(0, 9)) for _ in range(10))
        exists = db.query(AccountModel).filter(AccountModel.account_number == candidate).first()
        if exists is None:
            return candidate


def create_account(db: Session, payload: AccountCreate) -> Account:
    customer = db.get(CustomerModel, payload.customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="customer not found")

    account = AccountModel(
        account_id=new_id("acct"),
        account_number=_generate_account_number(db),
        customer_id=customer.customer_id,
        owner_name=f"{customer.first_name} {customer.last_name}",
        account_name=payload.account_name,
        account_type=payload.account_type.value,
        balance_cents=0,
        currency=payload.currency.value,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return Account.model_validate(account)


def get_account(db: Session, account_id: str) -> Account:
    account = db.get(AccountModel, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="account not found")
    return Account.model_validate(account)


def list_accounts_for_customer(db: Session, customer_id: str) -> list[Account]:
    accounts = db.query(AccountModel).filter(AccountModel.customer_id == customer_id).all()
    return [Account.model_validate(a) for a in accounts]
