import httpx
from fastapi import HTTPException

from app.mockbank.db.store import accounts, payments
from app.mockbank.models.schemas import Payment, PaymentRequest, PaymentStatus
from app.mockbank.utils.common import new_id


def initiate_payment(payload: PaymentRequest) -> Payment:
    from_account = accounts.get(payload.from_account_id)
    to_account = accounts.get(payload.to_account_id)
    if from_account is None or to_account is None:
        raise HTTPException(status_code=404, detail="account not found")

    payment = Payment(
        payment_id=new_id("pay"),
        from_account_id=payload.from_account_id,
        to_account_id=payload.to_account_id,
        amount_cents=payload.amount_cents,
        currency=payload.currency,
        status=PaymentStatus.PENDING,
    )

    if from_account.balance_cents < payload.amount_cents:
        payment.status = PaymentStatus.FAILED
    else:
        from_account.balance_cents -= payload.amount_cents
        to_account.balance_cents += payload.amount_cents
        payment.status = PaymentStatus.SETTLED

    payments[payment.payment_id] = payment

    if payload.webhook_url:
        _notify_webhook(payload.webhook_url, payment)

    return payment


def get_payment(payment_id: str) -> Payment:
    payment = payments.get(payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="payment not found")
    return payment


def _notify_webhook(webhook_url: str, payment: Payment) -> None:
    try:
        httpx.post(webhook_url, json=payment.model_dump(), timeout=5.0)
    except httpx.HTTPError:
        pass
