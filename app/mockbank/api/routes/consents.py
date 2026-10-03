from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.mockbank.api.deps import current_client, current_customer, same_origin
from app.mockbank.db.database import get_db
from app.mockbank.db.models import ApiClientModel, CustomerModel
from app.mockbank.models.schemas import ConsentCreate, ConsentOut, PinApproval
from app.mockbank.services import consents as consents_service

gateway_router = APIRouter(prefix="/consents", tags=["gateway"])
website_router = APIRouter(prefix="/me/consents", tags=["website: app permissions"], dependencies=[Depends(same_origin)])


@gateway_router.post("", response_model=ConsentOut, status_code=201)
def create_consent(payload: ConsentCreate, client: ApiClientModel = Depends(current_client), db: Session = Depends(get_db)):
    return consents_service.create(db, client, payload)


@gateway_router.get("/{consent_id}", response_model=ConsentOut)
def get_consent(consent_id: str, client: ApiClientModel = Depends(current_client), db: Session = Depends(get_db)):
    return consents_service.get_for_client(db, client, consent_id)


@website_router.get("", response_model=list[ConsentOut])
def list_consents(customer: CustomerModel = Depends(current_customer), db: Session = Depends(get_db)):
    return consents_service.list_for_customer(db, customer)


@website_router.post("/{consent_id}/approve", response_model=ConsentOut)
def approve(consent_id: str, payload: PinApproval, customer: CustomerModel = Depends(current_customer), db: Session = Depends(get_db)):
    return consents_service.approve(db, customer, consent_id, payload.upi_pin)


@website_router.post("/{consent_id}/reject", response_model=ConsentOut)
def reject(consent_id: str, customer: CustomerModel = Depends(current_customer), db: Session = Depends(get_db)):
    return consents_service.reject(db, customer, consent_id)


@website_router.post("/{consent_id}/revoke", response_model=ConsentOut)
def revoke(consent_id: str, customer: CustomerModel = Depends(current_customer), db: Session = Depends(get_db)):
    return consents_service.revoke(db, customer, consent_id)
