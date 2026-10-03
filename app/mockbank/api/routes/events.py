import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.mockbank.api.deps import current_client
from app.mockbank.core.errors import BankError
from app.mockbank.db.database import get_db
from app.mockbank.db.models import ApiClientModel, OutboxEventModel
from app.mockbank.models.schemas import EventPage

router = APIRouter(prefix="/events", tags=["gateway"])


@router.get("", response_model=EventPage)
def list_events(
    after: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    client: ApiClientModel = Depends(current_client),
    db: Session = Depends(get_db),
):
    """Poll for events in order, e.g. after a sleep or a missed webhook. Pass the last event_id you processed."""
    query = db.query(OutboxEventModel).filter(OutboxEventModel.client_id == client.client_id)
    if after:
        anchor = (
            db.query(OutboxEventModel)
            .filter(OutboxEventModel.event_id == after, OutboxEventModel.client_id == client.client_id)
            .one_or_none()
        )
        if anchor is None:
            raise BankError("NOT_FOUND", "unknown event_id in 'after'")
        query = query.filter(OutboxEventModel.seq > anchor.seq)
    events = query.order_by(OutboxEventModel.seq).limit(limit).all()
    return {"items": [json.loads(e.payload) for e in events]}
