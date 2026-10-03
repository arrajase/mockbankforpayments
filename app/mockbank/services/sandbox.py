"""Test triggers keyed on the last two digits of amount_cents. Active only with SANDBOX_TRIGGERS=true.

    ..13  move the money, then wait before answering (client times out)
    ..14  move the money, then answer 500 (client gets no confirmation)
    ..15  answer 503 without moving any money
    ..16  a collect request expires immediately
"""

from app.mockbank.core import config

SLOW_RESPONSE = 13
ERROR_AFTER_COMMIT = 14
UNAVAILABLE = 15
COLLECT_EXPIRES = 16


def trigger_for(amount_cents: int) -> int | None:
    if not config.SANDBOX_TRIGGERS:
        return None
    paise = amount_cents % 100
    return paise if paise in (SLOW_RESPONSE, ERROR_AFTER_COMMIT, UNAVAILABLE, COLLECT_EXPIRES) else None
