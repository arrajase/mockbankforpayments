from fastapi import HTTPException

from app.mockbank.db.store import accounts
from app.mockbank.models.schemas import Account, AccountCreate
from app.mockbank.utils.common import new_id


def create_account(payload: AccountCreate) -> Account:
    account = Account(
        account_id=new_id("acct"),
        owner_name=payload.owner_name,
        balance_cents=payload.opening_balance_cents,
        currency=payload.currency,
    )
    accounts[account.account_id] = account
    return account


def get_account(account_id: str) -> Account:
    account = accounts.get(account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="account not found")
    return account
