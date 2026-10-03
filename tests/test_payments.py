"""Money movement through the gateway: idempotency, locking, currency, permissions, status lookup."""

import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


def test_pay_moves_money_and_records_both_legs(bank, setup):
    r = setup.app.pay(setup.escrow.upi_id, setup.ravi.upi_id, 12_000, reference="payout-1", narration="refund")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "SUCCESS"
    assert body["currency"] == "INR"
    assert body["sender_upi_id"] == setup.escrow.upi_id
    assert body["recipient_upi_id"] == setup.ravi.upi_id
    assert body["client_reference"] == "payout-1"
    assert body["narration"] == "refund"
    assert body["balance_after_cents"] == 88_000
    assert body["created_at"].endswith("Z")
    assert body["transfer_id"]
    assert bank.balance(setup.escrow.account_id) == 88_000
    assert bank.balance(setup.ravi.account_id) == 62_000


def test_idempotent_replay_moves_money_once(bank, setup):
    key = str(uuid.uuid4())
    first = setup.app.pay(setup.escrow.upi_id, setup.ravi.upi_id, 10_000, reference="once", key=key)
    second = setup.app.pay(setup.escrow.upi_id, setup.ravi.upi_id, 10_000, reference="once", key=key)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert first.headers["Idempotent-Replayed"] == "false"
    assert second.headers["Idempotent-Replayed"] == "true"
    assert bank.balance(setup.escrow.account_id) == 90_000


def test_idempotency_key_reused_with_different_body(setup):
    key = str(uuid.uuid4())
    assert setup.app.pay(setup.escrow.upi_id, setup.ravi.upi_id, 100, reference="a", key=key).status_code == 200
    r = setup.app.pay(setup.escrow.upi_id, setup.ravi.upi_id, 200, reference="a", key=key)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_idempotency_key_required(bank, setup):
    r = setup.app.pay(setup.escrow.upi_id, setup.ravi.upi_id, 100, key=None)
    assert r.status_code == 400
    assert r.json() == {"error": {"code": "IDEMPOTENCY_KEY_REQUIRED", "message": "the Idempotency-Key header is required", "retryable": False}}
    assert bank.balance(setup.escrow.account_id) == 100_000


def test_concurrent_same_key_moves_money_once(bank, setup):
    key = str(uuid.uuid4())
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: setup.app.pay(setup.escrow.upi_id, setup.ravi.upi_id, 1_000, reference="race", key=key), range(8)))
    assert {r.status_code for r in results} == {200}
    assert len({r.json()["transaction_id"] for r in results}) == 1
    assert bank.balance(setup.escrow.account_id) == 99_000


def test_concurrent_payouts_never_overdraw(bank, setup):
    """20 parallel payouts of ₹100 from an account holding ₹1,000: exactly 10 succeed."""
    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(lambda i: setup.app.pay(setup.escrow.upi_id, setup.ravi.upi_id, 10_000, reference=f"p{i}"), range(20)))

    statuses = sorted(r.status_code for r in results)
    assert statuses.count(200) == 10
    assert statuses.count(422) == 10
    assert all(r.json()["error"]["code"] == "INSUFFICIENT_FUNDS" for r in results if r.status_code == 422)
    assert bank.balance(setup.escrow.account_id) == 0
    assert bank.balance(setup.ravi.account_id) == 150_000


def test_opposite_transfers_do_not_deadlock(bank, setup):
    ravi_app = bank.api_client(setup.ravi.customer_id)

    def move(i):
        if i % 2:
            return setup.app.pay(setup.escrow.upi_id, setup.ravi.upi_id, 100, reference=f"e{i}")
        return ravi_app.pay(setup.ravi.upi_id, setup.escrow.upi_id, 100, reference=f"r{i}")

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(move, range(40)))
    assert {r.status_code for r in results} == {200}
    assert bank.balance(setup.escrow.account_id) + bank.balance(setup.ravi.account_id) == 150_000


def test_database_rejects_negative_balance(db, setup):
    with pytest.raises(IntegrityError):
        db.execute(text("UPDATE accounts SET balance_cents = -1 WHERE account_id = :a"), {"a": setup.escrow.account_id})
        db.commit()
    db.rollback()


def test_insufficient_funds_is_recorded_and_retry_returns_same_failure(bank, setup):
    key = str(uuid.uuid4())
    r = setup.app.pay(setup.escrow.upi_id, setup.ravi.upi_id, 500_000, reference="too-big", key=key)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INSUFFICIENT_FUNDS"
    failed = r.json()["transaction"]
    assert failed["status"] == "FAILED"

    lookup = setup.app.get("/transactions", client_reference="too-big")
    assert lookup.status_code == 200
    assert lookup.json()["status"] == "FAILED"
    assert lookup.json()["failure_reason"] == "INSUFFICIENT_FUNDS"

    replay = setup.app.pay(setup.escrow.upi_id, setup.ravi.upi_id, 500_000, reference="too-big", key=key)
    assert replay.status_code == 422 and replay.json() == r.json()
    assert bank.balance(setup.escrow.account_id) == 100_000


def test_currency_mismatch(bank, setup):
    usd = bank.customer("Usd", deposit_cents=10_000, currency="USD", handle=f"usd{uuid.uuid4().hex[:6]}")
    r = setup.app.pay(setup.escrow.upi_id, usd.upi_id, 100)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "CURRENCY_MISMATCH"

    r = setup.app.pay(setup.escrow.upi_id, setup.ravi.upi_id, 100, currency="USD")
    assert r.json()["error"]["code"] == "CURRENCY_MISMATCH"
    assert bank.balance(setup.escrow.account_id) == 100_000


def test_currency_is_required(setup):
    r = setup.app.post(f"/upi/{setup.escrow.upi_id}/pay", {"recipient_upi_id": setup.ravi.upi_id, "amount_cents": 100, "client_reference": "x"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_client_cannot_pay_from_someone_elses_upi(bank, setup):
    r = setup.app.pay(setup.ravi.upi_id, setup.escrow.upi_id, 100)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "NOT_PERMITTED"
    assert bank.balance(setup.ravi.account_id) == 50_000


def test_same_upi(setup):
    r = setup.app.pay(setup.escrow.upi_id, setup.escrow.upi_id, 100)
    assert r.json()["error"]["code"] == "SAME_UPI"


def test_unknown_upi(setup):
    r = setup.app.pay(setup.escrow.upi_id, "nobody@okmockbank", 100)
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "UPI_NOT_FOUND"


def test_bad_api_key(app_client, setup):
    r = app_client.get(f"/upi/{setup.escrow.upi_id}/balance", headers={"x-api-key": "mbk_00000000_nope"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"


def test_duplicate_client_reference_with_new_key(setup):
    assert setup.app.pay(setup.escrow.upi_id, setup.ravi.upi_id, 100, reference="dup").status_code == 200
    r = setup.app.pay(setup.escrow.upi_id, setup.ravi.upi_id, 100, reference="dup")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "DUPLICATE_REFERENCE"


def test_status_lookup_only_shows_own_transactions(bank, setup):
    txn = setup.app.pay(setup.escrow.upi_id, setup.ravi.upi_id, 2_500, reference="lookup-me").json()

    by_id = setup.app.get(f"/transactions/{txn['transaction_id']}")
    assert by_id.status_code == 200
    assert by_id.json()["client_reference"] == "lookup-me"
    assert by_id.json()["amount_cents"] == 2_500

    by_ref = setup.app.get("/transactions", client_reference="lookup-me")
    assert by_ref.json()["transaction_id"] == txn["transaction_id"]

    other = bank.api_client(setup.ravi.customer_id)
    assert other.get(f"/transactions/{txn['transaction_id']}").status_code == 404
    assert other.get("/transactions", client_reference="lookup-me").status_code == 404


def test_tran_date_from_request_is_ignored(setup):
    r = setup.app.post(f"/upi/{setup.escrow.upi_id}/pay", {
        "recipient_upi_id": setup.ravi.upi_id, "amount_cents": 100, "currency": "INR",
        "client_reference": "dated", "tran_date": "2001-01-01",
    })
    assert r.status_code == 200
    assert r.json()["tran_date"] != "2001-01-01"


def test_gateway_single_posting_on_own_upi(bank, setup):
    r = setup.app.post(f"/upi/{setup.escrow.upi_id}/transactions", {
        "tran_type": "ATM Withdrawal", "amount_cents": 5_000, "currency": "INR", "client_reference": "wd-1",
    })
    assert r.status_code == 200, r.text
    assert r.json()["balance_after_cents"] == 95_000

    r = setup.app.post(f"/upi/{setup.ravi.upi_id}/transactions", {
        "tran_type": "ATM Withdrawal", "amount_cents": 5_000, "currency": "INR", "client_reference": "wd-2",
    })
    assert r.status_code == 403


# ---------- sandbox triggers ----------

@pytest.fixture
def triggers(monkeypatch):
    from app.mockbank.core import config

    monkeypatch.setattr(config, "SANDBOX_TRIGGERS", True)
    monkeypatch.setattr(config, "SANDBOX_SLOW_SECONDS", 0.3)


def test_trigger_14_moves_money_then_errors_and_retry_confirms(bank, setup, triggers):
    key = str(uuid.uuid4())
    r = setup.app.pay(setup.escrow.upi_id, setup.ravi.upi_id, 1_014, reference="t14", key=key)
    assert r.status_code == 500
    assert r.json()["error"]["retryable"] is True
    assert bank.balance(setup.escrow.account_id) == 100_000 - 1_014

    retry = setup.app.pay(setup.escrow.upi_id, setup.ravi.upi_id, 1_014, reference="t14", key=key)
    assert retry.status_code == 200
    assert retry.json()["status"] == "SUCCESS"
    assert bank.balance(setup.escrow.account_id) == 100_000 - 1_014


def test_trigger_15_returns_503_without_moving_money(bank, setup, triggers):
    r = setup.app.pay(setup.escrow.upi_id, setup.ravi.upi_id, 1_015, reference="t15")
    assert r.status_code == 503
    assert r.json()["error"] == {"code": "SERVICE_UNAVAILABLE", "message": "sandbox trigger: service unavailable, nothing was done", "retryable": True}
    assert bank.balance(setup.escrow.account_id) == 100_000
    assert setup.app.get("/transactions", client_reference="t15").status_code == 404


def test_trigger_13_answers_slowly_after_moving_money(bank, setup, triggers):
    import time

    start = time.monotonic()
    r = setup.app.pay(setup.escrow.upi_id, setup.ravi.upi_id, 1_013, reference="t13")
    assert time.monotonic() - start >= 0.3
    assert r.status_code == 200
    assert bank.balance(setup.escrow.account_id) == 100_000 - 1_013


def test_triggers_off_by_default(bank, setup):
    r = setup.app.pay(setup.escrow.upi_id, setup.ravi.upi_id, 1_015)
    assert r.status_code == 200
