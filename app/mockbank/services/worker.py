"""Background loop: webhook delivery, expiry sweeps and housekeeping.

Render's free tier sleeps idle services, which stops this loop; clients should also poll
GET /events?after=<event_id> to pick up anything they missed.
"""

import asyncio
import logging
from datetime import timedelta

from app.mockbank.core.config import IDEMPOTENCY_RETENTION_DAYS, WORKER_INTERVAL_SECONDS
from app.mockbank.db.database import SessionLocal
from app.mockbank.db.models import IdempotencyKeyModel
from app.mockbank.services import collect, consents, events, sessions
from app.mockbank.utils.common import utcnow

log = logging.getLogger("mockbank.worker")


def run_once() -> None:
    db = SessionLocal()
    try:
        collect.expire_due(db)
        consents.expire_due(db)
        events.deliver_due_events(db)
        cutoff = utcnow() - timedelta(days=IDEMPOTENCY_RETENTION_DAYS)
        db.query(IdempotencyKeyModel).filter(IdempotencyKeyModel.created_at < cutoff).delete(synchronize_session=False)
        db.commit()
        sessions.purge_idle_sessions(db)
    finally:
        db.close()


async def run_forever() -> None:
    while True:
        try:
            await asyncio.to_thread(run_once)
        except Exception:
            log.exception("worker pass failed")
        await asyncio.sleep(WORKER_INTERVAL_SECONDS)
