"""API clients: apps (not people) that call the gateway, each with its own key and permissions."""

import hmac
import secrets

from sqlalchemy.orm import Session

from app.mockbank.core.errors import BankError
from app.mockbank.db.models import ApiClientModel, CustomerModel, UpiModel
from app.mockbank.utils.common import new_id, sha256_hex, utcnow

KEY_PREFIX_TAG = "mbk"


def create_client(db: Session, name: str, owner_customer_id: str, webhook_url: str | None = None) -> tuple[ApiClientModel, str]:
    """Create a client and return it with its plaintext API key. Only the key's hash is stored."""
    if db.get(CustomerModel, owner_customer_id) is None:
        raise ValueError(f"customer {owner_customer_id} not found")
    if db.query(ApiClientModel).filter(ApiClientModel.name == name).first() is not None:
        raise ValueError(f"a client named {name!r} already exists")

    prefix = secrets.token_hex(4)
    api_key = f"{KEY_PREFIX_TAG}_{prefix}_{secrets.token_urlsafe(32)}"
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
