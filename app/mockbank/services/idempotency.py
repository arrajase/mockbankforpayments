import json
from collections.abc import Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.mockbank.core.errors import BankError
from app.mockbank.db.models import IdempotencyKeyModel
from app.mockbank.utils.common import canonical_json, sha256_hex, utcnow

MAX_KEY_LENGTH = 255


def request_hash(method: str, path: str, body: dict) -> str:
    return sha256_hex(f"{method.upper()}\n{path}\n{canonical_json(body)}")


def run(
    db: Session,
    *,
    client_id: str,
    key: str | None,
    method: str,
    path: str,
    body: dict,
    operation: Callable[[], tuple[int, dict]],
) -> tuple[int, dict, bool]:
    """Run operation once per (client_id, key). Returns (status_code, body, replayed).

    operation must make its changes on db without committing. Its result and the key row are
    committed in the same transaction, so a retry can never repeat a money movement. If
    operation raises, nothing is stored and the error is passed through.
    """
    if not key:
        raise BankError("IDEMPOTENCY_KEY_REQUIRED", "the Idempotency-Key header is required")
    if len(key) > MAX_KEY_LENGTH:
        raise BankError("VALIDATION_ERROR", f"Idempotency-Key must be at most {MAX_KEY_LENGTH} characters")

    fingerprint = request_hash(method, path, body)
    stored = _replay(db, client_id, key, fingerprint)
    if stored is not None:
        return stored

    try:
        status_code, response = operation()
    except Exception:
        db.rollback()
        # A concurrent request with the same key may have committed meanwhile (we would then see
        # its client_reference as taken); answer with its stored response instead of the error.
        stored = _replay(db, client_id, key, fingerprint)
        if stored is not None:
            return stored
        raise

    db.add(
        IdempotencyKeyModel(
            client_id=client_id,
            key=key,
            request_hash=fingerprint,
            status_code=status_code,
            response_body=json.dumps(response),
            created_at=utcnow(),
        )
    )
    try:
        db.commit()
    except IntegrityError:
        # Either a concurrent request with the same key won the race, or client_reference is taken.
        db.rollback()
        stored = _replay(db, client_id, key, fingerprint)
        if stored is not None:
            return stored
        raise BankError("DUPLICATE_REFERENCE", "client_reference has already been used by this client")
    return status_code, response, False


def _replay(db: Session, client_id: str, key: str, fingerprint: str) -> tuple[int, dict, bool] | None:
    row = db.get(IdempotencyKeyModel, (client_id, key))
    if row is None:
        return None
    if row.request_hash != fingerprint:
        raise BankError("IDEMPOTENCY_KEY_REUSED", "this Idempotency-Key was already used with a different request")
    return row.status_code, json.loads(row.response_body), True
