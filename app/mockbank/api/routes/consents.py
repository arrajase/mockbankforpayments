from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.mockbank.api.deps import current_client, current_customer, same_origin
from app.mockbank.db.database import get_db
from app.mockbank.db.models import ApiClientModel, CustomerModel
from app.mockbank.models.schemas import AppAccess, AppAccessUpdate, ConsentCreate, ConsentOut, PinApproval
from app.mockbank.services import consents as consents_service

gateway_router = APIRouter(prefix="/consents", tags=["gateway"])
website_router = APIRouter(prefix="/me/consents", tags=["website: app permissions"], dependencies=[Depends(same_origin)])
app_access_router = APIRouter(prefix="/me/app-access", tags=["website: app permissions"], dependencies=[Depends(same_origin)])


@gateway_router.post("", response_model=ConsentOut, status_code=201)
def create_consent(payload: ConsentCreate, client: ApiClientModel = Depends(current_client), db: Session = Depends(get_db)):
    return consents_service.create(db, client, payload)


@gateway_router.get("", response_model=list[ConsentOut])
def list_consents_for_client(
    upi_id: str | None = None,
    status: str | None = None,
    client: ApiClientModel = Depends(current_client),
    db: Session = Depends(get_db),
):
    """This client's consents, newest first, e.g. ?upi_id=someone@okmockbank&status=ACTIVE."""
    return consents_service.list_for_client(db, client, upi_id, status)


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


@app_access_router.get("", response_model=list[AppAccess])
def list_app_access(customer: CustomerModel = Depends(current_customer), db: Session = Depends(get_db)):
    return consents_service.app_access_for_customer(db, customer)


@app_access_router.put("", response_model=AppAccess)
def set_app_access(payload: AppAccessUpdate, customer: CustomerModel = Depends(current_customer), db: Session = Depends(get_db)):
    return consents_service.set_app_access(
        db, customer, payload.client_id, payload.upi_id, payload.purpose, payload.enabled, payload.upi_pin
    )
