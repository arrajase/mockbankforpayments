"""The website: sessions, ownership checks, cross-site protection, bank-set dates, currency default."""

import uuid

from fastapi.testclient import TestClient


def _anon(origin="http://testserver"):
    from main import app

    return TestClient(app, base_url="http://testserver", headers={"Origin": origin} if origin else {})


def test_login_sets_httponly_cookie_and_me_uses_it(bank):
    from main import app

    web = TestClient(app, base_url="http://testserver", headers={"Origin": "http://testserver"})
    web.post("/auth/signup", json={"first_name": "A", "last_name": "B", "login_id": "ab1", "password": "pw", "confirm_password": "pw"})
    r = web.post("/auth/login", json={"login_id": "ab1", "password": "pw"})
    assert r.status_code == 200
    assert "customer_id" not in r.json()
    cookie = r.headers["set-cookie"].lower()
    assert "mockbank_session=" in cookie and "httponly" in cookie and "samesite=lax" in cookie

    assert web.get("/me").json()["login_id"] == "ab1"
    assert web.post("/auth/logout").status_code == 204
    assert web.get("/me").status_code == 401


def test_requires_login(app_client):
    anon = _anon()
    for path in ("/me", "/accounts", "/upi", "/me/collect-requests", "/me/consents"):
        r = anon.get(path)
        assert r.status_code == 401, path
        assert r.json()["error"]["code"] == "UNAUTHORIZED"


def test_idle_session_expires(bank, db):
    from datetime import timedelta

    from app.mockbank.db.models import SessionModel

    alice = bank.customer("Alice")
    db.query(SessionModel).update({SessionModel.last_seen_at: SessionModel.last_seen_at - timedelta(minutes=31)})
    db.commit()
    assert alice.web.get("/me").status_code == 401


def test_other_customers_resources_are_404(bank):
    alice = bank.customer("Alice", deposit_cents=10_000, handle=f"alice{uuid.uuid4().hex[:6]}")
    mallory = bank.customer("Mallory", deposit_cents=1_000)

    assert mallory.web.get(f"/accounts/{alice.account_id}").status_code == 404
    assert mallory.web.get("/transactions", params={"account_id": alice.account_id}).status_code == 404
    r = mallory.web.post("/transactions", json={"account_id": alice.account_id, "tran_type": "ATM Withdrawal", "amount_cents": 100})
    assert r.status_code == 404
    r = mallory.web.put(f"/upi/{alice.upi_id}", json={"account_id": mallory.account_id})
    assert r.status_code == 404
    assert bank.balance(alice.account_id) == 10_000

    assert [a["account_id"] for a in mallory.web.get("/accounts").json()] == [mallory.account_id]
    assert mallory.web.get("/upi").json() == []


def test_cannot_link_upi_to_someone_elses_account(bank):
    alice = bank.customer("Alice")
    mallory = bank.customer("Mallory", handle=f"mal{uuid.uuid4().hex[:6]}")
    r = mallory.web.put(f"/upi/{mallory.upi_id}", json={"account_id": alice.account_id})
    assert r.status_code == 404


def test_writes_need_same_origin(bank):
    alice = bank.customer("Alice")
    for origin in ("https://evil.example", None):
        alice.web.headers.pop("Origin", None)
        headers = {"Origin": origin} if origin else {}
        r = alice.web.post("/accounts", json={"account_type": "savings", "account_name": "x"}, headers=headers)
        assert r.status_code == 403
        assert r.json()["error"]["code"] == "ORIGIN_NOT_ALLOWED"


def test_bank_sets_the_date_and_default_currency_is_inr(bank):
    alice = bank.customer("Alice")
    account = alice.web.post("/accounts", json={"account_type": "savings", "account_name": "Savings"}).json()
    assert account["currency"] == "INR"

    r = alice.web.post("/transactions", json={"account_id": account["account_id"], "tran_type": "ATM Deposit",
                                              "amount_cents": 700, "tran_date": "1999-12-31"})
    assert r.status_code == 200
    body = r.json()
    assert body["tran_date"] != "1999-12-31"
    assert body["created_at"].endswith("Z")
    assert body["currency"] == "INR"
    assert body["balance_after_cents"] == 700


def test_website_withdrawal_cannot_overdraw(bank):
    alice = bank.customer("Alice", deposit_cents=500)
    r = alice.web.post("/transactions", json={"account_id": alice.account_id, "tran_type": "ATM Withdrawal", "amount_cents": 501})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INSUFFICIENT_FUNDS"


def test_customer_can_hold_several_upi_ids_each_with_a_pin(bank):
    biz = bank.customer("Biz", handle=f"escrow{uuid.uuid4().hex[:6]}")
    second = biz.web.post("/accounts", json={"account_type": "checking", "account_name": "Operating"}).json()
    r = biz.web.post("/upi", json={"handle": f"ops{uuid.uuid4().hex[:6]}", "account_id": second["account_id"], "upi_pin": "5555"})
    assert r.status_code == 200
    upis = biz.web.get("/upi").json()
    assert len(upis) == 2 and all(u["pin_set"] for u in upis)


def test_upi_pin_rules(bank):
    alice = bank.customer("Alice")
    r = alice.web.post("/upi", json={"handle": f"a{uuid.uuid4().hex[:6]}", "account_id": alice.account_id, "upi_pin": "12"})
    assert r.status_code == 422

    alice = bank.customer("Alice2", handle=f"a{uuid.uuid4().hex[:6]}", pin="1234")
    r = alice.web.put(f"/upi/{alice.upi_id}/pin", json={"new_pin": "9999"})
    assert r.json()["error"]["code"] == "PIN_INVALID"
    r = alice.web.put(f"/upi/{alice.upi_id}/pin", json={"new_pin": "9999", "current_pin": "1234"})
    assert r.status_code == 200


def test_errors_use_one_format(app_client):
    r = _anon().post("/auth/login", json={"login_id": "nobody", "password": "x"})
    assert r.status_code == 401
    assert set(r.json()["error"]) == {"code", "message", "retryable"}
    r = _anon().post("/auth/login", json={})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
