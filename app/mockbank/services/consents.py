"""Consents: a customer lets an API client link a UPI ID and/or read its balance or statement."""

from datetime import date, timedelta, timezone

from sqlalchemy.orm import Session

from app.mockbank.core.config import CONSENT_TOGGLE_DAYS
from app.mockbank.core.errors import BankError
from app.mockbank.db.models import ApiClientModel, ConsentModel, CustomerModel, UpiModel
from app.mockbank.models.schemas import ConsentCreate, ConsentPurpose
from app.mockbank.services import clients as clients_service
from app.mockbank.services import events, pin
from app.mockbank.services.records import consent_record
from app.mockbank.utils.common import iso_utc, new_id, utcnow

LIVE_STATUSES = ("PENDING", "ACTIVE")
# A Statement toggle on the profile page covers this much history, up to the consent's expiry.
TOGGLE_STATEMENT_HISTORY = timedelta(days=365)


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


def _covers(consent: ConsentModel, purpose: ConsentPurpose, date_from: date | None, date_to: date | None) -> bool:
    if purpose.value not in consent.purposes.split(","):
        return False
    if purpose == ConsentPurpose.STATEMENT:
        date_from = date_from or consent.statement_from
        date_to = date_to or consent.statement_to
        return consent.statement_from <= date_from and date_to <= consent.statement_to
    return True


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

    Without consent_id, any ACTIVE consent this client holds for the UPI ID that covers the
    purpose (and dates) is used. Returns the statement date range to use: for consent-based
    statements, missing bounds default to the consented range.
    """
    if clients_service.owns_upi(client, upi):
        return date_from, date_to

    if consent_id:
        consent = db.get(ConsentModel, consent_id)
        if consent is None or consent.client_id != client.client_id or consent.upi_id != upi.upi_id:
            raise BankError("CONSENT_REQUIRED", "consent not found for this UPI ID")
        _expire_if_due(db, consent)
        if consent.status != "ACTIVE":
            raise BankError("CONSENT_REQUIRED", f"consent is {consent.status}")
        if purpose.value not in consent.purposes.split(","):
            raise BankError("CONSENT_REQUIRED", f"consent does not cover {purpose.value}")
        if not _covers(consent, purpose, date_from, date_to):
            raise BankError("CONSENT_REQUIRED", f"consent covers {consent.statement_from} to {consent.statement_to} only")
    else:
        candidates = (
            db.query(ConsentModel)
            .filter(
                ConsentModel.client_id == client.client_id,
                ConsentModel.upi_id == upi.upi_id,
                ConsentModel.status == "ACTIVE",
                ConsentModel.expires_at > utcnow(),
            )
            .order_by(ConsentModel.created_at.desc())
            .all()
        )
        consent = next((c for c in candidates if _covers(c, purpose, date_from, date_to)), None)
        if consent is None:
            raise BankError("CONSENT_REQUIRED", f"no active consent covers {purpose.value} for {upi.upi_id}")

    if purpose == ConsentPurpose.STATEMENT:
        date_from = date_from or consent.statement_from
        date_to = date_to or consent.statement_to
    return date_from, date_to


def list_for_client(db: Session, client: ApiClientModel, upi_id: str | None, status: str | None) -> list[dict]:
    query = db.query(ConsentModel).filter(ConsentModel.client_id == client.client_id)
    if upi_id:
        query = query.filter(ConsentModel.upi_id == upi_id)
    consents = query.order_by(ConsentModel.created_at.desc()).all()
    for consent in consents:
        _expire_if_due(db, consent)
    return [consent_record(c, client.name) for c in consents if status is None or c.status == status]


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


# ---------- website: profile page toggles ----------

def _active_for(db: Session, client_id: str, upi_id: str, lock: bool = False) -> list[ConsentModel]:
    query = db.query(ConsentModel).filter(
        ConsentModel.client_id == client_id,
        ConsentModel.upi_id == upi_id,
        ConsentModel.status == "ACTIVE",
        ConsentModel.expires_at > utcnow(),
    )
    if lock:
        query = query.with_for_update().populate_existing()
    return query.all()


def app_access_for_customer(db: Session, customer: CustomerModel) -> list[dict]:
    """One row per (app, UPI ID): which purposes are switched on, and until when."""
    upis = db.query(UpiModel).filter(UpiModel.customer_id == customer.customer_id).order_by(UpiModel.upi_id).all()
    apps = (
        db.query(ApiClientModel)
        .filter(ApiClientModel.active.is_(True), ApiClientModel.owner_customer_id != customer.customer_id)
        .order_by(ApiClientModel.name)
        .all()
    )
    rows = []
    for app in apps:
        for upi in upis:
            until = {}
            for consent in _active_for(db, app.client_id, upi.upi_id):
                for purpose in consent.purposes.split(","):
                    if purpose not in until or consent.expires_at > until[purpose]:
                        until[purpose] = consent.expires_at
            rows.append({
                "client_id": app.client_id,
                "client_name": app.name,
                "upi_id": upi.upi_id,
                "purposes": {
                    p.value: {"enabled": p.value in until, "expires_at": iso_utc(until.get(p.value))}
                    for p in ConsentPurpose
                },
            })
    return rows


def set_app_access(db: Session, customer: CustomerModel, client_id: str, upi_id: str, purpose: ConsentPurpose,
                   enabled: bool, upi_pin: str | None) -> dict:
    """Profile-page toggle. On: an ACTIVE consent for CONSENT_TOGGLE_DAYS (needs the UPI PIN).
    Off: the purpose is removed from this app's active consents for the UPI ID."""
    upi = db.get(UpiModel, upi_id)
    if upi is None or upi.customer_id != customer.customer_id:
        raise BankError("NOT_FOUND", "UPI ID not found")
    app = db.get(ApiClientModel, client_id)
    if app is None or not app.active or app.owner_customer_id == customer.customer_id:
        raise BankError("NOT_FOUND", "app not found")

    if enabled:
        if not upi_pin:
            raise BankError("PIN_INVALID", "enter your UPI PIN to give an app access")
        pin.verify_pin(db, upi_id, upi_pin)
        now = utcnow()
        expires_at = now + timedelta(days=CONSENT_TOGGLE_DAYS)
        is_statement = purpose == ConsentPurpose.STATEMENT
        consent = ConsentModel(
            consent_id=new_id("cns"),
            client_id=app.client_id,
            upi_id=upi_id,
            purposes=purpose.value,
            statement_from=(now - TOGGLE_STATEMENT_HISTORY).date() if is_statement else None,
            statement_to=expires_at.date() if is_statement else None,
            status="PENDING",
            created_at=now,
            updated_at=now,
            expires_at=expires_at,
        )
        db.add(consent)
        _set_status(db, consent, "ACTIVE")
    else:
        for consent in _active_for(db, app.client_id, upi_id, lock=True):
            purposes = consent.purposes.split(",")
            if purpose.value not in purposes:
                continue
            remaining = [p for p in purposes if p != purpose.value]
            if remaining:
                consent.purposes = ",".join(remaining)
                _set_status(db, consent, "ACTIVE")  # tells the app its access shrank
            else:
                _set_status(db, consent, "REVOKED")
    db.commit()
    return next(r for r in app_access_for_customer(db, customer) if r["client_id"] == client_id and r["upi_id"] == upi_id)
