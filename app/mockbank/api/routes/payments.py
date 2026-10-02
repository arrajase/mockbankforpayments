from fastapi import APIRouter, Depends

from app.mockbank.api.routes.auth import require_api_key
from app.mockbank.models.schemas import Payment, PaymentRequest
from app.mockbank.services import payments as payments_service

router = APIRouter(prefix="/payments", tags=["payments"], dependencies=[Depends(require_api_key)])


@router.post("", response_model=Payment)
def initiate_payment(payload: PaymentRequest):
    return payments_service.initiate_payment(payload)


@router.get("/{payment_id}", response_model=Payment)
def get_payment(payment_id: str):
    return payments_service.get_payment(payment_id)
