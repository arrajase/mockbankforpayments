"""Test setup. The suite needs Postgres (SQLite ignores SELECT ... FOR UPDATE, so locking can't be tested).

    docker compose up -d db
    TEST_DATABASE_URL=postgresql+psycopg://mockbank:mockbank@localhost:5433/mockbank_test uv run pytest

The test database is wiped, so TEST_DATABASE_URL must never point at real data.
"""

import os
import uuid

import pytest

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

# Must be set before the app is imported: config is read at import time, and .env must not win.
if TEST_DATABASE_URL:
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["WORKER_ENABLED"] = "false"
os.environ["COOKIE_SECURE"] = "false"  # the test client talks plain http
os.environ["ALLOWED_ORIGINS"] = ""


def pytest_collection_modifyitems(config, items):
    if TEST_DATABASE_URL and TEST_DATABASE_URL.startswith("postgresql"):
        return
    skip = pytest.mark.skip(reason="set TEST_DATABASE_URL to a disposable Postgres database (see tests/conftest.py)")
    for item in items:
        item.add_marker(skip)


ORIGIN = "http://testserver"


@pytest.fixture(scope="session")
def migrated_db():
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text

    engine = create_engine(TEST_DATABASE_URL)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()

    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(cfg, "head")
    yield


@pytest.fixture
def app_client(migrated_db):
    from fastapi.testclient import TestClient
    from sqlalchemy import text

    from app.mockbank.api.routes.upi_gateway import verify_limiter
    from app.mockbank.db.database import Base, engine
    from main import app

    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    verify_limiter.reset()

    with TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN}) as client:  # runs the lifespan seeds
        yield client


@pytest.fixture
def db(migrated_db):
    from app.mockbank.db.database import SessionLocal

    session = SessionLocal()
    yield session
    session.close()


class Bank:
    """Helpers that set up customers through the website, the way a real user would."""

    def __init__(self, client):
        self.client = client

    def customer(self, first_name: str, *, deposit_cents: int = 0, currency: str = "INR", handle: str | None = None,
                 pin: str = "1234"):
        from fastapi.testclient import TestClient

        from main import app

        login_id = f"{first_name.lower()}-{uuid.uuid4().hex[:6]}"
        web = TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN})
        assert web.post("/auth/signup", json={"first_name": first_name, "last_name": "Test", "login_id": login_id,
                                              "password": "pw", "confirm_password": "pw"}).status_code == 200
        assert web.post("/auth/login", json={"login_id": login_id, "password": "pw"}).status_code == 200
        me = web.get("/me").json()
        account = web.post("/accounts", json={"account_type": "checking", "account_name": "Main", "currency": currency}).json()
        if deposit_cents:
            r = web.post("/transactions", json={"account_id": account["account_id"], "tran_type": "ATM Deposit", "amount_cents": deposit_cents})
            assert r.status_code == 200, r.text
        upi = None
        if handle:
            r = web.post("/upi", json={"handle": handle, "account_id": account["account_id"], "upi_pin": pin})
            assert r.status_code == 200, r.text
            upi = r.json()["upi_id"]
        return Customer(web=web, customer_id=me["customer_id"], account_id=account["account_id"], upi_id=upi)

    def api_client(self, owner_customer_id: str, name: str | None = None, webhook_url: str | None = None):
        from app.mockbank.db.database import SessionLocal
        from app.mockbank.services.clients import create_client

        db = SessionLocal()
        try:
            client, key = create_client(db, name or f"app-{uuid.uuid4().hex[:6]}", owner_customer_id, webhook_url)
            return ApiCaller(self.client, key, client.client_id, client.webhook_secret)
        finally:
            db.close()

    def balance(self, account_id: str) -> int:
        from app.mockbank.db.database import SessionLocal
        from app.mockbank.db.models import AccountModel

        db = SessionLocal()
        try:
            return db.get(AccountModel, account_id).balance_cents
        finally:
            db.close()


class Customer:
    def __init__(self, web, customer_id, account_id, upi_id):
        self.web = web
        self.customer_id = customer_id
        self.account_id = account_id
        self.upi_id = upi_id


class ApiCaller:
    def __init__(self, http, api_key, client_id, webhook_secret):
        self.http = http
        self.api_key = api_key
        self.client_id = client_id
        self.webhook_secret = webhook_secret

    def headers(self, idempotency_key: str | None = None) -> dict:
        headers = {"x-api-key": self.api_key}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    def get(self, path, **params):
        return self.http.get(path, params=params, headers=self.headers())

    def post(self, path, body, key: str | None = "auto"):
        key = str(uuid.uuid4()) if key == "auto" else key
        return self.http.post(path, json=body, headers=self.headers(key))

    def pay(self, from_upi, to_upi, amount_cents, *, currency="INR", reference=None, key="auto", narration=None):
        body = {"recipient_upi_id": to_upi, "amount_cents": amount_cents, "currency": currency,
                "client_reference": reference or f"ref-{uuid.uuid4().hex[:10]}"}
        if narration:
            body["narration"] = narration
        return self.post(f"/upi/{from_upi}/pay", body, key=key)


@pytest.fixture
def bank(app_client):
    return Bank(app_client)


@pytest.fixture
def setup(bank):
    """A payments app with an escrow UPI ID (₹1,000.00) and a customer, Ravi, with ₹500.00."""
    escrow = bank.customer("Escrow", deposit_cents=100_000, handle=f"escrow{uuid.uuid4().hex[:6]}")
    ravi = bank.customer("Ravi", deposit_cents=50_000, handle=f"ravi{uuid.uuid4().hex[:6]}", pin="2468")
    app = bank.api_client(escrow.customer_id)
    return type("Setup", (), {"escrow": escrow, "ravi": ravi, "app": app})
