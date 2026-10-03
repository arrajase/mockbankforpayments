import hashlib
import json
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def utcnow() -> datetime:
    """Naive UTC timestamp; all DateTime columns store UTC without tzinfo."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def ist_today(now_utc: datetime | None = None) -> date:
    now_utc = now_utc or utcnow()
    return now_utc.replace(tzinfo=timezone.utc).astimezone(IST).date()


def iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_hex(value: str | bytes) -> str:
    if isinstance(value, str):
        value = value.encode()
    return hashlib.sha256(value).hexdigest()


def random_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def canonical_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
