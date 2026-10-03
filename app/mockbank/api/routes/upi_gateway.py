from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.mockbank.api.deps import current_client, idempotency_key
from app.mockbank.api.routes.money import run_money_call
from app.mockbank.core.config import VERIFY_RATE_LIMIT_PER_MINUTE
from app.mockbank.core.errors import BankError
from app.mockbank.db.database import get_db
from app.mockbank.db.models import ApiClientModel
from app.mockbank.models.schemas import (
    StatementPage,
    TransactionRecord,
    UpiBalance,
    UpiPaymentCreate,
    UpiTransactionCreate,
    UpiVerifyResult,
)
from app.mockbank.services import upi as upi_service
from app.mockbank.utils.ratelimit import SlidingWindowLimiter

router = APIRouter(prefix="/upi", tags=["gateway"])

verify_limiter = SlidingWindowLimiter(VERIFY_RATE_LIMIT_PER_MINUTE, 60)


@router.get("/{upi_id}/verify", response_model=UpiVerifyResult)
def verify(upi_id: str, client: ApiClientModel = Depends(current_client), db: Session = Depends(get_db)):
    """Check a UPI ID exists and whose it is, without revealing the balance."""
    if not verify_limiter.allow(client.client_id):
        raise BankError("RATE_LIMITED", f"at most {VERIFY_RATE_LIMIT_PER_MINUTE} verify calls per minute")
    return upi_service.verify_upi(db, upi_id)


@router.get("/{upi_id}/balance", response_model=UpiBalance)
def get_balance(
    upi_id: str,
    consent_id: str | None = None,
    client: ApiClientModel = Depends(current_client),
    db: Session = Depends(get_db),
):
    return upi_service.get_balance(db, client, upi_id, consent_id)


@router.get("/{upi_id}/statement", response_model=StatementPage)
def get_statement(
    upi_id: str,
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    limit: int = Query(default=100, ge=1, le=upi_service.MAX_STATEMENT_LIMIT),
    cursor: str | None = None,
    consent_id: str | None = None,
    client: ApiClientModel = Depends(current_client),
    db: Session = Depends(get_db),
):
    return upi_service.get_statement(
        db, client, upi_id, consent_id=consent_id, date_from=date_from, date_to=date_to, limit=limit, cursor=cursor
    )


@router.post("/{upi_id}/transactions", response_model=TransactionRecord)
def post_transaction(
    upi_id: str,
    payload: UpiTransactionCreate,
    request: Request,
    client: ApiClientModel = Depends(current_client),
    key: str | None = Depends(idempotency_key),
    db: Session = Depends(get_db),
):
    return run_money_call(
        db, request, client, key, payload, payload.amount_cents,
        lambda: upi_service.post_transaction(db, client, upi_id, payload),
    )


@router.post("/{upi_id}/pay", response_model=TransactionRecord)
def pay(
    upi_id: str,
    payload: UpiPaymentCreate,
    request: Request,
    client: ApiClientModel = Depends(current_client),
    key: str | None = Depends(idempotency_key),
    db: Session = Depends(get_db),
):
    return run_money_call(
        db, request, client, key, payload, payload.amount_cents,
        lambda: upi_service.pay(db, client, upi_id, payload),
    )
