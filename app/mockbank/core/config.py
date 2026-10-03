import os

from dotenv import load_dotenv

load_dotenv()


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mockbank.db")

# Website sessions
SESSION_COOKIE_NAME = "mockbank_session"
SESSION_IDLE_MINUTES = int(os.getenv("SESSION_IDLE_MINUTES", "30"))
COOKIE_SECURE = _bool_env("COOKIE_SECURE", True)
# Comma-separated list of origins allowed to make cookie-authenticated POST/PUT calls,
# e.g. "https://mockbankforpayments.onrender.com". When empty, the request's own origin is used.
ALLOWED_ORIGINS = [o.strip().rstrip("/") for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]

# Sandbox failure triggers (amount ending in 13/14/15/16 paise). Never enable in a shared demo you rely on.
SANDBOX_TRIGGERS = _bool_env("SANDBOX_TRIGGERS", False)
SANDBOX_SLOW_SECONDS = float(os.getenv("SANDBOX_SLOW_SECONDS", "30"))

# Background worker (webhook delivery + expiry sweeps)
WORKER_ENABLED = _bool_env("WORKER_ENABLED", True)
WORKER_INTERVAL_SECONDS = float(os.getenv("WORKER_INTERVAL_SECONDS", "5"))

VERIFY_RATE_LIMIT_PER_MINUTE = int(os.getenv("VERIFY_RATE_LIMIT_PER_MINUTE", "10"))
IDEMPOTENCY_RETENTION_DAYS = 7
