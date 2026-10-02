from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.mockbank.db.database import get_db
from app.mockbank.models.schemas import CustomerOut, LoginRequest, LoginResponse, SignupRequest
from app.mockbank.services import auth as auth_service

router = APIRouter(tags=["auth"])


@router.post("/auth/signup", response_model=CustomerOut)
def signup(payload: SignupRequest, db: Session = Depends(get_db)):
    customer = auth_service.signup(db, payload)
    return CustomerOut.model_validate(customer)


@router.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    customer = auth_service.login(db, payload)
    return LoginResponse.model_validate(customer)


@router.get("/customers/{customer_id}", response_model=CustomerOut)
def get_customer(customer_id: str, db: Session = Depends(get_db)):
    customer = auth_service.get_customer(db, customer_id)
    return CustomerOut.model_validate(customer)
