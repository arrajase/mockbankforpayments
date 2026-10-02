from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.mockbank.api.routes.auth import require_api_key
from app.mockbank.db.database import get_db
from app.mockbank.models.schemas import UpiBalance, UpiPaymentCreate, UpiPaymentResult, UpiTransaction, UpiTransactionCreate
from app.mockbank.services import upi as upi_service

router = APIRouter(prefix="/upi", tags=["upi-gateway"], dependencies=[Depends(require_api_key)])


@router.get("/{upi_id}/balance", response_model=UpiBalance)
def get_balance(upi_id: str, db: Session = Depends(get_db)):
    return upi_service.get_balance_by_upi(db, upi_id)


@router.get("/{upi_id}/statement", response_model=list[UpiTransaction])
def get_statement(upi_id: str, db: Session = Depends(get_db)):
    return upi_service.get_statement_by_upi(db, upi_id)


@router.post("/{upi_id}/transactions", response_model=UpiTransaction)
def post_transaction(upi_id: str, payload: UpiTransactionCreate, db: Session = Depends(get_db)):
    return upi_service.post_transaction_by_upi(db, upi_id, payload)


@router.post("/{upi_id}/pay", response_model=UpiPaymentResult)
def pay(upi_id: str, payload: UpiPaymentCreate, db: Session = Depends(get_db)):
    return upi_service.pay_via_upi(db, upi_id, payload)
