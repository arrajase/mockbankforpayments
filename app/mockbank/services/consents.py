"""Consents: a customer lets an API client link a UPI ID and/or read its balance or statement."""

from datetime import date, timezone

from sqlalchemy.orm import Session

from app.mockbank.core.errors import BankError
from app.mockbank.db.models import ApiClientModel, ConsentModel, CustomerModel, UpiModel
from app.mockbank.models.schemas import ConsentCreate, ConsentPurpose
from app.mockbank.services import clients as clients_service
from app.mockbank.services import events, pin
from app.mockbank.services.records import consent_record
from app.mockbank.utils.common import new_id, utcnow

LIVE_STATUSES = ("PENDING", "ACTIVE")


def _set_status(db: Session, consent: ConsentModel, status: str) -> None:
    consent.status = status
    consent.updated_at = utcnow()
    client = db.get(ApiClientModel, consent.client_id)
    if client is not None:
        events.emit(db, client, "consent.updated", consent_record(consent, client.name))


def _expire_if_due(db: Session, consent: ConsentModel) -> None:
    if consent.status in LIVE_STATUSES and consent.expires_at <= utcnow():
        _set_status(db, consent, "EXPIRED")
        db.commit()


def expire_due(db: Session) -> int:
    due = (
        db.query(ConsentModel)
        .filter(ConsentModel.status.in_(LIVE_STATUSES), ConsentModel.expires_at <= utcnow())
        .with_for_update(skip_locked=True)
        .all()
    )
    for consent in due:
        _set_status(db, consent, "EXPIRED")
    db.commit()
    return len(due)


# ---------- gateway ----------

def create(db: Session, client: ApiClientModel, payload: ConsentCreate) -> dict:
    if db.get(UpiModel, payload.upi_id) is None:
        raise BankError("UPI_NOT_FOUND", "UPI ID not found")
    expires_at = payload.expires_at
    if expires_at.tzinfo is not None:
        expires_at = expires_at.astimezone(timezone.utc).replace(tzinfo=None)
    now = utcnow()
    if expires_at <= now:
        raise BankError("VALIDATION_ERROR", "expires_at must be in the future")

    consent = ConsentModel(
        consent_id=new_id("cns"),
        client_id=client.client_id,
        upi_id=payload.upi_id,
        purposes=",".join(sorted({p.value for p in payload.purposes})),
        statement_from=payload.statement_from,
        statement_to=payload.statement_to,
        status="PENDING",
        created_at=now,
        updated_at=now,
        expires_at=expires_at,
    )
    db.add(consent)
    db.commit()
    return consent_record(consent, client.name)


def get_for_client(db: Session, client: ApiClientModel, consent_id: str) -> dict:
    consent = db.get(ConsentModel, consent_id)
    if consent is None or consent.client_id != client.client_id:
        raise BankError("NOT_FOUND", "consent not found")
    _expire_if_due(db, consent)
    return consent_record(consent, client.name)


def require_access(
    db: Session,
    client: ApiClientModel,
    upi: UpiModel,
    purpose: ConsentPurpose,
    consent_id: str | None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> tuple[date | None, date | None]:
    """Allow reads of the client's own UPI IDs, or of a customer's UPI ID under an ACTIVE consent.

    Returns the statement date range to use: for consent-based statements, missing bounds
    default to the consented range.
    """
    if clients_service.owns_upi(client, upi):
        return date_from, date_to
    if not consent_id:
        raise BankError("CONSENT_REQUIRED", f"a consent_id with purpose {purpose.value} is required for {upi.upi_id}")

    consent = db.get(ConsentModel, consent_id)
    if consent is None or consent.client_id != client.client_id or consent.upi_id != upi.upi_id:
        raise BankError("CONSENT_REQUIRED", "consent not found for this UPI ID")
    _expire_if_due(db, consent)
    if consent.status != "ACTIVE":
        raise BankError("CONSENT_REQUIRED", f"consent is {consent.status}")
    if purpose.value not in consent.purposes.split(","):
        raise BankError("CONSENT_REQUIRED", f"consent does not cover {purpose.value}")

    if purpose == ConsentPurpose.STATEMENT:
        date_from = date_from or consent.statement_from
        date_to = date_to or consent.statement_to
        if date_from < consent.statement_from or date_to > consent.statement_to:
            raise BankError(
                "CONSENT_REQUIRED",
                f"consent covers {consent.statement_from} to {consent.statement_to} only",
            )
    return date_from, date_to


# ---------- website ----------

def list_for_customer(db: Session, customer: CustomerModel) -> list[dict]:
    upi_ids = [u.upi_id for u in db.query(UpiModel).filter(UpiModel.customer_id == customer.customer_id)]
    if not upi_ids:
        return []
    consents = (
        db.query(ConsentModel)
        .filter(ConsentModel.upi_id.in_(upi_ids))
        .order_by(ConsentModel.created_at.desc())
        .all()
    )
    for consent in consents:
        _expire_if_due(db, consent)
    names = {c.client_id: c.name for c in db.query(ApiClientModel)}
    return [consent_record(c, names.get(c.client_id)) for c in consents]


def _own_consent_locked(db: Session, customer: CustomerModel, consent_id: str) -> ConsentModel:
    consent = (
        db.query(ConsentModel)
        .filter(ConsentModel.consent_id == consent_id)
        .with_for_update()
        .populate_existing()
        .one_or_none()
    )
    upi = db.get(UpiModel, consent.upi_id) if consent else None
    if consent is None or upi is None or upi.customer_id != customer.customer_id:
        raise BankError("NOT_FOUND", "consent not found")
    _expire_if_due(db, consent)
    return consent


def approve(db: Session, customer: CustomerModel, consent_id: str, upi_pin: str) -> dict:
    consent = _own_consent_locked(db, customer, consent_id)
    if consent.status != "PENDING":
        raise BankError("INVALID_STATE", f"consent is {consent.status}")
    pin.verify_pin(db, consent.upi_id, upi_pin)
    _set_status(db, consent, "ACTIVE")
    db.commit()
    return consent_record(consent)


def reject(db: Session, customer: CustomerModel, consent_id: str) -> dict:
    consent = _own_consent_locked(db, customer, consent_id)
    if consent.status != "PENDING":
        raise BankError("INVALID_STATE", f"consent is {consent.status}")
    _set_status(db, consent, "REJECTED")
    db.commit()
    return consent_record(consent)


def revoke(db: Session, customer: CustomerModel, consent_id: str) -> dict:
    consent = _own_consent_locked(db, customer, consent_id)
    if consent.status != "ACTIVE":
        raise BankError("INVALID_STATE", f"consent is {consent.status}")
    _set_status(db, consent, "REVOKED")
    db.commit()
    return consent_record(consent)
