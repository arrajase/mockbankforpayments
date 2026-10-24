"""API clients: apps (not people) that call the gateway, each with its own key and permissions."""

import hmac
import secrets

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.mockbank.core.errors import BankError
from app.mockbank.db.models import ApiClientModel, CustomerModel, UpiModel
from app.mockbank.utils.common import iso_utc, new_id, sha256_hex, utcnow

KEY_PREFIX_TAG = "mbk"
MAX_CLIENTS_PER_CUSTOMER = 10
UNSET = object()  # "field not sent", as opposed to None ("clear it")


def _new_key() -> tuple[str, str]:
    """Returns (prefix, plaintext key). The prefix is stored to find the client; the key only as a hash."""
    prefix = secrets.token_hex(4)
    return prefix, f"{KEY_PREFIX_TAG}_{prefix}_{secrets.token_urlsafe(32)}"


def create_client(db: Session, name: str, owner_customer_id: str, webhook_url: str | None = None) -> tuple[ApiClientModel, str]:
    """Create a client and return it with its plaintext API key. Only the key's hash is stored."""
    if db.get(CustomerModel, owner_customer_id) is None:
        raise ValueError(f"customer {owner_customer_id} not found")
    if db.query(ApiClientModel).filter(ApiClientModel.name == name).first() is not None:
        raise ValueError(f"a client named {name!r} already exists")

    prefix, api_key = _new_key()
    client = ApiClientModel(
        client_id=new_id("cli"),
        name=name,
        key_prefix=prefix,
        key_hash=sha256_hex(api_key),
        owner_customer_id=owner_customer_id,
        webhook_url=webhook_url,
        webhook_secret=f"whsec_{secrets.token_urlsafe(32)}",
        active=True,
        created_at=utcnow(),
    )
    db.add(client)
    db.commit()
    db.refresh(client)
    return client, api_key


def authenticate(db: Session, api_key: str | None) -> ApiClientModel:
    if not api_key:
        raise BankError("UNAUTHORIZED", "missing x-api-key header")
    parts = api_key.split("_", 2)
    if len(parts) != 3 or parts[0] != KEY_PREFIX_TAG:
        raise BankError("UNAUTHORIZED", "invalid api key")
    client = db.query(ApiClientModel).filter(ApiClientModel.key_prefix == parts[1]).one_or_none()
    if client is None or not hmac.compare_digest(client.key_hash, sha256_hex(api_key)) or not client.active:
        raise BankError("UNAUTHORIZED", "invalid api key")
    return client


def owns_upi(client: ApiClientModel, upi: UpiModel) -> bool:
    return upi.customer_id == client.owner_customer_id


def require_own_upi(client: ApiClientModel, upi: UpiModel) -> None:
    if not owns_upi(client, upi):
        raise BankError("NOT_PERMITTED", f"this client may not act for {upi.upi_id}")


# ---------- website: self-service developer portal ----------

def client_out(client: ApiClientModel) -> dict:
    return {
        "client_id": client.client_id,
        "name": client.name,
        "key_hint": f"{KEY_PREFIX_TAG}_{client.key_prefix}_...",
        "active": client.active,
        "webhook_url": client.webhook_url,
        "created_at": iso_utc(client.created_at),
    }


def list_owned(db: Session, customer: CustomerModel) -> list[dict]:
    clients = (
        db.query(ApiClientModel)
        .filter(ApiClientModel.owner_customer_id == customer.customer_id)
        .order_by(ApiClientModel.created_at)
        .all()
    )
    return [client_out(c) for c in clients]


def _owned(db: Session, customer: CustomerModel, client_id: str) -> ApiClientModel:
    client = db.get(ApiClientModel, client_id)
    if client is None or client.owner_customer_id != customer.customer_id:
        raise BankError("NOT_FOUND", "app not found")
    return client


def create_owned(db: Session, customer: CustomerModel, name: str, webhook_url: str | None) -> dict:
    """A customer registers an app for themselves: its key can only act for their own UPI IDs."""
    owned = db.query(ApiClientModel).filter(ApiClientModel.owner_customer_id == customer.customer_id).count()
    if owned >= MAX_CLIENTS_PER_CUSTOMER:
        raise BankError("CONFLICT", f"at most {MAX_CLIENTS_PER_CUSTOMER} apps per customer")
    try:
        client, api_key = create_client(db, name, customer.customer_id, webhook_url)
    except ValueError as exc:
        raise BankError("CONFLICT", str(exc))
    except IntegrityError:
        db.rollback()
        raise BankError("CONFLICT", f"a client named {name!r} already exists")
    return {**client_out(client), "api_key": api_key, "webhook_secret": client.webhook_secret}


def update_owned(db: Session, customer: CustomerModel, client_id: str, *, webhook_url=UNSET, active: bool | None = None) -> dict:
    client = _owned(db, customer, client_id)
    if webhook_url is not UNSET:
        client.webhook_url = webhook_url
    if active is not None:
        client.active = active
    db.commit()
    return client_out(client)


def rotate_key(db: Session, customer: CustomerModel, client_id: str) -> dict:
    """Issue a new key; the old one stops working immediately."""
    client = _owned(db, customer, client_id)
    prefix, api_key = _new_key()
    client.key_prefix = prefix
    client.key_hash = sha256_hex(api_key)
    db.commit()
    return {**client_out(client), "api_key": api_key}


def webhook_secret(db: Session, customer: CustomerModel, client_id: str) -> dict:
    return {"webhook_secret": _owned(db, customer, client_id).webhook_secret}


def rotate_webhook_secret(db: Session, customer: CustomerModel, client_id: str) -> dict:
    client = _owned(db, customer, client_id)
    client.webhook_secret = f"whsec_{secrets.token_urlsafe(32)}"
    db.commit()
    return {"webhook_secret": client.webhook_secret}
