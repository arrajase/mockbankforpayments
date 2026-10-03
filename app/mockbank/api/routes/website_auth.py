from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.mockbank.api.deps import current_customer, same_origin
from app.mockbank.core.config import COOKIE_SECURE, SESSION_COOKIE_NAME
from app.mockbank.db.database import get_db
from app.mockbank.db.models import CustomerModel
from app.mockbank.models.schemas import CustomerOut, LoginRequest, LoginResponse, SignupRequest
from app.mockbank.services import auth as auth_service
from app.mockbank.services import sessions as sessions_service

router = APIRouter(tags=["website: auth"], dependencies=[Depends(same_origin)])


@router.post("/auth/signup", response_model=CustomerOut)
def signup(payload: SignupRequest, db: Session = Depends(get_db)):
    return CustomerOut.model_validate(auth_service.signup(db, payload))


@router.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    customer = auth_service.login(db, payload)
    token = sessions_service.create_session(db, customer.customer_id)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path="/",
    )
    return LoginResponse.model_validate(customer)


@router.post("/auth/logout", status_code=204)
def logout(request: Request, db: Session = Depends(get_db)):
    sessions_service.delete_session(db, request.cookies.get(SESSION_COOKIE_NAME))
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE_NAME, path="/", httponly=True, secure=COOKIE_SECURE, samesite="lax")
    return response


@router.get("/me", response_model=CustomerOut)
def me(customer: CustomerModel = Depends(current_customer)):
    return CustomerOut.model_validate(customer)
