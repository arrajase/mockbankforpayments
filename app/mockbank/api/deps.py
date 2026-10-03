from urllib.parse import urlsplit

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.mockbank.core.config import ALLOWED_ORIGINS, SESSION_COOKIE_NAME
from app.mockbank.core.errors import BankError
from app.mockbank.db.database import get_db
from app.mockbank.db.models import ApiClientModel, CustomerModel
from app.mockbank.services import clients as clients_service
from app.mockbank.services import sessions as sessions_service


def current_customer(request: Request, db: Session = Depends(get_db)) -> CustomerModel:
    """Website caller, identified only by the session cookie."""
    customer = sessions_service.customer_for_token(db, request.cookies.get(SESSION_COOKIE_NAME))
    if customer is None:
        raise BankError("UNAUTHORIZED", "please log in")
    return customer


def same_origin(request: Request) -> None:
    """Cross-site request protection for cookie-authenticated writes."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    origin = request.headers.get("origin")
    if not origin:
        raise BankError("ORIGIN_NOT_ALLOWED", "missing Origin header")
    origin = origin.rstrip("/")
    if ALLOWED_ORIGINS:
        allowed = origin in ALLOWED_ORIGINS
    else:
        allowed = urlsplit(origin).netloc == request.headers.get("host")
    if not allowed:
        raise BankError("ORIGIN_NOT_ALLOWED", "request origin is not allowed")


def current_client(x_api_key: str | None = Header(default=None), db: Session = Depends(get_db)) -> ApiClientModel:
    return clients_service.authenticate(db, x_api_key)


def idempotency_key(idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")) -> str | None:
    return idempotency_key
