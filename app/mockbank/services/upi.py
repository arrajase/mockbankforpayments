import base64
from datetime import date, datetime

from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.mockbank.core.errors import BankError
from app.mockbank.db.models import AccountModel, ApiClientModel, CustomerModel, TransactionHistoryModel, UpiModel
from app.mockbank.models.schemas import (
    UPI_SUFFIX,
    ConsentPurpose,
    UpiCreate,
    UpiPaymentCreate,
    UpiPinSet,
    UpiTransactionCreate,
    UpiUpdate,
)
from app.mockbank.services import clients as clients_service
from app.mockbank.services import collect as collect_service
from app.mockbank.services import consents as consents_service
from app.mockbank.services import ledger, pin
from app.mockbank.services import transactions as transactions_service
from app.mockbank.services.accounts import get_own_account
from app.mockbank.services.records import transaction_record

MAX_STATEMENT_LIMIT = 500


def _upi_out(upi: UpiModel) -> dict:
    return {
        "upi_id": upi.upi_id,
        "customer_id": upi.customer_id,
        "account_id": upi.account_id,
        "status": upi.status,
        "pin_set": upi.pin_hash is not None,
    }


def resolve_upi(db: Session, upi_id: str) -> UpiModel:
    upi = db.get(UpiModel, upi_id)
    if upi is None:
        raise BankError("UPI_NOT_FOUND", f"UPI ID {upi_id} not found")
    return upi


# ---------- website (customer from the session) ----------

def create_upi(db: Session, customer: CustomerModel, payload: UpiCreate) -> dict:
    get_own_account(db, customer, payload.account_id)
    upi_id = f"{payload.handle}{UPI_SUFFIX}"
    if db.get(UpiModel, upi_id) is not None:
        raise BankError("CONFLICT", "UPI ID already taken")

    upi = UpiModel(
        upi_id=upi_id,
        customer_id=customer.customer_id,
        account_id=payload.account_id,
        status="ACTIVE",
        pin_hash=pin.hash_pin(payload.upi_pin),
        pin_failed_attempts=0,
    )
    db.add(upi)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise BankError("CONFLICT", "UPI ID already taken")
    return _upi_out(upi)


def list_upis_for_customer(db: Session, customer: CustomerModel) -> list[dict]:
    upis = db.query(UpiModel).filter(UpiModel.customer_id == customer.customer_id).order_by(UpiModel.upi_id).all()
    return [_upi_out(u) for u in upis]


def _own_upi(db: Session, customer: CustomerModel, upi_id: str) -> UpiModel:
    upi = db.get(UpiModel, upi_id)
    if upi is None or upi.customer_id != customer.customer_id:
        raise BankError("NOT_FOUND", "UPI ID not found")
    return upi


def update_upi_account(db: Session, customer: CustomerModel, upi_id: str, payload: UpiUpdate) -> dict:
    upi = _own_upi(db, customer, upi_id)
    get_own_account(db, customer, payload.account_id)
    upi.account_id = payload.account_id
    db.commit()
    return _upi_out(upi)


def set_upi_pin(db: Session, customer: CustomerModel, upi_id: str, payload: UpiPinSet) -> dict:
    upi = _own_upi(db, customer, upi_id)
    if upi.pin_hash is not None:
        if not payload.current_pin:
            raise BankError("PIN_INVALID", "enter your current UPI PIN to change it")
        upi = pin.verify_pin(db, upi_id, payload.current_pin)
    upi.pin_hash = pin.hash_pin(payload.new_pin)
    upi.pin_failed_attempts = 0
    upi.pin_locked_until = None
    db.commit()
    return _upi_out(upi)


# ---------- gateway (API client) ----------

def verify_upi(db: Session, upi_id: str) -> dict:
    upi = resolve_upi(db, upi_id)
    account = db.get(AccountModel, upi.account_id)
    return {
        "upi_id": upi.upi_id,
        "account_holder_name": account.owner_name,
        "currency": account.currency,
        "status": upi.status,
    }


def get_balance(db: Session, client: ApiClientModel, upi_id: str, consent_id: str | None) -> dict:
    upi = resolve_upi(db, upi_id)
    consents_service.require_access(db, client, upi, ConsentPurpose.BALANCE, consent_id)
    account = db.get(AccountModel, upi.account_id)
    return {
        "upi_id": upi.upi_id,
        "owner_name": account.owner_name,
        "account_type": account.account_type,
        "balance_cents": account.balance_cents,
        "currency": account.currency,
    }


def _encode_cursor(leg: TransactionHistoryModel) -> str:
    raw = f"{leg.created_at.isoformat()}|{leg.transaction_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        created_at, transaction_id = base64.urlsafe_b64decode(padded.encode()).decode().split("|", 1)
        return datetime.fromisoformat(created_at), transaction_id
    except (ValueError, UnicodeDecodeError):
        raise BankError("VALIDATION_ERROR", "invalid cursor")


def get_statement(
    db: Session,
    client: ApiClientModel,
    upi_id: str,
    *,
    consent_id: str | None,
    date_from: date | None,
    date_to: date | None,
    limit: int,
    cursor: str | None,
) -> dict:
    """Successful postings on the UPI ID's linked account, newest first, paginated by cursor."""
    upi = resolve_upi(db, upi_id)
    date_from, date_to = consents_service.require_access(
        db, client, upi, ConsentPurpose.STATEMENT, consent_id, date_from, date_to
    )
    limit = max(1, min(limit, MAX_STATEMENT_LIMIT))

    T = TransactionHistoryModel
    query = db.query(T).filter(T.account_id == upi.account_id, T.status == "SUCCESS")
    if date_from:
        query = query.filter(T.tran_date >= date_from)
    if date_to:
        query = query.filter(T.tran_date <= date_to)
    if cursor:
        created_at, transaction_id = _decode_cursor(cursor)
        query = query.filter(or_(T.created_at < created_at, and_(T.created_at == created_at, T.transaction_id < transaction_id)))
    rows = query.order_by(T.created_at.desc(), T.transaction_id.desc()).limit(limit + 1).all()

    next_cursor = _encode_cursor(rows[limit - 1]) if len(rows) > limit else None
    return {
        "items": [transaction_record(r, viewer_client_id=client.client_id) for r in rows[:limit]],
        "next_cursor": next_cursor,
    }


def _check_reference_free(db: Session, client: ApiClientModel, client_reference: str) -> None:
    if transactions_service.reference_in_use(db, client.client_id, client_reference) or collect_service.reference_in_use(
        db, client.client_id, client_reference
    ):
        raise BankError("DUPLICATE_REFERENCE", "client_reference has already been used by this client")


def pay(db: Session, client: ApiClientModel, sender_upi_id: str, payload: UpiPaymentCreate) -> tuple[int, dict]:
    """Direct payment from one of the client's own UPI IDs. Does not commit."""
    sender = resolve_upi(db, sender_upi_id)
    clients_service.require_own_upi(client, sender)
    recipient = resolve_upi(db, payload.recipient_upi_id)
    _check_reference_free(db, client, payload.client_reference)

    leg = ledger.transfer(
        db,
        sender_upi=sender,
        recipient_upi=recipient,
        amount_cents=payload.amount_cents,
        currency=payload.currency.value,
        client_id=client.client_id,
        client_reference=payload.client_reference,
        narration=payload.narration,
    )
    return _outcome(leg, client)


def post_transaction(db: Session, client: ApiClientModel, upi_id: str, payload: UpiTransactionCreate) -> tuple[int, dict]:
    """Single-account posting on one of the client's own UPI IDs. Does not commit."""
    upi = resolve_upi(db, upi_id)
    clients_service.require_own_upi(client, upi)
    _check_reference_free(db, client, payload.client_reference)

    leg = ledger.post_single(
        db,
        account_id=upi.account_id,
        tran_type=payload.tran_type,
        amount_cents=payload.amount_cents,
        currency=payload.currency.value,
        upi_id=upi.upi_id,
        client_id=client.client_id,
        client_reference=payload.client_reference,
        narration=payload.narration,
        record_failure=True,
    )
    return _outcome(leg, client)


def _outcome(leg: TransactionHistoryModel, client: ApiClientModel) -> tuple[int, dict]:
    db_record = transaction_record(leg, viewer_client_id=client.client_id)
    if leg.status == "SUCCESS":
        return 200, db_record
    # A recorded failure: the error body also carries the transaction so it can be looked up later.
    return 422, {
        "error": {"code": leg.failure_reason, "message": "insufficient funds", "retryable": False},
        "transaction": db_record,
    }
