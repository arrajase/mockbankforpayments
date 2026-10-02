from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.mockbank.db.database import get_db
from app.mockbank.models.schemas import Upi, UpiCreate, UpiUpdate
from app.mockbank.services import upi as upi_service

router = APIRouter(prefix="/upi", tags=["upi"])


@router.post("", response_model=Upi)
def create_upi(payload: UpiCreate, db: Session = Depends(get_db)):
    return upi_service.create_upi(db, payload)


@router.get("", response_model=Upi)
def get_upi(customer_id: str, db: Session = Depends(get_db)):
    upi = upi_service.get_upi_for_customer(db, customer_id)
    if upi is None:
        raise HTTPException(status_code=404, detail="no UPI ID for this customer")
    return upi


@router.put("/{upi_id}", response_model=Upi)
def update_upi(upi_id: str, payload: UpiUpdate, db: Session = Depends(get_db)):
    return upi_service.update_upi_account(db, upi_id, payload)
