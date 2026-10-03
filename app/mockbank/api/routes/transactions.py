from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.mockbank.api.deps import current_client, current_customer, same_origin
from app.mockbank.core.errors import BankError
from app.mockbank.db.database import get_db
from app.mockbank.db.models import ApiClientModel, CustomerModel
from app.mockbank.models.schemas import Transaction, TransactionCreate, TransactionRecord
from app.mockbank.services import clients as clients_service
from app.mockbank.services import transactions as transactions_service

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.post("", response_model=Transaction, dependencies=[Depends(same_origin)])
def post_transaction(payload: TransactionCreate, customer: CustomerModel = Depends(current_customer), db: Session = Depends(get_db)):
    """Website: post test money (e.g. ATM Deposit) to one of the logged-in customer's own accounts."""
    return transactions_service.post_own_transaction(db, customer, payload)


@router.get("")
def list_or_lookup(
    request: Request,
    account_id: str | None = None,
    client_reference: str | None = None,
    db: Session = Depends(get_db),
):
    """Two callers share this path:

    - API clients (x-api-key header): `?client_reference=...` returns that client's transaction.
    - The website (session cookie): `?account_id=...` lists the logged-in customer's account history.
    """
    api_key = request.headers.get("x-api-key")
    if api_key is not None:
        client = clients_service.authenticate(db, api_key)
        if not client_reference:
            raise BankError("VALIDATION_ERROR", "client_reference is required")
        return transactions_service.find_by_client_reference(db, client, client_reference)

    customer = current_customer(request, db)
    if not account_id:
        raise BankError("VALIDATION_ERROR", "account_id is required")
    return transactions_service.list_own_transactions(db, customer, account_id)


@router.get("/{transaction_id}", response_model=TransactionRecord, tags=["gateway"])
def get_transaction(transaction_id: str, client: ApiClientModel = Depends(current_client), db: Session = Depends(get_db)):
    return transactions_service.get_client_transaction(db, client, transaction_id)
