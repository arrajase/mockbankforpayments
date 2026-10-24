from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.mockbank.api.deps import current_customer, same_origin
from app.mockbank.db.database import get_db
from app.mockbank.db.models import CustomerModel
from app.mockbank.models.schemas import (
    ApiClientCreate,
    ApiClientCreated,
    ApiClientOut,
    ApiClientUpdate,
    ApiKeyRotated,
    WebhookSecret,
)
from app.mockbank.services import clients as clients_service

router = APIRouter(prefix="/me/api-clients", tags=["website: developer"], dependencies=[Depends(same_origin)])


@router.get("", response_model=list[ApiClientOut])
def list_clients(customer: CustomerModel = Depends(current_customer), db: Session = Depends(get_db)):
    return clients_service.list_owned(db, customer)


@router.post("", response_model=ApiClientCreated, status_code=201)
def create_client(payload: ApiClientCreate, customer: CustomerModel = Depends(current_customer), db: Session = Depends(get_db)):
    """Register an app. The API key is in this response only; the bank keeps just its hash."""
    return clients_service.create_owned(db, customer, payload.name, payload.webhook_url)


@router.put("/{client_id}", response_model=ApiClientOut)
def update_client(client_id: str, payload: ApiClientUpdate, customer: CustomerModel = Depends(current_customer),
                  db: Session = Depends(get_db)):
    changes = {}
    if "webhook_url" in payload.model_fields_set:
        changes["webhook_url"] = payload.webhook_url
    if payload.active is not None:
        changes["active"] = payload.active
    return clients_service.update_owned(db, customer, client_id, **changes)


@router.post("/{client_id}/rotate-key", response_model=ApiKeyRotated)
def rotate_key(client_id: str, customer: CustomerModel = Depends(current_customer), db: Session = Depends(get_db)):
    return clients_service.rotate_key(db, customer, client_id)


@router.get("/{client_id}/webhook-secret", response_model=WebhookSecret)
def get_webhook_secret(client_id: str, customer: CustomerModel = Depends(current_customer), db: Session = Depends(get_db)):
    return clients_service.webhook_secret(db, customer, client_id)


@router.post("/{client_id}/rotate-webhook-secret", response_model=WebhookSecret)
def rotate_webhook_secret(client_id: str, customer: CustomerModel = Depends(current_customer), db: Session = Depends(get_db)):
    return clients_service.rotate_webhook_secret(db, customer, client_id)
