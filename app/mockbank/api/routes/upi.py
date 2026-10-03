from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.mockbank.api.deps import current_customer, same_origin
from app.mockbank.db.database import get_db
from app.mockbank.db.models import CustomerModel
from app.mockbank.models.schemas import Upi, UpiCreate, UpiPinSet, UpiUpdate
from app.mockbank.services import upi as upi_service

router = APIRouter(prefix="/upi", tags=["website: upi"], dependencies=[Depends(same_origin)])


@router.post("", response_model=Upi)
def create_upi(payload: UpiCreate, customer: CustomerModel = Depends(current_customer), db: Session = Depends(get_db)):
    return upi_service.create_upi(db, customer, payload)


@router.get("", response_model=list[Upi])
def list_upis(customer: CustomerModel = Depends(current_customer), db: Session = Depends(get_db)):
    return upi_service.list_upis_for_customer(db, customer)


@router.put("/{upi_id}", response_model=Upi)
def update_upi(upi_id: str, payload: UpiUpdate, customer: CustomerModel = Depends(current_customer), db: Session = Depends(get_db)):
    return upi_service.update_upi_account(db, customer, upi_id, payload)


@router.put("/{upi_id}/pin", response_model=Upi)
def set_pin(upi_id: str, payload: UpiPinSet, customer: CustomerModel = Depends(current_customer), db: Session = Depends(get_db)):
    return upi_service.set_upi_pin(db, customer, upi_id, payload)
