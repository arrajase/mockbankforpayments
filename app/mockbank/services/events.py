"""Outbox events and signed webhook delivery.

Events are written to outbox_events in the same database transaction as the change they describe,
so an event exists if and only if the change committed. A background loop delivers them
(at least once); clients de-duplicate on event_id and can poll GET /events to catch up.
"""

import hashlib
import hmac
import json
import time
from datetime import timedelta

import httpx
from sqlalchemy.orm import Session

from app.mockbank.db.models import AccountModel, ApiClientModel, OutboxEventModel, TransactionHistoryModel
from app.mockbank.services.records import transaction_record
from app.mockbank.utils.common import iso_utc, new_id, utcnow

RETRY_DELAYS_SECONDS = [60, 5 * 60, 30 * 60, 2 * 60 * 60]
GIVE_UP_AFTER = timedelta(hours=24)
DELIVERY_TIMEOUT_SECONDS = 10


def sign(secret: str, timestamp: int, raw_body: str) -> str:
    return hmac.new(secret.encode(), f"{timestamp}.{raw_body}".encode(), hashlib.sha256).hexdigest()


def signature_header(secret: str, raw_body: str, timestamp: int | None = None) -> str:
    timestamp = int(time.time()) if timestamp is None else timestamp
    return f"t={timestamp},v1={sign(secret, timestamp, raw_body)}"


def emit(db: Session, client: ApiClientModel, event_type: str, data: dict) -> OutboxEventModel:
    """Add an event to the outbox. The caller commits it together with the change it describes."""
    now = utcnow()
    event_id = new_id("evt")
    payload = json.dumps({"event_id": event_id, "type": event_type, "created_at": iso_utc(now), "data": data})
    event = OutboxEventModel(
        event_id=event_id,
        client_id=client.client_id,
        type=event_type,
        payload=payload,
        created_at=now,
        delivery_status="PENDING" if client.webhook_url else "NO_ENDPOINT",
        attempts=0,
        next_attempt_at=now if client.webhook_url else None,
    )
    db.add(event)
    return event


def emit_transaction_posted(db: Session, legs: list[TransactionHistoryModel], accounts: dict[str, AccountModel]) -> None:
    """transaction.posted goes to every active client that owns an account a leg touched,
    including movements that client did not make."""
    owner_ids = {accounts[leg.account_id].customer_id for leg in legs if leg.account_id in accounts}
    if not owner_ids:
        return
    clients = (
        db.query(ApiClientModel)
        .filter(ApiClientModel.owner_customer_id.in_(owner_ids), ApiClientModel.active.is_(True))
        .all()
    )
    for leg in legs:
        account = accounts.get(leg.account_id)
        if account is None or leg.status != "SUCCESS":
            continue
        for client in clients:
            if client.owner_customer_id == account.customer_id:
                emit(db, client, "transaction.posted", transaction_record(leg, viewer_client_id=client.client_id))


def _next_attempt(event: OutboxEventModel, now):
    index = min(event.attempts - 1, len(RETRY_DELAYS_SECONDS) - 1)
    candidate = now + timedelta(seconds=RETRY_DELAYS_SECONDS[index])
    if candidate - event.created_at > GIVE_UP_AFTER:
        return None
    return candidate


def deliver_due_events(db: Session, limit: int = 50, http: httpx.Client | None = None) -> int:
    """One delivery pass. Returns the number of events attempted."""
    now = utcnow()
    events = (
        db.query(OutboxEventModel)
        .filter(OutboxEventModel.delivery_status == "PENDING", OutboxEventModel.next_attempt_at <= now)
        .order_by(OutboxEventModel.seq)
        .limit(limit)
        .with_for_update(skip_locked=True)
        .all()
    )
    if not events:
        return 0

    client_ids = {e.client_id for e in events}
    clients = {c.client_id: c for c in db.query(ApiClientModel).filter(ApiClientModel.client_id.in_(client_ids))}
    own_http = http is None
    http = http or httpx.Client(timeout=DELIVERY_TIMEOUT_SECONDS)
    try:
        for event in events:
            client = clients.get(event.client_id)
            if client is None or not client.active or not client.webhook_url:
                event.delivery_status = "NO_ENDPOINT"
                event.next_attempt_at = None
                continue
            event.attempts += 1
            try:
                response = http.post(
                    client.webhook_url,
                    content=event.payload,
                    headers={
                        "Content-Type": "application/json",
                        "X-MockBank-Event-Id": event.event_id,
                        "X-MockBank-Signature": signature_header(client.webhook_secret, event.payload),
                    },
                )
                ok = 200 <= response.status_code < 300
                error = None if ok else f"HTTP {response.status_code}"
            except httpx.HTTPError as exc:
                ok, error = False, f"{type(exc).__name__}: {exc}"[:500]

            attempted_at = utcnow()
            if ok:
                event.delivery_status = "DELIVERED"
                event.delivered_at = attempted_at
                event.next_attempt_at = None
                event.last_error = None
            else:
                event.last_error = error
                event.next_attempt_at = _next_attempt(event, attempted_at)
                if event.next_attempt_at is None:
                    event.delivery_status = "FAILED"
        db.commit()
    finally:
        if own_http:
            http.close()
    return len(events)
