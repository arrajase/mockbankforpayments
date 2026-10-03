"""Collect requests, consents, UPI ID verification and paginated statements."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest


def _collect(setup, amount_cents=20_000, reference=None, **extra):
    body = {"payer_upi_id": setup.ravi.upi_id, "payee_upi_id": setup.escrow.upi_id, "amount_cents": amount_cents,
            "currency": "INR", "client_reference": reference or f"col-{uuid.uuid4().hex[:8]}", "note": "Add money", **extra}
    return setup.app.post("/collect-requests", body)


# ---------- collect requests ----------

def test_collect_approved_with_pin_moves_money(bank, setup):
    r = _collect(setup, reference="add-1")
    assert r.status_code == 201, r.text
    collect = r.json()
    assert collect["status"] == "PENDING"
    assert bank.balance(setup.ravi.account_id) == 50_000

    pending = setup.ravi.web.get("/me/collect-requests").json()
    assert [p["collect_id"] for p in pending] == [collect["collect_id"]]

    r = setup.ravi.web.post(f"/me/collect-requests/{collect['collect_id']}/approve", json={"upi_pin": "2468"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "SUCCESS"

    status = setup.app.get(f"/collect-requests/{collect['collect_id']}").json()
    assert status["status"] == "SUCCESS"
    txn = setup.app.get(f"/transactions/{status['transaction_id']}").json()
    assert txn["client_reference"] == "add-1" and txn["amount_cents"] == 20_000
    assert bank.balance(setup.ravi.account_id) == 30_000
    assert bank.balance(setup.escrow.account_id) == 120_000
    assert setup.ravi.web.get("/me/collect-requests").json() == []


def test_collect_insufficient_funds_fails(bank, setup):
    collect = _collect(setup, amount_cents=60_000).json()
    r = setup.ravi.web.post(f"/me/collect-requests/{collect['collect_id']}/approve", json={"upi_pin": "2468"})
    assert r.json()["status"] == "FAILED"
    assert r.json()["failure_reason"] == "INSUFFICIENT_FUNDS"
    assert bank.balance(setup.ravi.account_id) == 50_000


def test_collect_decline(bank, setup):
    collect = _collect(setup).json()
    r = setup.ravi.web.post(f"/me/collect-requests/{collect['collect_id']}/decline")
    assert r.json()["status"] == "DECLINED"
    r = setup.ravi.web.post(f"/me/collect-requests/{collect['collect_id']}/approve", json={"upi_pin": "2468"})
    assert r.json()["error"]["code"] == "INVALID_STATE"


def test_wrong_pin_three_times_locks(bank, setup):
    collect = _collect(setup).json()
    url = f"/me/collect-requests/{collect['collect_id']}/approve"
    assert setup.ravi.web.post(url, json={"upi_pin": "0000"}).json()["error"]["code"] == "PIN_INVALID"
    assert setup.ravi.web.post(url, json={"upi_pin": "0000"}).json()["error"]["code"] == "PIN_INVALID"
    assert setup.ravi.web.post(url, json={"upi_pin": "0000"}).json()["error"]["code"] == "PIN_LOCKED"
    r = setup.ravi.web.post(url, json={"upi_pin": "2468"})
    assert r.status_code == 423 and r.json()["error"]["code"] == "PIN_LOCKED"
    assert bank.balance(setup.ravi.account_id) == 50_000


def test_only_the_payer_can_approve(bank, setup):
    collect = _collect(setup).json()
    other = bank.customer("Other")
    r = other.web.post(f"/me/collect-requests/{collect['collect_id']}/approve", json={"upi_pin": "1234"})
    assert r.status_code == 404


def test_collect_expires(bank, db, setup):
    from app.mockbank.db.models import CollectRequestModel
    from app.mockbank.services import collect as collect_service

    lazy = _collect(setup).json()
    swept = _collect(setup).json()
    db.query(CollectRequestModel).update({CollectRequestModel.expires_at: datetime(2000, 1, 1)})
    db.commit()

    # lazily on read
    assert setup.app.get(f"/collect-requests/{lazy['collect_id']}").json()["status"] == "EXPIRED"
    r = setup.ravi.web.post(f"/me/collect-requests/{lazy['collect_id']}/approve", json={"upi_pin": "2468"})
    assert r.json()["error"]["code"] in ("COLLECT_EXPIRED", "INVALID_STATE")
    # and by the periodic sweep
    assert collect_service.expire_due(db) == 1
    assert setup.app.get(f"/collect-requests/{swept['collect_id']}").json()["status"] == "EXPIRED"
    assert bank.balance(setup.ravi.account_id) == 50_000


def test_collect_trigger_16_expires_immediately(setup, monkeypatch):
    from app.mockbank.core import config

    monkeypatch.setattr(config, "SANDBOX_TRIGGERS", True)
    r = _collect(setup, amount_cents=1_016)
    assert r.json()["status"] == "EXPIRED"


def test_collect_payee_must_belong_to_client(bank, setup):
    body = {"payer_upi_id": setup.escrow.upi_id, "payee_upi_id": setup.ravi.upi_id, "amount_cents": 100,
            "currency": "INR", "client_reference": "steal"}
    r = setup.app.post("/collect-requests", body)
    assert r.status_code == 403 and r.json()["error"]["code"] == "NOT_PERMITTED"


def test_collect_expiry_limit(setup):
    r = _collect(setup, expires_in_seconds=901)
    assert r.status_code == 422


def test_collect_is_idempotent(setup):
    key = str(uuid.uuid4())
    body = {"payer_upi_id": setup.ravi.upi_id, "payee_upi_id": setup.escrow.upi_id, "amount_cents": 100,
            "currency": "INR", "client_reference": "c-idem"}
    first = setup.app.post("/collect-requests", body, key=key)
    second = setup.app.post("/collect-requests", body, key=key)
    assert first.json()["collect_id"] == second.json()["collect_id"]
    assert setup.app.post("/collect-requests", body, key=None).json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"


# ---------- consents ----------

def _consent(setup, purposes, **extra):
    body = {"upi_id": setup.ravi.upi_id, "purposes": purposes,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(), **extra}
    return setup.app.http.post("/consents", json=body, headers=setup.app.headers())


def test_customer_balance_needs_consent(setup):
    r = setup.app.get(f"/upi/{setup.ravi.upi_id}/balance")
    assert r.status_code == 403 and r.json()["error"]["code"] == "CONSENT_REQUIRED"

    consent = _consent(setup, ["BALANCE", "LINK"]).json()
    assert consent["status"] == "PENDING"
    assert setup.app.get(f"/upi/{setup.ravi.upi_id}/balance", consent_id=consent["consent_id"]).status_code == 403

    listed = setup.ravi.web.get("/me/consents").json()
    assert listed[0]["consent_id"] == consent["consent_id"]
    r = setup.ravi.web.post(f"/me/consents/{consent['consent_id']}/approve", json={"upi_pin": "2468"})
    assert r.json()["status"] == "ACTIVE"
    assert setup.app.get(f"/consents/{consent['consent_id']}").json()["status"] == "ACTIVE"

    r = setup.app.get(f"/upi/{setup.ravi.upi_id}/balance", consent_id=consent["consent_id"])
    assert r.status_code == 200 and r.json()["balance_cents"] == 50_000
    # BALANCE consent doesn't cover statements
    r = setup.app.get(f"/upi/{setup.ravi.upi_id}/statement", consent_id=consent["consent_id"])
    assert r.status_code == 403

    setup.ravi.web.post(f"/me/consents/{consent['consent_id']}/revoke")
    assert setup.app.get(f"/upi/{setup.ravi.upi_id}/balance", consent_id=consent["consent_id"]).status_code == 403


def test_statement_consent_limits_date_range(setup):
    today = datetime.now(timezone.utc).date()
    consent = _consent(setup, ["STATEMENT"], statement_from=str(today - timedelta(days=10)), statement_to=str(today + timedelta(days=1))).json()
    setup.ravi.web.post(f"/me/consents/{consent['consent_id']}/approve", json={"upi_pin": "2468"})

    r = setup.app.get(f"/upi/{setup.ravi.upi_id}/statement", consent_id=consent["consent_id"])
    assert r.status_code == 200
    assert [i["tran_type"] for i in r.json()["items"]] == ["ATM Deposit"]

    r = setup.app.get(f"/upi/{setup.ravi.upi_id}/statement", consent_id=consent["consent_id"], **{"from": str(today - timedelta(days=60))})
    assert r.status_code == 403


def test_another_clients_consent_is_useless(bank, setup):
    consent = _consent(setup, ["BALANCE"]).json()
    setup.ravi.web.post(f"/me/consents/{consent['consent_id']}/approve", json={"upi_pin": "2468"})
    other = bank.api_client(setup.escrow.customer_id)
    assert other.get(f"/upi/{setup.ravi.upi_id}/balance", consent_id=consent["consent_id"]).status_code == 403
    assert other.get(f"/consents/{consent['consent_id']}").status_code == 404


def test_consent_reject_and_validation(setup):
    consent = _consent(setup, ["LINK"]).json()
    assert setup.ravi.web.post(f"/me/consents/{consent['consent_id']}/reject").json()["status"] == "REJECTED"
    assert _consent(setup, ["STATEMENT"]).status_code == 422  # range required


# ---------- verify ----------

def test_verify_hides_balance_and_is_rate_limited(setup):
    r = setup.app.get(f"/upi/{setup.ravi.upi_id}/verify")
    assert r.status_code == 200
    assert r.json() == {"upi_id": setup.ravi.upi_id, "account_holder_name": "Ravi Test", "currency": "INR", "status": "ACTIVE"}
    for _ in range(9):
        assert setup.app.get(f"/upi/{setup.ravi.upi_id}/verify").status_code == 200
    r = setup.app.get(f"/upi/{setup.ravi.upi_id}/verify")
    assert r.status_code == 429
    assert r.json()["error"] == {"code": "RATE_LIMITED", "message": "at most 10 verify calls per minute", "retryable": True}


# ---------- statement ----------

def test_own_statement_paginates_with_cursor(setup):
    for i in range(5):
        assert setup.app.pay(setup.escrow.upi_id, setup.ravi.upi_id, 100 + i, reference=f"s{i}", narration=f"n{i}").status_code == 200

    seen, cursor = [], None
    while True:
        params = {"limit": 2}
        if cursor:
            params["cursor"] = cursor
        page = setup.app.get(f"/upi/{setup.escrow.upi_id}/statement", **params).json()
        seen.extend(page["items"])
        cursor = page["next_cursor"]
        if not cursor:
            break

    assert len(seen) == 6  # 5 payouts + the opening deposit
    assert [i["amount_cents"] for i in seen[:5]] == [104, 103, 102, 101, 100]
    newest = seen[0]
    assert newest["narration"] == "n4" and newest["counterparty_upi_id"] == setup.ravi.upi_id
    assert newest["client_reference"] == "s4" and newest["balance_after_cents"] == 100_000 - sum(range(100, 105))


@pytest.mark.parametrize("bad", ["not-base64!", "Zm9v"])
def test_bad_cursor(setup, bad):
    r = setup.app.get(f"/upi/{setup.escrow.upi_id}/statement", cursor=bad)
    assert r.status_code == 422


# ---------- profile page app-access toggles ----------

def _toggle(customer, app, purpose, enabled, pin=None):
    body = {"client_id": app.client_id, "upi_id": customer.upi_id, "purpose": purpose, "enabled": enabled}
    if pin:
        body["upi_pin"] = pin
    return customer.web.put("/me/app-access", json=body)


def test_toggle_gives_60_day_access_without_consent_id(setup):
    rows = setup.ravi.web.get("/me/app-access").json()
    assert [(r["client_id"], r["upi_id"]) for r in rows] == [(setup.app.client_id, setup.ravi.upi_id)]
    assert not any(p["enabled"] for p in rows[0]["purposes"].values())

    r = _toggle(setup.ravi, setup.app, "BALANCE", True, pin="2468")
    assert r.status_code == 200, r.text
    until = datetime.fromisoformat(r.json()["purposes"]["BALANCE"]["expires_at"].replace("Z", "+00:00"))
    assert timedelta(days=59) < until - datetime.now(timezone.utc) <= timedelta(days=60)

    # no consent_id needed: the bank finds the active consent
    balance = setup.app.get(f"/upi/{setup.ravi.upi_id}/balance")
    assert balance.status_code == 200 and balance.json()["balance_cents"] == 50_000
    assert setup.app.get(f"/upi/{setup.ravi.upi_id}/statement").status_code == 403  # not switched on

    active = setup.app.get("/consents", upi_id=setup.ravi.upi_id, status="ACTIVE").json()
    assert [c["purposes"] for c in active] == [["BALANCE"]]
    assert [e["type"] for e in setup.app.get("/events").json()["items"]] == ["consent.updated"]

    r = _toggle(setup.ravi, setup.app, "BALANCE", False)
    assert r.json()["purposes"]["BALANCE"]["enabled"] is False
    assert setup.app.get(f"/upi/{setup.ravi.upi_id}/balance").status_code == 403


def test_statement_toggle_covers_the_past_year(setup):
    _toggle(setup.ravi, setup.app, "STATEMENT", True, pin="2468")
    r = setup.app.get(f"/upi/{setup.ravi.upi_id}/statement")
    assert r.status_code == 200
    assert [i["tran_type"] for i in r.json()["items"]] == ["ATM Deposit"]
    old = str((datetime.now(timezone.utc) - timedelta(days=400)).date())
    assert setup.app.get(f"/upi/{setup.ravi.upi_id}/statement", **{"from": old}).status_code == 403


def test_toggle_on_needs_the_right_pin(setup):
    assert _toggle(setup.ravi, setup.app, "BALANCE", True).json()["error"]["code"] == "PIN_INVALID"
    assert _toggle(setup.ravi, setup.app, "BALANCE", True, pin="0000").json()["error"]["code"] == "PIN_INVALID"
    assert setup.app.get(f"/upi/{setup.ravi.upi_id}/balance").status_code == 403


def test_toggle_off_keeps_other_purposes_of_an_app_requested_consent(setup):
    consent = _consent(setup, ["BALANCE", "LINK"]).json()
    setup.ravi.web.post(f"/me/consents/{consent['consent_id']}/approve", json={"upi_pin": "2468"})

    _toggle(setup.ravi, setup.app, "BALANCE", False)
    assert setup.app.get(f"/upi/{setup.ravi.upi_id}/balance").status_code == 403
    after = setup.app.get(f"/consents/{consent['consent_id']}").json()
    assert after["status"] == "ACTIVE" and after["purposes"] == ["LINK"]


def test_cannot_toggle_someone_elses_upi_or_own_app(bank, setup):
    mallory = bank.customer("Mallory", handle=f"mal{uuid.uuid4().hex[:6]}")
    body = {"client_id": setup.app.client_id, "upi_id": setup.ravi.upi_id, "purpose": "BALANCE", "enabled": False}
    assert mallory.web.put("/me/app-access", json=body).status_code == 404
    # the app's owner doesn't need (or see) toggles for its own app
    assert setup.escrow.web.get("/me/app-access").json() == []
