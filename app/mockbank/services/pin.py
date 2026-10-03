"""UPI PIN: set by the customer on the bank's website, never seen by API clients."""

from datetime import timedelta

import bcrypt
from sqlalchemy.orm import Session

from app.mockbank.core.errors import BankError
from app.mockbank.db.models import UpiModel
from app.mockbank.utils.common import utcnow

MAX_ATTEMPTS = 3
LOCKOUT = timedelta(hours=24)


def hash_pin(pin: str) -> str:
    return bcrypt.hashpw(pin.encode(), bcrypt.gensalt()).decode()


def verify_pin(db: Session, upi_id: str, pin: str) -> UpiModel:
    """Check a PIN, counting failures. A wrong PIN is committed (so the counter sticks) before raising.

    Locks the UPI row so parallel guesses can't race past the attempt counter. On success the
    row stays locked in the caller's open transaction.
    """
    upi = db.query(UpiModel).filter(UpiModel.upi_id == upi_id).with_for_update().populate_existing().one_or_none()
    if upi is None:
        raise BankError("UPI_NOT_FOUND", "UPI ID not found")
    if not upi.pin_hash:
        raise BankError("PIN_NOT_SET", "set a UPI PIN for this UPI ID first")

    now = utcnow()
    if upi.pin_locked_until is not None and upi.pin_locked_until > now:
        raise BankError("PIN_LOCKED", "too many wrong PINs; try again after 24 hours")

    if bcrypt.checkpw(pin.encode(), upi.pin_hash.encode()):
        upi.pin_failed_attempts = 0
        upi.pin_locked_until = None
        return upi

    upi.pin_failed_attempts += 1
    if upi.pin_failed_attempts >= MAX_ATTEMPTS:
        upi.pin_failed_attempts = 0
        upi.pin_locked_until = now + LOCKOUT
        db.commit()
        raise BankError("PIN_LOCKED", "too many wrong PINs; UPI PIN locked for 24 hours")
    remaining = MAX_ATTEMPTS - upi.pin_failed_attempts
    db.commit()
    raise BankError("PIN_INVALID", f"incorrect UPI PIN; {remaining} attempt(s) left")
