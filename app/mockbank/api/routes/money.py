"""Shared handling for gateway calls that move money: idempotency plus sandbox triggers."""

import time
from collections.abc import Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.mockbank.core import config
from app.mockbank.core.errors import BankError
from app.mockbank.db.models import ApiClientModel
from app.mockbank.services import idempotency, sandbox


def run_money_call(
    db: Session,
    request: Request,
    client: ApiClientModel,
    key: str | None,
    payload: BaseModel,
    amount_cents: int,
    operation: Callable[[], tuple[int, dict]],
) -> JSONResponse:
    if not key:
        raise BankError("IDEMPOTENCY_KEY_REQUIRED", "the Idempotency-Key header is required")

    trigger = sandbox.trigger_for(amount_cents)
    if trigger == sandbox.UNAVAILABLE:
        raise BankError("SERVICE_UNAVAILABLE", "sandbox trigger: service unavailable, nothing was done")

    status_code, body, replayed = idempotency.run(
        db,
        client_id=client.client_id,
        key=key,
        method=request.method,
        path=request.url.path,
        body=payload.model_dump(mode="json"),
        operation=operation,
    )

    if not replayed:
        if trigger == sandbox.ERROR_AFTER_COMMIT:
            raise BankError("INTERNAL_ERROR", "sandbox trigger: the request was processed but no confirmation was sent")
        if trigger == sandbox.SLOW_RESPONSE:
            time.sleep(config.SANDBOX_SLOW_SECONDS)
    return JSONResponse(status_code=status_code, content=body, headers={"Idempotent-Replayed": str(replayed).lower()})
