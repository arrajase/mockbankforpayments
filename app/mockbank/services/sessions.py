from datetime import timedelta

from sqlalchemy.orm import Session

from app.mockbank.core.config import SESSION_IDLE_MINUTES
from app.mockbank.db.models import CustomerModel, SessionModel
from app.mockbank.utils.common import random_token, sha256_hex, utcnow

IDLE_TIMEOUT = timedelta(minutes=SESSION_IDLE_MINUTES)


def create_session(db: Session, customer_id: str) -> str:
    """Returns the raw token for the cookie; only its hash is stored."""
    token = random_token(32)
    now = utcnow()
    db.add(SessionModel(token_hash=sha256_hex(token), customer_id=customer_id, created_at=now, last_seen_at=now))
    db.commit()
    return token


def customer_for_token(db: Session, token: str | None) -> CustomerModel | None:
    if not token:
        return None
    session = db.get(SessionModel, sha256_hex(token))
    if session is None:
        return None
    now = utcnow()
    if now - session.last_seen_at > IDLE_TIMEOUT:
        db.delete(session)
        db.commit()
        return None
    session.last_seen_at = now
    db.commit()
    return db.get(CustomerModel, session.customer_id)


def delete_session(db: Session, token: str | None) -> None:
    if not token:
        return
    session = db.get(SessionModel, sha256_hex(token))
    if session is not None:
        db.delete(session)
        db.commit()


def purge_idle_sessions(db: Session) -> int:
    cutoff = utcnow() - IDLE_TIMEOUT
    count = db.query(SessionModel).filter(SessionModel.last_seen_at < cutoff).delete(synchronize_session=False)
    db.commit()
    return count
