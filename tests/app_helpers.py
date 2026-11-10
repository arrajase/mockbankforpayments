import uuid


def parse_signature(header: str) -> tuple[str, str]:
    """Split 'X-MockBank-Signature: t=<unix>,v1=<hex>' into (t, v1)."""
    parts = dict(item.split("=", 1) for item in header.split(","))
    return parts["t"], parts["v1"]


def new_mobile() -> str:
    """A random, valid 10-digit Indian mobile number."""
    return f"9{uuid.uuid4().int % 10**9:09d}"
