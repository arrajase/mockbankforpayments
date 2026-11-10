import bcrypt
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.mockbank.core.errors import BankError
from app.mockbank.db.models import CustomerModel, SessionModel
from app.mockbank.models.schemas import LoginRequest, MobileUpdate, PasswordReset, SignupRequest
from app.mockbank.utils.common import new_id, sha256_hex


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def _mobile_taken(db: Session, mobile_number: str, customer_id: str | None = None) -> bool:
    query = db.query(CustomerModel).filter(CustomerModel.mobile_number == mobile_number)
    if customer_id is not None:
        query = query.filter(CustomerModel.customer_id != customer_id)
    return query.first() is not None


def signup(db: Session, payload: SignupRequest) -> CustomerModel:
    existing = db.query(CustomerModel).filter(CustomerModel.login_id == payload.login_id).first()
    if existing is not None:
        raise BankError("CONFLICT", "login id already taken")
    if _mobile_taken(db, payload.mobile_number):
        raise BankError("CONFLICT", "mobile number is already registered")

    customer = CustomerModel(
        customer_id=new_id("cust"),
        first_name=payload.first_name,
        last_name=payload.last_name,
        login_id=payload.login_id,
        mobile_number=payload.mobile_number,
        password_hash=_hash_password(payload.password),
    )
    db.add(customer)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise BankError("CONFLICT", "login id or mobile number already registered")
    db.refresh(customer)
    return customer


def update_mobile(db: Session, customer: CustomerModel, payload: MobileUpdate) -> CustomerModel:
    """Add or change the customer's mobile number. A UPI ID linked to the old number follows the new one."""
    if _mobile_taken(db, payload.mobile_number, customer.customer_id):
        raise BankError("CONFLICT", "mobile number is already registered")
    customer.mobile_number = payload.mobile_number
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise BankError("CONFLICT", "mobile number is already registered")
    db.refresh(customer)
    return customer


def reset_password(db: Session, customer: CustomerModel, payload: PasswordReset, current_token: str | None) -> None:
    """Set a new password and sign out every other session; the one making the change stays signed in."""
    customer.password_hash = _hash_password(payload.new_password)
    others = db.query(SessionModel).filter(SessionModel.customer_id == customer.customer_id)
    if current_token:
        others = others.filter(SessionModel.token_hash != sha256_hex(current_token))
    others.delete(synchronize_session=False)
    db.commit()


def login(db: Session, payload: LoginRequest) -> CustomerModel:
    customer = db.query(CustomerModel).filter(CustomerModel.login_id == payload.login_id).first()
    if customer is None or not _verify_password(payload.password, customer.password_hash):
        raise BankError("UNAUTHORIZED", "invalid login id or password")
    return customer
