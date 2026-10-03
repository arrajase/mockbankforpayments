"""Collect requests: a client asks a customer for money; the customer approves with their UPI PIN."""

from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.mockbank.core.errors import BankError
from app.mockbank.db.models import AccountModel, ApiClientModel, CollectRequestModel, CustomerModel, UpiModel
from app.mockbank.models.schemas import CollectRequestCreate
from app.mockbank.services import clients as clients_service
from app.mockbank.services import events, ledger, pin
from app.mockbank.services import transactions as transactions_service
from app.mockbank.services.records import collect_record
from app.mockbank.utils.common import new_id, utcnow


def _resolve_upi(db: Session, upi_id: str) -> UpiModel:
    upi = db.get(UpiModel, upi_id)
    if upi is None:
        raise BankError("UPI_NOT_FOUND", f"UPI ID {upi_id} not found")
    return upi


def _payee_name(db: Session, collect: CollectRequestModel) -> str | None:
    upi = db.get(UpiModel, collect.payee_upi_id)
    account = db.get(AccountModel, upi.account_id) if upi else None
    return account.owner_name if account else None


def _set_status(db: Session, collect: CollectRequestModel, status: str, *, reason: str | None = None,
                transaction_id: str | None = None) -> None:
    collect.status = status
    collect.failure_reason = reason
    collect.transaction_id = transaction_id
    collect.updated_at = utcnow()
    client = db.get(ApiClientModel, collect.client_id)
    if client is not None:
        events.emit(db, client, "collect_request.updated", collect_record(collect, _payee_name(db, collect)))


def _expire_if_due(db: Session, collect: CollectRequestModel) -> None:
    if collect.status == "PENDING" and collect.expires_at <= utcnow():
        _set_status(db, collect, "EXPIRED")
        db.commit()


def expire_due(db: Session) -> int:
    due = (
        db.query(CollectRequestModel)
        .filter(CollectRequestModel.status == "PENDING", CollectRequestModel.expires_at <= utcnow())
        .with_for_update(skip_locked=True)
        .all()
    )
    for collect in due:
        _set_status(db, collect, "EXPIRED")
    db.commit()
    return len(due)


def reference_in_use(db: Session, client_id: str, client_reference: str) -> bool:
    return (
        db.query(CollectRequestModel.collect_id)
        .filter(CollectRequestModel.client_id == client_id, CollectRequestModel.client_reference == client_reference)
        .first()
        is not None
    )


# ---------- gateway ----------

def create(db: Session, client: ApiClientModel, payload: CollectRequestCreate, expire_immediately: bool = False) -> tuple[int, dict]:
    """Builds the request without committing (the idempotency wrapper commits)."""
    payee = _resolve_upi(db, payload.payee_upi_id)
    payer = _resolve_upi(db, payload.payer_upi_id)
    clients_service.require_own_upi(client, payee)
    if payer.upi_id == payee.upi_id:
        raise BankError("SAME_UPI", "payer and payee are the same UPI ID")
    for upi in (payer, payee):
        if upi.status != "ACTIVE":
            raise BankError("UPI_INACTIVE", f"UPI ID {upi.upi_id} is not active")
        account = db.get(AccountModel, upi.account_id)
        if account.currency != payload.currency.value:
            raise BankError("CURRENCY_MISMATCH", f"{upi.upi_id} holds {account.currency}, not {payload.currency.value}")
    if reference_in_use(db, client.client_id, payload.client_reference) or transactions_service.reference_in_use(
        db, client.client_id, payload.client_reference
    ):
        raise BankError("DUPLICATE_REFERENCE", "client_reference has already been used by this client")

    now = utcnow()
    collect = CollectRequestModel(
        collect_id=new_id("col"),
        client_id=client.client_id,
        payer_upi_id=payer.upi_id,
        payee_upi_id=payee.upi_id,
        amount_cents=payload.amount_cents,
        currency=payload.currency.value,
        client_reference=payload.client_reference,
        note=payload.note,
        status="PENDING",
        created_at=now,
        updated_at=now,
        expires_at=now if expire_immediately else now + timedelta(seconds=payload.expires_in_seconds),
    )
    db.add(collect)
    if expire_immediately:
        _set_status(db, collect, "EXPIRED")
    return 201, collect_record(collect, _payee_name(db, collect))


def get_for_client(db: Session, client: ApiClientModel, collect_id: str) -> dict:
    collect = db.get(CollectRequestModel, collect_id)
    if collect is None or collect.client_id != client.client_id:
        raise BankError("NOT_FOUND", "collect request not found")
    _expire_if_due(db, collect)
    return collect_record(collect, _payee_name(db, collect))


# ---------- website ----------

def list_pending_for_customer(db: Session, customer: CustomerModel) -> list[dict]:
    upi_ids = [u.upi_id for u in db.query(UpiModel).filter(UpiModel.customer_id == customer.customer_id)]
    if not upi_ids:
        return []
    pending = (
        db.query(CollectRequestModel)
        .filter(CollectRequestModel.payer_upi_id.in_(upi_ids), CollectRequestModel.status == "PENDING")
        .order_by(CollectRequestModel.created_at.desc())
        .all()
    )
    result = []
    for collect in pending:
        _expire_if_due(db, collect)
        if collect.status == "PENDING":
            result.append(collect_record(collect, _payee_name(db, collect)))
    return result


def _own_pending_locked(db: Session, customer: CustomerModel, collect_id: str) -> CollectRequestModel:
    collect = (
        db.query(CollectRequestModel)
        .filter(CollectRequestModel.collect_id == collect_id)
        .with_for_update()
        .populate_existing()
        .one_or_none()
    )
    payer = db.get(UpiModel, collect.payer_upi_id) if collect else None
    if collect is None or payer is None or payer.customer_id != customer.customer_id:
        raise BankError("NOT_FOUND", "collect request not found")
    _expire_if_due(db, collect)
    if collect.status == "EXPIRED":
        raise BankError("COLLECT_EXPIRED", "this collect request has expired")
    if collect.status != "PENDING":
        raise BankError("INVALID_STATE", f"collect request is {collect.status}")
    return collect


def approve(db: Session, customer: CustomerModel, collect_id: str, upi_pin: str) -> dict:
    collect = _own_pending_locked(db, customer, collect_id)
    pin.verify_pin(db, collect.payer_upi_id, upi_pin)

    try:
        leg = ledger.transfer(
            db,
            sender_upi=db.get(UpiModel, collect.payer_upi_id),
            recipient_upi=db.get(UpiModel, collect.payee_upi_id),
            amount_cents=collect.amount_cents,
            currency=collect.currency,
            client_id=collect.client_id,
            client_reference=collect.client_reference,
            narration=collect.note,
        )
        if leg.status == "SUCCESS":
            _set_status(db, collect, "SUCCESS", transaction_id=leg.transaction_id)
        else:
            _set_status(db, collect, "FAILED", reason=leg.failure_reason, transaction_id=leg.transaction_id)
        db.commit()
    except (BankError, IntegrityError) as exc:
        # The transfer could not be attempted (e.g. a linked account changed currency, or the
        # reference was taken by a direct payment). Record the failure; no money moved.
        db.rollback()
        reason = exc.code if isinstance(exc, BankError) else "DUPLICATE_REFERENCE"
        collect = db.query(CollectRequestModel).filter_by(collect_id=collect_id).with_for_update().populate_existing().one()
        _set_status(db, collect, "FAILED", reason=reason)
        db.commit()
    return collect_record(collect, _payee_name(db, collect))


def decline(db: Session, customer: CustomerModel, collect_id: str) -> dict:
    collect = _own_pending_locked(db, customer, collect_id)
    _set_status(db, collect, "DECLINED")
    db.commit()
    return collect_record(collect, _payee_name(db, collect))
