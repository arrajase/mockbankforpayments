from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.mockbank.api.deps import current_client, current_customer, idempotency_key, same_origin
from app.mockbank.api.routes.money import run_money_call
from app.mockbank.db.database import get_db
from app.mockbank.db.models import ApiClientModel, CustomerModel
from app.mockbank.models.schemas import CollectRequestCreate, CollectRequestOut, PinApproval
from app.mockbank.services import collect as collect_service
from app.mockbank.services import sandbox

gateway_router = APIRouter(prefix="/collect-requests", tags=["gateway"])
website_router = APIRouter(prefix="/me/collect-requests", tags=["website: collect requests"], dependencies=[Depends(same_origin)])


@gateway_router.post("", response_model=CollectRequestOut, status_code=201)
def create_collect_request(
    payload: CollectRequestCreate,
    request: Request,
    client: ApiClientModel = Depends(current_client),
    key: str | None = Depends(idempotency_key),
    db: Session = Depends(get_db),
):
    expire_now = sandbox.trigger_for(payload.amount_cents) == sandbox.COLLECT_EXPIRES
    return run_money_call(
        db, request, client, key, payload, payload.amount_cents,
        lambda: collect_service.create(db, client, payload, expire_immediately=expire_now),
    )


@gateway_router.get("/{collect_id}", response_model=CollectRequestOut)
def get_collect_request(collect_id: str, client: ApiClientModel = Depends(current_client), db: Session = Depends(get_db)):
    return collect_service.get_for_client(db, client, collect_id)


@website_router.get("", response_model=list[CollectRequestOut])
def list_pending(customer: CustomerModel = Depends(current_customer), db: Session = Depends(get_db)):
    return collect_service.list_pending_for_customer(db, customer)


@website_router.post("/{collect_id}/approve", response_model=CollectRequestOut)
def approve(collect_id: str, payload: PinApproval, customer: CustomerModel = Depends(current_customer), db: Session = Depends(get_db)):
    return collect_service.approve(db, customer, collect_id, payload.upi_pin)


@website_router.post("/{collect_id}/decline", response_model=CollectRequestOut)
def decline(collect_id: str, customer: CustomerModel = Depends(current_customer), db: Session = Depends(get_db)):
    return collect_service.decline(db, customer, collect_id)
