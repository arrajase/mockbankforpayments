import bcrypt
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.mockbank.db.models import CustomerModel
from app.mockbank.models.schemas import LoginRequest, SignupRequest
from app.mockbank.utils.common import new_id


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def signup(db: Session, payload: SignupRequest) -> CustomerModel:
    existing = db.query(CustomerModel).filter(CustomerModel.login_id == payload.login_id).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="login id already taken")

    customer = CustomerModel(
        customer_id=new_id("cust"),
        first_name=payload.first_name,
        last_name=payload.last_name,
        login_id=payload.login_id,
        password_hash=_hash_password(payload.password),
    )
    db.add(customer)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="login id already taken")
    db.refresh(customer)
    return customer


def login(db: Session, payload: LoginRequest) -> CustomerModel:
    customer = db.query(CustomerModel).filter(CustomerModel.login_id == payload.login_id).first()
    if customer is None or not _verify_password(payload.password, customer.password_hash):
        raise HTTPException(status_code=401, detail="invalid login id or password")
    return customer


def get_customer(db: Session, customer_id: str) -> CustomerModel:
    customer = db.get(CustomerModel, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="customer not found")
    return customer
