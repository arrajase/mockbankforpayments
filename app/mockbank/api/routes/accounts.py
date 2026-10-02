from fastapi import APIRouter, Depends

from app.mockbank.api.routes.auth import require_api_key
from app.mockbank.models.schemas import Account, AccountCreate
from app.mockbank.services import accounts as accounts_service

router = APIRouter(prefix="/accounts", tags=["accounts"], dependencies=[Depends(require_api_key)])


@router.post("", response_model=Account)
def create_account(payload: AccountCreate):
    return accounts_service.create_account(payload)


@router.get("/{account_id}", response_model=Account)
def get_account(account_id: str):
    return accounts_service.get_account(account_id)
